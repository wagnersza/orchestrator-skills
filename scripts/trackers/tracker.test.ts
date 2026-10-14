// One suite for every tracker backend. A small in-memory tracker holds the issues, the
// PRs and the labels, and each backend's fake CLI serves it in that CLI's recorded JSON
// shapes: `gh api` REST and GraphQL for github, `glab api` REST and GraphQL for gitlab.
// Each contract test then runs once per backend, and asserts what the tracker holds
// after the call, not the command lines that got it there.

import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { main } from "../orchestrator.ts";
import type { Result, Sh } from "../sh.ts";
import { github } from "./github.ts";
import { gitlab } from "./gitlab.ts";
import { IN_PROGRESS, NEEDS_HUMAN, READY, READY_FOR_HUMAN, USER_STORY, type Tracker } from "./tracker.ts";

// An issue in the home project by number, or one elsewhere as `acme/infra#7`.
type Key = number | string;

type Seed = {
  n: number;
  project?: string;
  title?: string;
  open?: boolean;
  labels?: string[];
  assignees?: string[];
  body?: string;
  // Native links: the issues that block this one, and this one's child items.
  blockedBy?: Key[];
  children?: Key[];
  // A link GitLab lists beside the blockers, which is no blocker.
  relates?: Key[];
};

type PrSeed = {
  n: number;
  closes: number;
  state: "open" | "closed" | "merged";
  mergeable?: "yes" | "conflict" | "unknown";
  changesRequested?: boolean;
};

type State = Required<Omit<Seed, "project">> & { project?: string; comments: string[] };

const OTHER = "acme/infra";

// The tracker's own state, which both fake CLIs read and write.
class Server {
  me = "me";
  issues = new Map<string, State>();
  prs: PrSeed[];
  labels: string[];
  // Each command line that changed something, in order.
  writes: string[] = [];

  constructor(issues: Seed[], prs: PrSeed[] = [], labels: string[] = []) {
    for (const seed of issues) {
      const key = seed.project ? `${seed.project}#${seed.n}` : String(seed.n);
      this.issues.set(key, {
        title: `issue ${seed.n}`, open: true, labels: [], assignees: [], body: "", blockedBy: [], children: [], relates: [],
        ...seed, comments: [],
      });
    }
    this.prs = prs.map((pr) => ({ ...pr }));
    this.labels = [...labels];
  }

  issue(key: Key): State | undefined {
    return this.issues.get(String(key));
  }

  // The issue `key` names, which a test seeded.
  at(key: Key): State {
    const found = this.issue(key);
    if (!found) throw new Error(`no seeded issue ${key}`);
    return found;
  }

  home(): State[] {
    return [...this.issues.values()].filter((s) => !s.project);
  }

  // A merge closes the issue its PR names, as `Closes #N` does.
  merge(n: number): void {
    const pr = this.prs.find((p) => p.n === n);
    if (!pr) throw new Error(`no PR ${n}`);
    pr.state = "merged";
    this.at(pr.closes).open = false;
  }
}

type Fake = { sh: Sh; calls: string[] };

const ok = (stdout: unknown): Result => ({ code: 0, stdout: typeof stdout === "string" ? stdout : JSON.stringify(stdout), stderr: "" });
const missing = (line: string): Result => ({ code: 1, stdout: "", stderr: `unexpected call: ${line}` });

// Replies for the commands that are not the tracker's (orca, git), by exact line or by
// a prefix that ends in " *".
type Extra = Record<string, unknown>;

function fromExtra(extra: Extra, line: string): Result {
  const key = line in extra ? line : Object.keys(extra).find((k) => k.endsWith(" *") && line.startsWith(k.slice(0, -1)));
  if (key === undefined) return missing(line);
  const reply = extra[key];
  if (typeof reply === "object" && reply !== null && "fail" in reply) return (reply as { fail: Result }).fail;
  return ok(reply);
}

// --- github: `gh api`, as github.ts reads it

const GH_HOME = "https://api.github.com/repos/wagnersza/orchestrator-skills";

function ghIssue(server: Server, s: State) {
  const repo = s.project ? `https://api.github.com/repos/${s.project}` : GH_HOME;
  return {
    url: `${repo}/issues/${s.n}`,
    repository_url: repo,
    html_url: `${repo.replace("api.github.com/repos", "github.com")}/issues/${s.n}`,
    number: s.n,
    title: s.title,
    labels: s.labels.map((name) => ({ id: 11684709514, name, color: "1D76DB" })),
    state: s.open ? "open" : "closed",
    assignees: s.assignees.map((login) => ({ login })),
    issue_dependencies_summary: {
      blocked_by: s.blockedBy.filter((k) => server.issue(k)?.open).length,
      total_blocked_by: s.blockedBy.length,
      blocking: 0,
      total_blocking: 0,
    },
    sub_issues_summary: { total: s.children.length, completed: 0, percent_completed: 0 },
    body: s.body,
  };
}

