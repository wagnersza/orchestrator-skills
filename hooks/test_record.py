#!/usr/bin/env python3
"""The suite for `hooks/record.py`, the `PostToolUse` hook for `Bash`.

Each test drives the hook as its own process, with the JSON a `PostToolUse` event
carries on standard input. The assertions are the exit code and the line the hook
appended. No test imports the hook and no test reaches for a helper inside it.

The fixture is a real git repository in a temporary directory, so `head_sha` is a
real commit and a test can tie a line to it. There is no network and no login.

**A completed command and a failed command arrive in different shapes.** The tool
answers a completed command with an object, and a failed one with a string that names
the exit code. The fixture builds both, because the record has to hold a red run.

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

HOOK = Path(__file__).resolve().parent / "record.py"

ITEM = "202"

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}

# The `gates:` block of the config, in the shape the template writes. `deep` is blank
# here, the way the `lite` profile leaves it, so the fixture also covers a dropped
# layer that names no command.
CONFIG = """# Orchestrator config

```yaml
tool:     orca
harness:  claude
gates:
  profile: lite           # layers 1 to 3 run
  langs:   [python]
  quick:   "make quick"   # layers 1 + 2
  full:    "make full"    # layer 3
  deep:    ""             # blank on `lite`
  story:   "/improve-codebase-architecture"  # layer 5 — advisory, not a Gate
  thresholds:
    complexity: 16
  infra:
    plan_role:    ""
```

## Notes

