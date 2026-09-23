#!/usr/bin/env python3
"""Behaviour tests for the close seam: fixture state in, JSON plan out.

Every case runs `python3 -m scripts.close_item` as a subprocess against local git
repos built in a temp directory, and asserts on the emitted plan and on what was
mutated — never on a helper's return value. No network, no GitHub, no mocking
framework and no agent runs: `--gh-fixture` stands in for every tracker read, so
`gh` is never called. The one exception is the failed card write, which a fixture
cannot answer: that case puts a `gh` that exits non-zero on `PATH` and reads the line
the plan carries. `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` point at
`os.devnull`, so the developer's git config cannot leak into a fixture.

The teardown command is a passed-in string, which is what makes the destructive
path testable: every case here passes a command that creates a marker file, and
then asserts the file exists only when it should. The single most valuable
assertion in the file is that the marker is absent — see
`test_a_refused_gate_runs_no_teardown_and_names_the_reason`.

The last group covers the abandon path, which removes a worktree that never opened a
pull request. Its cases read the same fixture and the same marker, because an abandon
runs the very teardown command a close runs. What they assert on top of that is what an
abandon must never do: close the item, add a label, or remove a worktree that still
holds work.

    python3 -m pytest scripts/ -q
    python3 -m unittest discover -s scripts -t . -q     # fallback, no pytest
"""

import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# One case imports the seam rather than running it: a fixture write never fails, so the
# failed card write has no answer through the command line (ADR 0067). Every other case
# runs the seam as a subprocess.
from scripts import close_item
from scripts.tracker import Tracker

REPO_ROOT = Path(__file__).resolve().parents[1]

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.com",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}

ISSUE = 32
PR = 48
REVIEW_LABEL = "to-review"

# The label an abandoned worktree's item still carries, and the label only a human
# writes. An abandon takes the first one off and never writes the second.
START_LABEL = "in-progress"
READY_LABEL = "ready-for-agent"

# The second tracker, and the two values its commands need. `--repo` names the checkout
# on disk, so the tracker project has an argument of its own.
HOST = "git.example.com"
PROJECT = "team/thing"
GLAB = ["--tracker-cli", "glab", "--tracker-host", HOST, "--tracker-repo", PROJECT]

# A closing reason with no space in it, so one write is one line in the write log. The
# abandon reason is the same shape, for the same reason.
REASON = "merged-and-closed"
ABANDON_REASON = "the-readiness-gate-refused-the-spawn"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_PR_NOT_MERGED = 2
EXIT_WORKTREE_DIRTY = 3
EXIT_PR_OPEN = 4
EXIT_COMMITS_AHEAD = 5
EXIT_USAGE = 64


def git(cwd, *args):
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        env=GIT_ENV,
    )


