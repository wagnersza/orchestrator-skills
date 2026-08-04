#!/usr/bin/env python3
"""Plan steps 4 to 7 of the **Close transaction**, in the one order they hold.

The order is the contract (ADR 0015). Steps 1 to 3 of the transaction need
judgement, so they stay prose. Steps 4 to 8 need none — they are two gates, a
pull, two tracker writes and a passed-in command — so this seam owns them and no
reader can put them in a different order.

**This mode is the default and it mutates nothing.** It resolves every
precondition and emits JSON: the ordered steps, each marked `todo`, `done`,
`refused`, `skipped` or `blocked`, the refusal reason, and the exit code an
execute run would use:

    python3 -m scripts.close_item --issue 32 --pr 48 \\
        --repo /path/to/main/checkout --worktree /path/to/worktree \\
        --remove-label to-review

The steps, and what each one does:

| Step | Behaviour |
|---|---|
| 4. PR merged? | refuse if not. Nothing else has run, so the item is untouched |
| 5. pull the merge | do it. A step, not a gate — behind is normal after a merge |
| 6. worktree clean? | refuse if dirty, and name the files. Nothing recovers that |
| 7. label, close, card | one step, so a label cannot move without its card |

Two things this seam never learns, because each one turns it from a testable part
into a coupled one:

- **The project board.** The coordinates arrive as arguments. This seam reads no
  Markdown and holds no board.
- **Any tracker but GitHub.** See the `ponytail:` comment on `GH` below.

The exit code carries the outcome, so the caller reports the cause and parses no
prose: 0 clean, 2 the PR is not merged, 3 the worktree is dirty, 1 a read failed.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_PR_NOT_MERGED = 2
EXIT_WORKTREE_DIRTY = 3

# ponytail: `gh` is hardcoded, so this seam speaks to GitHub and to no other
# tracker. One tracker does not pay for an abstraction. Whoever first needs
# GitLab has two upgrade paths, and both stop at `Tracker`: swap the command
# builders in that class for their `glab` equivalents, or put a `--tracker-cli`
# argument in front of them. The gates, the plan and the order above them do not
# change, because none of them knows which CLI ran.
GH = "gh"

STATUS_DONE = "done"
STATUS_TODO = "todo"
STATUS_REFUSED = "refused"
STATUS_SKIPPED = "skipped"
STATUS_BLOCKED = "blocked"

BOARD_ARGS = (
    "project_number",
    "project_owner",
    "project_id",
    "status_field_id",
    "done_option_id",
)


class GitError(RuntimeError):
    """A git command failed — reported into the plan, never raised past the CLI."""


class GhError(RuntimeError):
    """A tracker command failed — reported into the plan, not raised past the CLI."""


# --- git --------------------------------------------------------------------


def git(repo, *args):
    """Run a git command in `repo` and return stdout stripped."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed in {repo}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def current_branch(repo):
    """The branch `repo` has checked out, or an empty string if git cannot say."""
    try:
        return git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    except GitError:
        return ""


def contains(repo, sha, branch):
    """Whether `branch` in `repo` already has `sha`. False if the object is absent."""
    if not sha:
        return False
    try:
        git(repo, "merge-base", "--is-ancestor", sha, branch)
        return True
    except GitError:
        return False


def dirty_files(worktree):
    """The uncommitted paths in `worktree`, untracked files included.

    Split on the status code rather than at a fixed column: an unstaged edit
    reports a leading space, and `git()` has already stripped the output.
    """
    lines = git(worktree, "status", "--porcelain").splitlines()
    return [line.split(None, 1)[1] for line in lines if line.strip()]


# --- the tracker ------------------------------------------------------------


class Tracker:
    """The tracker reads this seam needs, or a fixture in their place.

    A fixture file (`--gh-fixture`) is how the tests plan a close with no network
    and no `gh` login, the same way `fork_state.py` plans a bootstrap. Each key
    holds what the matching `gh` read returns, keyed by number:

        {"pull_requests": {"48": {"state": "MERGED", "mergeCommit": {"oid": "a1"}}},
         "issues": {"32": {"state": "OPEN", "labels": ["to-review"]}},
         "project_items": {"32": "PVTI_x"}}

    A number absent from a key reads as an empty record.
    """

    def __init__(self, fixture_path=None):
        self.path = Path(fixture_path) if fixture_path else None
        self.fixture = json.loads(self.path.read_text()) if self.path else None

    def _record(self, key, number):
        return (self.fixture.get(key) or {}).get(str(number)) or {}

    def pull_request(self, number):
        """The PR's state and its merge commit."""
        if self.fixture is not None:
            return self._record("pull_requests", number)
        return gh_json("pr", "view", str(number), "--json", "state,mergeCommit")

    def issue(self, number):
        """The issue's state and its label names."""
        if self.fixture is not None:
            return self._record("issues", number)
        data = gh_json("issue", "view", str(number), "--json", "state,labels")
        return {
            "state": data.get("state"),
            "labels": [label["name"] for label in data.get("labels") or []],
        }

    def board_item(self, number, project_number, owner):
        """The board item id for an issue, or an empty string if it has no card."""
        if self.fixture is not None:
            return (self.fixture.get("project_items") or {}).get(str(number), "")
        return gh_text(
            "project",
            "item-list",
            str(project_number),
            "--owner",
            owner,
            "--format",
            "json",
            "--limit",
            "100",
            "--jq",
            f".items[] | select(.content.number=={number}) | .id",
        )


