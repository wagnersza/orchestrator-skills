#!/usr/bin/env python3
"""Emit the skill-fork-sync plans as JSON. Mutates nothing.

The deterministic half of both modes lives here and nowhere else (ADR 0008).

**Sync plan** — which SHA each fork is pinned to, which SHA upstream is on, what
the delta touches, which of the changed skills this repo consumes, and how the
5-run budget is spread across them:

    python3 -m scripts.fork_state                       # every fork
    python3 -m scripts.fork_state --fork mattpocock     # one fork
    python3 -m scripts.fork_state --clone /path/to/fork --upstream-repo o/r

**Bootstrap plan** — the fork targets, each one's currently-installed SHA, and
the six ordered bootstrap steps with a per-step done/todo status, printed as the
dry run and executed by nobody:

    python3 -m scripts.fork_state --bootstrap           # human-readable dry run
    python3 -m scripts.fork_state --bootstrap --json    # the same plan as JSON
    python3 -m scripts.fork_state --bootstrap --fork ponytail

Every fact is derived; none is recorded in this repo. Read-only by construction:
`git rev-parse`, `git diff --name-only`, `git ls-tree`, `git merge-base
--is-ancestor`, `git remote get-url`, `git cat-file -e`, `gh repo view`, `gh api
user`, and reads of `known_marketplaces.json` / `installed_plugins.json`. No
fetch, so a sync must refresh the `upstream` remote before calling this — that is
the caller's mutation, not this script's.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ADR 0008: 5 worker runs per sync, pinned-baseline runs included. An eval is a
# pair — one candidate run, one pinned-baseline run — so the ceiling buys two
# paired comparisons and keeps the 5th run as a tiebreak.
RUN_BUDGET = 5
RUNS_PER_SKILL = 2

PINNED_REF = "main"
CANDIDATE_REF = "upstream/main"

DEFAULT_MARKETPLACES = Path.home() / ".claude/plugins/known_marketplaces.json"
DEFAULT_INSTALLED = Path.home() / ".claude/plugins/installed_plugins.json"
DEFAULT_FORKS_DIR = Path.home() / ".orchestrator/forks"

# Directories never grepped for a skill reference: machine-local noise, vendored
# trees, and git's own object store.
SKIP_DIRS = {".git", ".orchestrator", "node_modules", "__pycache__", ".venv"}


# --- git (read-only) --------------------------------------------------------


def git(clone, *args):
    """Run a read-only git command in `clone`, returning stdout stripped."""
    proc = subprocess.run(
        ["git", "-C", str(clone), *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed in {clone}: {proc.stderr.strip()}")
    return proc.stdout.strip()


class GitError(RuntimeError):
    """A git read failed — reported into the plan, never raised past the CLI."""


def skill_dirs(clone, sha):
    """Every directory holding a SKILL.md at `sha`."""
    listing = git(clone, "ls-tree", "-r", "--name-only", sha)
    return {
        str(Path(path).parent)
        for path in listing.splitlines()
        if Path(path).name == "SKILL.md"
    }


def changed_paths(clone, pinned, candidate):
    diff = git(clone, "diff", "--name-only", f"{pinned}..{candidate}")
    return [line for line in diff.splitlines() if line]


# --- fork discovery ---------------------------------------------------------


def discover_forks(marketplaces_path, forks_dir, gh=None):
    """The fork set: registered marketplaces that GitHub says are forks.

    No hand-maintained registry — the marketplace config says which repos feed
    this machine's sessions, and `gh repo view --json parent` says which of
    those are forks. A fork with no clone is reported as an error entry rather
    than dropped, since a missing clone means bootstrap has not run.

    The complement is `bootstrap_targets()`: this finds the forks bootstrap has
    already made, that finds the declared dependencies still on upstream.
    """
    gh = gh or GitHubReader()
    data = json.loads(Path(marketplaces_path).read_text())
    forks = []
    for name in sorted(data):
        repo = (data[name].get("source") or {}).get("repo")
        if not repo:
            continue
        parent = gh.repo(repo)["parent"]
        if not parent:
            continue
        forks.append(
            {
                "fork": name,
                "fork_repo": repo,
                "upstream": parent,
                "clone": str(Path(forks_dir) / name),
            }
        )
    return forks


def gh_user():
    """The authenticated GitHub login — the account forks are created in."""
    proc = subprocess.run(
        ["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise GhError(f"gh api user failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def gh_repo_state(repo):
    """Whether `repo` exists on GitHub and, if it is a fork, its upstream."""
    proc = subprocess.run(
        ["gh", "repo", "view", repo, "--json", "parent"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        if "Could not resolve to a Repository" not in proc.stderr:
            print(
                f"warning: gh repo view {repo} failed for a reason other than "
                f"'not found', reporting it as absent: {proc.stderr.strip()}",
                file=sys.stderr,
            )
        return {"exists": False, "parent": None}
    parent = (json.loads(proc.stdout or "{}") or {}).get("parent")
    return {
        "exists": True,
        "parent": parent.get("nameWithOwner") if parent else None,
    }


class GhError(RuntimeError):
    """A GitHub read failed — reported into the plan, never raised past the CLI."""


class GitHubReader:
    """The two GitHub reads bootstrap needs, or a fixture standing in for them.

    A fixture file (`--gh-fixture`) is how the tests plan a bootstrap without a
    network or a `gh` login, the same way `--clone` bypasses fork discovery:

        {"user": "me", "repos": {"them/skills": {"exists": true, "parent": null}}}

    A repo absent from `repos` is reported as not existing.
    """

    def __init__(self, fixture_path=None):
        self.fixture = (
            json.loads(Path(fixture_path).read_text()) if fixture_path else None
        )

    def user(self):
        if self.fixture is not None:
            return self.fixture.get("user", "")
        return gh_user()

    def repo(self, repo):
        if self.fixture is not None:
            state = (self.fixture.get("repos") or {}).get(repo) or {}
            return {"exists": bool(state.get("exists")), "parent": state.get("parent")}
        return gh_repo_state(repo)


# --- consumption ------------------------------------------------------------


def repo_texts(repo):
    """Every readable text file in `repo` as (relative path, contents)."""
    out = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            path = Path(root) / name
            try:
                out.append((str(path.relative_to(repo)), path.read_text()))
            except (OSError, UnicodeDecodeError):
                continue
    return out


def referenced_by(texts, skill):
    """Files in this repo that mention `skill` by name.

    Plain substring match, case-sensitive. ADR 0008: grep over-tests on purpose
    — a false positive spends budget on a skill that did not need it, a false
    negative ships an unevaluated contract change.
    """
    return sorted(path for path, text in texts if skill in text)


# --- the plan ---------------------------------------------------------------


def fork_plan(fork, repo_texts_cache):
    """Derive one fork's half of the Sync plan. No runs allocated yet."""
    plan = dict(fork)
    clone = Path(fork["clone"])
    if not (clone / ".git").exists():
        plan["error"] = f"no fork clone at {clone} — run /skill-fork-sync bootstrap"
        return plan

    try:
        pinned = git(clone, "rev-parse", PINNED_REF)
        candidate = git(clone, "rev-parse", CANDIDATE_REF)
    except GitError as exc:
        plan["error"] = str(exc)
        return plan

    plan["pinned_sha"] = pinned
    plan["candidate_sha"] = candidate
    plan["sha_source"] = "git rev-parse (FORK.md is never read)"
    plan["up_to_date"] = pinned == candidate

    if plan["up_to_date"]:
        plan.update(
            changed_paths=[],
            unmapped_paths=[],
            skills=[],
            consumed=[],
            skipped=[],
        )
        return plan

    paths = changed_paths(clone, pinned, candidate)
    dirs = sorted(
        skill_dirs(clone, pinned) | skill_dirs(clone, candidate),
        key=len,
        reverse=True,
    )

    hits = {}
    unmapped = []
    for path in paths:
        for skill_dir in dirs:
            if path == skill_dir or path.startswith(skill_dir + "/"):
                hits.setdefault(skill_dir, []).append(path)
                break
        else:
            unmapped.append(path)

    skills = []
    for skill_dir in sorted(hits):
        name = Path(skill_dir).name
        refs = referenced_by(repo_texts_cache, name)
        entry = {
            "skill": name,
            "path": skill_dir,
            "changed_paths": hits[skill_dir],
            "consumed": bool(refs),
        }
        if refs:
            entry["referenced_by"] = refs
        else:
            entry["reason"] = "not referenced by this repo"
        skills.append(entry)

    plan.update(
        changed_paths=paths,
        unmapped_paths=unmapped,
        skills=skills,
        consumed=[s["skill"] for s in skills if s["consumed"]],
        skipped=[
            {"skill": s["skill"], "reason": s["reason"]}
            for s in skills
            if not s["consumed"]
        ],
    )
    return plan


