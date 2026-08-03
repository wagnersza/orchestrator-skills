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

**Eval plan** — the sync plan turned into the runs a sync may actually spend: a
candidate/pinned worktree pair per **Consumed skill**, the committed eval set each
one extends, the transcript paths, and the budget accounting with everything left
uncovered named:

    python3 -m scripts.fork_state --evals               # every fork
    python3 -m scripts.fork_state --evals --fork mattpocock

**Eval-set merge** — extend a committed eval set with newly drafted assertions
without dropping or rewriting one, printed to stdout for the caller to write:

    python3 -m scripts.fork_state --merge-eval-set --fork mattpocock \\
        --skill code-review --new-assertions new.json --first-seen <candidate-sha>

**Promote plan** — the four ordered steps that turn the dial, each with a status:
whether the candidate can be taken without rewriting history, the `FORK.md` line
that records it, and the update command the dependency's install shape calls for.
Exit 2 when a fork's promote is refused:

    python3 -m scripts.fork_state --promote --fork mattpocock
    python3 -m scripts.fork_state --promote --fork mattpocock --candidate <sha>

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

# The directory the plugin system owns. Claude Code may reset or re-clone
# anything under it on `marketplace update`, so no fork clone, candidate worktree
# or eval artefact may live there (ADR 0007). Enforced, not merely intended:
# `check_outside_plugin_root()` refuses to emit an eval plan that names a path
# inside it.
DEFAULT_PLUGIN_ROOT = Path.home() / ".claude/plugins"

# Eval sets are committed here, one file per fork per skill, extended each sync.
EVAL_SET_DIR = "evals"
# Results and transcripts are machine-local noise, gitignored via `.orchestrator/`.
RESULTS_DIR = ".orchestrator/fork-sync"

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


# The **invocation overlay** (ADR 0010): the two keys a fork may delete so an
# unattended worker can reach every registered skill. `scripts/invocation_overlay.py`
# writes it; this is the half that lets a promote still recognise it as the
# overlay rather than a rogue local commit. Keep the two in step.
OVERLAY_KEYS = ("disable-model-invocation", "allow_implicit_invocation")


def overlay_diff(clone, pinned, candidate, path):
    """Whether `path`'s diff is the invocation overlay and nothing else.

    Checked on *content*, not on the filename: an overlaid file's diff is
    deletions of the two `OVERLAY_KEYS` lines (plus the `policy:` header that
    only held one of them). A commit that edits a skill body under cover of the
    overlay adds or deletes something else, and this returns False — which is the
    whole point of reading the diff rather than allowlisting paths.
    """
    body = git(clone, "diff", "--unified=0", f"{pinned}..{candidate}", "--", path)
    for line in body.splitlines():
        if line.startswith(("+++", "---", "@@", "diff ", "index ")):
            continue
        if line.startswith("+"):
            return False  # the overlay only ever deletes
        if line.startswith("-"):
            gone = line[1:].strip()
            if gone == "policy:" or any(key in gone for key in OVERLAY_KEYS):
                continue
            return False
    return True


def overlay_only(clone, pinned, candidate):
    """Whether `pinned..candidate` is nothing but `FORK.md` and the overlay.

    This is the divergence bootstrap and every promote legitimately leave on a
    fork's default branch, so both `pinned_at()` and `fast_forwardable()` ask it
    rather than comparing SHAs or trusting a path allowlist.
    """
    return all(
        path == FORK_RECORD or overlay_diff(clone, pinned, candidate, path)
        for path in changed_paths(clone, pinned, candidate)
    )


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

    # Step 7 goes after the swap, not before: it is the one step that changes what
    # a skill *does* rather than which version is in force, and a fork whose pin
    # has not landed has nothing worth overlaying (ADR 0010).
    overlay_status, overlay_note = "blocked", "needs the clone from step 2"
    if cloned:
        pending = overlay_pending(clone)
        if pending is None:
            overlay_status, overlay_note = "blocked", (
                "no .claude-plugin/plugin.json in the clone — nothing declares "
                "which skills load"
            )
        elif pending:
            overlay_status, overlay_note = "todo", (
                f"{len(pending)} registered skill(s) still block model invocation "
                f"({', '.join(pending[:3])}{'…' if len(pending) > 3 else ''}) — an "
                "unattended worker cannot reach them"
            )
        else:
            overlay_status, overlay_note = "done", (
                "every registered skill is already model-invocable"
            )
    steps.append(
        step(
            7,
            "invocation overlay",
            f"python3 -m scripts.invocation_overlay --clone {clone} --apply && "
            f"git -C {clone} add -A && "
            f'git -C {clone} commit -m "Make every registered skill model-invocable '
            f'(invocation overlay)" && '
            f"git -C {clone} push origin {PINNED_REF}",
            overlay_status,
            overlay_note,
        )
    )
    return steps


