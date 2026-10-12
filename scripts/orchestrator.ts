// The v2 entry point: `node scripts/orchestrator.ts <subcommand>`. Node >= 22.18 runs it
// directly, with no build step. Today it has two subcommands, `status` and `start`.
//
// Every dependency comes in through `main`, so a test drives the script exactly as the
// skill calls it, with a fake process runner in place of the real one.

import { readFileSync, realpathSync } from "node:fs";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { sh as realSh, type Result, type Sh } from "./sh.ts";
import { github } from "./trackers/github.ts";
import { READY, type Issue, type Tracker } from "./trackers/tracker.ts";

const ROLES = ["heavy", "medium", "light"] as const;

type RoleName = (typeof ROLES)[number];

type Role = { harness: string; model: string; effort: string };

type Config = {
  tracker: string;
  base: string;
  max_workers: number;
  roles: Record<RoleName, Role>;
  role_labels: { heavy: string; light: string };
  heavy_touches: number;
};

const DEFAULTS: Config = {
  tracker: "github",
  base: "main",
  max_workers: 3,
  // The claude CLI's own aliases, which it resolves on every provider. A versioned id
  // such as "sonnet-5" is refused.
  roles: {
    heavy: { harness: "claude", model: "opus", effort: "high" },
    medium: { harness: "claude", model: "sonnet", effort: "medium" },
    light: { harness: "claude", model: "sonnet", effort: "low" },
  },
  role_labels: { heavy: "heavy", light: "light" },
  heavy_touches: 3,
};

const CONFIG_PATH = join("docs", "agents", "orchestrator.md");

// The gitignored file that holds the orca Run id, as `{ "run": "<id>" }`.
const RUN_PATH = join(".orchestrator", "run.json");

// The first fenced `json` block in the config doc.
const JSON_BLOCK = /^```json[ \t]*\n([\s\S]*?)^```/m;

type PartialEach<T> = { [K in keyof T]?: Partial<T[K]> };

// The config doc's JSON block over the defaults. A missing doc or a doc with no JSON
// block reads as the defaults; a block that does not parse is an error.
function readConfig(root: string): Config {
  let text: string;
  try {
    text = readFileSync(join(root, CONFIG_PATH), "utf8");
  } catch {
    return DEFAULTS;
  }
  const block = JSON_BLOCK.exec(text);
  if (!block) return DEFAULTS;
  let given: Partial<Omit<Config, "roles" | "role_labels">> & {
    roles?: PartialEach<Config["roles"]>;
    role_labels?: Partial<Config["role_labels"]>;
  };
  try {
    given = JSON.parse(block[1] ?? "");
  } catch (error) {
    throw new Error(`the json block in ${CONFIG_PATH} does not parse: ${(error as Error).message}`);
  }
  return {
    ...DEFAULTS,
    ...given,
    roles: {
      heavy: { ...DEFAULTS.roles.heavy, ...given.roles?.heavy },
      medium: { ...DEFAULTS.roles.medium, ...given.roles?.medium },
      light: { ...DEFAULTS.roles.light, ...given.roles?.light },
    },
    role_labels: { ...DEFAULTS.role_labels, ...given.role_labels },
  };
}

function trackerFor(config: Config, sh: Sh, cwd: string): Tracker {
  if (config.tracker === "github") return github(sh, cwd);
  throw new Error(`tracker "${config.tracker}" is not supported yet`);
}

// Eligible: open, ready-for-agent, unassigned or assigned to me, every blocker closed.
// Returns null for an eligible issue, or else the one reason it is not.
function whyNotEligible(tracker: Tracker, issue: Issue, me: string): string | null {
  if (!issue.open) return "closed";
  if (!issue.labels.includes(READY)) return `not ${READY}`;
  if (issue.assignees.length > 0 && !issue.assignees.includes(me)) {
    return `assigned to ${issue.assignees.join(", ")}`;
  }
  const open = tracker.blockers(issue.id).filter((id) => tracker.view(id).open);
  if (open.length > 0) return `blocked by ${open.map((id) => tracker.ref(id)).join(", ")}`;
  return null;
}

