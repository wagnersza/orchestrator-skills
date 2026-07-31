#!/usr/bin/env python3
"""Emit the Sync plan for the skill-fork-sync forks as JSON. Mutates nothing.

The deterministic half of a sync lives here and nowhere else (ADR 0008): which
SHA each fork is pinned to, which SHA upstream is on, what the delta touches,
which of the changed skills this repo consumes, and how the 5-run budget is
spread across them. Every fact is derived, none is recorded in the repo.

    python3 -m scripts.fork_state                       # every fork
    python3 -m scripts.fork_state --fork mattpocock     # one fork
    python3 -m scripts.fork_state --clone /path/to/fork --upstream-repo o/r

Read-only by construction: `git rev-parse`, `git diff --name-only` and
`git ls-tree` only. No fetch, so a sync must refresh the `upstream` remote
before calling this — that is the caller's mutation, not this script's.
"""

import argparse
import json
import os
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


def gh_parent(repo):
    """The upstream `nameWithOwner` if `repo` is a GitHub fork, else None."""
    proc = subprocess.run(
        ["gh", "repo", "view", repo, "--json", "parent"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(
            f"warning: gh repo view {repo} failed, treating as non-fork: "
            f"{proc.stderr.strip()}",
            file=sys.stderr,
        )
        return None
    parent = (json.loads(proc.stdout or "{}") or {}).get("parent")
    return parent.get("nameWithOwner") if parent else None


def discover_forks(marketplaces_path, forks_dir):
    """The fork set: registered marketplaces that GitHub says are forks.

    No hand-maintained registry — the marketplace config says which repos feed
    this machine's sessions, and `gh repo view --json parent` says which of
    those are forks. A fork with no clone is reported as an error entry rather
    than dropped, since a missing clone means bootstrap has not run.
    """
    data = json.loads(Path(marketplaces_path).read_text())
    forks = []
    for name in sorted(data):
        repo = (data[name].get("source") or {}).get("repo")
        if not repo:
            continue
        parent = gh_parent(repo)
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
        description="Emit the Sync plan for the pinned skill forks as JSON.",
    )
    parser.add_argument("--fork", help="plan one discovered fork by marketplace name")
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
    parser.add_argument("--forks-dir", default=str(DEFAULT_FORKS_DIR))
    parser.add_argument("--budget", type=int, default=RUN_BUDGET)
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args(argv)

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
        forks = discover_forks(args.marketplaces, args.forks_dir)
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
