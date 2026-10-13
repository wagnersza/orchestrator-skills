// `status`, `start`, `tick`, `merge` and `install` driven through the entry point, with a fake runner that replays
// recorded `gh api` and `orca` JSON and records every call.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, utimesSync, writeFileSync } from "node:fs";
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

const USAGE = "usage: orchestrator.ts status | start N [--role heavy|medium|light] [--note TEXT] [--run ID] | tick [--run ID] | merge N [--run ID] | install";
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

const GONE: Result = {
  code: 1,
  stdout: JSON.stringify({ ok: false, error: { code: "selector_not_found", message: "no worktree" } }),
  stderr: "",
};

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
    // An unlisted worktree is gone, the way orca answers for a name it does not know.
    if (key === undefined && line.startsWith("orca worktree show ")) return GONE;
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
    "# Orchestrator config\n\n```json\n{ \"tracker\": \"jira\", \"max_workers\": 2 }\n```\n\n```json\n{ \"tracker\": \"github\" }\n```\n",
  );
  const result = run(["status"], {}, cwd);
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, ['error: tracker "jira" is not supported yet']);
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
  for (const argv of [[], ["close"], ["status", "extra"], ["install", "extra"]]) {
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

const RUN = "run_1";
const COORDINATOR = "term_4f0ec745-92e8-4178-b33c-e0b32e2792db";
const ORCA = (...args: string[]) => `orca orchestration ${args.join(" ")} --json`;
const RUN_SHOW = ORCA("run-show", "--id", RUN);
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
    [RUN_SHOW]: receipt({ run: { id: RUN, coordinator_handle: COORDINATOR } }),
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
  assert.deepEqual(result.calls.slice(0, 7), [VIEW(10), SCAN, ME, GIT, RUN_SHOW, SHOW(10), PATCH(10)]);
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
    "--from", COORDINATOR,
    "--json",
  ]);
  assert.equal(result.calls.length, 8);
});

const SHOW = (n: number) => `orca worktree show --worktree name:issue-${n} --json`;
const RESUME_LINE = "This issue was resumed. Read the latest comments first: they answer why you stopped.";

test("start resumes in the existing worktree issue-N: no creation flags, and the resume line", () => {
  const result = run(
    ["start", "10", "--run", "run_1"],
    startReplies(10, {}, { [SHOW(10)]: receipt({ worktree: { path: "/wt/issue-10" } }) }),
  );
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 0);
  const argv = workerStart(result) ?? [];
  const spec = flag(argv, "--spec") ?? "";
  assert.deepEqual(argv, [
    "orca", "orchestration", "worker-start",
    "--spec", spec,
    "--task-title", "issue-10",
    "--worktree", "name:issue-10",
    "--agent", "claude",
    "--model", "sonnet",
    "--effort", "medium",
    "--run", "run_1",
    "--from", COORDINATOR,
    "--json",
  ]);
  assert.ok(spec.endsWith(`7. When you finish, send worker_done --outcome succeeded with the PR URL, or --outcome failed with the reason.\n\n${RESUME_LINE}\n`), spec);
});

test("start on a missing worktree makes a new one from base, with no resume line", () => {
  const result = run(["start", "10", "--run", "run_1"], startReplies(10));
  const argv = workerStart(result) ?? [];
  assert.equal(flag(argv, "--worktree"), "new-top-level");
  assert.equal(flag(argv, "--base-branch"), "main");
  assert.equal(flag(argv, "--spec")?.includes(RESUME_LINE), false);
});

test("start keeps the --note after the resume line", () => {
  const result = run(
    ["start", "10", "--run", "run_1", "--note", "Mind the cache."],
    startReplies(10, {}, { [SHOW(10)]: receipt({ worktree: { path: "/wt/issue-10" } }) }),
  );
  assert.ok(flag(workerStart(result), "--spec")?.endsWith(`${RESUME_LINE}\n\nMind the cache.\n`));
});

