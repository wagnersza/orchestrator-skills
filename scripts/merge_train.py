#!/usr/bin/env python3
"""Plan one **Merge train**: the order the queued branches merge in, and the parked ones.

The ordering rule and the park rule live in
`orchestrator/references/merge-train.md`, and this file restates neither one. This file
holds the seam's own contract instead: the flags, the JSON it prints, and one row per
exit code.

**It plans, and it merges nothing.** There is no `--execute` flag, because there is
nothing to execute. The merge is the **Close transaction** this repo already holds. The
session runs that transaction once per item, in the printed order:

    python3 <plugin root>/scripts/merge_train.py --repo /path/to/main/checkout \\
        --default-branch main --item 152:152-merge-train-seam --item 153:153-train-flow

One `--item` carries one queued work item, as its number, a colon and its branch. A
branch name can hold no colon, so the colon needs no escape.

**One JSON object goes to stdout, and nothing else does.** So a caller reads it with
`jq`. Every message about a refusal goes to stderr instead, and a refused run prints
no JSON at all:

    {"generated_by": "scripts.merge_train", "mutates": "nothing", "repo": "...",
     "default_branch": "main", "checkout": "<the throwaway checkout, already removed>",
     "order":  [{"item": 152, "branch": "152-merge-train-seam", "overlaps": 0}],
     "parked": [{"item": 153, "branch": "153-train-flow",
                 "reason": "...", "paths": ["orchestrator/SKILL.md"]}]}

`overlaps` counts the other branches in `order` that change a file this branch also
changes. `paths` names the files the test-merge left conflicted. A run where every
branch parks prints an empty `order` and still exits 0. An empty `order` is a plan, and
not a failure.

| Code | Meaning |
|---|---|
| 0 | the plan is on stdout |
| 1 | a git command failed, or a test-merge failed with no conflicted path to name |
| 2 | a usage error. `argparse` reports it, and no plan is printed |
| 3 | `--repo` holds uncommitted work |
| 4 | a branch this run needs does not exist |
| 5 | a queued branch is already in the default branch |
| 6 | the queue is empty, so there is no train to plan |

**An already-merged branch stops the whole run, and that is the deliberate decision.**
Such an item did not fail, because the item is finished. A queue that still holds it is
a stale queue, and a plan built on one is wrong before anybody reads it. So the run
refuses with code 5, and it names every such branch. The human then takes those items
out of the queue. This seam writes no label, so it cannot do that itself.

**The throwaway checkout is the one risk, so this seam holds it tightly.** One checkout
under the system temp directory serves the whole run. `tempfile.TemporaryDirectory`
removes it on every path out, a raised exception included. The `checkout` key names it
for a reader, and the directory is already gone when that reader sees the path.

The checkout is a fresh repository that fetches the refs it needs, and never a
`git worktree` of the target. So the target's worktree list gains no entry that a
session can read as a worker worktree. This seam undoes each test-merge before the next
branch starts. So no half-merged state outlives one branch.

**`--repo` must be clean, because the plan reads committed state only.** The fetch
carries the refs, and not the uncommitted work beside them. A dirty repo gets a plan
that is silent about half of what is there. So code 3 stops the run instead.

**What this seam never touches.** No branch, no ref and no working tree in `--repo`: it
reads that repo and writes nothing back. And no tracker at all — it writes no label,
closes nothing and comments nowhere. Every tracker write belongs to the session, which
is the split the **Worker watch** already takes.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

EXIT_OK = 0
EXIT_ERROR = 1

# Code 2 stays with `argparse`, so a flag with a typo cannot land on one of the four
# refusals. That is why the refusals start at 3.
EXIT_DIRTY_REPO = 3
EXIT_MISSING_BRANCH = 4
EXIT_ALREADY_MERGED = 5
EXIT_EMPTY_QUEUE = 6

# Where the fetch puts the refs this run needs, inside the throwaway checkout. Its own
# namespace, so a branch called `main` or `origin/main` cannot shadow the ref the
# test-merge runs onto.
DEFAULT_REF = "refs/train/default"


class GitError(RuntimeError):
    """A git command failed. The CLI reports it and exits `EXIT_ERROR`."""


class Refusal(RuntimeError):
    """A refusal that carries its own exit code, and a message that names the cause."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# --- git --------------------------------------------------------------------


def git(repo, *args):
    """Run a git command in `repo` and return stdout stripped."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed in {repo}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def git_code(repo, *args):
    """Run a git command in `repo` and return its exit code, whatever that code is."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    return proc.returncode