def overlay_pending(clone):
    """Registered skills in `clone` that still block model invocation, or None.

    None means the manifest is unreadable, so nothing declares which skills load.
    An empty list means the overlay is already applied — which is what makes step
    7 idempotent and safe to re-run after every promote (ADR 0010).
    """
    manifest = Path(clone) / ".claude-plugin" / "plugin.json"
    try:
        registered = json.loads(manifest.read_text()).get("skills", [])
    except (OSError, json.JSONDecodeError):
        return None
    pending = []
    for rel in registered:
        skill_md = Path(clone) / rel / "SKILL.md"
        try:
            text = skill_md.read_text()
        except OSError:
            continue
        if any(
            line.strip().startswith(f"{OVERLAY_KEYS[0]}:") for line in text.splitlines()
        ):
            pending.append(Path(rel).name)
    return pending


def step(n, name, command, status, note):
    """One ordered step of a plan: what to run, whether it is needed, and why.

    Shared by the bootstrap dry run and the promote plan, because both are read
    the same way — a numbered list where `done` means "skip it, the effect is
    already in place" (`bootstrap_steps`, `promote_steps`).
    """
    return {"step": n, "name": name, "command": command, "status": status, "note": note}


def has_commit(clone, sha):
    """Whether `sha` is an object in `clone` — read-only."""
    try:
        git(clone, "cat-file", "-e", f"{sha}^{{commit}}")
        return True
    except GitError:
        return False


def pinned_at(clone, sha):
    """Whether the default branch is pinned at `sha`.

    Not `main == sha`: step 5 commits `FORK.md` on top of the pin and the
    invocation overlay (ADR 0010) commits on top of that, so an
    already-bootstrapped fork sits a couple of commits ahead of the installed SHA.
    The pin holds as long as the installed SHA is an ancestor and everything after
    it is `FORK.md` or the overlay — anything else means the dial has moved and
    re-running the reset would be a promote nobody approved.
    """
    try:
        git(clone, "merge-base", "--is-ancestor", sha, PINNED_REF)
    except GitError:
        return False
    try:
        return overlay_only(clone, sha, PINNED_REF)
    except GitError:
        return False


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
- **Local changes:** none but the **invocation overlay**, and none else intended.
  This fork pins a version; it is not a development branch. The overlay deletes
  two keys and nothing more — `disable-model-invocation` from `SKILL.md`
  frontmatter and `policy.allow_implicit_invocation` from `agents/openai.yaml` —
  so every registered skill is reachable by an unattended orchestrator worker. No
  skill body, name or description is edited. See ADR 0010 in
  wagnersza/orchestrator-skills.

The pinned SHA that drives any decision is read live from git (`git rev-parse
{PINNED_REF}` in this clone), never from this file.

## Re-applying the overlay after a promote

The overlay is a deletion of two known keys, so an upstream commit that adds a new
user-invoked skill re-introduces them. After every promote, from the
`orchestrator-skills` repo root:

```bash
python3 -m scripts.invocation_overlay --clone {target['clone']} --apply
```

Without `--apply` it prints what it would change and touches nothing.
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


# --- the eval plan: the Sync plan turned into the runs a sync may spend -------


class PluginRootError(RuntimeError):
    """A planned path fell inside the directory the plugin system owns.

    Raised instead of reported, so no eval plan naming such a path is ever
    emitted: the guarantee behind "the live plugin cache is unmodified" is that
    the plan the flow follows cannot contain a path under it (ADR 0007).
    """


def check_outside_plugin_root(paths, plugin_root):
    """Refuse any planned path inside `plugin_root`. Returns the paths checked."""
    root = Path(plugin_root).expanduser().resolve()
    for path in paths:
        resolved = Path(path).expanduser().resolve()
        if resolved == root or root in resolved.parents:
            raise PluginRootError(
                f"planned path {resolved} is inside the plugin system's directory "
                f"{root} — Claude Code may reset or re-clone that tree on "
                "`marketplace update`, and an eval must never write there"
            )
    return [str(p) for p in paths]


def loads_via_hook(clone, sha):
    """Whether the plugin at `sha` loads through a session hook.

    A `hooks` key in `.claude-plugin/plugin.json` means the skill body reaches a
    session via a SessionStart hook rather than skill invocation (`ponytail`),
    and path injection cannot exercise a hook. Such a fork's assertions test the
    skill body's *content* instead of its runtime behaviour — weaker evidence,
    named in the plan rather than papered over (ADR 0008).
    """
    try:
        manifest = git(clone, "show", f"{sha}:.claude-plugin/plugin.json")
    except GitError:
        return False
    try:
        return bool(json.loads(manifest).get("hooks"))
    except json.JSONDecodeError:
        return False