def allocate(fork_plans, ceiling=RUN_BUDGET):
    """Spread the Run budget across every consumed skill in the whole plan.

    The ceiling is per sync, not per fork, so allocation is global and in fork
    order. Anything past the ceiling is named in `dropped_for_budget` — silent
    truncation would read as full coverage (ADR 0008).
    """
    capacity = ceiling // RUNS_PER_SKILL
    allocated = 0
    dropped = []

    for plan in fork_plans:
        plan.setdefault("allocated_runs", 0)
        plan.setdefault("dropped_for_budget", [])
        for skill in plan.get("skills", []):
            if not skill["consumed"]:
                skill["runs"] = 0
                continue
            if capacity > 0:
                skill["runs"] = RUNS_PER_SKILL
                capacity -= 1
                allocated += RUNS_PER_SKILL
                plan["allocated_runs"] += RUNS_PER_SKILL
            else:
                skill["runs"] = 0
                skill["dropped_for_budget"] = True
                drop = {
                    "fork": plan["fork"],
                    "skill": skill["skill"],
                    "reason": f"run budget exhausted ({ceiling} runs per sync)",
                }
                dropped.append(drop)
                plan["dropped_for_budget"].append(drop)

    return {
        "ceiling": ceiling,
        "runs_per_skill": RUNS_PER_SKILL,
        "runs_per_skill_note": "one candidate run plus one pinned-baseline run",
        "allocated": allocated,
        "tiebreak_reserve": ceiling - allocated,
        "dropped_for_budget": dropped,
    }