test("start stops before the claim when orca cannot say whether the worktree exists", () => {
  const result = run(["start", "10", "--run", "run_1"], startReplies(10, {}, {
    [SHOW(10)]: { fail: { code: 1, stdout: "", stderr: "orca is not running" } },
  }));
  assert.equal(result.code, 1);
  assert.equal(result.calls.includes(PATCH(10)), false);
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

// A repo whose config gives the medium role `role`.
function repoWithRole(role: Record<string, string>): string {
  return repoWithConfig(`\`\`\`json\n${JSON.stringify({ roles: { medium: role } })}\n\`\`\`\n`);
}

const WT_CREATE = (n: number) => `orca worktree create --name issue-${n} --repo path:/repo --base-branch main --no-parent --json`;
const TERMINAL_CREATE = "orca terminal create *";
const WAIT = (handle: string) => `orca terminal wait --terminal ${handle} --for tui-idle --timeout-ms 5000 --json`;
const ENTER = (handle: string) => `orca terminal send --terminal ${handle} --enter --json`;
const CLOSE = (handle: string) => `orca terminal close --terminal ${handle} --json`;
const TERMINAL = "term_w10";

// The `terminal wait` reply for a harness at its prompt, or held at a dialog.
function waited(blockedReason?: string) {
  return receipt({ wait: { handle: TERMINAL, condition: "tui-idle", satisfied: !blockedReason, status: "running", blockedReason } });
}

// The replies a terminal start on issue 10 needs, past the ones every start needs. The
// trust dialog is up until the key is sent.
const TERMINAL_STARTS = {
  [WT_CREATE(10)]: receipt({ worktree: { path: "/wt/issue-10" } }),
  [TERMINAL_CREATE]: receipt({ terminal: { handle: TERMINAL } }),
  [WAIT(TERMINAL)]: (calls: string[]) => waited(calls.includes(ENTER(TERMINAL)) ? undefined : "agent-trust-workspace"),
  [ENTER(TERMINAL)]: receipt({ send: { accepted: true } }),
};

// The orca calls a start made, after its claim.
function orcaCalls(result: { argvs: string[][]; calls: string[] }): string[][] {
  const claim = result.calls.indexOf(PATCH(10));
  return result.argvs.slice(claim + 1);
}

test("start renders each harness row's start arguments", () => {
  const cases: [string, Record<string, string>, string[][]][] = [
    ["claude", { harness: "claude", model: "opus", effort: "high" }, [
      ["--agent", "claude", "--model", "opus", "--effort", "high"],
    ]],
    ["codex", { harness: "codex", model: "gpt-5.5", effort: "medium" }, [
      ["--agent", "codex", "--model", "gpt-5.5", "--effort", "medium"],
    ]],
    ["cursor, an anthropic model", { harness: "cursor", model: "claude-opus-5", effort: "xhigh" }, [
      ["--agent", "cursor", "--model", "claude-opus-5-thinking-xhigh"],
    ]],
    ["cursor, any other model", { harness: "cursor", model: "gpt-5.6-terra", effort: "low" }, [
      ["--agent", "cursor", "--model", "gpt-5.6-terra-low"],
    ]],
  ];
  for (const [name, role, [flags]] of cases) {
    const result = run(["start", "10", "--run", "run_1"], startReplies(10), repoWithRole(role));
    assert.deepEqual(result.err, [], name);
    const argv = workerStart(result) ?? [];
    assert.deepEqual(argv, [
      "orca", "orchestration", "worker-start",
      "--spec", flag(argv, "--spec") ?? "",
      "--task-title", "issue-10",
      "--worktree", "new-top-level", "--name", "issue-10", "--repo", "path:/repo", "--base-branch", "main",
      ...(flags ?? []),
      "--run", "run_1", "--from", COORDINATOR, "--json",
    ], name);
  }
});

test("start runs pi in a terminal it creates, then binds that terminal as the worker", () => {
  const role = { harness: "pi", model: "anthropic/claude-sonnet-4-5", effort: "high" };
  const result = run(["start", "10", "--run", "run_1"], startReplies(10, {}, TERMINAL_STARTS), repoWithRole(role));
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 0);
  const calls = orcaCalls(result);
  const spec = flag(calls.at(-1), "--spec") ?? "";
  assert.deepEqual(calls, [
    ["orca", "worktree", "create", "--name", "issue-10", "--repo", "path:/repo", "--base-branch", "main", "--no-parent", "--json"],
    ["orca", "terminal", "create", "--worktree", "name:issue-10", "--title", "issue-10",
      "--command", "pi -t read,bash,edit,write,grep,find,ls --model anthropic/claude-sonnet-4-5 --thinking high", "--json"],
    ["orca", "orchestration", "worker-start", "--spec", spec, "--task-title", "issue-10", "--worktree", "name:issue-10",
      "--terminal", TERMINAL, "--run", "run_1", "--from", COORDINATOR, "--json"],
  ]);
  assert.deepEqual(result.out, [
    "started #10 in worktree issue-10: pi anthropic/claude-sonnet-4-5 @ high (medium role), dispatch ctx_54923f33c600",
  ]);
});

test("start runs copilot in a terminal, answers its trust dialog, and binds once the dialog is gone", () => {
  const role = { harness: "copilot", model: "gpt-5-mini", effort: "medium" };
  // Measured on orca 1.4.223 and copilot 1.0.96: copilot idles at boot before it draws
  // the dialog, and orca still reports the dialog for a second or two after the key.
  const readings = [undefined, "agent-trust-workspace", "agent-trust-workspace", "agent-trust-workspace", undefined];
  let waits = 0;
  const result = run(["start", "10", "--run", "run_1"], startReplies(10, {}, {
    ...TERMINAL_STARTS,
    [WAIT(TERMINAL)]: () => waited(readings[waits++]),
    "sleep 1": "",
  }), repoWithRole(role));
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 0);
  const calls = orcaCalls(result).map((argv) => argv.join(" "));
  assert.deepEqual(calls.slice(0, -1), [
    WT_CREATE(10),
    "orca terminal create --worktree name:issue-10 --title issue-10 --command copilot --allow-all --model gpt-5-mini --effort medium --json",
    WAIT(TERMINAL),
    "sleep 1",
    WAIT(TERMINAL),
    ENTER(TERMINAL),
    WAIT(TERMINAL),
    "sleep 1",
    WAIT(TERMINAL),
    "sleep 1",
    WAIT(TERMINAL),
  ]);
  assert.match(calls.at(-1) ?? "", new RegExp(`^orca orchestration worker-start --spec .* --terminal ${TERMINAL} --run run_1 `, "s"));
});

test("start closes copilot's terminal and unclaims when its trust dialog stays up after the key", () => {
  const role = { harness: "copilot", model: "gpt-5-mini", effort: "medium" };
  const result = run(["start", "10", "--run", "run_1"], startReplies(10, {}, {
    ...TERMINAL_STARTS,
    [WAIT(TERMINAL)]: waited("agent-trust-workspace"),
    [CLOSE(TERMINAL)]: receipt({ closed: true }),
    "sleep 1": "",
  }), repoWithRole(role));
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, [
    "error: answering the trust dialog of copilot failed, so #10 is unclaimed again: "
      + "orca still reported the dialog 30 readings after the key",
  ]);
  assert.equal(result.calls.filter((c) => c === ENTER(TERMINAL)).length, 1);
  assert.equal(workerStart(result), undefined);
  assert.deepEqual(result.calls.slice(-2), [CLOSE(TERMINAL), PATCH(10)]);
  assert.deepEqual(patches(result).at(-1), { labels: ["ready-for-agent"], assignees: [] });
});

test("start sends no key where copilot's trust dialog never shows", () => {
  const role = { harness: "copilot", model: "gpt-5-mini", effort: "medium" };
  const result = run(["start", "10", "--run", "run_1"], startReplies(10, {}, {
    ...TERMINAL_STARTS, [WAIT(TERMINAL)]: waited(), "sleep 1": "",
  }), repoWithRole(role));
  assert.equal(result.code, 0);
  assert.equal(result.calls.filter((c) => c === WAIT(TERMINAL)).length, 30);
  assert.equal(result.calls.includes(ENTER(TERMINAL)), false);
});

