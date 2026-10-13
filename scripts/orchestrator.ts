// The v2 entry point: `node scripts/orchestrator.ts <subcommand>`. Node >= 22.18 runs it
// directly, with no build step. Today it has five subcommands, `status`, `start`, `tick`,
// `merge` and `install`.
//
// Every dependency comes in through `main`, so a test drives the script exactly as the
// skill calls it, with a fake process runner in place of the real one.

import { existsSync, mkdirSync, readFileSync, realpathSync, rmSync, statSync, writeFileSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { launchFor, launchLine, skill, useSkill, type Harness, type Launch } from "./harnesses.ts";
import { sh as realSh, type Result, type Sh } from "./sh.ts";
import { github } from "./trackers/github.ts";
import { gitlab } from "./trackers/gitlab.ts";
import { local } from "./trackers/local.ts";
import { IN_PROGRESS, NEEDS_HUMAN, READY, READY_FOR_HUMAN, worktreeName, type Id, type Issue, type Label, type Tracker } from "./trackers/tracker.ts";

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
  if (config.tracker === "gitlab") return gitlab(sh, cwd);
  if (config.tracker === "local") return local(sh, cwd, config.base);
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

// The line a resumed worker gets: its worktree already exists, so an earlier worker stopped here.
const RESUMED = "This issue was resumed. Read the latest comments first: they answer why you stopped.";

// The worker's whole prompt, with each skill named the way `harness` names one. orca adds
// its own preamble with the Task, the Dispatch and the exact `worker_done` and `ask`
// commands. The worker reads the issue itself.
function render(tracker: Tracker, harness: Harness, issue: Issue, base: string, note: string | undefined, resumed: boolean): string {
  const lines = [
    `You are working on issue ${tracker.ref(issue.id)}: "${issue.title}", in the orca worktree `
      + `${worktreeName(issue.id)}, on the branch it checked out.`,
    "",
    `1. Read the issue and every comment: ${tracker.viewCommand(issue.id)}`,
    `2. ${useSkill(harness, "implement")} on it.`,
    "3. Commit in slices: one logical change per commit, Conventional Commits.",
    `4. ${tracker.reviewStep(issue.id, base, skill(harness, "pr"))}`,
    "5. Never change the issue's state or labels, and never merge.",
    "6. If you are blocked on a decision only a human can make, use the orchestration `ask` "
      + "command from your preamble, and stop.",
    "7. When you finish, send worker_done --outcome succeeded with the PR URL, or --outcome "
      + "failed with the reason.",
  ];
  if (resumed) lines.push("", RESUMED);
  if (note) lines.push("", note);
  return lines.join("\n") + "\n";
}

// The issue a Task title or a worktree name names, or undefined: `N` for `issue-N`, and
// `<feature>/NN` for `issue-<feature>-NN`.
function issueNamed(name: string | null | undefined): Id | undefined {
  const named = /^issue-(?:(\d+)|(.+)-(\d+))$/.exec(name ?? "");
  return named?.[1] ?? (named ? `${named[2]}/${named[3]}` : undefined);
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

type OrcaReply = { result?: { dispatchId?: string }; error?: { code?: string; message?: string } };

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

// A failed orca call that found no worktree by the name it was given.
function noWorktree(run: Result): boolean {
  return orcaReply(run).error?.code === "selector_not_found";
}

// Whether orca still holds worktree `name`. Any failure but "not found" stops the start.
function worktreeExists(sh: Sh, cwd: string, name: string): boolean {
  const show = sh("orca", ["worktree", "show", "--worktree", `name:${name}`, "--json"], { cwd });
  if (show.code === 0) return true;
  if (noWorktree(show)) return false;
  throw new Error(`orca worktree show ${name} failed: ${orcaError(show)}`);
}

type StartArgs = { id: string; role?: RoleName; note?: string; run?: string };

// `from` reads the Run's coordinator handle on its first call, and only then.
type LeafArgs = { role?: RoleName; note?: string; run: string; from: () => string };

// The Run's coordinator terminal. orca wants it as the sender of each worker-start and
// each mailbox read. It still answers for a terminal that has closed since, so the loop
// runs with no session open.
function coordinatorOf(sh: Sh, cwd: string, run: string): string {
  const handle = orca<{ run: { coordinator_handle?: string | null } }>(sh, cwd, ["run-show", "--id", run]).run.coordinator_handle;
  if (!handle) throw new Error(`orca Run ${run} has no coordinator terminal, so no worker can start and its mailbox cannot be read`);
  return handle;
}

// `get` on its first call, and the same value on every call after it.
function once<T>(get: () => T): () => T {
  let value: { is: T } | undefined;
  return () => (value ??= { is: get() }).is;
}

// `start N`: a parent claims and starts its children, and any other issue starts as a leaf.
function start(config: Config, tracker: Tracker, sh: Sh, cwd: string, args: StartArgs, deps: Deps): number {
  const run = args.run ?? readRun(cwd);
  const leaf = { role: args.role, note: args.note, run, from: once(() => coordinatorOf(sh, cwd, run)) };
  const issue = tracker.view(args.id);
  if (tracker.isParent(issue.id)) return startParent(config, tracker, sh, cwd, issue, leaf, deps);
  return startLeaf(config, tracker, sh, cwd, issue, leaf, deps);
}

// Claim one eligible issue and start a supervised worker on it in worktree issue-N. An
// issue that is not eligible, or a role its harness cannot launch, changes nothing.
function startLeaf(config: Config, tracker: Tracker, sh: Sh, cwd: string, issue: Issue, args: LeafArgs, deps: Deps): number {
  const ref = tracker.ref(issue.id);
  const why = whyNotEligible(tracker, issue, tracker.me());
  if (why !== null) {
    deps.err(`${ref} is not eligible: ${why}`);
    return 1;
  }
  const role = pickRole(config, issue, args.role);
  const launch = launchFor(config.roles[role]);
  if (typeof launch === "string") {
    deps.err(`${ref} is not started: its ${role} role ${launch}`);
    return 1;
  }
  const name = worktreeName(issue.id);
  const repo = mainCheckout(sh, cwd);
  const from = args.from();
  // A worktree issue-N that is still there means an earlier worker stopped on this issue.
  // The new worker takes it over, branch and files kept. Orca rejects the creation flags on
  // an existing worktree. A worktree that is gone gets a new one from base.
  const resumed = worktreeExists(sh, cwd, name);
  tracker.claim(issue.id);
  const spec = render(tracker, launch.harness, issue, config.base, args.note, resumed);
  const placed = { name, repo, base: config.base, resumed };
  const started = launch.harness.start === "agent"
    ? startAgent(sh, cwd, launch, spec, placed, args.run, from)
    : startTerminal(sh, cwd, launch, spec, placed, args.run, from);
  if ("failed" in started) {
    tracker.unclaim(issue.id);
    deps.err(`error: ${started.failed} failed, so ${ref} is unclaimed again: ${started.why}`);
    return 1;
  }
  const { harness, model, effort, clamped } = launch;
  deps.out(
    `started ${ref} in worktree ${name}: ${harness.name} ${model} @ ${effort} (${role} role${clamped ? `; ${clamped}` : ""}), `
      + `dispatch ${orcaReply(started).result?.dispatchId ?? "unknown"}`,
  );
  return 0;
}

// Where a worker starts: worktree `name` of `repo`, new from `base` unless `resumed`.
type Placement = { name: string; repo: string; base: string; resumed: boolean };

// The `worker-start` flags that name the Task and its worktree, with the creation flags
// only for a new one.
function placementFlags(spec: string, placed: Placement, create: boolean): string[] {
  return [
    "--spec", spec,
    "--task-title", placed.name,
    ...(create
      ? ["--worktree", "new-top-level", "--name", placed.name, "--repo", `path:${placed.repo}`, "--base-branch", placed.base]
      : ["--worktree", `name:${placed.name}`]),
  ];
}

// A start step that failed, and orca's message.
type Failed = { failed: string; why: string };

// orca launches the harness itself. Returns the receipt, or the step that failed.
function startAgent(sh: Sh, cwd: string, launch: Launch, spec: string, placed: Placement, run: string, from: string): Result | Failed {
  const worker = sh("orca", [
    "orchestration", "worker-start",
    ...placementFlags(spec, placed, !placed.resumed),
    "--agent", launch.harness.name,
    ...launch.harness.flags(launch.model, launch.effort),
    "--run", run,
    "--from", from,
    "--json",
  ], { cwd });
  return worker.code === 0 ? worker : { failed: "orca worker-start", why: orcaError(worker) };
}

// The `blockedReason` orca reports for a harness held at its trust dialog.
const TRUST_BLOCKED = "agent-trust-workspace";

// How often, and how many times, a terminal start asks orca whether the trust dialog is
// up. The harness idles at boot before it draws the dialog, so one idle reading proves
// nothing, and a key sent then is lost.
const TRUST_POLLS = 30;
const TRUST_POLL_SECONDS = "1";

// Wait for the trust dialog of the harness in terminal `handle`, then send its key.
// Returns the failed call, or null. A dialog that never shows sends nothing.
function answerTrust(sh: Sh, cwd: string, handle: string, keys: string[]): Result | null {
  for (let poll = 0; poll < TRUST_POLLS; poll++) {
    if (poll > 0) sh("sleep", [TRUST_POLL_SECONDS], { cwd });
    const wait = sh("orca", ["terminal", "wait", "--terminal", handle, "--for", "tui-idle", "--timeout-ms", "5000", "--json"], { cwd });
    const blocked = (orcaReply(wait) as { result?: { wait?: { blockedReason?: string | null } } }).result?.wait?.blockedReason;
    if (blocked !== TRUST_BLOCKED) continue;
    const answer = sh("orca", ["terminal", "send", "--terminal", handle, ...keys, "--json"], { cwd });
    return answer.code === 0 ? null : answer;
  }
  return null;
}

// orca's `--agent` does not know the harness. Make the worktree where it is new, run
// the launch line in a terminal there, answer the trust dialog where the row has a key,
// then bind the terminal as a supervised worker. Returns the receipt, or the step that
// failed. A terminal whose worker did not start is closed again.
function startTerminal(sh: Sh, cwd: string, launch: Launch, spec: string, placed: Placement, run: string, from: string): Result | Failed {
  if (!placed.resumed) {
    const made = sh("orca", [
      "worktree", "create", "--name", placed.name, "--repo", `path:${placed.repo}`, "--base-branch", placed.base, "--no-parent", "--json",
    ], { cwd });
    if (made.code !== 0) return { failed: `orca worktree create ${placed.name}`, why: orcaError(made) };
  }
  const command = launchLine(launch).map((word) => (/^[\w@%+=:,./-]+$/.test(word) ? word : shellQuote(word))).join(" ");
  const terminal = sh("orca", [
    "terminal", "create", "--worktree", `name:${placed.name}`, "--title", placed.name, "--command", command, "--json",
  ], { cwd });
  if (terminal.code !== 0) return { failed: `orca terminal create in ${placed.name}`, why: orcaError(terminal) };
  const handle = (JSON.parse(terminal.stdout) as { result: { terminal: { handle: string } } }).result.terminal.handle;
  const fail = (failed: string, call: Result): Failed => {
    sh("orca", ["terminal", "close", "--terminal", handle, "--json"], { cwd });
    return { failed, why: orcaError(call) };
  };
  const answer = launch.harness.trust ? answerTrust(sh, cwd, handle, launch.harness.trust) : null;
  if (answer) return fail(`answering the trust dialog of ${launch.harness.name}`, answer);
  const worker = sh("orca", [
    "orchestration", "worker-start",
    ...placementFlags(spec, placed, false),
    "--terminal", handle,
    "--run", run,
    "--from", from,
    "--json",
  ], { cwd });
  return worker.code === 0 ? worker : fail("orca worker-start", worker);
}

// The slots `live`, the in-progress issues, take: one per issue that is not a parent.
function slotsTaken(tracker: Tracker, live: Issue[]): number {
  return live.filter((issue) => !tracker.isParent(issue.id)).length;
}

// Claim an eligible parent, which takes no worker and no slot.
function claimParent(tracker: Tracker, parent: Issue, deps: Deps): void {
  tracker.claim(parent.id);
  deps.out(`claimed parent ${tracker.ref(parent.id)}: no worker, no slot`);
}

// `start P` on a parent: claim it, or keep my claim, then start each open child that is
// eligible, in order, up to the free slots. A child that waits gets a line with its
// reason. A child that is a parent itself waits for its own `start`.
function startParent(config: Config, tracker: Tracker, sh: Sh, cwd: string, parent: Issue, args: LeafArgs, deps: Deps): number {
  const ref = tracker.ref(parent.id);
  const me = tracker.me();
  const mine = parent.open && parent.labels.includes(IN_PROGRESS)
    && (parent.assignees.length === 0 || parent.assignees.includes(me));
  if (mine) {
    deps.out(`parent ${ref} is already claimed`);
  } else {
    const why = whyNotEligible(tracker, parent, me);
    if (why !== null) {
      deps.err(`${ref} is not eligible: ${why}`);
      return 1;
    }
    claimParent(tracker, parent, deps);
  }
  let free = config.max_workers - slotsTaken(tracker, tracker.list({ label: IN_PROGRESS }));
  let code = 0;
  for (const id of tracker.children(parent.id)) {
    const child = tracker.view(id);
    if (!child.open) continue;
    const why = tracker.isParent(id) ? "it is a parent, so it needs its own start" : whyNotEligible(tracker, child, me);
    if (why !== null || free <= 0) {
      deps.out(`${tracker.ref(id)} waits: ${why ?? "no free slot"}`);
      continue;
    }
    if (startLeaf(config, tracker, sh, cwd, child, args, deps) === 0) free--;
    else code = 1;
  }
  return code;
}

// Close each in-progress parent, unassigned or mine, once it has children and every one
// is closed. The comment lists each child's PR. The comment comes before the close, so a
// replay before the close posts it again, and a replay after it finds no parent.
function closeParents(tracker: Tracker, live: Issue[], deps: Deps): void {
  for (const parent of live) {
    if (!tracker.isParent(parent.id)) continue;
    if (parent.assignees.length > 0 && !parent.assignees.includes(tracker.me())) continue;
    const children = tracker.children(parent.id);
    if (children.length === 0 || children.some((id) => tracker.view(id).open)) continue;
    const lines = children.map((id) => {
      const pr = tracker.prFor(id);
      return `- ${tracker.ref(id)}: ${pr ? `PR ${pr.ref}` : "no PR"}`;
    });
    tracker.close(parent.id, `Every child of this story is closed, so the tick closes it.\n\n${lines.join("\n")}`);
    deps.out(`${tracker.ref(parent.id)}: closed, every child is closed (${children.map((id) => tracker.ref(id)).join(", ")})`);
  }
}

// The tick lock. A live tick holds it for seconds, so one older than five minutes is
// left over from a crash.
const LOCK_PATH = join(".orchestrator", "tick.lock");
const STALE_MS = 5 * 60 * 1000;

// Take the lock, or return false where a live tick holds it.
function takeLock(root: string): boolean {
  const path = join(root, LOCK_PATH);
  mkdirSync(dirname(path), { recursive: true });
  if (createLock(path)) return true;
  let age: number;
  try {
    age = Date.now() - statSync(path).mtimeMs;
  } catch {
    return createLock(path);
  }
  if (age < STALE_MS) return false;
  rmSync(path, { force: true });
  return createLock(path);
}

// Create the lock file exclusively, or return false where it exists.
function createLock(path: string): boolean {
  try {
    writeFileSync(path, `${process.pid}\n`, { flag: "wx" });
    return true;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "EEXIST") return false;
    throw error;
  }
}

// One `orca orchestration --json` call's `result`, or an error with orca's message.
function orca<T>(sh: Sh, cwd: string, args: string[]): T {
  const call = sh("orca", ["orchestration", ...args, "--json"], { cwd });
  if (call.code !== 0) throw new Error(`orca orchestration ${args[0]} failed: ${orcaError(call)}`);
  return (JSON.parse(call.stdout) as { result: T }).result;
}

type Message = {
  id: string;
  type: string;
  subject?: string;
  body?: string;
  from_handle?: string;
  payload?: string | null;
};

type Task = { id: string; task_title?: string | null; result?: string | null };

type Worker = {
  dispatchId: string;
  taskId?: string;
  resource?: { worktreeId?: string } | null;
  projection?: { liveness?: { verdict?: string } };
};

// What the tick reads from orca before it acts: each Task by id, and each Dispatch,
// newest first, with the issue it works on.
type Observed = { tasks: Map<string, Task>; workers: Worker[]; issueOf: (task?: string, dispatch?: string) => Id | undefined };

function observe(sh: Sh, cwd: string, run: string): Observed {
  const tasks = new Map(orca<{ tasks: Task[] }>(sh, cwd, ["task-list", "--run", run]).tasks.map((t) => [t.id, t]));
  const workers: Worker[] = [];
  let cursor: string | null | undefined;
  do {
    const page = orca<{ workers: Worker[]; page?: { nextCursor?: string | null } }>(
      sh, cwd, ["worker-list", "--run", run, ...(cursor ? ["--cursor", cursor] : [])],
    );
    workers.push(...page.workers);
    cursor = page.page?.nextCursor;
  } while (cursor);
  const byDispatch = new Map(workers.map((w) => [w.dispatchId, w]));
  // By Task title, then by worktree name, and never by a message's text.
  const issueOf = (task?: string, dispatch?: string) => {
    const worker = dispatch ? byDispatch.get(dispatch) : undefined;
    return issueNamed(tasks.get(task ?? worker?.taskId ?? "")?.task_title)
      ?? issueNamed(basename(worker?.resource?.worktreeId ?? ""));
  };
  return { tasks, workers, issueOf };
}

// A message's payload, which orca sends as a JSON string.
function payloadOf(message: Message): { taskId?: string; dispatchId?: string; outcome?: string; options?: string[] } {
  try {
    return JSON.parse(message.payload ?? "{}") ?? {};
  } catch {
    return {};
  }
}

// The worker's own text as a Markdown quote.
function quote(message: Message): string {
  const text = message.body?.trim() || message.subject?.trim() || "(no text)";
  return text.split("\n").map((line) => `> ${line}`.trimEnd()).join("\n");
}

const RESUME = "Answer here, then relabel `ready-for-agent` to resume. The worktree is kept.";

type Transition = { to: string; why: string; comment?: string; orca?: "worker-release" | "worker-stop" };

// The transition one mailbox message asks for, or null for a type the tick ignores.
function transitionFor(tracker: Tracker, id: Id, message: Message): Transition | null {
  const payload = payloadOf(message);
  if (message.type === "worker_done" && payload.outcome === "succeeded") {
    const pr = tracker.prFor(id);
    if (pr?.open) return { to: READY_FOR_HUMAN, why: `worker_done succeeded, PR ${pr.ref}`, orca: "worker-release" };
    return {
      to: NEEDS_HUMAN,
      why: "worker_done succeeded with no open PR",
      comment: `The worker reported success, but no open PR closes this issue. Its report:\n\n${quote(message)}\n\n${RESUME}`,
      orca: "worker-release",
    };
  }
  if (message.type === "worker_done") {
    return {
      to: NEEDS_HUMAN,
      why: "worker_done failed",
      comment: `The worker reported a failure:\n\n${quote(message)}\n\n${RESUME}`,
      orca: "worker-release",
    };
  }
  if (message.type === "question") {
    const options = payload.options?.length ? `\n\nIts options: ${payload.options.map((o) => `\`${o}\``).join(", ")}.` : "";
    return {
      to: NEEDS_HUMAN,
      why: "question",
      comment: `The worker asked a question, and the tick stopped it:\n\n${quote(message)}${options}\n\n${RESUME}`,
      orca: "worker-stop",
    };
  }
  if (message.type === "escalation") {
    return {
      to: NEEDS_HUMAN,
      why: "escalation",
      comment: `The worker escalated, and the tick stopped it:\n\n${quote(message)}\n\n${RESUME}`,
      orca: "worker-stop",
    };
  }
  return null;
}

// Apply one transition to an in-progress issue. The orca call and the comment come
// first and the label last, so a replay before the label redoes them, and a replay
// after it finds the issue out of in-progress and writes nothing.
function apply(tracker: Tracker, sh: Sh, cwd: string, issue: Issue, step: Transition, dispatch: string | undefined, deps: Deps): void {
  const ref = tracker.ref(issue.id);
  const done: string[] = [];
  if (step.orca && dispatch) {
    const call = sh("orca", ["orchestration", step.orca, "--dispatch", dispatch, "--json"], { cwd });
    if (call.code === 0) done.push(step.orca === "worker-stop" ? `stopped ${dispatch}` : `released ${dispatch}`);
    else deps.err(`tick: ${ref}: orca ${step.orca} ${dispatch} failed: ${orcaError(call)}`);
  }
  if (step.comment) {
    tracker.comment(issue.id, step.comment);
    done.push("commented");
  }
  tracker.setState(issue.id, IN_PROGRESS, step.to);
  deps.out(`${ref}: ${IN_PROGRESS} -> ${step.to} (${step.why})${done.length ? `; ${done.join(", ")}` : ""}`);
}

// The in-progress issue `id` names, or null with a line saying why the tick skips it.
function inProgress(tracker: Tracker, id: Id, what: string, deps: Deps): Issue | null {
  const issue = tracker.view(id);
  if (issue.open && issue.labels.includes(IN_PROGRESS)) return issue;
  deps.out(`${tracker.ref(id)}: ${what} changes nothing, the issue is not ${IN_PROGRESS}`);
  return null;
}

// Drain the Run's mailbox without waiting. Each batch is acknowledged only after every
// message in it is applied, so a crash replays the batch, and the replay is a no-op.
function drain(tracker: Tracker, sh: Sh, cwd: string, run: string, from: () => string, seen: Observed, deps: Deps): Set<string> {
  const handled = new Set<string>();
  const check = ["check", "--run", run, "--terminal", from()];
  let batch = orca<{ deliveryId?: string | null; messages?: Message[] }>(sh, cwd, check);
  while (batch.deliveryId) {
    for (const message of batch.messages ?? []) {
      const payload = payloadOf(message);
      const dispatch = payload.dispatchId
        ?? (message.from_handle?.startsWith("dispatch:") ? message.from_handle.slice("dispatch:".length) : undefined);
      if (!["worker_done", "question", "escalation"].includes(message.type)) continue;
      if (dispatch) handled.add(dispatch);
      const id = seen.issueOf(payload.taskId, dispatch);
      if (id === undefined) {
        deps.err(`tick: ${message.id} (${message.type}) names no issue-N Task or worktree, so it is skipped`);
        continue;
      }
      const issue = inProgress(tracker, id, `${message.type} ${message.id}`, deps);
      const step = issue && transitionFor(tracker, id, message);
      if (issue && step) apply(tracker, sh, cwd, issue, step, dispatch, deps);
    }
    batch = orca(sh, cwd, [...check, "--ack", batch.deliveryId]);
  }
  return handled;
}

// The newest Dispatch of each issue that exited with no worker_done moves the issue to
// needs-human. An older Dispatch is a worker an earlier claim already replaced.
function catchDeaths(tracker: Tracker, sh: Sh, cwd: string, seen: Observed, handled: Set<string>, deps: Deps): void {
  const newest = new Map<Id, Worker>();
  for (const worker of seen.workers) {
    const id = seen.issueOf(undefined, worker.dispatchId);
    if (id !== undefined && !newest.has(id)) newest.set(id, worker);
  }
  for (const [id, worker] of newest) {
    if (worker.projection?.liveness?.verdict !== "exited" || handled.has(worker.dispatchId)) continue;
    if (reported(seen.tasks.get(worker.taskId ?? ""))) continue;
    const issue = tracker.view(id);
    if (!issue.open || !issue.labels.includes(IN_PROGRESS)) continue;
    apply(tracker, sh, cwd, issue, {
      to: NEEDS_HUMAN,
      why: "worker exited without reporting",
      comment: `The worker exited without sending worker_done, so it left no report. ${RESUME}`,
    }, undefined, deps);
  }
}

// A Task its worker settled with worker_done, whose report orca keeps as the result.
function reported(task: Task | undefined): boolean {
  try {
    return (JSON.parse(task?.result ?? "null") as { provenance?: string } | null)?.provenance === "worker_report";
  } catch {
    return false;
  }
}

// Walk the ready queue in order. An eligible parent is claimed, with no worker and no
// slot, so a full house still claims it. An eligible leaf starts while a slot is free:
// `max_workers` minus the in-progress issues in `live` that are not parents. An issue
// that is not eligible keeps its place in the queue, and an issue whose worker does not
// start frees its slot again.
function fill(config: Config, tracker: Tracker, sh: Sh, cwd: string, leaf: LeafArgs, live: Issue[], deps: Deps): void {
  let free = config.max_workers - slotsTaken(tracker, live);
  const queue = tracker.list({ label: READY });
  if (queue.length === 0) return;
  const me = tracker.me();
  for (const issue of queue) {
    const parent = tracker.isParent(issue.id);
    if ((!parent && free <= 0) || whyNotEligible(tracker, issue, me) !== null) continue;
    if (parent) claimParent(tracker, issue, deps);
    else if (startLeaf(config, tracker, sh, cwd, issue, leaf, deps) === 0) free--;
  }
}

// The precheck of the orca automation. It observes the workers, moves their issues'
// state labels, tears down each issue merged on the tracker, closes each parent whose
// children are all closed, then fills the free slots from the ready queue. It exits
// non-zero on every path, so the automation's agent never runs.
function tick(config: Config, tracker: Tracker, sh: Sh, cwd: string, run: string | undefined, deps: Deps): number {
  if (!takeLock(cwd)) {
    deps.err(`tick: another tick holds ${LOCK_PATH}, so this one exits`);
    return 1;
  }
  try {
    const id = run ?? readRun(cwd);
    const from = once(() => coordinatorOf(sh, cwd, id));
    const seen = observe(sh, cwd, id);
    const handled = drain(tracker, sh, cwd, id, from, seen, deps);
    catchDeaths(tracker, sh, cwd, seen, handled, deps);
    teardownMerged(tracker, sh, cwd, seen, deps);
    const live = tracker.list({ label: IN_PROGRESS });
    closeParents(tracker, live, deps);
    fill(config, tracker, sh, cwd, { run: id, from }, live, deps);
  } finally {
    rmSync(join(cwd, LOCK_PATH), { force: true });
  }
  return 1;
}

// Why worktree issue-N is not safe to remove, or null. A missing worktree holds no work.
function uncommitted(sh: Sh, cwd: string, id: Id): string | null {
  const name = worktreeName(id);
  const show = sh("orca", ["worktree", "show", "--worktree", `name:${name}`, "--json"], { cwd });
  if (show.code !== 0) {
    if (noWorktree(show)) return null;
    throw new Error(`orca worktree show ${name} failed: ${orcaError(show)}`);
  }
  const path = (JSON.parse(show.stdout) as { result: { worktree: { path: string } } }).result.worktree.path;
  const git = sh("git", ["status", "--porcelain"], { cwd: path });
  if (git.code !== 0) throw new Error(`git status in ${path} failed: ${git.stderr.trim() || `exit ${git.code}`}`);
  return git.stdout.trim() === "" ? null : `worktree ${name} has uncommitted work`;
}

// Tear down a merged issue: release its newest worker, remove worktree issue-N, then
// drop the state label and close the issue in one write. A failed release is reported
// and passed. A failed removal throws before the write, so the issue keeps
// ready-for-human and the next tick tries again. A replay finds each step done.
function teardown(tracker: Tracker, sh: Sh, cwd: string, seen: Observed, issue: Issue, deps: Deps): void {
  const ref = tracker.ref(issue.id);
  const done: string[] = [];
  const worker = seen.workers.find((w) => seen.issueOf(undefined, w.dispatchId) === issue.id);
  if (worker) {
    const call = sh("orca", ["orchestration", "worker-release", "--dispatch", worker.dispatchId, "--json"], { cwd });
    if (call.code === 0) done.push(`released ${worker.dispatchId}`);
    else deps.err(`${ref}: orca worker-release ${worker.dispatchId} failed: ${orcaError(call)}`);
  }
  const name = worktreeName(issue.id);
  const rm = sh("orca", ["worktree", "rm", "--worktree", `name:${name}`, "--json"], { cwd });
  if (rm.code === 0) done.push(`removed worktree ${name}`);
  else if (!noWorktree(rm)) {
    throw new Error(`orca worktree rm ${name} failed, so ${ref} keeps ${READY_FOR_HUMAN} for the next tick: ${orcaError(rm)}`);
  }
  done.push(`dropped ${READY_FOR_HUMAN}`, "closed");
  tracker.close(issue.id, `The PR is merged, so this issue is torn down: ${done.join(", ")}.`);
  deps.out(`${ref}: torn down; ${done.join(", ")}`);
}

type MergeArgs = { id: string; run?: string };

// `merge N`: refuse in one line, changing nothing, unless the issue is ready-for-human,
// its worktree is clean and the tracker takes the merge. Teardown runs only once the
// tracker confirms the merge, because a merge command can fail after the merge landed.
function merge(tracker: Tracker, sh: Sh, cwd: string, args: MergeArgs, deps: Deps): number {
  const run = args.run ?? readRun(cwd);
  const issue = tracker.view(args.id);
  const ref = tracker.ref(issue.id);
  const refuse = (why: string) => {
    deps.err(`${ref} is not merged: ${why}`);
    return 1;
  };
  const why = issue.labels.includes(READY_FOR_HUMAN) ? uncommitted(sh, cwd, issue.id) : `not ${READY_FOR_HUMAN}`;
  if (why !== null) return refuse(why);
  let failure: string | undefined;
  try {
    const refusal = tracker.merge(issue.id);
    if (refusal !== null) return refuse(refusal);
  } catch (error) {
    failure = (error as Error).message;
  }
  if (!tracker.isMerged(issue.id)) {
    deps.err(`error: ${ref} is not confirmed merged, so nothing is torn down${failure ? `: ${failure}` : ""}`);
    return 1;
  }
  deps.out(`${ref}: merged${failure ? `, though the merge command failed: ${failure}` : ""}`);
  teardown(tracker, sh, cwd, observe(sh, cwd, run), issue, deps);
  return 0;
}

// Tear down each ready-for-human issue, unassigned or mine, whose PR was merged on the
// tracker. A closed one counts, because `Closes #N` closes the issue at the merge. A
// teardown that fails is reported, and the tick goes on.
function teardownMerged(tracker: Tracker, sh: Sh, cwd: string, seen: Observed, deps: Deps): void {
  for (const issue of tracker.list({ label: READY_FOR_HUMAN, closed: true })) {
    if (issue.assignees.length > 0 && !issue.assignees.includes(tracker.me())) continue;
    if (!tracker.isMerged(issue.id)) continue;
    try {
      teardown(tracker, sh, cwd, seen, issue, deps);
    } catch (error) {
      deps.err(`tick: ${(error as Error).message}`);
    }
  }
}

// The state labels of an issue the loop has claimed and not yet closed.
const LIVE = [IN_PROGRESS, NEEDS_HUMAN, READY_FOR_HUMAN];

// Each claimed issue, unassigned or mine, with its state, role, harness, liveness and
// PR, then the ready queue, then each other open ready-for-agent issue with its reason.
// Liveness is the newest worker's, and "-" where no Run is saved.
function status(config: Config, tracker: Tracker, sh: Sh, cwd: string, out: (line: string) => void): number {
  const me = tracker.me();
  const live = LIVE.flatMap((label) => tracker.list({ label })
    .filter((issue) => issue.assignees.length === 0 || issue.assignees.includes(me))
    .map((issue): [Issue, string] => [issue, label]));
  if (live.length > 0) {
    const seen = existsSync(join(cwd, RUN_PATH)) ? observe(sh, cwd, readRun(cwd)) : undefined;
    const rows = [["issue", "state", "role", "harness", "liveness", "pr", "title"]];
    for (const [issue, label] of live) {
      const role = pickRole(config, issue, undefined);
      const worker = seen?.workers.find((w) => seen.issueOf(undefined, w.dispatchId) === issue.id);
      const liveness = seen ? worker?.projection?.liveness?.verdict ?? (worker ? "unknown" : "none") : "-";
      const pr = tracker.prFor(issue.id)?.ref ?? "-";
      rows.push([tracker.ref(issue.id), label, role, config.roles[role].harness, liveness, pr, issue.title]);
    }
    const widths = rows[0]?.map((_, column) => Math.max(...rows.map((row) => row[column]?.length ?? 0))) ?? [];
    out(`live (${live.length})`);
    for (const row of rows) out(`  ${row.map((cell, column) => cell.padEnd(widths[column] ?? 0)).join("  ").trimEnd()}`);
  }
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

// The labels the loop writes, then the role labels the config names.
function labelsFor(config: Config): Label[] {
  const labels = [
    { name: READY, color: "0E8A16", description: "Ready for the orchestrator to pick up" },
    { name: IN_PROGRESS, color: "FBCA04", description: "Claimed: a worker is on it" },
    { name: NEEDS_HUMAN, color: "D93F0B", description: "The worker failed, asked, escalated or died" },
    { name: READY_FOR_HUMAN, color: "1D76DB", description: "A PR is open for review" },
    { name: config.role_labels.heavy, color: "5319E7", description: "Run on the heavy role" },
    { name: config.role_labels.light, color: "C5DEF5", description: "Run on the light role" },
  ];
  return labels.filter((label, i) => labels.findIndex((l) => l.name === label.name) === i);
}

// The automation whose precheck is the tick.
const AUTOMATION = "orchestrator-tick";
const EVERY_MINUTE = "* * * * *";
// orca's default of 60 seconds can kill a tick that starts a few workers. A tick that
// lives as long as its lock never sees a second tick take that lock.
const PRECHECK_TIMEOUT = String(STALE_MS / 1000);

// This script by absolute path, which the precheck names.
const SCRIPT = fileURLToPath(import.meta.url);

function shellQuote(word: string): string {
  return `'${word.replaceAll("'", `'\\''`)}'`;
}

// The precheck: the tick, with node, the script and the repo as absolute paths, because
// orca runs it later in a shell that saw no assignment.
function precheckFor(root: string): string {
  return `cd ${shellQuote(root)} && ${shellQuote(process.execPath)} ${shellQuote(SCRIPT)} tick`;
}

type Automation = {
  id: string;
  name: string;
  enabled?: boolean;
  rrule?: string;
  precheck?: { command?: string; timeoutSeconds?: number } | null;
  runContext?: { path?: string } | null;
};

// The saved Run, kept while orca has it with a coordinator, else a new one saved in its
// place. A run file that is missing or does not parse counts as no Run. orca binds the
// new Run to the terminal that runs install.
function ensureRun(sh: Sh, cwd: string, deps: Deps): void {
  let saved: string | undefined;
  try {
    saved = readRun(cwd);
  } catch {
    saved = undefined;
  }
  let why = "";
  if (saved) {
    const show = sh("orca", ["orchestration", "run-show", "--id", saved, "--json"], { cwd });
    const reply = orcaReply(show) as OrcaReply & { result?: { run?: { coordinator_handle?: string | null } } };
    if (show.code === 0 && reply.result?.run?.coordinator_handle) {
      deps.out(`run ${saved}: present`);
      return;
    }
    if (show.code !== 0 && reply.error?.code !== "run_not_found") throw new Error(`orca run-show ${saved} failed: ${orcaError(show)}`);
    why = `, in place of ${saved}, which ${show.code === 0 ? "has no coordinator terminal" : "orca no longer has"}`;
  }
  const run = orca<{ run: { id: string } }>(sh, cwd, ["run-create", "--objective", `orchestrator loop for ${basename(cwd)}`]).run.id;
  mkdirSync(join(cwd, ".orchestrator"), { recursive: true });
  writeFileSync(join(cwd, RUN_PATH), `${JSON.stringify({ run })}\n`);
  deps.out(`run ${run}: created${why}, saved to ${RUN_PATH}`);
}

// The automation for this repo, created where it is missing, and repaired where its
// precheck, its timeout, its trigger or its switch differs.
function ensureAutomation(sh: Sh, cwd: string, deps: Deps): void {
  const repo = mainCheckout(sh, cwd);
  const precheck = precheckFor(cwd);
  const list = sh("orca", ["automations", "list", "--json"], { cwd });
  if (list.code !== 0) throw new Error(`orca automations list failed: ${orcaError(list)}`);
  const found = (JSON.parse(list.stdout) as { result: { automations: Automation[] } }).result.automations
    .find((a) => a.name === AUTOMATION && a.runContext?.path === repo);
  const prompt = "The precheck is the whole tick, and it always exits non-zero, so this agent never runs. Do nothing.";
  if (!found) {
    const create = sh("orca", [
      "automations", "create",
      "--name", AUTOMATION,
      "--trigger", EVERY_MINUTE,
      "--precheck", precheck,
      "--precheck-timeout", PRECHECK_TIMEOUT,
      "--prompt", prompt,
      "--provider", "claude",
      "--workspace", `path:${cwd}`,
      "--enabled",
      "--json",
    ], { cwd });
    if (create.code !== 0) throw new Error(`orca automations create failed: ${orcaError(create)}`);
    const id = (JSON.parse(create.stdout) as { result: { automation: { id: string } } }).result.automation.id;
    deps.out(`automation ${AUTOMATION}: created (${id}), precheck ${precheck}`);
    return;
  }
  const same = found.precheck?.command === precheck && String(found.precheck.timeoutSeconds) === PRECHECK_TIMEOUT;
  if (same && found.rrule === EVERY_MINUTE && found.enabled) {
    deps.out(`automation ${AUTOMATION}: present (${found.id})`);
    return;
  }
  const edit = sh("orca", [
    "automations", "edit", "--id", found.id, "--trigger", EVERY_MINUTE,
    "--precheck", precheck, "--precheck-timeout", PRECHECK_TIMEOUT, "--enabled", "--json",
  ], { cwd });
  if (edit.code !== 0) throw new Error(`orca automations edit ${found.id} failed: ${orcaError(edit)}`);
  deps.out(`automation ${AUTOMATION}: repaired (${found.id}), precheck ${precheck}`);
}

// `install`: labels, then the Run, then the automation, then one tick through the exact
// precheck string, as proof it runs. Each step that finds its part present creates
// nothing, so a re-run repairs a broken install and duplicates nothing.
function install(config: Config, tracker: Tracker, sh: Sh, cwd: string, deps: Deps): number {
  const created = new Set(tracker.ensureLabels(labelsFor(config)));
  for (const label of labelsFor(config)) deps.out(`label ${label.name}: ${created.has(label.name) ? "created" : "present"}`);
  ensureRun(sh, cwd, deps);
  ensureAutomation(sh, cwd, deps);
  // The tick exits 1 on every path. Any other code, or an `error:` line, is a failure.
  const proof = sh("sh", ["-c", precheckFor(cwd)], { cwd });
  const lines = [...proof.stdout.split("\n"), ...proof.stderr.split("\n")].filter((line) => line.trim() !== "");
  const ok = proof.code === 1 && !lines.some((line) => line.startsWith("error:"));
  deps.out(`tick: exit ${proof.code}, ${ok ? "the precheck works" : "the precheck fails"}`);
  for (const line of lines) deps.out(`  ${line}`);
  return ok ? 0 : 1;
}

export type Deps = {
  sh: Sh;
  cwd: string;
  out: (line: string) => void;
  err: (line: string) => void;
};

const USAGE = "usage: orchestrator.ts status | start N [--role heavy|medium|light] [--note TEXT] [--run ID] "
  + "| tick [--run ID] | merge N [--run ID] | install";

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
  if (positionals.length !== 1) return null;
  if (role !== undefined && !ROLES.includes(role)) return null;
  return { id: positionals[0] ?? "", role, note: values.note, run: values.run };
}

// The `tick` arguments, or null where they do not parse.
function tickArgs(argv: string[]): { run?: string } | null {
  try {
    return parseArgs({ args: argv, options: { run: { type: "string" } } }).values;
  } catch {
    return null;
  }
}

// The `merge` arguments, or null where they do not parse.
function mergeArgs(argv: string[]): MergeArgs | null {
  let parsed;
  try {
    parsed = parseArgs({ args: argv, allowPositionals: true, options: { run: { type: "string" } } });
  } catch {
    return null;
  }
  const { positionals, values } = parsed;
  if (positionals.length !== 1) return null;
  return { id: positionals[0] ?? "", run: values.run };
}

// The id a command-line argument names on `tracker`, or null where it names none: `N`
// or `#N`, and on the local tracker `<feature>/NN`, or `<feature>` for its spec.
function idArg(tracker: string, arg: string): Id | null {
  if (tracker === "local") return /^[A-Za-z0-9_][\w.-]*(?:\/\d+)?$/.test(arg) ? arg : null;
  return /^#?(\d+)$/.exec(arg)?.[1] ?? null;
}

export function main(argv: string[], deps: Deps): number {
  const [command, ...rest] = argv;
  const args = command === "start" ? startArgs(rest) : null;
  const ticking = command === "tick" ? tickArgs(rest) : null;
  const merging = command === "merge" ? mergeArgs(rest) : null;
  const bare = (command === "status" || command === "install") && rest.length === 0;
  if (!bare && !args && !ticking && !merging) {
    deps.err(USAGE);
    return 2;
  }
  try {
    const config = readConfig(deps.cwd);
    const target = args ?? merging;
    if (target) {
      const id = idArg(config.tracker, target.id);
      if (id === null) {
        deps.err(USAGE);
        return 2;
      }
      target.id = id;
    }
    const tracker = trackerFor(config, deps.sh, deps.cwd);
    if (args) return start(config, tracker, deps.sh, deps.cwd, args, deps);
    if (ticking) return tick(config, tracker, deps.sh, deps.cwd, ticking.run, deps);
    if (merging) return merge(tracker, deps.sh, deps.cwd, merging, deps);
    if (command === "install") return install(config, tracker, deps.sh, deps.cwd, deps);
    return status(config, tracker, deps.sh, deps.cwd, deps.out);
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
