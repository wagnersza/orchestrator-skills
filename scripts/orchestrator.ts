// The v2 entry point: `node scripts/orchestrator.ts <subcommand>`. Node >= 22.18 runs it
// directly, with no build step. Today it has one subcommand, `status`.
//
// Every dependency comes in through `main`, so a test drives the script exactly as the
// skill calls it, with a fake process runner in place of the real one.

import { readFileSync, realpathSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { sh as realSh, type Sh } from "./sh.ts";
import { github } from "./trackers/github.ts";
import { READY, type Issue, type Tracker } from "./trackers/tracker.ts";

type RoleName = "heavy" | "medium" | "light";

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

const USAGE = "usage: orchestrator.ts status";

export function main(argv: string[], deps: Deps): number {
  const [command, ...rest] = argv;
  if (command !== "status" || rest.length > 0) {
    deps.err(USAGE);
    return 2;
  }
  try {
    return status(trackerFor(readConfig(deps.cwd), deps.sh, deps.cwd), deps.out);
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