function ghPr(pr: PrSeed) {
  return {
    number: pr.n,
    url: `https://github.com/wagnersza/orchestrator-skills/pull/${pr.n}`,
    state: pr.state.toUpperCase(),
    mergeable: { yes: "MERGEABLE", conflict: "CONFLICTING", unknown: "UNKNOWN" }[pr.mergeable ?? "unknown"],
    reviewDecision: pr.changesRequested ? "CHANGES_REQUESTED" : "APPROVED",
  };
}

function fakeGh(server: Server, extra: Extra = {}): Fake {
  const calls: string[] = [];
  const sh: Sh = (cmd, args, opts = {}) => {
    const line = [cmd, ...args].join(" ");
    calls.push(line);
    if (cmd !== "gh") return fromExtra(extra, line);
    const input = opts.input ? JSON.parse(opts.input) : undefined;
    const issuePath = /^repos\/(\{owner\}\/\{repo\}|[^/]+\/[^/]+)\/issues\/(\d+)$/;
    const keyOf = (repo: string, n: string) => (repo === "{owner}/{repo}" ? n : `${repo}#${n}`);
    const reply = (value: unknown) => ok(value);
    if (line === "gh api user --jq .login") return reply(`${server.me}\n`);
    let m: RegExpMatchArray | null;
    if ((m = line.match(/^gh api --paginate --slurp repos\/\{owner\}\/\{repo\}\/issues\?state=(open|all)(?:&labels=([^&]+))?&per_page=100$/))) {
      const label = m[2] && decodeURIComponent(m[2]);
      return reply([server.home()
        .filter((s) => (m?.[1] === "all" || s.open) && (!label || s.labels.includes(label)))
        .map((s) => ghIssue(server, s))]);
    }
    if ((m = line.match(/^gh api --paginate --slurp (repos\/.+)\/(dependencies\/blocked_by|sub_issues)\?per_page=100$/))) {
      const [, repo = "", n = ""] = (m[1] ?? "").match(issuePath) ?? [];
      const s = server.at(keyOf(repo, n));
      const keys = m[2] === "sub_issues" ? s.children : s.blockedBy;
      return reply([keys.map((k) => ghIssue(server, server.at(k)))]);
    }
    if ((m = line.match(/^gh api (repos\/\S+)$/)) && issuePath.test(m[1] ?? "")) {
      const [, repo = "", n = ""] = (m[1] ?? "").match(issuePath) ?? [];
      const s = server.issue(keyOf(repo, n));
      return s ? reply(ghIssue(server, s)) : missing(line);
    }
    if ((m = line.match(/^gh api -X PATCH (repos\/\S+) --input -$/))) {
      const [, repo = "", n = ""] = (m[1] ?? "").match(issuePath) ?? [];
      const s = server.at(keyOf(repo, n));
      server.writes.push(line);
      if (input.labels) s.labels = input.labels;
      if (input.assignees) s.assignees = input.assignees;
      if (input.state === "closed") s.open = false;
      return reply(ghIssue(server, s));
    }
    if ((m = line.match(/^gh api -X POST (repos\/\S+)\/comments --input -$/))) {
      const [, repo = "", n = ""] = (m[1] ?? "").match(issuePath) ?? [];
      server.writes.push(line);
      server.at(keyOf(repo, n)).comments.push(input.body);
      return reply({ id: 1, body: input.body });
    }
    if ((m = line.match(/^gh api graphql -f query=.+ -F owner=\{owner\} -F repo=\{repo\} -F number=(\d+)$/))) {
      const nodes = server.prs.filter((pr) => pr.closes === Number(m?.[1])).map(ghPr);
      return reply({ data: { repository: { issue: { closedByPullRequestsReferences: { nodes } } } } });
    }
    if ((m = line.match(/^gh pr merge (\d+) -R wagnersza\/orchestrator-skills --squash --delete-branch$/))) {
      server.writes.push(line);
      server.merge(Number(m[1]));
      return reply("");
    }
    if (line === "gh api --paginate --slurp repos/{owner}/{repo}/labels?per_page=100") {
      return reply([server.labels.map((name) => ({ name, color: "ededed" }))]);
    }
    if (line === "gh api -X POST repos/{owner}/{repo}/labels --input -") {
      server.writes.push(line);
      server.labels.push(input.name);
      return reply({ id: 1, ...input });
    }
    return missing(line);
  };
  return { sh, calls };
}

// --- gitlab: `glab api`, in the shapes GitLab's REST and GraphQL docs record

const GL_HOST = "https://gitlab.example.com";
const GL_HOME = "group/project";
const PROJECT_IDS: Record<string, number> = { [GL_HOME]: 3, [OTHER]: 9 };

// `GET /projects/:id`, trimmed to the fields beside the ones the backend reads.
const GL_PROJECT = {
  id: 3,
  description: "",
  name: "project",
  name_with_namespace: "group / project",
  path: "project",
  path_with_namespace: GL_HOME,
  default_branch: "main",
  web_url: `${GL_HOST}/${GL_HOME}`,
};