test("start on a terminal row resumes in the existing worktree, with no worktree create", () => {
  const role = { harness: "pi", model: "openai/gpt-5.5", effort: "low" };
  const result = run(["start", "10", "--run", "run_1"], startReplies(10, {}, {
    ...TERMINAL_STARTS, [SHOW(10)]: receipt({ worktree: { path: "/wt/issue-10" } }),
  }), repoWithRole(role));
  assert.equal(result.code, 0);
  assert.equal(result.calls.includes(WT_CREATE(10)), false);
  assert.equal(flag(workerStart(result), "--worktree"), "name:issue-10");
  assert.ok(flag(workerStart(result), "--spec")?.includes(RESUME_LINE));
});

test("start on a terminal row closes its terminal and unclaims when orca refuses the worker", () => {
  const role = { harness: "pi", model: "openai/gpt-5.5", effort: "low" };
  const result = run(["start", "10", "--run", "run_1"], startReplies(10, {}, {
    ...TERMINAL_STARTS, [WORKER_START]: REFUSED, [CLOSE(TERMINAL)]: receipt({ closed: true }),
  }), repoWithRole(role));
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, [
    "error: orca worker-start failed, so #10 is unclaimed again: repo_not_found Orchestration mutation request ID: 6de9.",
  ]);
  assert.deepEqual(result.calls.slice(-2), [CLOSE(TERMINAL), PATCH(10)]);
  assert.deepEqual(patches(result).at(-1), { labels: ["ready-for-agent"], assignees: [] });
});

test("start on a terminal row unclaims when orca cannot make the worktree", () => {
  const role = { harness: "copilot", model: "gpt-5-mini", effort: "low" };
  const result = run(["start", "10", "--run", "run_1"], startReplies(10, {}, {
    [WT_CREATE(10)]: { fail: { code: 1, stdout: JSON.stringify({ ok: false, error: { code: "repo_not_found", message: "no repo" } }), stderr: "" } },
  }), repoWithRole(role));
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, ["error: orca worktree create issue-10 failed, so #10 is unclaimed again: no repo"]);
  assert.equal(result.calls.some((c) => c.startsWith("orca terminal")), false);
});

test("start clamps an effort the harness cannot take, and reports the clamp", () => {
  const cases: [Record<string, string>, string[], string][] = [
    [{ harness: "codex", model: "gpt-5.5", effort: "xhigh" }, ["--effort", "high"],
      "codex gpt-5.5 @ high (medium role; effort xhigh clamped to high, the most codex takes)"],
    [{ harness: "codex", model: "gpt-5.5", effort: "max" }, ["--effort", "high"],
      "codex gpt-5.5 @ high (medium role; effort max clamped to high, the most codex takes)"],
    [{ harness: "pi", model: "openai/gpt-5.5", effort: "max" }, ["--thinking", "xhigh"],
      "pi openai/gpt-5.5 @ xhigh (medium role; effort max clamped to xhigh, the most pi takes)"],
  ];
  for (const [role, [name, value], line] of cases) {
    const result = run(["start", "10", "--run", "run_1"], startReplies(10, {}, TERMINAL_STARTS), repoWithRole(role));
    assert.deepEqual(result.err, [], line);
    assert.deepEqual(result.out, [`started #10 in worktree issue-10: ${line}, dispatch ctx_54923f33c600`]);
    const launched = role.harness === "pi"
      ? (result.argvs.find((argv) => argv[1] === "terminal" && argv[2] === "create") ?? [])[8]?.split(" ") ?? []
      : workerStart(result) ?? [];
    assert.equal(flag(launched, name ?? ""), value, line);
  }
});

test("start passes an effort the harness takes unchanged, with no clamp line", () => {
  for (const role of [
    { harness: "claude", model: "opus", effort: "max" },
    { harness: "codex", model: "gpt-5.5", effort: "high" },
    { harness: "copilot", model: "gpt-5-mini", effort: "max" },
  ]) {
    const result = run(["start", "10", "--run", "run_1"], startReplies(10, {}, TERMINAL_STARTS), repoWithRole(role));
    assert.equal(result.code, 0, role.harness);
    assert.doesNotMatch(result.out[0] ?? "", /clamped/, role.harness);
    assert.match(result.out[0] ?? "", new RegExp(`@ ${role.effort} \\(medium role\\)`), role.harness);
  }
});

test("start refuses a role its harness cannot launch in one line, before it claims", () => {
  const cases: [Record<string, string>, string][] = [
    [{ harness: "claude", model: "gpt-5.5" }, 'its medium role pairs model "gpt-5.5" with claude, which launches only anthropic models'],
    [{ harness: "codex", model: "opus" }, 'its medium role pairs model "opus" with codex, which launches only openai models'],
    [{ harness: "jules" }, 'its medium role names harness "jules", which is not one of claude, codex, cursor, pi, copilot'],
    [{ effort: "superhigh" }, 'its medium role asks effort "superhigh", which is not one of low, medium, high, xhigh, max'],
  ];
  for (const [role, why] of cases) {
    const result = run(["start", "10", "--run", "run_1"], startReplies(10), repoWithRole(role));
    assert.equal(result.code, 1, why);
    assert.deepEqual(result.err, [`#10 is not started: ${why}`]);
    assert.deepEqual(result.out, []);
    assert.deepEqual(result.calls, [VIEW(10), SCAN, ME], why);
  }
});

