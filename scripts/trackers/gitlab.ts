// The GitLab backend, through `glab api`. It reads the REST issue and merge request
// shapes, which answer in JSON whatever the terminal, and the GraphQL work item shape for
// the one link REST lacks: an issue's child items. The merge goes through `glab mr merge`.

import type { Sh } from "../sh.ts";
import { IN_PROGRESS, READY, STATES, USER_STORY, type Filter, type Id, type Issue, type Label, type Pr, type Tracker } from "./tracker.ts";

type Raw = {
  iid: number;
  project_id: number;
  title: string;
  state: string;
  description: string | null;
  labels: string[];
  assignees: { id: number; username: string }[];
  web_url: string;
  // Set on an entry of the `links` endpoint, from the side of the issue it was read for.
  link_type?: string;
};

type RawMr = { iid: number; web_url: string; state: string; detailed_merge_status?: string };

type Project = { id: number; path_with_namespace: string };

// The project glab reads from the checkout it runs in.
const HOME = "projects/:fullpath";

// GitLab caps a page at 100 rows, so a page that comes back full has a next one.
const PER_PAGE = 100;

// An issue's child items. Only GraphQL has this link.
const CHILDREN = "query($path:ID!,$iid:String!){project(fullPath:$path){workItems(iid:$iid)"
  + "{nodes{widgets{... on WorkItemWidgetHierarchy{children(first:100){nodes{iid webUrl}}}}}}}}";

type Widget = { children?: { nodes: { iid: string; webUrl: string }[] } };

// A `Blocked by: #12, #14` line anywhere in the body.
const BLOCKED_BY_LINE = /^[ \t]*blocked by:(.*)$/gim;