// The `## Touches` block's paths: each list item up to the next heading.
function touches(body: string): number {
  const block = /^##[ \t]+Touches[ \t]*\n([\s\S]*?)(?=^#|(?![\s\S]))/m.exec(body);
  return (block?.[1] ?? "").split("\n").filter((line) => /^[ \t]*[-*][ \t]+\S/.test(line)).length;
}

// A manual --role, then the heavy label, then the light label, then the Touches count.
function pickRole(config: Config, issue: Issue, manual: RoleName | undefined): RoleName {
  if (manual) return manual;
  if (issue.labels.includes(config.role_labels.heavy)) return "heavy";
  if (issue.labels.includes(config.role_labels.light)) return "light";
  if (touches(issue.body) >= config.heavy_touches) return "heavy";
  return "medium";
}

// The worker's whole prompt. orca adds its own preamble with the Task, the Dispatch and
// the exact `worker_done` and `ask` commands. The worker reads the issue itself.
function render(tracker: Tracker, issue: Issue, base: string, note: string | undefined): string {
  const lines = [
    `You are working on issue ${tracker.ref(issue.id)}: "${issue.title}", in the orca worktree `
      + `${worktreeName(issue.id)}, on the branch it checked out.`,
    "",
    `1. Read the issue and every comment: ${tracker.viewCommand(issue.id)}`,
    "2. Run /implement on it.",
    "3. Commit in slices: one logical change per commit, Conventional Commits.",
    `4. ${tracker.reviewStep(issue.id, base, "/pr")}`,
    "5. Never change the issue's state or labels, and never merge.",
    "6. If you are blocked on a decision only a human can make, use the orchestration `ask` "
      + "command from your preamble, and stop.",
    "7. When you finish, send worker_done --outcome succeeded with the PR URL, or --outcome "
      + "failed with the reason.",
  ];
  if (note) lines.push("", note);
  return lines.join("\n") + "\n";
}

function worktreeName(id: string): string {
  return `issue-${id.replace(/^.*#/, "")}`;
}

function readRun(root: string): string {
  let text: string;
  try {
    text = readFileSync(join(root, RUN_PATH), "utf8");
  } catch {
    throw new Error(`no orca Run: pass --run <id>, or write { "run": "<id>" } to ${RUN_PATH}`);
  }
  let run: unknown;
  try {
    run = (JSON.parse(text) as { run?: unknown }).run;
  } catch (error) {
    throw new Error(`${RUN_PATH} does not parse: ${(error as Error).message}`);
  }
  if (typeof run !== "string" || run === "") throw new Error(`${RUN_PATH} has no "run" id`);
  return run;
}

// The main checkout, which orca names the repo by. `cwd` may be a linked worktree of it.
function mainCheckout(sh: Sh, cwd: string): string {
  const git = sh("git", ["rev-parse", "--path-format=absolute", "--git-common-dir"], { cwd });
  if (git.code !== 0) throw new Error(`${cwd} is not a git checkout: ${git.stderr.trim()}`);
  return dirname(git.stdout.trim());
}

type OrcaReply = { result?: { dispatchId?: string }; error?: { message?: string } };

// The JSON an `orca --json` call printed, or an empty reply where it printed none.
function orcaReply(run: Result): OrcaReply {
  try {
    return JSON.parse(run.stdout) as OrcaReply;
  } catch {
    return {};
  }
}

// orca's own message from a failed `--json` call, or its raw output.
function orcaError(run: Result): string {
  return orcaReply(run).error?.message || run.stderr.trim() || run.stdout.trim() || `exit ${run.code}`;
}

type StartArgs = { id: string; role?: RoleName; note?: string; run?: string };