def eval_set_path(repo, fork, skill):
    """Where the committed eval set for one fork's one skill lives.

    Per fork per skill, under `evals/`, so a sync extends exactly one file and
    two forks that happen to ship a same-named skill never collide.
    """
    return Path(repo) / EVAL_SET_DIR / fork / f"{skill}.json"


def read_eval_set(path, fork, skill):
    """The committed eval set, or the empty skeleton a first sync would write."""
    path = Path(path)
    if not path.exists():
        return {
            "skill_name": skill,
            "fork": fork,
            "assertions": [],
        }, False
    data = json.loads(path.read_text())
    data.setdefault("skill_name", skill)
    data.setdefault("fork", fork)
    data.setdefault("assertions", [])
    return data, True


def merge_eval_set(existing, new_assertions, first_seen=""):
    """Extend an eval set — never rewrite or drop one.

    Existing assertions keep their text, their order and their
    `first_seen_candidate`, so results stay comparable across syncs; a new
    assertion is appended only if its `name` is not already present. An incoming
    assertion that reuses an existing name is reported as `unchanged` rather than
    overwriting it: a redrafted assertion under an old name would silently break
    comparability with every earlier sync.
    """
    merged = dict(existing)
    kept = [dict(a) for a in existing.get("assertions", [])]
    names = {a.get("name") for a in kept}

    added, unchanged = [], []
    for assertion in new_assertions:
        name = assertion.get("name")
        if not name:
            raise ValueError("every assertion needs a `name` — the table is read by name")
        if name in names:
            unchanged.append(name)
            continue
        entry = dict(assertion)
        entry.setdefault("first_seen_candidate", first_seen)
        kept.append(entry)
        names.add(name)
        added.append(name)

    merged["assertions"] = kept
    return {
        "eval_set": merged,
        "kept": [a["name"] for a in existing.get("assertions", [])],
        "added": added,
        "unchanged_kept_as_is": unchanged,
        "total_assertions": len(kept),
    }


def skill_evals(fork, skill, repo, results_root, hook_loaded):
    """The two runs one **Consumed skill** costs, and everything they need."""
    clone = Path(fork["clone"])
    candidate = fork["candidate_sha"]
    pinned = fork["pinned_sha"]
    worktree_root = clone.parent / ".worktrees" / fork["fork"]
    candidate_tree = worktree_root / f"{candidate[:7]}-candidate"
    pinned_tree = worktree_root / f"{pinned[:7]}-pinned"
    results = Path(results_root) / f"{fork['fork']}-{candidate[:7]}"

    set_path = eval_set_path(repo, fork["fork"], skill["skill"])
    eval_set, existed = read_eval_set(set_path, fork["fork"], skill["skill"])

    return {
        "skill": skill["skill"],
        "skill_path_in_repo": skill["path"],
        "changed_paths": skill["changed_paths"],
        "referenced_by": skill.get("referenced_by", []),
        "runs": skill["runs"],
        "eval_set": {
            "path": str(set_path.relative_to(Path(repo))),
            "exists": existed,
            "action": "extend" if existed else "create",
            "assertions_now": len(eval_set["assertions"]),
            "assertion_names": [a.get("name") for a in eval_set["assertions"]],
            "committed": True,
        },
        "assertion_target": (
            "skill body content — this plugin loads via a session hook, which "
            "path injection cannot exercise"
            if hook_loaded
            else "runtime behaviour under path injection"
        ),
        "loads_via_hook": hook_loaded,
        "worktrees": {
            "candidate": {
                "path": str(candidate_tree),
                "ref": candidate,
                "skill_dir": str(candidate_tree / skill["path"]),
            },
            "pinned": {
                "path": str(pinned_tree),
                "ref": pinned,
                "skill_dir": str(pinned_tree / skill["path"]),
                "why": "baseline is the Pinned SHA, not no-skill — the question is "
                "whether upstream regressed",
            },
        },
        "transcripts": {
            "candidate": str(results / f"{skill['skill']}-candidate.md"),
            "pinned": str(results / f"{skill['skill']}-pinned.md"),
        },
        "results_dir": str(results),
    }