// The child's half of the parent link: a `## Parent` heading followed by `#N`, which
// docs/agents/issue-tracker.md names, or a `Part of #N` line.
const PARENT_LINE = /^(?:##[ \t]+Parent\s+|[ \t]*Part of[ \t]+)#(\d+)\b/im;

// The project path in a web URL, such as `group/sub/project` in
// `https://gitlab.com/group/sub/project/-/issues/12`.
function pathOf(url: string): string {
  return new URL(url).pathname.split("/-/")[0]?.slice(1) ?? "";
}

export function gitlab(sh: Sh, cwd: string): Tracker {
  // Every issue read in this process, so a blocker listed twice costs one call.
  const seen = new Map<Id, Raw>();
  // Each issue's child items, read once per process.
  const native = new Map<Id, Id[]>();
  let user: { id: number; username: string } | undefined;
  let home: Project | undefined;
  // Each parent's children by parent line, from one read of every issue in the project.
  let byParentLine: Map<Id, Id[]> | undefined;

  function glab(args: string[], input?: string): string {
    const run = sh("glab", args, { cwd, input });
    if (run.code !== 0) {
      throw new Error(`glab ${args.join(" ")} failed: ${run.stderr.trim() || `exit ${run.code}`}`);
    }
    return run.stdout;
  }

  function get<T>(path: string): T {
    return JSON.parse(glab(["api", path])) as T;
  }

  // One JSON write, whose reply is the object it wrote.
  function send<T>(method: string, path: string, body: unknown): T {
    const args = ["api", "-X", method, path, "-H", "Content-Type: application/json", "--input", "-"];
    return JSON.parse(glab(args, JSON.stringify(body))) as T;
  }

  // Every page of a list endpoint, as one array.
  function pages<T>(path: string): T[] {
    const all: T[] = [];
    for (let page = 1; ; page++) {
      const rows = get<T[]>(`${path}${path.includes("?") ? "&" : "?"}per_page=${PER_PAGE}&page=${page}`);
      all.push(...rows);
      if (rows.length < PER_PAGE) return all;
    }
  }

  function project(): Project {
    home ??= get<Project>(HOME);
    return home;
  }

  // An issue in another project carries its path, as `group/project#12`.
  function path(id: Id): string {
    const [repo, number] = id.includes("#") ? id.split("#") : [undefined, id];
    return `${repo ? `projects/${encodeURIComponent(repo)}` : HOME}/issues/${number}`;
  }

  // An issue in this project keeps its bare number; one elsewhere carries its path.
  function idOf(iid: number | string, url: string): Id {
    const repo = pathOf(url);
    return repo === project().path_with_namespace ? String(iid) : `${repo}#${iid}`;
  }

  function remember(raw: Raw): Id {
    const id = idOf(raw.iid, raw.web_url);
    seen.set(id, raw);
    return id;
  }

  function fetch(id: Id): Raw {
    let raw = seen.get(id);
    if (!raw) {
      raw = get<Raw>(path(id));
      seen.set(id, raw);
    }
    return raw;
  }

  function issue(id: Id, raw: Raw): Issue {
    return {
      id,
      title: raw.title,
      open: raw.state === "opened",
      labels: raw.labels,
      assignees: raw.assignees.map((user) => user.username),
      body: raw.description ?? "",
    };
  }

  function whoami(): { id: number; username: string } {
    user ??= get<{ id: number; username: string }>("user");
    return user;
  }

  // One PUT that adds and removes labels and sets the assignees, so a claim is one write.
  // The assignees go only where they change.
  function edit(id: Id, change: { add?: string; remove?: string; assignees?: (ids: number[]) => number[] }): void {
    const raw = fetch(id);
    const body: Record<string, unknown> = {};
    if (change.add) body.add_labels = change.add;
    if (change.remove) body.remove_labels = change.remove;
    if (change.assignees) {
      const before = raw.assignees.map((a) => a.id);
      const after = [...new Set(change.assignees(before))];
      if (after.length !== before.length || after.some((a) => !before.includes(a))) body.assignee_ids = after;
    }
    seen.set(id, send<Raw>("PUT", path(id), body));
  }

  // The children whose body names `id` in a parent line. Only an issue in this project
  // has them, because the line carries a bare number.
  function lineChildren(id: Id): Id[] {
    if (id.includes("#")) return [];
    if (!byParentLine) {
      byParentLine = new Map();
      for (const raw of pages<Raw>(`${HOME}/issues?state=all`).sort((a, b) => a.iid - b.iid)) {
        const parent = PARENT_LINE.exec(raw.description ?? "")?.[1];
        const child = String(raw.iid);
        if (parent === undefined || parent === child) continue;
        if (!seen.has(child)) seen.set(child, raw);
        byParentLine.set(parent, [...(byParentLine.get(parent) ?? []), child]);
      }
    }
    return byParentLine.get(id) ?? [];
  }

  // The child items GitLab links to `id`, read once per process.
  function nativeChildren(id: Id): Id[] {
    let found = native.get(id);
    if (!found) {
      const [repo, iid] = id.includes("#") ? id.split("#") : [project().path_with_namespace, id];
      const reply = JSON.parse(glab([
        "api", "graphql", "-f", `query=${CHILDREN}`, "-f", `path=${repo}`, "-f", `iid=${iid}`,
      ])) as { data?: { project: { workItems: { nodes: { widgets: Widget[] }[] } } | null }; errors?: { message: string }[] };
      if (reply.errors?.length) throw new Error(`glab api graphql failed: ${reply.errors.map((e) => e.message).join("; ")}`);
      const widgets = reply.data?.project?.workItems.nodes[0]?.widgets ?? [];
      found = widgets.flatMap((w) => w.children?.nodes ?? []).map((child) => idOf(child.iid, child.webUrl));
      native.set(id, found);
    }
    return found;
  }

  function ref(id: Id): string {
    return id.includes("#") ? id : `#${id}`;
  }

  // Every MR that closes `id` on merge, oldest first, read fresh on each call.
  function closingMrs(id: Id): RawMr[] {
    return pages<RawMr>(`${path(id)}/closed_by`).sort((a, b) => a.iid - b.iid);
  }

  // The open MR, else the newest closed or merged one.
  function pick(mrs: RawMr[]): RawMr | undefined {
    return mrs.find((m) => m.state === "opened") ?? mrs.at(-1);
  }

  function mrRef(id: Id, mr: RawMr): string {
    return `${id.includes("#") ? id.split("#")[0] : ""}!${mr.iid}`;
  }

  function repoFlag(id: Id): string {
    return id.includes("#") ? ` -R ${id.split("#")[0]}` : "";
  }

  return {
    list(filter: Filter) {
      const label = encodeURIComponent(filter.label);
      return pages<Raw>(`${HOME}/issues?state=${filter.closed ? "all" : "opened"}&labels=${label}`)
        .sort((a, b) => a.iid - b.iid)
        .map((raw) => {
          seen.set(String(raw.iid), raw);
          return issue(String(raw.iid), raw);
        });
    },

    view(id) {
      return issue(id, fetch(id));
    },

    me() {
      return whoami().username;
    },

    ref,

    // `links` names each link from the side of the issue it was read for, so a blocker
    // reads `is_blocked_by`.
    blockers(id) {
      const raw = fetch(id);
      const links = get<Raw[]>(`${path(id)}/links`).filter((link) => link.link_type === "is_blocked_by").map(remember);
      const lines = [...(raw.description ?? "").matchAll(BLOCKED_BY_LINE)]
        .flatMap((line) => [...(line[1] ?? "").matchAll(/#(\d+)/g)].map((ref) => ref[1] ?? ""));
      return [...new Set([...links, ...lines])];
    },

    claim(id) {
      const me = whoami().id;
      edit(id, { add: IN_PROGRESS, remove: READY, assignees: (ids) => [...ids, me] });
    },

    unclaim(id) {
      const me = whoami().id;
      edit(id, { add: READY, remove: IN_PROGRESS, assignees: (ids) => ids.filter((a) => a !== me) });
    },

    setState(id, from, to) {
      if (fetch(id).labels.includes(to)) return;
      edit(id, { add: to, remove: from });
    },

    comment(id, body) {
      send("POST", `${path(id)}/notes`, { body });
    },

    // The label costs no call, and the body scan costs one per process, so the child
    // items, one call per issue, come last.
    isParent(id) {
      return fetch(id).labels.includes(USER_STORY) || lineChildren(id).length > 0 || nativeChildren(id).length > 0;
    },

    // The child items, then each issue whose parent line names `id`, once each.
    children(id) {
      return [...new Set([...nativeChildren(id), ...lineChildren(id)])];
    },

    close(id, body) {
      send("POST", `${path(id)}/notes`, { body });
      const drop = fetch(id).labels.filter((label) => STATES.includes(label));
      seen.set(id, send<Raw>("PUT", path(id), { state_event: "close", ...(drop.length ? { remove_labels: drop.join(",") } : {}) }));
    },

    prFor(id): Pr | null {
      const mr = pick(closingMrs(id));
      if (!mr) return null;
      return { ref: mrRef(id, mr), url: mr.web_url, open: mr.state === "opened" };
    },

    isMerged(id) {
      return closingMrs(id).some((mr) => mr.state === "merged");
    },

    // `-R` names the MR's project by its URL, which carries the host as well. GitLab
    // removes the source branch on its side, so the worktree that has it checked out
    // stays as it is.
    merge(id) {
      const mrs = closingMrs(id);
      const mr = mrs.find((m) => m.state === "opened");
      const merged = mrs.find((m) => m.state === "merged");
      if (!mr && merged) return `MR ${mrRef(id, merged)} is already merged, so the next tick tears it down`;
      if (!mr) return `no open MR closes ${ref(id)}`;
      if (mr.detailed_merge_status === "requested_changes") return `MR ${mrRef(id, mr)} has changes requested`;
      if (mr.detailed_merge_status !== "mergeable") {
        return `MR ${mrRef(id, mr)} is not mergeable (${(mr.detailed_merge_status ?? "unknown").replaceAll("_", " ")})`;
      }
      const repo = mr.web_url.split("/-/")[0] ?? "";
      glab(["mr", "merge", String(mr.iid), "-R", repo, "--squash", "--remove-source-branch", "--yes"]);
      return null;
    },

    viewCommand(id) {
      return `glab issue view ${id.split("#").pop()}${repoFlag(id)} --comments`;
    },

    reviewStep(id, base, prSkill) {
      return `Push, and open a merge request (not a draft) against ${base}. Write its description with ${prSkill}, `
        + `and put "Closes ${ref(id)}" in it.`;
    },

    // The list holds the group labels the project inherits too. A name that differs
    // only in case counts as present, so install never makes a near-duplicate.
    ensureLabels(labels: Label[]) {
      const have = new Set(pages<{ name: string }>(`${HOME}/labels`).map((label) => label.name.toLowerCase()));
      const created: string[] = [];
      for (const label of labels) {
        if (have.has(label.name.toLowerCase())) continue;
        send("POST", `${HOME}/labels`, { ...label, color: `#${label.color}` });
        have.add(label.name.toLowerCase());
        created.push(label.name);
      }
      return created;
    },
  };
}
