#!/usr/bin/env python3
"""The suite for `hooks/gate_record.py`, the one home of the **Gate record** format.

The format is a library and not a hook, so this suite imports it and calls it. The
three hook suites still drive their hook as a process, because a hook's contract is the
payload it prints. **The format is tested once here**, and its four callers inherit it:

- `hooks/record.py` writes the line,
- `hooks/refuse.py` denies the push,
- `hooks/context.py` injects the session-start verdict,
- `scripts/worker_state.py` fires `gates-unproven`.

The fixture is a real git repository in a temporary directory, so a written line ties to
a real commit. There is no network and no login.

    python3 -m pytest hooks/ -q
    python3 -m unittest discover -s hooks -t . -q     # fallback, no pytest
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from hooks import gate_record

ITEM = "202"

# A fixture commit with the developer's own configuration sealed off. A machine with a
# signing key or a commit template must not change what these tests see.
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


class GateRecord(unittest.TestCase):
    """A worktree, the lines its gate runs left, and what a reader makes of them."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        (self.root / ".orchestrator").mkdir(parents=True)
        self.git("init", "-q", "-b", "main")
        (self.root / "README.md").write_text("fixture\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-qm", "fixture")
        self.record = gate_record.path(self.root, ITEM)

    # --- the fixture ---------------------------------------------------------

    def git(self, *args):
        """One git command in the fixture checkout."""
        subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=True,
            capture_output=True,
            text=True,
            env=GIT_ENV,
        )

    def head(self):
        """The commit the fixture sits on."""
        proc = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            env=GIT_ENV,
        )
        return proc.stdout.strip()

    def write(self, *lines):
        """The record, holding these lines of text in this order."""
        self.record.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")

    def green(self, command="make quick", code=0, sha=None):
        """One record line as text, with the four keys."""
        return json.dumps(
            {
                "command": command,
                "exit": code,
                "utc": "2026-09-25T09:14:02Z",
                "head_sha": self.head() if sha is None else sha,
            }
        )

    # --- the write ------------------------------------------------------------

    def test_the_path_sits_beside_the_checklist(self):
        """The record belongs to one work item, in that worker's own worktree."""
        self.assertEqual(
            self.record, self.root / ".orchestrator" / f"gates-{ITEM}.jsonl"
        )

    def test_an_appended_line_holds_the_four_keys_and_the_real_commit(self):
        """The deciding case for the write. One reader has to be able to tie the run
        to a commit and to a moment, so no key is optional."""
        gate_record.append(self.root, ITEM, "make quick", 0)

        runs, malformed = gate_record.runs(self.record)
        self.assertEqual(malformed, 0)
        self.assertEqual(len(runs), 1, runs)
        self.assertEqual(sorted(runs[0]), sorted(gate_record.KEYS))
        self.assertEqual(runs[0]["command"], "make quick")
        self.assertEqual(runs[0]["exit"], 0)
        self.assertEqual(runs[0]["head_sha"], self.head())
        self.assertRegex(runs[0]["utc"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_a_second_run_is_appended_and_replaces_nothing(self):
        """A worker corrects a fault and runs the command again. Both runs stay
        readable, because the record is a history and not a verdict."""
        gate_record.append(self.root, ITEM, "make quick", 1)
        gate_record.append(self.root, ITEM, "make quick", 0)

        runs, _ = gate_record.runs(self.record)
        self.assertEqual([run["exit"] for run in runs], [1, 0])

    def test_an_unreadable_head_is_written_as_an_empty_value(self):
        """A run with no readable commit still happened, so it earns its line. The
        empty value is what stops a reader from matching it to any commit."""
        outside = Path(self.tmp.name) / "outside"
        (outside / ".orchestrator").mkdir(parents=True)

        gate_record.append(outside, ITEM, "make quick", 0)

        runs, _ = gate_record.runs(gate_record.path(outside, ITEM))
        self.assertEqual(runs[0]["head_sha"], "")
        self.assertFalse(gate_record.at_head(runs[0]["head_sha"], self.head()))

    # --- the read -------------------------------------------------------------

    def test_a_missing_file_holds_no_run_and_no_fault(self):
        """A worker that ran no gate yet is a normal state. The caller reads the
        missing file itself, because only it knows what to say about it."""
        self.assertEqual(gate_record.runs(self.record), ([], 0))

    def test_every_run_is_kept_in_the_order_they_were_appended(self):
        """The read keeps every run, so the one caller that needs the whole history
        gets it and the two that want a verdict per command derive it."""
        self.write(
            self.green(code=1),
            self.green(command="make full", sha="0" * 40),
            self.green(),
        )

        runs, malformed = gate_record.runs(self.record)
        self.assertEqual(malformed, 0)
        self.assertEqual(
            [(run["command"], run["exit"]) for run in runs],
            [("make quick", 1), ("make full", 0), ("make quick", 0)],
        )

    def test_the_newest_run_of_each_command_is_the_last_line_it_wrote(self):
        """The verdict per command, which is what the push denial and the
        session-start verdict each ask for."""
        self.write(self.green(code=1), self.green(command="make full"), self.green())

        latest = gate_record.newest(gate_record.runs(self.record)[0])
        self.assertEqual(sorted(latest), ["make full", "make quick"])
        self.assertEqual(latest["make quick"]["exit"], 0)

    def test_a_blank_line_is_neither_a_run_nor_a_fault(self):
        """A text file ends with a newline, so the last split is empty."""
        self.write(self.green(), "", "   ")

        self.assertEqual(len(gate_record.runs(self.record)[0]), 1)
        self.assertEqual(gate_record.runs(self.record)[1], 0)

    def test_a_line_that_is_not_json_is_malformed_and_names_its_number(self):
        """A reader that guesses at a broken line proves a gate that never ran."""
        self.write(self.green(), "make full exited 0, honestly")

        self.assertEqual(gate_record.runs(self.record)[1], 2)

    def test_a_line_that_is_not_one_object_is_malformed(self):
        """One line is one run. A list of runs on one line is another format."""
        self.write(json.dumps([json.loads(self.green())]))

        self.assertEqual(gate_record.runs(self.record)[1], 1)

    def test_a_line_that_drops_one_of_the_four_keys_is_malformed(self):
        """A run nobody can date, or cannot tie to a commit, proves nothing."""
        for key in gate_record.KEYS:
            with self.subTest(key=key):
                run = json.loads(self.green())
                del run[key]
                self.write(json.dumps(run))

                self.assertEqual(gate_record.runs(self.record)[1], 1)

    def test_a_line_whose_exit_is_not_a_number_is_malformed(self):
        """The exit code is the whole verdict, so a value nothing can compare to zero
        is not a code."""
        self.write(self.green().replace('"exit": 0', '"exit": "green"'))

        self.assertEqual(gate_record.runs(self.record)[1], 1)

    def test_the_walk_stops_at_the_first_malformed_line(self):
        """One unreadable line puts the lines around it in doubt as well. The runs
        before it are still returned, so a caller can name what it did read."""
        self.write(self.green(), "not json at all", self.green(command="make full"))

        runs, malformed = gate_record.runs(self.record)
        self.assertEqual(malformed, 2)
        self.assertEqual([run["command"] for run in runs], ["make quick"])

    # --- the at-HEAD test -----------------------------------------------------

    def test_a_short_recorded_sha_matches_by_prefix(self):
        """A recorded sha can be short, so the test is a prefix and not an
        equality."""
        head = self.head()

        self.assertTrue(gate_record.at_head(head, head))
        self.assertTrue(gate_record.at_head(head[: gate_record.SHA_PREFIX], head))

    def test_a_sha_under_the_floor_matches_nothing(self):
        """A one-character value is a prefix of every commit there is, so the floor
        is what keeps the prefix test honest."""
        head = self.head()

        self.assertFalse(gate_record.at_head(head[: gate_record.SHA_PREFIX - 1], head))
        self.assertFalse(gate_record.at_head("", head))

    def test_another_commit_and_an_unreadable_head_each_match_nothing(self):
        """Two states read the same way: the run saw another commit, or this worktree
        has no commit to compare it to."""
        self.assertFalse(gate_record.at_head("0" * 40, self.head()))
        self.assertFalse(gate_record.at_head(self.head(), ""))


if __name__ == "__main__":
    unittest.main()