# --- bootstrap: fork targets and the installed SHA --------------------------


def installed_shas(installed_path):
    """`{marketplace name: {plugin, sha, version}}` from `installed_plugins.json`.

    The pin comes from here and not from upstream's head: the installed
    `gitCommitSha` is the body sessions run today, so bootstrapping onto it is
    behaviour-neutral (ADR 0007). A plugin id is `<plugin>@<marketplace>`, and
    the marketplace half is the fork key everywhere else in this script.

    An entry with no `gitCommitSha` (a `@skills-dir` clone, or a plugin installed
    from a local path) is recorded with `sha: None` — there is nothing to pin to,
    which the plan reports rather than guessing.
    """
    data = json.loads(Path(installed_path).read_text())
    out = {}
    for plugin_id, entries in (data.get("plugins") or {}).items():
        if "@" not in plugin_id or not entries:
            continue
        plugin, _, marketplace = plugin_id.rpartition("@")
        newest = max(entries, key=lambda e: e.get("lastUpdated") or "")
        out[marketplace] = {
            "plugin_id": plugin_id,
            "plugin": plugin,
            "installed_sha": newest.get("gitCommitSha"),
            "installed_version": newest.get("version"),
        }
    return out


def declared_marketplaces(repo):
    """Marketplace names this repo declares as dependencies.

    Read out of `orchestrator/references/requirements.md`, which is where the
    dependency set is declared (ADR 0007: "the fork set is exactly what
    `requirements.md` declares"). Every `<plugin>@<marketplace>` id in that file
    contributes its marketplace half, so a dependency added there is picked up
    with no second list to keep in step.
    """
    declared = Path(repo) / "orchestrator/references/requirements.md"
    if not declared.exists():
        return set()
    ids = re.findall(r"\b[a-z0-9][a-z0-9-]*@[a-z0-9][a-z0-9-]*\b", declared.read_text())
    return {i.rpartition("@")[2] for i in ids}


