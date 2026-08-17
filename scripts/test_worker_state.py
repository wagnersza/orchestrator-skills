#!/usr/bin/env python3
"""Behaviour tests for the worker-state seam: real fixtures in, an exit code and a
line out.

Every case runs `python3 -m scripts.worker_state` as a subprocess against a real
worktree in a temp directory. Each one asserts on the exit code and the printed
line, which are the two things a caller consumes. No mock of `subprocess`, no
assertion about which internal function ran. No network and no agent run:
`--gh-fixture` stands in for the label and comment read, so `gh` is never called.
`GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` point at `os.devnull`, so the
developer's git config cannot leak into a fixture.

`ready` is tested with a real process: a short-lived `python3` child whose working
directory is the temp worktree. That is what makes the process check credible
rather than asserted. Durations are arguments, so no case here sleeps for a real
stall window.

    python3 -m pytest scripts/ -q
    python3 -m unittest discover -s scripts -t . -q     # fallback, no pytest
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
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

ITEM = 54

EXIT_COMPLETE = 0
EXIT_GONE = 3
EXIT_NOT_READY = 1
EXIT_USAGE = 64

# `phase` is a predicate, so it has two codes plus the worktree that is gone.
EXIT_DUE = 0
EXIT_NOTHING = 1

IMPL = ["in-progress", "phase:impl"]
REVIEW = ["in-progress", "phase:review"]
E2E = ["in-progress", "phase:e2e"]
CHANGES = "Verdict: request-changes"

# The pattern comes from the harness reference, never from the seam — so a test
# fixture names no harness either. This one matches the interpreter running the
# suite, which is the process the `ready` cases actually start.
PROCESS_PATTERN = "[Pp]ython"

UNTICKED = """# Checklist — 54

