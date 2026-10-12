// `status` and `start` driven through the entry point, with a fake runner that replays
// recorded `gh api` and `orca` JSON and records every call.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, utimesSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { main } from "./orchestrator.ts";
import type { Result, Sh } from "./sh.ts";

const HOME = "https://api.github.com/repos/wagnersza/orchestrator-skills";

// Issue 349 as `gh api repos/{owner}/{repo}/issues/349` returned it, trimmed to the
// fields the backend reads and a few beside them.
const RECORDED = {
  url: `${HOME}/issues/349`,
  repository_url: HOME,
  html_url: "https://github.com/wagnersza/orchestrator-skills/issues/349",
  number: 349,
  title: "v2 tracer: status reads the ready queue from GitHub",
  labels: [{ id: 11684709514, name: "ready-for-agent", color: "1D76DB" }],
  state: "open",
  assignees: [] as { login: string }[],
  issue_dependencies_summary: { blocked_by: 0, total_blocked_by: 0, blocking: 1, total_blocking: 1 },
  sub_issues_summary: { total: 0, completed: 0, percent_completed: 0 },
  body: "## Parent\n\n#348\n\n## What to build\n\nThe first tracer bullet f",
};

type Fixture = {
  title?: string;
  labels?: string[];
  state?: string;
  assignees?: string[];
  body?: string;
  blockedBy?: number;
  // The native sub-issues the summary counts.
  subIssues?: number;
  repo?: string;
  pr?: boolean;
};

function issue(number: number, fixture: Fixture = {}) {
  const repo = fixture.repo ?? HOME;
  return {
    ...RECORDED,
    url: `${repo}/issues/${number}`,
    repository_url: repo,
    number,
    title: fixture.title ?? `issue ${number}`,
    ...(fixture.labels ? { labels: fixture.labels.map((name) => ({ name })) } : {}),
    state: fixture.state ?? "open",
    assignees: (fixture.assignees ?? []).map((login) => ({ login })),
    issue_dependencies_summary: {
      ...RECORDED.issue_dependencies_summary,
      blocked_by: fixture.blockedBy ?? 0,
      total_blocked_by: fixture.blockedBy ?? 0,
    },
    sub_issues_summary: { total: fixture.subIssues ?? 0, completed: 0, percent_completed: 0 },
    body: fixture.body ?? RECORDED.body,
    ...(fixture.pr ? { pull_request: { url: `${repo}/pulls/${number}` } } : {}),
  };
}

const USAGE = "usage: orchestrator.ts status | start N [--role heavy|medium|light] [--note TEXT] [--run ID] | tick [--run ID]";
const ME = "gh api user --jq .login";
const LIST_OF = (label: string) => `gh api --paginate --slurp repos/{owner}/{repo}/issues?state=open&labels=${label}&per_page=100`;
const LIST = LIST_OF("ready-for-agent");
// The three lists status reads before the ready queue, and replies that find nothing live.
const LIVE = ["in-progress", "needs-human", "ready-for-human"].map(LIST_OF);
const NO_LIVE = Object.fromEntries(LIVE.map((line) => [line, [[]]]));
const VIEW = (n: number) => `gh api repos/{owner}/{repo}/issues/${n}`;
const NATIVE = (n: number) =>
  `gh api --paginate --slurp repos/{owner}/{repo}/issues/${n}/dependencies/blocked_by?per_page=100`;
// The one read of every issue that finds the children by `## Parent` line.
const SCAN = "gh api --paginate --slurp repos/{owner}/{repo}/issues?state=all&per_page=100";
const SUB_ISSUES = (n: number) => `gh api --paginate --slurp repos/{owner}/{repo}/issues/${n}/sub_issues?per_page=100`;

// A failed command, for a reply. A command that succeeds replies with its stdout.
type Failure = { fail: Result };

// A runner that answers each known command line with its recorded output, and fails
// any other call, the way `gh` fails on a path it does not know. A key that ends in
// " *" answers every line it prefixes. A reply that is a function gets the calls so far,
// so a list can change after a write.
function fakeRunner(replies: Record<string, unknown>) {
  const calls: string[] = [];
  const argvs: string[][] = [];
  const inputs: (string | undefined)[] = [];
  const sh: Sh = (cmd, args, opts = {}) => {
    const line = [cmd, ...args].join(" ");
    calls.push(line);
    argvs.push([cmd, ...args]);
    inputs.push(opts.input);
    const key = line in replies
      ? line
      : Object.keys(replies).find((k) => k.endsWith(" *") && line.startsWith(k.slice(0, -1)));
    if (key === undefined) return { code: 1, stdout: "", stderr: `unexpected call: ${line}` };
    const raw = replies[key];
    const reply = typeof raw === "function" ? (raw as (calls: string[]) => unknown)(calls) : raw;
    if (typeof reply === "object" && reply !== null && "fail" in reply) return (reply as Failure).fail;
    return { code: 0, stdout: typeof reply === "string" ? reply : JSON.stringify(reply), stderr: "" };
  };
  return { sh, calls, argvs, inputs };
}

function run(argv: string[], replies: Record<string, unknown>, cwd = mkdtempSync(join(tmpdir(), "orch-"))) {
  const runner = fakeRunner(replies);
  const out: string[] = [];
  const err: string[] = [];
  const code = main(argv, { sh: runner.sh, cwd, out: (l) => out.push(l), err: (l) => err.push(l) });
  return { code, out, err, calls: runner.calls, argvs: runner.argvs, inputs: runner.inputs };
}

function repoWithConfig(doc: string): string {
  const root = mkdtempSync(join(tmpdir(), "orch-"));
  mkdirSync(join(root, "docs", "agents"), { recursive: true });
  writeFileSync(join(root, "docs", "agents", "orchestrator.md"), doc);
  return root;
}

test("status lists the ready queue, then each other issue with its reason", () => {
  const result = run(["status"], {
    ...NO_LIVE,
    [ME]: "me\n",
    [LIST]: [[
      issue(16, { title: "line blocker, closed", body: "Blocked by: #31" }),
      issue(15, { title: "native blocker, closed", blockedBy: 1 }),
      issue(14, { title: "line blocker, open", body: "## Notes\n\nBlocked by: #21, #22\n" }),
      issue(13, { title: "native blocker, open", blockedBy: 1 }),
      issue(12, { title: "assigned to someone else", assignees: ["alice"] }),
      issue(11, { title: "assigned to me", assignees: ["me"] }),
      issue(10, { title: "unassigned" }),
    ]],
    [NATIVE(13)]: [[issue(20)]],
    [NATIVE(15)]: [[issue(30, { state: "closed" })]],
    [VIEW(21)]: issue(21),
    [VIEW(22)]: issue(22, { state: "closed" }),
    [VIEW(31)]: issue(31, { state: "closed" }),
  });
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 0);
  assert.deepEqual(result.out, [
    "ready queue (4)",
    "  #10  unassigned",
    "  #11  assigned to me",
    "  #15  native blocker, closed",
    "  #16  line blocker, closed",
    "not eligible (3)",
    "  #12  assigned to someone else  (assigned to alice)",
    "  #13  native blocker, open  (blocked by #20)",
    "  #14  line blocker, open  (blocked by #21)",
  ]);
});

test("status asks for native blockers only where the summary counts one", () => {
  const result = run(["status"], {
    ...NO_LIVE,
    [ME]: "me\n",
    [LIST]: [[issue(10), issue(11, { blockedBy: 1 })]],
    [NATIVE(11)]: [[issue(20, { state: "closed" })]],
  });
  assert.equal(result.code, 0);
  assert.deepEqual(result.calls, [ME, ...LIVE, LIST, NATIVE(11)]);
});