def bootstrap_targets(marketplaces_path, installed_path, forks_dir, repo, gh):
    """The bootstrap fork set: every declared dependency bootstrap has a job on.

    A **fork target** is a registered marketplace that this repo declares as a
    dependency and that is not already the maintainer's own non-fork repo. Two
    shapes qualify, and both must, because bootstrap has to be re-runnable:

    - the marketplace still points at a third party's repo (`gh repo view` reports
      no `parent`) — bootstrap has work to do, and the upstream is that repo;
    - the marketplace already points at a fork (`parent` is set) — bootstrap has
      nothing to do, and reports every step as already done rather than dropping
      the entry, which is what makes a re-run readable as a no-op.

    A declared marketplace whose repo the authenticated user already owns outright
    (`wagnersza/prompt-improver`: their own, no `parent`) is not a target — there
    is nothing to fork.

    `discover_forks()` is the sync-side view of the same config: it lists only the
    forks, because only a fork has a delta to evaluate.
    """
    data = json.loads(Path(marketplaces_path).read_text())
    installed = installed_shas(installed_path)
    declared = declared_marketplaces(repo)
    user = gh.user()

    targets = []
    for name in sorted(data):
        if name not in declared:
            continue
        repo_path = (data[name].get("source") or {}).get("repo")
        if not repo_path:
            continue
        owner, _, tail = repo_path.partition("/")
        parent = gh.repo(repo_path)["parent"]
        if not parent and owner == user:
            continue  # the maintainer's own repo, not a fork of anyone — skip
        upstream = parent or repo_path
        entry = {
            "fork": name,
            "upstream": upstream,
            "fork_repo": f"{user}/{upstream.partition('/')[2] or tail}",
            "clone": str(Path(forks_dir) / name),
            "marketplace_source_now": repo_path,
        }
        entry.update(
            installed.get(
                name,
                {
                    "plugin_id": None,
                    "plugin": None,
                    "installed_sha": None,
                    "installed_version": None,
                },
            )
        )
        if entry["installed_sha"] is None:
            entry["pin_error"] = (
                f"no gitCommitSha for marketplace {name!r} in {installed_path} — "
                "nothing to pin to, so bootstrap cannot be behaviour-neutral"
            )
        targets.append(entry)
    return targets