def build_eval_plan(plan, repo, results_root=None, plugin_root=DEFAULT_PLUGIN_ROOT):
    """Turn a Sync plan into the eval plan: what runs, where, against what.

    Adds no run of its own and spends nothing — it only says what the judgment
    half may spend, and refuses to name a path inside the plugin system's
    directory (`check_outside_plugin_root`).
    """
    repo = Path(repo)
    results_root = Path(results_root) if results_root else repo / RESULTS_DIR
    budget = plan["run_budget"]

    forks, planned_paths, uncovered = [], [], []
    for fork in plan["forks"]:
        entry = {
            "fork": fork["fork"],
            "clone": fork["clone"],
        }
        if "error" in fork:
            entry.update(
                error=fork["error"],
                bootstrapped=False,
                evals=[],
                runs_planned=0,
                verdict="cannot evaluate",
                verdict_reason=(
                    "no fork clone — run /skill-fork-sync bootstrap first; nothing "
                    "was spent"
                ),
            )
            forks.append(entry)
            continue

        entry.update(
            pinned_sha=fork["pinned_sha"],
            candidate_sha=fork["candidate_sha"],
            bootstrapped=True,
            up_to_date=fork["up_to_date"],
        )
        hook_loaded = (
            False if fork["up_to_date"] else loads_via_hook(fork["clone"], fork["candidate_sha"])
        )
        evals = [
            skill_evals(fork, skill, repo, results_root, hook_loaded)
            for skill in fork.get("skills", [])
            if skill.get("runs")
        ]
        for item in evals:
            planned_paths += [
                item["worktrees"]["candidate"]["path"],
                item["worktrees"]["pinned"]["path"],
                item["results_dir"],
            ]

        for skill in fork.get("skipped", []):
            uncovered.append(
                {
                    "fork": fork["fork"],
                    "skill": skill["skill"],
                    "reason": skill["reason"],
                    "cost": 0,
                }
            )
        for drop in fork.get("dropped_for_budget", []):
            uncovered.append({**drop, "cost": 0})

        entry.update(
            evals=evals,
            runs_planned=sum(item["runs"] for item in evals),
            loads_via_hook=hook_loaded,
        )
        if fork["up_to_date"]:
            entry.update(
                verdict="promotable",
                verdict_reason="no delta — the pin is already the candidate",
            )
        elif not evals:
            entry.update(
                verdict="promotable",
                verdict_reason=(
                    "the delta touches nothing this repo consumes, so zero eval "
                    "runs are spent"
                ),
            )
        else:
            entry.update(
                verdict="needs evaluation",
                verdict_reason=(
                    f"{len(evals)} consumed skill(s) changed; the promote-or-hold "
                    "recommendation comes from the assertion table, and the "
                    "decision stays the maintainer's"
                ),
            )
        forks.append(entry)

    check_outside_plugin_root(planned_paths, plugin_root)

    runs_planned = sum(f["runs_planned"] for f in forks)
    return {
        "generated_by": "scripts.fork_state --evals",
        "mutates": "nothing",
        "consuming_repo": str(repo),
        "plugin_root_untouched": str(Path(plugin_root).expanduser()),
        "candidate_loaded_by": "path injection into the eval worker's prompt",
        "budget": {
            "ceiling": budget["ceiling"],
            "runs_per_skill": budget["runs_per_skill"],
            "runs_planned": runs_planned,
            "spent_on": [
                {
                    "fork": fork["fork"],
                    "skill": item["skill"],
                    "runs": item["runs"],
                    "split": "1 candidate + 1 pinned baseline",
                }
                for fork in forks
                for item in fork["evals"]
            ],
            "remaining": budget["ceiling"] - runs_planned,
            "remaining_note": "held as a tiebreak, not spent to fill the ceiling",
            "uncovered": uncovered,
        },
        "promotes": "nothing — the recommendation is advisory and the maintainer decides",
        "rejecting_a_candidate": (
            "remove the candidate worktree; the live install was never modified, so "
            "there is no rollback"
        ),
        "forks": forks,
    }


# --- promote: the two decisions turning the dial must not get wrong ----------


FORK_RECORD = "FORK.md"
SKILLS_DIR_MARKETPLACE = "skills-dir"


def is_ancestor(clone, ancestor, descendant):
    """Whether `ancestor` is reachable from `descendant` — read-only."""
    try:
        git(clone, "merge-base", "--is-ancestor", ancestor, descendant)
        return True
    except GitError:
        return False