test("status reads a blocker once, even when two forms name it", () => {
  const result = run(["status"], {
    ...NO_LIVE,
    [ME]: "me\n",
    [LIST]: [[issue(10, { blockedBy: 1, body: "Blocked by: #20" })]],
    [NATIVE(10)]: [[issue(20)]],
  });
  assert.deepEqual(result.out, ["ready queue (0)", "not eligible (1)", "  #10  issue 10  (blocked by #20)"]);
  assert.deepEqual(result.calls, [ME, ...LIVE, LIST, NATIVE(10)]);
});

test("status names a native blocker in another repo by its repo", () => {
  const other = "https://api.github.com/repos/acme/infra";
  const result = run(["status"], {
    ...NO_LIVE,
    [ME]: "me\n",
    [LIST]: [[issue(10, { blockedBy: 1 })]],
    [NATIVE(10)]: [[issue(7, { repo: other })]],
  });
  assert.deepEqual(result.out.slice(-1), ["  #10  issue 10  (blocked by acme/infra#7)"]);
});

test("status skips pull requests, which the issues endpoint also returns", () => {
  const result = run(["status"], {
    ...NO_LIVE,
    [ME]: "me\n",
    [LIST]: [[issue(10), issue(11, { pr: true })], [issue(12)]],
  });
  assert.deepEqual(result.out, ["ready queue (2)", "  #10  issue 10", "  #12  issue 12"]);
});

test("status reads the tracker from the first json block in the config doc", () => {
  const cwd = repoWithConfig(
    "# Orchestrator config\n\n```json\n{ \"tracker\": \"gitlab\", \"max_workers\": 2 }\n```\n\n```json\n{ \"tracker\": \"github\" }\n```\n",
  );
  const result = run(["status"], {}, cwd);
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, ['error: tracker "gitlab" is not supported yet']);
  assert.deepEqual(result.calls, []);
});

test("status falls back to the defaults when the config doc has no json block", () => {
  const cwd = repoWithConfig("# Orchestrator config\n\n```yaml\ntracker: gitlab\n```\n");
  const result = run(["status"], { ...NO_LIVE, [ME]: "me\n", [LIST]: [[issue(10)]] }, cwd);
  assert.equal(result.code, 0);
  assert.deepEqual(result.out, ["ready queue (1)", "  #10  issue 10"]);
});

test("status refuses a json block that does not parse", () => {
  const cwd = repoWithConfig("```json\n{ tracker: github }\n```\n");
  const result = run(["status"], {}, cwd);
  assert.equal(result.code, 1);
  assert.match(result.err[0] ?? "", /^error: the json block in docs\/agents\/orchestrator\.md does not parse/);
});

test("status exits 1 with gh's own message when gh fails", () => {
  const result = run(["status"], { ...NO_LIVE, [ME]: "me\n" });
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, [`error: ${LIST} failed: unexpected call: ${LIST}`]);
});

test("an unknown subcommand prints the usage and exits 2", () => {
  for (const argv of [[], ["merge"], ["status", "extra"]]) {
    const result = run(argv, {});
    assert.equal(result.code, 2);
    assert.deepEqual(result.err, [USAGE]);
  }
});

test("node runs the script directly, with no build step", () => {
  const script = join(import.meta.dirname, "orchestrator.ts");
  const result = spawnSync(process.execPath, [script, "no-such-subcommand"], { encoding: "utf8" });
  assert.equal(result.status, 2);
  assert.equal(result.stderr, `${USAGE}\n`);
});

const GIT = "git rev-parse --path-format=absolute --git-common-dir";
const PATCH = (n: number) => `gh api -X PATCH repos/{owner}/{repo}/issues/${n} --input -`;
const WORKER_START = "orca orchestration worker-start *";

// The receipt `orca orchestration worker-start --json` printed for the manual run on
// issue 363, trimmed to the fields beside the one the script reads.
const RECEIPT = {
  id: "57273150-b080-4346-a1c8-a327da8250c2",
  ok: true,
  result: {
    runId: "run_b4cfa6c0dc58",
    taskId: "task_1d8a5f724329",
    dispatchId: "ctx_54923f33c600",
    state: "ready",
    stage: "input_accepted",
    launch: { effective: { agent: "claude", model: "sonnet", effort: "low" } },
  },
};

// The `--json` reply of a worker-start orca refused, as it printed one for a worktree path.
const REFUSED = {
  fail: {
    code: 1,
    stdout: JSON.stringify({
      ok: false,
      error: { code: "repo_not_found", message: "repo_not_found Orchestration mutation request ID: 6de9." },
    }),
    stderr: "",
  },
};

// The replies a start on eligible issue `n` needs, with `fixture` shaping the issue.
function startReplies(n: number, fixture: Fixture = {}, extra: Record<string, unknown> = {}) {
  const labels = fixture.labels ?? ["ready-for-agent"];
  return {
    [VIEW(n)]: issue(n, { ...fixture, labels }),
    [SCAN]: [[]],
    [ME]: "me\n",
    [GIT]: "/repo/.git\n",
    [PATCH(n)]: issue(n, { ...fixture, labels: ["in-progress"], assignees: ["me"] }),
    [WORKER_START]: RECEIPT,
    ...extra,
  };
}

// The argv of the one worker-start call, or undefined where none ran.
function workerStart(result: { argvs: string[][] }): string[] | undefined {
  return result.argvs.find((argv) => argv[0] === "orca" && argv[2] === "worker-start");
}

function flag(argv: string[] | undefined, name: string): string | undefined {
  const at = argv?.indexOf(name) ?? -1;
  return at < 0 ? undefined : argv?.[at + 1];
}

function patches(result: { calls: string[]; inputs: (string | undefined)[] }) {
  return result.calls.flatMap((line, i) => (line.includes("-X PATCH") ? [JSON.parse(result.inputs[i] ?? "")] : []));
}

test("start claims an eligible issue in one write, then starts a claude worker on issue-N", () => {
  const result = run(
    ["start", "10", "--run", "run_1"],
    startReplies(10, { title: "Add the thing", labels: ["ready-for-agent", "docs"] }),
  );
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 0);
  assert.deepEqual(result.out, [
    "started #10 in worktree issue-10: claude sonnet @ medium (medium role), dispatch ctx_54923f33c600",
  ]);
  assert.deepEqual(result.calls.slice(0, 5), [VIEW(10), SCAN, ME, GIT, PATCH(10)]);
  assert.deepEqual(patches(result), [{ labels: ["docs", "in-progress"], assignees: ["me"] }]);
  const argv = workerStart(result) ?? [];
  const spec = flag(argv, "--spec") ?? "";
  assert.deepEqual(argv, [
    "orca", "orchestration", "worker-start",
    "--spec", spec,
    "--task-title", "issue-10",
    "--worktree", "new-top-level",
    "--name", "issue-10",
    "--repo", "path:/repo",
    "--base-branch", "main",
    "--agent", "claude",
    "--model", "sonnet",
    "--effort", "medium",
    "--run", "run_1",
    "--json",
  ]);
  assert.equal(result.calls.length, 6);
});

test("start takes #N, and an issue already assigned to me keeps one assignee", () => {
  const result = run(["start", "#10", "--run", "run_1"], startReplies(10, { assignees: ["me"] }));
  assert.equal(result.code, 0);
  assert.deepEqual(patches(result), [{ labels: ["in-progress"], assignees: ["me"] }]);
});

