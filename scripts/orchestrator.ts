// The v2 entry point: `node scripts/orchestrator.ts <subcommand>`. Node >= 22.18 runs it
// directly, with no build step. Today it has four subcommands, `status`, `start`, `tick`
// and `merge`.
//
// Every dependency comes in through `main`, so a test drives the script exactly as the
// skill calls it, with a fake process runner in place of the real one.

import { existsSync, mkdirSync, readFileSync, realpathSync, rmSync, statSync, writeFileSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { sh as realSh, type Result, type Sh } from "./sh.ts";
import { github } from "./trackers/github.ts";
import { IN_PROGRESS, NEEDS_HUMAN, READY, READY_FOR_HUMAN, type Id, type Issue, type Tracker } from "./trackers/tracker.ts";

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

// The issue a Task title or a worktree name `issue-N` names, or undefined.
function issueNamed(name: string | null | undefined): Id | undefined {
  return /^issue-(\d+)$/.exec(name ?? "")?.[1];
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

type StartArgs = { id: string; role?: RoleName; note?: string; run?: string };

type LeafArgs = { role?: RoleName; note?: string; run: string };

// `start N`: a parent claims and starts its children, and any other issue starts as a leaf.
function start(config: Config, tracker: Tracker, sh: Sh, cwd: string, args: StartArgs, deps: Deps): number {
  const leaf = { role: args.role, note: args.note, run: args.run ?? readRun(cwd) };
  const issue = tracker.view(args.id);
  if (tracker.isParent(issue.id)) return startParent(config, tracker, sh, cwd, issue, leaf, deps);
  return startLeaf(config, tracker, sh, cwd, issue, leaf, deps);
}

// Claim one eligible issue and start a supervised worker on it in worktree issue-N. An
// issue that is not eligible, or a role on a harness start cannot launch yet, changes
// nothing.
function startLeaf(config: Config, tracker: Tracker, sh: Sh, cwd: string, issue: Issue, args: LeafArgs, deps: Deps): number {
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
    "--run", args.run,
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
function drain(tracker: Tracker, sh: Sh, cwd: string, run: string, seen: Observed, deps: Deps): Set<string> {
  const handled = new Set<string>();
  const handle = orca<{ run: { coordinator_handle?: string | null } }>(sh, cwd, ["run-show", "--id", run]).run.coordinator_handle;
  if (!handle) throw new Error(`orca Run ${run} has no coordinator terminal, so its mailbox cannot be read`);
  const check = ["check", "--run", run, "--terminal", handle];
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
function fill(config: Config, tracker: Tracker, sh: Sh, cwd: string, run: string, live: Issue[], deps: Deps): void {
  let free = config.max_workers - slotsTaken(tracker, live);
  const queue = tracker.list({ label: READY });
  if (queue.length === 0) return;
  const me = tracker.me();
  for (const issue of queue) {
    const parent = tracker.isParent(issue.id);
    if ((!parent && free <= 0) || whyNotEligible(tracker, issue, me) !== null) continue;
    if (parent) claimParent(tracker, issue, deps);
    else if (startLeaf(config, tracker, sh, cwd, issue, { run }, deps) === 0) free--;
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
    const seen = observe(sh, cwd, id);
    const handled = drain(tracker, sh, cwd, id, seen, deps);
    catchDeaths(tracker, sh, cwd, seen, handled, deps);
    teardownMerged(tracker, sh, cwd, seen, deps);
    const live = tracker.list({ label: IN_PROGRESS });
    closeParents(tracker, live, deps);
    fill(config, tracker, sh, cwd, id, live, deps);
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

export type Deps = {
  sh: Sh;
  cwd: string;
  out: (line: string) => void;
  err: (line: string) => void;
};

const USAGE = "usage: orchestrator.ts status | start N [--role heavy|medium|light] [--note TEXT] [--run ID] "
  + "| tick [--run ID] | merge N [--run ID]";

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
  if (positionals.length !== 1 || !/^#?\d+$/.test(positionals[0] ?? "")) return null;
  return { id: (positionals[0] ?? "").replace("#", ""), run: values.run };
}

export function main(argv: string[], deps: Deps): number {
  const [command, ...rest] = argv;
  const args = command === "start" ? startArgs(rest) : null;
  const ticking = command === "tick" ? tickArgs(rest) : null;
  const merging = command === "merge" ? mergeArgs(rest) : null;
  if (!(command === "status" && rest.length === 0) && !args && !ticking && !merging) {
    deps.err(USAGE);
    return 2;
  }
  try {
    const config = readConfig(deps.cwd);
    const tracker = trackerFor(config, deps.sh, deps.cwd);
    if (args) return start(config, tracker, deps.sh, deps.cwd, args, deps);
    if (ticking) return tick(config, tracker, deps.sh, deps.cwd, ticking.run, deps);
    if (merging) return merge(tracker, deps.sh, deps.cwd, merging, deps);
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
