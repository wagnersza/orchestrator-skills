#!/usr/bin/env python3
"""The suite for `hooks/refuse.py`, the `PreToolUse` hook for `Bash`.

Each test drives the hook as its own process, with the JSON a `PreToolUse` event
carries on standard input. The assertions are the exit code and the payload the hook
printed. No test imports the hook and no test reaches for a helper inside it.

**Each denial has a matching allow case.** A hook that denies everything passes a
deny test and breaks every run. So each of the two denials is paired here with a
command that must go through.

    python3 -m pytest hooks/ -q
    python3 -m unittest discover -s hooks -t . -q     # fallback, no pytest
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "refuse.py"

# The work-state label table, as the file that owns the vocabulary writes it.
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
| review | `phase:review` | A reviewer is reading the diff. |
"""

# The seam invocation a close runs. It carries the teardown command as an argument,
# so it is the case that proves the hook reads the caller and not the words alone.
CLOSE = (
    "python3 /plugin/root/scripts/close_item.py --issue 202 --pr 203 --execute "
    "--teardown --teardown-command 'orca worktree rm --worktree id:W --force --json'"
)


class RefuseHook(unittest.TestCase):
    """A repository, a `Bash` command, and the decision the hook returned.

    `setUp` writes the marker and the label vocabulary, because that is the state
    every denial needs. A test that wants no marker deletes the config itself.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.config = self.write("docs/agents/orchestrator.md", "# Orchestrator\n")
        self.write("docs/agents/issue-tracker.md", TRACKER_CONFIG)

    # --- the fixture ---------------------------------------------------------

    def write(self, relative, text):
        """One file in the fixture, with its parent directories."""
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    # --- the hook ------------------------------------------------------------

    def run_hook(self, command, tool_name="Bash"):
        """The hook, driven through a real `PreToolUse` event."""
        event = {
            "session_id": "fixture",
            "cwd": str(self.root),
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": {"command": command, "description": "a fixture command"},
        }
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            cwd=str(self.root),
            env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(self.root)},
        )

    def allowed(self, command):
        """Assert the hook returned no decision, and return nothing."""
        proc = self.run_hook(command)
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        self.assertEqual(proc.stdout, "", f"denied: {command}")

    def denied(self, command):
        """Assert the hook denied the command, and return the reason it gave."""
        proc = self.run_hook(command)
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        payload = json.loads(proc.stdout)
        output = payload["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertEqual(output["permissionDecision"], "deny")
        # The reason travels twice, because two payload keys carry a reason to the
        # model and only one of them is confirmed on every version.
        self.assertEqual(output["permissionDecisionReason"], payload["systemMessage"])
        return output["permissionDecisionReason"]

    # --- the marker is absent ------------------------------------------------

    def test_a_repo_with_no_marker_denies_nothing(self):
        """The hook fires on every `Bash` call in every session on the machine. So a
        repo this plugin has nothing to say about must pay nothing for it, and must
        keep every command it runs today."""
        self.config.unlink()
        self.allowed('gh issue edit 202 --add-label "in-progress"')
        self.allowed("orca worktree rm --worktree id:W --force")

    def test_a_tool_that_is_not_bash_is_not_read(self):
        """The hook is registered for `Bash` alone. A second registration would
        reach it with another tool, and the command key would then be absent."""
        proc = self.run_hook(
            "gh issue edit 202 --add-label to-review", tool_name="Edit"
        )
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        self.assertEqual(proc.stdout, "")

    # --- the marker is present, and no item is in context --------------------

    def test_the_denials_need_no_work_item(self):
        """Neither denial reads a checklist, so a main checkout with no worker
        worktree is guarded in the same way. This is what stops a label write from
        the orchestrator session itself."""
        self.assertNotIn(".orchestrator", [p.name for p in self.root.iterdir()])
        self.assertIn(
            "work-state label",
            self.denied("gh issue edit 202 -R o/n --add-label to-review"),
        )

    def test_an_ordinary_command_goes_through(self):
        """Most commands are not one of the two writes. The hook must be invisible
        to them, whatever else the repo holds."""
        self.allowed("make quick")
        self.allowed("git commit -m 'feat: add the hook plane'")
        self.allowed("python3 -m pytest hooks/ -q")

    # --- denial one: a work-state label write --------------------------------

    def test_a_work_state_label_write_is_denied(self):
        """The deciding case. Only a seam writes a work-state label, so a session
        that writes one by hand puts the tracker out of step with the loop."""
        reason = self.denied('gh issue edit 202 --add-label "in-progress"')
        self.assertIn("`in-progress`", reason)
        self.assertIn("close_item.py", reason)

    def test_a_removal_is_a_write_too(self):
        """A swap is two halves of one write. Denying the add and permitting the
        remove would leave an item wearing nothing."""
        self.assertIn(
            "`to-review`", self.denied("gh issue edit 202 --remove-label to-review")
        )

    def test_the_flag_can_carry_its_value_after_an_equals_sign(self):
        """One spelling of a flag must not be a way around the denial."""
        self.assertIn(
            "`to-merge`", self.denied("gh issue edit 202 --add-label=to-merge")
        )

    def test_a_comma_separated_list_is_read_to_the_end(self):
        """A list is one flag and several labels. A work-state label in the tail of
        it is still a work-state label."""
        self.assertIn(
            "`in-progress`",
            self.denied('gh issue edit 202 --add-label "wave:1,in-progress"'),
        )

    def test_the_other_tracker_cli_is_denied_on_the_same_terms(self):
        """The label vocabulary belongs to the tracker configuration and not to one
        CLI, so the second CLI's own flag is read as well."""
        self.assertIn(
            "`in-progress`", self.denied("glab issue update 202 --label in-progress")
        )

    def test_a_label_outside_the_work_state_family_goes_through(self):
        """The allow case for denial one. A phase label, a wave label and a version
        label are each a legal write from a session, and the loop needs them."""
        self.allowed(
            "gh issue edit 202 --add-label phase:impl --remove-label phase:review"
        )
        self.allowed('gh issue edit 202 --add-label "wave:1,version:0.36.0"')

    def test_creating_the_label_in_the_repo_goes_through(self):
        """`gh label create` writes the vocabulary and no item, so it is setup work
        and never a state change."""
        self.allowed("gh label create in-progress --color FBCA04 --description 'owned'")

    def test_a_comment_that_names_a_label_goes_through(self):
        """A review note quotes a label often. The hook reads the value of a label
        flag, so prose that holds the same word is not a write."""
        self.allowed("gh issue comment 202 --body 'this item is in-progress today'")

    # --- denial two: the teardown outside the close seam ---------------------

    def test_a_teardown_by_hand_is_denied(self):
        """The deciding case. Step 8 of the close transaction removes a worktree,
        after the pull request is merged and the tree is clean. A removal outside
        that order can destroy work nobody pushed."""
        reason = self.denied("orca worktree rm --worktree id:W --force --json")
        self.assertIn("removes a worktree", reason)
        self.assertIn("close_item.py", reason)

    def test_the_other_spelling_of_the_verb_is_denied_too(self):
        """One tool says `worktree rm` and another says `worktree remove`. The hook
        matches the verb, so a tool it was never told about is covered."""
        self.assertIn(
            "removes a worktree", self.denied("git worktree remove ../202-three-hooks")
        )
        self.assertIn(
            "removes a worktree", self.denied("git -C /repo worktree remove /wt")
        )

    def test_the_close_seam_carries_the_teardown_and_goes_through(self):
        """The allow case for denial two. The seam invocation holds the teardown
        command as an argument, so a hook that read the words alone would deny the
        one caller that is permitted to run it."""
        self.allowed(CLOSE)

    def test_reading_the_worktrees_goes_through(self):
        """A list and an add are not a teardown. Denying them would stop a spawn."""
        self.allowed("git worktree list")
        self.allowed("orca worktree create --name 202-three-hooks")

    # --- what this hook does not deny ----------------------------------------

    def test_a_git_push_goes_through(self):
        """The push block is a separate work item. It needs a gate record a machine
        wrote, and the worker still writes its own, so a push denied against that
        record proves nothing."""
        self.allowed("git push -u origin 202-three-hooks")
        self.allowed("make full && git push")

    def test_an_unparsable_command_goes_through(self):
        """The hook fails open. A command it cannot split into words is a command it
        permits, because a guess denies correct work."""
        self.allowed('gh issue edit 202 --add-label "in-progress')

    def test_an_empty_event_is_answered_with_silence(self):
        """A payload the hook cannot parse is not a command it can judge."""
        proc = subprocess.run(
            [sys.executable, str(HOOK)],
            input="not json",
            capture_output=True,
            text=True,
            cwd=str(self.root),
            env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(self.root)},
        )
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        self.assertEqual(proc.stdout, "")


if __name__ == "__main__":
    unittest.main()
