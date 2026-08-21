#!/usr/bin/env python3
"""Behaviour tests for the worker-state seam: real fixtures in, an exit code and a
line out.

Every case runs `python3 -m scripts.worker_state` as a subprocess against a real
worktree in a temp directory. Each one asserts on the exit code and the printed
line, which are the two things a caller consumes. No mock of `subprocess`, no
assertion about which internal function ran. No network and no agent run:
`--gh-fixture` stands in for the label and comment read, so no tracker CLI is
called. `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` point at `os.devnull`, so the
developer's git config cannot leak into a fixture.

The cases that assert the argv of a tracker read need a real command. Each one puts
a fake CLI of that name on `PATH` (`fake_cli`). It records the argv it received and
prints canned JSON. That keeps the black-box shape of every other case: the seam
runs the command it built, and the assertion is on what the command received.
Neither CLI has to be installed. `PATH` starts with that directory for every case,
so no case here can reach a real `gh` or `glab` by accident.

The `wake` cases stand in for the send the same way (`fake_sender`). The stub logs
every argv and succeeds only for the targets a case accepts, which is how a case
walks the three targets in order. So no case needs a tool, a terminal or a network.

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

# `wake` is that predicate plus a delivery, and no path through it exits 0.
EXIT_DELIVERED = 4
EXIT_UNDELIVERED = 5

# The send template a spawn resolves from the tool file's operation 4. `sender` is a
# stub this suite writes onto `PATH`, so no test names a real Tool either.
SEND = "sender terminal send --terminal {target} --text {text} --enter"

IMPL = ["in-progress", "phase:impl"]
REVIEW = ["in-progress", "phase:review"]
E2E = ["in-progress", "phase:e2e"]
CHANGES = "Verdict: request-changes"

# The pattern comes from the harness reference, never from the seam — so a test
# fixture names no harness either. This one matches the interpreter running the
# suite, which is the process the `ready` cases actually start.
PROCESS_PATTERN = "[Pp]ython"

# The gate commands a spawn resolves from the `gates:` block of the Config. They are
# named here and passed in as a repeatable flag, because the seam holds none of its own.
QUICK = "make quick"
FULL = "make full"
GATES = ("--require-gate", QUICK, "--require-gate", FULL)

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
        # The Gate record sits beside the checklist. No case writes it in setUp: a
        # worktree with no record is the state before the first gate run.
        self.gates = self.worktree / ".orchestrator" / f"gates-{ITEM}.jsonl"
        self.write_fixture()

        # A stub CLI written here wins over an installed one, so no case can reach
        # a real tracker.
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = {**GIT_ENV, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}"}

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

    def gate_run(self, command, code=0, sha=None):
        """One line of the Gate record, as a gate command appends it.

        The sha defaults to the commit the worktree is on, which is what a green run
        records. A case that wants a stale line passes its own.
        """
        return json.dumps(
            {
                "command": command,
                "exit": code,
                "utc": "2026-08-21T09:14:02Z",
                "head_sha": self.rev("HEAD") if sha is None else sha,
            }
        )

    def write_gates(self, *lines):
        """Write the whole Gate record, one appended line per argument."""
        write(self.gates, "".join(f"{line}\n" for line in lines))

    def break_fixture(self):
        """Make the tracker read fail, the way a lost login or a broken CLI does."""
        self.fixture = self.root / "no-such-fixture.json"

    def fake_cli(self, name, **payloads):
        """A tracker CLI of `name` on `PATH`, and the file it logs its argv to.

        Each keyword is a first argument the seam can send (`issue`, `api`), and
        its value is the JSON that command prints. A command with no payload exits
        non-zero, which is how a case fires a failed read.
        """
        log = self.root / f"{name}.argv"
        cases = "\n".join(
            f"  {first}) printf '%s' '{json.dumps(payload)}' ;;"
            for first, payload in payloads.items()
        )
        script = self.bin / name
        script.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' \"$*\" >> '{log}'\n"
            'case "$1" in\n'
            f"{cases}\n"
            "  *) echo 'stub: no payload for this command' >&2; exit 9 ;;\n"
            "esac\n"
        )
        script.chmod(0o755)
        return log

    def fake_sender(self, accept=(), name="sender"):
        """A send command on `PATH` that succeeds only for a target in `accept`.

        It logs every argv it received, so a case asserts what each target got. A
        target it does not accept exits non-zero, which is how a case walks the
        ladder down to the next target. So the delivery needs no tool and no
        terminal.
        """
        log = self.root / f"{name}.argv"
        accepted = " ".join(f"'{value}'" for value in accept) or "''"
        script = self.bin / name
        script.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' \"$*\" >> '{log}'\n"
            f"for ok in {accepted}; do\n"
            '  for arg in "$@"; do\n'
            '    [ "$arg" = "$ok" ] && exit 0\n'
            "  done\n"
            "done\n"
            "echo 'stub: this target does not accept a send' >&2\n"
            "exit 7\n"
        )
        script.chmod(0o755)
        return log

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

    def run_seam(self, *argv, expect=0, lines=1):
        """Run the seam and return what it printed, with the line count asserted."""
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.worker_state", *argv],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(proc.returncode, expect, f"stdout: {proc.stdout}")
        self.assertLessEqual(
            len(proc.stdout.strip().splitlines()),
            lines,
            f"more lines printed than {lines}: {proc.stdout!r}",
        )
        return proc.stdout.strip()

    def tick_argv(
        self,
        *extra,
        rounds=3,
        stall="4h",
        pattern=PROCESS_PATTERN,
        worktree=None,
        fixture=True,
    ):
        """The flags both the predicate and the wake take, in one place.

        `fixture=False` drops `--gh-fixture`, so the tick makes a real tracker read
        against whichever stub CLI the case put on `PATH`.
        """
        return [
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
            *(("--gh-fixture", str(self.fixture)) if fixture else ()),
            *extra,
        ]

    def tick(self, *extra, expect=0, **flags):
        """Ask the predicate once, the way an Item automation's precheck asked it
        before the wake existed."""
        return self.run_seam("phase", *self.tick_argv(*extra, **flags), expect=expect)

    def wake(
        self,
        *extra,
        handle="",
        title="",
        send="",
        expect=EXIT_DELIVERED,
        lines=1,
        **flags,
    ):
        """Run the whole body of a tick: the same predicate, plus the delivery."""
        return self.run_seam(
            "wake",
            *self.tick_argv(*extra, **flags),
            *(("--handle", handle) if handle else ()),
            *(("--title", title) if title else ()),
            *(("--send-command", send) if send else ()),
            expect=expect,
            lines=lines,
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
            self.assertNotIn(
                proc.returncode, (EXIT_COMPLETE, EXIT_NOT_READY, EXIT_GONE)
            )

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

    # --- the Gate record: the third fact of the Completion signal -----------

    def test_a_ticked_checklist_with_a_green_record_is_a_finish(self):
        """The pass path. Every required layer has a green line at HEAD, so the third
        fact agrees with the ticked box and the finish stands."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        self.write_gates(self.gate_run(QUICK), self.gate_run(FULL))

        line = self.tick(*GATES, expect=EXIT_DUE)

        self.assertTrue(line.startswith("implementation-complete:"), line)
        self.assertNotIn("gates-unproven", line)

    def test_a_missing_gate_record_is_unproven(self):
        """Cause one of four. Nothing on disk says a gate ever ran, so a ticked
        checklist proves nothing and the item stops before review."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)

        line = self.tick(*GATES, expect=EXIT_DUE)

        self.assertTrue(line.startswith("gates-unproven:"), line)
        self.assertIn("a missing file", line)
        self.assertIn(str(self.gates), line)

    def test_a_malformed_line_is_unproven(self):
        """Cause two. A record with an unreadable line cannot be trusted for the
        lines around it, so the line number goes in the diagnosis."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        self.write_gates(
            self.gate_run(QUICK), "make full exited 0", self.gate_run(FULL)
        )

        line = self.tick(*GATES, expect=EXIT_DUE)

        self.assertTrue(line.startswith("gates-unproven:"), line)
        self.assertIn("a malformed line", line)
        self.assertIn("line 2", line)

        # A line that is JSON and drops one of the four keys is malformed too.
        self.write_gates(json.dumps({"command": QUICK, "exit": 0}))
        self.assertIn("a malformed line", self.tick(*GATES, expect=EXIT_DUE))

    def test_a_non_zero_exit_is_unproven(self):
        """Cause three. The gate ran, at this commit, and it was red. So the record
        is what says the work is not done."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        self.write_gates(self.gate_run(QUICK, code=1), self.gate_run(FULL))

        line = self.tick(*GATES, expect=EXIT_DUE)

        self.assertIn("a non-zero exit", line)
        self.assertIn(repr(QUICK), line)
        self.assertIn("exited 1", line)

        # A red run the worker then fixed at the same commit is a pass: the newest
        # line for a command is the one that counts.
        self.write_gates(
            self.gate_run(QUICK, code=1), self.gate_run(QUICK), self.gate_run(FULL)
        )
        self.assertTrue(
            self.tick(*GATES, expect=EXIT_DUE).startswith("implementation-complete:")
        )

    def test_a_stale_head_sha_is_unproven(self):
        """Cause four. A green run against an older commit proves nothing about the
        commit the worker is asking a reviewer to read."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        stale = "0" * 40
        self.write_gates(self.gate_run(QUICK, sha=stale), self.gate_run(FULL))

        line = self.tick(*GATES, expect=EXIT_DUE)

        self.assertIn("a stale head_sha", line)
        self.assertIn(stale, line)
        self.assertIn(self.rev("HEAD")[:7], line)

        # The short sha a gate command can write matches the same commit.
        self.write_gates(
            self.gate_run(QUICK, sha=self.rev("HEAD")[:7]), self.gate_run(FULL)
        )
        self.assertTrue(
            self.tick(*GATES, expect=EXIT_DUE).startswith("implementation-complete:")
        )

    def test_a_required_layer_with_no_line_is_unproven(self):
        """One green layer does not prove the other. The line names the command it
        wanted, because that is what a maintainer needs to correct one."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        self.write_gates(self.gate_run(QUICK))

        line = self.tick(*GATES, expect=EXIT_DUE)

        self.assertIn("a missing line", line)
        self.assertIn(repr(FULL), line)

    def test_with_no_required_gate_the_record_is_never_read(self):
        """The flag is the whole of the requirement, so a caller that names no layer
        keeps the behaviour it had before the flag existed. A red record is then not
        read at all, and the seam names no command that could stand in for it."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        self.write_gates(self.gate_run(QUICK, code=1, sha="0" * 40))

        self.assertTrue(
            self.tick(expect=EXIT_DUE).startswith("implementation-complete:")
        )

    def test_gates_unproven_never_competes_with_dead_or_stalled(self):
        """It fires in place of the finish, so it needs a ticked checklist. An
        unticked one is what the other two need, and no tick can reach both."""
        self.write_fixture(labels=IMPL)
        self.backdate(3600)

        # No live process and an unticked checklist: `dead` still owns this tick.
        self.assertTrue(
            self.tick(*GATES, stall="30m", expect=EXIT_DUE).startswith("dead:")
        )

        # A live process and stale work product: `stalled` still owns it.
        self.child_in(self.worktree)
        self.assertTrue(
            self.tick(*GATES, stall="30m", expect=EXIT_DUE).startswith("stalled:")
        )

        # And the ticked checklist is what hands the tick to the record.
        write(self.checklist, TICKED)
        line = self.tick(*GATES, stall="30m", expect=EXIT_DUE)
        self.assertTrue(line.startswith("gates-unproven:"), line)

    def test_gates_unproven_shares_the_back_off_window(self):
        """One marker per (item, outcome) pair, and this outcome is one more pair. So
        an unanswered re-prompt does not repeat every minute."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)

        first = self.tick(*GATES, "--back-off", "1h", expect=EXIT_DUE)
        held = self.tick(*GATES, "--back-off", "1h", expect=EXIT_NOTHING)

        self.assertTrue(first.startswith("gates-unproven:"), first)
        self.assertTrue(held.startswith("suppressed:"), held)
        self.assertIn("gates-unproven", held)
        self.assertTrue(self.marker("gates-unproven").is_file())

        # And a green record fires the finish on the next tick, which is a different
        # pair and therefore a different marker.
        self.write_gates(self.gate_run(QUICK), self.gate_run(FULL))
        fixed = self.tick(*GATES, "--back-off", "1h", expect=EXIT_DUE)
        self.assertTrue(fixed.startswith("implementation-complete:"), fixed)

    def test_the_seam_names_no_gate_command(self):
        """The required layers arrive as a repeatable flag, so the module holds no
        gate command in a default, a help string or a docstring example."""
        source = (REPO_ROOT / "scripts" / "worker_state.py").read_text()

        for command in (QUICK, FULL, "make deep", "checks.sh"):
            self.assertNotIn(command, source, f"{command!r} is named in the seam")

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
            comments=[
                "I would approve this, but the verdict comes after the fix round"
            ],
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
        self.write_fixture(
            comments=[CHANGES, CHANGES, "Verdict: approve"], labels=REVIEW
        )

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
        self.assertTrue(
            self.tick(stall="30m", expect=EXIT_NOTHING).startswith("nothing:")
        )

    def test_dead_and_stalled_never_both_fire(self):
        """`dead` is the absence of the live process `stalled` needs, so stale work
        product with nothing running is dead and never a stall."""
        self.write_fixture(labels=IMPL)
        self.backdate(3600)

        line = self.tick(stall="30m", expect=EXIT_DUE)

        self.assertTrue(line.startswith("dead:"), line)
        self.assertNotIn("stalled", line)

    def test_a_reviewer_is_never_stalled_by_the_commit_it_inherited(self):
        """A reviewer's worktree holds the implementation's commit and checklist, so
        both are already stale on its first minute. In `phase:review` the seam reads
        neither one, and the freshness fact is the newest `Verdict:` comment. With no
        verdict, no stall can be proven, so a long first read is a quiet tick."""
        self.write_fixture(labels=REVIEW)
        self.backdate(3600)
        child = self.child_in(self.worktree)

        line = self.tick(stall="30m", expect=EXIT_NOTHING)

        self.assertTrue(line.startswith("nothing:"), line)
        self.assertNotIn("stalled", line)
        self.assertIn("no Verdict: comment yet", line)
        # The same stale state in the implementation phase is a stall, which is what
        # makes this the phase's rule and not a dropped signal.
        self.write_fixture(labels=IMPL)
        self.assertTrue(self.tick(stall="30m", expect=EXIT_DUE).startswith("stalled:"))

        # And dropping the stall clock costs no coverage of the failure that
        # matters: a reviewer with no live process is dead, with no window elapsed.
        self.write_fixture(labels=REVIEW)
        self.stop(child)
        dead = self.tick(stall="4h", expect=EXIT_DUE)
        self.assertTrue(dead.startswith("dead:"), dead)
        self.assertIn("phase:review", dead)

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

    def test_an_unreadable_tracker_read_is_an_outcome_and_not_a_silence(self):
        """21 failed reads looked like 21 quiet minutes, because a failed read exited
        1. It is an outcome now, and no phase label gates it: a read that failed
        cannot say which phase the item is in. The back-off holds it like any
        other, so one broken read costs one report per window."""
        self.break_fixture()

        line = self.tick("--back-off", "1h", expect=EXIT_DUE)

        self.assertTrue(line.startswith("unreadable:"), line)
        self.assertIn(f"#{ITEM}", line)
        held = self.tick("--back-off", "1h", expect=EXIT_NOTHING)
        self.assertTrue(held.startswith("suppressed:"), held)
        self.assertIn("unreadable", held)

        # The same outcome for the fault that fired it live: the tracker CLI itself
        # failed, so the line carries the command that failed.
        self.fake_cli("gh")
        broken = self.tick("--repo", "owner/name", fixture=False, expect=EXIT_DUE)
        self.assertTrue(broken.startswith("unreadable:"), broken)
        self.assertIn("gh issue view", broken)
        self.assertEqual(len(broken.splitlines()), 1, broken)

    def test_the_marker_dir_argument_holds_the_marker_outside_the_worktree(self):
        """The watched worktree moves when a schedule follows the work item to a
        reviewer. A marker inside that worktree moves too, so an answered wake fires
        again from a fresh directory. One directory named by an argument fixes that."""
        shared = self.root / "markers"
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)

        first = self.tick(
            "--back-off", "1h", "--marker-dir", str(shared), expect=EXIT_DUE
        )

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

    def test_the_glab_reads_carry_the_host_where_each_one_needs_it(self):
        """Two reads, two places for the host. A bare owner/name in the API path
        resolves against the CLI's default server, which is the fault this closes.
        The stub CLI records the argv, so neither CLI has to be installed."""
        log = self.fake_cli(
            "glab",
            issue={"labels": ["in-progress", "phase:review"]},
            api=[{"body": "Verdict: approve"}],
        )

        line = self.tick(
            "--tracker-cli",
            "glab",
            "--tracker-host",
            "gitlab.example.com",
            "--repo",
            "team/thing",
            fixture=False,
            expect=EXIT_DUE,
        )

        self.assertTrue(line.startswith("verdict-approve:"), line)
        self.assertEqual(
            log.read_text().splitlines(),
            [
                f"issue view {ITEM} -F json -R gitlab.example.com/team/thing",
                f"api projects/team%2Fthing/issues/{ITEM}/notes "
                "--hostname gitlab.example.com",
            ],
        )

    def test_the_gh_argv_is_unchanged_and_grows_no_host_flag(self):
        """The default tracker reads exactly what it read before these arguments
        existed, host or no host. So a caller that passes neither one cannot notice
        that the other builder exists."""
        log = self.fake_cli(
            "gh",
            issue={
                "labels": [{"name": "phase:review"}],
                "comments": [{"body": "Verdict: approve"}],
            },
        )
        expected = f"issue view {ITEM} --json comments,labels --repo owner/name"

        line = self.tick("--repo", "owner/name", fixture=False, expect=EXIT_DUE)
        self.assertTrue(line.startswith("verdict-approve:"), line)

        self.tick(
            "--repo",
            "owner/name",
            "--tracker-cli",
            "gh",
            "--tracker-host",
            "github.example.com",
            fixture=False,
            expect=EXIT_DUE,
        )
        self.assertEqual(log.read_text().splitlines(), [expected, expected])

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
        self.assertTrue(
            self.tick(stall="1h", expect=EXIT_NOTHING).startswith("nothing:")
        )

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

    def test_the_nine_outcomes_exit_zero_and_every_quiet_one_does_not(self):
        """The whole exit-code contract in one place. A due transition is 0 whichever
        outcome fired, and the printed line names which one. No quiet outcome can
        read as a transition."""
        due = {}

        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        due["implementation-complete"] = self.tick(expect=EXIT_DUE)

        self.write_fixture(labels=E2E)
        due["proof-complete"] = self.tick(expect=EXIT_DUE)

        # The same ticked checklist, with a required layer nothing on disk proves.
        self.write_fixture(labels=IMPL)
        due["gates-unproven"] = self.tick(*GATES, expect=EXIT_DUE)

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

        self.break_fixture()
        due["unreadable"] = self.tick(expect=EXIT_DUE)
        self.write_fixture(labels=IMPL)

        self.assertEqual(
            sorted(due),
            sorted(
                [
                    "implementation-complete",
                    "proof-complete",
                    "gates-unproven",
                    "verdict-approve",
                    "verdict-request-changes",
                    "rounds-exhausted",
                    "dead",
                    "stalled",
                    "unreadable",
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

    # --- wake: the whole body of a tick -------------------------------------

    def complete_line(self):
        """The line a ticked checklist prints, with the path the seam resolves."""
        checklist = (
            Path(os.path.realpath(self.worktree))
            / ".orchestrator"
            / f"checklist-{ITEM}.md"
        )
        return f"implementation-complete: every box in {checklist} is ticked (3 of 3)"

    def test_a_due_transition_delivers_to_the_handle_and_exits_non_zero(self):
        """The handle is target one, and the argv it receives is the send template
        with the whole printed line in it. The exit code is not 0, so the automation
        records the run as skipped and its provider never loads."""
        log = self.fake_sender(accept=("H1",))
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)

        line = self.wake(handle="H1", title="orchestrator", send=SEND)

        self.assertEqual(
            line, f"delivered: {self.complete_line()} — the terminal handle H1 took it"
        )
        self.assertNotEqual(EXIT_DELIVERED, EXIT_DUE)
        self.assertEqual(
            log.read_text().splitlines(),
            [f"terminal send --terminal H1 --text {self.complete_line()} --enter"],
        )

    def test_a_failed_send_falls_back_to_the_title_and_then_to_a_comment(self):
        """Three targets in one order, and the first that succeeds ends the delivery.
        A stale handle then costs one failed send rather than a lost wake."""
        log = self.fake_sender(accept=("orchestrator",))
        comments = self.fake_cli("gh", issue={})
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)

        line = self.wake(
            "--repo", "owner/name", handle="H1", title="orchestrator", send=SEND
        )

        self.assertIn("the terminal title orchestrator took it", line)
        self.assertEqual(
            log.read_text().splitlines(),
            [
                f"terminal send --terminal H1 --text {self.complete_line()} --enter",
                "terminal send --terminal orchestrator --text "
                f"{self.complete_line()} --enter",
            ],
        )
        # The ladder stopped at target two, so the tracker was never asked.
        self.assertFalse(comments.exists())

        # Neither terminal takes it now, so the comment does. That records the
        # transition late rather than losing it.
        self.fake_sender(accept=())
        line = self.wake(
            "--repo", "owner/name", handle="H1", title="orchestrator", send=SEND
        )

        self.assertIn(f"a comment on work item #{ITEM} took it", line)
        self.assertEqual(
            comments.read_text().splitlines(),
            [f"issue comment {ITEM} --body {self.complete_line()} --repo owner/name"],
        )

    def test_a_wake_that_no_target_takes_prints_every_failure(self):
        """A maintainer who got no wake has to read why, and the three causes ask for
        three different repairs. So every failure is printed, not just the last."""
        self.fake_sender(accept=())
        self.fake_cli("gh")  # no payload, so the comment fails as well
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)

        out = self.wake(
            "--repo",
            "owner/name",
            handle="H1",
            title="orchestrator",
            send=SEND,
            expect=EXIT_UNDELIVERED,
            lines=4,
        )

        printed = out.splitlines()
        self.assertEqual(
            printed[0], f"undelivered: {self.complete_line()} — no target took it"
        )
        self.assertEqual(len(printed), 4, out)
        for what in (
            "the terminal handle H1",
            "the terminal title orchestrator",
            f"a comment on work item #{ITEM}",
        ):
            self.assertTrue(
                any(what in row and "exited" in row for row in printed[1:]), what
            )

    def test_a_quiet_tick_delivers_nothing(self):
        """The common case. Nothing is due, so nothing is sent and no command runs."""
        log = self.fake_sender(accept=("H1",))
        self.write_fixture(labels=IMPL)
        self.child_in(self.worktree)

        line = self.wake(handle="H1", send=SEND, expect=EXIT_NOTHING)

        self.assertTrue(line.startswith("nothing:"), line)
        self.assertFalse(log.exists())

    def test_a_suppressed_outcome_delivers_nothing(self):
        """The back-off window is unchanged, and it is what stops one unanswered wake
        from being delivered sixty times in an hour."""
        log = self.fake_sender(accept=("H1",))
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)

        first = self.wake("--back-off", "1h", handle="H1", send=SEND)
        held = self.wake(
            "--back-off", "1h", handle="H1", send=SEND, expect=EXIT_NOTHING
        )

        self.assertTrue(first.startswith("delivered:"), first)
        self.assertTrue(held.startswith("suppressed:"), held)
        self.assertEqual(len(log.read_text().splitlines()), 1, log.read_text())

    def test_no_wake_path_exits_zero_so_no_agent_runs_on_a_tick(self):
        """Exit 0 is the one code that loads an automation's provider. Five paths,
        and none of them is 0: delivered, undelivered, a quiet tick, a suppressed
        fire and a worktree that is gone."""
        self.fake_sender(accept=("H1",))
        codes = {}

        self.write_fixture(labels=IMPL)
        self.child_in(self.worktree)
        codes["nothing"] = EXIT_NOTHING
        self.assertTrue(
            self.wake(handle="H1", send=SEND, expect=EXIT_NOTHING).startswith(
                "nothing:"
            )
        )

        write(self.checklist, TICKED)
        codes["delivered"] = EXIT_DELIVERED
        self.assertTrue(
            self.wake("--back-off", "1h", handle="H1", send=SEND).startswith(
                "delivered:"
            )
        )

        codes["suppressed"] = EXIT_NOTHING
        self.assertTrue(
            self.wake(
                "--back-off", "1h", handle="H1", send=SEND, expect=EXIT_NOTHING
            ).startswith("suppressed:")
        )

        self.fake_sender(accept=())
        self.fake_cli("gh")
        codes["undelivered"] = EXIT_UNDELIVERED
        self.assertTrue(
            self.wake(
                handle="H1", send=SEND, expect=EXIT_UNDELIVERED, lines=3
            ).startswith("undelivered:")
        )

        shutil.rmtree(self.worktree)
        codes["gone"] = EXIT_GONE
        self.assertTrue(
            self.wake(handle="H1", send=SEND, expect=EXIT_GONE).startswith("gone:")
        )

        self.assertEqual(len(codes), 5)
        self.assertNotIn(EXIT_DUE, codes.values())

    def test_a_send_command_that_names_no_placeholder_is_a_usage_error(self):
        """A template with no {target} sends the wake nowhere, and a template with no
        {text} sends an empty one. Both would do it silently, so both are usage
        errors and neither can read as an outcome."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)

        for template in (
            "sender terminal send --terminal {target}",
            "sender terminal send --text {text}",
            "sender terminal send --terminal 'H1 --text {text}",
        ):
            self.assertEqual(
                self.wake(send=template, expect=EXIT_USAGE, lines=0), "", template
            )

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
            self.tick(stall="30m", expect=EXIT_DUE).startswith(
                "implementation-complete:"
            )
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
        self.assertIn(
            "no-such-agent-process",
            self.ready(pattern="no-such-agent-process", expect=EXIT_NOT_READY),
        )

    def test_the_seam_names_no_tool(self):
        """The send command is a template the spawn resolves from the tool file's
        operation 4, so the module names no Tool in a command, a default or an
        example. The one place a tool name may appear is a citation of the reference
        file that records a measurement, and this asserts every hit is one of those."""
        source = (REPO_ROOT / "scripts" / "worker_state.py").read_text().lower()
        for tool in ("orca", "cmux", "herdr"):
            self.assertEqual(
                source.count(tool),
                source.count(f"references/tools/{tool}.md"),
                f"{tool!r} is named in the seam outside a citation of its file",
            )


if __name__ == "__main__":
    unittest.main()
