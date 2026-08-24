#!/usr/bin/env python3
"""Behaviour tests for the merge-train seam: a local git repo in, a JSON plan out.

Every case runs `python3 -m scripts.merge_train` as a subprocess against one repo built
in a temp directory. Each one asserts on the printed plan, on the exit code and on the
target repo afterwards, and never on a helper's return value. No network, no tracker and
no mocking framework: the fixture is git and nothing else. `GIT_CONFIG_GLOBAL` and
`GIT_CONFIG_SYSTEM` point at `os.devnull`, so the developer's git config cannot leak
into a fixture.

The fixture holds one branch per case the seam has to separate. One branch touches its
own file. Two touch the same file as each other. One conflicts with the default branch.
One is already in the default branch. And one has no common ancestor at all.

Two assertions here are the most valuable. The target repo is byte-identical after a
run, and the throwaway checkout is gone even when the run raised. See
`test_the_run_mutates_no_branch_no_ref_and_no_working_tree` and
`test_the_checkout_is_removed_after_a_failure_too`.

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

REPO_ROOT = Path(__file__).resolve().parents[1]
SEAM = REPO_ROOT / "scripts" / "merge_train.py"

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.com",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_DIRTY_REPO = 3
EXIT_MISSING_BRANCH = 4
EXIT_ALREADY_MERGED = 5
EXIT_EMPTY_QUEUE = 6

# One queued item per case, as the `--item` values the seam takes. The numbers are out
# of order on purpose, so a passing tie-break cannot be the insertion order.
ALONE = "101:101-alone"
SHARED_LOW = "202:202-shared"
SHARED_HIGH = "303:303-shared"
CONFLICTS = "404:404-conflicts"
MERGED = "505:505-merged"
LONELY = "606:606-lonely"


def git(cwd, *args):
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        env=GIT_ENV,
    )


def git_out(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        env=GIT_ENV,
    ).stdout


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class MergeTrainTestCase(unittest.TestCase):
    """One repo whose branches cover every case the seam has to separate."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        write(self.repo / "README.md", "the default branch\n")
        write(self.repo / "shared.md", "a line every shared branch appends to\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "base")

        # Its own file, so it overlaps with nothing.
        self.branch("101-alone", "alone.md", "one item's own file\n")
        # The same file as each other, so each one overlaps with exactly one branch.
        self.branch("202-shared", "shared.md", "the lower item's line\n", append=True)
        self.branch("303-shared", "shared.md", "the higher item's line\n", append=True)
        # The same file the default branch is about to change, so it conflicts there.
        self.branch("404-conflicts", "README.md", "the branch's own first line\n")
        # A branch with no commit of its own, cut after the default branch moved.
        git(self.repo, "checkout", "-q", "main")
        write(self.repo / "README.md", "the default branch, moved on\n")
        git(self.repo, "commit", "-qam", "move the default branch")
        git(self.repo, "branch", "505-merged", "main")
        # No common ancestor with the default branch at all.
        git(self.repo, "checkout", "-q", "--orphan", "606-lonely")
        git(self.repo, "rm", "-rq", "--cached", ".")
        for name in ("README.md", "shared.md"):
            (self.repo / name).unlink()
        write(self.repo / "lonely.md", "a history of its own\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "an unrelated history")
        git(self.repo, "checkout", "-q", "main")

    # --- fixture helpers ----------------------------------------------------

    def branch(self, name, path, text, append=False):
        """One branch off the default branch, with one commit that changes one file."""
        git(self.repo, "checkout", "-q", "main")
        git(self.repo, "checkout", "-qb", name)
        target = self.repo / path
        write(target, (target.read_text() + text) if append else text)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", f"the work of {name}")
        git(self.repo, "checkout", "-q", "main")

    def run_seam(self, *items, extra=(), repo=None, expect=EXIT_OK, env=None):
        """Run the seam and return its finished process."""
        argv = [sys.executable, "-m", "scripts.merge_train", "--repo"]
        argv.append(str(self.repo if repo is None else repo))
        for item in items:
            argv += ["--item", item]
        proc = subprocess.run(
            [*argv, *extra],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env={**GIT_ENV, **(env or {})},
        )
        self.assertEqual(proc.returncode, expect, f"stderr: {proc.stderr}")
        return proc

    def plan(self, *items, **kwargs):
        """Run the seam and return the one JSON object it printed."""
        proc = self.run_seam(*items, **kwargs)
        return json.loads(proc.stdout)

    def repo_state(self):
        """Every fact the seam promises to leave alone."""
        return (
            git_out(self.repo, "status", "--porcelain"),
            git_out(self.repo, "for-each-ref", "--format=%(refname) %(objectname)"),
            git_out(self.repo, "worktree", "list", "--porcelain"),
            sorted(str(path.relative_to(self.repo)) for path in self.repo.rglob("*")),
        )

    # --- the plan -----------------------------------------------------------

    def test_a_queue_prints_one_json_object_with_an_order_and_a_parked_list(self):
        """The whole output is one object, and both lists are in it."""
        proc = self.run_seam(ALONE, SHARED_LOW)
        plan = json.loads(proc.stdout)  # a second object raises here

        self.assertEqual(plan["mutates"], "nothing")
        self.assertEqual(plan["generated_by"], "scripts.merge_train")
        self.assertEqual(plan["repo"], str(self.repo.resolve()))
        self.assertEqual(plan["default_branch"], "main")
        self.assertEqual(plan["parked"], [])
        self.assertEqual(
            plan["order"],
            [
                {"item": 101, "branch": "101-alone", "overlaps": 0},
                {"item": 202, "branch": "202-shared", "overlaps": 0},
            ],
        )
        # Every order entry carries the three keys and nothing else.
        for entry in plan["order"]:
            self.assertEqual(sorted(entry), ["branch", "item", "overlaps"])
        self.assertEqual(proc.stderr, "")

    def test_the_ranking_is_fewest_overlaps_first_then_item_number_ascending(self):
        """The tie-break, proved by two branches of equal overlap.

        `202-shared` and `303-shared` change the same file, so both count one
        overlap. `101-alone` changes its own file and counts none.
        """
        plan = self.plan(SHARED_HIGH, ALONE, SHARED_LOW)

        # The two tied branches go in as 303 then 202, so the item number decides the
        # order that follows and the argument order does not.
        self.assertEqual(
            [(entry["item"], entry["overlaps"]) for entry in plan["order"]],
            [(101, 0), (202, 1), (303, 1)],
        )
        self.assertEqual(plan["parked"], [])

    def test_a_conflicting_branch_is_parked_and_never_ordered(self):
        """The park entry names the item, the branch, a reason and the paths."""
        plan = self.plan(ALONE, CONFLICTS)

        self.assertEqual(
            plan["parked"],
            [
                {
                    "item": 404,
                    "branch": "404-conflicts",
                    "reason": "the test-merge onto main conflicts",
                    "paths": ["README.md"],
                }
            ],
        )
        self.assertEqual([entry["item"] for entry in plan["order"]], [101])
        # And the parked branch is out of the overlap count of the survivors.
        self.assertEqual(plan["order"][0]["overlaps"], 0)

    def test_a_queue_where_every_branch_parks_is_still_a_plan(self):
        """An empty order is a plan, and not a failure."""
        plan = self.plan(CONFLICTS)

        self.assertEqual(plan["order"], [])
        self.assertEqual([entry["item"] for entry in plan["parked"]], [404])

    # --- the target repo is untouched ---------------------------------------

    def test_the_run_mutates_no_branch_no_ref_and_no_working_tree(self):
        """The seam plans, so `git status` and every ref survive it unchanged."""
        before = self.repo_state()

        self.plan(ALONE, SHARED_LOW, SHARED_HIGH, CONFLICTS)

        self.assertEqual(before, self.repo_state())
        # And a refused run leaves the same repo behind.
        self.run_seam(expect=EXIT_EMPTY_QUEUE)
        self.assertEqual(before, self.repo_state())

    def test_the_throwaway_checkout_is_under_the_system_temp_directory(self):
        """The checkout is removed on the way out, and it was never inside the repo."""
        plan = self.plan(ALONE, CONFLICTS)
        checkout = Path(plan["checkout"])

        self.assertFalse(checkout.exists(), plan["checkout"])
        self.assertTrue(
            plan["checkout"].startswith(tempfile.gettempdir()), plan["checkout"]
        )
        self.assertNotIn(str(self.repo), plan["checkout"])
        # A `git worktree` of the target shows up in this list.
        self.assertEqual(len(git_out(self.repo, "worktree", "list").splitlines()), 1)

    def test_the_checkout_is_removed_after_a_failure_too(self):
        """`606-lonely` shares no ancestor, so the test-merge raises mid-run.

        The temp directory is this run's own. So an empty directory afterwards proves
        the removal happened on the raised path, and not on the clean one.
        """
        probe = self.root / "probe-temp"
        probe.mkdir()

        proc = self.run_seam(
            ALONE, LONELY, expect=EXIT_ERROR, env={"TMPDIR": str(probe)}
        )

        self.assertEqual(list(probe.iterdir()), [])
        self.assertEqual(proc.stdout, "")
        self.assertIn("606-lonely", proc.stderr)
        self.assertIn("no conflicted path", proc.stderr)

        # The clean path uses that same directory. So the check before this one reads
        # the directory the checkout really goes in.
        plan = self.plan(ALONE, env={"TMPDIR": str(probe)})
        self.assertTrue(plan["checkout"].startswith(str(probe)), plan["checkout"])
        self.assertEqual(list(probe.iterdir()), [])

    # --- the refusals -------------------------------------------------------

    def test_a_dirty_repo_refuses_with_its_own_code_and_names_the_files(self):
        """The plan reads committed state only, so uncommitted work is a stop."""
        write(self.repo / "unsaved.md", "work nobody committed\n")
        write(self.repo / "README.md", "an edit nobody committed\n")

        proc = self.run_seam(ALONE, expect=EXIT_DIRTY_REPO)

        for name in ("README.md", "unsaved.md"):
            self.assertIn(name, proc.stderr)
        self.assertIn("committed state", proc.stderr)
        self.assertEqual(proc.stdout, "")

    def test_a_missing_branch_refuses_with_its_own_code_and_names_it(self):
        """This seam checks a queued branch and the default branch the same way."""
        proc = self.run_seam(ALONE, "707:707-never-existed", expect=EXIT_MISSING_BRANCH)
        self.assertIn("707-never-existed", proc.stderr)
        self.assertNotIn("101-alone", proc.stderr)
        self.assertEqual(proc.stdout, "")

        proc = self.run_seam(
            ALONE, extra=["--default-branch", "trunk"], expect=EXIT_MISSING_BRANCH
        )
        self.assertIn("trunk", proc.stderr)

    def test_an_already_merged_branch_refuses_with_its_own_code(self):
        """A finished item makes the queue stale, and a stale queue plans wrong."""
        proc = self.run_seam(ALONE, MERGED, expect=EXIT_ALREADY_MERGED)

        self.assertIn("505-merged", proc.stderr)
        self.assertIn("#505", proc.stderr)
        self.assertIn("out of the queue", proc.stderr)
        self.assertEqual(proc.stdout, "")

    def test_an_empty_queue_refuses_with_its_own_code(self):
        """There is no train to plan, so the seam prints no plan."""
        proc = self.run_seam(expect=EXIT_EMPTY_QUEUE)

        self.assertIn("--item", proc.stderr)
        self.assertEqual(proc.stdout, "")

    def test_each_refusal_carries_a_code_of_its_own(self):
        """The code is the contract, so no two causes can share one."""
        codes = (
            EXIT_OK,
            EXIT_ERROR,
            EXIT_USAGE,
            EXIT_DIRTY_REPO,
            EXIT_MISSING_BRANCH,
            EXIT_ALREADY_MERGED,
            EXIT_EMPTY_QUEUE,
        )
        self.assertEqual(len(set(codes)), len(codes))

        # A usage error keeps code 2, so a flag with a typo cannot read as one of the
        # four refusals.
        self.run_seam(ALONE, extra=["--nonsense"], expect=EXIT_USAGE)
        self.run_seam("not-a-queued-item", expect=EXIT_USAGE)

    # --- the argument surface ----------------------------------------------

    def test_help_is_the_argument_surface_and_offers_no_execute_flag(self):
        """There is nothing to execute, so the flag is absent rather than rejected."""
        proc = self.run_seam(extra=["--help"])
        offered = proc.stdout.split("options:", 1)[-1]

        for flag in ("--repo", "--default-branch", "--item", "NUMBER:BRANCH"):
            self.assertIn(flag, offered)
        self.assertIn("merge-train.md", proc.stdout)
        # The description says the flag does not exist. The list of flags is where a
        # usable flag appears, and `--execute` is not in that list.
        self.assertNotIn("--execute", offered)
        self.run_seam(ALONE, extra=["--execute"], expect=EXIT_USAGE)

    def test_the_module_imports_the_standard_library_only(self):
        """No dependency to install, which is what makes this seam a seam."""
        roots = set[str]()
        for node in ast.walk(ast.parse(SEAM.read_text())):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                roots.add((node.module or "").split(".")[0])

        self.assertTrue(roots)
        self.assertEqual(roots - set(sys.stdlib_module_names), set())

    def test_the_docstring_names_the_reference_file_and_restates_no_rule(self):
        """A rule with two homes drifts, so the ordering rule keeps the one it has."""
        docstring = ast.get_docstring(ast.parse(SEAM.read_text())) or ""

        self.assertIn("orchestrator/references/merge-train.md", docstring)
        for phrase in ("fewest", "ascending", "review state", "tie"):
            self.assertNotIn(phrase, docstring.lower(), phrase)
        # It holds its own contract instead: the flags, the JSON and the codes.
        for flag in ("--repo", "--default-branch", "--item", "--execute"):
            self.assertIn(flag, docstring)
        for key in ("order", "parked", "overlaps", "paths", "checkout"):
            self.assertIn(key, docstring)
        for code in (0, 1, 2, 3, 4, 5, 6):
            self.assertIn(f"| {code} |", docstring)


if __name__ == "__main__":
    unittest.main()