def bootstrap_steps(target, gh, fork_exists=None):
    """The six ordered bootstrap steps for one target, each with a status.

    Order is load-bearing: the fork must exist before it can be cloned, the pin
    must land before `FORK.md` records it, and the marketplace swap goes last so
    a half-built fork is never what sessions load.

    Status is `todo`, `done` (the step's effect is already in place, so a re-run
    is a no-op) or `blocked` (a precondition is missing — the steps after it can
    only be planned, not checked). Nothing here runs a command that writes.
    """
    clone = Path(target["clone"])
    sha = target.get("installed_sha")
    fork_repo = target["fork_repo"]
    if fork_exists is None:
        fork_exists = gh.repo(fork_repo)["exists"]
    cloned = (clone / ".git").exists()

    def step(n, name, command, status, note):
        return {
            "step": n,
            "name": name,
            "command": command,
            "status": status,
            "note": note,
        }

    steps = [
        step(
            1,
            "fork",
            f"gh repo fork {target['upstream']} --clone=false",
            "done" if fork_exists else "todo",
            f"{fork_repo} already exists"
            if fork_exists
            else f"creates {fork_repo}, public, with GitHub's fork banner and parent field",
        ),
        step(
            2,
            "clone",
            f"git clone https://github.com/{fork_repo}.git {clone}",
            "done" if cloned else ("todo" if fork_exists else "blocked"),
            f"clone already at {clone}"
            if cloned
            else "never under ~/.claude/plugins/marketplaces/ — Claude Code may re-clone that",
        ),
    ]

    if cloned:
        try:
            origin = git(clone, "remote", "get-url", "upstream")
        except GitError:
            origin = ""
        remote_done = origin.rstrip("/").removesuffix(".git").endswith(
            target["upstream"]
        )
    else:
        remote_done = False
    steps.append(
        step(
            3,
            "remote",
            f"git -C {clone} remote add upstream https://github.com/{target['upstream']}.git",
            "done" if remote_done else ("todo" if cloned else "blocked"),
            "upstream remote already points at the original"
            if remote_done
            else "the delta accumulates here and reaches no session until a promote",
        )
    )

    pin_status, pin_note = "blocked", "needs the clone from step 2"
    if not sha:
        pin_status, pin_note = "blocked", target.get("pin_error", "no installed SHA")
    elif cloned:
        pin_status, pin_note = "todo", (
            f"pins the dial at the installed SHA {sha[:7]} "
            f"({target.get('installed_version')}), not upstream's head — "
            "starting at head would advance sessions past unevaluated commits"
        )
        if not has_commit(clone, sha):
            pin_status, pin_note = "blocked", (
                f"installed SHA {sha[:7]} is not in {clone} — fetch upstream first"
            )
        elif pinned_at(clone, sha):
            pin_status, pin_note = "done", f"default branch already pinned at {sha[:7]}"
    steps.append(
        step(
            4,
            "pin",
            f"git -C {clone} reset --hard {sha or '<installed-sha>'} && "
            f"git -C {clone} push --force origin {PINNED_REF}",
            pin_status,
            pin_note,
        )
    )

    fork_md_done = cloned and (clone / "FORK.md").exists()
    steps.append(
        step(
            5,
            "FORK.md",
            f"write {clone / 'FORK.md'} && git -C {clone} add FORK.md && "
            f'git -C {clone} commit -m "Record the fork and its pin" && '
            f"git -C {clone} push origin {PINNED_REF}",
            "done" if fork_md_done else ("todo" if cloned else "blocked"),
            "FORK.md already committed"
            if fork_md_done
            else "upstream repo, fork date, last-synced SHA, why the fork exists, "
            "local changes — a human record; the pin is always read live from git",
        )
    )

    swap_done = target["marketplace_source_now"] == fork_repo
    if swap_done:
        swap_status = "done"
        swap_note = f"{target['fork']} already points at {fork_repo}"
    else:
        # The swap goes last on purpose: pointing the marketplace at a fork whose
        # pin has not landed is what would change what sessions load.
        swap_status = "todo" if pin_status == "done" and fork_md_done else "blocked"
        swap_note = (
            f"remove-then-add: {target['fork']} currently points at "
            f"{target['marketplace_source_now']}, and one marketplace name holds "
            "exactly one source, so fork and upstream are mutually exclusive. The "
            "name itself stays as upstream defines it"
        )
        if swap_status == "blocked":
            swap_note += " — needs the pin from step 4 in place first"
    steps.append(
        step(
            6,
            "marketplace swap",
            f"claude plugin marketplace remove {target['fork']} && "
            f"claude plugin marketplace add {fork_repo}",
            swap_status,
            swap_note,
        )
    )
    return steps


def has_commit(clone, sha):
    """Whether `sha` is an object in `clone` — read-only."""
    try:
        git(clone, "cat-file", "-e", f"{sha}^{{commit}}")
        return True
    except GitError:
        return False


