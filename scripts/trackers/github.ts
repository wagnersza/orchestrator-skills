// The GitHub backend, through `gh api`. It reads the REST issue shape, because only that
// shape carries `issue_dependencies_summary`.

import type { Sh } from "../sh.ts";
import { IN_PROGRESS, READY, type Filter, type Id, type Issue, type Pr, type Tracker } from "./tracker.ts";

type Raw = {
  number: number;
  title: string;
  state: string;
  body: string | null;
  labels: { name: string }[];
  assignees: { login: string }[];
  repository_url: string;
  pull_request?: unknown;
  issue_dependencies_summary?: { total_blocked_by: number };
};

const REPO = "repos/{owner}/{repo}";

// The PRs GitHub links as closing an issue. Only GraphQL has this link.
const CLOSING_PRS = "query($owner:String!,$repo:String!,$number:Int!){repository(owner:$owner,name:$repo)"
  + "{issue(number:$number){closedByPullRequestsReferences(first:20,includeClosedPrs:true)"
  + "{nodes{number url state}}}}}";

type RawPr = { number: number; url: string; state: string };

// A `Blocked by: #12, #14` line anywhere in the body.
const BLOCKED_BY_LINE = /^[ \t]*blocked by:(.*)$/gim;

export function github(sh: Sh, cwd: string): Tracker {
  // Every issue read in this process, so a blocker listed twice costs one call.
  const seen = new Map<Id, Raw>();
  let login: string | undefined;

  function gh(args: string[], input?: string): string {
    const run = sh("gh", args, { cwd, input });
    if (run.code !== 0) {
      throw new Error(`gh ${args.join(" ")} failed: ${run.stderr.trim() || `exit ${run.code}`}`);
    }
    return run.stdout;
  }

  // Every page of a list endpoint, as one array.
  function pages(path: string): Raw[] {
    return (JSON.parse(gh(["api", "--paginate", "--slurp", path])) as Raw[][]).flat();
  }

  function path(id: Id): string {
    const [repo, number] = id.includes("#") ? id.split("#") : [undefined, id];
    return `${repo ? `repos/${repo}` : REPO}/issues/${number}`;
  }

  // An issue in the repo at `home` keeps its bare number; one elsewhere carries its repo.
  function remember(raw: Raw, home: string): Id {
    const id = raw.repository_url === home
      ? String(raw.number)
      : `${raw.repository_url.split("/").slice(-2).join("/")}#${raw.number}`;
    seen.set(id, raw);
    return id;
  }

  function fetch(id: Id): Raw {
    let raw = seen.get(id);
    if (!raw) {
      raw = JSON.parse(gh(["api", path(id)])) as Raw;
      seen.set(id, raw);
    }
    return raw;
  }

  function issue(id: Id, raw: Raw): Issue {
    return {
      id,
      title: raw.title,
      open: raw.state === "open",
      labels: raw.labels.map((label) => label.name),
      assignees: raw.assignees.map((user) => user.login),
      body: raw.body ?? "",
    };
  }

  function me(): string {
    login ??= gh(["api", "user", "--jq", ".login"]).trim();
    return login;
  }

  // One PATCH that sets the labels and assignees whole, so a state swap is one write.
  function edit(id: Id, change: (labels: string[], assignees: string[]) => [string[], string[]]): void {
    const raw = fetch(id);
    const [labels, assignees] = change(raw.labels.map((l) => l.name), raw.assignees.map((u) => u.login));
    const body = JSON.stringify({ labels: [...new Set(labels)], assignees: [...new Set(assignees)] });
    seen.set(id, JSON.parse(gh(["api", "-X", "PATCH", path(id), "--input", "-"], body)) as Raw);
  }

  function ref(id: Id): string {
    return id.includes("#") ? id : `#${id}`;
  }

  function repoFlag(id: Id): string {
    return id.includes("#") ? ` -R ${id.split("#")[0]}` : "";
  }

  return {
    list(filter: Filter) {
      const label = encodeURIComponent(filter.label);
      return pages(`${REPO}/issues?state=open&labels=${label}&per_page=100`)
        .filter((raw) => raw.pull_request === undefined)
        .sort((a, b) => a.number - b.number)
        .map((raw) => issue(remember(raw, raw.repository_url), raw));
    },

    view(id) {
      return issue(id, fetch(id));
    },

    me,
    ref,

    blockers(id) {
      const raw = fetch(id);
      const native = (raw.issue_dependencies_summary?.total_blocked_by ?? 0) > 0
        ? pages(`${path(id)}/dependencies/blocked_by?per_page=100`).map((b) => remember(b, raw.repository_url))
        : [];
      const lines = [...(raw.body ?? "").matchAll(BLOCKED_BY_LINE)]
        .flatMap((line) => [...(line[1] ?? "").matchAll(/#(\d+)/g)].map((ref) => ref[1] ?? ""));
      return [...new Set([...native, ...lines])];
    },

    claim(id) {
      const login = me();
      edit(id, (labels, assignees) => [[...labels.filter((l) => l !== READY), IN_PROGRESS], [...assignees, login]]);
    },

    unclaim(id) {
      const login = me();
      edit(id, (labels, assignees) => [
        [...labels.filter((l) => l !== IN_PROGRESS), READY],
        assignees.filter((a) => a !== login),
      ]);
    },

    setState(id, from, to) {
      if (fetch(id).labels.some((label) => label.name === to)) return;
      edit(id, (labels, assignees) => [[...labels.filter((l) => l !== from), to], assignees]);
    },

    comment(id, body) {
      gh(["api", "-X", "POST", `${path(id)}/comments`, "--input", "-"], JSON.stringify({ body }));
    },

    prFor(id): Pr | null {
      const [repo, number] = id.includes("#") ? id.split("#") : [undefined, id];
      const [owner, name] = repo ? repo.split("/") : ["{owner}", "{repo}"];
      const reply = JSON.parse(gh([
        "api", "graphql", "-f", `query=${CLOSING_PRS}`,
        "-F", `owner=${owner}`, "-F", `repo=${name}`, "-F", `number=${number}`,
      ])) as { data: { repository: { issue: { closedByPullRequestsReferences: { nodes: RawPr[] } } } } };
      const prs = reply.data.repository.issue.closedByPullRequestsReferences.nodes;
      const pr = prs.find((p) => p.state === "OPEN") ?? prs.at(-1);
      if (!pr) return null;
      return { ref: `${repo ?? ""}#${pr.number}`, url: pr.url, open: pr.state === "OPEN" };
    },

    // JSON, because outside a terminal `--comments` prints the comments and not the body.
    viewCommand(id) {
      return `gh issue view ${id.split("#").pop()}${repoFlag(id)} --json title,body,comments`;
    },

    reviewStep(id, base, prSkill) {
      return `Push, and open a PR (not a draft) against ${base}. Write its body with ${prSkill}, `
        + `and put "Closes ${ref(id)}" in it.`;
    },
  };
}