Nothing under here is part of the block.
"""


class RecordHook(unittest.TestCase):
    """A repository, a finished `Bash` call, and the gate record after it.

    `setUp` writes the config and the checklist, because that is the state a worker's
    worktree holds while it runs a gate. A test that wants less removes it.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.git("init", "-q", "-b", "main")
        (self.root / "README.md").write_text("fixture\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-qm", "fixture")
        self.config = self.write("docs/agents/orchestrator.md", CONFIG)
        self.checklist = self.write(f".orchestrator/checklist-{ITEM}.md", "- [ ] go\n")
        self.record = self.root / ".orchestrator" / f"gates-{ITEM}.jsonl"

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

    # --- the hook ------------------------------------------------------------

    def run_hook(self, command, response, tool_name="Bash"):
        """The hook, driven through a real `PostToolUse` event."""
        event = {
            "session_id": "fixture",
            "cwd": str(self.root),
            "hook_event_name": "PostToolUse",
            "tool_name": tool_name,
            "tool_input": {"command": command},
            "tool_response": response,
        }
        proc = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            cwd=str(self.root),
            env={**GIT_ENV, "CLAUDE_PROJECT_DIR": str(self.root)},
        )
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        self.assertEqual(proc.stdout, "", "this hook prints nothing")
        return proc

    def completed(self, command, stdout="every step passed\n"):
        """A command the tool ran to the end, in the shape it answers with."""
        return self.run_hook(
            command,
            {
                "stdout": stdout,
                "stderr": "",
                "interrupted": False,
                "isImage": False,
                "noOutputExpected": False,
            },
        )

    def failed(self, command, code=1):
        """A command that exited non-zero, in the shape the tool answers with.

        The tool reports a failure as a string, and its first line names the code.
        """
        return self.run_hook(command, f"Error: Exit code {code}\nthe step failed\n")

    def lines(self):
        """Every line of the gate record, parsed."""
        if not self.record.is_file():
            return []
        text = self.record.read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def only_line(self):
        """The one line the record holds, or a failure naming what it holds."""
        found = self.lines()
        self.assertEqual(len(found), 1, found)
        return found[0]

    # --- the marker is absent ------------------------------------------------

    def test_a_repo_with_no_marker_writes_nothing(self):
        """The hook fires after every `Bash` call in every session on the machine.
        So a repo this plugin has nothing to say about must pay nothing for it, and
        must gain no file it did not ask for."""
        self.config.unlink()
        self.checklist.unlink()
        self.completed("make quick")
        self.assertEqual(self.lines(), [])
        self.assertFalse(self.record.exists())

    def test_a_tool_that_is_not_bash_writes_nothing(self):
        """A gate is a command. So a file edit records nothing, whatever it holds."""
        self.run_hook("make quick", {"stdout": ""}, tool_name="Edit")
        self.assertEqual(self.lines(), [])

    # --- the marker is present, and no item is in context ---------------------

    def test_a_checkout_with_no_checklist_writes_nothing(self):
        """The checklist names the item, so a run outside a worker's worktree has
        no file to append to. This is what leaves a CI run with nothing to write,
        and it is not a fault."""
        self.checklist.unlink()
        self.completed("make quick")
        self.assertEqual(self.lines(), [])

    # --- the deciding case: a configured gate command -------------------------

    def test_a_configured_gate_command_appends_one_line(self):
        """The deciding case. The record is the third fact a completion signal
        reads, so the line has to carry all four keys and the real commit."""
        self.completed("make quick")
        line = self.only_line()
        self.assertEqual(line["command"], "make quick")
        self.assertEqual(line["exit"], 0)
        self.assertEqual(line["head_sha"], self.head())
        self.assertRegex(line["utc"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(sorted(line), ["command", "exit", "head_sha", "utc"])

    def test_the_line_names_the_command_the_config_holds(self):
        """The record reads as the `gates:` block names it, and never as the whole
        command line a worker typed. So one reader can group runs by layer."""
        self.completed("make full 2>&1 | tail -20")
        self.assertEqual(self.only_line()["command"], "make full")

    def test_a_non_zero_exit_appends_a_line_too(self):
        """A red run that writes no line reads as a run that never happened. So the
        code reaches the record whatever it is."""
        self.failed("make quick", code=2)
        line = self.only_line()
        self.assertEqual(line["command"], "make quick")
        self.assertEqual(line["exit"], 2)
        self.assertEqual(line["head_sha"], self.head())

    def test_a_second_run_appends_and_does_not_replace(self):
        """The record is append-only. A worker corrects a fault and runs the command
        again, and both runs stay readable."""
        self.failed("make quick")
        self.completed("make quick")
        self.assertEqual([line["exit"] for line in self.lines()], [1, 0])

    def test_each_layer_records_under_its_own_name(self):
        """Two commands are two layers. A reader needs a green line per required
        layer, so the two must not collapse into one name."""
        self.completed("make quick")
        self.completed("make full")
        self.assertEqual(
            [line["command"] for line in self.lines()], ["make quick", "make full"]
        )

    # --- a command that is not a gate ----------------------------------------

    def test_a_command_that_is_not_a_gate_writes_nothing(self):
        """Most commands are not a gate. A record that held them would say nothing
        about whether the work is proven."""
        self.completed("git status")
        self.completed("python3 -m pytest hooks/ -q")
        self.assertEqual(self.lines(), [])

    def test_a_longer_word_is_not_the_gate_command(self):
        """The match is on a word boundary. `make quickly` is another target, and a
        line under the name `make quick` for it would be false."""
        self.completed("make quickly")
        self.assertEqual(self.lines(), [])

    def test_a_blank_gate_field_matches_nothing(self):
        """`deep` is blank on the `lite` profile, so that layer names no command. A
        blank field must not match an empty string and record every call."""
        self.completed("echo done")
        self.assertEqual(self.lines(), [])

    def test_layer_five_is_not_a_gate(self):
        """The story command has no exit code, so it stops nothing and it is not a
        Gate. It must not reach the record even where a session runs it."""
        self.completed("/improve-codebase-architecture")
        self.assertEqual(self.lines(), [])

    # --- a call that reached no verdict ---------------------------------------

    def test_an_interrupted_command_writes_no_line(self):
        """An interrupted command did not finish, so it has no exit code. A zero
        for it would be a green line no command earned."""
        self.run_hook("make quick", {"stdout": "", "stderr": "", "interrupted": True})
        self.assertEqual(self.lines(), [])

    def test_a_call_the_session_never_ran_writes_no_line(self):
        """A denied call and a rejected call each answer with a string that names no
        exit code. A line the hook cannot stand behind is worse than no line."""
        self.run_hook("make quick", "Error: Permission to use Bash with command denied")
        self.run_hook("make quick", "User rejected tool use")
        self.assertEqual(self.lines(), [])

    def test_an_empty_event_writes_nothing(self):
        """A payload the hook cannot parse is not a run it can record."""
        proc = subprocess.run(
            [sys.executable, str(HOOK)],
            input="not json",
            capture_output=True,
            text=True,
            cwd=str(self.root),
            env={**GIT_ENV, "CLAUDE_PROJECT_DIR": str(self.root)},
        )
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        self.assertEqual(self.lines(), [])


if __name__ == "__main__":
    unittest.main()