def pinned_at(clone, sha):
    """Whether the default branch is pinned at `sha`.

    Not `main == sha`: step 5 commits `FORK.md` on top of the pin, so an
    already-bootstrapped fork sits one commit ahead of the installed SHA. The pin
    holds as long as the installed SHA is an ancestor and every commit after it
    touches nothing but `FORK.md` — anything else means the dial has moved and
    re-running the reset would be a promote nobody approved.
    """
    try:
        git(clone, "merge-base", "--is-ancestor", sha, PINNED_REF)
    except GitError:
        return False
    try:
        changed = changed_paths(clone, sha, PINNED_REF)
    except GitError:
        return False
    return all(path == "FORK.md" for path in changed)


def fork_md(target, today):
    """The `FORK.md` body bootstrap would write for one target.

    The five fields are the shape ADR 0007 fixes: upstream repository, fork date,
    last-synced SHA, why the fork exists, local changes.
    """
    sha = target.get("installed_sha") or "<installed-sha>"
    version = target.get("installed_version") or "unknown"
    plugin_id = target.get("plugin_id") or target["fork"]
    return f"""# Fork of {target['upstream']}

- **Upstream repository:** https://github.com/{target['upstream']}
- **Fork date:** {today}
- **Last-synced SHA:** `{sha}` ({version})
- **Why this fork exists:** `claude plugin marketplace add` accepts no ref,
  branch or tag, so a marketplace tracks its source's default-branch HEAD. This
  fork's `{PINNED_REF}` is therefore the version dial for `{plugin_id}`: upstream
  commits accumulate on the `upstream` remote and reach no session until a sync
  evaluates them and the maintainer promotes. See ADR 0007 in
  wagnersza/orchestrator-skills.
- **Local changes:** none, and none intended. This fork pins a version; it is not
  a development branch. The only commit ahead of the pinned upstream SHA is this
  file.

The pinned SHA that drives any decision is read live from git (`git rev-parse
{PINNED_REF}` in this clone), never from this file.
"""


def build_bootstrap_plan(targets, gh, today):
    """The full bootstrap dry run: per target, the ordered steps and FORK.md."""
    plans = []
    for target in targets:
        plan = dict(target)
        plan["steps"] = bootstrap_steps(target, gh)
        plan["fork_md"] = fork_md(target, today)
        plan["already_bootstrapped"] = all(
            s["status"] == "done" for s in plan["steps"]
        )
        plans.append(plan)
    return {
        "generated_by": "scripts.fork_state --bootstrap",
        "mode": "dry run",
        "mutates": "nothing",
        "executed": "nothing — running these steps for real is a human action",
        "pin_source": "installed_plugins.json gitCommitSha (not upstream's head)",
        "targets": plans,
    }


def render_bootstrap(plan):
    """The dry run as text: every action it would take, none of them taken."""
    lines = [
        "DRY RUN — /skill-fork-sync bootstrap",
        "Nothing below is executed. No repository is created, no branch is pushed,",
        "and no marketplace registration is changed by this command.",
        f"Pin source: {plan['pin_source']}",
    ]
    if not plan["targets"]:
        lines += [
            "",
            "No fork targets: every declared dependency is already a fork, already",
            "owned by you, or not registered as a marketplace. Nothing to bootstrap.",
        ]
        return "\n".join(lines) + "\n"

    for target in plan["targets"]:
        sha = target.get("installed_sha")
        lines += [
            "",
            "=" * 74,
            f"{target['fork']}: {target['upstream']} -> {target['fork_repo']}",
            "=" * 74,
            f"  marketplace name   {target['fork']}  (unchanged — comes from "
            "upstream's marketplace.json)",
            f"  plugin id          {target.get('plugin_id') or '(none installed)'}",
            f"  installed SHA      {sha or '(none)'}"
            + (f"  ({target.get('installed_version')})" if sha else ""),
            f"  clone              {target['clone']}",
            f"  status             {'already bootstrapped — every step a no-op' if target['already_bootstrapped'] else 'not bootstrapped'}",
            "",
            "  Steps, in the order they must happen:",
        ]
        for step in target["steps"]:
            lines += [
                f"    {step['step']}. [{step['status'].upper():>7}] {step['name']}",
                f"       would run: {step['command']}",
                f"       {step['note']}",
            ]
        lines += ["", f"  Would write {Path(target['clone']) / 'FORK.md'}:"]
        lines += [f"    | {line}" for line in target["fork_md"].splitlines()]

    lines += [
        "",
        "=" * 74,
        "To run this for real, execute the steps above yourself, in order, per fork.",
        "Creating public repositories and force-pushing are human actions; this",
        "command only ever prints them.",
    ]
    return "\n".join(lines) + "\n"