test("start renders the fixed worker template, with no issue body in it", () => {
  const result = run(
    ["start", "10", "--run", "run_1"],
    startReplies(10, { title: "Add the thing", body: "## What to build\n\nA SECRET BODY LINE\n" }),
  );
  assert.equal(flag(workerStart(result), "--spec"), [
    'You are working on issue #10: "Add the thing", in the orca worktree issue-10, on the branch it checked out.',
    "",
    "1. Read the issue and every comment: gh issue view 10 --json title,body,comments",
    "2. Run /implement on it.",
    "3. Commit in slices: one logical change per commit, Conventional Commits.",
    '4. Push, and open a PR (not a draft) against main. Write its body with /pr, and put "Closes #10" in it.',
    "5. Never change the issue's state or labels, and never merge.",
    "6. If you are blocked on a decision only a human can make, use the orchestration `ask` command from your preamble, and stop.",
    "7. When you finish, send worker_done --outcome succeeded with the PR URL, or --outcome failed with the reason.",
    "",
  ].join("\n"));
});

test("start appends a --note as the template's last line", () => {
  const result = run(
    ["start", "10", "--run", "run_1", "--note", "Keep the old flag as an alias."],
    startReplies(10, { title: "Add the thing" }),
  );
  const spec = flag(workerStart(result), "--spec") ?? "";
  assert.match(spec, /with the reason\.\n\nKeep the old flag as an alias\.\n$/);
});

test("start picks the role: --role, then the heavy label, the light label, Touches, medium", () => {
  const touches = (n: number) => `## Touches\n\n${Array.from({ length: n }, (_, i) => `- src/f${i}.ts`).join("\n")}\n\n## Next\n\n- not a path\n`;
  const cases: [string, Fixture, string[], string][] = [
    ["--role beats every label", { labels: ["ready-for-agent", "heavy"] }, ["--role", "light"], "light"],
    ["the heavy label", { labels: ["ready-for-agent", "heavy"] }, [], "heavy"],
    ["the heavy label beats the light label", { labels: ["ready-for-agent", "light", "heavy"] }, [], "heavy"],
    ["the light label beats Touches", { labels: ["ready-for-agent", "light"], body: touches(5) }, [], "light"],
    ["three Touches paths", { body: touches(3) }, [], "heavy"],
    ["two Touches paths", { body: touches(2) }, [], "medium"],
    ["no Touches block", {}, [], "medium"],
  ];
  const efforts: Record<string, [string, string]> = {
    heavy: ["opus", "high"],
    medium: ["sonnet", "medium"],
    light: ["sonnet", "low"],
  };
  for (const [name, fixture, argv, role] of cases) {
    const result = run(["start", "10", "--run", "run_1", ...argv], startReplies(10, fixture));
    const [model, effort] = efforts[role] ?? [];
    assert.equal(result.code, 0, name);
    assert.equal(flag(workerStart(result), "--model"), model, name);
    assert.equal(flag(workerStart(result), "--effort"), effort, name);
    assert.match(result.out[0] ?? "", new RegExp(`\\(${role} role\\)`), name);
  }
});

test("start reads the role labels, the Touches bar and each role from the config doc", () => {
  const cwd = repoWithConfig([
    "```json",
    JSON.stringify({
      base: "trunk",
      roles: { heavy: { model: "opus-big", effort: "max" } },
      role_labels: { heavy: "size:L", light: "size:S" },
      heavy_touches: 2,
    }),
    "```",
  ].join("\n"));
  const big = run(["start", "10", "--run", "run_1"], startReplies(10, { labels: ["ready-for-agent", "size:L"] }), cwd);
  assert.deepEqual(
    ["--model", "--effort", "--base-branch"].map((f) => flag(workerStart(big), f)),
    ["opus-big", "max", "trunk"],
  );
  const wide = run(["start", "10", "--run", "run_1"], startReplies(10, { body: "## Touches\n- a\n- b\n" }), cwd);
  assert.equal(flag(workerStart(wide), "--effort"), "max");
  const small = run(["start", "10", "--run", "run_1"], startReplies(10, { labels: ["ready-for-agent", "size:S"] }), cwd);
  assert.equal(flag(workerStart(small), "--effort"), "low");
});

test("start on an issue that is not eligible prints one line and writes nothing", () => {
  const cases: [Fixture, Record<string, unknown>, string][] = [
    [{ state: "closed" }, {}, "#10 is not eligible: closed"],
    [{ labels: ["needs-triage"] }, {}, "#10 is not eligible: not ready-for-agent"],
    [{ assignees: ["alice"] }, {}, "#10 is not eligible: assigned to alice"],
    [{ body: "Blocked by: #21" }, { [VIEW(21)]: issue(21) }, "#10 is not eligible: blocked by #21"],
  ];
  for (const [fixture, extra, line] of cases) {
    const result = run(["start", "10", "--run", "run_1"], startReplies(10, fixture, extra));
    assert.equal(result.code, 1, line);
    assert.deepEqual(result.err, [line]);
    assert.deepEqual(result.out, []);
    assert.deepEqual(result.calls.filter((c) => !c.startsWith("gh api repos/") && c !== ME && c !== SCAN), [], line);
  }
});

test("start refuses a role whose harness is not claude, before it claims", () => {
  const cwd = repoWithConfig('```json\n{ "roles": { "heavy": { "harness": "codex" } } }\n```\n');
  const result = run(["start", "10", "--run", "run_1", "--role", "heavy"], startReplies(10), cwd);
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, ["#10 is not started: its heavy role runs on codex, and start launches only claude for now"]);
  assert.deepEqual(result.calls, [VIEW(10), SCAN, ME]);
});

test("start reads the Run id from the run file when no --run is given", () => {
  const cwd = mkdtempSync(join(tmpdir(), "orch-"));
  mkdirSync(join(cwd, ".orchestrator"));
  writeFileSync(join(cwd, ".orchestrator", "run.json"), '{ "run": "run_from_file" }\n');
  const result = run(["start", "10"], startReplies(10), cwd);
  assert.equal(result.code, 0);
  assert.equal(flag(workerStart(result), "--run"), "run_from_file");
});

test("start refuses a run file that does not parse, before any call", () => {
  const cwd = mkdtempSync(join(tmpdir(), "orch-"));
  mkdirSync(join(cwd, ".orchestrator"));
  writeFileSync(join(cwd, ".orchestrator", "run.json"), "run_1\n");
  const result = run(["start", "10"], startReplies(10), cwd);
  assert.equal(result.code, 1);
  assert.match(result.err[0] ?? "", /^error: \.orchestrator\/run\.json does not parse: /);
  assert.deepEqual(result.calls, []);
});

test("start with no Run id stops before any call", () => {
  const result = run(["start", "10"], startReplies(10));
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, [
    'error: no orca Run: pass --run <id>, or write { "run": "<id>" } to .orchestrator/run.json',
  ]);
  assert.deepEqual(result.calls, []);
});

test("start undoes the claim when orca refuses the worker, and prints orca's message", () => {
  const result = run(["start", "10", "--run", "run_1"], startReplies(10, {}, { [WORKER_START]: REFUSED }));
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, [
    "error: orca worker-start failed, so #10 is unclaimed again: repo_not_found Orchestration mutation request ID: 6de9.",
  ]);
  assert.deepEqual(patches(result), [
    { labels: ["in-progress"], assignees: ["me"] },
    { labels: ["ready-for-agent"], assignees: [] },
  ]);
  assert.equal(result.calls.at(-1), PATCH(10));
});

test("start refuses arguments it cannot read, with the usage", () => {
  for (const argv of [["start"], ["start", "ten"], ["start", "1", "2"], ["start", "1", "--role", "huge"], ["start", "1", "--x"]]) {
    const result = run(argv, {});
    assert.equal(result.code, 2, argv.join(" "));
    assert.deepEqual(result.err, [USAGE]);
    assert.deepEqual(result.calls, []);
  }
});

