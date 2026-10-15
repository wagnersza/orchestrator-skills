// The local backend through the entry point, against a real git repository in a temp
// dir. git runs for real, and a fake orca stands in for the workers: a worker-start adds
// a real worktree on its own branch. A test plays the worker. It commits in that
// worktree, appends its review under `## Comments` where the prompt says, and queues its
// mailbox message.

import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { main } from "../orchestrator.ts";
import { sh as realSh, type Result, type Sh } from "../sh.ts";
import { local } from "./local.ts";

const RUN = "run_1";
const ME = "Ada Lovelace";
const CONFIG = { "docs/agents/orchestrator.md": '```json\n{ "tracker": "local" }\n```\n' };

function git(cwd: string, ...args: string[]): string {
  const run = realSh("git", args, { cwd });
  if (run.code !== 0) throw new Error(`git ${args.join(" ")} failed: ${run.stderr}`);
  return run.stdout;
}

function write(root: string, files: Record<string, string>): void {
  for (const [path, text] of Object.entries(files)) {
    mkdirSync(dirname(join(root, path)), { recursive: true });
    writeFileSync(join(root, path), text);
  }
}

function read(root: string, path: string): string {
  return readFileSync(join(root, path), "utf8");
}

// A repo whose main holds the config and `files`, all committed, `.scratch/` with them.
function repo(files: Record<string, string>): string {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "orch-local-")));
  git(root, "init", "-q", "-b", "main");
  git(root, "config", "user.name", ME);
  git(root, "config", "user.email", "ada@example.com");
  git(root, "config", "commit.gpgsign", "false");
  write(root, { ...CONFIG, ...files });
  git(root, "add", "-A");
  git(root, "commit", "-q", "-m", "init");
  return root;
}

type Worker = {
  dispatchId: string;
  taskId: string;
  title: string;
  resource: { worktreeId: string };
  projection: { liveness: { verdict: string } };
};

const ok = (result: unknown): Result => ({ code: 0, stdout: JSON.stringify({ ok: true, result }), stderr: "" });

// orca, as far as the loop reads it. Each worker-start adds worktree issue-<feature>-NN
// on branch `ada/<name>`, or reuses the one a resume finds. Every other command goes to
// the real runner.
class Orca {
  workers: Worker[] = [];
  worktrees = new Map<string, string>();
  specs: string[] = [];
  mailbox: unknown[] = [];
  calls: string[] = [];
  readonly dir = realpathSync(mkdtempSync(join(tmpdir(), "orch-wt-")));

  readonly root: string;

  constructor(root: string) {
    this.root = root;
  }

  sh: Sh = (cmd, args, opts) => {
    if (cmd !== "orca") return realSh(cmd, args, opts);
    this.calls.push(args.slice(0, 2).join(" "));
    return this.call(args);
  };

  private call(args: string[]): Result {
    const flag = (name: string) => (args.includes(name) ? args[args.indexOf(name) + 1] : "") ?? "";
    const [group, verb] = args;
    if (group === "worktree") {
      const name = flag("--worktree").replace(/^name:/, "");
      const path = this.worktrees.get(name);
      if (!path) return { code: 1, stdout: JSON.stringify({ ok: false, error: { code: "selector_not_found", message: "no worktree" } }), stderr: "" };
      if (verb === "show") return ok({ worktree: { path } });
      git(this.root, "worktree", "remove", "--force", path);
      this.worktrees.delete(name);
      return ok({ removed: true });
    }
    if (verb === "run-show") return ok({ run: { id: RUN, coordinator_handle: "term_1" } });
    if (verb === "worker-start") {
      const name = flag("--name") || flag("--worktree").replace(/^name:/, "");
      if (!this.worktrees.has(name)) {
        const path = join(this.dir, name);
        git(this.root, "worktree", "add", "-q", "-b", `ada/${name}`, path, flag("--base-branch"));
        this.worktrees.set(name, path);
      }
      const n = this.workers.length + 1;
      this.workers.unshift({
        dispatchId: `ctx_${n}`,
        taskId: `task_${n}`,
        title: name,
        resource: { worktreeId: `repo::${this.worktrees.get(name)}` },
        projection: { liveness: { verdict: "alive" } },
      });
      this.specs.push(flag("--spec"));
      return ok({ dispatchId: `ctx_${n}` });
    }
    if (verb === "task-list") return ok({ tasks: this.workers.map((w) => ({ id: w.taskId, task_title: w.title, result: null })) });
    if (verb === "worker-list") return ok({ workers: this.workers, page: { nextCursor: null } });
    if (verb === "check" && args.includes("--ack")) {
      this.mailbox = [];
      return ok({ deliveryId: null, messages: [] });
    }
    if (verb === "check") return ok({ deliveryId: this.mailbox.length ? "delivery_1" : null, messages: this.mailbox });
    if (verb === "worker-release" || verb === "worker-stop") return ok({});
    return { code: 1, stdout: "", stderr: `unexpected call: orca ${args.join(" ")}` };
  }