// Claim one eligible issue and start a supervised worker on it in worktree issue-N. An
// issue that is not eligible, or a role on a harness start cannot launch yet, changes
// nothing.
function start(config: Config, tracker: Tracker, sh: Sh, cwd: string, args: StartArgs, deps: Deps): number {
  const run = args.run ?? readRun(cwd);
  const issue = tracker.view(args.id);
  const ref = tracker.ref(issue.id);
  const why = whyNotEligible(tracker, issue, tracker.me());
  if (why !== null) {
    deps.err(`${ref} is not eligible: ${why}`);
    return 1;
  }
  const role = pickRole(config, issue, args.role);
  const { harness, model, effort } = config.roles[role];
  if (harness !== "claude") {
    deps.err(`${ref} is not started: its ${role} role runs on ${harness}, and start launches only claude for now`);
    return 1;
  }
  const name = worktreeName(issue.id);
  const repo = mainCheckout(sh, cwd);
  tracker.claim(issue.id);
  const worker = sh("orca", [
    "orchestration", "worker-start",
    "--spec", render(tracker, issue, config.base, args.note),
    "--task-title", name,
    "--worktree", "new-top-level",
    "--name", name,
    "--repo", `path:${repo}`,
    "--base-branch", config.base,
    "--agent", harness,
    "--model", model,
    "--effort", effort,
    "--run", run,
    "--json",
  ], { cwd });
  if (worker.code !== 0) {
    tracker.unclaim(issue.id);
    deps.err(`error: orca worker-start failed, so ${ref} is unclaimed again: ${orcaError(worker)}`);
    return 1;
  }
  deps.out(
    `started ${ref} in worktree ${name}: ${harness} ${model} @ ${effort} (${role} role), `
      + `dispatch ${orcaReply(worker).result?.dispatchId ?? "unknown"}`,
  );
  return 0;
}

// The ready queue, then each other open ready-for-agent issue with its reason.
function status(tracker: Tracker, out: (line: string) => void): number {
  const me = tracker.me();
  const ready: Issue[] = [];
  const waiting: [Issue, string][] = [];
  for (const issue of tracker.list({ label: READY })) {
    const why = whyNotEligible(tracker, issue, me);
    if (why === null) ready.push(issue);
    else waiting.push([issue, why]);
  }
  out(`ready queue (${ready.length})`);
  for (const issue of ready) out(`  ${tracker.ref(issue.id)}  ${issue.title}`);
  if (waiting.length > 0) {
    out(`not eligible (${waiting.length})`);
    for (const [issue, why] of waiting) out(`  ${tracker.ref(issue.id)}  ${issue.title}  (${why})`);
  }
  return 0;
}

export type Deps = {
  sh: Sh;
  cwd: string;
  out: (line: string) => void;
  err: (line: string) => void;
};

const USAGE = "usage: orchestrator.ts status | start N [--role heavy|medium|light] [--note TEXT] [--run ID]";

// The `start` arguments, or null where they do not parse.
function startArgs(argv: string[]): StartArgs | null {
  let parsed;
  try {
    parsed = parseArgs({
      args: argv,
      allowPositionals: true,
      options: { role: { type: "string" }, note: { type: "string" }, run: { type: "string" } },
    });
  } catch {
    return null;
  }
  const { positionals, values } = parsed;
  const role = values.role as RoleName | undefined;
  if (positionals.length !== 1 || !/^#?\d+$/.test(positionals[0] ?? "")) return null;
  if (role !== undefined && !ROLES.includes(role)) return null;
  return { id: (positionals[0] ?? "").replace("#", ""), role, note: values.note, run: values.run };
}

export function main(argv: string[], deps: Deps): number {
  const [command, ...rest] = argv;
  const args = command === "start" ? startArgs(rest) : null;
  if (!(command === "status" && rest.length === 0) && !args) {
    deps.err(USAGE);
    return 2;
  }
  try {
    const config = readConfig(deps.cwd);
    const tracker = trackerFor(config, deps.sh, deps.cwd);
    if (args) return start(config, tracker, deps.sh, deps.cwd, args, deps);
    return status(tracker, deps.out);
  } catch (error) {
    deps.err(`error: ${(error as Error).message}`);
    return 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  process.exitCode = main(process.argv.slice(2), {
    sh: realSh,
    cwd: process.cwd(),
    out: (line) => console.log(line),
    err: (line) => console.error(line),
  });
}