// The user record `GET /user` and an issue's `assignees` share.
function glUser(username: string) {
  const id = username === "me" ? 1 : 100 + username.length;
  return { id, username, name: username, state: "active", avatar_url: null, web_url: `${GL_HOST}/${username}` };
}

const USERS = new Map<number, string>();

// `GET /projects/:id/issues/:iid` as GitLab's docs record it, trimmed.
function glIssue(s: State) {
  const project = s.project ?? GL_HOME;
  const assignees = s.assignees.map(glUser);
  for (const a of assignees) USERS.set(a.id, a.username);
  return {
    id: 1000 + s.n,
    iid: s.n,
    project_id: PROJECT_IDS[project],
    title: s.title,
    description: s.body,
    state: s.open ? "opened" : "closed",
    created_at: "2026-10-01T09:00:00.000Z",
    updated_at: "2026-10-02T09:00:00.000Z",
    closed_at: s.open ? null : "2026-10-03T09:00:00.000Z",
    labels: s.labels,
    milestone: null,
    assignees,
    assignee: assignees[0] ?? null,
    author: glUser("alice"),
    type: "ISSUE",
    issue_type: "issue",
    user_notes_count: s.comments.length,
    merge_requests_count: 0,
    confidential: false,
    discussion_locked: null,
    web_url: `${GL_HOST}/${project}/-/issues/${s.n}`,
    references: { short: `#${s.n}`, relative: `#${s.n}`, full: `${project}#${s.n}` },
    task_completion_status: { count: 0, completed_count: 0 },
    blocking_issues_count: 0,
    has_tasks: false,
  };
}

// `GET /projects/:id/issues/:iid/closed_by`, the MergeRequestBasic shape, trimmed.
function glMr(pr: PrSeed) {
  const status = pr.changesRequested ? "requested_changes" : { yes: "mergeable", conflict: "conflict", unknown: "unchecked" }[pr.mergeable ?? "unknown"];
  return {
    id: 5000 + pr.n,
    iid: pr.n,
    project_id: 3,
    title: `Resolve issue ${pr.closes}`,
    description: `Closes #${pr.closes}`,
    state: pr.state === "open" ? "opened" : pr.state,
    target_branch: "main",
    source_branch: `issue-${pr.closes}`,
    draft: false,
    merge_status: status === "mergeable" ? "can_be_merged" : "cannot_be_merged",
    detailed_merge_status: status,
    has_conflicts: pr.mergeable === "conflict",
    squash: false,
    web_url: `${GL_HOST}/${GL_HOME}/-/merge_requests/${pr.n}`,
    references: { short: `!${pr.n}`, relative: `!${pr.n}`, full: `${GL_HOME}!${pr.n}` },
  };
}

// One page of `rows`, the way `per_page` and `page` cut it.
function page<T>(rows: T[], query: URLSearchParams): T[] {
  const size = Number(query.get("per_page") ?? 20);
  const at = Number(query.get("page") ?? 1);
  return rows.slice((at - 1) * size, at * size);
}