  // The newest worker of worktree `name`.
  worker(name: string): Worker {
    const found = this.workers.find((w) => w.title === name);
    if (!found) throw new Error(`no worker on ${name}`);
    return found;
  }

  // Queue a message from the newest worker of `name`.
  send(name: string, type: string, body: string, outcome?: string): void {
    const { dispatchId, taskId } = this.worker(name);
    this.mailbox.push({
      id: `msg_${this.mailbox.length + 1}`, type, body, from_handle: `dispatch:${dispatchId}`,
      payload: JSON.stringify({ taskId, dispatchId, ...(outcome ? { outcome } : {}) }),
    });
  }

  // Play the worker on `name`: commit `file` in its worktree, then append its review where
  // the newest prompt's review step names the ticket.
  work(name: string, file: string, review: string): void {
    const path = this.worktrees.get(name) ?? "";
    write(path, { [file]: `${file}\n` });
    git(path, "add", file);
    git(path, "commit", "-q", "-m", `feat: add ${file}`);
    const ticket = /append it under "## Comments" at the end of (.+)\.$/m.exec(this.specs.at(-1) ?? "")?.[1] ?? "";
    writeFileSync(ticket, `${readFileSync(ticket, "utf8")}\n${review}\n`);
  }
}

function runMain(orca: Orca, ...argv: string[]) {
  const out: string[] = [];
  const err: string[] = [];
  const code = main(argv, { sh: orca.sh, cwd: orca.root, out: (l) => out.push(l), err: (l) => err.push(l) });
  return { code, out, err };
}

// Assigned, so the tick takes the story and each ticket under it.
const SPEC = "# Search\n\nStatus: ready-for-agent\nAssignee: Ada Lovelace\n\nFind things fast.\n";
const INDEX = [
  "# 01: Build the index",
  "",
  "**What to build:** an index of every document.",
  "",
  "**Blocked by:** None (can start immediately)",
  "",
  "**Status:** ready-for-agent",
  "",
  "- [ ] It indexes",
  "",
].join("\n");
const QUERY = "# 02: Query the index\n\nStatus: ready-for-agent\nBlocked by: 01\n\n## What to build\n\nA query.\n";

const STORY = {
  ".scratch/search/spec.md": SPEC,
  ".scratch/search/issues/01-index.md": INDEX,
  ".scratch/search/issues/02-query.md": QUERY,
};

const TICK = ["tick", "--run", RUN];

// The squash commits on main, newest first, with their trailers.
function squashes(root: string): string[] {
  return git(root, "log", "main", "--format=%s | %(trailers:key=Resolves,valueonly)").trim().split("\n").filter((l) => l.includes("("));
}