test("start names each skill the way the harness names one", () => {
  const cases: [Record<string, string>, string, string][] = [
    [{ harness: "claude", model: "sonnet" }, "2. Run /implement on it.", "Write its body with /pr,"],
    ...(["codex", "cursor", "pi", "copilot"].map((harness): [Record<string, string>, string, string] => [
      { harness, model: harness === "codex" ? "gpt-5.5" : "openai/gpt-5.5" },
      "2. Use the `implement` skill on it.",
      "Write its body with the `pr` skill,",
    ])),
  ];
  for (const [role, implement, pr] of cases) {
    const result = run(["start", "10", "--run", "run_1"], startReplies(10, {}, { ...TERMINAL_STARTS, "sleep 1": "" }), repoWithRole(role));
    const spec = flag(workerStart(result), "--spec") ?? "";
    assert.equal(spec.split("\n")[3], implement, role.harness);
    assert.ok(spec.split("\n")[5]?.includes(pr), `${role.harness}: ${spec}`);
  }
});

test("start reads the Run id from the run file when no --run is given", () => {
  const cwd = mkdtempSync(join(tmpdir(), "orch-"));
  mkdirSync(join(cwd, ".orchestrator"));
  writeFileSync(join(cwd, ".orchestrator", "run.json"), '{ "run": "run_from_file" }\n');
  const result = run(["start", "10"], startReplies(10, {}, {
    [ORCA("run-show", "--id", "run_from_file")]: receipt({ run: { id: "run_from_file", coordinator_handle: COORDINATOR } }),
  }), cwd);
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
    [REVIEW]: [[]],
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

// The ready-for-human issues in any state, which the tick reads for a merge on GitHub.
const REVIEW = "gh api --paginate --slurp repos/{owner}/{repo}/issues?state=all&labels=ready-for-human&per_page=100";

// The three lists a tick reads last: the ready-for-human issues, for a merge on GitHub,
// the in-progress issues, for the parents to close and the free slots, then the queue.
const FILL = [REVIEW, LIST_OF("in-progress"), LIST];

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

// The replies orca gave a release and a stop of a worker on a terminal the script
// created, on the copilot proof of run_caa3a9907dfe. The stop exits 1.
const KEPT_RELEASE = receipt({ dispatchId: "ctx_10", state: "retained", reason: "external_terminal", processAction: "none" });
const KEPT_STOP = {
  fail: {
    code: 1,
    stdout: JSON.stringify(receipt({
      dispatchId: "ctx_10", state: "stop_unknown", alreadySettled: false, processAction: "none",
      lastError: "The worker terminal is external; no terminal was closed.",
    })),
    stderr: "",
  },
};

test("tick closes the terminal of a terminal-start worker that orca releases but keeps running", () => {
  const result = run(TICK, tickReplies(
    {
      messages: [message(10, "worker_done", { outcome: "succeeded" })],
      tasks: [task(10)],
      workers: [{ ...worker(10), agentTerminalHandle: "term_w10" }],
      issues: { 10: ["in-progress"] },
    },
    { [PRS(10)]: prs([12, "OPEN"]), [RELEASE(10)]: KEPT_RELEASE, [CLOSE("term_w10")]: receipt({ closed: true }) },
  ));
  assert.deepEqual(result.err, []);
  assert.deepEqual(result.out, ["#10: in-progress -> ready-for-human (worker_done succeeded, PR #12); released ctx_10, closed its terminal"]);
  assert.deepEqual(result.calls.slice(6, 9), [RELEASE(10), CLOSE("term_w10"), PATCH(10)]);
});

test("tick closes the terminal of a terminal-start worker whose stop orca cannot finish", () => {
  const result = run(TICK, tickReplies(
    {
      messages: [message(10, "question", { body: "Keep the old flag?" })],
      tasks: [task(10)],
      workers: [{ ...worker(10), agentTerminalHandle: "term_w10" }],
      issues: { 10: ["in-progress"] },
    },
    { [STOP(10)]: KEPT_STOP, [CLOSE("term_w10")]: receipt({ closed: true }) },
  ));
  assert.deepEqual(result.err, []);
  assert.deepEqual(result.out, ["#10: in-progress -> needs-human (question); stopped ctx_10, closed its terminal, commented"]);
});

test("tick reports a terminal it cannot close, and still moves the issue", () => {
  const result = run(TICK, tickReplies(
    {
      messages: [message(10, "question", { body: "Keep the old flag?" })],
      tasks: [task(10)],
      workers: [{ ...worker(10), agentTerminalHandle: "term_w10" }],
      issues: { 10: ["in-progress"] },
    },
    { [STOP(10)]: KEPT_STOP },
  ));
  assert.deepEqual(result.err, ["tick: #10: orca terminal close term_w10 failed: unexpected call: orca terminal close --terminal term_w10 --json"]);
  assert.deepEqual(result.out, ["#10: in-progress -> needs-human (question); commented"]);
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

test("tick starts each worker from the Run's coordinator, read once, so no session needs to be open", () => {
  const result = run(TICK, tickReplies({ queue: [[10], [11]] }), MAX(3));
  assert.deepEqual(result.err, []);
  assert.deepEqual(result.argvs.filter((argv) => argv[2] === "worker-start").map((argv) => flag(argv, "--from")), [COORDINATOR, COORDINATOR]);
  assert.equal(result.calls.filter((line) => line === RUN_SHOW).length, 1);
});

test("start refuses a Run with no coordinator before it claims", () => {
  const result = run(["start", "10", "--run", RUN], startReplies(10, {}, {
    [RUN_SHOW]: receipt({ run: { id: RUN, coordinator_handle: null } }),
  }));
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, [`error: orca Run ${RUN} has no coordinator terminal, so no worker can start and its mailbox cannot be read`]);
  assert.deepEqual(patches(result), []);
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
    [RUN_SHOW]: receipt({ run: { id: RUN, coordinator_handle: COORDINATOR } }),
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

const MERGE = ["merge", "10", "--run", RUN];
const WT_SHOW = (n: number) => `orca worktree show --worktree name:issue-${n} --json`;
const WT_RM = (n: number) => `orca worktree rm --worktree name:issue-${n} --json`;
const GIT_STATUS = "git status --porcelain";
const PR_MERGE = "gh pr merge 12 -R wagnersza/orchestrator-skills --squash --delete-branch";
const OPEN_PR = prs([12, "OPEN", { mergeable: "MERGEABLE", reviewDecision: "APPROVED" }]);

// The `--json` reply of an orca call that found no worktree by the name it was given.
const NO_WORKTREE = {
  fail: {
    code: 1,
    stdout: JSON.stringify({ ok: false, error: { code: "selector_not_found", message: "selector_not_found" } }),
    stderr: "",
  },
};

// The replies `merge 10` needs on a ready-for-human issue with a clean worktree and an
// open, mergeable, approved PR #12 that GitHub shows merged once `gh pr merge` ran.
function mergeReplies(extra: Record<string, unknown> = {}) {
  return {
    [VIEW(10)]: issue(10, { labels: ["ready-for-human", "docs"], assignees: ["me"] }),
    [WT_SHOW(10)]: receipt({ worktree: { path: "/Users/me/orca/workspaces/repo/issue-10", displayName: "issue-10" } }),
    [GIT_STATUS]: "",
    [PRS(10)]: (calls: string[]) => (calls.includes(PR_MERGE) ? prs([12, "MERGED"]) : OPEN_PR),
    [PR_MERGE]: "",
    [TASKS]: receipt({ tasks: [task(10)] }),
    [WORKERS]: receipt({ workers: [worker(10, { dispatch: 101 }), worker(10, { dispatch: 100 })], page: { nextCursor: null } }),
    [ORCA("worker-release", "--dispatch", "ctx_101")]: receipt({ status: "already_released" }),
    [WT_RM(10)]: receipt({ removed: true }),
    [COMMENT(10)]: { id: 1 },
    [PATCH(10)]: issue(10, { state: "closed", labels: ["docs"], assignees: ["me"] }),
    ...extra,
  };
}

// The calls that change something: a write, a merge, a release or a removal.
function changes(result: { calls: string[] }): string[] {
  return result.calls.filter((c) => c.includes("-X ") || c.startsWith("gh pr merge") || c.includes("worker-release") || c.includes("worktree rm"));
}

test("merge squashes the PR, confirms it on GitHub, then tears down in order", () => {
  const result = run(MERGE, mergeReplies());
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 0);
  assert.deepEqual(result.out, [
    "#10: merged",
    "#10: torn down; released ctx_101, removed worktree issue-10, dropped ready-for-human, closed",
  ]);
  assert.deepEqual(result.calls, [
    VIEW(10), WT_SHOW(10), GIT_STATUS, PRS(10), PR_MERGE, PRS(10),
    TASKS, WORKERS, ORCA("worker-release", "--dispatch", "ctx_101"), WT_RM(10), COMMENT(10), PATCH(10),
  ]);
  assert.deepEqual(patches(result), [{ state: "closed", state_reason: "completed", labels: ["docs"] }]);
  assert.deepEqual(comments(result), [
    "The PR is merged, so this issue is torn down: released ctx_101, removed worktree issue-10, dropped ready-for-human, closed.",
  ]);
});

test("merge refuses in one line and changes nothing unless every precondition holds", () => {
  const cases: [string, Record<string, unknown>, string][] = [
    ["in-progress", { [VIEW(10)]: issue(10, { labels: ["in-progress"] }) }, "#10 is not merged: not ready-for-human"],
    ["needs-human", { [VIEW(10)]: issue(10, { labels: ["needs-human"] }) }, "#10 is not merged: not ready-for-human"],
    ["a dirty worktree", { [GIT_STATUS]: " M scripts/orchestrator.ts\n?? notes.md\n" }, "#10 is not merged: worktree issue-10 has uncommitted work"],
    ["no PR", { [PRS(10)]: prs() }, "#10 is not merged: no open PR closes #10"],
    ["a closed PR", { [PRS(10)]: prs([12, "CLOSED"]) }, "#10 is not merged: no open PR closes #10"],
    ["a merged PR", { [PRS(10)]: prs([12, "MERGED"], [13, "CLOSED"]) }, "#10 is not merged: PR #12 is already merged, so the next tick tears it down"],
    ["a conflict", { [PRS(10)]: prs([12, "OPEN", { mergeable: "CONFLICTING", reviewDecision: "APPROVED" }]) }, "#10 is not merged: PR #12 is not mergeable (conflicting)"],
    ["mergeable not computed yet", { [PRS(10)]: prs([12, "OPEN"]) }, "#10 is not merged: PR #12 is not mergeable (unknown)"],
    [
      "changes requested",
      { [PRS(10)]: prs([12, "OPEN", { mergeable: "MERGEABLE", reviewDecision: "CHANGES_REQUESTED" }]) },
      "#10 is not merged: PR #12 has changes requested",
    ],
  ];
  for (const [name, extra, line] of cases) {
    const result = run(MERGE, mergeReplies(extra));
    assert.equal(result.code, 1, name);
    assert.deepEqual(result.err, [line], name);
    assert.deepEqual(result.out, [], name);
    assert.deepEqual(changes(result), [], name);
  }
});

test("merge reads the open PR's own checks, not a newer closed one's", () => {
  const result = run(MERGE, mergeReplies({
    [PRS(10)]: (calls: string[]) => (calls.includes(PR_MERGE)
      ? prs([12, "MERGED"], [13, "CLOSED"])
      : prs([12, "OPEN", { mergeable: "MERGEABLE" }], [13, "CLOSED", { mergeable: "CONFLICTING" }])),
  }));
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 0);
  assert.ok(result.calls.includes(PR_MERGE));
});

test("merge tears nothing down until GitHub shows the PR merged", () => {
  const queued = run(MERGE, mergeReplies({ [PRS(10)]: OPEN_PR }));
  assert.equal(queued.code, 1);
  assert.deepEqual(queued.err, ["error: #10 is not confirmed merged, so nothing is torn down"]);
  assert.deepEqual(changes(queued), [PR_MERGE]);

  const failed = run(MERGE, mergeReplies({ [PRS(10)]: OPEN_PR, [PR_MERGE]: { fail: { code: 1, stdout: "", stderr: "Pull request is not mergeable: the base branch policy prohibits the merge." } } }));
  assert.equal(failed.code, 1);
  assert.deepEqual(failed.err, [
    `error: #10 is not confirmed merged, so nothing is torn down: ${PR_MERGE} failed: `
      + "Pull request is not mergeable: the base branch policy prohibits the merge.",
  ]);
  assert.deepEqual(changes(failed), [PR_MERGE]);
});

test("merge tears down when gh fails after GitHub took the merge, and says so", () => {
  const result = run(MERGE, mergeReplies({ [PR_MERGE]: { fail: { code: 1, stdout: "", stderr: "HTTP 502" } } }));
  assert.equal(result.code, 0);
  assert.deepEqual(result.out[0], `#10: merged, though the merge command failed: ${PR_MERGE} failed: HTTP 502`);
  assert.deepEqual(changes(result).slice(1), [ORCA("worker-release", "--dispatch", "ctx_101"), WT_RM(10), COMMENT(10), PATCH(10)]);
});

test("merge on an issue with no worktree and no worker still drops the label and closes", () => {
  const result = run(MERGE, mergeReplies({
    [WT_SHOW(10)]: NO_WORKTREE,
    [WT_RM(10)]: NO_WORKTREE,
    [WORKERS]: receipt({ workers: [], page: { nextCursor: null } }),
  }));
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 0);
  assert.equal(result.calls.includes(GIT_STATUS), false);
  assert.deepEqual(result.out.at(-1), "#10: torn down; dropped ready-for-human, closed");
  assert.deepEqual(patches(result), [{ state: "closed", state_reason: "completed", labels: ["docs"] }]);
});

test("teardown stops before the label when orca cannot remove the worktree", () => {
  const result = run(MERGE, mergeReplies({
    [WT_RM(10)]: { fail: { code: 1, stdout: JSON.stringify({ ok: false, error: { code: "worktree_dirty", message: "worktree has local changes" } }), stderr: "" } },
  }));
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, [
    "error: orca worktree rm issue-10 failed, so #10 keeps ready-for-human for the next tick: worktree has local changes",
  ]);
  assert.deepEqual(changes(result), [PR_MERGE, ORCA("worker-release", "--dispatch", "ctx_101"), WT_RM(10)]);
});

test("merge with no Run id stops before any call", () => {
  const result = run(["merge", "10"], mergeReplies());
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, ['error: no orca Run: pass --run <id>, or write { "run": "<id>" } to .orchestrator/run.json']);
  assert.deepEqual(result.calls, []);
});