def fast_forwardable(clone, pinned, candidate):
    """Whether taking `candidate` only *adds* commits, so no force-push.

    A promote that would rewrite the fork's default branch means the pin moved
    under the evaluation, and the answer is a re-sync, never a force
    (`promote.md`). Two shapes qualify, and both leave the remote's history
    intact:

    - `candidate` is a descendant of the **Pinned SHA** — a literal fast-forward;
    - the pin diverges from their shared base by nothing but `FORK.md` and the
      **invocation overlay** (ADR 0010), which is exactly the shape bootstrap
      leaves behind (`pinned_at`) and every earlier promote adds to. Merging then
      adds commits and rewrites none.

    Anything else — a real commit on the fork, or a pin ahead of the candidate —
    is refused with the reason, rather than promoted with a `--force`.
    """
    if is_ancestor(clone, pinned, candidate):
        return True, "candidate is a descendant of the pin — a fast-forward"
    try:
        base = git(clone, "merge-base", pinned, candidate)
        local = changed_paths(clone, base, pinned)
        extra = [
            path
            for path in local
            if path != FORK_RECORD and not overlay_diff(clone, base, pinned, path)
        ]
    except GitError as exc:
        return False, str(exc)
    if extra:
        return False, (
            f"the fork's default branch carries local changes upstream does not "
            f"have ({', '.join(extra[:3])}) — merging the candidate would not "
            "produce the evaluated tree. Re-sync; never force"
        )
    return True, (
        f"the pin diverges from the candidate's history by {FORK_RECORD} and the "
        "invocation overlay only, so the merge adds commits and rewrites none"
    )


def plugin_version(clone, sha):
    """The plugin version declared at `sha`, or None — read-only."""
    try:
        manifest = git(clone, "show", f"{sha}:.claude-plugin/plugin.json")
        return json.loads(manifest).get("version")
    except (GitError, json.JSONDecodeError):
        return None


def clones_of(root, fork):
    """Directories directly under `root` that are git clones of this fork's repo.

    Matched on `origin`, not on the directory name: a skills-directory clone is
    named for the *skill* it holds, which need not be the marketplace name.
    """
    wanted = {
        r.rstrip("/").removesuffix(".git")
        for r in (fork.get("fork_repo"), fork.get("upstream"))
        if r
    }
    if not wanted or not Path(root).is_dir():
        return []
    found = []
    for path in sorted(Path(root).iterdir()):
        if not (path / ".git").exists():
            continue
        try:
            origin = git(path, "remote", "get-url", "origin")
        except GitError:
            continue
        if any(origin.rstrip("/").removesuffix(".git").endswith(w) for w in wanted):
            found.append(path)
    return found


def install_shape(fork, installed_path, repo, skills_dir=None):
    """Which update command this dependency's install shape calls for.

    `requirements.md`'s three-shape table, applied rather than restated: a plugin
    takes `claude plugin update <plugin>@<marketplace>`; a clone auto-registered
    from the skills directory takes `git pull --ff-only`, because
    `claude plugin update` fails on it (`Plugin not found`, exit 1); a
    project-level clone takes a `git pull` in the project.

    The discriminators are the two a human reads, in that order: an entry in
    `installed_plugins.json` (which a `@skills-dir` clone is absent from), then a
    git clone on disk under either skills directory whose `origin` is this
    dependency's repo. A dependency that is *both* is the shadowing case
    `requirements.md` warns about, so it is reported as ambiguous and blocks the
    step rather than picking one.
    """
    skills_dir = Path(skills_dir) if skills_dir else Path.home() / ".claude/skills"
    name = fork["fork"]
    installed = installed_shas(installed_path) if Path(installed_path).exists() else {}
    entry = installed.get(name) or {}
    plugin_id = entry.get("plugin_id")

    clones = [
        (label, path)
        for label, root in (
            ("skills-dir clone", skills_dir),
            ("project clone", Path(repo) / ".claude/skills"),
        )
        for path in clones_of(root, fork)
    ]

    if plugin_id and clones:
        return {
            "shape": "ambiguous",
            "command": None,
            "why": (
                f"both a plugin install ({plugin_id}) and a clone at "
                f"{clones[0][1]} — two copies shadowing each other, which "
                "requirements.md says to resolve rather than update blind"
            ),
        }
    if plugin_id:
        return {
            "shape": "plugin",
            "command": f"claude plugin update {plugin_id}",
            "why": "installed as a plugin, so the full plugin@marketplace id updates it",
        }
    if len(clones) == 1:
        label, path = clones[0]
        return {
            "shape": label,
            "command": f"git -C {path} pull"
            + (" --ff-only" if label == "skills-dir clone" else ""),
            "why": (
                "a clone under ~/.claude/skills/ is auto-registered under the "
                "skills-dir marketplace, so it appears in `claude plugin list` but "
                "`claude plugin update` fails on it (Plugin not found, exit 1)"
                if label == "skills-dir clone"
                else "a project-level clone appears in no plugin listing; git owns it"
            ),
        }
    if clones:
        return {
            "shape": "ambiguous",
            "command": None,
            "why": (
                "clones in both ~/.claude/skills/ and the project's .claude/skills/ "
                f"({', '.join(str(p) for _, p in clones)}) — two copies shadowing "
                "each other, which requirements.md says to resolve first"
            ),
        }
    return {
        "shape": "unknown",
        "command": None,
        "why": (
            f"no entry for marketplace {name!r} in {installed_path} and no clone "
            f"under {skills_dir} or {Path(repo) / '.claude/skills'} — read "
            "`claude plugin list` and pick the command from requirements.md's "
            "three-shape table before running anything"
        ),
    }