const RUN = "run_1";
const COORDINATOR = "term_4f0ec745-92e8-4178-b33c-e0b32e2792db";
const ORCA = (...args: string[]) => `orca orchestration ${args.join(" ")} --json`;
const RUN_SHOW = ORCA("run-show", "--id", RUN);
const TASKS = ORCA("task-list", "--run", RUN);
const WORKERS = ORCA("worker-list", "--run", RUN);
const CHECK = ORCA("check", "--run", RUN, "--terminal", COORDINATOR);
const ACK = (delivery: string) => ORCA("check", "--run", RUN, "--terminal", COORDINATOR, "--ack", delivery);
const RELEASE = (n: number) => ORCA("worker-release", "--dispatch", `ctx_${n}`);
const STOP = (n: number) => ORCA("worker-stop", "--dispatch", `ctx_${n}`);
const COMMENT = (n: number) => `gh api -X POST repos/{owner}/{repo}/issues/${n}/comments --input -`;
const CLOSING_PRS = "query($owner:String!,$repo:String!,$number:Int!){repository(owner:$owner,name:$repo)"
  + "{issue(number:$number){closedByPullRequestsReferences(first:20,includeClosedPrs:true)"
  + "{nodes{number url state mergeable reviewDecision}}}}}";
const PRS = (n: number) => `gh api graphql -f query=${CLOSING_PRS} -F owner={owner} -F repo={repo} -F number=${n}`;
const TICK = ["tick", "--run", RUN];

// An `orca orchestration --json` receipt around `result`, as orca printed them for the
// manual proof on run_b4cfa6c0dc58.
function receipt(result: unknown) {
  return { id: "3da4edb0-6347-43cc-bcce-aaa35ee9f725", ok: true, result, _meta: { runtimeId: "56165fca" } };
}

// A `task-list` row for issue `n`. A reported Task holds the worker_done report orca kept.
function task(n: number, fixture: { title?: string; reported?: boolean } = {}) {
  return {
    id: `task_${n}`,
    run_id: RUN,
    task_title: fixture.title ?? `issue-${n}`,
    display_name: fixture.title ?? `issue-${n}`,
    status: fixture.reported ? "completed" : "dispatched",
    result: fixture.reported
      ? JSON.stringify({ provenance: "worker_report", outcome: "succeeded", messageId: `msg_${n}` })
      : null,
  };
}

// A `worker-list` row for issue `n`'s Dispatch `ctx_<dispatch>`.
function worker(n: number, fixture: { dispatch?: number; liveness?: string; worktree?: string } = {}) {
  const dispatch = `ctx_${fixture.dispatch ?? n}`;
  const worktreeId = `b33c1c8a::/Users/me/orca/workspaces/repo/${fixture.worktree ?? `issue-${n}`}`;
  return {
    dispatchId: dispatch,
    taskId: `task_${n}`,
    runId: RUN,
    workerState: "running",
    terminalState: "active",
    resource: { id: `wtr_${n}`, worktreeId, ownerDispatchId: dispatch },
    projection: {
      dispatchId: dispatch,
      workspace: { id: worktreeId, kind: "folder_or_worktree" },
      liveness: { verdict: fixture.liveness ?? "alive", source: "resource_release" },
    },
  };
}

// A mailbox message from issue `n`'s worker, shaped like msg_d85f0a8f3b6b and
// msg_6fad840dcc3c from the manual proof.
function message(n: number, type: string, fixture: { outcome?: string; body?: string; options?: string[] } = {}) {
  return {
    id: `msg_${type}_${n}`,
    run_id: RUN,
    from_handle: type === "question" ? `dispatch:ctx_${n}` : `term_worker_${n}`,
    to_handle: `run:${RUN}`,
    subject: type === "question" ? "Question" : "Report",
    body: fixture.body ?? `${type} text from issue ${n}`,
    type,
    payload: JSON.stringify({
      taskId: `task_${n}`,
      dispatchId: `ctx_${n}`,
      ...(fixture.outcome ? { outcome: fixture.outcome } : {}),
      ...(fixture.options ? { options: fixture.options } : {}),
    }),
  };
}

function batch(delivery: string | null, messages: unknown[] = []) {
  return receipt({ runId: RUN, deliveryId: delivery, count: messages.length, messages, acknowledged: null });
}

// The closing PRs GraphQL returned, each as [number, state] with an optional
// mergeable and review decision.
function prs(...nodes: [number, string, { mergeable?: string; reviewDecision?: string | null }?][]) {
  return {
    data: { repository: { issue: { closedByPullRequestsReferences: { nodes: nodes.map(([number, state, extra]) => ({
      number, url: `https://github.com/wagnersza/orchestrator-skills/pull/${number}`, state,
      mergeable: extra?.mergeable ?? "UNKNOWN", reviewDecision: extra?.reviewDecision ?? null,
    })) } } } },
  };
}

type TickFixture = {
  messages?: unknown[];
  tasks?: unknown[];
  workers?: unknown[];
  issues?: Record<number, string[]>;
  // The ready-for-agent issues, in the order the tracker lists them.
  queue?: [number, Fixture?][];
};

// The replies a tick needs: one batch, its ack, and each issue holding its labels. The
// in-progress list holds the issues that hold the label and have no PATCH yet, and the
// ready list holds the queue.
function tickReplies(fixture: TickFixture = {}, extra: Record<string, unknown> = {}) {
  const issues = Object.entries(fixture.issues ?? {}).flatMap(([n, labels]) => [
    [VIEW(Number(n)), issue(Number(n), { labels, assignees: ["me"] })],
    [PATCH(Number(n)), issue(Number(n), { labels: ["patched"], assignees: ["me"] })],
    [COMMENT(Number(n)), { id: 1 }],
  ]);
  return {
    [RUN_SHOW]: receipt({ run: { id: RUN, coordinator_handle: COORDINATOR } }),
    [TASKS]: receipt({ runId: RUN, tasks: fixture.tasks ?? [] }),
    [WORKERS]: receipt({ workers: fixture.workers ?? [], page: { limit: 100, hasMore: false, nextCursor: null } }),
    [CHECK]: batch(fixture.messages ? "delivery_1" : null, fixture.messages),
    [ACK("delivery_1")]: batch(null),
    ...Object.fromEntries(issues),
    [LIST_OF("in-progress")]: (calls: string[]) => [Object.entries(fixture.issues ?? {})
      .filter(([n, labels]) => labels.includes("in-progress") && !calls.includes(PATCH(Number(n))))
      .map(([n, labels]) => issue(Number(n), { labels, assignees: ["me"] }))],
    [LIST]: [(fixture.queue ?? []).map(([n, f]) => issue(n, { ...f, labels: ["ready-for-agent", ...(f?.labels ?? [])] }))],
    [SCAN]: [[]],
    [ME]: "me\n",
    ...Object.fromEntries((fixture.queue ?? []).flatMap(([n, f]) => Object.entries(startReplies(n, f)))),
    ...extra,
  };
}

// The two lists a tick reads last: the in-progress issues, for the parents to close and
// the free slots, then the queue.
const FILL = [LIST_OF("in-progress"), LIST];

function comments(result: { calls: string[]; inputs: (string | undefined)[] }): string[] {
  return result.calls.flatMap((line, i) =>
    line.includes("-X POST") ? [(JSON.parse(result.inputs[i] ?? "") as { body: string }).body] : []);
}

function lockAt(cwd: string): string {
  return join(cwd, ".orchestrator", "tick.lock");
}