def full_ref(repo, name):
    """The one ref `name` resolves to in `repo`, or an empty string if none does.

    A fully qualified name is what `build_checkout` needs for its fetch. It also
    settles what `--item` can carry: a local branch, a remote-tracking branch, or any
    other name that resolves to exactly one ref.
    """
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "rev-parse",
            "--symbolic-full-name",
            "--verify",
            "--quiet",
            name,
        ],
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def dirty_files(repo):
    """The uncommitted paths in `repo`, untracked files included.

    Split on the status code rather than at a fixed column, the same way
    `close_item.py` reads the same porcelain output.
    """
    lines = git(repo, "status", "--porcelain").splitlines()
    return [line.split(None, 1)[1] for line in lines if line.strip()]


# --- the refusals, before any checkout exists -------------------------------


def check_repo(repo, default_branch, queue):
    """Refuse on a fact `repo` alone can answer, in the order the codes hold.

    Each refusal happens before this seam creates the throwaway checkout. So a run
    that cannot produce a plan also creates nothing to remove.
    """
    if not queue:
        raise Refusal(
            EXIT_EMPTY_QUEUE,
            "the queue is empty, so there is no train to plan. Pass one "
            "--item NUMBER:BRANCH for each queued work item",
        )

    dirty = dirty_files(repo)
    if dirty:
        raise Refusal(
            EXIT_DIRTY_REPO,
            f"the repo {repo} holds uncommitted work: {', '.join(dirty)}. The plan "
            f"reads committed state only, so commit that work or stash it first",
        )

    missing = [
        name
        for name in [default_branch, *(branch for _, branch in queue)]
        if not full_ref(repo, name)
    ]
    if missing:
        raise Refusal(
            EXIT_MISSING_BRANCH,
            f"the repo {repo} has no branch {', or '.join(missing)}. Every queued "
            f"branch and the default branch must resolve to one ref there",
        )

    merged = [
        f"{branch} (#{item})"
        for item, branch in queue
        if git_code(repo, "merge-base", "--is-ancestor", branch, default_branch) == 0
    ]
    if merged:
        raise Refusal(
            EXIT_ALREADY_MERGED,
            f"{default_branch} already holds {', '.join(merged)}. Those items are "
            f"finished, so take them out of the queue and plan the train again",
        )


# --- the throwaway checkout -------------------------------------------------


def train_ref(item):
    """Where the fetch puts one queued item's branch inside the checkout."""
    return f"refs/train/item-{item}"


def build_checkout(root, repo, default_branch, queue):
    """Create the checkout under `root` and fetch every ref this run needs.

    A fresh repository, and never a `git worktree` of the target. A worktree puts an
    entry in the target's worktree list, and a session reads that list to find a
    worker's worktree. The fetch names each ref in full, so no mapping a clone makes
    of the target's branches can change the result.
    """
    checkout = Path(root) / "checkout"
    checkout.mkdir()
    git(checkout, "init", "--quiet")
    refspecs = [f"+{full_ref(repo, default_branch)}:{DEFAULT_REF}"]
    refspecs += [
        f"+{full_ref(repo, branch)}:{train_ref(item)}" for item, branch in queue
    ]
    git(checkout, "fetch", "--quiet", "--no-tags", str(repo), *refspecs)
    git(checkout, "checkout", "--quiet", "--detach", DEFAULT_REF)
    return checkout


def reset(checkout):
    """Put the checkout back on the default branch, whatever the last merge left."""
    git_code(checkout, "merge", "--abort")
    git(checkout, "reset", "--quiet", "--hard", DEFAULT_REF)
    git(checkout, "clean", "--quiet", "-fdx")


def test_merge(checkout, ref, branch, default_branch):
    """Merge `ref` onto the default branch, then undo it. Conflicted paths out.

    An empty list means the merge is clean. `git merge --abort` runs whatever the
    merge returned. This seam ignores the exit code of the abort, because a merge that
    never started has nothing to abort.

    A merge that fails and reports no conflicted path is not a park. Unrelated
    histories are one such case. This seam cannot name the repair for it, so it
    refuses rather than guess (ADR 0015).
    """
    code = git_code(checkout, "merge", "--no-commit", "--no-ff", ref)
    conflicts = []
    if code != 0:
        unmerged = git(checkout, "diff", "--name-only", "--diff-filter=U")
        conflicts = sorted(set(unmerged.splitlines()))
    git_code(checkout, "merge", "--abort")
    if code != 0 and not conflicts:
        raise GitError(
            f"the test-merge of {branch} onto {default_branch} failed, and reported no "
            f"conflicted path. So there is nothing to park it with"
        )
    return conflicts