def build_plan(forks, repo, ceiling=RUN_BUDGET):
    texts = repo_texts(repo)
    fork_plans = [fork_plan(fork, texts) for fork in forks]
    return {
        "generated_by": "scripts.fork_state",
        "mutates": "nothing",
        "consuming_repo": str(repo),
        "run_budget": allocate(fork_plans, ceiling),
        "forks": fork_plans,
    }


# --- CLI --------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.fork_state",
        description=(
            "Emit the Sync plan for the pinned skill forks as JSON, or the "
            "bootstrap dry run with --bootstrap. Mutates nothing either way."
        ),
    )
    parser.add_argument("--fork", help="plan one discovered fork by marketplace name")
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="print the bootstrap dry run instead of the sync plan; takes no action",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="with --bootstrap, emit the plan as JSON instead of text",
    )
    parser.add_argument(
        "--clone",
        help="plan this fork clone directly, skipping discovery (used by the tests)",
    )
    parser.add_argument(
        "--upstream-repo", default="", help="upstream nameWithOwner for --clone"
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="the consuming repo grepped for skill references (default: cwd)",
    )
    parser.add_argument("--marketplaces", default=str(DEFAULT_MARKETPLACES))
    parser.add_argument("--installed", default=str(DEFAULT_INSTALLED))
    parser.add_argument("--forks-dir", default=str(DEFAULT_FORKS_DIR))
    parser.add_argument(
        "--gh-fixture",
        help="JSON standing in for the `gh` reads, so a plan needs no network "
        "(used by the tests)",
    )
    parser.add_argument(
        "--today",
        default="",
        help="the fork date FORK.md records (default: today, UTC)",
    )
    parser.add_argument("--budget", type=int, default=RUN_BUDGET)
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args(argv)

    gh = GitHubReader(args.gh_fixture)

    if args.bootstrap:
        repo = Path(args.repo).resolve()
        try:
            targets = bootstrap_targets(
                args.marketplaces, args.installed, args.forks_dir, repo, gh
            )
        except GhError as exc:
            parser.error(str(exc))
        if args.fork:
            targets = [t for t in targets if t["fork"] == args.fork]
            if not targets:
                parser.error(
                    f"no fork target named {args.fork!r} — a target is a registered "
                    "marketplace this repo declares as a dependency in "
                    "orchestrator/references/requirements.md"
                )
        today = args.today or datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%d"
        )
        plan = build_bootstrap_plan(targets, gh, today)
        if args.json:
            print(json.dumps(plan, indent=args.indent))
        else:
            print(render_bootstrap(plan), end="")
        return 0

    if args.clone:
        clone = Path(args.clone)
        forks = [
            {
                "fork": clone.name,
                "fork_repo": "",
                "upstream": args.upstream_repo,
                "clone": str(clone),
            }
        ]
    else:
        forks = discover_forks(args.marketplaces, args.forks_dir, gh)
        if args.fork:
            forks = [f for f in forks if f["fork"] == args.fork]
            if not forks:
                parser.error(
                    f"no fork named {args.fork!r} in {args.marketplaces} "
                    "(a fork is a registered marketplace whose repo has a GitHub parent)"
                )

    plan = build_plan(forks, Path(args.repo).resolve(), args.budget)
    print(json.dumps(plan, indent=args.indent))
    return 1 if any("error" in f for f in plan["forks"]) else 0


if __name__ == "__main__":
    sys.exit(main())