def gh_json(*args):
    """Run a `gh` read and parse its JSON."""
    return json.loads(gh_text(*args) or "{}")


def gh_text(*args):
    """Run a `gh` read and return stdout stripped."""
    proc = subprocess.run([GH, *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise GhError(f"{GH} {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


# --- the plan ---------------------------------------------------------------


def step(number, name, command, status, note, **extra):
    """One ordered step: what it runs, whether it is needed, and why."""
    return {
        "step": number,
        "name": name,
        "command": command,
        "status": status,
        "note": note,
        **extra,
    }


def not_reached(refusal):
    return f"not reached, because step {refusal['step']} refused"


def build_plan(args, tracker):
    """Resolve every precondition and return the ordered steps.

    Reads only. The order here is the order the steps hold, and there is no
    second list of them anywhere.
    """
    steps = []
    refusal = None
    checkout = Path(args.repo)
    branch = args.default_branch
    worktree = Path(args.worktree) if args.worktree else None

    # --- 4. the PR is merged, or nothing else happens.
    pr = tracker.pull_request(args.pr)
    pr_state = (pr.get("state") or "unknown").upper()
    merge_commit = (pr.get("mergeCommit") or {}).get("oid") or ""
    read_pr = f"{GH} pr view {args.pr} --json state,mergeCommit"
    if pr_state == "MERGED":
        steps.append(
            step(
                4,
                "pr merged",
                read_pr,
                STATUS_DONE,
                f"PR #{args.pr} is merged"
                + (f" at {merge_commit[:7]}" if merge_commit else ""),
                merge_commit=merge_commit,
            )
        )
    else:
        reason = (
            f"PR #{args.pr} is {pr_state.lower()}, and not merged. Nothing else ran, "
            f"so the item keeps its review state and its card keeps `In review`."
        )
        refusal = {"step": 4, "reason": reason, "exit_code": EXIT_PR_NOT_MERGED}
        steps.append(step(4, "pr merged", read_pr, STATUS_REFUSED, reason))

    # --- 5. pull the merge into the local default branch. A step, not a gate.
    #
    # A checkout on a different branch gets a ref update instead of a pull. A
    # pull there would merge the default branch into the branch in front of the
    # maintainer, which is not what step 5 asks for.
    checked_out = current_branch(checkout)
    if checked_out == branch:
        pull = ["git", "-C", str(checkout), "pull", "--ff-only", "origin", branch]
        pull_note = f"moves {branch} to the merge"
    else:
        pull = ["git", "-C", str(checkout), "fetch", "origin", f"{branch}:{branch}"]
        pull_note = (
            f"the checkout is on {checked_out or 'no branch'}, so this moves the "
            f"{branch} ref and leaves the working tree as it is"
        )
    if refusal:
        status, note = STATUS_BLOCKED, not_reached(refusal)
    elif contains(checkout, merge_commit, branch):
        status, note = STATUS_DONE, f"{branch} already has the merge {merge_commit[:7]}"
    else:
        status, note = STATUS_TODO, pull_note
    steps.append(step(5, "pull", " ".join(pull), status, note, argv=pull))

    # --- 6. the worktree is clean, or nothing is removed. Uncommitted work has
    #        no reflog, so this is the one unrecoverable case in the flow.
    check_tree = f"git -C {worktree or '<worktree>'} status --porcelain"
    if refusal:
        steps.append(
            step(6, "worktree clean", check_tree, STATUS_BLOCKED, not_reached(refusal))
        )
    elif worktree is None or not worktree.exists():
        steps.append(
            step(
                6,
                "worktree clean",
                check_tree,
                STATUS_SKIPPED,
                "there is no worktree to check"
                + (f" at {worktree}" if worktree else ", because none was given"),
            )
        )
    else:
        try:
            dirty = dirty_files(worktree)
        except GitError as exc:
            reason = f"the read of the worktree failed, so its tree is unproven: {exc}"
            refusal = {"step": 6, "reason": reason, "exit_code": EXIT_ERROR}
            steps.append(step(6, "worktree clean", check_tree, STATUS_REFUSED, reason))
        else:
            if dirty:
                reason = (
                    f"the worktree {worktree} holds uncommitted work: "
                    f"{', '.join(dirty)}. Commit it or stash it first. Uncommitted "
                    f"work has no reflog."
                )
                refusal = {
                    "step": 6,
                    "reason": reason,
                    "exit_code": EXIT_WORKTREE_DIRTY,
                }
                steps.append(
                    step(
                        6,
                        "worktree clean",
                        check_tree,
                        STATUS_REFUSED,
                        reason,
                        dirty_files=dirty,
                    )
                )
            else:
                steps.append(
                    step(
                        6, "worktree clean", check_tree, STATUS_DONE, "the tree is clean"
                    )
                )

    # --- 7. the label, the close and the card, as one step. A label that moves
    #        without its card cannot happen while they share a step.
    parts = tracker_parts(args, tracker)
    if refusal:
        status, note = STATUS_BLOCKED, not_reached(refusal)
    else:
        status, note = STATUS_TODO, (
            "one step, so the label and the card always move together"
        )
    steps.append(
        step(
            7,
            "tracker",
            " && ".join(part["command"] for part in parts),
            status,
            note,
            parts=parts,
        )
    )

    return steps, refusal


def tracker_parts(args, tracker):
    """The three writes step 7 holds, each with its own command."""
    flags = []
    for name in args.remove_label:
        flags += ["--remove-label", name]
    for name in args.add_label:
        flags += ["--add-label", name]
    label = part(
        "label",
        [GH, "issue", "edit", str(args.issue), *flags],
        STATUS_TODO,
        f"the item carries "
        f"{', '.join(tracker.issue(args.issue).get('labels') or []) or 'no work-state label'}",
    )
    close = part(
        "close",
        [GH, "issue", "close", str(args.issue)],
        STATUS_TODO,
        f"closes issue #{args.issue}",
    )
    return [label, close, card_part(args, tracker)]


def card_part(args, tracker):
    """The board write, built from the coordinates the caller passed in."""
    item = tracker.board_item(args.issue, args.project_number, args.project_owner)
    argv = [
        GH,
        "project",
        "item-edit",
        "--id",
        item,
        "--project-id",
        args.project_id,
        "--field-id",
        args.status_field_id,
        "--single-select-option-id",
        args.done_option_id,
    ]
    return part(
        "card",
        argv,
        STATUS_TODO,
        "writes the card. A repeat of this write changes nothing, so a part-applied "
        "close is resumable",
    )


def part(name, argv, status, note):
    """One write inside step 7."""
    return {
        "name": name,
        "command": " ".join(argv) or "(nothing to write)",
        "status": status,
        "note": note,
        "argv": argv,
    }


def build(args, tracker):
    """The whole plan, ready to read."""
    steps, refusal = build_plan(args, tracker)
    return {
        "generated_by": "scripts.close_item",
        "mode": "plan",
        "mutates": "nothing",
        "issue": args.issue,
        "pr": args.pr,
        "repo": str(Path(args.repo)),
        "worktree": args.worktree or "",
        "refused": refusal,
        "exit_code": refusal["exit_code"] if refusal else EXIT_OK,
        "steps": steps,
    }


# --- CLI --------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.close_item",
        description=(
            "Plan steps 4 to 7 of the close transaction, in the one order they hold. "
            "The steps are the PR gate, the pull into the local default branch, the "
            "clean-tree gate, and the tracker writes. This prints the plan as JSON "
            "and mutates nothing."
        ),
    )
    parser.add_argument("--issue", required=True, type=int, help="the work item number")
    parser.add_argument(
        "--pr", required=True, type=int, help="the pull request that must be merged"
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="the main checkout that receives the merge (default: cwd)",
    )
    parser.add_argument(
        "--default-branch",
        default="main",
        help="the branch that the merge landed on (default: main)",
    )
    parser.add_argument(
        "--worktree",
        help="the item's worktree. Step 6 reads it for uncommitted work. If you do "
        "not give it, step 6 does nothing",
    )
    parser.add_argument(
        "--remove-label",
        action="append",
        default=[],
        metavar="LABEL",
        help="a label to remove from the item. Repeatable",
    )
    parser.add_argument(
        "--add-label",
        action="append",
        default=[],
        metavar="LABEL",
        help="a label to add to the item. Repeatable",
    )
    parser.add_argument("--project-number", help="the number of the board")
    parser.add_argument("--project-owner", help="the owner of the board")
    parser.add_argument("--project-id", help="the node id of the board")
    parser.add_argument(
        "--status-field-id", help="the id of the status field on the board"
    )
    parser.add_argument(
        "--done-option-id", help="the id of the done option in that status field"
    )
    parser.add_argument(
        "--gh-fixture",
        help="JSON that stands in for the tracker reads, so a plan needs no network "
        "(used by the tests)",
    )
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args(argv)

    try:
        plan = build(args, Tracker(args.gh_fixture))
    except (GitError, GhError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    print(json.dumps(plan, indent=args.indent))
    return plan["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