test("tick moves a worker_done with an open PR to ready-for-human, releases the worker, then acks", () => {
  const result = run(TICK, tickReplies(
    { messages: [message(10, "worker_done", { outcome: "succeeded" })], tasks: [task(10)], workers: [worker(10)], issues: { 10: ["in-progress"] } },
    { [PRS(10)]: prs([12, "OPEN"]), [RELEASE(10)]: receipt({ released: true }) },
  ));
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 1);
  assert.deepEqual(result.out, ["#10: in-progress -> ready-for-human (worker_done succeeded, PR #12); released ctx_10"]);
  assert.deepEqual(result.calls, [TASKS, WORKERS, RUN_SHOW, CHECK, VIEW(10), PRS(10), RELEASE(10), PATCH(10), ACK("delivery_1"), ...FILL]);
  assert.deepEqual(patches(result), [{ labels: ["ready-for-human"], assignees: ["me"] }]);
  assert.deepEqual(comments(result), []);
});

test("tick moves a worker_done with no open PR to needs-human, with the worker's report", () => {
  const result = run(TICK, tickReplies(
    { messages: [message(10, "worker_done", { outcome: "succeeded", body: "Done." })], tasks: [task(10)], issues: { 10: ["in-progress"] } },
    { [PRS(10)]: prs([12, "CLOSED"]), [RELEASE(10)]: receipt({}) },
  ));
  assert.equal(result.code, 1);
  assert.deepEqual(result.out, ["#10: in-progress -> needs-human (worker_done succeeded with no open PR); released ctx_10, commented"]);
  assert.deepEqual(patches(result), [{ labels: ["needs-human"], assignees: ["me"] }]);
  assert.deepEqual(comments(result), [
    "The worker reported success, but no open PR closes this issue. Its report:\n\n> Done.\n\n"
      + "Answer here, then relabel `ready-for-agent` to resume. The worktree is kept.",
  ]);
});

test("tick moves a failed worker_done to needs-human and posts the worker's own reason", () => {
  const result = run(TICK, tickReplies(
    { messages: [message(10, "worker_done", { outcome: "failed", body: "The suite fails on main.\n\nSee CI." })], tasks: [task(10)], issues: { 10: ["in-progress", "docs"] } },
    { [RELEASE(10)]: receipt({}) },
  ));
  assert.equal(result.code, 1);
  assert.deepEqual(result.out, ["#10: in-progress -> needs-human (worker_done failed); released ctx_10, commented"]);
  assert.deepEqual(result.calls.slice(4), [VIEW(10), RELEASE(10), COMMENT(10), PATCH(10), ACK("delivery_1"), ...FILL]);
  assert.deepEqual(patches(result), [{ labels: ["docs", "needs-human"], assignees: ["me"] }]);
  assert.deepEqual(comments(result), [
    "The worker reported a failure:\n\n> The suite fails on main.\n>\n> See CI.\n\n"
      + "Answer here, then relabel `ready-for-agent` to resume. The worktree is kept.",
  ]);
});

test("tick moves a question to needs-human, posts it with its options, and stops the worker", () => {
  const result = run(TICK, tickReplies(
    {
      messages: [message(10, "question", { body: "Keep the old flag?", options: ["keep", "drop"] })],
      tasks: [task(10)],
      issues: { 10: ["in-progress"] },
    },
    { [STOP(10)]: receipt({ stopped: true }) },
  ));
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 1);
  assert.deepEqual(result.out, ["#10: in-progress -> needs-human (question); stopped ctx_10, commented"]);
  assert.deepEqual(result.calls.slice(4), [VIEW(10), STOP(10), COMMENT(10), PATCH(10), ACK("delivery_1"), ...FILL]);
  assert.deepEqual(comments(result), [
    "The worker asked a question, and the tick stopped it:\n\n> Keep the old flag?\n\nIts options: `keep`, `drop`.\n\n"
      + "Answer here, then relabel `ready-for-agent` to resume. The worktree is kept.",
  ]);
  assert.equal(result.calls.some((c) => c.includes("worktree")), false);
});

test("tick moves an escalation to needs-human and stops the worker", () => {
  const result = run(TICK, tickReplies(
    { messages: [message(10, "escalation", { body: "I need repo admin." })], tasks: [task(10)], issues: { 10: ["in-progress"] } },
    { [STOP(10)]: receipt({}) },
  ));
  assert.equal(result.code, 1);
  assert.deepEqual(result.out, ["#10: in-progress -> needs-human (escalation); stopped ctx_10, commented"]);
  assert.match(comments(result)[0] ?? "", /^The worker escalated, and the tick stopped it:\n\n> I need repo admin\.\n\n/);
});

test("tick maps a message to its issue by worktree name when the Task title is not issue-N", () => {
  const result = run(TICK, tickReplies(
    {
      messages: [message(10, "escalation")],
      tasks: [task(10, { title: "a free-text title naming #99" })],
      workers: [worker(10, { worktree: "issue-11" })],
      issues: { 11: ["in-progress"] },
    },
    { [STOP(10)]: receipt({}) },
  ));
  assert.deepEqual(result.out, ["#11: in-progress -> needs-human (escalation); stopped ctx_10, commented"]);
});

test("tick skips a message that names no issue, ignores status mail, and acks the batch", () => {
  const result = run(TICK, tickReplies({
    messages: [message(10, "escalation"), message(12, "status"), message(12, "heartbeat")],
    tasks: [task(10, { title: "not an issue" })],
  }));
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, ["tick: msg_escalation_10 (escalation) names no issue-N Task or worktree, so it is skipped"]);
  assert.deepEqual(result.calls, [TASKS, WORKERS, RUN_SHOW, CHECK, ACK("delivery_1"), ...FILL]);
});

test("tick writes nothing for a replayed message whose issue already left in-progress", () => {
  for (const labels of [["needs-human"], ["ready-for-human"]]) {
    const result = run(TICK, tickReplies({
      messages: [message(10, "question"), message(10, "worker_done", { outcome: "succeeded" })],
      tasks: [task(10)],
      issues: { 10: labels },
    }));
    assert.equal(result.code, 1);
    assert.deepEqual(result.err, []);
    assert.deepEqual(result.out, [
      "#10: question msg_question_10 changes nothing, the issue is not in-progress",
      "#10: worker_done msg_worker_done_10 changes nothing, the issue is not in-progress",
    ]);
    assert.deepEqual(result.calls, [TASKS, WORKERS, RUN_SHOW, CHECK, VIEW(10), ACK("delivery_1"), ...FILL]);
  }
});

test("tick acks nothing when a transition fails to write, so the next tick replays it", () => {
  const cwd = mkdtempSync(join(tmpdir(), "orch-"));
  const result = run(TICK, tickReplies(
    { messages: [message(10, "question")], tasks: [task(10)], issues: { 10: ["in-progress"] } },
    { [STOP(10)]: receipt({}), [PATCH(10)]: { fail: { code: 1, stdout: "", stderr: "HTTP 502" } } },
  ), cwd);
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, [`error: ${PATCH(10)} failed: HTTP 502`]);
  assert.equal(result.calls.includes(ACK("delivery_1")), false);
  assert.equal(existsSync(lockAt(cwd)), false);
});

test("tick drains every batch, acking each one after its messages", () => {
  const result = run(TICK, tickReplies(
    { messages: [message(10, "question")], tasks: [task(10), task(11)], issues: { 10: ["in-progress"], 11: ["in-progress"] } },
    {
      [STOP(10)]: receipt({}),
      [STOP(11)]: receipt({}),
      [ACK("delivery_1")]: batch("delivery_2", [message(11, "escalation")]),
      [ACK("delivery_2")]: batch(null),
    },
  ));
  assert.deepEqual(result.out, [
    "#10: in-progress -> needs-human (question); stopped ctx_10, commented",
    "#11: in-progress -> needs-human (escalation); stopped ctx_11, commented",
  ]);
  assert.deepEqual(result.calls.filter((c) => c.includes(" check ") || c.includes("PATCH")), [
    CHECK, PATCH(10), ACK("delivery_1"), PATCH(11), ACK("delivery_2"),
  ]);
});