def records_sha(clone, candidate):
    """Whether `FORK.md` on the default branch already records `candidate`.

    Read from git rather than the working tree, so an uncommitted edit does not
    make step 2 look done. This is the one thing `FORK.md` is read *for* — whether
    the record has caught up — never for what the pin is.
    """
    try:
        return candidate in git(clone, "show", f"{PINNED_REF}:{FORK_RECORD}")
    except GitError:
        return False


def promote_fork_md(clone, candidate, version=None):
    """`FORK.md` with its last-synced SHA rewritten to the candidate.

    The one place this skill writes `FORK.md`. It is still never *read back for a
    decision* — every status in the promote plan comes from git, so a stale record
    cannot make a promote look done (ADR 0007).
    """
    path = Path(clone) / FORK_RECORD
    if not path.exists():
        return None, f"no {FORK_RECORD} at {path} — run /skill-fork-sync bootstrap"
    body = path.read_text()
    line = f"- **Last-synced SHA:** `{candidate}`" + (f" ({version})" if version else "")
    new_body, count = re.subn(
        r"^- \*\*Last-synced SHA:\*\*.*$", lambda _: line, body, flags=re.M
    )
    if not count:
        return None, (
            f"{path} has no `- **Last-synced SHA:**` line to rewrite — restore the "
            "five fields bootstrap writes before promoting"
        )
    return new_body, None


def promote_steps(fork, shape, candidate, ff_ok, ff_reason, already, recorded):
    """The four ordered steps of a promote, each with a status.

    Order is load-bearing and stated in `promote.md`: the branch moves before the
    record, and **the marketplace refreshes before the plugin** — the plugin is
    installed from the marketplace's local clone, so updating the plugin against a
    stale clone reinstalls the version already in force.

    Status is per step and derived from that step's own effect, which is what makes
    a promote that failed partway legible: step 1 landing says nothing about step
    4, so `already` marks step 1 `done` and leaves the rest to their own checks.
    Steps 3 and 4 have no check at all — the marketplace refresh is a fetch that
    costs nothing to repeat, and reading the installed SHA back would report false
    mismatches until a restart, so promote deliberately does not (ADR 0007).
    """
    clone = fork["clone"]
    if already:
        move = ("done", f"the default branch already carries {candidate[:7]}")
    elif ff_ok:
        move = ("todo", ff_reason)
    else:
        move = ("refused", ff_reason)
    blocked = move[0] == "refused"

    return [
        step(
            1,
            "advance the pin",
            f"git -C {clone} merge --no-edit {candidate} && "
            f"git -C {clone} push origin {PINNED_REF}",
            move[0],
            move[1],
        ),
        step(
            2,
            FORK_RECORD,
            f"write {Path(clone) / FORK_RECORD} && git -C {clone} add {FORK_RECORD} && "
            f'git -C {clone} commit -m "Promote to {candidate[:7]}" && '
            f"git -C {clone} push origin {PINNED_REF}",
            "blocked" if blocked else ("done" if recorded else "todo"),
            f"already records {candidate[:7]}"
            if recorded
            else f"records {candidate[:7]} as the synced SHA — a human record, never "
            "read back for a version decision",
        ),
        step(
            3,
            "marketplace",
            f"claude plugin marketplace update {fork['fork']}",
            "blocked" if blocked else "todo",
            "refreshes the marketplace's local clone from the fork; the plugin is "
            "installed out of that clone, so this goes first. Unchecked — a fetch "
            "costs nothing to repeat",
        ),
        step(
            4,
            "plugin",
            shape["command"] or "(shape unresolved — see requirements.md)",
            "blocked" if blocked or not shape["command"] else "todo",
            f"{shape['shape']}: {shape['why']}",
        ),
    ]