test("merge refuses arguments it cannot read, with the usage", () => {
  for (const argv of [["merge"], ["merge", "ten"], ["merge", "1", "2"], ["merge", "1", "--role", "heavy"]]) {
    const result = run(argv, {});
    assert.equal(result.code, 2, argv.join(" "));
    assert.deepEqual(result.err, [USAGE]);
    assert.deepEqual(result.calls, []);
  }
});

test("merge takes #N", () => {
  const result = run(["merge", "#10", "--run", RUN], mergeReplies());
  assert.equal(result.code, 0);
});

test("tick tears down each ready-for-human issue merged on GitHub, closed by Closes #N or not", () => {
  const result = run(TICK, tickReplies(
    { tasks: [task(10), task(11)], workers: [worker(10), worker(11)] },
    {
      [REVIEW]: [[
        issue(10, { state: "closed", labels: ["ready-for-human"], assignees: ["me"] }),
        issue(11, { labels: ["ready-for-human", "docs"] }),
        issue(12, { labels: ["ready-for-human"], assignees: ["me"] }),
        issue(13, { state: "closed", labels: ["ready-for-human"], assignees: ["alice"] }),
      ]],
      [PRS(10)]: prs([12, "MERGED"]),
      [PRS(11)]: prs([14, "MERGED"]),
      [PRS(12)]: prs([15, "OPEN"]),
      [RELEASE(10)]: receipt({}),
      [RELEASE(11)]: receipt({}),
      [WT_RM(10)]: receipt({}),
      [WT_RM(11)]: receipt({}),
      [COMMENT(10)]: { id: 1 },
      [COMMENT(11)]: { id: 2 },
      [PATCH(10)]: issue(10, { state: "closed", labels: [] }),
      [PATCH(11)]: issue(11, { state: "closed", labels: ["docs"] }),
    },
  ));
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 1);
  assert.deepEqual(result.out, [
    "#10: torn down; released ctx_10, removed worktree issue-10, dropped ready-for-human, closed",
    "#11: torn down; released ctx_11, removed worktree issue-11, dropped ready-for-human, closed",
  ]);
  assert.deepEqual(result.calls, [
    TASKS, WORKERS, RUN_SHOW, CHECK, REVIEW, ME,
    PRS(10), RELEASE(10), WT_RM(10), COMMENT(10), PATCH(10),
    PRS(11), RELEASE(11), WT_RM(11), COMMENT(11), PATCH(11),
    PRS(12),
    LIST_OF("in-progress"), LIST,
  ]);
  assert.deepEqual(patches(result), [
    { state: "closed", state_reason: "completed", labels: [] },
    { state: "closed", state_reason: "completed", labels: ["docs"] },
  ]);
  assert.equal(result.calls.includes(PRS(13)), false);
});