function fakeGlab(server: Server, extra: Extra = {}): Fake {
  const calls: string[] = [];
  const sh: Sh = (cmd, args, opts = {}) => {
    const line = [cmd, ...args].join(" ");
    calls.push(line);
    if (cmd !== "glab") return fromExtra(extra, line);
    const input = opts.input ? JSON.parse(opts.input) : undefined;
    const reply = (value: unknown) => ok(value);
    if (args[0] === "mr" && args[1] === "merge") {
      if (args.slice(3).join(" ") !== `-R ${GL_HOST}/${GL_HOME} --squash --remove-source-branch --yes`) return missing(line);
      server.writes.push(line);
      server.merge(Number(args[2]));
      return reply(`✓ Merged!\n${GL_HOST}/${GL_HOME}/-/merge_requests/${args[2]}\n`);
    }
    if (args[0] !== "api") return missing(line);
    if (args[1] === "graphql") {
      const field = (name: string) => args.find((a) => a.startsWith(`${name}=`))?.slice(name.length + 1) ?? "";
      const s = server.issue(field("path") === GL_HOME ? field("iid") : `${field("path")}#${field("iid")}`);
      if (!s) return reply({ data: { project: { workItems: { nodes: [] } } } });
      const nodes = s.children.map((k) => {
        const child = server.at(k);
        return { iid: String(child.n), webUrl: `${GL_HOST}/${child.project ?? GL_HOME}/-/work_items/${child.n}` };
      });
      // A fragment on another widget type answers an empty object.
      return reply({ data: { project: { workItems: { nodes: [{ widgets: [{}, { children: { nodes } }, {}] }] } } } });
    }
    const method = args[1] === "-X" ? args[2] : "GET";
    const target = method === "GET" ? args[1] : args[3];
    if (method !== "GET" && args.slice(4).join(" ") !== "-H Content-Type: application/json --input -") return missing(line);
    const [path = "", search = ""] = (target ?? "").split("?");
    const query = new URLSearchParams(search);
    if (path === "user") return reply(glUser(server.me));
    if (path === "projects/:fullpath") return reply(GL_PROJECT);
    const m = path.match(/^projects\/(:fullpath|[^/]+)\/(?:issues\/(\d+)(?:\/(\w+))?|(issues|labels))$/);
    if (!m) return missing(line);
    const project = m[1] === ":fullpath" ? GL_HOME : decodeURIComponent(m[1] ?? "");
    const key = project === GL_HOME ? (m[2] ?? "") : `${project}#${m[2]}`;
    if (m[4] === "issues" && method === "GET") {
      const labels = (query.get("labels") ?? "").split(",").filter(Boolean);
      const rows = server.home()
        .filter((s) => query.get("state") === "all" || (query.get("state") === "opened") === s.open)
        .filter((s) => labels.every((l) => s.labels.includes(l)))
        .sort((a, b) => b.n - a.n)
        .map(glIssue);
      return reply(page(rows, query));
    }
    if (m[4] === "labels" && method === "GET") {
      return reply(page(server.labels.map((name, i) => ({ id: i + 1, name, color: "#ededed", description: null })), query));
    }
    if (m[4] === "labels" && method === "POST") {
      server.writes.push(line);
      server.labels.push(input.name);
      return reply({ id: 99, ...input });
    }
    const s = server.issue(key);
    if (!s) return reply404(line);
    if (m[3] === undefined && method === "GET") return reply(glIssue(s));
    if (m[3] === undefined && method === "PUT") {
      server.writes.push(line);
      const add = String(input.add_labels ?? "").split(",").filter(Boolean);
      const remove = String(input.remove_labels ?? "").split(",").filter(Boolean);
      s.labels = [...new Set([...s.labels.filter((l) => !remove.includes(l)), ...add])];
      if (input.assignee_ids) s.assignees = (input.assignee_ids as number[]).map((id) => (id === 1 ? server.me : USERS.get(id) ?? `user${id}`));
      if (input.state_event === "close") s.open = false;
      return reply(glIssue(s));
    }
    if (m[3] === "notes" && method === "POST") {
      server.writes.push(line);
      s.comments.push(input.body);
      return reply({ id: 7, body: input.body, system: false, noteable_type: "Issue", noteable_iid: s.n, author: glUser(server.me) });
    }
    if (m[3] === "links" && method === "GET") {
      const link = (k: Key, type: string) => ({
        ...glIssue(server.at(k)), issue_link_id: 40 + Number(String(k).split("#").pop()), link_type: type,
        link_created_at: "2026-10-01T09:00:00.000Z", link_updated_at: "2026-10-01T09:00:00.000Z",
      });
      return reply([...s.relates.map((k) => link(k, "relates_to")), ...s.blockedBy.map((k) => link(k, "is_blocked_by"))]);
    }
    if (m[3] === "closed_by" && method === "GET") {
      return reply(page(server.prs.filter((pr) => pr.closes === s.n && !s.project).map(glMr), query));
    }
    return missing(line);
  };
  return { sh, calls };
}

function reply404(line: string): Result {
  return { code: 1, stdout: "", stderr: `glab: 404 Not Found (HTTP 404)\n${line}` };
}

// --- the backends the contract runs against

type Backend = {
  name: string;
  make: (sh: Sh, cwd: string) => Tracker;
  fake: (server: Server, extra?: Extra) => Fake;
  // How the backend names a PR in a line it prints: "#12" or "!12", "PR" or "MR".
  pr: (n: number) => string;
  word: string;
  status: { conflict: string; unknown: string };
};

const BACKENDS: Backend[] = [
  {
    name: "github",
    make: github,
    fake: fakeGh,
    pr: (n) => `#${n}`,
    word: "PR",
    status: { conflict: "conflicting", unknown: "unknown" },
  },
  {
    name: "gitlab",
    make: gitlab,
    fake: fakeGlab,
    pr: (n) => `!${n}`,
    word: "MR",
    status: { conflict: "conflict", unknown: "unchecked" },
  },
];

function setup(backend: Backend, issues: Seed[], prs: PrSeed[] = [], labels: string[] = []) {
  const server = new Server(issues, prs, labels);
  const fake = backend.fake(server);
  return { server, calls: fake.calls, tracker: backend.make(fake.sh, "/repo") };
}

// The parent-line body of a child of `p`, in the form docs/agents/issue-tracker.md names.
const partOf = (p: number, rest = "") => `## Parent\n\n#${p}\n\n${rest}`;

