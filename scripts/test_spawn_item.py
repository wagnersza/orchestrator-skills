#!/usr/bin/env python3
"""Behaviour tests for the spawn seam: fixture state in, JSON plan out.

Every case runs `python3 -m scripts.spawn_item` as a subprocess and asserts on the
emitted plan and on what was mutated — never on a helper's return value. No network,
no GitHub, and no real harness: `--gh-fixture` stands in for every tracker read and
write, the same fixture format `scripts/close_item.py` and `scripts/worker_state.py`
already read. Where a case needs a live process for the readiness gate, it starts a
real, short-lived Python process rather than a mock — the same technique
`scripts/test_worker_state.py` already uses.

    python3 -m pytest scripts/ -q
    python3 -m unittest discover -s scripts -t . -q     # fallback, no pytest
"""

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

ITEM = 62

CONFIG_TEXT = """# fixture config

```yaml
tool:     orca
harness:  claude
yolo:     on
models:
  role_default: light
  heavy:
    model:  opus-5
    effort: high
  medium:
    model:  sonnet-5
    effort: medium
  light:
    model:  sonnet-5
    effort: low
  review:
    model:  gpt-5.6-sol
    effort: high
```
"""

# The pattern the readiness gate matches against. A real Python child answers it, the
# same fixture process `scripts/test_worker_state.py` spawns.
PROCESS_PATTERN = "[Pp]ython"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2
EXIT_USAGE = 64


