// The local markdown backend, on mattpocock's `.scratch/` convention, with no hosted
// tracker. A feature is a directory, `.scratch/<feature>/`. Its spec.md or map.md is the
// parent, with the id `<feature>`, and each `issues/NN-<slug>.md` is a child, with the id
// `<feature>/NN`. Lines near the top of a file hold its fields: `Status:` is the state,
// `Assignee:` the claim, and `Blocked by: NN, NN` the blockers. Each line may be bold, as
// `**Status:** ready-for-agent`. Comments append under `## Comments`.
//
// The files live in the main checkout, whichever worktree the script runs in. The branch
// of worktree issue-<feature>-NN is the review surface, and a merge squashes it into base
// in the main checkout. The squash commit carries a `Resolves: <feature>/NN` trailer,
// which is how a later read finds the merge.

import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import type { Sh } from "../sh.ts";
import { IN_PROGRESS, READY, worktreeName, type Filter, type Id, type Issue, type Label, type Pr, type Tracker } from "./tracker.ts";

// The Status of a done ticket, in mattpocock's word.
export const RESOLVED = "resolved";

// The trailer of the squash commit, followed by the id it merged.
const TRAILER = "Resolves";

// The files a parent can be, in the order they are tried.
const PARENT_FILES = ["spec.md", "map.md"];

// A child file, `NN-<slug>.md`.
const CHILD_FILE = /^(\d+)-.*\.md$/;

// A feature directory name. It never starts with a dot, so `..` names no feature.
const FEATURE = /^[A-Za-z0-9_][\w.-]*$/;

// The heading the comments append under. Fields are read only above it.
const COMMENTS = /^##[ \t]+Comments[ \t]*$/m;

// The loop's own state in the main checkout, which the merge's clean check skips.
const OWN_STATE = [".scratch", ".orchestrator"];

// The first `name:` line, plain or bold. Group 1 is everything up to the value, and
// group 2 is the value.
function fieldLine(name: string): RegExp {
  return new RegExp(`^([ \\t]*(?:\\*\\*)?${name}(?::\\*\\*|\\*\\*:|:)[ \\t]*)(.*?)[ \\t]*$`, "im");
}

// The part of a file above `## Comments`.
function headOf(text: string): string {
  const at = text.search(COMMENTS);
  return at === -1 ? text : text.slice(0, at);
}

function field(text: string, name: string): string | undefined {
  return fieldLine(name).exec(headOf(text))?.[2];
}

// `text` with field `name` set to `value`, or with its line dropped where `value` is "".
// A new line goes under the Status line, in its style, else under the title.
function setField(text: string, name: string, value: string): string {
  const head = headOf(text);
  const rest = text.slice(head.length);
  const found = fieldLine(name).exec(head);
  if (found) {
    const start = found.index;
    const end = start + found[0].length;
    if (value === "") return head.slice(0, start) + head.slice(end + (head[end] === "\n" ? 1 : 0)) + rest;
    const lead = found[1] ?? "";
    return head.slice(0, start) + lead + (/\s$/.test(lead) ? "" : " ") + value + head.slice(end) + rest;
  }
  if (value === "") return text;
  const status = fieldLine("Status").exec(head);
  if (status) {
    const end = status.index + status[0].length;
    const bold = /^[ \t]*\*\*/.test(status[0]);
    return `${head.slice(0, end)}\n${bold ? `**${name}:**` : `${name}:`} ${value}${head.slice(end)}${rest}`;
  }
  const title = /^#[ \t]+.*$/m.exec(head);
  const at = title ? title.index + title[0].length : -1;
  if (at === -1) return `${name}: ${value}\n\n${text}`;
  return `${head.slice(0, at)}\n\n${name}: ${value}${head.slice(at)}${rest}`;
}

// `text` with `body` appended under `## Comments`, which is added once where missing.
function appendComment(text: string, body: string): string {
  const base = text.replace(/\s*$/, "\n");
  const heading = COMMENTS.test(text) ? "" : "\n## Comments\n";
  return `${base}${heading}\n${body.trim()}\n`;
}

function names(value: string | undefined): string[] {
  return (value ?? "").split(",").map((name) => name.trim()).filter(Boolean);
}