for (const backend of BACKENDS) {
  const it = (name: string, body: () => void) => test(`${backend.name}: ${name}`, body);

  it("list returns the open issues with the label, by number, and a closed one only when asked", () => {
    const { tracker } = setup(backend, [
      { n: 12, title: "second", labels: [READY, "docs"], assignees: ["alice"], body: "Body text." },
      { n: 10, title: "first", labels: [READY] },
      { n: 11, labels: ["needs-triage"] },
      { n: 13, labels: [READY], open: false },
    ]);
    assert.deepEqual(tracker.list({ label: READY }), [
      { id: "10", title: "first", open: true, labels: [READY], assignees: [], body: "" },
      { id: "12", title: "second", open: true, labels: [READY, "docs"], assignees: ["alice"], body: "Body text." },
    ]);
    assert.deepEqual(tracker.list({ label: READY, closed: true }).map((i) => [i.id, i.open]), [["10", true], ["12", true], ["13", false]]);
  });

  it("list reads every page", () => {
    const { tracker } = setup(backend, Array.from({ length: 230 }, (_, i) => ({ n: i + 1, labels: [READY] })));
    const ids = tracker.list({ label: READY }).map((i) => i.id);
    assert.equal(ids.length, 230);
    assert.equal(ids[229], "230");
  });

  it("view and me read the issue and the login", () => {
    const { tracker } = setup(backend, [{ n: 10, title: "The thing", labels: ["docs"], assignees: ["me"], body: "## What\n" }]);
    assert.deepEqual(tracker.view("10"), { id: "10", title: "The thing", open: true, labels: ["docs"], assignees: ["me"], body: "## What\n" });
    assert.equal(tracker.me(), "me");
  });

  it("blockers reads the native links and the Blocked by line, once each, and names another project's issue by its path", () => {
    const { tracker, calls } = setup(backend, [
      { n: 10, blockedBy: [20, `${OTHER}#7`], relates: [30], body: "## Notes\n\nBlocked by: #20, #21\n" },
      { n: 20 },
      { n: 21 },
      { n: 30 },
      { n: 7, project: OTHER, open: false },
    ]);
    assert.deepEqual(tracker.blockers("10"), ["20", `${OTHER}#7`, "21"]);
    assert.equal(tracker.ref(`${OTHER}#7`), `${OTHER}#7`);
    const before = calls.length;
    assert.equal(tracker.view("20").open, true);
    assert.equal(tracker.view(`${OTHER}#7`).open, false);
    assert.equal(calls.length, before, "a blocker the links read is not read again");
  });

  it("claim swaps ready-for-agent for in-progress and assigns me, in one write", () => {
    const { tracker, server } = setup(backend, [
      { n: 10, labels: [READY, "docs"] },
      { n: 11, labels: [READY], assignees: ["me"] },
      { n: 12, labels: [READY], assignees: ["alice"] },
    ]);
    for (const id of ["10", "11", "12"]) tracker.claim(id);
    assert.equal(server.writes.length, 3);
    assert.deepEqual([server.at(10).labels.sort(), server.at(10).assignees], [["docs", IN_PROGRESS], ["me"]]);
    assert.deepEqual([server.at(11).labels, server.at(11).assignees], [[IN_PROGRESS], ["me"]]);
    assert.deepEqual(server.at(12).assignees, ["alice", "me"]);
  });

  it("unclaim undoes a claim in one write, and keeps another assignee", () => {
    const { tracker, server } = setup(backend, [{ n: 10, labels: [READY, "docs"], assignees: ["alice"] }]);
    tracker.claim("10");
    tracker.unclaim("10");
    assert.equal(server.writes.length, 2);
    assert.deepEqual([server.at(10).labels.sort(), server.at(10).assignees], [["docs", READY], ["alice"]]);
  });

  it("setState swaps one state label in one write, and writes nothing where the issue already holds it", () => {
    const { tracker, server } = setup(backend, [
      { n: 10, labels: [IN_PROGRESS, "docs"], assignees: ["me"] },
      { n: 11, labels: [READY_FOR_HUMAN], assignees: ["me"] },
    ]);
    tracker.setState("10", IN_PROGRESS, NEEDS_HUMAN);
    tracker.setState("11", IN_PROGRESS, READY_FOR_HUMAN);
    assert.equal(server.writes.length, 1);
    assert.deepEqual([server.at(10).labels.sort(), server.at(10).assignees], [["docs", NEEDS_HUMAN], ["me"]]);
    assert.deepEqual(server.at(11).labels, [READY_FOR_HUMAN]);
  });

  it("comment posts the body as it is", () => {
    const { tracker, server } = setup(backend, [{ n: 10 }]);
    tracker.comment("10", "The worker asked:\n\n> Keep it?");
    assert.deepEqual(server.at(10).comments, ["The worker asked:\n\n> Keep it?"]);
  });

  it("isParent holds for the label, for native children and for a parent line, and not for a leaf", () => {
    const { tracker } = setup(backend, [
      { n: 30, labels: [USER_STORY] },
      { n: 31, children: [41] },
      { n: 32 },
      { n: 33 },
      { n: 41 },
      { n: 42, body: partOf(32) },
    ]);
    assert.deepEqual(["30", "31", "32", "33", "41"].map((id) => tracker.isParent(id)), [true, true, true, false, false]);
  });

  it("children joins the native children and the parent lines, once each, open or closed", () => {
    const { tracker } = setup(backend, [
      { n: 40, children: [41, `${OTHER}#7`, 43] },
      { n: 41, open: false },
      { n: 7, project: OTHER },
      { n: 43, body: partOf(40) },
      { n: 44, body: partOf(40), open: false },
      { n: 45, body: partOf(39) },
    ]);
    assert.deepEqual(tracker.children("40"), ["41", `${OTHER}#7`, "43", "44"]);
  });

  it("close posts the body first, then closes and drops every state label", () => {
    const { tracker, server } = setup(backend, [{ n: 40, labels: [IN_PROGRESS, USER_STORY, "docs"], assignees: ["me"] }]);
    tracker.close("40", "Every child is closed.");
    assert.deepEqual(server.at(40).comments, ["Every child is closed."]);
    assert.deepEqual([server.at(40).open, server.at(40).labels], [false, [USER_STORY, "docs"]]);
    assert.equal(server.writes.length, 2);
    assert.match(server.writes[0] ?? "", /comments|notes/);
  });

  it("prFor prefers the open PR, else the newest closed or merged one, else none", () => {
    const { tracker } = setup(backend, [{ n: 10 }, { n: 11 }, { n: 12 }], [
      { n: 20, closes: 10, state: "open" },
      { n: 21, closes: 10, state: "closed" },
      { n: 22, closes: 11, state: "closed" },
      { n: 23, closes: 11, state: "merged" },
    ]);
    const open = tracker.prFor("10");
    assert.deepEqual([open?.ref, open?.open], [backend.pr(20), true]);
    assert.match(open?.url ?? "", /\/(pull|merge_requests)\/20$/);
    assert.deepEqual([tracker.prFor("11")?.ref, tracker.prFor("11")?.open], [backend.pr(23), false]);
    assert.equal(tracker.prFor("12"), null);
  });

  it("isMerged holds once a PR that closes the issue is merged, read fresh each time", () => {
    const { tracker, server } = setup(backend, [{ n: 10 }], [{ n: 20, closes: 10, state: "open" }]);
    assert.equal(tracker.isMerged("10"), false);
    server.merge(20);
    assert.equal(tracker.isMerged("10"), true);
  });

  it("merge refuses in one line, and writes nothing, unless the open PR is mergeable with no changes requested", () => {
    const pr = backend.pr(20);
    const cases: [PrSeed[], string][] = [
      [[], `no open ${backend.word} closes #10`],
      [[{ n: 20, closes: 10, state: "closed" }], `no open ${backend.word} closes #10`],
      [[{ n: 20, closes: 10, state: "merged" }], `${backend.word} ${pr} is already merged, so the next tick tears it down`],
      [[{ n: 20, closes: 10, state: "open", mergeable: "conflict" }], `${backend.word} ${pr} is not mergeable (${backend.status.conflict})`],
      [[{ n: 20, closes: 10, state: "open" }], `${backend.word} ${pr} is not mergeable (${backend.status.unknown})`],
      [[{ n: 20, closes: 10, state: "open", mergeable: "yes", changesRequested: true }], `${backend.word} ${pr} has changes requested`],
    ];
    for (const [prs, why] of cases) {
      const { tracker, server } = setup(backend, [{ n: 10, labels: [READY_FOR_HUMAN] }], prs);
      assert.equal(tracker.merge("10"), why);
      assert.deepEqual(server.writes, [], why);
    }
  });

  it("merge squashes the open PR in one command, not a newer closed one", () => {
    const { tracker, server } = setup(backend, [{ n: 10, labels: [READY_FOR_HUMAN] }], [
      { n: 20, closes: 10, state: "open", mergeable: "yes" },
      { n: 21, closes: 10, state: "closed", mergeable: "conflict" },
    ]);
    assert.equal(tracker.merge("10"), null);
    assert.equal(server.writes.length, 1);
    assert.match(server.writes[0] ?? "", / merge 20 .*--squash/);
    assert.equal(tracker.isMerged("10"), true);
  });

  it("ensureLabels creates only the labels the project lacks, by name without case", () => {
    const { tracker, server } = setup(backend, [], [], ["bug", "Ready-For-Agent"]);
    const created = tracker.ensureLabels([
      { name: READY, color: "0E8A16", description: "Ready" },
      { name: IN_PROGRESS, color: "FBCA04", description: "Claimed" },
      { name: "heavy", color: "5319E7", description: "Heavy" },
    ]);
    assert.deepEqual(created, [IN_PROGRESS, "heavy"]);
    assert.deepEqual(server.labels, ["bug", "Ready-For-Agent", IN_PROGRESS, "heavy"]);
  });

  it("an issue goes through every state: claimed, needs-human, resumed, ready-for-human, merged, closed", () => {
    const { tracker, server } = setup(backend, [{ n: 10, labels: [READY, "docs"] }], [{ n: 20, closes: 10, state: "open", mergeable: "yes" }]);
    const state = () => server.at(10).labels.filter((l) => l !== "docs");
    tracker.claim("10");
    assert.deepEqual(state(), [IN_PROGRESS]);
    tracker.setState("10", IN_PROGRESS, NEEDS_HUMAN);
    assert.deepEqual(state(), [NEEDS_HUMAN]);
    // The human answers and relabels the issue, as the needs-human comment asks.
    tracker.setState("10", NEEDS_HUMAN, READY);
    tracker.claim("10");
    assert.deepEqual([state(), server.at(10).assignees], [[IN_PROGRESS], ["me"]]);
    tracker.setState("10", IN_PROGRESS, READY_FOR_HUMAN);
    assert.deepEqual(state(), [READY_FOR_HUMAN]);
    assert.equal(tracker.merge("10"), null);
    assert.equal(tracker.isMerged("10"), true);
    tracker.close("10", "Merged, so torn down.");
    assert.deepEqual([server.at(10).open, server.at(10).labels], [false, ["docs"]]);
  });
}

