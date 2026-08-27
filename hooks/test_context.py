#!/usr/bin/env python3
"""The suite for `hooks/context.py`, the `SessionStart` hook.

Each test drives the hook as its own process, with the JSON a `SessionStart` event
carries on standard input. The assertions are the exit code and the payload the hook
printed. No test imports the hook and no test reaches for a helper inside it, so the
suite holds the same contract a running session holds.

The fixture is a real git repository in a temporary directory, plus a `gh` script on
`PATH` that answers the one tracker read with fixture JSON. So the suite needs no
network and no login. A test that wants no tracker at all leaves that script out and
asserts the named gap instead.

    python3 -m pytest hooks/ -q
    python3 -m unittest discover -s hooks -t . -q     # fallback, no pytest
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "context.py"
PLUGIN_ROOT = HOOK.parent.parent

# The item every fixture uses. One number, so a path in a failure message reads
# against the checklist that made it.
ITEM = "202"

# The git identity of a fixture commit, with the developer's own configuration
# sealed off. A machine with a signing key or a commit template must not change what
# these tests see.
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}

# The work-state label table, as the file that owns the vocabulary writes it. The
# hook reads the family from here, so the fixture carries the shape and not a copy
# of the strings in the hook.
TRACKER_CONFIG = """# Issue tracker: GitHub

## Work-state labels

| State | Label | Meaning |
|-------|-------|---------|
| ready | `ready-for-agent` | Fully specified. |
| in progress | `in-progress` | A worker owns it. |
| review | `to-review` | Waiting on a human. |
| to merge | `to-merge` | A human approved the merge. |
| done | *(closed)* | Closed. |

## Phase labels