function shellQuote(word: string): string {
  return `'${word.replaceAll("'", `'\\''`)}'`;
}

export function local(sh: Sh, cwd: string, base: string): Tracker {
  let home: string | undefined;
  let user: string | undefined;

  function git(args: string[], at = root()): string {
    const run = sh("git", args, { cwd: at });
    if (run.code !== 0) throw new Error(`git ${args.join(" ")} failed: ${run.stderr.trim() || `exit ${run.code}`}`);
    return run.stdout;
  }

  // The main checkout, which holds `.scratch/` and base.
  function root(): string {
    home ??= dirname(git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd).trim());
    return home;
  }

  function scratch(...parts: string[]): string {
    return join(root(), ".scratch", ...parts);
  }

  function features(): string[] {
    if (!existsSync(scratch())) return [];
    return readdirSync(scratch(), { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && FEATURE.test(entry.name))
      .map((entry) => entry.name)
      .sort();
  }

  function parentFile(feature: string): string | undefined {
    return PARENT_FILES.map((name) => scratch(feature, name)).find((path) => existsSync(path));
  }

  // A feature's children, by number.
  function childFiles(feature: string): { id: Id; path: string }[] {
    const dir = scratch(feature, "issues");
    if (!existsSync(dir)) return [];
    return readdirSync(dir)
      .flatMap((name) => {
        const number = CHILD_FILE.exec(name)?.[1];
        return number === undefined ? [] : [{ id: `${feature}/${number}`, number: Number(number), path: join(dir, name) }];
      })
      .sort((a, b) => a.number - b.number)
      .map(({ id, path }) => ({ id, path }));
  }

  // The file `id` names, with the id as its file spells the number. `feat/1` finds
  // `feat/issues/01-schema.md` and comes back as `feat/01`.
  function locate(id: Id): { id: Id; path: string } {
    const [feature = "", number, extra] = id.split("/");
    if (!FEATURE.test(feature) || extra !== undefined || (number !== undefined && !/^\d+$/.test(number))) {
      throw new Error(`"${id}" is not a local ticket id: use <feature>/NN, or <feature> for its spec`);
    }
    if (number === undefined) {
      const path = parentFile(feature);
      if (!path) throw new Error(`no ticket ${id}: .scratch/${feature} has no ${PARENT_FILES.join(" or ")}`);
      return { id: feature, path };
    }
    const child = childFiles(feature).find((c) => Number(c.id.split("/")[1]) === Number(number));
    if (!child) throw new Error(`no ticket ${id}: .scratch/${feature}/issues has no ${number}-*.md`);
    return child;
  }

  function issue(id: Id, text: string): Issue {
    const status = field(text, "Status") ?? "";
    const title = /^#[ \t]+(.+?)[ \t]*$/m.exec(text)?.[1]?.replace(/^\d+:\s*/, "") ?? id;
    return {
      id,
      title,
      open: status.toLowerCase() !== RESOLVED,
      labels: status ? [status] : [],
      assignees: names(field(text, "Assignee")),
      body: text,
    };
  }

  // Read the file `id` names, change it, and write it back in one write.
  function edit(id: Id, change: (text: string) => string): void {
    const { path } = locate(id);
    const before = readFileSync(path, "utf8");
    const after = change(before);
    if (after !== before) writeFileSync(path, after);
  }

  function me(): string {
    if (user === undefined) {
      const run = sh("git", ["config", "user.name"], { cwd: root() });
      user = run.stdout.trim();
      if (run.code !== 0 || user === "") throw new Error("git user.name is not set, so the local tracker cannot claim a ticket");
    }
    return user;
  }

  // The branch of worktree issue-<feature>-NN, while that worktree exists.
  function branchOf(id: Id): string | undefined {
    const name = worktreeName(id);
    for (const block of git(["worktree", "list", "--porcelain"]).split("\n\n")) {
      const path = /^worktree (.+)$/m.exec(block)?.[1];
      const branch = /^branch refs\/heads\/(.+)$/m.exec(block)?.[1];
      if (path && branch && basename(path) === name) return branch;
    }
    return undefined;
  }

  // The short hash of the commit on base whose trailer names `id`, read fresh each time.
  function squashOf(id: Id): string | undefined {
    const format = `--format=%h%x09%(trailers:key=${TRAILER},valueonly,separator=%x2C)`;
    for (const line of git(["log", base, format, "--"]).split("\n")) {
      const [hash, values] = line.split("\t");
      if (hash && names(values).includes(id)) return hash;
    }
    return undefined;
  }

  function ahead(branch: string): number {
    return Number(git(["rev-list", "--count", `${base}..${branch}`]).trim());
  }

  return {
    list(filter: Filter) {
      const found: Issue[] = [];
      for (const feature of features()) {
        const parent = parentFile(feature);
        const files = [...(parent ? [{ id: feature, path: parent }] : []), ...childFiles(feature)];
        for (const file of files) {
          const ticket = issue(file.id, readFileSync(file.path, "utf8"));
          if (ticket.labels.includes(filter.label) && (ticket.open || filter.closed)) found.push(ticket);
        }
      }
      return found;
    },

    view(id) {
      const file = locate(id);
      return issue(file.id, readFileSync(file.path, "utf8"));
    },

    me,

    ref(id) {
      return id;
    },

    // Each item of the Blocked by line that starts with a number, such as `01` or
    // `01: Set up the schema`, is a ticket of the same feature. `other/02` names a ticket
    // of another feature. `None (can start immediately)` names none.
    blockers(id) {
      const { id: own, path } = locate(id);
      const feature = own.split("/")[0] ?? "";
      const found = names(field(readFileSync(path, "utf8"), "Blocked by")).flatMap((item) => {
        const ref = /^(?:([A-Za-z0-9_][\w.-]*)\/)?#?(\d+)\b/.exec(item);
        if (!ref) return [];
        const blocker = `${ref[1] ?? feature}/${ref[2]}`;
        try {
          return [locate(blocker).id];
        } catch {
          return [blocker];
        }
      });
      return [...new Set(found)];
    },

    claim(id) {
      const user = me();
      edit(id, (text) => setField(
        setField(text, "Status", IN_PROGRESS),
        "Assignee",
        [...new Set([...names(field(text, "Assignee")), user])].join(", "),
      ));
    },

    unclaim(id) {
      const user = me();
      edit(id, (text) => setField(
        setField(text, "Status", READY),
        "Assignee",
        names(field(text, "Assignee")).filter((name) => name !== user).join(", "),
      ));
    },

    setState(id, _from, to) {
      edit(id, (text) => (field(text, "Status") === to ? text : setField(text, "Status", to)));
    },

    comment(id, body) {
      edit(id, (text) => appendComment(text, body));
    },

    // A spec or a map is a parent, with or without children, and a ticket never is.
    isParent(id) {
      return !id.includes("/");
    },

    children(id) {
      return id.includes("/") ? [] : childFiles(id).map((child) => child.id);
    },

    close(id, body) {
      edit(id, (text) => setField(appendComment(text, body), "Status", RESOLVED));
    },

    // The branch is the PR. It is open while it holds commits that base has not taken.
    // Once its worktree is gone, the squash commit stands for it.
    prFor(id): Pr | null {
      const squash = squashOf(id);
      const branch = branchOf(id);
      if (branch) return { ref: branch, url: branch, open: squash === undefined && ahead(branch) > 0 };
      return squash ? { ref: squash, url: squash, open: false } : null;
    },

    isMerged(id) {
      return squashOf(id) !== undefined;
    },

    // Squash the branch into base in the main checkout, then commit. It refuses unless
    // that checkout is on base and clean, apart from the loop's own state, and the branch
    // merges with no conflict.
    merge(id) {
      const squash = squashOf(id);
      if (squash) return `${id} is already merged into ${base} as ${squash}, so the next tick tears it down`;
      const branch = branchOf(id);
      if (!branch) return `no worktree ${worktreeName(id)} holds a branch for ${id}`;
      if (ahead(branch) === 0) return `branch ${branch} has no commits ahead of ${base}`;
      const head = sh("git", ["symbolic-ref", "--quiet", "--short", "HEAD"], { cwd: root() }).stdout.trim();
      if (head !== base) return `the main checkout ${root()} is on ${head || "a detached HEAD"}, not ${base}`;
      const dirty = git(["status", "--porcelain", "--", ".", ...OWN_STATE.map((path) => `:(exclude)${path}`)]);
      if (dirty.trim() !== "") return `the main checkout ${root()} has uncommitted changes`;
      const trial = sh("git", ["merge-tree", "--write-tree", base, branch], { cwd: root() });
      if (trial.code === 1) return `branch ${branch} does not merge cleanly into ${base}`;
      if (trial.code !== 0) throw new Error(`git merge-tree ${base} ${branch} failed: ${trial.stderr.trim() || `exit ${trial.code}`}`);
      const file = locate(id);
      const { title } = issue(file.id, readFileSync(file.path, "utf8"));
      git(["merge", "--squash", branch]);
      git(["commit", "-m", `${title} (${id})`, "-m", `Squash of branch ${branch}.`, "-m", `${TRAILER}: ${id}`]);
      return null;
    },

    viewCommand(id) {
      return `cat ${shellQuote(locate(id).path)}`;
    },

    reviewStep(id, base, prSkill) {
      return `Leave the work committed on your branch, and push nothing: the branch is the review surface, and `
        + `${base} takes it as a squash merge. Write its description with ${prSkill}, and append it under `
        + `"## Comments" at the end of ${locate(id).path}.`;
    },

    // The state is the Status line, so there is no label to create.
    ensureLabels(_labels: Label[]) {
      return [];
    },
  };
}