test("local: a story with two tickets, one blocked by the other, runs through every state and ends resolved and merged", () => {
  const root = repo(STORY);
  const orca = new Orca(root);
  const index = ".scratch/search/issues/01-index.md";
  const query = ".scratch/search/issues/02-query.md";

  assert.deepEqual(runMain(orca, "status"), {
    code: 0,
    out: ["ready queue (2)", "  search  Search", "  search/01  Build the index", "not eligible (1)", "  search/02  Query the index  (blocked by search/01)"],
    err: [],
  });

  // The tick claims the parent with no worker, and starts the one ticket nothing blocks.
  assert.deepEqual(runMain(orca, ...TICK), {
    code: 1,
    out: ["claimed parent search: no worker, no slot", "started search/01 in worktree issue-search-01: claude sonnet @ medium (medium role), dispatch ctx_1"],
    err: [],
  });
  assert.match(read(root, ".scratch/search/spec.md"), /^Status: in-progress\nAssignee: Ada Lovelace\n/m);
  assert.match(read(root, index), /^\*\*Status:\*\* in-progress\n\*\*Assignee:\*\* Ada Lovelace\n\n- \[ \] It indexes/m);
  assert.ok(orca.specs[0]?.includes(`1. Read the issue and every comment: cat '${join(root, index)}'`), orca.specs[0]);
  assert.ok(orca.specs[0]?.includes(
    "4. Leave the work committed on your branch, and push nothing: the branch is the review surface, and main takes it "
      + `as a squash merge. Write its description with /pr, and append it under "## Comments" at the end of ${join(root, index)}.`,
  ), orca.specs[0]);

  // The worker asks, so the ticket goes to needs-human with the question under ## Comments.
  orca.send("issue-search-01", "question", "Index titles too?");
  assert.deepEqual(runMain(orca, ...TICK), {
    code: 1,
    out: ["search/01: in-progress -> needs-human (question); stopped ctx_1, commented"],
    err: [],
  });
  assert.match(read(root, index), /\*\*Status:\*\* needs-human\n[\s\S]*- \[ \] It indexes\n\n## Comments\n\nThe worker asked a question, and the tick stopped it:\n\n> Index titles too\?\n\n/);

  // The human answers under ## Comments and sets the Status back, and the next tick resumes it.
  write(root, { [index]: `${read(root, index).replace("**Status:** needs-human", "**Status:** ready-for-agent")}\nYes, titles too.\n` });
  assert.deepEqual(runMain(orca, ...TICK), {
    code: 1,
    out: ["started search/01 in worktree issue-search-01: claude sonnet @ medium (medium role), dispatch ctx_2"],
    err: [],
  });
  assert.match(read(root, index), /\*\*Status:\*\* in-progress\n\*\*Assignee:\*\* Ada Lovelace\n/);

  orca.work("issue-search-01", "index.txt", "## Build the index\n\nAdds the index.");
  orca.send("issue-search-01", "worker_done", "Done on ada/issue-search-01.", "succeeded");
  assert.deepEqual(runMain(orca, ...TICK), {
    code: 1,
    out: ["search/01: in-progress -> ready-for-human (worker_done succeeded, PR ada/issue-search-01); released ctx_2"],
    err: [],
  });
  assert.match(read(root, index), /\nYes, titles too\.\n\n## Build the index\n\nAdds the index\.\n$/);

  // A dirty main checkout refuses the merge and changes nothing.
  write(root, { "notes.txt": "draft\n" });
  const head = git(root, "rev-parse", "HEAD");
  assert.deepEqual(runMain(orca, "merge", "search/01", "--run", RUN), {
    code: 1,
    out: [],
    err: [`search/01 is not merged: the main checkout ${root} has uncommitted changes`],
  });
  assert.equal(git(root, "rev-parse", "HEAD"), head);
  assert.match(read(root, index), /\*\*Status:\*\* ready-for-human\n/);
  rmSync(join(root, "notes.txt"));

  assert.deepEqual(runMain(orca, "merge", "search/01", "--run", RUN), {
    code: 0,
    out: ["search/01: merged", "search/01: torn down; released ctx_2, removed worktree issue-search-01, dropped ready-for-human, closed"],
    err: [],
  });
  assert.match(read(root, index), /\*\*Status:\*\* resolved\n/);

  // The blocker is resolved, so the next tick starts the second ticket on the new main.
  assert.deepEqual(runMain(orca, ...TICK), {
    code: 1,
    out: ["started search/02 in worktree issue-search-02: claude sonnet @ medium (medium role), dispatch ctx_3"],
    err: [],
  });
  orca.work("issue-search-02", "query.txt", "## Query the index\n\nAdds the query.");
  orca.send("issue-search-02", "worker_done", "Done.", "succeeded");
  assert.equal(runMain(orca, ...TICK).out[0], "search/02: in-progress -> ready-for-human (worker_done succeeded, PR ada/issue-search-02); released ctx_3");
  assert.equal(runMain(orca, "merge", "search/02", "--run", RUN).code, 0);

  // Every child is resolved, so the tick closes the story.
  const [second, first] = git(root, "log", "-2", "--format=%h", "main").trim().split("\n");
  assert.deepEqual(runMain(orca, ...TICK), {
    code: 1,
    out: ["search: closed, every child is closed (search/01, search/02)"],
    err: [],
  });
  assert.ok(read(root, ".scratch/search/spec.md").endsWith(
    `## Comments\n\nEvery child of this story is closed, so the tick closes it.\n\n- search/01: PR ${first}\n- search/02: PR ${second}\n`,
  ));

  for (const path of [".scratch/search/spec.md", index, query]) assert.match(read(root, path), /^(\*\*)?Status:(\*\*)? resolved$/m, path);
  assert.deepEqual(squashes(root), ["Query the index (search/02) | search/02", "Build the index (search/01) | search/01"]);
  assert.deepEqual([existsSync(join(root, "index.txt")), existsSync(join(root, "query.txt"))], [true, true]);
  assert.equal(git(root, "status", "--porcelain", "--", ".", ":(exclude).scratch", ":(exclude).orchestrator"), "");
  assert.deepEqual([...orca.worktrees.keys()], []);
  assert.equal(git(root, "worktree", "list").trim().split("\n").length, 1);
});

test("local: status reads each line format, and only above ## Comments", () => {
  const root = repo({
    ".scratch/a/issues/01-plain.md": "# 01: Plain\n\nStatus: ready-for-agent\n",
    ".scratch/a/issues/02-bold.md": "# 02: Bold\n\n**Blocked by:** 01: Plain, 03\n\n**Status:** ready-for-agent\n",
    ".scratch/a/issues/03-bold-after.md": "# 03: Bold colon after\n\n**Status**: ready-for-agent\n**Assignee**: Grace Hopper\n",
    ".scratch/a/issues/04-mine.md": "# 04: Mine\n\nStatus: ready-for-agent\nAssignee: Ada Lovelace\nBlocked by: None (can start immediately)\n",
    ".scratch/a/issues/05-quoted.md": "# 05: Quoted\n\nStatus: needs-triage\n\n## Comments\n\nStatus: ready-for-agent\n",
    ".scratch/a/issues/06-across.md": "# 06: Across features\n\nstatus: ready-for-agent\nblocked by: b/1\n",
    ".scratch/b/issues/01-other.md": "# 01: Same number, other feature\n\nStatus: ready-for-agent\n",
  });
  assert.deepEqual(runMain(new Orca(root), "status"), {
    code: 0,
    out: [
      "ready queue (1)",
      "  a/04  Mine",
      "not eligible (5)",
      "  a/01  Plain  (unassigned: the tick takes it once assigned to Ada Lovelace)",
      "  a/02  Bold  (blocked by a/01, a/03)",
      "  a/03  Bold colon after  (assigned to Grace Hopper)",
      "  a/06  Across features  (blocked by b/01)",
      "  b/01  Same number, other feature  (unassigned: the tick takes it once assigned to Ada Lovelace)",
    ],
    err: [],
  });
});

test("local: start <feature>/N claims the ticket in one write, in the style of its lines, and names the worktree by both parts", () => {
  const root = repo({
    ".scratch/a/issues/01-one.md": "# 01: One\n\n**Status:** ready-for-agent\n\nBody.\n",
    ".scratch/b/issues/01-one.md": "# 01: Other one\n\nStatus: ready-for-agent\nAssignee: Ada Lovelace\n",
  });
  const orca = new Orca(root);
  assert.deepEqual(runMain(orca, "start", "a/1", "--run", RUN), {
    code: 0,
    out: ["started a/01 in worktree issue-a-01: claude sonnet @ medium (medium role), dispatch ctx_1"],
    err: [],
  });
  assert.deepEqual(runMain(orca, "start", "b/01", "--run", RUN), {
    code: 0,
    out: ["started b/01 in worktree issue-b-01: claude sonnet @ medium (medium role), dispatch ctx_2"],
    err: [],
  });
  assert.equal(read(root, ".scratch/a/issues/01-one.md"), "# 01: One\n\n**Status:** in-progress\n**Assignee:** Ada Lovelace\n\nBody.\n");
  assert.equal(read(root, ".scratch/b/issues/01-one.md"), "# 01: Other one\n\nStatus: in-progress\nAssignee: Ada Lovelace\n");
  assert.ok(orca.specs[0]?.startsWith('You are working on issue a/01: "One", in the orca worktree issue-a-01,'), orca.specs[0]);
  assert.deepEqual([...orca.worktrees.keys()], ["issue-a-01", "issue-b-01"]);

  // A message from each worker maps back to its own ticket by worktree name.
  orca.send("issue-b-01", "escalation", "Stuck.");
  assert.deepEqual(runMain(orca, ...TICK).out, ["b/01: in-progress -> needs-human (escalation); stopped ctx_2, commented"]);
  assert.match(read(root, ".scratch/a/issues/01-one.md"), /\*\*Status:\*\* in-progress/);
});

test("local: an id that names no ticket file is the usage, or an error naming the file it looked for", () => {
  const root = repo({ ".scratch/a/issues/01-one.md": "# 01: One\n\nStatus: ready-for-agent\n" });
  const orca = new Orca(root);
  for (const argv of [["start", "../a"], ["start", "a/01/x"], ["merge", "a/x"]]) {
    const result = runMain(orca, ...argv, "--run", RUN);
    assert.equal(result.code, 2, argv.join(" "));
    assert.match(result.err[0] ?? "", /^usage: /);
  }
  assert.deepEqual(runMain(orca, "start", "a/07", "--run", RUN).err, ["error: no ticket a/07: .scratch/a/issues has no 07-*.md"]);
  assert.deepEqual(runMain(orca, "start", "a", "--run", RUN).err, ["error: no ticket a: .scratch/a has no spec.md or map.md"]);
  assert.deepEqual(orca.calls, []);
});

test("local: comment appends under ## Comments, adding the heading once, and close resolves in the same write", () => {
  const root = repo({ ".scratch/a/issues/01-one.md": "# 01: One\n\nStatus: ready-for-human\n\nBody.\n\n\n" });
  const tracker = local(realSh, root, "main");
  tracker.comment("a/01", "First.");
  tracker.comment("a/1", "\nSecond,\nin two lines.\n");
  tracker.close("a/01", "Merged.");
  assert.equal(
    read(root, ".scratch/a/issues/01-one.md"),
    "# 01: One\n\nStatus: resolved\n\nBody.\n\n## Comments\n\nFirst.\n\nSecond,\nin two lines.\n\nMerged.\n",
  );
  assert.equal(tracker.view("a/01").open, false);
});

// A ticket in ready-for-human whose worktree issue-a-01 holds one commit on its branch.
function reviewed() {
  const root = repo({
    ".scratch/a/issues/01-one.md": "# 01: One\n\nStatus: ready-for-human\nAssignee: Ada Lovelace\n",
    "shared.txt": "base\n",
  });
  const orca = new Orca(root);
  const path = join(orca.dir, "issue-a-01");
  git(root, "worktree", "add", "-q", "-b", "ada/issue-a-01", path, "main");
  orca.worktrees.set("issue-a-01", path);
  return { root, orca, path };
}

function commit(at: string, file: string, text: string): void {
  write(at, { [file]: text });
  git(at, "add", file);
  git(at, "commit", "-q", "-m", `edit ${file}`);
}

test("local: merge squashes the branch into base in the main checkout, and commits with a Resolves trailer", () => {
  const { root, orca, path } = reviewed();
  commit(path, "one.txt", "one\n");
  commit(path, "two.txt", "two\n");
  // The loop's own state in the main checkout does not count as dirty.
  write(root, { ".scratch/a/issues/01-one.md": `${read(root, ".scratch/a/issues/01-one.md")}\n## Comments\n\nReview.\n`, ".orchestrator/run.json": "{}\n" });
  const before = git(root, "rev-parse", "HEAD").trim();
  assert.deepEqual(runMain(orca, "merge", "a/01", "--run", RUN), {
    code: 0,
    out: ["a/01: merged", "a/01: torn down; removed worktree issue-a-01, dropped ready-for-human, closed"],
    err: [],
  });
  assert.equal(git(root, "rev-parse", "HEAD~1").trim(), before, "one commit on main, not a merge of two");
  assert.equal(git(root, "log", "-1", "--format=%B"), "One (a/01)\n\nSquash of branch ada/issue-a-01.\n\nResolves: a/01\n\n");
  assert.deepEqual(git(root, "show", "--name-only", "--format=", "HEAD").trim().split("\n"), ["one.txt", "two.txt"]);
  assert.match(read(root, ".scratch/a/issues/01-one.md"), /^Status: resolved$/m);
  assert.equal(git(root, "branch", "--list", "ada/issue-a-01").trim(), "ada/issue-a-01", "the branch stays, as orca keeps a branch it cannot prove merged");
});

test("local: merge refuses unless the main checkout is clean and on base, and the branch is ahead and merges cleanly", () => {
  const cases: [string, (s: ReturnType<typeof reviewed>) => void][] = [
    ["has uncommitted changes", ({ root, path }) => {
      commit(path, "one.txt", "one\n");
      write(root, { "shared.txt": "edited\n" });
    }],
    ["has uncommitted changes", ({ root, path }) => {
      commit(path, "one.txt", "one\n");
      write(root, { "untracked.txt": "new\n" });
    }],
    ["is on side, not main", ({ root, path }) => {
      commit(path, "one.txt", "one\n");
      git(root, "checkout", "-q", "-b", "side");
    }],
    ["no commits ahead", () => {}],
    ["does not merge cleanly", ({ root, path }) => {
      commit(path, "shared.txt", "branch\n");
      commit(root, "shared.txt", "main\n");
    }],
  ];
  for (const [why, arrange] of cases) {
    const setup = reviewed();
    arrange(setup);
    const head = git(setup.root, "rev-parse", "HEAD");
    const ticket = read(setup.root, ".scratch/a/issues/01-one.md");
    const result = runMain(setup.orca, "merge", "a/01", "--run", RUN);
    assert.equal(result.code, 1, why);
    assert.ok(result.err[0]?.startsWith("a/01 is not merged: ") && result.err[0].includes(why), result.err[0]);
    assert.equal(git(setup.root, "rev-parse", "HEAD"), head, why);
    assert.equal(read(setup.root, ".scratch/a/issues/01-one.md"), ticket, why);
    assert.deepEqual([...setup.orca.worktrees.keys()], ["issue-a-01"], why);
  }
});

test("local: prFor is the branch while it is ahead, and the squash commit once the worktree is gone", () => {
  const { root, orca, path } = reviewed();
  const tracker = local(orca.sh, root, "main");
  assert.deepEqual(tracker.prFor("a/01"), { ref: "ada/issue-a-01", url: "ada/issue-a-01", open: false });
  assert.equal(tracker.pageUrl("a/01"), null);
  commit(path, "one.txt", "one\n");
  assert.equal(tracker.prFor("a/01")?.open, true);
  assert.equal(tracker.isMerged("a/01"), false);
  assert.equal(tracker.merge("a/01"), null);
  assert.equal(tracker.isMerged("a/01"), true);
  assert.equal(tracker.prFor("a/01")?.open, false);
  assert.match(tracker.merge("a/01") ?? "", /^a\/01 is already merged into main as [0-9a-f]+, so the next tick tears it down$/);
  git(root, "worktree", "remove", "--force", path);
  const squash = git(root, "log", "-1", "--format=%h").trim();
  assert.deepEqual(tracker.prFor("a/01"), { ref: squash, url: squash, open: false });
});