// --- gitlab only: the parts of the backend the shared contract does not reach

function gitlabSetup(issues: Seed[], prs: PrSeed[] = []) {
  const server = new Server(issues, prs);
  const fake = fakeGlab(server);
  return { server, calls: fake.calls, tracker: gitlab(fake.sh, "/repo") };
}

test("gitlab: a Part of line is a parent link too", () => {
  const { tracker } = gitlabSetup([{ n: 40 }, { n: 41, body: "Part of #40\n\n## What to build\n" }]);
  assert.equal(tracker.isParent("40"), true);
  assert.deepEqual(tracker.children("40"), ["41"]);
});

test("gitlab: a claim sends one PUT with the label change and the assignee ids", () => {
  const server = new Server([{ n: 10, labels: [READY], assignees: ["alice"] }]);
  const inputs: unknown[] = [];
  const fake = fakeGlab(server);
  const sh: Sh = (cmd, args, opts) => {
    if (args[1] === "-X") inputs.push([args.slice(0, 4).join(" "), JSON.parse(opts?.input ?? "")]);
    return fake.sh(cmd, args, opts);
  };
  gitlab(sh, "/repo").claim("10");
  assert.deepEqual(inputs, [
    ["api -X PUT projects/:fullpath/issues/10", { add_labels: IN_PROGRESS, remove_labels: READY, assignee_ids: [glUser("alice").id, 1] }],
  ]);
});