def changed_files(checkout, ref):
    """The files `ref` changes against its merge base with the default branch."""
    diff = git(checkout, "diff", "--name-only", f"{DEFAULT_REF}...{ref}")
    return set(diff.splitlines())


def plan_merges(checkout, queue, default_branch):
    """Test-merge every queued branch onto the default branch, one at a time.

    Each branch starts from the same default branch, and never from the branch
    before it. So one park cannot hide the next one.
    """
    survivors = []
    parked = []
    for item, branch in queue:
        reset(checkout)
        ref = train_ref(item)
        conflicts = test_merge(checkout, ref, branch, default_branch)
        if conflicts:
            parked.append(
                {
                    "item": item,
                    "branch": branch,
                    "reason": f"the test-merge onto {default_branch} conflicts",
                    "paths": conflicts,
                }
            )
        else:
            survivors.append((item, branch, changed_files(checkout, ref)))
    return survivors, parked


# --- the order --------------------------------------------------------------


def rank(survivors):
    """Order the survivors by the rule `orchestrator/references/merge-train.md` holds.

    The tuple carries both keys of that rule, so one `sort()` applies them together.
    The overlap count runs over the survivors alone. A parked branch does not merge in
    this train, so an overlap with it changes no risk.
    """
    counted = []
    for item, branch, files in survivors:
        overlaps = sum(
            1 for other, _, theirs in survivors if other != item and files & theirs
        )
        counted.append((overlaps, item, branch))
    counted.sort()
    return [
        {"item": item, "branch": branch, "overlaps": overlaps}
        for overlaps, item, branch in counted
    ]


def build(repo, default_branch, queue):
    """The whole plan. Reads `repo`, writes nothing anywhere but the temp directory."""
    check_repo(repo, default_branch, queue)
    # The context manager is the removal. It runs on the way out of the block,
    # whichever way that is, so a raised exception leaves no checkout behind.
    with tempfile.TemporaryDirectory(prefix="merge-train-") as root:
        checkout = build_checkout(root, repo, default_branch, queue)
        survivors, parked = plan_merges(checkout, queue, default_branch)
    return {
        "generated_by": "scripts.merge_train",
        "mutates": "nothing",
        "repo": str(repo),
        "default_branch": default_branch,
        "checkout": str(checkout),
        "order": rank(survivors),
        "parked": parked,
    }


# --- CLI --------------------------------------------------------------------


def queued_item(text):
    """One `--item` value, as the pair `(number, branch)`.

    A git branch name can hold no colon, so the colon separates the two facts and
    needs no escape (`git check-ref-format`).
    """
    number, _, branch = str(text).partition(":")
    if not number.strip().isdigit() or not branch.strip():
        raise argparse.ArgumentTypeError(
            f"{text!r} is not a queued item. Write the work-item number, a colon and "
            f"the branch, as in 152:152-merge-train-seam"
        )
    return int(number.strip()), branch.strip()


def main(argv=None):
    parser = argparse.ArgumentParser(
        # The usage block prints the command that ran. So a reader copies a form
        # that resolves from their own working directory. The module form resolves
        # only at the plugin root
        # (orchestrator/docs/adr/0034-the-seam-invocation-carries-a-resolved-plugin-root.md).
        prog=f"python3 {Path(__file__).resolve()}",
        # The description is wrapped by hand, because the default formatter breaks a
        # long line wherever it runs out of room. That splits the reference file's
        # path across two lines, and a reader then copies half a path.
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Plan one merge train: the order the queued branches merge in, and the\n"
            "branches that park. It plans and it merges nothing, so there is no\n"
            "--execute flag.\n"
            "\n"
            "This command test-merges each queued branch onto the default branch. It\n"
            "does that in a throwaway checkout under the system temp directory, and\n"
            "it removes that checkout again on every path out. The plan is one JSON\n"
            "object on stdout.\n"
            "\n"
            "The ordering rule and the park rule live in\n"
            "orchestrator/references/merge-train.md."
        ),
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="the checkout that holds every queued branch (default: cwd). It must be "
        "clean, because the plan reads committed state only",
    )
    parser.add_argument(
        "--default-branch",
        default="main",
        help="the branch this command test-merges every queued branch onto "
        "(default: main)",
    )
    parser.add_argument(
        "--item",
        action="append",
        default=[],
        type=queued_item,
        metavar="NUMBER:BRANCH",
        help="one queued work item, as its number, a colon and its branch. Repeat the "
        "flag once per item in the queue. With no --item there is no train to plan",
    )
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args(argv)

    try:
        plan = build(Path(args.repo).resolve(), args.default_branch, args.item)
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    except GitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    print(json.dumps(plan, indent=args.indent))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