def build_promote_plan(
    forks, repo, installed_path, candidate=None, skills_dir=None
):
    """The ordered promote plan per fork. Runs nothing and writes nothing."""
    plans = []
    for fork in forks:
        entry = {"fork": fork["fork"], "clone": fork["clone"]}
        clone = Path(fork["clone"])
        if not (clone / ".git").exists():
            entry.update(
                error=f"no fork clone at {clone} — run /skill-fork-sync bootstrap",
                promotable=False,
                steps=[],
            )
            plans.append(entry)
            continue
        try:
            pinned = git(clone, "rev-parse", PINNED_REF)
            head = git(clone, "rev-parse", CANDIDATE_REF)
        except GitError as exc:
            entry.update(error=str(exc), promotable=False, steps=[])
            plans.append(entry)
            continue

        target = candidate or head
        entry.update(
            pinned_sha=pinned,
            candidate_sha=target,
            upstream_head=head,
            sha_source="git rev-parse (FORK.md is never read)",
        )

        if candidate and not has_commit(clone, candidate):
            entry.update(
                error=(
                    f"candidate {candidate[:7]} is not in {clone} — fetch upstream, "
                    "then re-sync"
                ),
                promotable=False,
                steps=[],
            )
            plans.append(entry)
            continue
        already = is_ancestor(clone, target, pinned)
        if candidate and not already and git(clone, "rev-parse", candidate) != head:
            # The approved candidate is no longer upstream's head: upstream moved
            # after the sync, so the assertion table describes a different tree.
            # Moot once the pin already carries it — there is nothing left to take.
            entry["stale_evaluation"] = (
                f"the approved candidate {candidate[:7]} is not {CANDIDATE_REF} "
                f"({head[:7]}) any more — upstream moved after the sync, so re-sync "
                "before promoting"
            )

        ff_ok, ff_reason = (
            (True, "already promoted")
            if already
            else fast_forwardable(clone, pinned, target)
        )
        shape = install_shape(fork, installed_path, repo, skills_dir)
        version = plugin_version(clone, target)
        body, record_error = promote_fork_md(clone, target, version)

        recorded = records_sha(clone, target)
        entry.update(
            up_to_date=pinned == head and already,
            already_promoted=already,
            record_up_to_date=recorded,
            fast_forward=ff_ok,
            fast_forward_reason=ff_reason,
            install_shape=shape,
            candidate_version=version,
            steps=promote_steps(
                fork, shape, target, ff_ok, ff_reason, already, recorded
            ),
            fork_md=body,
            promotable=ff_ok and "stale_evaluation" not in entry,
        )
        if record_error:
            entry["fork_md_error"] = record_error
        plans.append(entry)

    return {
        "generated_by": "scripts.fork_state --promote",
        "mutates": "nothing",
        "executed": "nothing — running these steps is the maintainer's approved act",
        "approval": (
            "explicit and per promote, including on an all-green assertion table "
            "(ADR 0008)"
        ),
        "verifies_installed_sha_afterwards": False,
        "why_not": (
            "`claude plugin update` may not refresh the loaded cache until a "
            "restart, so reading the installed SHA back would report false "
            "mismatches"
        ),
        "takes_effect": "next session — the running one keeps the body it started with",
        "forks": plans,
    }


def render_promote(plan):
    """The promote plan as text: the ordered steps and what each one is for."""
    lines = [
        "PROMOTE — /skill-fork-sync promote",
        "Nothing below is executed. Run the steps in order, per fork, and report",
        "which ones completed if any of them fails partway.",
        f"Takes effect: {plan['takes_effect']}",
    ]
    if not plan["forks"]:
        return "\n".join(lines + ["", "No fork in scope. Nothing to promote."]) + "\n"

    for fork in plan["forks"]:
        lines += ["", "=" * 74, f"{fork['fork']}", "=" * 74]
        if "error" in fork:
            lines += [f"  REFUSED: {fork['error']}"]
            continue
        lines += [
            f"  pin                {fork['pinned_sha']}",
            f"  candidate          {fork['candidate_sha']}"
            + (f"  ({fork['candidate_version']})" if fork["candidate_version"] else ""),
            f"  fast-forward       {'yes' if fork['fast_forward'] else 'NO'} — "
            f"{fork['fast_forward_reason']}",
            f"  install shape      {fork['install_shape']['shape']}",
        ]
        if fork.get("stale_evaluation"):
            lines += [f"  STALE: {fork['stale_evaluation']}"]
        if fork.get("fork_md_error"):
            lines += [f"  {FORK_RECORD}: {fork['fork_md_error']}"]
        if not fork["promotable"]:
            lines += ["", "  REFUSED — nothing was promoted. Re-sync; never force."]
        lines += ["", "  Steps, in the order they must happen:"]
        for entry in fork["steps"]:
            lines += [
                f"    {entry['step']}. [{entry['status'].upper():>7}] {entry['name']}",
                f"       run: {entry['command']}",
                f"       {entry['note']}",
            ]

    lines += [
        "",
        "=" * 74,
        f"The installed SHA is not checked afterwards: {plan['why_not']}",
    ]
    return "\n".join(lines) + "\n"


