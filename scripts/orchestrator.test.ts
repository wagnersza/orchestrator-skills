// `status` driven through the entry point, with a fake runner that replays recorded
// `gh api` JSON and records every call.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { main } from "./orchestrator.ts";
import type { Sh } from "./sh.ts";

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

const ME = "gh api user --jq .login";
const LIST = "gh api --paginate --slurp repos/{owner}/{repo}/issues?state=open&labels=ready-for-agent&per_page=100";
const VIEW = (n: number) => `gh api repos/{owner}/{repo}/issues/${n}`;
const NATIVE = (n: number) =>
  `gh api --paginate --slurp repos/{owner}/{repo}/issues/${n}/dependencies/blocked_by?per_page=100`;

// A runner that answers each known command line with its recorded output, and fails
// any other call, the way `gh` fails on a path it does not know.
function fakeRunner(replies: Record<string, unknown>) {
  const calls: string[] = [];
  const sh: Sh = (cmd, args) => {
    const line = [cmd, ...args].join(" ");
    calls.push(line);
    if (!(line in replies)) return { code: 1, stdout: "", stderr: `unexpected call: ${line}` };
    const reply = replies[line];
    return { code: 0, stdout: typeof reply === "string" ? reply : JSON.stringify(reply), stderr: "" };
  };
  return { sh, calls };
}

function run(argv: string[], replies: Record<string, unknown>, cwd = mkdtempSync(join(tmpdir(), "orch-"))) {
  const runner = fakeRunner(replies);
  const out: string[] = [];
  const err: string[] = [];
  const code = main(argv, { sh: runner.sh, cwd, out: (l) => out.push(l), err: (l) => err.push(l) });
  return { code, out, err, calls: runner.calls };
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
    assert.deepEqual(result.err, ["usage: orchestrator.ts status"]);
  }
});

test("node runs the script directly, with no build step", () => {
  const script = join(import.meta.dirname, "orchestrator.ts");
  const result = spawnSync(process.execPath, [script, "no-such-subcommand"], { encoding: "utf8" });
  assert.equal(result.status, 2);
  assert.equal(result.stderr, "usage: orchestrator.ts status\n");
});