test("gitlab: a label is created with GitLab's # colour", () => {
  const server = new Server([]);
  const inputs: unknown[] = [];
  const fake = fakeGlab(server);
  const sh: Sh = (cmd, args, opts) => {
    if (args[1] === "-X") inputs.push(JSON.parse(opts?.input ?? ""));
    return fake.sh(cmd, args, opts);
  };
  gitlab(sh, "/repo").ensureLabels([{ name: READY, color: "0E8A16", description: "Ready" }]);
  assert.deepEqual(inputs, [{ name: READY, color: "#0E8A16", description: "Ready" }]);
});

test("gitlab: a GraphQL error is an error, not a parent with no children", () => {
  const sh: Sh = (_cmd, args) => {
    if (args[1] === "projects/:fullpath") return ok(GL_PROJECT);
    if (args[1] === "projects/:fullpath/issues/40") return ok(glIssue({ ...new Server([{ n: 40 }]).at(40) }));
    if (args[1]?.startsWith("projects/:fullpath/issues?")) return ok([]);
    return ok({ errors: [{ message: "Field 'workItems' doesn't exist on type 'Project'" }] });
  };
  assert.throws(() => gitlab(sh, "/repo").isParent("40"), /^Error: glab api graphql failed: Field 'workItems' doesn't exist on type 'Project'$/);
});

test("gitlab: a failed glab call throws with glab's own message", () => {
  const { tracker } = gitlabSetup([]);
  assert.throws(() => tracker.view("99"), /^Error: glab api projects\/:fullpath\/issues\/99 failed: glab: 404 Not Found/);
});

test("gitlab: the worker reads an issue in another project with -R", () => {
  const { tracker } = gitlabSetup([]);
  assert.equal(tracker.viewCommand("10"), "glab issue view 10 --comments");
  assert.equal(tracker.viewCommand(`${OTHER}#7`), `glab issue view 7 -R ${OTHER} --comments`);
});

// --- gitlab through the entry point: `tracker: gitlab` in config runs the loop on glab

const RUN = "run_1";
const COORDINATOR = "term_4f0ec745";
const ORCA = (...args: string[]) => `orca orchestration ${args.join(" ")} --json`;
const receipt = (result: unknown) => ({ id: "3da4edb0", ok: true, result });

function gitlabRepo(): string {
  const root = mkdtempSync(join(tmpdir(), "orch-"));
  mkdirSync(join(root, "docs", "agents"), { recursive: true });
  writeFileSync(join(root, "docs", "agents", "orchestrator.md"), '```json\n{ "tracker": "gitlab" }\n```\n');
  return root;
}

function runMain(argv: string[], server: Server, extra: Extra = {}) {
  const fake = fakeGlab(server, extra);
  const out: string[] = [];
  const err: string[] = [];
  const code = main(argv, { sh: fake.sh, cwd: gitlabRepo(), out: (l) => out.push(l), err: (l) => err.push(l) });
  return { code, out, err, calls: fake.calls };
}

test("gitlab: tracker gitlab in config reads the ready queue through glab", () => {
  const result = runMain(["status"], new Server([
    { n: 10, title: "unassigned", labels: [READY] },
    { n: 11, title: "blocked", labels: [READY], blockedBy: [20] },
    { n: 20 },
  ]));
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 0);
  assert.deepEqual(result.out, [
    "ready queue (0)",
    "not eligible (2)",
    "  #10  unassigned  (unassigned: the tick takes it once assigned to me)",
    "  #11  blocked  (blocked by #20)",
  ]);
  assert.ok(result.calls.every((line) => line.startsWith("glab ")));
});