test("tick still moves the issue when orca cannot stop the worker, and says so", () => {
  const result = run(TICK, tickReplies(
    { messages: [message(10, "question")], tasks: [task(10)], issues: { 10: ["in-progress"] } },
    { [STOP(10)]: { fail: { code: 1, stdout: JSON.stringify({ ok: false, error: { message: "dispatch_not_found" } }), stderr: "" } } },
  ));
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, ["tick: #10: orca worker-stop ctx_10 failed: dispatch_not_found"]);
  assert.deepEqual(result.out, ["#10: in-progress -> needs-human (question); commented"]);
  assert.deepEqual(patches(result), [{ labels: ["needs-human"], assignees: ["me"] }]);
});

test("tick moves an issue whose newest worker exited without worker_done to needs-human", () => {
  const result = run(TICK, tickReplies({
    tasks: [task(10), task(11, { reported: true }), task(12), task(13)],
    workers: [
      worker(10, { liveness: "exited" }),
      worker(11, { liveness: "exited" }),
      worker(12, { dispatch: 120 }),
      worker(12, { dispatch: 121, liveness: "exited" }),
      worker(13, { liveness: "exited" }),
    ],
    issues: { 10: ["in-progress"], 13: ["needs-human"] },
  }));
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 1);
  assert.deepEqual(result.out, ["#10: in-progress -> needs-human (worker exited without reporting); commented"]);
  assert.deepEqual(result.calls, [TASKS, WORKERS, RUN_SHOW, CHECK, VIEW(10), COMMENT(10), PATCH(10), VIEW(13), ...FILL]);
  assert.deepEqual(comments(result), [
    "The worker exited without sending worker_done, so it left no report. "
      + "Answer here, then relabel `ready-for-agent` to resume. The worktree is kept.",
  ]);
});

test("tick does not call a worker dead when this tick read its worker_done", () => {
  const result = run(TICK, tickReplies(
    { messages: [message(10, "question")], tasks: [task(10)], workers: [worker(10, { liveness: "exited" })], issues: { 10: ["in-progress"] } },
    { [STOP(10)]: receipt({}) },
  ));
  assert.deepEqual(result.out, ["#10: in-progress -> needs-human (question); stopped ctx_10, commented"]);
  assert.equal(comments(result).length, 1);
});

test("tick reads every worker-list page", () => {
  const result = run(TICK, tickReplies({ tasks: [task(10)], issues: { 10: ["in-progress"] } }, {
    [WORKERS]: receipt({ workers: [], page: { nextCursor: "c2" } }),
    [ORCA("worker-list", "--run", RUN, "--cursor", "c2")]: receipt({ workers: [worker(10, { liveness: "exited" })], page: { nextCursor: null } }),
  }));
  assert.deepEqual(result.out, ["#10: in-progress -> needs-human (worker exited without reporting); commented"]);
});

test("tick exits at once while another tick holds the lock, and leaves its lock alone", () => {
  const cwd = mkdtempSync(join(tmpdir(), "orch-"));
  mkdirSync(join(cwd, ".orchestrator"));
  writeFileSync(lockAt(cwd), "4242\n");
  const result = run(TICK, tickReplies(), cwd);
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, ["tick: another tick holds .orchestrator/tick.lock, so this one exits"]);
  assert.deepEqual(result.calls, []);
  assert.equal(readFileSync(lockAt(cwd), "utf8"), "4242\n");
});

test("tick takes over a lock older than five minutes, and removes it when done", () => {
  const cwd = mkdtempSync(join(tmpdir(), "orch-"));
  mkdirSync(join(cwd, ".orchestrator"));
  writeFileSync(lockAt(cwd), "4242\n");
  const sixMinutesAgo = new Date(Date.now() - 6 * 60 * 1000);
  utimesSync(lockAt(cwd), sixMinutesAgo, sixMinutesAgo);
  const result = run(TICK, tickReplies(), cwd);
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, []);
  assert.deepEqual(result.calls, [TASKS, WORKERS, RUN_SHOW, CHECK, ...FILL]);
  assert.equal(existsSync(lockAt(cwd)), false);
});

test("tick exits non-zero on every path, and never leaves its lock behind", () => {
  const cases: [string, string[], Record<string, unknown>, number][] = [
    ["a quiet tick", TICK, tickReplies(), 1],
    ["no Run", ["tick"], tickReplies(), 1],
    ["orca fails", TICK, tickReplies({}, { [TASKS]: { fail: { code: 1, stdout: "", stderr: "orca is not running" } } }), 1],
    ["a Run with no coordinator", TICK, tickReplies({}, { [RUN_SHOW]: receipt({ run: { id: RUN, coordinator_handle: null } }) }), 1],
    ["bad arguments", ["tick", "10"], {}, 2],
  ];
  for (const [name, argv, replies, code] of cases) {
    const cwd = mkdtempSync(join(tmpdir(), "orch-"));
    const result = run(argv, replies, cwd);
    assert.equal(result.code, code, name);
    assert.notEqual(result.code, 0, name);
    assert.equal(existsSync(lockAt(cwd)), false, name);
  }
});

// The issue numbers worker-start ran for, in order, from the `--name issue-N` flag.
function started(result: { argvs: string[][] }): string[] {
  return result.argvs.filter((argv) => argv[2] === "worker-start").map((argv) => flag(argv, "--name") ?? "");
}

const MAX = (n: number) => repoWithConfig(`\`\`\`json\n{ "max_workers": ${n} }\n\`\`\`\n`);

test("tick starts every ready issue that fits, in queue order, with no session involved", () => {
  const result = run(TICK, tickReplies({ queue: [[10], [11]] }), MAX(3));
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 1);
  assert.deepEqual(started(result), ["issue-10", "issue-11"]);
  assert.deepEqual(result.out, [
    "started #10 in worktree issue-10: claude sonnet @ medium (medium role), dispatch ctx_54923f33c600",
    "started #11 in worktree issue-11: claude sonnet @ medium (medium role), dispatch ctx_54923f33c600",
  ]);
  assert.deepEqual(patches(result), [
    { labels: ["in-progress"], assignees: ["me"] },
    { labels: ["in-progress"], assignees: ["me"] },
  ]);
});

test("tick fills only the free slots: max_workers minus the in-progress issues that are not parents", () => {
  const result = run(TICK, tickReplies({
    queue: [[20], [21], [22]],
    issues: { 10: ["in-progress"], 11: ["in-progress", "user-story"] },
  }), MAX(3));
  assert.deepEqual(started(result), ["issue-20", "issue-21"]);
});

test("tick starts nothing while every slot is full, and reads no blocker of a leaf it cannot start", () => {
  const result = run(TICK, tickReplies({
    queue: [[20, { body: "Blocked by: #21" }]],
    issues: { 10: ["in-progress"], 11: ["in-progress"] },
  }), MAX(2));
  assert.deepEqual(result.err, []);
  assert.deepEqual(started(result), []);
  assert.equal(result.calls.includes(VIEW(21)), false);
  assert.deepEqual(patches(result), []);
});

test("tick skips an issue that is not eligible, and keeps queue order for the rest", () => {
  const result = run(TICK, tickReplies({
    queue: [[20, { assignees: ["other"] }], [21], [22]],
  }), MAX(2));
  assert.deepEqual(result.err, []);
  assert.deepEqual(started(result), ["issue-21", "issue-22"]);
});

