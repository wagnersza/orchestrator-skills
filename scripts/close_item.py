#!/usr/bin/env python3
"""Run steps 4 to 8 of the **Close transaction**, in the one order they hold.

The order is the contract (ADR 0015). Steps 1 to 3 of the transaction need
judgement, so they stay prose. Steps 4 to 8 need none — they are two gates, a
pull, two tracker writes and a passed-in command — so this seam owns them and no
reader can put them in a different order.

**Plan mode is the default and mutates nothing.** It resolves every precondition
and emits JSON: the five ordered steps, each marked `todo`, `done`, `refused`,
`skipped` or `blocked`, the refusal reason, and the exit code an execute run
would use:

    python3 <plugin root>/scripts/close_item.py --issue 32 --pr 48 \\
        --repo /path/to/main/checkout --worktree /path/to/worktree \\
        --remove-label to-review

**Execute mode runs that same plan in order** and stops at the first refusal:

    python3 <plugin root>/scripts/close_item.py --issue 32 --pr 48 ... --execute

**Teardown needs `--execute --teardown` together**, so no single flag is
destructive and a bare invocation can only read:

    python3 <plugin root>/scripts/close_item.py ... --execute --teardown \\
        --teardown-command '<the command the tool reference gives, ids filled in>'

The five steps, and what each one does:

| Step | Behaviour |
|---|---|
| 4. PR merged? | refuse if not. Nothing else has run, so the item is untouched |
| 5. pull the merge | do it. A step, not a gate — behind is normal after a merge |
| 6. worktree clean? | refuse if dirty, and name the files. Nothing recovers that |
| 7. label and close | one step, so an item cannot close without its label moving |
| 8. remove the worktree | only with `--execute --teardown`, and then the card moves to `Done` |

**Step 7 writes no board column, and step 8 does.** The column write follows the teardown, so
a column of `Done` means the worktree is gone (ADR 0067). It rides on step 8 rather than
standing as a step of its own, because the transaction keeps the numbers 4 to 8.
`--board-project` and `--board-owner` carry the two coordinates on GitHub, and with either one
missing no card moves. **On GitLab a column is a scoped label and there are no coordinates**,
so the write always has one and the two flags are not read (ADR 0070). **A failed column
write is reported in the plan and it never fails the close**: every step has already run by
then. GitHub's own built-in **item closed to Done** workflow writes the same column for most
items, so this write is safe to repeat. GitLab ships no such workflow, so there this write is
the only thing that fills that column.

**`--abandon` is the other path, and an abandon is not a close.** A worker can die
before its first commit, and then no pull request exists and no merge can ever fire the
five steps above. So this seam takes a second path for that worktree:

    python3 <plugin root>/scripts/close_item.py --issue 316 \\
        --repo /path/to/main/checkout --worktree /path/to/worktree \\
        --remove-label in-progress \\
        --abandon 'the readiness gate refused the spawn' \\
        --execute --teardown --teardown-command '<op 12 && op 10>'

**It moves no work state.** The work item stays open, the abandon adds no label, and it
writes no start label, because only a human writes one. It removes the work-state label
the caller names, and it posts one comment that says why the worktree went.

**It proves there is nothing to lose before it removes anything.** Three proofs, each a
step of its own, so a refusal names which one failed:

| Step | Behaviour |
|---|---|
| 1. no commit | refuse where the branch is ahead of the base branch, and name the commits |
| 2. worktree clean? | refuse if dirty, and name the files |
| 3. no pull request | refuse where the branch already has an open one |
| 4. label and note | remove the work-state label, and post the reason. No close, and no label added |
| 5. remove the worktree | the same `--teardown-command`, so `hooks/refuse.py` needs no new exemption. **No card moves here**, because the item stays open |

That command removes the item's schedule as well as its worktree, because the caller
composes it as operation 12 then operation 10. So no tick survives the worktree it
watched, and this path needs no schedule flag of its own.

Two things this seam never learns, because each one turns it from a testable
part into a coupled one:

- **The workspace tool.** The teardown command arrives as `--teardown-command`.
  The caller reads it from `references/tools/<tool>.md` and substitutes the ids.
  So a new tool stays a Markdown change and no `orca` command is written here.
- **Which tracker it talks to.** `--tracker-cli`, `--tracker-host` and
  `--tracker-repo` name it, and the caller reads all three from the repo's tracker
  configuration. Every command then comes from the **Tracker adapter** in
  `scripts/tracker.py`, so this seam holds no tracker command and no CLI name
  (ADR 0040). **It holds no order of its own either.** Step 7 asks the adapter for
  the writes that close an item, and it runs them in the order the adapter gives
  them. Where a tracker closes an item with no reason flag, that order is the reason
  first and the close second (ADR 0056).

The exit code carries the outcome, so the caller reports the cause and parses no
prose. Every code holds one meaning, and the two paths share only the codes that carry
the same proof: 0 clean, 1 a step failed, 2 the PR is not merged, 3 the worktree is
dirty, 4 the branch has an open pull request, 5 the branch is ahead of the base branch,
and 64 a flag with a typo.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Both invocation forms reach the adapter: `python3 <plugin root>/scripts/close_item.py`
# puts `scripts/` on the path, and `python3 -m scripts.close_item` puts the repo root
# there (ADR 0034).
try:
    from .tracker import COLUMN_DONE, GH, GLAB, OPEN_STATES, Tracker, TrackerError
except ImportError:  # the type checker reads the package form above
    from tracker import (  # type: ignore[no-redef, import-not-found]
        COLUMN_DONE,
        GH,
        GLAB,
        OPEN_STATES,
        Tracker,
        TrackerError,
    )

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_PR_NOT_MERGED = 2
EXIT_WORKTREE_DIRTY = 3
# The two proofs only an abandon makes. Each code keeps one meaning, so neither one
# reuses a code above: a close refuses because a pull request is *not* merged, and an
# abandon refuses because a pull request exists at all.
EXIT_PR_OPEN = 4
EXIT_COMMITS_AHEAD = 5
# 64 is `EX_USAGE`, and it sits outside every outcome above: a flag with a typo is not a
# refusal, so no caller reads it as one.
EXIT_USAGE = 64

STATUS_DONE = "done"
STATUS_TODO = "todo"
STATUS_REFUSED = "refused"
STATUS_SKIPPED = "skipped"
STATUS_BLOCKED = "blocked"
STATUS_FAILED = "failed"


class GitError(RuntimeError):
    """A git command failed — reported into the plan, never raised past the CLI."""


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


def commits_ahead(worktree, branch):
    """The commits `worktree` holds that `branch` does not, newest first.

    One line per commit, so a refusal can name them. An empty list is the proof an
    abandon needs: a spawn that died before its first commit has nothing to lose.
    """
    return git(worktree, "log", "--oneline", f"{branch}..HEAD").splitlines()


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
    """Resolve every precondition and return the five ordered steps.

    Reads only. The statuses it writes are what an execute run acts on, so the
    order here is the order there — there is no second list of steps.
    """
    steps = []
    refusal = None
    checkout = Path(args.repo)
    branch = args.default_branch
    worktree = Path(args.worktree) if args.worktree else None

    # --- 4. the PR is merged, or nothing else happens.
    pr = tracker.pull_request(args.pr)
    pr_state = (pr.get("state") or "unknown").upper()
    merge_commit = pr.get("merge_commit") or ""
    read_pr = " ".join(tracker.pr_read_argv(args.pr))
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
            f"so the item keeps its review state."
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
                        6,
                        "worktree clean",
                        check_tree,
                        STATUS_DONE,
                        "the tree is clean",
                    )
                )

    # --- 7. the label and the close, as one step. An item that closes without its
    #        label moving cannot happen while they share a step. There is no card part:
    #        the card write comes after the teardown of step 8 (ADR 0067).
    parts = tracker_parts(args, tracker)
    if refusal:
        status, note = STATUS_BLOCKED, not_reached(refusal)
    elif all(part["status"] in (STATUS_DONE, STATUS_SKIPPED) for part in parts):
        status, note = STATUS_DONE, "the label and the item are already set"
    else:
        status, note = (
            STATUS_TODO,
            ("one step, so the label and the close always move together"),
        )
    steps.append(
        step(
            7,
            "tracker",
            " && ".join(part["command"] for part in parts) or "(nothing to write)",
            status,
            note,
            parts=parts,
        )
    )

    # --- 8. remove the worktree, and then move the card to `Done`. Two flags, or the
    #        teardown does not run, and the card write goes with it (ADR 0067).
    steps.append(
        teardown_step(8, args, worktree, refusal, card=card_target(args, tracker))
    )

    return steps, refusal


def card_target(args, tracker):
    """The column write that follows the teardown, or `None` where there is none.

    **The close writes `Done` after the teardown, so a column of `Done` means the worktree is
    gone** (ADR 0067). That is why the write rides on step 8 rather than standing as a step
    of its own: the transaction keeps the numbers 4 to 8.

    `board_project` and `board_owner` read through `getattr`, because
    `scripts/worker_state.py` builds its own namespace for a close. An older caller then
    reads as a caller that named no board, and no card moves.

    **On GitLab the two coordinates are not the condition, because that tracker has
    neither** (ADR 0070). A column there is a scoped label on the item. So the column name is
    the whole coordinate, and this write always has one. The adapter holds every other part of
    that difference. This is the one place a seam reads the CLI name, because the condition is
    what differs: no column name and no argv does.

    **The abandon reaches no column write.** Its work item stays open, so `Done` would be a
    lie about an item nobody closed. `build_abandon_plan` passes no card at all.
    """
    project = getattr(args, "board_project", 0)
    owner = getattr(args, "board_owner", "")
    if tracker.cli != GLAB and not (project and owner):
        return None
    return {
        "item": args.issue,
        "column": COLUMN_DONE,
        "project": project,
        "owner": owner,
    }


def card_write(card, tracker):
    """The card write that follows a teardown, as the lines it puts in the plan.

    **A failed card write is reported and it never fails the close.** Every step of the
    transaction has already run by this point, so a board that cannot be written leaves a
    stale card and nothing else (ADR 0067).

    The board's own **item closed to Done** workflow writes the same column for most items.
    The adapter reads the card before it writes, so this is safe to repeat and a card that
    already sits in `Done` costs no write.
    """
    if not card:
        return []
    try:
        wrote = tracker.card_write(
            card["item"], card["column"], card["project"], card["owner"]
        )
    except (TrackerError, OSError, json.JSONDecodeError) as exc:
        cause = " ".join(str(exc).split())
        return [f"the card write to {card['column']!r} failed: {cause}"]
    return [wrote] if wrote else []


def teardown_step(number, args, worktree, refusal, card=None):
    """The one step that destroys anything, and both paths reach the same one.

    The close reaches it as step 8 and the abandon as its step 5, so the number is an
    argument. Everything else is the same: two flags or it does not run, and the command
    is always the caller's own string. So `hooks/refuse.py` needs no second exemption for
    an abandon, because the abandon runs the very command the close runs.

    `card` is the card write that follows the command, and the close is the one path that
    passes one. It rides on this step because the write has to come after the teardown, and
    the transaction keeps the numbers 4 to 8 (ADR 0067).
    """
    command = args.teardown_command or "(no teardown command)"
    if refusal:
        status, note = STATUS_BLOCKED, not_reached(refusal)
    elif not args.teardown_command:
        status, note = (
            STATUS_SKIPPED,
            (
                "there is no --teardown-command, so nothing removes the worktree. The "
                "caller reads that command from its tool reference and passes it in"
            ),
        )
    elif not args.teardown:
        status, note = (
            STATUS_SKIPPED,
            (
                "teardown needs --execute and --teardown together, and --teardown is "
                "absent"
            ),
        )
    elif worktree is not None and not worktree.exists():
        status, note = STATUS_SKIPPED, f"there is no worktree at {worktree} any more"
    else:
        status, note = (
            STATUS_TODO,
            (
                "removes the worktree. This is the only step that destroys anything"
                + (f", and then moves the card to {card['column']!r}" if card else "")
            ),
        )
    return step(number, "teardown", command, status, note, card=card)


# --- the abandon ------------------------------------------------------------


def build_abandon_plan(args, tracker):
    """Resolve the three proofs of an empty worktree and return the five ordered steps.

    Reads only, the same as `build_plan`. **An abandon is not a close**: nothing here
    closes the item and nothing here writes a work state onto it. The proofs come first,
    and each one carries its own exit code, so a refusal names which proof failed.

    A worktree that is already gone is no error. The three proofs skip, the tracker step
    still runs, and teardown skips. So a part-applied abandon is resumable, the same way
    a part-applied close is.
    """
    steps = []
    refusal = None
    branch = args.default_branch
    worktree = Path(args.worktree)
    absent = f"there is no worktree at {worktree} any more"

    # --- 1. no commit ahead of the base branch. A commit is the proof that this
    #        worktree holds work, and work is not abandoned.
    read_commits = f"git -C {worktree} log --oneline {branch}..HEAD"
    if not worktree.exists():
        steps.append(step(1, "no commit", read_commits, STATUS_SKIPPED, absent))
    else:
        try:
            ahead = commits_ahead(worktree, branch)
        except GitError as exc:
            reason = (
                f"the read of the branch failed, so its commits are unproven: {exc}"
            )
            refusal = {"step": 1, "reason": reason, "exit_code": EXIT_ERROR}
            steps.append(step(1, "no commit", read_commits, STATUS_REFUSED, reason))
        else:
            if ahead:
                reason = (
                    f"the branch in {worktree} holds work that {branch} does not: "
                    f"{'; '.join(ahead)}. That is work to review, so open a pull request "
                    f"for it and let the merge close the item."
                )
                refusal = {
                    "step": 1,
                    "reason": reason,
                    "exit_code": EXIT_COMMITS_AHEAD,
                }
                steps.append(
                    step(
                        1,
                        "no commit",
                        read_commits,
                        STATUS_REFUSED,
                        reason,
                        commits_ahead=ahead,
                    )
                )
            else:
                steps.append(
                    step(
                        1,
                        "no commit",
                        read_commits,
                        STATUS_DONE,
                        f"the branch is not ahead of {branch}",
                    )
                )

    # --- 2. the worktree is clean. Uncommitted work has no reflog, so this is the
    #        one unrecoverable case on this path as well.
    check_tree = f"git -C {worktree} status --porcelain"
    if refusal:
        steps.append(
            step(2, "worktree clean", check_tree, STATUS_BLOCKED, not_reached(refusal))
        )
    elif not worktree.exists():
        steps.append(step(2, "worktree clean", check_tree, STATUS_SKIPPED, absent))
    else:
        try:
            dirty = dirty_files(worktree)
        except GitError as exc:
            reason = f"the read of the worktree failed, so its tree is unproven: {exc}"
            refusal = {"step": 2, "reason": reason, "exit_code": EXIT_ERROR}
            steps.append(step(2, "worktree clean", check_tree, STATUS_REFUSED, reason))
        else:
            if dirty:
                reason = (
                    f"the worktree {worktree} holds uncommitted work: "
                    f"{', '.join(dirty)}. Commit it or stash it first. Uncommitted "
                    f"work has no reflog."
                )
                refusal = {
                    "step": 2,
                    "reason": reason,
                    "exit_code": EXIT_WORKTREE_DIRTY,
                }
                steps.append(
                    step(
                        2,
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
                        2,
                        "worktree clean",
                        check_tree,
                        STATUS_DONE,
                        "the tree is clean",
                    )
                )

    # --- 3. the branch has no open pull request. Where one is open there is a review
    #        to finish, and the close path is the way out.
    head = current_branch(worktree) if worktree.exists() else ""
    read_prs = " ".join(tracker.pr_for_branch_argv(head)) if head else "(no branch)"
    if refusal:
        steps.append(
            step(3, "no pull request", read_prs, STATUS_BLOCKED, not_reached(refusal))
        )
    elif not worktree.exists():
        steps.append(step(3, "no pull request", read_prs, STATUS_SKIPPED, absent))
    elif not head:
        reason = (
            f"git cannot name the branch in {worktree}, so its pull requests are "
            f"unproven"
        )
        refusal = {"step": 3, "reason": reason, "exit_code": EXIT_ERROR}
        steps.append(step(3, "no pull request", read_prs, STATUS_REFUSED, reason))
    else:
        found = tracker.pull_request_for_branch(head)
        state = (found.get("state") or "").upper()
        if state in OPEN_STATES:
            reason = (
                f"the branch {head} already has pull request #{found['number']}, and it "
                f"is open. So there is a review to finish, and the merge is the way to "
                f"close this item."
            )
            refusal = {"step": 3, "reason": reason, "exit_code": EXIT_PR_OPEN}
            steps.append(
                step(
                    3,
                    "no pull request",
                    read_prs,
                    STATUS_REFUSED,
                    reason,
                    pull_request=found["number"],
                )
            )
        else:
            steps.append(
                step(
                    3,
                    "no pull request",
                    read_prs,
                    STATUS_DONE,
                    f"the branch {head} has no open pull request",
                )
            )

    # --- 4. the label and the note. **No close, and no label added**: the item stays
    #        open, and only a human writes a start label onto it.
    parts = abandon_parts(args, tracker)
    if refusal:
        status, note = STATUS_BLOCKED, not_reached(refusal)
    elif all(one["status"] in (STATUS_DONE, STATUS_SKIPPED) for one in parts):
        status, note = (
            STATUS_DONE,
            "the label and the reason are already as they should be",
        )
    else:
        status, note = (
            STATUS_TODO,
            "takes the work-state label off the item and records why. The item stays "
            "open, and no label is added",
        )
    steps.append(
        step(
            4,
            "tracker",
            " && ".join(one["command"] for one in parts) or "(nothing to write)",
            status,
            note,
            parts=parts,
        )
    )

    # --- 5. remove the worktree, through the command the close runs.
    steps.append(teardown_step(5, args, worktree, refusal))

    return steps, refusal


def abandon_parts(args, tracker):
    """The two writes an abandon makes: the label it removes, and the reason it posts.

    **There is no close part and no added label.** An abandon moves no work state, so
    this list holds neither, and the item is still open when the worktree is gone.
    """
    labels = tracker.issue(args.issue).get("labels") or []
    return [label_part(args, tracker, labels), abandon_note_part(args, tracker)]


def abandon_note_part(args, tracker):
    """The one comment an abandon posts, and a repeat of it posts nothing.

    The read of the comments is what makes the write repeatable, the same as the closing
    reason in `note_part`. This comment is the only trace an abandon leaves on the item,
    because the item keeps its state and its number.
    """
    argv = tracker.comment_argv(args.issue, args.abandon)
    _, comments = tracker.item_facts(args.issue)
    if any(args.abandon in (body or "") for body in comments):
        return part("note", argv, STATUS_DONE, "the reason is already on the item")
    return part(
        "note",
        argv,
        STATUS_TODO,
        "posts why this worktree went. The item stays open, so this comment is the "
        "whole record of the abandon",
    )


def tracker_parts(args, tracker):
    """The writes step 7 holds, each with its own status.

    Each part is idempotent, which is what makes a part-applied close resumable:
    a re-run finds the parts that landed already `done` and finishes the rest.

    The label is one part. The close is one or two more, and the adapter answers which
    writes those are and in what order (ADR 0056). So this seam iterates that answer. It
    learns neither that one tracker needs a second write nor where that write goes, and
    it names no tracker (ADR 0040).

    **No part of step 7 writes a board card.** The card write follows the teardown of step
    8, so a card in `Done` means the worktree is gone (ADR 0067).
    """
    issue = tracker.issue(args.issue)
    labels = issue.get("labels") or []
    closed = (issue.get("state") or "").upper() == "CLOSED"

    parts = [label_part(args, tracker, labels)]
    for name, argv in tracker.close_writes(args.issue, args.close_comment):
        parts.append(
            note_part(args, tracker, argv)
            if name == "note"
            else close_part(args, argv, closed)
        )
    return parts


def label_part(args, tracker, labels):
    """The label write, and whether it still has anything to do.

    Both paths ask for this one, because both move a label off an item and neither one
    holds a label string of its own. An abandon reaches it with an empty `--add-label`,
    which its own CLI check guarantees, so the same three cases below cover it.
    """
    argv = tracker.label_argv(args.issue, args.remove_label, args.add_label)
    if not (args.remove_label or args.add_label):
        return part("label", argv, STATUS_SKIPPED, "there is no label to move")
    if not any(name in labels for name in args.remove_label) and all(
        name in labels for name in args.add_label
    ):
        return part("label", argv, STATUS_DONE, "the labels are already correct")
    return part(
        "label",
        argv,
        STATUS_TODO,
        f"the item carries {', '.join(labels) or 'no work-state label'}",
    )


def close_part(args, argv, closed):
    """The write that closes the item."""
    return part(
        "close",
        argv,
        STATUS_DONE if closed else STATUS_TODO,
        f"issue #{args.issue} is already closed"
        if closed
        else f"closes issue #{args.issue}",
    )


def note_part(args, tracker, argv):
    """The closing reason as a write of its own.

    A repeat of this write posts a second note. So this part reads the comments on the
    item first, and it answers `done` where the reason is already there. That keeps
    every part of step 7 repeatable, which is what makes a part-applied close resumable.

    The adapter answers this write only where there is a reason to post and the close
    command takes none. So a tracker that closes with a reason costs no extra read.
    """
    _, comments = tracker.item_facts(args.issue)
    if any(args.close_comment in (body or "") for body in comments):
        return part(
            "note", argv, STATUS_DONE, "the closing reason is already on the item"
        )
    return part(
        "note",
        argv,
        STATUS_TODO,
        "posts the closing reason, before the close. This tracker closes an item with "
        "no reason flag, so the reason is its own write",
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
    """The whole plan, ready to read or to run.

    `abandon` reads through `getattr`, because `scripts/worker_state.py` builds its own
    namespace for a close and knows nothing about this path. An older caller then reads
    as a caller that asked for a close, which is what it asked for.
    """
    abandon = getattr(args, "abandon", "")
    steps, refusal = (
        build_abandon_plan(args, tracker) if abandon else build_plan(args, tracker)
    )
    return {
        "generated_by": "scripts.close_item",
        "path": "abandon" if abandon else "close",
        "mode": "execute" if args.execute else "plan",
        "mutates": "the steps marked todo below" if args.execute else "nothing",
        "issue": args.issue,
        "pr": args.pr,
        "repo": str(Path(args.repo)),
        "worktree": args.worktree or "",
        "teardown_requested": bool(args.teardown),
        "refused": refusal,
        "exit_code": refusal["exit_code"] if refusal else EXIT_OK,
        "ran": [],
        "steps": steps,
    }


# --- execute ----------------------------------------------------------------


def execute(plan, tracker):
    """Run the plan in order and stop at the first refusal.

    Nothing is re-derived here. The step that a refusal stopped keeps its status,
    and every step after it stays `blocked`, so the emitted plan says what ran.
    """
    for entry in plan["steps"]:
        if entry["status"] == STATUS_REFUSED:
            return plan["exit_code"]
        if entry["status"] != STATUS_TODO:
            continue
        try:
            plan["ran"] += run_step(entry, tracker)
        except (GitError, TrackerError, TeardownError) as exc:
            entry["status"] = STATUS_FAILED
            plan["error"] = str(exc)
            plan["exit_code"] = EXIT_ERROR
            return EXIT_ERROR
        entry["status"] = STATUS_DONE
    return plan["exit_code"]


class TeardownError(RuntimeError):
    """The teardown command exited non-zero."""


def run_step(entry, tracker):
    """Run one step and return the commands it ran.

    **The runner is chosen by the step's name, and never by its number.** The abandon
    path holds the same tracker step and the same teardown step under numbers of its own,
    so a number would send its teardown to the runner of the close's pull.
    """
    if entry["name"] == "pull":
        proc = subprocess.run(entry["argv"], capture_output=True, text=True)
        if proc.returncode != 0:
            raise GitError(f"{entry['command']} failed: {proc.stderr.strip()}")
        return [entry["command"]]
    if entry["name"] == "tracker":
        ran = []
        for item in entry["parts"]:
            if item["status"] != STATUS_TODO:
                continue
            tracker.write(item["argv"])
            item["status"] = STATUS_DONE
            ran.append(item["command"])
        return ran
    if entry["name"] == "teardown":
        # The command is a string the caller composed from its tool reference, so
        # a shell runs it. This is the only step that destroys anything, and it
        # is reached only behind --execute --teardown and every gate above.
        proc = subprocess.run(
            entry["command"], shell=True, capture_output=True, text=True
        )
        if proc.returncode != 0:
            raise TeardownError(
                f"the teardown command failed: {proc.stderr.strip() or proc.stdout.strip()}"
            )
        # The card write follows the teardown, so a card in `Done` means the worktree is
        # gone. It cannot fail the close: every step has already run (ADR 0067).
        return [entry["command"], *card_write(entry.get("card"), tracker)]
    raise TrackerError(f"step {entry['step']} has no runner")


# --- CLI --------------------------------------------------------------------


class UsageExitParser(argparse.ArgumentParser):
    """A parser whose usage errors exit 64, outside the outcome codes above.

    A refusal is a refusal, so a flag with a typo must not land on one of those codes.
    The default is 2, which is the code a close uses for an unmerged pull request.
    """

    def exit(self, status=0, message=None):
        if message:
            self._print_message(message, sys.stderr)
        sys.exit(EXIT_USAGE if status else status)


def main(argv=None):
    parser = UsageExitParser(
        # The usage block prints the command that ran. So a reader copies a form
        # that resolves from their own working directory. The module form resolves
        # only at the plugin root
        # (orchestrator/docs/adr/0034-the-seam-invocation-carries-a-resolved-plugin-root.md).
        prog=f"python3 {Path(__file__).resolve()}",
        description=(
            "Run steps 4 to 8 of the close transaction, in the one order they hold. "
            "The steps are the PR gate, the pull into the local default branch, the "
            "clean-tree gate, the tracker writes, and teardown. The default prints "
            "the plan as JSON and mutates nothing. --execute runs the plan and stops "
            "at the first refusal. Teardown needs --execute and --teardown together. "
            "--abandon takes the other path: it proves the worktree holds nothing, "
            "removes it, and leaves the work item open."
        ),
    )
    parser.add_argument("--issue", required=True, type=int, help="the work item number")
    parser.add_argument(
        "--pr",
        type=int,
        help="the pull request that must be merged. Where a tracker numbers its merge "
        "requests in a sequence of their own, this is that number and not the item's. "
        "Required for a close, and not permitted with --abandon",
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
        help="the item's worktree. Step 6 reads it for uncommitted work, and step 8 "
        "removes it. If you do not give it, both steps do nothing",
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
    parser.add_argument(
        "--close-comment",
        default="",
        metavar="TEXT",
        help="the reason to record on the item as it closes. With no reason, this seam "
        "posts nothing. Where the tracker closes an item with a reason flag, the close "
        "command carries the text. Where it does not, step 7 posts the reason first and "
        "closes second",
    )
    parser.add_argument(
        "--tracker-cli",
        default=GH,
        choices=(GH, GLAB),
        help="which CLI runs every tracker read and write. The caller resolves it from "
        "the repo's tracker configuration. This seam passes the name to the tracker "
        "adapter, which holds every command, so this seam names no tracker",
    )
    parser.add_argument(
        "--tracker-host",
        default="",
        metavar="HOST",
        help="the tracker host, for a server the CLI does not reach by default. Each "
        "command carries it in the place that command needs. With no host, every "
        "command goes to the CLI's own default server",
    )
    parser.add_argument(
        "--tracker-repo",
        default="",
        metavar="OWNER/NAME",
        help="the tracker project that holds the item and its pull request. --repo is "
        "the checkout on disk, so the tracker project takes an argument of its own. "
        "With no value, every command goes to the clone the working directory holds",
    )
    # The two board coordinates. Step 7 still writes no card: the write comes after the
    # teardown of step 8, so a card in `Done` means the worktree is gone (ADR 0067).
    parser.add_argument(
        "--board-project",
        default=0,
        type=int,
        metavar="NUMBER",
        help="the project number of the board that holds the card. Step 8 moves that card "
        "to Done after the teardown, so a card in Done means the worktree is gone. The "
        "caller reads it from the Project board section of docs/agents/issue-tracker.md. "
        "With this flag missing no card moves, and the close is unchanged. An --abandon "
        "moves no card whatever this flag says, because its work item stays open",
    )
    parser.add_argument(
        "--board-owner",
        default="",
        metavar="OWNER",
        help="the owner the board belongs to, from the same section. With this flag "
        "missing no card moves",
    )
    parser.add_argument(
        "--teardown-command",
        help="the command that removes the worktree, with the ids already in it. "
        "The caller reads it from its tool reference, so this seam holds no "
        "command of its own",
    )
    parser.add_argument(
        "--abandon",
        default="",
        metavar="REASON",
        help="take the abandon path instead of the close path, and record REASON as "
        "the comment that says why. The abandon needs no pull request and no merge. It "
        "refuses unless the branch is not ahead of the base branch, the tree is clean, "
        "and the branch has no open pull request. The work item stays open",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="run the plan instead of printing it. The run stops at the first refusal",
    )
    parser.add_argument(
        "--teardown",
        action="store_true",
        help="permit step 8. Step 8 runs only with --execute as well, so no single "
        "flag destroys a worktree",
    )
    parser.add_argument(
        "--gh-fixture",
        help="JSON that stands in for the tracker reads, so a plan needs no network and "
        "no login (used by the tests). One format for either --tracker-cli, and it is "
        "the one scripts/tracker.py documents. scripts/worker_state.py reads the same "
        "one",
    )
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args(argv)

    # The two paths ask for different flags, and a flag from the wrong one is a typo
    # rather than a refusal. So each case below exits 64 and mutates nothing.
    if args.abandon:
        for flag, value in (
            ("--pr", args.pr),
            ("--add-label", args.add_label),
            ("--close-comment", args.close_comment),
        ):
            if value:
                parser.error(
                    f"--abandon takes no {flag}. An abandon needs no pull request, it "
                    f"adds no label, and it closes nothing"
                )
        if not args.worktree:
            parser.error(
                "--abandon needs --worktree, because the worktree is the thing it "
                "removes"
            )
    elif args.pr is None:
        parser.error(
            "--pr is required, because a merged pull request is what authorises a "
            "close. Use --abandon for a worktree that opened none"
        )

    tracker = Tracker(
        args.tracker_cli, args.tracker_host, args.tracker_repo, args.gh_fixture
    )
    try:
        plan = build(args, tracker)
    except (GitError, TrackerError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    code = execute(plan, tracker) if args.execute else plan["exit_code"]
    print(json.dumps(plan, indent=args.indent))
    return code


if __name__ == "__main__":
    sys.exit(main())