test("gitlab: start claims the issue and renders the merge request step", () => {
  const server = new Server([{ n: 10, title: "Add the thing", labels: [READY] }]);
  const result = runMain(["start", "10", "--run", RUN], server, {
    "git rev-parse --path-format=absolute --git-common-dir": "/repo/.git\n",
    [ORCA("run-show", "--id", RUN)]: receipt({ run: { id: RUN, coordinator_handle: COORDINATOR } }),
    "orca worktree show *": { fail: { code: 1, stdout: JSON.stringify({ error: { code: "selector_not_found" } }), stderr: "" } },
    "orca orchestration worker-start *": receipt({ dispatchId: "ctx_1" }),
  });
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 0);
  assert.deepEqual(result.out, ["started #10 in worktree issue-10: claude sonnet @ medium (medium role), dispatch ctx_1"]);
  assert.deepEqual([server.at(10).labels, server.at(10).assignees], [[IN_PROGRESS], ["me"]]);
  const start = result.calls.find((line) => line.startsWith("orca orchestration worker-start")) ?? "";
  assert.ok(start.includes([
    'You are working on issue #10: "Add the thing", in the orca worktree issue-10, on the branch it checked out.',
    "",
    "1. Read the issue and every comment: glab issue view 10 --comments",
    "2. Run /implement on it.",
    "3. Commit in slices: one logical change per commit, Conventional Commits.",
    '4. Push, and open a merge request (not a draft) against main. Write its description with /pr, and put "Closes #10" in it.',
    "5. Never change the issue's state or labels, and never merge.",
  ].join("\n")), start);
});

// The orca replies a merge and a teardown of issue 10 need, with no worker left.
const TEARDOWN = {
  [ORCA("task-list", "--run", RUN)]: receipt({ tasks: [] }),
  [ORCA("worker-list", "--run", RUN)]: receipt({ workers: [], page: { nextCursor: null } }),
  "orca worktree show --worktree name:issue-10 --json": receipt({ worktree: { path: "/wt/issue-10" } }),
  "git status --porcelain": "",
  "orca worktree rm --worktree name:issue-10 --json": receipt({ removed: true }),
};

test("gitlab: merge N squashes the MR with glab, confirms it, then tears down", () => {
  const server = new Server([{ n: 10, labels: [READY_FOR_HUMAN, "docs"], assignees: ["me"] }], [
    { n: 3, closes: 10, state: "open", mergeable: "yes" },
  ]);
  const result = runMain(["merge", "10", "--run", RUN], server, TEARDOWN);
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 0);
  assert.deepEqual(result.out, ["#10: merged", "#10: torn down; removed worktree issue-10, dropped ready-for-human, closed"]);
  assert.ok(server.writes.includes(`glab mr merge 3 -R ${GL_HOST}/${GL_HOME} --squash --remove-source-branch --yes`));
  assert.deepEqual([server.at(10).open, server.at(10).labels], [false, ["docs"]]);
});

test("gitlab: the tick tears down an issue whose MR was merged on GitLab", () => {
  const server = new Server([{ n: 10, labels: [READY_FOR_HUMAN], assignees: ["me"], open: false }], [{ n: 3, closes: 10, state: "merged" }]);
  const result = runMain(["tick", "--run", RUN], server, {
    ...TEARDOWN,
    [ORCA("run-show", "--id", RUN)]: receipt({ run: { id: RUN, coordinator_handle: COORDINATOR } }),
    [ORCA("check", "--run", RUN, "--terminal", COORDINATOR)]: receipt({ deliveryId: null, messages: [] }),
  });
  assert.deepEqual(result.err, []);
  assert.equal(result.code, 1);
  assert.deepEqual(result.out, ["#10: torn down; removed worktree issue-10, dropped ready-for-human, closed"]);
  assert.deepEqual(server.at(10).labels, []);
  assert.deepEqual(server.at(10).comments, ["The PR is merged, so this issue is torn down: removed worktree issue-10, dropped ready-for-human, closed."]);
});