- [ ] implement + self-test
- [ ] commit in slices
- [ ] push the branch
"""

TICKED = UNTICKED.replace("- [ ]", "- [x]")


def git(cwd, *args):
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        env=GIT_ENV,
    )


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class WorkerStateTestCase(unittest.TestCase):
    """A worker's worktree: a real git repo on its own branch, plus a checklist.

    This is the state a tick reads. The worktree exists, the checklist file has
    boxes in it, and the branch carries the worker's commits.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        self.worktree = self.root / "worktree"
        self.worktree.mkdir()
        git(self.worktree, "init", "-q", "-b", "main")
        write(self.worktree / "README.md", "# fixture\n")
        # The checklist lives in the worktree and is gitignored, as it is for real.
        write(self.worktree / ".gitignore", ".orchestrator/\n")
        git(self.worktree, "add", "-A")
        git(self.worktree, "commit", "-qm", "base")
        git(self.worktree, "checkout", "-qb", f"{ITEM}-worker-state-seam")

        self.checklist = self.worktree / ".orchestrator" / f"checklist-{ITEM}.md"
        write(self.checklist, UNTICKED)
        self.write_fixture()

    # --- fixture helpers ----------------------------------------------------

    def write_fixture(self, comments=(), labels=()):
        """Stand in for the tracker read a phase tick makes."""
        self.fixture = self.root / "gh.json"
        self.fixture.write_text(
            json.dumps(
                {
                    "comments": {str(ITEM): list(comments)},
                    "labels": {str(ITEM): list(labels)},
                }
            )
        )

    def backdate(self, seconds):
        """Age both freshness facts, so a stall needs no real waiting.

        The commit is rewritten with an old date, and `os.utime` moves the
        checklist's write time. The predicate takes the newer of the two, so
        both must move.
        """
        old = time.time() - seconds
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime(old))
        subprocess.run(
            ["git", "-C", str(self.worktree), "commit", "-q", "--amend", "--no-edit"],
            check=True,
            capture_output=True,
            text=True,
            env={**GIT_ENV, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
        )
        os.utime(self.checklist, (old, old))

    def run_seam(self, *argv, expect=0):
        """Run the seam and return the one line it printed."""
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.worker_state", *argv],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=GIT_ENV,
        )
        self.assertEqual(proc.returncode, expect, f"stdout: {proc.stdout}")
        self.assertLessEqual(
            len(proc.stdout.strip().splitlines()),
            1,
            f"more than one line printed: {proc.stdout!r}",
        )
        return proc.stdout.strip()

    def tick(
        self,
        *extra,
        rounds=3,
        stall="4h",
        pattern=PROCESS_PATTERN,
        worktree=None,
        expect=0,
    ):
        """Ask the predicate once, the way an Item automation's precheck asks it."""
        return self.run_seam(
            "phase",
            "--item",
            str(ITEM),
            "--worktree",
            str(worktree or self.worktree),
            "--process",
            pattern,
            "--rounds",
            str(rounds),
            "--stall-after",
            stall,
            "--gh-fixture",
            str(self.fixture),
            *extra,
            expect=expect,
        )

    def marker(self, outcome, directory=None):
        """Where the back-off marker for one `(item, outcome)` pair lands."""
        base = Path(directory) if directory else self.worktree / ".orchestrator"
        return base / f"phase-{ITEM}-{outcome}.fired"

    def ready(self, *extra, worktree=None, pattern=PROCESS_PATTERN, expect=0):
        return self.run_seam(
            "ready",
            "--worktree",
            str(worktree or self.worktree),
            "--process",
            pattern,
            *extra,
            expect=expect,
        )

    def child_in(self, cwd, seconds=30):
        """A real live process whose working directory is `cwd`."""
        proc = subprocess.Popen(
            [sys.executable, "-c", f"import time; time.sleep({seconds})"],
            cwd=str(cwd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.addCleanup(self.stop, proc)
        # Wait until the child is far enough into start-up that `ps` lists it.
        for _ in range(100):
            listing = subprocess.run(
                ["ps", "-o", "pid=", "-p", str(proc.pid)], capture_output=True, text=True
            )
            if listing.stdout.strip():
                return proc
            time.sleep(0.05)
        self.fail(f"the child process {proc.pid} never appeared in ps output")

    def stop(self, proc):
        if proc.poll() is None:
            proc.kill()
        proc.wait()

    def disk_state(self):
        return sorted(
            (str(path), path.stat().st_mtime if path.is_file() else 0)
            for path in self.root.rglob("*")
        )

    def rev(self, ref):
        return subprocess.run(
            ["git", "-C", str(self.worktree), "rev-parse", ref],
            check=True,
            capture_output=True,
            text=True,
            env=GIT_ENV,
        ).stdout.strip()

    def porcelain(self):
        return subprocess.run(
            ["git", "-C", str(self.worktree), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
            env=GIT_ENV,
        ).stdout

    # --- ready: a real process, or nothing at all ---------------------------

    def test_a_live_process_in_the_worktree_is_ready(self):
        """The process check, proven against a real child rather than a mock."""
        child = self.child_in(self.worktree)

        line = self.ready()

        self.assertTrue(line.startswith("ready:"), line)
        self.assertIn(str(child.pid), line)
        self.assertIn(str(self.worktree), line)

    def test_nothing_running_in_the_worktree_is_not_ready(self):
        """Nothing to send a prompt into, so the gate fails closed."""
        line = self.ready(expect=EXIT_NOT_READY)

        self.assertTrue(line.startswith("not ready:"), line)
        self.assertIn(str(self.worktree), line)
        self.assertNotEqual(EXIT_NOT_READY, EXIT_COMPLETE)

    def test_a_process_in_another_directory_is_not_this_worktree_ready(self):
        """The worktree is half the signal, so a live agent elsewhere is not it."""
        other = self.root / "somewhere-else"
        other.mkdir()
        self.child_in(other)

        self.assertTrue(self.ready(expect=EXIT_NOT_READY).startswith("not ready:"))
        # And the same process does satisfy the gate for the directory it is in.
        self.assertTrue(self.ready(worktree=other).startswith("ready:"))

    def test_a_child_deeper_in_the_worktree_still_counts(self):
        """Inside the worktree, not equal to it — a worker can cd into a subdir."""
        deeper = self.worktree / "scripts"
        deeper.mkdir()
        self.child_in(deeper)

        self.assertTrue(self.ready().startswith("ready:"))

    def test_a_pattern_that_matches_no_process_is_not_ready(self):
        """The pattern is what varies per harness, so a wrong one must not pass."""
        self.child_in(self.worktree)

        line = self.ready(pattern="no-such-agent-process", expect=EXIT_NOT_READY)
        self.assertIn("no-such-agent-process", line)

    def test_a_removed_worktree_is_reported_as_gone_by_ready_too(self):
        """One code, one meaning: a vanished worktree is 3 in both subcommands."""
        shutil.rmtree(self.worktree)

        line = self.ready(expect=EXIT_GONE)
        self.assertTrue(line.startswith("gone:"), line)

    def test_a_usage_error_lands_outside_the_exit_contract(self):
        """A missing flag and a missing subcommand both exit 64 and print nothing,
        so neither can read as an outcome a caller acts on."""
        for argv in (("ready",), ("ready", "--worktree", str(self.worktree)), ()):
            proc = subprocess.run(
                [sys.executable, "-m", "scripts.worker_state", *argv],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                env=GIT_ENV,
            )
            self.assertEqual(proc.returncode, EXIT_USAGE, f"{argv}: {proc.stderr}")
            self.assertEqual(proc.stdout, "", argv)
            self.assertNotIn(proc.returncode, (EXIT_COMPLETE, EXIT_NOT_READY, EXIT_GONE))

    # --- phase: the predicate an Item automation runs -----------------------

    def test_a_ticked_checklist_in_the_impl_phase_is_a_due_transition(self):
        """Nothing is running here, so this also proves the Completion signal is
        read before liveness: a worker that finished and exited is not dead."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)

        line = self.tick(expect=EXIT_DUE)

        self.assertTrue(line.startswith("implementation-complete:"), line)
        self.assertIn(str(self.checklist), line)
        self.assertIn("3 of 3", line)

    def test_a_ticked_checklist_in_the_proof_phase_is_proof_complete(self):
        """The same fact, and the Phase is what names the outcome."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=E2E)

        self.assertTrue(self.tick(expect=EXIT_DUE).startswith("proof-complete:"))

    def test_an_absent_checklist_is_not_a_completed_one(self):
        """Zero boxes is not "every box ticked" — that state holds between the
        worktree and the first prompt, and it must not read as a finish."""
        self.checklist.unlink()
        self.write_fixture(labels=IMPL)
        self.child_in(self.worktree)

        line = self.tick(expect=EXIT_NOTHING)

        self.assertTrue(line.startswith("nothing:"), line)
        self.assertIn("0 of 0 boxes ticked", line)

    def test_the_phase_label_picks_the_signal_and_the_two_never_substitute(self):
        """A reviewer ticks no boxes and an implementation worker posts no verdict,
        so neither signal may stand in for the other. The label is what chooses."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=REVIEW)
        self.child_in(self.worktree)

        line = self.tick(expect=EXIT_NOTHING)
        self.assertTrue(line.startswith("nothing:"), line)
        self.assertIn("no Verdict: comment yet", line)

        # And the mirror: a verdict does not finish an item in the impl phase.
        write(self.checklist, UNTICKED)
        self.write_fixture(comments=["Verdict: approve"], labels=IMPL)
        self.assertTrue(self.tick(expect=EXIT_NOTHING).startswith("nothing:"))

    def test_a_comment_with_no_verdict_line_does_not_fire(self):
        """The literal is the signal, so prose about a verdict is not one."""
        self.write_fixture(
            comments=["I would approve this, but the verdict comes after the fix round"],
            labels=REVIEW,
        )
        self.child_in(self.worktree)

        self.assertIn("no Verdict: comment yet", self.tick(expect=EXIT_NOTHING))

    def test_each_verdict_value_is_its_own_due_transition(self):
        """Two verdicts, two responses, so the line must tell them apart."""
        for value, outcome in (
            ("approve", "verdict-approve"),
            ("request-changes", "verdict-request-changes"),
        ):
            self.write_fixture(
                comments=[f"## Findings\n\nnone of note\n\nVerdict: {value}\n"],
                labels=REVIEW,
            )
            line = self.tick(expect=EXIT_DUE)

            self.assertTrue(line.startswith(f"{outcome}:"), line)
            self.assertIn(f"Verdict: {value}", line)
            self.assertIn("round 1 of 3", line)
            self.assertIn(f"#{ITEM}", line)

    def test_rounds_exhausted_fires_at_the_passed_in_bound_and_never_at_three(self):
        """The bound is the argument, so the same three rounds are exhausted under
        3 and not under 5, and two rounds are exhausted under 2."""
        self.write_fixture(comments=[CHANGES] * 3, labels=REVIEW)

        line = self.tick(rounds=3, expect=EXIT_DUE)
        self.assertTrue(line.startswith("rounds-exhausted:"), line)
        self.assertIn("3 Verdict: comments", line)
        self.assertIn("round bound of 3", line)

        under_five = self.tick(rounds=5, expect=EXIT_DUE)
        self.assertTrue(under_five.startswith("verdict-request-changes:"), under_five)
        self.assertIn("round 3 of 5", under_five)

        self.write_fixture(comments=[CHANGES] * 2, labels=REVIEW)
        line = self.tick(rounds=2, expect=EXIT_DUE)
        self.assertTrue(line.startswith("rounds-exhausted:"), line)
        self.assertIn("round bound of 2", line)

    def test_an_approve_at_the_bound_reads_as_approve_and_not_as_exhausted(self):
        """Both hand the item to human review, and approve is the stronger fact:
        the reviewer said yes, so no loop was cut short."""
        self.write_fixture(comments=[CHANGES, CHANGES, "Verdict: approve"], labels=REVIEW)

        line = self.tick(rounds=3, expect=EXIT_DUE)

        self.assertTrue(line.startswith("verdict-approve:"), line)
        self.assertIn("round 3 of 3", line)

    def test_the_round_count_comes_from_the_tracker_and_nothing_stores_a_counter(self):
        """A Review round number is the count of Verdict: comments, so two ticks
        read round 1 twice and round 2 arrives with a second comment."""
        self.write_fixture(comments=[CHANGES], labels=REVIEW)
        before = self.disk_state()

        self.assertIn("round 1 of 3", self.tick(expect=EXIT_DUE))
        self.assertIn("round 1 of 3", self.tick(expect=EXIT_DUE))
        self.assertEqual(before, self.disk_state())

        self.write_fixture(comments=[CHANGES] * 2, labels=REVIEW)
        self.assertIn("round 2 of 3", self.tick(expect=EXIT_DUE))

    def test_a_dead_worker_fires_with_no_stall_window_elapsed(self):
        """Nothing is listening, so a re-prompt cannot help. `dead` needs no stall
        window, so it reports in about a minute rather than in an hour."""
        self.write_fixture(labels=IMPL)

        line = self.tick(stall="4h", expect=EXIT_DUE)

        self.assertTrue(line.startswith("dead:"), line)
        self.assertIn(str(self.worktree), line)
        self.assertIn("phase:impl", line)

    def test_a_stall_needs_a_live_process_and_stale_work_product(self):
        """Both halves, because a re-prompt only helps where something listens."""
        self.write_fixture(labels=IMPL)
        self.backdate(3600)
        child = self.child_in(self.worktree)

        line = self.tick(stall="30m", expect=EXIT_DUE)
        self.assertTrue(line.startswith("stalled:"), line)
        self.assertIn(str(child.pid), line)
        self.assertIn("30m", line)

        # The same live worker with fresh work product is neither outcome.
        self.checklist.write_text(UNTICKED + "- [ ] a step added just now\n")
        self.assertTrue(self.tick(stall="30m", expect=EXIT_NOTHING).startswith("nothing:"))

    def test_dead_and_stalled_never_both_fire(self):
        """`dead` is the absence of the live process `stalled` needs, so stale work
        product with nothing running is dead and never a stall."""
        self.write_fixture(labels=IMPL)
        self.backdate(3600)

        line = self.tick(stall="30m", expect=EXIT_DUE)

        self.assertTrue(line.startswith("dead:"), line)
        self.assertNotIn("stalled", line)

    def test_a_quiet_minute_is_nothing_to_do(self):
        """The common case, and the one that must cost no tokens."""
        self.write_fixture(labels=IMPL)
        child = self.child_in(self.worktree)

        line = self.tick(stall="4h", expect=EXIT_NOTHING)

        self.assertTrue(line.startswith("nothing:"), line)
        self.assertIn("0 of 3 boxes ticked", line)
        self.assertIn(str(child.pid), line)
        self.assertNotEqual(EXIT_NOTHING, EXIT_DUE)

    def test_no_phase_label_is_human_review_and_nothing_is_due(self):
        """A ticked checklist here, so the label is what gates the outcome."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=["to-review"])

        line = self.tick(expect=EXIT_NOTHING)

        self.assertTrue(line.startswith("nothing:"), line)
        self.assertIn("no phase:* label", line)

    def test_the_back_off_marker_suppresses_a_second_fire_and_then_stops(self):
        """An unanswered wake must not queue sixty prompts in an hour, and it must
        not go silent for good either."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)

        first = self.tick("--back-off", "1h", expect=EXIT_DUE)
        self.assertTrue(first.startswith("implementation-complete:"), first)

        line = self.tick("--back-off", "1h", expect=EXIT_NOTHING)
        self.assertTrue(line.startswith("suppressed:"), line)
        self.assertIn("implementation-complete", line)
        self.assertIn("1h 0m", line)

        # The window passes, and the same outcome fires again.
        marker = self.marker("implementation-complete")
        self.assertTrue(marker.is_file())
        old = time.time() - 7200
        os.utime(marker, (old, old))
        again = self.tick("--back-off", "1h", expect=EXIT_DUE)
        self.assertTrue(again.startswith("implementation-complete:"), again)

        # It lives in the worktree, so it dies with the worktree.
        self.assertIn(str(self.worktree), str(marker))
        shutil.rmtree(self.worktree)
        self.assertFalse(marker.exists())

    def test_the_back_off_is_keyed_to_the_outcome_as_well_as_the_item(self):
        """A dead tick must not be suppressed by another outcome's fire a moment
        earlier, because the two ask for opposite responses."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        self.tick("--back-off", "1h", expect=EXIT_DUE)

        write(self.checklist, UNTICKED)  # no longer complete, and nothing is running
        line = self.tick("--back-off", "1h", stall="4h", expect=EXIT_DUE)

        self.assertTrue(line.startswith("dead:"), line)
        self.assertTrue(self.marker("dead").is_file())

    def test_the_marker_dir_argument_holds_the_marker_outside_the_worktree(self):
        """The watched worktree moves when a schedule follows the work item to a
        reviewer. A marker inside that worktree moves too, so an answered wake fires
        again from a fresh directory. One directory named by an argument fixes that."""
        shared = self.root / "markers"
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)

        first = self.tick("--back-off", "1h", "--marker-dir", str(shared), expect=EXIT_DUE)

        self.assertTrue(first.startswith("implementation-complete:"), first)
        self.assertTrue(self.marker("implementation-complete", shared).is_file())
        self.assertFalse(self.marker("implementation-complete").exists())

        # The watched worktree changes and the marker directory does not, so the
        # answered wake stays answered.
        other = self.root / "second-worktree"
        shutil.copytree(self.worktree, other)
        line = self.tick(
            "--back-off",
            "1h",
            "--marker-dir",
            str(shared),
            worktree=other,
            expect=EXIT_NOTHING,
        )
        self.assertTrue(line.startswith("suppressed:"), line)

        # And with no --marker-dir the marker lands where it always did.
        self.write_fixture(labels=E2E)
        default = self.tick("--back-off", "1h", expect=EXIT_DUE)
        self.assertTrue(default.startswith("proof-complete:"), default)
        self.assertTrue(self.marker("proof-complete").is_file())

    def test_durations_are_arguments_so_no_test_waits_for_a_real_window(self):
        """Both units and a bare number of seconds mean the same window, and a bad
        one is a usage error rather than a quiet tick."""
        self.write_fixture(labels=IMPL)
        self.backdate(120)
        self.child_in(self.worktree)

        for stall in ("60s", "1m", "60"):
            self.assertTrue(
                self.tick(stall=stall, expect=EXIT_DUE).startswith("stalled:"), stall
            )
        # The same fixture is not a stall under a window that has not passed.
        self.assertTrue(self.tick(stall="1h", expect=EXIT_NOTHING).startswith("nothing:"))

    def test_a_removed_worktree_is_gone_for_the_predicate_too(self):
        """The existing ordering guarantee, held for this subcommand: a torn-down
        worker is reported as gone and never as a stall."""
        self.write_fixture(labels=IMPL)
        self.backdate(3600)  # old enough to look like a stall, if it were checked
        shutil.rmtree(self.worktree)

        line = self.tick(stall="30m", expect=EXIT_GONE)

        self.assertTrue(line.startswith("gone:"), line)
        self.assertNotIn("stalled", line)
        self.assertNotEqual(EXIT_GONE, EXIT_DUE)

    def test_the_seven_outcomes_exit_zero_and_every_quiet_one_does_not(self):
        """The whole exit-code contract in one place. A due transition is 0 whichever
        outcome fired, and the printed line names which one. No quiet outcome can
        read as a transition."""
        due = {}

        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        due["implementation-complete"] = self.tick(expect=EXIT_DUE)

        self.write_fixture(labels=E2E)
        due["proof-complete"] = self.tick(expect=EXIT_DUE)

        self.write_fixture(comments=["Verdict: approve"], labels=REVIEW)
        due["verdict-approve"] = self.tick(expect=EXIT_DUE)

        self.write_fixture(comments=[CHANGES], labels=REVIEW)
        due["verdict-request-changes"] = self.tick(expect=EXIT_DUE)

        self.write_fixture(comments=[CHANGES] * 3, labels=REVIEW)
        due["rounds-exhausted"] = self.tick(rounds=3, expect=EXIT_DUE)

        write(self.checklist, UNTICKED)
        self.write_fixture(labels=IMPL)
        due["dead"] = self.tick(stall="4h", expect=EXIT_DUE)

        self.child_in(self.worktree)
        self.backdate(3600)
        due["stalled"] = self.tick(stall="30m", expect=EXIT_DUE)

        self.assertEqual(
            sorted(due),
            sorted(
                [
                    "implementation-complete",
                    "proof-complete",
                    "verdict-approve",
                    "verdict-request-changes",
                    "rounds-exhausted",
                    "dead",
                    "stalled",
                ]
            ),
        )
        for outcome, line in due.items():
            self.assertEqual(line.split(":")[0], outcome, line)
            self.assertEqual(len(line.splitlines()), 1, line)

        # A quiet minute, a suppressed fire and a gone worktree are the three
        # non-zero outcomes, and each one says which it is.
        self.checklist.write_text(UNTICKED)
        quiet = self.tick(stall="4h", expect=EXIT_NOTHING)

        write(self.checklist, TICKED)
        self.tick("--back-off", "1h", expect=EXIT_DUE)
        held = self.tick("--back-off", "1h", expect=EXIT_NOTHING)

        shutil.rmtree(self.worktree)
        gone = self.tick(expect=EXIT_GONE)

        self.assertEqual(
            [line.split(":")[0] for line in (quiet, held, gone)],
            ["nothing", "suppressed", "gone"],
        )

    def test_a_phase_usage_error_can_never_read_as_a_due_transition(self):
        """A flag with a typo exits outside the contract, so it is never mistaken
        for a transition the session must run."""
        base = (
            "phase",
            "--item",
            str(ITEM),
            "--worktree",
            str(self.worktree),
            "--process",
            PROCESS_PATTERN,
        )
        for argv in (
            ("phase", "--item", str(ITEM)),
            (*base, "--stall-after", "1s"),  # no --rounds, and there is no default
            (*base, "--rounds", "3"),  # no --stall-after
            (*base, "--rounds", "3", "--stall-after", "soon"),
            (*base, "--rounds", "0", "--stall-after", "1s"),
            (*base, "--rounds", "3", "--stall-after", "1s", "--back-off", "soonish"),
            (*base, "--rounds", "3", "--stall-after", "1s", "--roundz", "3"),
        ):
            proc = subprocess.run(
                [sys.executable, "-m", "scripts.worker_state", *argv],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                env=GIT_ENV,
            )
            self.assertEqual(proc.returncode, EXIT_USAGE, f"{argv}: {proc.stderr}")
            self.assertEqual(proc.stdout, "", argv)
            self.assertNotIn(proc.returncode, (EXIT_DUE, EXIT_NOTHING, EXIT_GONE))

    # --- what the seam refuses to do ---------------------------------------

    def test_the_phase_predicate_writes_nothing_but_its_back_off_marker(self):
        """The refusal case for the predicate. A live child survives every outcome,
        and the branch does not move. With no --back-off the tick leaves the disk
        byte-identical. The marker is the one file it writes, and it opts in."""
        child = self.child_in(self.worktree)
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        head = self.rev("HEAD")
        before = self.disk_state()

        self.tick(expect=EXIT_DUE)  # implementation-complete
        self.assertEqual(before, self.disk_state())

        write(self.checklist, UNTICKED)
        self.backdate(3600)
        stalled_head = self.rev("HEAD")
        stalled_state = self.disk_state()

        self.tick(stall="30m", expect=EXIT_DUE)  # stalled
        self.tick(stall="4h", expect=EXIT_NOTHING)  # nothing to do
        self.assertEqual(stalled_state, self.disk_state())

        self.write_fixture(comments=[CHANGES], labels=REVIEW)
        with_verdict = self.disk_state()
        self.tick(expect=EXIT_DUE)  # verdict-request-changes
        self.assertEqual(with_verdict, self.disk_state())

        # The one file it writes is the marker, and only where --back-off asks.
        self.write_fixture(labels=IMPL)
        write(self.checklist, TICKED)
        paths = {path for path, _ in self.disk_state()}
        self.tick("--back-off", "1h", expect=EXIT_DUE)
        added = {path for path, _ in self.disk_state()} - paths
        self.assertEqual(added, {str(self.marker("implementation-complete"))})

        # The worker is still running: no outcome killed it. No tracker write was
        # attempted, and the branch is where the worker left it with nothing staged.
        self.assertIsNone(child.poll())
        self.assertFalse((self.root / "gh.json.writes").exists())
        self.assertEqual(self.rev("HEAD"), stalled_head)
        self.assertNotEqual(stalled_head, head)  # the backdate moved it, not the seam
        self.assertEqual(self.porcelain(), "")

    def test_the_predicate_holds_no_state_that_changes_an_answer(self):
        """Two identical ticks give the same line, so a restart of the session that
        owns the schedule costs nothing."""
        self.write_fixture(labels=IMPL)
        self.backdate(3600)

        first = self.tick(stall="30m", expect=EXIT_DUE)
        second = self.tick(stall="30m", expect=EXIT_DUE)

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("dead:"), first)
        # And a fix reads as a fix, with no memory of the earlier answer.
        write(self.checklist, TICKED)
        self.assertTrue(
            self.tick(stall="30m", expect=EXIT_DUE).startswith("implementation-complete:")
        )

    def test_the_seam_names_no_harness(self):
        """The pattern comes from the harness reference, so the file holds none —
        not in a default, not in a docstring example, not anywhere."""
        source = (REPO_ROOT / "scripts" / "worker_state.py").read_text().lower()
        for harness in ("claude", "codex", "copilot", "cursor"):
            self.assertNotIn(harness, source, f"{harness!r} is named in the seam")
        # `pi` is a substring of ordinary words, so it is checked as a token.
        self.assertIsNone(re.search(r"\bpi\b", source), "'pi' is named in the seam")
        # --process is required, which is what leaves no room for a default.
        self.assertIn("no-such-agent-process", self.ready(
            pattern="no-such-agent-process", expect=EXIT_NOT_READY
        ))


if __name__ == "__main__":
    unittest.main()
