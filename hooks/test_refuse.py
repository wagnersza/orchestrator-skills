#!/usr/bin/env python3
"""The suite for `hooks/refuse.py`, the `PreToolUse` hook for `Bash`.

Each test drives the hook as its own process, with the JSON a `PreToolUse` event
carries on standard input. The assertions are the exit code and the payload the hook
printed. No test imports the hook and no test reaches for a helper inside it.

**Each denial has a matching allow case.** A hook that denies everything passes a
deny test and breaks every run. So each of the three denials is paired here with a
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

# The `gates:` block of config, as the template writes it on the `lite` profile. The
# blank `deep` field is the case that must drop out of the push check.
GATES_CONFIG = """# Orchestrator config

```yaml
tool:     orca
gates:
  profile: lite           # layers 1 to 3 run; `lite` drops layer 4
  langs:   [python]
  quick:   "make quick"   # layers 1 + 2
  full:    "make full"    # layer 3
  deep:    "{deep}"       # blank on `lite`
  story:   "/improve-codebase-architecture"  # layer 5 — advisory, not a Gate
  thresholds:
    complexity: 16
```
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

    def worker(self, deep=""):
        """A worker's worktree: a config with gates, a checklist, and one commit.

        The commit is real, because the push check compares a recorded `head_sha`
        against `git rev-parse HEAD`. It returns that sha.
        """
        self.write("docs/agents/orchestrator.md", GATES_CONFIG.format(deep=deep))
        self.write(".orchestrator/checklist-204.md", "- [ ] implement + self-test\n")
        self.git("init", "--quiet")
        self.git("add", "--all")
        self.git(
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.com",
            "commit",
            "--quiet",
            "-m",
            "the fixture commit",
        )
        return self.git("rev-parse", "HEAD").strip()

    def git(self, *arguments):
        """One `git` command inside the fixture, and what it printed."""
        proc = subprocess.run(
            ["git", *arguments],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout

    def record(self, *runs):
        """The gate record of item 204, one line per `(command, exit, sha)` run."""
        lines = [
            json.dumps(
                {
                    "command": command,
                    "exit": code,
                    "utc": "2026-08-28T09:14:02Z",
                    "head_sha": sha,
                }
            )
            for command, code, sha in runs
        ]
        return self.write(
            ".orchestrator/gates-204.jsonl", "".join(f"{line}\n" for line in lines)
        )

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
        self.allowed("git push -u origin 204-push-block")

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
        """The label denial and the teardown denial read no checklist, so a main
        checkout with no worker worktree is guarded in the same way. This is what
        stops a label write from the orchestrator session itself."""
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

    # --- denial three: a push against a record that is not green -------------

    def test_a_push_with_no_green_line_is_denied(self):
        """The deciding case. A push that skips a gate is what made "all gates are
        deterministic" false, because nothing in the stack could stop it."""
        self.worker()
        reason = self.denied("git push -u origin 204-push-block")
        self.assertIn("no green line at HEAD", reason)
        self.assertIn("the record holds no line of it", reason)

    def test_the_denial_names_each_failing_gate_and_its_command(self):
        """A worker that reads "denied" and no command guesses. So the message names
        the gate that failed and the exact command that repairs it, and it leaves out
        a gate that is already green."""
        head = self.worker()
        self.record(("make quick", 0, head))
        reason = self.denied("git push")
        self.assertIn("the `full` gate", reason)
        self.assertIn("run `make full`", reason)
        self.assertNotIn("`quick`", reason)

    def test_a_blank_gate_command_is_not_a_gate(self):
        """The `lite` profile leaves `gates.deep` blank, so no `make deep` exists to
        run. A check that read the blank field would deny every push in that repo."""
        head = self.worker()
        self.record(("make quick", 0, head), ("make full", 0, head))
        self.allowed("git push")
        # The same record, against a config that fills the field in. The gate is then
        # read, which is what proves the blank value is what dropped it.
        self.worker(deep="make deep")
        self.assertIn("the `deep` gate", self.denied("git push"))

    def test_a_stale_head_sha_is_not_green(self):
        """A commit made after a gate run means the gate runs again. Otherwise a
        worker greens the record, commits once more, and pushes the untested code."""
        self.worker()
        stale = "0" * 40
        self.record(("make quick", 0, stale), ("make full", 0, stale))
        self.assertIn("names another commit", self.denied("git push"))

    def test_a_non_zero_exit_is_not_green(self):
        """A Gate has no warning state. A non-zero exit is a stop, so the newest run
        of a red command holds the push."""
        head = self.worker()
        self.record(("make quick", 0, head), ("make full", 1, head))
        self.assertIn("exited 1", self.denied("git push"))

    def test_the_newest_line_of_a_command_is_the_one_that_counts(self):
        """A worker corrects a fault and runs the command again. The second run is
        the verdict, in both directions."""
        head = self.worker()
        self.record(
            ("make quick", 0, head), ("make full", 1, head), ("make full", 0, head)
        )
        self.allowed("git push")
        self.record(
            ("make quick", 0, head), ("make full", 0, head), ("make full", 2, head)
        )
        self.assertIn("exited 2", self.denied("git push"))

    def test_a_malformed_line_is_not_green(self):
        """One line nobody can read puts the lines around it in doubt as well. This
        is the rule the `gates-unproven` outcome already holds."""
        head = self.worker()
        self.record(("make quick", 0, head))
        with (self.root / ".orchestrator" / "gates-204.jsonl").open("a") as handle:
            handle.write("make full exited 0, honestly\n")
        self.assertIn("is not one JSON object", self.denied("git push"))

    def test_the_push_is_read_after_a_global_flag_and_inside_a_chain(self):
        """`git -C <dir> push` is a push, and so is the tail of `make full &&
        git push`. A check that read the first two words alone would miss both."""
        self.worker()
        self.assertIn("no green line", self.denied(f"git -C {self.root} push --force"))
        self.assertIn("no green line", self.denied("make full && git push"))

    def test_a_push_with_every_gate_green_goes_through(self):
        """The allow case for denial three. The block exists to stop an unproven
        push, and a proven one must cost the worker nothing."""
        head = self.worker()
        self.record(("make quick", 0, head), ("make full", 0, head))
        self.allowed("git push -u origin 204-push-block")

    def test_a_push_from_a_checkout_with_no_work_item_goes_through(self):
        """The record belongs to one work item, and the checklist names it. A main
        checkout has neither, so it proves nothing and it is not held."""
        self.write("docs/agents/orchestrator.md", GATES_CONFIG.format(deep=""))
        self.allowed("git push origin main")

    def test_a_config_with_no_gates_block_denies_no_push(self):
        """A repo configured before the gates existed names no gate command. The
        hook fails open, so that repo keeps every push it runs today."""
        self.write(".orchestrator/checklist-204.md", "- [ ] implement\n")
        self.allowed("git push")

    def test_a_git_command_that_is_not_a_push_goes_through(self):
        """Only the push verb is read. A worker commits, reads and fetches on every
        item, and a hook that held those would stop the work it protects."""
        self.worker()
        self.allowed("git commit -m 'feat: deny an unproven push'")
        self.allowed("git status --short")
        self.allowed("git fetch origin main")

    def test_prose_that_names_the_push_goes_through(self):
        """A review note quotes the rule often. The hook reads the program and its
        verb, so a quoted sentence that holds the two words is not a push."""
        self.worker()
        self.allowed("gh issue comment 204 --body 'the hook denies a git push'")
        self.allowed("echo 'run git push after make full'")

    # --- what this hook does not deny ----------------------------------------

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