# --- CLI --------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.fork_state",
        description=(
            "Emit the Sync plan for the pinned skill forks as JSON, the bootstrap "
            "dry run with --bootstrap, or the promote plan with --promote. Mutates "
            "nothing in any mode."
        ),
    )
    parser.add_argument("--fork", help="plan one discovered fork by marketplace name")
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="print the bootstrap dry run instead of the sync plan; takes no action",
    )
    parser.add_argument(
        "--evals",
        action="store_true",
        help="print the eval plan derived from the sync plan: the worktree pair, "
        "eval set and transcript paths per consumed skill, plus the budget "
        "accounting. Spends no run and creates no worktree",
    )
    parser.add_argument(
        "--merge-eval-set",
        action="store_true",
        help="extend a committed eval set with newly drafted assertions and print "
        "the merged set; writes nothing",
    )
    parser.add_argument(
        "--promote",
        action="store_true",
        help="print the promote plan: the four ordered steps, whether the candidate "
        "can be taken without a force-push, and the update command the install "
        "shape calls for. Promotes nothing. Exit 2 if any fork is refused",
    )
    parser.add_argument(
        "--candidate",
        help="with --promote, the approved candidate SHA (default: upstream/main). A "
        "candidate that is no longer upstream's head is reported as a stale "
        "evaluation",
    )
    parser.add_argument(
        "--skills-dir",
        help="the skills directory a @skills-dir clone would live in "
        "(default: ~/.claude/skills)",
    )
    parser.add_argument("--skill", help="with --merge-eval-set, the skill's eval set")
    parser.add_argument(
        "--new-assertions",
        help="with --merge-eval-set, a JSON file holding the drafted assertions "
        "(a list, or an object with an `assertions` list)",
    )
    parser.add_argument(
        "--first-seen",
        default="",
        help="with --merge-eval-set, the candidate SHA new assertions were drafted "
        "against",
    )
    parser.add_argument(
        "--check-path",
        action="append",
        default=[],
        help="assert this path is outside the plugin system's directory and exit; "
        "how the flow checks a worktree path the configured tool chose rather "
        "than one this script planned. Exit 2 if it is inside",
    )
    parser.add_argument(
        "--results-root",
        help="where eval results and transcripts would go "
        f"(default: <repo>/{RESULTS_DIR}, gitignored)",
    )
    parser.add_argument(
        "--plugin-root",
        default=str(DEFAULT_PLUGIN_ROOT),
        help="the directory the plugin system owns; no planned path may fall "
        "inside it (default: ~/.claude/plugins)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="with --bootstrap or --promote, emit the plan as JSON instead of text",
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

    if args.check_path:
        try:
            checked = check_outside_plugin_root(args.check_path, args.plugin_root)
        except PluginRootError as exc:
            parser.error(str(exc))
        print(
            json.dumps(
                {
                    "checked": checked,
                    "plugin_root": str(Path(args.plugin_root).expanduser()),
                    "outside_plugin_root": True,
                },
                indent=args.indent,
            )
        )
        return 0

    if args.merge_eval_set:
        if not (args.fork and args.skill and args.new_assertions):
            parser.error("--merge-eval-set needs --fork, --skill and --new-assertions")
        repo = Path(args.repo).resolve()
        incoming = json.loads(Path(args.new_assertions).read_text())
        if isinstance(incoming, dict):
            incoming = incoming.get("assertions", [])
        path = eval_set_path(repo, args.fork, args.skill)
        existing, _ = read_eval_set(path, args.fork, args.skill)
        try:
            merged = merge_eval_set(existing, incoming, args.first_seen)
        except ValueError as exc:
            parser.error(str(exc))
        merged["write_to"] = str(path)
        print(json.dumps(merged, indent=args.indent))
        return 0

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

    repo = Path(args.repo).resolve()

    if args.promote:
        plan = build_promote_plan(
            forks, repo, args.installed, args.candidate, args.skills_dir
        )
        if args.json:
            print(json.dumps(plan, indent=args.indent))
        else:
            print(render_promote(plan), end="")
        return 0 if all(f.get("promotable") for f in plan["forks"]) else 2

    plan = build_plan(forks, repo, args.budget)
    if args.evals:
        try:
            plan = build_eval_plan(plan, repo, args.results_root, args.plugin_root)
        except PluginRootError as exc:
            parser.error(str(exc))
    print(json.dumps(plan, indent=args.indent))
    return 1 if any("error" in f for f in plan["forks"]) else 0


if __name__ == "__main__":
    sys.exit(main())