test("tick reports a teardown orca cannot finish, keeps the label, and still fills", () => {
  const result = run(TICK, tickReplies({ queue: [[20]] }, {
    [REVIEW]: [[issue(10, { state: "closed", labels: ["ready-for-human"], assignees: ["me"] })]],
    [PRS(10)]: prs([12, "MERGED"]),
    [WT_RM(10)]: { fail: { code: 1, stdout: "", stderr: "orca is not running" } },
  }));
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, [
    "tick: orca worktree rm issue-10 failed, so #10 keeps ready-for-human for the next tick: orca is not running",
  ]);
  assert.equal(result.calls.includes(PATCH(10)), false);
  assert.deepEqual(started(result), ["issue-20"]);
});

const LABELS = "gh api --paginate --slurp repos/{owner}/{repo}/labels?per_page=100";
const LABEL_POST = "gh api -X POST repos/{owner}/{repo}/labels --input -";
const RUN_CREATE = "orca orchestration run-create *";
const AUTOMATIONS = "orca automations list --json";
const AUTOMATION_CREATE = "orca automations create *";
const AUTOMATION_EDIT = "orca automations edit *";
const PROOF = "sh -c *";
const SCRIPT = join(import.meta.dirname, "orchestrator.ts");
const EVERY = ["ready-for-agent", "in-progress", "needs-human", "ready-for-human", "heavy", "light"];