test("tick observes before it fills: a slot freed this tick is filled this tick", () => {
  const result = run(TICK, tickReplies(
    {
      messages: [message(10, "worker_done", { outcome: "succeeded" })],
      tasks: [task(10)],
      workers: [worker(10)],
      issues: { 10: ["in-progress"], 11: ["in-progress"] },
      queue: [[20], [21]],
    },
    { [PRS(10)]: prs([12, "OPEN"]), [RELEASE(10)]: receipt({ released: true }) },
  ), MAX(2));
  assert.deepEqual(result.err, []);
  assert.deepEqual(started(result), ["issue-20"]);
  const at = (needle: string) => result.calls.findIndex((line) => line.includes(needle));
  assert.ok(at(PATCH(10)) > 0);
  assert.ok(at(PATCH(10)) < at("worker-start"));
  assert.ok(at(ACK("delivery_1")) < at("worker-start"));
  assert.deepEqual(result.out[0], "#10: in-progress -> ready-for-human (worker_done succeeded, PR #12); released ctx_10");
});

test("tick keeps a full slot full when no worker finished", () => {
  const result = run(TICK, tickReplies(
    { tasks: [task(10)], workers: [worker(10)], issues: { 10: ["in-progress"], 11: ["in-progress"] }, queue: [[20]] },
  ), MAX(2));
  assert.deepEqual(started(result), []);
});

test("tick gives a slot back when a worker does not start, and tries the next issue", () => {
  let starts = 0;
  const result = run(TICK, tickReplies({ queue: [[20], [21]] }, {
    [WORKER_START]: () => (starts++ === 0 ? REFUSED : RECEIPT),
  }), MAX(1));
  assert.deepEqual(started(result), ["issue-20", "issue-21"]);
  assert.equal(result.err.length, 1);
  assert.match(result.err[0] ?? "", /^error: orca worker-start failed, so #20 is unclaimed again: /);
});

test("node runs the tick directly, and it exits non-zero", () => {
  const script = join(import.meta.dirname, "orchestrator.ts");
  const cwd = mkdtempSync(join(tmpdir(), "orch-"));
  const result = spawnSync(process.execPath, [script, "tick"], { cwd, encoding: "utf8" });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /^error: no orca Run: /);
});

test("status prints each live issue, unassigned or mine, with its state, role, harness, liveness and PR", () => {
  const cwd = mkdtempSync(join(tmpdir(), "orch-"));
  mkdirSync(join(cwd, ".orchestrator"));
  writeFileSync(join(cwd, ".orchestrator", "run.json"), `{ "run": "${RUN}" }\n`);
  const result = run(["status"], {
    [ME]: "me\n",
    [LIVE[0] ?? ""]: [[
      issue(10, { title: "medium work", labels: ["in-progress"], assignees: ["me"] }),
      issue(11, { title: "someone else's", labels: ["in-progress"], assignees: ["alice"] }),
      issue(14, { title: "no worker yet", labels: ["in-progress", "light"] }),
    ]],
    [LIVE[1] ?? ""]: [[issue(12, { title: "stuck", labels: ["needs-human", "heavy"], assignees: ["me"] })]],
    [LIVE[2] ?? ""]: [[issue(13, { title: "in review", labels: ["ready-for-human"], assignees: ["me"] })]],
    [LIST]: [[issue(20, { title: "next" })]],
    [TASKS]: receipt({ tasks: [task(10), task(12), task(13)] }),
    [WORKERS]: receipt({
      workers: [worker(10), worker(12, { liveness: "exited" }), worker(13, { dispatch: 131, liveness: "exited" }), worker(13, { dispatch: 130 })],
      page: { nextCursor: null },
    }),
    [PRS(10)]: prs(),
    [PRS(12)]: prs([30, "CLOSED"]),
    [PRS(13)]: prs([31, "CLOSED"], [32, "OPEN"]),
    [PRS(14)]: prs(),
  }, cwd);
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 0);
  assert.deepEqual(result.out, [
    "live (4)",
    "  issue  state            role    harness  liveness  pr   title",
    "  #10    in-progress      medium  claude   alive     -    medium work",
    "  #14    in-progress      light   claude   none      -    no worker yet",
    "  #12    needs-human      heavy   claude   exited    #30  stuck",
    "  #13    ready-for-human  medium  claude   exited    #32  in review",
    "ready queue (1)",
    "  #20  next",
  ]);
});

test("status prints liveness as - and calls no orca where no Run is saved", () => {
  const result = run(["status"], {
    ...NO_LIVE,
    [ME]: "me\n",
    [LIVE[0] ?? ""]: [[issue(10, { title: "work", labels: ["in-progress"], assignees: ["me"] })]],
    [LIST]: [[]],
    [PRS(10)]: prs([12, "OPEN"]),
  });
  assert.equal(result.code, 0);
  assert.deepEqual(result.out.slice(1, 3), [
    "  issue  state        role    harness  liveness  pr   title",
    "  #10    in-progress  medium  claude   -         #12  work",
  ]);
  assert.equal(result.calls.some((line) => line.startsWith("orca")), false);
});

// A child of parent `p` by `## Parent` line, as the body scan finds it.
function child(n: number, p: number, fixture: Fixture = {}) {
  return issue(n, { labels: ["ready-for-agent"], ...fixture, body: `## Parent\n\n#${p}\n\n${fixture.body ?? ""}` });
}

test("tick claims a ready parent in each form, with no worker and no slot", () => {
  const result = run(TICK, tickReplies(
    {
      queue: [
        [30, { labels: ["user-story"] }],
        [31, { subIssues: 2 }],
        [32],
        [33, { labels: ["user-story"], assignees: ["alice"] }],
        [40],
      ],
    },
    { [SCAN]: [[child(35, 32, { labels: [] })]] },
  ), MAX(1));
  assert.deepEqual(result.err, []);
  assert.deepEqual(result.out, [
    "claimed parent #30: no worker, no slot",
    "claimed parent #31: no worker, no slot",
    "claimed parent #32: no worker, no slot",
    "started #40 in worktree issue-40: claude sonnet @ medium (medium role), dispatch ctx_54923f33c600",
  ]);
  assert.deepEqual(started(result), ["issue-40"]);
  assert.deepEqual(result.calls.filter((c) => c.includes("-X PATCH")), [PATCH(30), PATCH(31), PATCH(32), PATCH(40)]);
});

test("tick gives an in-progress parent no slot, in each parent form", () => {
  const result = run(TICK, tickReplies({ queue: [[20], [21]] }, {
    [LIST_OF("in-progress")]: [[
      issue(10, { labels: ["in-progress"], assignees: ["me"] }),
      issue(11, { labels: ["in-progress", "user-story"], assignees: ["me"] }),
      issue(12, { labels: ["in-progress"], assignees: ["me"], subIssues: 1 }),
      issue(13, { labels: ["in-progress"], assignees: ["me"] }),
    ]],
    [SUB_ISSUES(12)]: [[issue(14, { labels: [] })]],
    [SCAN]: [[child(15, 13, { labels: [] })]],
  }), MAX(3));
  assert.deepEqual(result.err, []);
  assert.deepEqual(started(result), ["issue-20", "issue-21"]);
  assert.deepEqual(comments(result), []);
});

