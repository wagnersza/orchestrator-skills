#!/usr/bin/env python3
"""Behaviour tests for the close seam: fixture state in, JSON plan out.

Every case runs `python3 -m scripts.close_item` as a subprocess against local git
repos built in a temp directory, and asserts on the emitted plan and on what was
mutated — never on a helper's return value. No network, no GitHub, no mocking
framework and no agent runs: `--gh-fixture` stands in for every tracker read, so
`gh` is never called. `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` point at
`os.devnull`, so the developer's git config cannot leak into a fixture.

The teardown command is a passed-in string, which is what makes the destructive
path testable: every case here passes a command that creates a marker file, and
then asserts the file exists only when it should. The single most valuable
assertion in the file is that the marker is absent — see
`test_a_refused_gate_runs_no_teardown_and_names_the_reason`.

    python3 -m pytest scripts/ -q
    python3 -m unittest discover -s scripts -t . -q     # fallback, no pytest
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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
BOARD = [
    "--project-number", "6",
    "--project-owner", "wagnersza",
    "--project-id", "PVT_fixture",
    "--status-field-id", "PVTSSF_fixture",
    "--done-option-id", "98236657",
]

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_PR_NOT_MERGED = 2
EXIT_WORKTREE_DIRTY = 3


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
        git(self.worktree, "checkout", "-qb", f"{ISSUE}-close-item-seam")

        self.marker = self.root / "teardown-ran"
        self.write_fixture()

    # --- fixture helpers ----------------------------------------------------

    def write_fixture(
        self,
        pr_state="MERGED",
        issue_state="OPEN",
        labels=(REVIEW_LABEL,),
        card="PVTI_fixture",
    ):
        """Stand in for the three tracker reads: the PR, the issue, the card."""
        self.fixture = self.root / "gh.json"
        data = {
            "pull_requests": {
                str(PR): {
                    "state": pr_state,
                    "mergeCommit": {"oid": self.merge_commit}
                    if pr_state == "MERGED"
                    else None,
                }
            },
            "issues": {str(ISSUE): {"state": issue_state, "labels": list(labels)}},
            "project_items": {str(ISSUE): card} if card else {},
        }
        self.fixture.write_text(json.dumps(data))
        self.writes = self.root / "gh.json.writes"

    def teardown_command(self):
        """A teardown command that leaves proof it ran, and destroys nothing."""
        return f"touch {self.marker}"

    def close(self, *extra, board=True, worktree=True, teardown_command=True, expect=0):
        """Run the seam and return the parsed plan."""
        argv = [
            sys.executable,
            "-m",
            "scripts.close_item",
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
        if board:
            argv += BOARD
        if teardown_command:
            argv += ["--teardown-command", self.teardown_command()]
        proc = subprocess.run(
            [*argv, *extra],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=GIT_ENV,
        )
        self.assertEqual(proc.returncode, expect, f"stderr: {proc.stderr}")
        return json.loads(proc.stdout)

    def step(self, plan, number):
        for entry in plan["steps"]:
            if entry["step"] == number:
                return entry
        self.fail(f"step {number} missing: {[s['step'] for s in plan['steps']]}")

    def part(self, plan, name):
        for entry in self.step(plan, 7)["parts"]:
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
        self.assertIn("`In review`", plan["refused"]["reason"])
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

    def test_the_label_the_close_and_the_card_are_one_step(self):
        """A label that moves without its card cannot happen inside one step."""
        plan = self.close()

        self.assertEqual(self.step(plan, 7)["name"], "tracker")
        self.assertEqual(
            [p["name"] for p in self.step(plan, 7)["parts"]],
            ["label", "close", "card"],
        )
        self.assertIn("move together", self.step(plan, 7)["note"])
        self.assertIn(REVIEW_LABEL, self.part(plan, "label")["command"])
        self.assertIn(f"close {ISSUE}", self.part(plan, "close")["command"])

    # --- execute mode -------------------------------------------------------

    def test_execute_runs_every_step_in_order(self):
        """The pull lands, then the three tracker writes, in the plan's order."""
        plan = self.close("--execute")

        self.assertEqual(plan["mode"], "execute")
        self.assertEqual(
            self.statuses(plan), ["done", "done", "done", "done", "skipped"]
        )
        self.assertEqual(rev(self.checkout, "main"), self.merge_commit)
        self.assertEqual(
            [w.split()[1:3] for w in self.tracker_writes()],
            [["issue", "edit"], ["issue", "close"], ["project", "item-edit"]],
        )
        self.assertEqual(plan["ran"][0], self.step(plan, 5)["command"])
        self.assertEqual(len(plan["ran"]), 4)

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
        for extra in ([], ["--teardown"], ["--indent", "0"]):
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
        self.assertEqual(len(self.tracker_writes()), 3)
        self.assertEqual(rev(self.checkout, "main"), self.merge_commit)

    def test_execute_without_the_teardown_flag_leaves_the_worktree_alone(self):
        """One flag is not destructive: the tracker moves and the worktree stays."""
        plan = self.close("--execute")

        self.assertEqual(self.step(plan, 8)["status"], "skipped")
        self.assertFalse(self.marker.exists())
        self.assertTrue(self.worktree.exists())
        self.assertFalse(plan["teardown_requested"])
        # The tracker steps did run, so this is a real close minus teardown.
        self.assertEqual(len(self.tracker_writes()), 3)

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
        self.assertEqual(len(self.tracker_writes()), 3)

    # --- the two things the seam must not know ------------------------------

    def test_the_board_coordinates_are_arguments_not_knowledge(self):
        """Different coordinates give a different command, so none is built in."""
        command = self.part(self.close(), "card")["command"]
        for value in ("PVTI_fixture", "PVT_fixture", "PVTSSF_fixture", "98236657"):
            self.assertIn(value, command)

        self.write_fixture(card="PVTI_second")
        second = self.part(
            self.close(
                "--project-number", "9",
                "--project-owner", "someone",
                "--project-id", "PVT_second",
                "--status-field-id", "PVTSSF_second",
                "--done-option-id", "aaaaaaaa",
                board=False,
            ),
            "card",
        )["command"]
        self.assertNotEqual(command, second)
        for value in ("PVTI_second", "PVT_second", "PVTSSF_second", "aaaaaaaa"):
            self.assertIn(value, second)

        # And no board id of this repo's own is in the module, nor the Markdown
        # file that owns them.
        source = (REPO_ROOT / "scripts" / "close_item.py").read_text()
        for coordinate in ("PVT_kwHO", "PVTSSF_lAHO", "issue-tracker"):
            self.assertNotIn(coordinate, source, f"{coordinate!r} is in the seam")

    def test_gh_is_hardcoded_with_its_ceiling_named(self):
        """The GitHub-only assumption is visible to whoever first needs GitLab."""
        source = (REPO_ROOT / "scripts" / "close_item.py").read_text()
        self.assertIn("ponytail:", source)
        self.assertIn("GitLab", source)


if __name__ == "__main__":
    unittest.main()
