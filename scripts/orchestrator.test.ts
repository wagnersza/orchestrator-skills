// `status` and `start` driven through the entry point, with a fake runner that replays
// recorded `gh api` and `orca` JSON and records every call.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
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
  body: "## Parent\n\n#348\n\n## What to build\n\nThe first tracer bullet f",
};

type Fixture = {
  title?: string;
  labels?: string[];
  state?: string;
  assignees?: string[];
  body?: string;
  blockedBy?: number;
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
    body: fixture.body ?? RECORDED.body,
    ...(fixture.pr ? { pull_request: { url: `${repo}/pulls/${number}` } } : {}),
  };
}

const USAGE = "usage: orchestrator.ts status | start N [--role heavy|medium|light] [--note TEXT] [--run ID]";
const ME = "gh api user --jq .login";
const LIST = "gh api --paginate --slurp repos/{owner}/{repo}/issues?state=open&labels=ready-for-agent&per_page=100";
const VIEW = (n: number) => `gh api repos/{owner}/{repo}/issues/${n}`;
const NATIVE = (n: number) =>
  `gh api --paginate --slurp repos/{owner}/{repo}/issues/${n}/dependencies/blocked_by?per_page=100`;

// A failed command, for a reply. A command that succeeds replies with its stdout.
type Failure = { fail: Result };

// A runner that answers each known command line with its recorded output, and fails
// any other call, the way `gh` fails on a path it does not know. A key that ends in
// " *" answers every line it prefixes.
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
    const reply = replies[key];
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
    [ME]: "me\n",
    [LIST]: [[issue(10), issue(11, { blockedBy: 1 })]],
    [NATIVE(11)]: [[issue(20, { state: "closed" })]],
  });
  assert.equal(result.code, 0);
  assert.deepEqual(result.calls, [ME, LIST, NATIVE(11)]);
});

test("status reads a blocker once, even when two forms name it", () => {
  const result = run(["status"], {
    [ME]: "me\n",
    [LIST]: [[issue(10, { blockedBy: 1, body: "Blocked by: #20" })]],
    [NATIVE(10)]: [[issue(20)]],
  });
  assert.deepEqual(result.out, ["ready queue (0)", "not eligible (1)", "  #10  issue 10  (blocked by #20)"]);
  assert.deepEqual(result.calls, [ME, LIST, NATIVE(10)]);
});

test("status names a native blocker in another repo by its repo", () => {
  const other = "https://api.github.com/repos/acme/infra";
  const result = run(["status"], {
    [ME]: "me\n",
    [LIST]: [[issue(10, { blockedBy: 1 })]],
    [NATIVE(10)]: [[issue(7, { repo: other })]],
  });
  assert.deepEqual(result.out.slice(-1), ["  #10  issue 10  (blocked by acme/infra#7)"]);
});

test("status skips pull requests, which the issues endpoint also returns", () => {
  const result = run(["status"], {
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
  const result = run(["status"], { [ME]: "me\n", [LIST]: [[issue(10)]] }, cwd);
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
  const result = run(["status"], { [ME]: "me\n" });
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, [`error: ${LIST} failed: unexpected call: ${LIST}`]);
});

test("an unknown subcommand prints the usage and exits 2", () => {
  for (const argv of [[], ["tick"], ["status", "extra"]]) {
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
  assert.deepEqual(result.calls.slice(0, 4), [VIEW(10), ME, GIT, PATCH(10)]);
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
  assert.equal(result.calls.length, 5);
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
    assert.deepEqual(result.calls.filter((c) => !c.startsWith("gh api repos/") && c !== ME), [], line);
  }
});

test("start refuses a role whose harness is not claude, before it claims", () => {
  const cwd = repoWithConfig('```json\n{ "roles": { "heavy": { "harness": "codex" } } }\n```\n');
  const result = run(["start", "10", "--run", "run_1", "--role", "heavy"], startReplies(10), cwd);
  assert.equal(result.code, 1);
  assert.deepEqual(result.err, ["#10 is not started: its heavy role runs on codex, and start launches only claude for now"]);
  assert.deepEqual(result.calls, [VIEW(10), ME]);
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