test("tick closes no parent with an open child or with no child, and none held by someone else", () => {
  const result = run(TICK, tickReplies({}, {
    [LIST_OF("in-progress")]: [[
      issue(50, { labels: ["in-progress", "user-story"], assignees: ["me"] }),
      issue(51, { labels: ["in-progress"], assignees: ["me"], subIssues: 1 }),
      issue(53, { labels: ["in-progress", "user-story"], assignees: ["alice"], subIssues: 1 }),
    ]],
    [SUB_ISSUES(51)]: [[issue(52, { labels: [] })]],
  }));
  assert.deepEqual(result.err, []);
  assert.deepEqual(result.out, []);
  assert.deepEqual(started(result), []);
  assert.equal(result.calls.some((c) => c.includes("-X ")), false);
  assert.equal(result.calls.includes(SUB_ISSUES(53)), false);
});

test("a story runs in order: A and C start, B starts once A closes, then the parent closes with each PR", () => {
  // Parent #40 holds three native sub-issues. B (#42) is blocked by A (#41).
  const blockedByA = { body: "Blocked by: #41" };
  const parentLive = issue(40, { labels: ["in-progress"], assignees: ["me"], subIssues: 3 });

  const first = run(TICK, tickReplies({ queue: [[40, { subIssues: 3 }], [41], [42, blockedByA], [43]] }), MAX(3));
  assert.deepEqual(first.err, []);
  assert.deepEqual(first.out.slice(0, 1), ["claimed parent #40: no worker, no slot"]);
  assert.deepEqual(started(first), ["issue-41", "issue-43"]);
  assert.deepEqual(first.calls.filter((c) => c.includes("-X PATCH")), [PATCH(40), PATCH(41), PATCH(43)]);

  const second = run(TICK, tickReplies({ issues: { 43: ["in-progress"] }, queue: [[42, blockedByA]] }, {
    [LIST_OF("in-progress")]: [[parentLive, issue(43, { labels: ["in-progress"], assignees: ["me"] })]],
    [SUB_ISSUES(40)]: [[
      issue(41, { labels: [], state: "closed" }),
      issue(42, { ...blockedByA, labels: ["ready-for-agent"] }),
      issue(43, { labels: ["in-progress"], assignees: ["me"] }),
    ]],
  }), MAX(3));
  assert.deepEqual(second.err, []);
  assert.deepEqual(started(second), ["issue-42"]);
  assert.deepEqual(comments(second), []);

  const third = run(TICK, tickReplies({ issues: { 40: ["in-progress"] } }, {
    [LIST_OF("in-progress")]: [[parentLive]],
    [SUB_ISSUES(40)]: [[41, 42, 43].map((n) => issue(n, { labels: [], state: "closed" }))],
    [PRS(41)]: prs([60, "MERGED"]),
    [PRS(42)]: prs([62, "MERGED"]),
    [PRS(43)]: prs([61, "CLOSED"], [63, "MERGED"]),
  }));
  assert.deepEqual(third.err, []);
  assert.deepEqual(third.out, ["#40: closed, every child is closed (#41, #42, #43)"]);
  assert.deepEqual(comments(third), [
    "Every child of this story is closed, so the tick closes it.\n\n- #41: PR #60\n- #42: PR #62\n- #43: PR #63",
  ]);
  assert.deepEqual(patches(third), [{ state: "closed", state_reason: "completed", labels: [] }]);
  assert.ok(third.calls.indexOf(COMMENT(40)) < third.calls.indexOf(PATCH(40)));
  assert.deepEqual(started(third), []);
});

test("tick closes a parent read by `## Parent` line, naming a child with no PR", () => {
  const result = run(TICK, tickReplies({ issues: { 40: ["in-progress", "user-story"] } }, {
    [LIST_OF("in-progress")]: [[issue(40, { labels: ["in-progress", "user-story", "docs"], assignees: ["me"] })]],
    [SCAN]: [[child(41, 40, { state: "closed" }), child(42, 40, { state: "closed" }), issue(43, { state: "closed" })]],
    [PRS(41)]: prs([60, "MERGED"]),
    [PRS(42)]: prs(),
  }));
  assert.deepEqual(result.err, []);
  assert.deepEqual(result.out, ["#40: closed, every child is closed (#41, #42)"]);
  assert.deepEqual(comments(result), [
    "Every child of this story is closed, so the tick closes it.\n\n- #41: PR #60\n- #42: no PR",
  ]);
  assert.deepEqual(patches(result), [{ state: "closed", state_reason: "completed", labels: ["user-story", "docs"] }]);
});

// The replies `start 40` needs on a parent whose children the body scan finds, with
// #10 a leaf that holds a slot.
function parentReplies(parent: Fixture, children: unknown[], extra: Record<string, unknown> = {}) {
  return {
    [VIEW(40)]: issue(40, parent),
    [SCAN]: [children],
    [ME]: "me\n",
    [GIT]: "/repo/.git\n",
    [PATCH(40)]: issue(40, { labels: ["in-progress"], assignees: ["me"] }),
    [LIST_OF("in-progress")]: [[
      issue(10, { labels: ["in-progress"], assignees: ["me"] }),
      issue(40, { ...parent, labels: ["in-progress"], assignees: ["me"] }),
    ]],
    ...Object.fromEntries([41, 43, 44].map((n) => [PATCH(n), issue(n, { labels: ["in-progress"], assignees: ["me"] })])),
    [WORKER_START]: RECEIPT,
    ...extra,
  };
}

test("start on a parent claims it, then starts its eligible children up to the free slots", () => {
  const result = run(["start", "40", "--run", RUN], parentReplies({ labels: ["ready-for-agent"] }, [
    child(41, 40),
    child(42, 40, { labels: [] }),
    child(43, 40, { body: "Blocked by: #41" }),
    child(44, 40),
    child(45, 40, { state: "closed" }),
  ]), MAX(3));
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 0);
  assert.deepEqual(result.out, [
    "claimed parent #40: no worker, no slot",
    "started #41 in worktree issue-41: claude sonnet @ medium (medium role), dispatch ctx_54923f33c600",
    "#42 waits: not ready-for-agent",
    "#43 waits: blocked by #41",
    "started #44 in worktree issue-44: claude sonnet @ medium (medium role), dispatch ctx_54923f33c600",
  ]);
  assert.deepEqual(started(result), ["issue-41", "issue-44"]);
  assert.deepEqual(patches(result)[0], { labels: ["in-progress"], assignees: ["me"] });
});

test("start on a parent stops starting children when the slots run out", () => {
  const result = run(["start", "40", "--run", RUN], parentReplies({ labels: ["ready-for-agent"] }, [
    child(41, 40),
    child(44, 40),
  ]), MAX(2));
  assert.equal(result.code, 0);
  assert.deepEqual(started(result), ["issue-41"]);
  assert.deepEqual(result.out.at(-1), "#44 waits: no free slot");
});

test("start on a parent I already claimed reads its native sub-issues and starts them", () => {
  const result = run(["start", "40", "--run", RUN], parentReplies(
    { labels: ["in-progress"], assignees: ["me"], subIssues: 2 },
    [],
    { [SUB_ISSUES(40)]: [[issue(41), issue(43, { labels: ["in-progress", "user-story"] })]] },
  ), MAX(3));
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 0);
  assert.deepEqual(result.out, [
    "parent #40 is already claimed",
    "started #41 in worktree issue-41: claude sonnet @ medium (medium role), dispatch ctx_54923f33c600",
    "#43 waits: it is a parent, so it needs its own start",
  ]);
  assert.equal(result.calls.includes(PATCH(40)), false);
});

test("start on a parent that is not eligible claims nothing and starts no child", () => {
  const result = run(["start", "40", "--run", RUN], parentReplies(
    { labels: ["ready-for-agent", "user-story"], assignees: ["alice"] },
    [child(41, 40)],
  ));
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, ["#40 is not eligible: assigned to alice"]);
  assert.deepEqual(result.out, []);
  assert.equal(result.calls.some((c) => c.includes("-X ") || c.startsWith("orca")), false);
});