// The precheck install writes for the repo at `cwd`.
function precheck(cwd: string): string {
  return `cd '${cwd}' && '${process.execPath}' '${SCRIPT}' tick`;
}

// An `orca automations list` row, shaped like the one orca printed for the scratch repo.
function automation(fixture: { id?: string; name?: string; path?: string; precheck?: string; timeout?: number; rrule?: string; enabled?: boolean }) {
  return {
    id: fixture.id ?? "auto_1",
    name: fixture.name ?? "orchestrator-tick",
    precheck: { command: fixture.precheck ?? "", timeoutSeconds: fixture.timeout ?? 300 },
    agentId: "claude",
    runContext: { kind: "workspace-run", repoId: "79ff050a", path: fixture.path ?? "/repo" },
    workspaceMode: "existing",
    rrule: fixture.rrule ?? "* * * * *",
    enabled: fixture.enabled ?? true,
  };
}

// The replies an install needs, with `labels` the repo already has and `automations`
// orca already lists. The proof tick is a quiet one: no output, exit 1.
function installReplies(labels: string[], automations: unknown[], extra: Record<string, unknown> = {}) {
  return {
    [LABELS]: [labels.map((name) => ({ name, color: "ededed" }))],
    [LABEL_POST]: { id: 1 },
    [RUN_CREATE]: receipt({ run: { id: "run_new", coordinator_handle: COORDINATOR } }),
    [GIT]: "/repo/.git\n",
    [AUTOMATIONS]: receipt({ automations, items: [], orphanCount: 0 }),
    [AUTOMATION_CREATE]: receipt({ automation: { id: "auto_new" } }),
    [AUTOMATION_EDIT]: receipt({ automation: { id: "auto_1" } }),
    [PROOF]: { fail: { code: 1, stdout: "", stderr: "" } },
    ...extra,
  };
}

function withRunFile(text: string): string {
  const cwd = mkdtempSync(join(tmpdir(), "orch-"));
  mkdirSync(join(cwd, ".orchestrator"));
  writeFileSync(join(cwd, ".orchestrator", "run.json"), text);
  return cwd;
}

function runFile(cwd: string): string {
  return readFileSync(join(cwd, ".orchestrator", "run.json"), "utf8");
}

test("install on a bare repo creates the labels, the Run and the automation, then runs one tick", () => {
  const cwd = mkdtempSync(join(tmpdir(), "orch-"));
  // Another repo's automation of the same name is not this repo's.
  const result = run(["install"], installReplies(["bug", "ready-for-agent"], [automation({ id: "other", path: "/elsewhere" })]), cwd);
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 0);
  assert.deepEqual(result.out, [
    "label ready-for-agent: present",
    "label in-progress: created",
    "label needs-human: created",
    "label ready-for-human: created",
    "label heavy: created",
    "label light: created",
    "run run_new: created, saved to .orchestrator/run.json",
    `automation orchestrator-tick: created (auto_new), precheck ${precheck(cwd)}`,
    "tick: exit 1, the precheck works",
  ]);
  assert.deepEqual(
    result.calls.flatMap((line, i) => (line === LABEL_POST ? [(JSON.parse(result.inputs[i] ?? "") as { name: string }).name] : [])),
    EVERY.slice(1),
  );
  assert.deepEqual(JSON.parse(runFile(cwd)), { run: "run_new" });
  const create = result.argvs.find((argv) => argv[1] === "automations" && argv[2] === "create") ?? [];
  assert.deepEqual(create, [
    "orca", "automations", "create",
    "--name", "orchestrator-tick",
    "--trigger", "* * * * *",
    "--precheck", precheck(cwd),
    "--precheck-timeout", "300",
    "--prompt", flag(create, "--prompt") ?? "",
    "--provider", "claude",
    "--workspace", `path:${cwd}`,
    "--enabled",
    "--json",
  ]);
  assert.deepEqual(result.argvs.at(-1), ["sh", "-c", precheck(cwd)]);
  assert.equal(result.calls.some((line) => line.startsWith("orca automations edit")), false);
});

test("a second install finds every part present and creates nothing", () => {
  const cwd = withRunFile('{ "run": "run_1" }\n');
  const result = run(["install"], installReplies(
    ["Ready-For-Agent", "in-progress", "needs-human", "ready-for-human", "Heavy", "light"],
    [automation({ precheck: precheck(cwd) })],
    { [RUN_SHOW]: receipt({ run: { id: RUN, coordinator_handle: COORDINATOR } }) },
  ), cwd);
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 0);
  assert.deepEqual(result.out, [
    ...EVERY.map((name) => `label ${name}: present`),
    "run run_1: present",
    "automation orchestrator-tick: present (auto_1)",
    "tick: exit 1, the precheck works",
  ]);
  assert.deepEqual(result.calls, [LABELS, RUN_SHOW, GIT, AUTOMATIONS, `sh -c ${precheck(cwd)}`]);
  assert.equal(runFile(cwd), '{ "run": "run_1" }\n');
});