def rev(cwd, ref):
    return subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", ref],
        check=True,
        capture_output=True,
        text=True,
        env=GIT_ENV,
    ).stdout.strip()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class CloseItemTestCase(unittest.TestCase):
    """An origin holding the merge, a main checkout behind it, and a worktree.

    The fixture is the state a real close starts from: the PR is merged on the
    origin, the local default branch has not caught up, and the item's worktree
    still exists because teardown has not run.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        # --- Origin: the base commit, then the commit the merge landed.
        self.origin = self.root / "origin"
        self.origin.mkdir()
        git(self.origin, "init", "-q", "-b", "main")
        write(self.origin / "README.md", "# fixture\n")
        git(self.origin, "add", "-A")
        git(self.origin, "commit", "-qm", "base")
        self.base = rev(self.origin, "main")

        # --- Main checkout, cloned before the merge, so it is behind.
        self.checkout = self.root / "checkout"
        subprocess.run(
            ["git", "clone", "-q", str(self.origin), str(self.checkout)],
            check=True,
            capture_output=True,
            env=GIT_ENV,
        )

        write(self.origin / "feature.md", "the merged work\n")
        git(self.origin, "add", "-A")
        git(self.origin, "commit", "-qm", "merge the item's PR")
        self.merge_commit = rev(self.origin, "main")

        # --- The item's worktree: a clean clone on its own branch.
        self.worktree = self.root / "worktree"
        subprocess.run(
            ["git", "clone", "-q", str(self.origin), str(self.worktree)],
            check=True,
            capture_output=True,
            env=GIT_ENV,
        )
        self.branch = f"{ISSUE}-close-item-seam"
        git(self.worktree, "checkout", "-qb", self.branch)

        self.marker = self.root / "teardown-ran"
        self.write_fixture()

    # --- fixture helpers ----------------------------------------------------

    def write_fixture(
        self,
        pr_state="MERGED",
        issue_state="OPEN",
        labels=(REVIEW_LABEL,),
        comments=(),
        pr_head="",
    ):
        """Stand in for the two tracker reads: the PR and the issue.

        One record for this item and one for its PR, in the one format
        `scripts/tracker.py` documents. `scripts/worker_state.py` reads the same one.
        There is no card key, because no read here asks for one: the close writes a card
        and reads none of its own (ADR 0067).

        `pr_head` is the branch the PR was opened from, and it is what the abandon's
        third proof matches. The default is empty, so the default fixture is a branch
        with no pull request of its own.
        """
        self.fixture = self.root / "gh.json"
        item = {"state": issue_state, "labels": list(labels)}
        if comments:
            item["comments"] = list(comments)
        data = {
            "items": {str(ISSUE): item},
            "pull_requests": {
                str(PR): {
                    "state": pr_state,
                    "merge_commit": self.merge_commit if pr_state == "MERGED" else "",
                    "head": pr_head,
                }
            },
        }
        self.fixture.write_text(json.dumps(data))
        self.writes = self.root / "gh.json.writes"

    def teardown_command(self):
        """A teardown command that leaves proof it ran, and destroys nothing."""
        return f"touch {self.marker}"

    def seam(self, argv, expect=0):
        """Run the seam once and return the finished process.

        The one runner, so a usage error can be read as well as a plan: exit 64 prints
        no plan at all, and the message on standard error is the whole answer.
        """
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.close_item", *argv],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=GIT_ENV,
        )
        self.assertEqual(proc.returncode, expect, f"stderr: {proc.stderr}")
        return proc

    def close(self, *extra, worktree=True, teardown_command=True, expect=0):
        """Run the close path and return the parsed plan."""
        argv = [
            "--issue",
            str(ISSUE),
            "--pr",
            str(PR),
            "--repo",
            str(self.checkout),
            "--remove-label",
            REVIEW_LABEL,
            "--gh-fixture",
            str(self.fixture),
        ]
        if worktree:
            argv += ["--worktree", str(self.worktree)]
        if teardown_command:
            argv += ["--teardown-command", self.teardown_command()]
        return json.loads(self.seam([*argv, *extra], expect).stdout)

    def abandon_argv(self, worktree=True, teardown_command=True):
        """The abandon invocation: no `--pr`, and a reason instead of a merge."""
        argv = [
            "--issue",
            str(ISSUE),
            "--repo",
            str(self.checkout),
            "--remove-label",
            START_LABEL,
            "--abandon",
            ABANDON_REASON,
            "--gh-fixture",
            str(self.fixture),
        ]
        if worktree:
            argv += ["--worktree", str(self.worktree)]
        if teardown_command:
            argv += ["--teardown-command", self.teardown_command()]
        return argv

    def abandon(self, *extra, worktree=True, teardown_command=True, expect=0):
        """Run the abandon path and return the parsed plan."""
        argv = self.abandon_argv(worktree, teardown_command)
        return json.loads(self.seam([*argv, *extra], expect).stdout)

    def step(self, plan, number):
        for entry in plan["steps"]:
            if entry["step"] == number:
                return entry
        self.fail(f"step {number} missing: {[s['step'] for s in plan['steps']]}")

    def part(self, plan, name, number=7):
        """One write inside the tracker step. It is step 7 of a close, and 4 of an
        abandon."""
        for entry in self.step(plan, number)["parts"]:
            if entry["name"] == name:
                return entry
        self.fail(f"part {name} missing")

    def statuses(self, plan):
        return [entry["status"] for entry in plan["steps"]]

    def tracker_writes(self):
        return self.writes.read_text().splitlines() if self.writes.exists() else []

    def assertNothingMutated(self, before):
        """The default invocation touched no branch, no tracker and no worktree."""
        self.assertEqual(before, self.disk_state())
        self.assertEqual(self.tracker_writes(), [])
        self.assertFalse(self.marker.exists())

    def disk_state(self):
        return (
            rev(self.checkout, "main"),
            sorted(str(p) for p in self.root.rglob("*")),
        )

    # --- plan mode: the gates, with no mutation -----------------------------

    def test_merged_clean_and_behind_plans_the_pull_and_exits_clean(self):
        """Every gate passes and step 5 is the one thing left to do."""
        before = self.disk_state()
        plan = self.close()

        self.assertEqual(plan["mode"], "plan")
        self.assertEqual(plan["mutates"], "nothing")
        self.assertIsNone(plan["refused"])
        self.assertEqual(plan["exit_code"], EXIT_OK)
        self.assertEqual([s["step"] for s in plan["steps"]], [4, 5, 6, 7, 8])
        self.assertEqual(
            [s["name"] for s in plan["steps"]],
            ["pr merged", "pull", "worktree clean", "tracker", "teardown"],
        )
        self.assertEqual(self.step(plan, 4)["status"], "done")
        self.assertEqual(self.step(plan, 4)["merge_commit"], self.merge_commit)
        # The local default branch is behind, which is normal after a merge — so
        # the pull is planned, and no gate refused over it.
        self.assertEqual(self.step(plan, 5)["status"], "todo")
        self.assertNotEqual(rev(self.checkout, "main"), self.merge_commit)
        self.assertEqual(self.step(plan, 6)["status"], "done")
        self.assertEqual(self.step(plan, 7)["status"], "todo")
        self.assertEqual(self.step(plan, 8)["status"], "skipped")
        self.assertIn("--teardown", self.step(plan, 8)["note"])

        self.assertNothingMutated(before)

    def test_an_unmerged_pr_refuses_and_the_tracker_steps_are_never_reached(self):
        """The item stays where it is, so nothing has to be undone."""
        self.write_fixture(pr_state="OPEN")
        before = self.disk_state()
        plan = self.close(expect=EXIT_PR_NOT_MERGED)

        self.assertEqual(self.step(plan, 4)["status"], "refused")
        self.assertEqual(plan["refused"]["step"], 4)
        self.assertIn("not merged", plan["refused"]["reason"])
        self.assertIn("review state", plan["refused"]["reason"])
        self.assertEqual(plan["exit_code"], EXIT_PR_NOT_MERGED)
        # Everything after the refusal is blocked, and each one says why.
        self.assertEqual(self.statuses(plan), ["refused"] + ["blocked"] * 4)
        for number in (5, 6, 7, 8):
            self.assertIn("step 4 refused", self.step(plan, number)["note"])

        self.assertNothingMutated(before)

    def test_a_dirty_worktree_refuses_and_names_the_files(self):
        """Uncommitted work has no reflog, so the files are named to act on."""
        write(self.worktree / "unsaved.md", "work nobody committed\n")
        write(self.worktree / "README.md", "an edit nobody committed\n")
        before = self.disk_state()

        plan = self.close(expect=EXIT_WORKTREE_DIRTY)

        self.assertEqual(self.step(plan, 6)["status"], "refused")
        self.assertEqual(
            sorted(self.step(plan, 6)["dirty_files"]), ["README.md", "unsaved.md"]
        )
        for name in ("README.md", "unsaved.md"):
            self.assertIn(name, plan["refused"]["reason"])
        self.assertIn("no reflog", plan["refused"]["reason"])
        self.assertEqual(plan["exit_code"], EXIT_WORKTREE_DIRTY)
        # The gates above it passed, and the step below it is blocked.
        self.assertEqual(
            self.statuses(plan), ["done", "todo", "refused", "blocked", "blocked"]
        )

        self.assertNothingMutated(before)

    def test_the_plan_holds_no_card_part_at_all(self):
        """Step 7 plans no board write, because the card moves after the teardown of step
        8 (ADR 0067).

        A `skipped` card part would still be a part a reader has to read, and the write
        that does happen is not part of the label-and-close step at all.
        """
        plan = self.close()

        names = [entry["name"] for entry in self.step(plan, 7)["parts"]]
        self.assertNotIn("card", names)
        for entry in self.step(plan, 7)["parts"]:
            self.assertNotIn("project", entry["command"])
        # And the close is still valid: the label and the close still run.
        self.assertIsNone(plan["refused"])
        self.assertEqual(plan["exit_code"], EXIT_OK)
        self.assertEqual(self.step(plan, 7)["status"], "todo")
        self.assertEqual(self.part(plan, "label")["status"], "todo")
        self.assertEqual(self.part(plan, "close")["status"], "todo")

    def test_an_already_closed_item_reads_done_and_the_plan_stays_valid(self):
        """Idempotence: a part-applied close is resumable rather than broken."""
        self.write_fixture(issue_state="CLOSED", labels=())
        git(self.checkout, "pull", "-q", "--ff-only", "origin", "main")
        plan = self.close()

        self.assertEqual(self.step(plan, 5)["status"], "done")
        self.assertIn("already has the merge", self.step(plan, 5)["note"])
        self.assertEqual(self.part(plan, "label")["status"], "done")
        self.assertEqual(self.part(plan, "close")["status"], "done")
        self.assertIsNone(plan["refused"])
        self.assertEqual(plan["exit_code"], EXIT_OK)
        # Both parts landed, so step 7 reads done as a whole.
        self.assertEqual(self.step(plan, 7)["status"], "done")
        self.assertEqual(self.statuses(plan)[:4], ["done", "done", "done", "done"])

    def test_a_local_branch_that_already_has_the_merge_is_not_pulled_again(self):
        """Behind is a step, and caught up is nothing to do — never a refusal."""
        git(self.checkout, "pull", "-q", "--ff-only", "origin", "main")
        plan = self.close()

        self.assertEqual(self.step(plan, 5)["status"], "done")
        self.assertIn("already has the merge", self.step(plan, 5)["note"])
        self.assertIsNone(plan["refused"])

    def test_no_worktree_argument_skips_the_clean_check(self):
        """There is no tree to prove, so step 6 does nothing and refuses nothing."""
        plan = self.close(worktree=False)

        self.assertEqual(self.step(plan, 6)["status"], "skipped")
        self.assertIn("there is no worktree to check", self.step(plan, 6)["note"])
        self.assertIsNone(plan["refused"])
        self.assertEqual(plan["exit_code"], EXIT_OK)
        # The teardown command still owns the removal, because the caller asked
        # for it and no gate above refused.
        self.assertEqual(self.step(plan, 8)["status"], "skipped")

    def test_the_label_and_the_close_are_one_step(self):
        """An item that closes without its label moving cannot happen in one step."""
        plan = self.close()

        self.assertEqual(self.step(plan, 7)["name"], "tracker")
        self.assertEqual(
            [p["name"] for p in self.step(plan, 7)["parts"]],
            ["label", "close"],
        )
        self.assertIn("move together", self.step(plan, 7)["note"])
        self.assertIn(REVIEW_LABEL, self.part(plan, "label")["command"])
        self.assertIn(f"close {ISSUE}", self.part(plan, "close")["command"])

    # --- execute mode -------------------------------------------------------

    def test_execute_runs_every_step_in_order(self):
        """The pull lands, then the two tracker writes, in the plan's order."""
        plan = self.close("--execute")

        self.assertEqual(plan["mode"], "execute")
        self.assertEqual(
            self.statuses(plan), ["done", "done", "done", "done", "skipped"]
        )
        self.assertEqual(rev(self.checkout, "main"), self.merge_commit)
        self.assertEqual(
            [w.split()[1:3] for w in self.tracker_writes()],
            [["issue", "edit"], ["issue", "close"]],
        )
        self.assertEqual(plan["ran"][0], self.step(plan, 5)["command"])
        self.assertEqual(len(plan["ran"]), 3)
        # No write reaches a project board.
        for line in self.tracker_writes():
            self.assertNotIn("project", line)

    def test_execute_stops_at_the_first_refusal_and_writes_nothing(self):
        """A refused gate means the tracker is never touched at all."""
        write(self.worktree / "unsaved.md", "work nobody committed\n")
        plan = self.close("--execute", expect=EXIT_WORKTREE_DIRTY)

        self.assertEqual(plan["refused"]["step"], 6)
        self.assertEqual(self.step(plan, 7)["status"], "blocked")
        self.assertEqual(self.tracker_writes(), [])
        # The pull before the refusal did run, and nothing after it did: that is
        # what stop-at-the-first-refusal means.
        self.assertEqual(self.step(plan, 5)["status"], "done")
        self.assertEqual(plan["ran"], [self.step(plan, 5)["command"]])

        # An unmerged PR refuses before even the pull, with its own exit code.
        self.write_fixture(pr_state="OPEN")
        before = self.disk_state()
        plan = self.close("--execute", expect=EXIT_PR_NOT_MERGED)
        self.assertEqual(self.tracker_writes(), [])
        self.assertEqual(before, self.disk_state())
        self.assertNotEqual(EXIT_PR_NOT_MERGED, EXIT_WORKTREE_DIRTY)

    def test_a_checkout_on_another_branch_moves_the_ref_and_merges_nothing(self):
        """A pull there would merge the default branch into the wrong branch."""
        git(self.checkout, "checkout", "-qb", "something-else")
        plan = self.close("--execute")

        self.assertEqual(self.step(plan, 5)["status"], "done")
        self.assertEqual(rev(self.checkout, "main"), self.merge_commit)
        # The branch the maintainer is on received nothing.
        self.assertEqual(rev(self.checkout, "HEAD"), self.base)
        self.assertFalse((self.checkout / "feature.md").exists())

    def test_the_default_invocation_mutates_nothing_at_all(self):
        """No --execute, so this seam is a read whatever else it is given."""
        before = self.disk_state()
        variants: tuple[list[str], ...] = ([], ["--teardown"], ["--indent", "0"])
        for extra in variants:
            self.close(*extra)
            self.assertNothingMutated(before)

    # --- teardown: two flags, or it does not run ----------------------------

    def test_every_gate_passing_with_both_flags_runs_the_teardown_command(self):
        """The happy path, asserted by the marker file rather than by reading code."""
        plan = self.close("--execute", "--teardown")

        self.assertTrue(plan["teardown_requested"])
        self.assertEqual(self.statuses(plan), ["done"] * 5)
        self.assertTrue(self.marker.exists())
        self.assertEqual(plan["ran"][-1], self.teardown_command())
        # And the tracker half of the close happened before it.
        self.assertEqual(len(self.tracker_writes()), 2)
        self.assertEqual(rev(self.checkout, "main"), self.merge_commit)

    def test_the_card_moves_to_done_after_the_teardown(self):
        """A card in `Done` means the worktree is gone, so the write follows the command
        that removed it (ADR 0067). The write rides on step 8, so the transaction keeps its
        numbers 4 to 8 and gains no step."""
        board = ("--board-project", "6", "--board-owner", "someone")

        plan = self.close("--execute", "--teardown", *board)

        self.assertEqual([entry["step"] for entry in plan["steps"]], [4, 5, 6, 7, 8])
        self.assertEqual(self.statuses(plan), ["done"] * 5)
        # The teardown command ran, and then the card write. That order is the point.
        self.assertEqual(plan["ran"][-2], self.teardown_command())
        self.assertIn("moved to 'Done'", plan["ran"][-1])
        self.assertEqual(
            [one for one in self.tracker_writes() if "project item-edit" in one],
            [
                f"gh project item-edit --item {ISSUE} --project 6 --owner someone "
                f"--status Done"
            ],
        )

    def test_a_close_with_no_board_coordinate_moves_no_card(self):
        """A tracker with no project board is a supported configuration, so the close runs
        whole and writes nothing to a board."""
        for board in (("--board-project", "6"), ("--board-owner", "someone"), ()):
            self.setUp()

            plan = self.close("--execute", "--teardown", *board)

            self.assertEqual(self.statuses(plan), ["done"] * 5, board)
            self.assertIsNone(self.step(plan, 8)["card"], board)
            self.assertEqual(
                [one for one in self.tracker_writes() if "project" in one], [], board
            )

    def test_a_skipped_teardown_moves_no_card(self):
        """The card write follows the teardown, so a teardown that did not run leaves the
        card where it was. The board's own item closed to Done workflow is what covers
        that case, and it is still on."""
        plan = self.close("--execute", "--board-project", "6", "--board-owner", "some")

        self.assertEqual(self.step(plan, 8)["status"], "skipped")
        self.assertEqual([one for one in self.tracker_writes() if "project" in one], [])

    def test_an_abandon_moves_no_card_whatever_the_flags_say(self):
        """Its work item stays open, so `Done` would be a lie about an item nobody
        closed."""
        self.write_fixture(labels=(START_LABEL,))

        plan = self.abandon(
            "--execute", "--teardown", "--board-project", "6", "--board-owner", "some"
        )

        self.assertTrue(self.marker.exists())
        self.assertIsNone(self.step(plan, 5)["card"])
        self.assertEqual(plan["ran"][-1], self.teardown_command())
        self.assertEqual([one for one in self.tracker_writes() if "project" in one], [])

    def test_a_failed_card_write_is_reported_and_never_fails_the_close(self):
        """Every step has already run by then, so a board that cannot be written leaves a
        stale card and nothing else.

        This is the one case a fixture cannot answer: a fixture write records its command
        and never fails. So the card write here goes through a real `gh` that exits
        non-zero, and the answer is a line for the plan rather than an exception.
        """
        failing = self.root / "bin"
        failing.mkdir()
        (failing / "gh").write_text("#!/bin/sh\necho 'no project scope' >&2\nexit 1\n")
        (failing / "gh").chmod(0o755)
        path = os.environ["PATH"]
        os.environ["PATH"] = f"{failing}{os.pathsep}{path}"
        self.addCleanup(os.environ.__setitem__, "PATH", path)
        card = {"item": ISSUE, "column": "Done", "project": 6, "owner": "someone"}

        ran = close_item.card_write(card, Tracker())

        self.assertEqual(len(ran), 1, ran)
        self.assertIn("the card write to 'Done' failed", ran[0])
        self.assertIn("no project scope", ran[0])
        self.assertEqual(len(ran[0].splitlines()), 1, ran[0])

    def test_execute_without_the_teardown_flag_leaves_the_worktree_alone(self):
        """One flag is not destructive: the tracker moves and the worktree stays."""
        plan = self.close("--execute")

        self.assertEqual(self.step(plan, 8)["status"], "skipped")
        self.assertFalse(self.marker.exists())
        self.assertTrue(self.worktree.exists())
        self.assertFalse(plan["teardown_requested"])
        # The tracker steps did run, so this is a real close minus teardown.
        self.assertEqual(len(self.tracker_writes()), 2)

    def test_the_teardown_flag_alone_is_not_destructive_either(self):
        """--teardown with no --execute is still a plan, so nothing runs."""
        before = self.disk_state()
        plan = self.close("--teardown")

        self.assertEqual(plan["mode"], "plan")
        self.assertEqual(self.step(plan, 8)["status"], "todo")  # planned, not run
        self.assertNothingMutated(before)

    def test_a_refused_gate_runs_no_teardown_and_names_the_reason(self):
        """The most valuable assertion here: teardown did not run.

        Both flags are given and a gate refuses, so the destructive step must not
        happen and the exit code must say which gate stopped it.
        """
        write(self.worktree / "unsaved.md", "work nobody committed\n")

        plan = self.close("--execute", "--teardown", expect=EXIT_WORKTREE_DIRTY)

        self.assertFalse(self.marker.exists())
        self.assertTrue(self.worktree.exists())
        self.assertTrue((self.worktree / "unsaved.md").exists())
        self.assertEqual(self.step(plan, 8)["status"], "blocked")
        self.assertEqual(plan["refused"]["step"], 6)
        self.assertEqual(plan["exit_code"], EXIT_WORKTREE_DIRTY)
        # The tracker was never written either, so the board cannot say done.
        self.assertEqual(self.tracker_writes(), [])
        self.assertEqual(self.step(plan, 7)["status"], "blocked")

        # An unmerged PR is the other refusal, and it carries its own exit code.
        self.write_fixture(pr_state="OPEN")
        plan = self.close("--execute", "--teardown", expect=EXIT_PR_NOT_MERGED)
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.tracker_writes(), [])
        self.assertNotEqual(EXIT_PR_NOT_MERGED, EXIT_WORKTREE_DIRTY)

    def test_a_rerun_after_a_part_applied_close_finishes_it(self):
        """Resumable: the first run stops short of teardown, the second finishes."""
        self.close("--execute")
        self.assertFalse(self.marker.exists())

        self.write_fixture(issue_state="CLOSED", labels=())
        plan = self.close("--execute", "--teardown")

        self.assertEqual(self.step(plan, 5)["status"], "done")
        self.assertEqual(self.part(plan, "label")["status"], "done")
        self.assertEqual(self.part(plan, "close")["status"], "done")
        self.assertEqual(self.step(plan, 8)["status"], "done")
        self.assertTrue(self.marker.exists())
        # Nothing was written twice. The card write was the one repeat, and it is gone.
        self.assertEqual(
            [w.split()[1:3] for w in self.tracker_writes()],
            [["issue", "edit"], ["issue", "close"]],
        )

    def test_the_teardown_command_is_only_ever_the_passed_in_string(self):
        """A second command changes step 8, so the seam holds none of its own."""
        plan = self.close("--teardown")
        self.assertEqual(self.step(plan, 8)["command"], self.teardown_command())

        other = self.root / "other-marker"
        plan = self.close(
            "--execute",
            "--teardown",
            "--teardown-command",
            f"touch {other}",
            teardown_command=False,
        )
        self.assertEqual(self.step(plan, 8)["command"], f"touch {other}")
        self.assertTrue(other.exists())
        self.assertFalse(self.marker.exists())

        # And no workspace tool's own command shape is written into the module.
        source = (REPO_ROOT / "scripts" / "close_item.py").read_text()
        for shape in ("worktree rm", "worktree remove", "cmux ", "herdr "):
            self.assertNotIn(shape, source, f"{shape!r} is hardcoded in the seam")

    def test_no_teardown_command_removes_nothing_and_fails_nothing(self):
        """The caller owns the command, so its absence is a no-op not an error."""
        plan = self.close("--execute", "--teardown", teardown_command=False)

        self.assertEqual(self.step(plan, 8)["status"], "skipped")
        self.assertIn("--teardown-command", self.step(plan, 8)["note"])
        self.assertFalse(self.marker.exists())
        self.assertIsNone(plan["refused"])
        self.assertEqual(len(self.tracker_writes()), 2)

    # --- the other tracker --------------------------------------------------

    def test_the_other_tracker_runs_the_same_five_steps_with_its_own_commands(self):
        """The seam reaches a second tracker, and the eight steps do not change.

        The one fixture format stands in for either CLI, so this case needs no
        network and no login. `merged` in lower case passes the same gate, because
        the seam compares the state in its own case.
        """
        self.write_fixture(pr_state="merged")
        plan = self.close("--execute", *GLAB)

        self.assertEqual([s["step"] for s in plan["steps"]], [4, 5, 6, 7, 8])
        self.assertEqual(self.step(plan, 4)["status"], "done")
        self.assertEqual(
            self.step(plan, 4)["command"],
            f"glab mr view {PR} -F json -R {HOST}/{PROJECT}",
        )
        self.assertIsNone(plan["refused"])
        self.assertEqual(plan["exit_code"], EXIT_OK)
        self.assertEqual(
            self.tracker_writes(),
            [
                f"glab issue update {ISSUE} --unlabel {REVIEW_LABEL} -R {HOST}/{PROJECT}",
                f"glab issue close {ISSUE} -R {HOST}/{PROJECT}",
            ],
        )

    def test_a_close_reason_is_its_own_write_before_the_close_on_that_tracker(self):
        """Its close command takes no reason, so the note is a part of its own."""
        plan = self.close("--execute", *GLAB, "--close-comment", REASON)

        self.assertEqual(
            [p["name"] for p in self.step(plan, 7)["parts"]],
            ["label", "note", "close"],
        )
        self.assertEqual(self.part(plan, "note")["status"], "done")
        # The note was written before the close, which is the whole point of the part.
        self.assertEqual(
            self.tracker_writes(),
            [
                f"glab issue update {ISSUE} --unlabel {REVIEW_LABEL} -R {HOST}/{PROJECT}",
                f"glab issue note {ISSUE} --message {REASON} -R {HOST}/{PROJECT}",
                f"glab issue close {ISSUE} -R {HOST}/{PROJECT}",
            ],
        )

    def test_a_reason_already_on_the_item_is_not_posted_a_second_time(self):
        """A note is not idempotent by itself, so the part reads the comments first."""
        self.write_fixture(comments=[f"a line, and {REASON}"])
        plan = self.close("--execute", *GLAB, "--close-comment", REASON)

        self.assertEqual(self.part(plan, "note")["status"], "done")
        self.assertIn("already on the item", self.part(plan, "note")["note"])
        self.assertEqual(
            [w.split()[1:3] for w in self.tracker_writes()],
            [["issue", "update"], ["issue", "close"]],
        )

    def test_a_close_reason_rides_the_close_command_where_the_cli_takes_one(self):
        """One write and not two, so this tracker gains no part."""
        plan = self.close("--close-comment", REASON)

        self.assertEqual(
            [p["name"] for p in self.step(plan, 7)["parts"]], ["label", "close"]
        )
        self.assertIn(f"--comment {REASON}", self.part(plan, "close")["command"])

    def test_no_tracker_argument_leaves_every_command_as_it_was(self):
        """The default is the tracker this repo runs on, and no plan of it changes."""
        plan = self.close()

        self.assertEqual(
            self.step(plan, 4)["command"], f"gh pr view {PR} --json state,mergeCommit"
        )
        self.assertEqual(
            self.part(plan, "label")["command"],
            f"gh issue edit {ISSUE} --remove-label {REVIEW_LABEL}",
        )
        self.assertEqual(self.part(plan, "close")["command"], f"gh issue close {ISSUE}")
        self.assertEqual(
            [p["name"] for p in self.step(plan, 7)["parts"]], ["label", "close"]
        )

    # --- the two things the seam must not know ------------------------------

    def test_the_seam_takes_two_board_coordinates_and_no_id(self):
        """Step 8 writes the card, so the seam takes the project and the owner (ADR 0067).

        The five id flags stay gone. A caller holds a name, and the adapter resolves every
        id at run time, so a flag that carries an id is a flag a caller resolves for
        nothing. The argument surface is where this is proven.
        """
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.close_item", "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=GIT_ENV,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--board-project", proc.stdout)
        self.assertIn("--board-owner", proc.stdout)
        for flag in (
            "--project-number",
            "--project-owner",
            "--project-id",
            "--status-field-id",
            "--done-option-id",
        ):
            self.assertNotIn(flag, proc.stdout, f"--help still names {flag}")

        # And no board id of this repo's own is in the module. The two coordinates a
        # caller passes are a number and an owner, and neither one is an id.
        source = (REPO_ROOT / "scripts" / "close_item.py").read_text()
        for coordinate in ("PVT_kwHO", "PVTSSF_lAHO"):
            self.assertNotIn(coordinate, source, f"{coordinate!r} is in the seam")

    # --- the abandon: a worktree that never opened a pull request -----------

    def commit_in_the_worktree(self):
        """One commit on the item's branch, which is work an abandon must not remove."""
        write(self.worktree / "half-done.md", "work with no pull request\n")
        git(self.worktree, "add", "-A")
        git(self.worktree, "commit", "-qm", "a first commit nobody reviewed")

    def test_an_abandon_of_an_empty_worktree_removes_it_and_leaves_the_item_open(self):
        """The whole point: no pull request, no merge, and the worktree still goes."""
        self.write_fixture(labels=(START_LABEL,))
        plan = self.abandon("--execute", "--teardown")

        self.assertEqual(plan["path"], "abandon")
        self.assertEqual([s["step"] for s in plan["steps"]], [1, 2, 3, 4, 5])
        self.assertEqual(
            [s["name"] for s in plan["steps"]],
            ["no commit", "worktree clean", "no pull request", "tracker", "teardown"],
        )
        self.assertEqual(self.statuses(plan), ["done"] * 5)
        self.assertIsNone(plan["refused"])
        # The worktree went, through the same command the close runs.
        self.assertTrue(self.marker.exists())
        self.assertEqual(plan["ran"][-1], self.teardown_command())
        # The item stays open: the label came off, the reason went on, and nothing
        # closed it.
        self.assertEqual(
            self.tracker_writes(),
            [
                f"gh issue edit {ISSUE} --remove-label {START_LABEL}",
                f"gh issue comment {ISSUE} --body {ABANDON_REASON}",
            ],
        )
        for line in self.tracker_writes():
            self.assertNotIn("close", line)
            self.assertNotIn("--add-label", line)

    def test_a_commit_on_the_branch_refuses_the_abandon_and_removes_nothing(self):
        """A commit is work, and work is never abandoned unread."""
        self.commit_in_the_worktree()
        before = self.disk_state()

        plan = self.abandon("--execute", "--teardown", expect=EXIT_COMMITS_AHEAD)

        self.assertEqual(self.step(plan, 1)["status"], "refused")
        self.assertEqual(plan["refused"]["step"], 1)
        self.assertEqual(len(self.step(plan, 1)["commits_ahead"]), 1)
        self.assertIn("nobody reviewed", plan["refused"]["reason"])
        self.assertIn("pull request", plan["refused"]["reason"])
        self.assertEqual(plan["exit_code"], EXIT_COMMITS_AHEAD)
        # Every step after it is blocked, so the worktree and the item are untouched.
        self.assertEqual(self.statuses(plan), ["refused"] + ["blocked"] * 4)
        self.assertNothingMutated(before)

    def test_a_dirty_worktree_refuses_the_abandon_with_the_dirty_code(self):
        """The same proof and the same code as the close: uncommitted work stays."""
        write(self.worktree / "unsaved.md", "work nobody committed\n")
        before = self.disk_state()

        plan = self.abandon("--execute", "--teardown", expect=EXIT_WORKTREE_DIRTY)

        self.assertEqual(self.step(plan, 1)["status"], "done")
        self.assertEqual(self.step(plan, 2)["status"], "refused")
        self.assertEqual(self.step(plan, 2)["dirty_files"], ["unsaved.md"])
        self.assertIn("no reflog", plan["refused"]["reason"])
        self.assertNothingMutated(before)

    def test_an_open_pull_request_refuses_the_abandon_on_a_code_of_its_own(self):
        """There is a review to finish, so the merge is the way out and not this."""
        self.write_fixture(pr_state="OPEN", labels=(START_LABEL,), pr_head=self.branch)
        before = self.disk_state()

        plan = self.abandon("--execute", "--teardown", expect=EXIT_PR_OPEN)

        self.assertEqual(
            self.statuses(plan), ["done", "done", "refused", "blocked", "blocked"]
        )
        self.assertEqual(self.step(plan, 3)["pull_request"], PR)
        self.assertIn(f"#{PR}", plan["refused"]["reason"])
        self.assertIn("review to finish", plan["refused"]["reason"])
        # Its own code, because 2 already means the opposite fact.
        self.assertNotEqual(EXIT_PR_OPEN, EXIT_PR_NOT_MERGED)
        self.assertNothingMutated(before)

    def test_the_abandon_plan_mutates_nothing_either(self):
        """Plan mode is the default on this path too, --teardown included."""
        self.write_fixture(labels=(START_LABEL,))
        before = self.disk_state()

        plan = self.abandon("--teardown")

        self.assertEqual(plan["mode"], "plan")
        self.assertEqual(plan["mutates"], "nothing")
        self.assertEqual(plan["exit_code"], EXIT_OK)
        self.assertEqual(self.step(plan, 4)["status"], "todo")
        self.assertEqual(self.step(plan, 5)["status"], "todo")
        self.assertNothingMutated(before)

    def test_an_abandon_plans_no_close_and_no_added_label(self):
        """An abandon moves no work state, so neither write can be planned at all."""
        self.write_fixture(labels=(START_LABEL,))
        plan = self.abandon()

        names = [entry["name"] for entry in self.step(plan, 4)["parts"]]
        self.assertEqual(names, ["label", "note"])
        self.assertNotIn("close", names)
        self.assertIn(
            f"--remove-label {START_LABEL}", self.part(plan, "label", 4)["command"]
        )
        self.assertNotIn("--add-label", self.part(plan, "label", 4)["command"])

        # A caller that asks for the start label is a caller with a typo, and 64 says
        # so without touching anything.
        proc = self.seam(
            [*self.abandon_argv(), "--add-label", READY_LABEL], expect=EXIT_USAGE
        )
        self.assertIn("--add-label", proc.stderr)
        self.assertEqual(self.tracker_writes(), [])

    def test_the_two_paths_refuse_each_other_s_flags_with_the_usage_code(self):
        """A flag typo is 64, so no caller reads one as a refusal."""
        proc = self.seam([*self.abandon_argv(), "--pr", str(PR)], expect=EXIT_USAGE)
        self.assertIn("--pr", proc.stderr)

        # And a close with no pull request names the flag rather than refusing.
        argv = [
            "--issue",
            str(ISSUE),
            "--repo",
            str(self.checkout),
            "--gh-fixture",
            str(self.fixture),
        ]
        proc = self.seam(argv, expect=EXIT_USAGE)
        self.assertIn("--abandon", proc.stderr)
        self.assertNotEqual(EXIT_USAGE, EXIT_PR_NOT_MERGED)

    def test_a_second_abandon_posts_no_second_comment(self):
        """The reason is a comment, and a comment repeats unless the write reads first."""
        self.write_fixture(
            labels=(START_LABEL,), comments=[f"a line, {ABANDON_REASON}"]
        )
        plan = self.abandon("--execute", "--teardown")

        self.assertEqual(self.part(plan, "note", 4)["status"], "done")
        self.assertIn("already on the item", self.part(plan, "note", 4)["note"])
        self.assertEqual(
            self.tracker_writes(),
            [f"gh issue edit {ISSUE} --remove-label {START_LABEL}"],
        )
        self.assertTrue(self.marker.exists())

    def test_the_seam_names_no_tracker_cli(self):
        """Every tracker command comes from the adapter, so this seam writes no CLI
        name. `--gh-fixture` keeps its own name, and that flag string is not a CLI
        name, so it is not a hit."""
        source = (REPO_ROOT / "scripts" / "close_item.py").read_text()
        literals = [
            node.value
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        for cli in ("gh", "glab"):
            self.assertNotIn(cli, literals, f"{cli!r} is a literal in the seam")


if __name__ == "__main__":
    unittest.main()