class SpawnItemTestCase(unittest.TestCase):
    """A fixture config, a fixture tracker, and a plain worktree directory.

    No real git worktree is cut, per the item's own test-style note: the readiness
    gate and the tracker are the only two facts this seam reads from outside its own
    argument strings, and both are fixtures here.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        self.config = self.root / "orchestrator.md"
        self.config.write_text(CONFIG_TEXT)

        self.worktree = self.root / "worktree"

        self.sent = self.root / "sent"
        self.write_fixture()

    def write_fixture(self, labels=()):
        self.fixture = self.root / "gh.json"
        self.fixture.write_text(
            json.dumps(
                {"items": {str(ITEM): {"state": "OPEN", "labels": list(labels)}}}
            )
        )
        self.writes = self.root / "gh.json.writes"

    # --- a real, short-lived child process, for the readiness gate ----------

    def child_in(self, cwd, seconds=30):
        proc = subprocess.Popen(
            [sys.executable, "-c", f"import time; time.sleep({seconds})"],
            cwd=str(cwd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.addCleanup(self.stop, proc)
        for _ in range(100):
            listing = subprocess.run(
                ["ps", "-o", "pid=", "-p", str(proc.pid)],
                capture_output=True,
                text=True,
            )
            if listing.stdout.strip():
                return proc
            time.sleep(0.05)
        self.fail(f"the child process {proc.pid} never appeared in ps output")

    def stop(self, proc):
        if proc.poll() is None:
            proc.kill()
        proc.wait()

    # --- the CLI --------------------------------------------------------

    def spawn(
        self,
        *extra,
        worktree=None,
        process=PROCESS_PATTERN,
        panel_command="",
        schedule_command="",
        execute=False,
        expect=0,
        role="light",
        raw=False,
    ):
        argv = [
            sys.executable,
            "-m",
            "scripts.spawn_item",
            "--item",
            str(ITEM),
            "--role",
            role,
            "--config",
            str(self.config),
            "--worktree",
            str(worktree or self.worktree),
            "--process",
            process,
            "--worktree-command",
            f"mkdir -p {worktree or self.worktree}",
            "--terminal-command",
            "true",
            "--send-command",
            f"touch {self.sent}",
            "--item-title",
            "The widget cache key carries the tenant",
            "--item-body",
            "the body",
            "--checklist",
            "- [ ] implement + self-test",
            "--skill",
            "/implement",
            "--gh-fixture",
            str(self.fixture),
        ]
        if panel_command:
            argv += ["--panel-command", panel_command]
        if schedule_command:
            argv += ["--schedule-command", schedule_command]
        if execute:
            argv += ["--execute"]
        proc = subprocess.run(
            [*argv, *extra], cwd=REPO_ROOT, capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, expect, f"stderr: {proc.stderr}")
        if raw:
            return proc
        return json.loads(proc.stdout)

    def step(self, plan, number):
        for entry in plan["steps"]:
            if entry["step"] == number:
                return entry
        self.fail(f"step {number} missing: {[s['step'] for s in plan['steps']]}")

    def tracker_writes(self):
        return self.writes.read_text().splitlines() if self.writes.exists() else []

    # --- a plan that resolves ------------------------------------------------

    def test_a_plan_that_resolves_prints_the_seven_steps_in_order_and_mutates_nothing(
        self,
    ):
        """The default invocation: every precondition read, nothing changed."""
        plan = self.spawn()

        self.assertEqual(plan["mode"], "plan")
        self.assertEqual(plan["mutates"], "nothing")
        self.assertIsNone(plan["refused"])
        self.assertEqual(plan["exit_code"], EXIT_OK)
        self.assertEqual([s["step"] for s in plan["steps"]], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(
            [s["name"] for s in plan["steps"]],
            [
                "worktree",
                "terminal",
                "prompt",
                "readiness gate",
                "in-progress label",
                "follow-along panel",
                "item schedule",
            ],
        )
        self.assertFalse(self.worktree.exists())
        self.assertEqual(self.tracker_writes(), [])
        self.assertFalse(self.sent.exists())

    # --- a harness that fails the readiness gate -----------------------------

    def test_a_harness_that_fails_the_readiness_gate_refuses_and_names_the_reason(
        self,
    ):
        """No live process inside the worktree, so the gate refuses on its own."""
        self.worktree.mkdir()

        plan = self.spawn(execute=True, expect=EXIT_REFUSED)

        gate = self.step(plan, 4)
        self.assertEqual(gate["status"], "refused")
        self.assertEqual(plan["refused"]["step"], 4)
        self.assertIn("not ready", plan["refused"]["reason"])
        self.assertEqual(plan["exit_code"], EXIT_REFUSED)
        # Everything after the gate is blocked, and each one says why.
        for number in (5, 6, 7):
            self.assertEqual(self.step(plan, number)["status"], "blocked")
            self.assertIn("step 4 refused", self.step(plan, number)["note"])

    def test_a_refusal_at_the_gate_mutates_nothing(self):
        """The single most valuable assertion here: no label, and no prompt sent."""
        self.worktree.mkdir()

        self.spawn(execute=True, expect=EXIT_REFUSED)

        self.assertEqual(self.tracker_writes(), [])
        self.assertFalse(self.sent.exists())
        replan = self.spawn(expect=EXIT_REFUSED)
        self.assertEqual(self.step(replan, 5)["status"], "blocked")

    # --- the label written before the prompt ---------------------------------

    def test_the_label_is_written_before_the_prompt_is_sent(self):
        """A live process, so the gate passes. The send-command proves the order.

        The send-command only leaves its own marker where the tracker's write log
        already exists, so a send that ran before the label lands fails this
        assertion rather than passing it by accident.
        """
        self.worktree.mkdir()
        self.child_in(self.worktree)

        proved = self.root / "order-proved"
        plan = self.spawn(
            "--send-command",
            f"test -f {self.writes} && touch {proved}",
            execute=True,
            expect=EXIT_OK,
        )

        self.assertEqual(self.step(plan, 4)["status"], "done")
        self.assertEqual(self.step(plan, 5)["status"], "done")
        self.assertEqual(
            [w.split()[1:3] for w in self.tracker_writes()],
            [["issue", "edit"]],
        )
        self.assertTrue(proved.exists(), "the send ran after the label write")

    def test_a_needs_human_item_refuses_the_label_and_sends_no_prompt(self):
        """A second refusal path into the same step: the item is already parked."""
        self.write_fixture(labels=["needs-human"])
        self.worktree.mkdir()
        self.child_in(self.worktree)

        plan = self.spawn(execute=True, expect=EXIT_REFUSED)

        self.assertEqual(self.step(plan, 5)["status"], "refused")
        self.assertIn("needs-human", plan["refused"]["reason"])
        self.assertEqual(self.tracker_writes(), [])
        self.assertFalse(self.sent.exists())

    # --- the panel step present in the plan ----------------------------------

    def test_the_panel_step_is_present_whether_or_not_the_tool_supports_it(self):
        """Absence is a skip, and it is never a refusal."""
        with_command = self.spawn(panel_command="echo open {item}")
        panel = self.step(with_command, 6)
        self.assertEqual(panel["name"], "follow-along panel")
        self.assertEqual(panel["status"], "todo")
        self.assertIn("open 62", panel["command"])
        self.assertEqual(with_command["exit_code"], EXIT_OK)

        without_command = self.spawn()
        skipped = self.step(without_command, 6)
        self.assertEqual(skipped["name"], "follow-along panel")
        self.assertEqual(skipped["status"], "skipped")
        self.assertIn("unsupported", skipped["note"])
        self.assertEqual(without_command["exit_code"], EXIT_OK)

    def test_the_schedule_step_names_the_item_and_skips_without_a_command(self):
        with_command = self.spawn(schedule_command="orca schedule create item-{item}")
        schedule = self.step(with_command, 7)
        self.assertEqual(schedule["status"], "todo")
        self.assertIn("item-62", schedule["command"])

        without_command = self.step(self.spawn(), 7)
        self.assertEqual(without_command["status"], "skipped")

    # --- the model pair comes from the config, never from a flag -------------

    def test_the_model_pair_comes_from_the_config_and_not_from_a_caller_flag(self):
        plan = self.spawn(
            "--terminal-command",
            "echo {tool} {harness} {yolo} {model} {effort}",
        )
        terminal = self.step(plan, 2)
        self.assertEqual(terminal["command"], "echo orca claude on sonnet-5 low")

    # --- every Role the vocabulary names resolves -----------------------------

    def test_every_role_in_the_vocabulary_resolves_to_a_pair(self):
        """`orchestrator/CONTEXT.md` is the source, so the two lists cannot drift.

        The seam's own `ROLES` is not read here on purpose. A test that reads the list
        it is checking passes on any list.
        """
        context = (REPO_ROOT / "orchestrator" / "CONTEXT.md").read_text()
        entry = context.split("**Role**:")[1].split("_Avoid_:")[0]
        named = [
            role
            for role in ("heavy", "medium", "light", "review")
            if f"**{role}**" in entry
        ]
        self.assertEqual(
            len(named), 4, f"CONTEXT.md names {named}, expected four Roles"
        )
        for role in named:
            plan = self.spawn(
                "--terminal-command",
                "echo {model} {effort}",
                role=role,
            )
            self.assertEqual(plan["role"], role)
            self.assertNotIn("{model}", self.step(plan, 2)["command"])

    def test_the_medium_role_resolves_its_own_pair(self):
        plan = self.spawn(
            "--terminal-command",
            "echo {model} {effort}",
            role="medium",
        )
        self.assertEqual(self.step(plan, 2)["command"], "echo sonnet-5 medium")

    def test_an_unknown_name_in_the_models_block_is_reported(self):
        self.config.write_text(CONFIG_TEXT.replace("  light:", "  lite:"))
        proc = self.spawn(expect=EXIT_ERROR, raw=True)
        self.assertIn("lite", proc.stderr)
        self.assertIn("no Role", proc.stderr)

    def test_a_key_outside_the_models_block_is_not_read_as_a_role(self):
        """`gates:` holds `thresholds:` and `infra:` at the indent a Role takes.

        Both would match the role pattern, so an unscoped scan would report either one
        as an unknown Role and refuse a config that is correct.
        """
        gates = "gates:\n  thresholds:\n    coverage: 90\n  infra:\n    halt_on: none\n"
        self.config.write_text(CONFIG_TEXT.replace("```\n", gates + "```\n", 1))
        plan = self.spawn(role="medium")
        self.assertEqual(plan["role"], "medium")

    def test_a_flag_typo_exits_64(self):
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.spawn_item", "--not-a-flag"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, EXIT_USAGE)


if __name__ == "__main__":
    unittest.main()