test("install creates the role labels the config names", () => {
  const cwd = repoWithConfig('```json\n{ "role_labels": { "heavy": "size:L", "light": "size:S" } }\n```\n');
  const result = run(["install"], installReplies(EVERY, [automation({ precheck: precheck(cwd) })]), cwd);
  assert.equal(result.code, 0);
  assert.deepEqual(result.out.slice(4, 6), ["label size:L: created", "label size:S: created"]);
});

test("install replaces a saved Run that is gone, has no coordinator, or does not parse", () => {
  const cases: [string, string, Record<string, unknown>, string][] = [
    ["gone", '{ "run": "run_1" }\n', {
      [RUN_SHOW]: { fail: { code: 1, stdout: JSON.stringify({ ok: false, error: { code: "run_not_found", message: "Run run_1 was not found." } }), stderr: "" } },
    }, "run run_new: created, in place of run_1, which orca no longer has, saved to .orchestrator/run.json"],
    ["no coordinator", '{ "run": "run_1" }\n', {
      [RUN_SHOW]: receipt({ run: { id: RUN, coordinator_handle: null } }),
    }, "run run_new: created, in place of run_1, which has no coordinator terminal, saved to .orchestrator/run.json"],
    ["not JSON", "run_1\n", {}, "run run_new: created, saved to .orchestrator/run.json"],
  ];
  for (const [name, text, extra, line] of cases) {
    const cwd = withRunFile(text);
    const result = run(["install"], installReplies(EVERY, [automation({ precheck: precheck(cwd) })], extra), cwd);
    assert.equal(result.code, 0, name);
    assert.equal(result.out[6], line, name);
    assert.deepEqual(JSON.parse(runFile(cwd)), { run: "run_new" }, name);
  }
});

test("install stops, and keeps the run file, when orca cannot say whether the Run exists", () => {
  const cwd = withRunFile('{ "run": "run_1" }\n');
  const result = run(["install"], installReplies(EVERY, [], {
    [RUN_SHOW]: { fail: { code: 1, stdout: "", stderr: "orca is not running" } },
  }), cwd);
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, ["error: orca run-show run_1 failed: orca is not running"]);
  assert.equal(result.calls.some((line) => line.startsWith("orca orchestration run-create")), false);
  assert.equal(runFile(cwd), '{ "run": "run_1" }\n');
});

test("install repairs this repo's automation where its precheck, timeout, trigger or switch differs", () => {
  const cases: [string, Parameters<typeof automation>[0]][] = [
    ["an old node path", { precheck: "cd '/repo' && '/old/node' '/old/orchestrator.ts' tick" }],
    ["orca's default timeout", { timeout: 60 }],
    ["another trigger", { rrule: "hourly" }],
    ["switched off", { enabled: false }],
  ];
  for (const [name, fixture] of cases) {
    const cwd = withRunFile('{ "run": "run_1" }\n');
    const result = run(["install"], installReplies(EVERY, [automation({ precheck: precheck(cwd), ...fixture })], {
      [RUN_SHOW]: receipt({ run: { id: RUN, coordinator_handle: COORDINATOR } }),
    }), cwd);
    assert.equal(result.code, 0, name);
    assert.equal(result.out[7], `automation orchestrator-tick: repaired (auto_1), precheck ${precheck(cwd)}`, name);
    assert.deepEqual(result.argvs.find((argv) => argv[2] === "edit"), [
      "orca", "automations", "edit", "--id", "auto_1", "--trigger", "* * * * *",
      "--precheck", precheck(cwd), "--precheck-timeout", "300", "--enabled", "--json",
    ], name);
    assert.equal(result.calls.some((line) => line.startsWith("orca automations create")), false, name);
  }
});

test("install prints the proof tick's output, and exits 1 when the precheck fails", () => {
  const cases: [string, unknown, string[], number][] = [
    ["a tick that acted", { fail: { code: 1, stdout: "started #10 in worktree issue-10\n", stderr: "" } },
      ["tick: exit 1, the precheck works", "  started #10 in worktree issue-10"], 0],
    ["a tick another tick locked out", { fail: { code: 1, stdout: "", stderr: "tick: another tick holds .orchestrator/tick.lock, so this one exits\n" } },
      ["tick: exit 1, the precheck works", "  tick: another tick holds .orchestrator/tick.lock, so this one exits"], 0],
    ["a tick that errored", { fail: { code: 1, stdout: "", stderr: "error: orca orchestration task-list failed: orca is not running\n" } },
      ["tick: exit 1, the precheck fails", "  error: orca orchestration task-list failed: orca is not running"], 1],
    ["no node", { fail: { code: 127, stdout: "", stderr: "sh: /old/node: No such file or directory\n" } },
      ["tick: exit 127, the precheck fails", "  sh: /old/node: No such file or directory"], 1],
  ];
  for (const [name, proof, lines, code] of cases) {
    const cwd = mkdtempSync(join(tmpdir(), "orch-"));
    const result = run(["install"], installReplies(EVERY, [automation({ precheck: precheck(cwd) })], { [PROOF]: proof }), cwd);
    assert.equal(result.code, code, name);
    assert.deepEqual(result.out.slice(-lines.length), lines, name);
  }
});

test("the precheck names node, the script and the repo by absolute path, so it runs from any directory", () => {
  const cwd = mkdtempSync(join(tmpdir(), "orch it's-"));
  const result = run(["install"], installReplies(EVERY, [automation({ precheck: precheck(cwd) })]), cwd);
  const command = result.argvs.at(-1)?.[2] ?? "";
  assert.equal(command, `cd '${cwd.replace("'", "'\\''")}' && '${process.execPath}' '${SCRIPT}' tick`);
  // The real shell, from another directory and with no PATH, reaches the real tick in
  // `cwd`. With the run file gone, that tick stops at its first step.
  rmSync(join(cwd, ".orchestrator", "run.json"));
  const proof = spawnSync("/bin/sh", ["-c", command], { cwd: tmpdir(), env: {}, encoding: "utf8" });
  assert.equal(proof.status, 1);
  assert.match(proof.stderr, /^error: no orca Run: /);
});