| Phase | Label | Meaning |
|-------|-------|---------|
| implementation | `phase:impl` | A worker is implementing. |
"""


class ContextHook(unittest.TestCase):
    """A repository, a session event, and the context the hook injected.

    Every test builds the repo it needs from `setUp`'s empty checkout. So a test
    that wants no marker deletes nothing, and a test that wants a worker's facts
    writes the checklist and the record itself.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.bin = Path(self.tmp.name) / "bin"
        self.bin.mkdir()
        # A `gh` that refuses stands on `PATH` from the first line of every test.
        # So no test can reach the machine's own `gh`, and the suite is network-free
        # whether or not the test asked for a tracker answer.
        self.refusing_tracker()
        self.git("init", "-q", "-b", "main")
        (self.root / "README.md").write_text("fixture\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-qm", "fixture")

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

    def write(self, relative, text):
        """One file in the fixture, with its parent directories."""
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def config(self):
        """The repo marker: the orchestrator config in its documented place."""
        return self.write("docs/agents/orchestrator.md", "# Orchestrator config\n")

    def labels(self):
        """The file that owns the work-state vocabulary.

        The hook reads the family from here rather than carrying the strings, so a
        fixture that leaves this out is a repo whose vocabulary is unknown.
        """
        return self.write("docs/agents/issue-tracker.md", TRACKER_CONFIG)

    def stub_tracker(self, body):
        """A `gh` on `PATH` with this shell body, ahead of the machine's own."""
        script = self.bin / "gh"
        script.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        script.chmod(0o755)

    def refusing_tracker(self):
        """A `gh` that fails, which is what an unreachable tracker looks like."""
        self.stub_tracker('echo "no tracker in this fixture" >&2\nexit 1')

    def tracker(self, labels):
        """A `gh` on `PATH` that answers the one read with these labels.

        The hook reaches the tracker through the adapter, and the adapter runs
        `gh issue view <n> --json state,labels`. So a script that prints that JSON
        drives the real code path with no network and no login.
        """
        answer = json.dumps({"state": "OPEN", "labels": [{"name": n} for n in labels]})
        self.stub_tracker(f"printf '%s' '{answer}'")

    def checklist(self, ticked, unticked):
        """A checklist at a known position."""
        boxes = "".join(["- [x] done\n"] * ticked + ["- [ ] to do\n"] * unticked)
        return self.write(f".orchestrator/checklist-{ITEM}.md", boxes)

    def record(self, *lines):
        """A gate record holding these lines, in this order."""
        body = "".join(f"{json.dumps(line)}\n" for line in lines)
        return self.write(f".orchestrator/gates-{ITEM}.jsonl", body)

    def green_line(self, command="make quick", sha=None):
        """One green gate record line at the fixture's own commit."""
        return {
            "command": command,
            "exit": 0,
            "utc": "2026-08-27T09:14:02Z",
            "head_sha": self.head() if sha is None else sha,
        }

    # --- the hook ------------------------------------------------------------

    def run_hook(self, source="startup"):
        """The hook, driven through a real `SessionStart` event.

        The event carries the keys the harness sends. The environment carries the
        two variables it exports, plus the fixture's own `PATH`.
        """
        event = {
            "session_id": "fixture",
            "transcript_path": str(self.root / "transcript.jsonl"),
            "cwd": str(self.root),
            "hook_event_name": "SessionStart",
            "source": source,
        }
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            cwd=str(self.root),
            env={
                **GIT_ENV,
                "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                "CLAUDE_PROJECT_DIR": str(self.root),
                "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
            },
        )

    def injected(self, source="startup"):
        """The context block the hook injected, as one string."""
        proc = self.run_hook(source)
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        payload = json.loads(proc.stdout)
        self.assertEqual(
            payload["hookSpecificOutput"]["hookEventName"], "SessionStart", proc.stdout
        )
        return payload["hookSpecificOutput"]["additionalContext"]

    # --- the marker is absent ------------------------------------------------

    def test_a_repo_with_no_marker_gets_no_output_and_costs_nothing(self):
        """The hook fires in every session on the machine once the plugin is
        installed. So a repo this plugin has nothing to say about must pay nothing
        for it: no output, no payload and a zero exit."""
        proc = self.run_hook()
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        self.assertEqual(proc.stdout, "")

    def test_an_orchestrator_directory_alone_is_a_marker(self):
        """A worker's worktree carries the checklist directory and no config, so
        either fact turns the hook on."""
        self.checklist(1, 1)
        self.assertIn("work item 202", self.injected())

    # --- the marker is present, and no item is in context --------------------

    def test_a_checkout_with_no_checklist_gets_the_root_and_the_role(self):
        """An orchestrator session owns no work item, so there are no item facts to
        inject. It still needs the plugin root, because that is the value it
        substitutes into every seam invocation."""
        self.config()
        injected = self.injected()
        self.assertIn(str(PLUGIN_ROOT), injected)
        self.assertIn("owns no work item", injected)
        self.assertNotIn("checklist is at", injected)

    def test_the_hook_answers_a_resumed_session_the_same_way(self):
        """A compaction is where a session loses the facts, so `resume` and
        `compact` carry the same answer as `startup`."""
        self.config()
        self.assertIn(str(PLUGIN_ROOT), self.injected("compact"))

    # --- the deciding case: the three facts of a worker session --------------

    def test_a_worker_session_gets_the_label_the_position_and_a_green_record(self):
        """The deciding case. The hook reads the work-state label from the tracker,
        the position from the checklist, and the verdict from the gate record. A
        session that starts with these three facts is not working from memory."""
        self.config()
        self.labels()
        self.tracker(["in-progress", "phase:impl"])
        self.checklist(3, 7)
        self.record(self.green_line())
        injected = self.injected()
        self.assertIn("worker on work item 202", injected)
        self.assertIn("`in-progress`", injected)
        self.assertIn("3 of 10 boxes", injected)
        self.assertIn("green at HEAD", injected)

    def test_the_phase_label_is_not_the_work_state_label(self):
        """Two label families stack on one item. The hook injects the work-state
        one, so a session reads the state and not the phase."""
        self.config()
        self.labels()
        self.tracker(["phase:review", "to-review"])
        self.checklist(10, 0)
        self.assertIn("`to-review`", self.injected())

    def test_a_record_at_another_commit_is_not_green(self):
        """A green line against a stale commit proves nothing, so the hook says
        which commit the run saw rather than reporting a pass."""
        self.config()
        self.checklist(9, 1)
        self.record(self.green_line(sha="0000000"))
        self.assertIn("ran against another commit", self.injected())

    def test_a_non_zero_exit_in_the_record_is_not_green(self):
        """A red run is a stop. The hook names the command and the code, so the
        session knows which layer to run again."""
        self.config()
        self.checklist(4, 6)
        self.record({**self.green_line(), "exit": 1})
        self.assertIn("`make quick` exited 1", self.injected())

    def test_the_last_line_a_command_wrote_is_the_one_that_counts(self):
        """A worker corrects a fault and runs the command again. So a red line
        followed by a green one at the same commit is green."""
        self.config()
        self.checklist(9, 1)
        self.record({**self.green_line(), "exit": 1}, self.green_line())
        self.assertIn("green at HEAD", self.injected())

    def test_one_red_command_holds_the_whole_record_back(self):
        """Every configured layer has to be green. So a green `make quick` beside a
        red `make full` is not a green record."""
        self.config()
        self.checklist(9, 1)
        self.record(
            self.green_line(),
            {**self.green_line(command="make full"), "exit": 2},
        )
        self.assertIn("`make full` exited 2", self.injected())

    def test_a_malformed_line_is_not_green(self):
        """A line that is not JSON reads as a record nothing can trust."""
        self.config()
        self.checklist(9, 1)
        self.write(f".orchestrator/gates-{ITEM}.jsonl", "not json at all\n")
        self.assertIn("not JSON", self.injected())

    def test_an_absent_record_says_no_gate_left_a_line(self):
        """A worker that ran no gate yet is a normal state, and not a fault."""
        self.config()
        self.checklist(1, 9)
        self.assertIn("no gate command left a line yet", self.injected())

    def test_an_unreachable_tracker_is_a_named_gap(self):
        """A tracker with no `gh` on `PATH` must not read as an item that wears no
        label. The hook names the gap, because a session that reads no reason
        assumes the item wears nothing."""
        self.config()
        self.labels()
        self.checklist(2, 8)
        injected = self.injected()
        self.assertIn("the tracker read failed", injected)
        self.assertIn("2 of 10 boxes", injected)

    def test_a_repo_that_names_no_label_family_is_a_named_gap_too(self):
        """The hook copies no label string, so a repo whose tracker file is absent
        has a vocabulary the hook cannot know. It says which file is missing rather
        than guessing the four strings."""
        self.config()
        self.tracker(["in-progress"])
        self.checklist(2, 8)
        self.assertIn("names no work-state label", self.injected())

    def test_an_item_with_no_work_state_label_says_so(self):
        """An item can wear a phase label and no work state. That is a fact worth
        injecting, and it is not the same fact as a failed read."""
        self.config()
        self.labels()
        self.tracker(["wave:1"])
        self.checklist(2, 8)
        self.assertIn("the item wears no work-state label", self.injected())

    def test_an_empty_event_is_answered_with_silence(self):
        """A payload the hook cannot parse is not a session it can describe."""
        proc = subprocess.run(
            [sys.executable, str(HOOK)],
            input="not json",
            capture_output=True,
            text=True,
            cwd=str(self.root),
            env={**GIT_ENV, "CLAUDE_PROJECT_DIR": str(self.root)},
        )
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        self.assertEqual(proc.stdout, "")


if __name__ == "__main__":
    unittest.main()
