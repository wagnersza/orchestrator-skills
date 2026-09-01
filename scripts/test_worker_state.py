#!/usr/bin/env python3
"""Behaviour tests for the worker-state seam: real fixtures in, an exit code and a
line out.

Every case reads a real worktree in a temp directory, and asserts on the exit code and
the printed line. Those are the two things a caller consumes. No mock of `subprocess`,
no assertion about which internal function ran. No network and no agent run: a fixture
file stands in for the label read and the comment read, so no tracker
CLI is called. `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` point at `os.devnull`, so
the developer's git config cannot leak into a fixture.

**An outcome case asks the predicate in process** (`ask`). It builds one **Tracker
adapter** over the fixture file and calls `phase` with it, the way `main` calls it.
Every argument past the fifth is named. So the case reads as the question it asks, and
in-process line coverage measures the module the case exercises.

**A transition case asks the tick the same way** (`apply`), and then reads the tracker
writes back out of the `<fixture>.writes` file. That file is the seam's external answer
for a write. `scripts/tracker.py` appends one line per write in fixture mode. So a case
asserts which commands a run made, with no network and no login. `writes` and `swaps`
parse that file, and `work_states_after` is where the one-label assertion reads.

**A case that proves the command line runs as a subprocess** (`run_seam`, `phase_cli`,
`tick_cli`). Those cases are the `--help` output, every usage error, the whole exit-code
table, and the argv each tracker read builds. Each one consumes the CLI contract itself,
so it must cross a process boundary to prove anything.

The cases that assert the argv of a tracker read need a real command. Each one puts
a fake CLI of that name on `PATH` (`fake_cli`). It records the argv it received and
prints canned JSON. That keeps the black-box shape of every other case: the seam
runs the command it built, and the assertion is on what the command received.
Neither CLI has to be installed. `PATH` starts with that directory for every case,
so no case here can reach a real `gh` or `glab` by accident.

`ready` is tested with a real process: a short-lived `python3` child whose working
directory is the temp worktree. That is what makes the process check credible
rather than asserted. Durations are arguments, so no case here sleeps for a real
stall window.

    python3 -m pytest scripts/ -q
    python3 -m unittest discover -s scripts -t . -q     # fallback, no pytest
"""

import ast
import itertools
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

from scripts import worker_state
from scripts.tracker import Tracker

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

# The worker's branch, and the pull request opened from it. A tick in human review reads
# the branch off the worktree, so the number is the fixture's answer and never a flag.
BRANCH = f"{ITEM}-worker-state-seam"
PR = 242

EXIT_COMPLETE = 0
EXIT_GONE = 3
EXIT_NOT_READY = 1
EXIT_USAGE = 64

# `phase` is a predicate, so it has two codes plus the worktree that is gone.
EXIT_DUE = 0
EXIT_NOTHING = 1

# `tick` is that predicate plus the write it computed, and no path through it exits 0.
EXIT_REFUSED = 2
EXIT_APPLIED = 4

CHANGES = "Verdict: request-changes"
APPROVE = "Verdict: approve"

# The literal a re-prompt writes, and the bound on how many of them a stall gets. The seam
# owns both, so this file names neither as a value of its own.
RE_PROMPT = worker_state.RE_PROMPT
RE_PROMPTS = worker_state.RE_PROMPTS

# One comment that already carries that literal, in the shape the seam writes it. A case
# that wants the second stall puts this on the item.
SENT = f"{RE_PROMPT} stalled: pid 1 is alive. Reset the worker's context"

# The one Work-state family, whose four values come from docs/agents/issue-tracker.md.
# `needs-human` is the one that stops every tick.
READY_FOR_AGENT = "ready-for-agent"
IN_PROGRESS = "in-progress"
TO_REVIEW = "to-review"
NEEDS_HUMAN = "needs-human"
WORK_STATES = (READY_FOR_AGENT, IN_PROGRESS, TO_REVIEW, NEEDS_HUMAN)

# What a work item wears in each of the two positions a worker owns. A review round is
# the same label plus a `Verdict:` comment, because the position is computed and no
# second label records it.
IMPL = [IN_PROGRESS]
HUMAN_REVIEW = [TO_REVIEW]

# The label strings this migration deleted. A repo whose migration has not run yet still
# ticks, so a read of an item that still wears one must not crash.
RETIRED = ("phase:impl", "phase:review", "phase:e2e", "to-merge")

# The three computed Positions, named by the seam rather than by this file.
POSITIONS = (
    worker_state.HUMAN_REVIEW,
    worker_state.REVIEW_ROUND,
    worker_state.IMPLEMENTATION,
)

# The board flags this migration deleted. They served the merge-requested outcome alone,
# so both subcommands lose all three.
BOARD_FLAGS = ("--board-project", "--board-owner", "--board-option")

# The wake and its five delivery flags. There is no delivery left, so no transition can
# be lost to one. No fact lives in a file a restart cannot read either.
WAKE_FLAGS = ("--handle", "--title", "--send-command", "--back-off", "--marker-dir")

# The three outcomes that carry a transition, and the label each one ends on. Every other
# outcome writes nothing.
TRANSITIONS = {
    "implementation-complete": TO_REVIEW,
    "verdict-approve": TO_REVIEW,
    "rounds-exhausted": TO_REVIEW,
}

# Every work-state label a transition can legally start from. An item at `to-review` is in
# human review, which is the one position no transition is due in, so it is not a
# predecessor. An item wearing `needs-human` stops every tick.
PREDECESSORS: tuple[list[str], ...] = ([IN_PROGRESS], [READY_FOR_AGENT], [])

# The board coordinates and the two column names a start gate reads. They come from the
# Project board section of docs/agents/issue-tracker.md, so the seam holds none of them.
# `READY_LANE` is the column before the start column, which is the maintainer's own lane.
BOARD_PROJECT = 6
BOARD_OWNER = "someone"
START_COLUMN = "To do"
READY_LANE = "Ready"

# The three answers the start gate gives, named by the seam rather than by this file.
START = worker_state.START
ONE_FACT = worker_state.ONE_FACT
NO_FACT = worker_state.NO_FACT

# The stall windows, in the seconds the predicate takes. The command line takes `30m` and
# `1h`, and one case still proves that parse.
HALF_HOUR = 30 * 60
AN_HOUR = 60 * 60
FOUR_HOURS = 4 * 60 * 60

# The pattern comes from the harness reference, never from the seam — so a test
# fixture names no harness either. This one matches the interpreter running the
# suite, which is the process the `ready` cases actually start.
PROCESS_PATTERN = "[Pp]ython"

# The gate commands a spawn resolves from the `gates:` block of the Config. They are
# named here and passed in as a repeatable flag, because the seam holds none of its own.
QUICK = "make quick"
FULL = "make full"
GATES = ("--require-gate", QUICK, "--require-gate", FULL)
REQUIRED = (QUICK, FULL)

UNTICKED = """# Checklist — 54

- [ ] implement + self-test
- [ ] commit in slices
- [ ] push the branch
"""

TICKED = UNTICKED.replace("- [ ]", "- [x]")

# The proof box the checklist template ships where `run_recipe` is not blank. It is one
# more box and nothing else, which is the whole point of it.
PROOF_BOX = "- [ ] prove the feature works through the browser surface\n"


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
        git(self.worktree, "checkout", "-qb", BRANCH)

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

    def write_fixture(self, comments=(), labels=(), pull_requests=None, board=None):
        """Stand in for the tracker reads a tick makes.

        One record for this item, in the one format `scripts/tracker.py` documents. The
        labels and the comments are every fact the tick reads in implementation, because a
        position is computed from them and from the checklist file.

        `pull_requests` is the second record type of that same format. A tick in human
        review reads it through the branch, so each record carries a `head` key.

        `board` is the `Status` name on this item's card, which is the second fact of a
        start gate. `None` leaves the key out, and that is a fixture with no card at all.
        """
        self.fixture = self.root / "gh.json"
        record = {"comments": list(comments), "labels": list(labels)}
        if board is not None:
            record["board"] = board
        self.fixture.write_text(
            json.dumps(
                {
                    "items": {str(ITEM): record},
                    "pull_requests": dict(pull_requests or {}),
                }
            )
        )
        # A fresh fixture is a fresh case, so the write log starts empty too. A case that
        # asserts on two ticks of one fixture writes the fixture once.
        (self.root / "gh.json.writes").unlink(missing_ok=True)

    def pull_request(self, state="MERGED", head=None, merge_commit=None):
        """One pull request record for this worktree's branch, in the one format.

        `merge_commit` defaults to the commit `main` already holds, so step 5 of the close
        reads the merge as landed and pulls nothing. A case that wants that pull to really
        run passes a commit the checkout does not hold.
        """
        return {
            str(PR): {
                "state": state,
                "merge_commit": self.rev("main")
                if merge_commit is None
                else merge_commit,
                "head": BRANCH if head is None else head,
            }
        }

    def teardown_marker(self):
        """The file the teardown command touches, so a case reads whether step 8 ran."""
        return self.root / "teardown-ran"

    def origin(self):
        """A bare remote behind this worktree, created once."""
        path = self.root / "origin.git"
        if not path.exists():
            subprocess.run(
                ["git", "init", "-q", "--bare", str(path)], check=True, env=GIT_ENV
            )
            git(self.worktree, "remote", "add", "origin", str(path))
            git(self.worktree, "push", "-q", "origin", "main")
        return path

    def checkout(self):
        """The checkout the close pulls the merge into, created once.

        **It is never the item's worktree.** A worker's worktree is a linked one, and
        `git fetch origin main:main` there exits 128 with `refusing to fetch into branch`,
        because the sibling checkout holds that branch. So a close case needs the real
        shape: a checkout on the default branch, with an origin behind it.
        """
        path = self.root / "checkout"
        if not path.exists():
            subprocess.run(
                ["git", "clone", "-q", str(self.origin()), str(path)],
                check=True,
                env=GIT_ENV,
            )
        return path

    def merge_onto_origin(self):
        """One commit on the remote's default branch, and the sha of it.

        A checkout cloned before this call does not hold it, so step 5 of the close has a
        real pull to make.
        """
        ahead = self.root / "ahead"
        subprocess.run(
            ["git", "clone", "-q", str(self.origin()), str(ahead)],
            check=True,
            env=GIT_ENV,
        )
        write(ahead / "merged.txt", "the merge landed\n")
        git(ahead, "add", "-A")
        git(ahead, "commit", "-qm", "the merge landed")
        git(ahead, "push", "-q", "origin", "main")
        return subprocess.run(
            ["git", "-C", str(ahead), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            env=GIT_ENV,
        ).stdout.strip()

    def close_flags(self):
        """The three close flags a tick carries: `(checkout, default branch, teardown)`.

        The teardown command is a real shell command. So a case proves step 8 ran by
        reading the file that command leaves, and no case removes a real worktree.
        """
        return (str(self.checkout()), "main", f"touch {self.teardown_marker()}")

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
        """Write the whole Gate record, one appended line per argument.

        With no lines there is no file at all. That is the state before the first gate
        run, and the first of the four causes a refusal names.
        """
        if not lines:
            self.gates.unlink(missing_ok=True)
            return
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

    def writes(self):
        """Every tracker write this case's run made, as a list of argv strings.

        `scripts/tracker.py` appends one line per write to `<fixture>.writes` in fixture
        mode. So this file is the seam's external answer for a write, and an empty list is
        a run that wrote nothing at all.
        """
        log = self.fixture.parent / (self.fixture.name + ".writes")
        try:
            return log.read_text().splitlines()
        except OSError:
            return []

    def swaps(self):
        """Every label write, as `(removed, added)` name lists, oldest first.

        The flags are the ones the default tracker takes. So this reads the argv the
        adapter built rather than a value the seam held.
        """
        found = []
        for line in self.writes():
            words = line.split()
            if not any(flag in words for flag in ("--remove-label", "--add-label")):
                continue
            removed, added = [], []
            for flag, name in zip(words, words[1:]):
                if flag == "--remove-label":
                    removed.append(name)
                if flag == "--add-label":
                    added.append(name)
            found.append((removed, added))
        return found

    def work_states_after(self, labels):
        """The work-state labels the item wears after this run's swaps.

        Where the one-label assertion reads. It starts from the labels the item wore, and
        it applies each swap the run made. So the answer is what the tracker holds, rather
        than what the printed line claims.
        """
        wearing = list(labels)
        for removed, added in self.swaps():
            wearing = [name for name in wearing if name not in removed]
            wearing += [name for name in added if name not in wearing]
        return [name for name in wearing if name in WORK_STATES]

    def set_up_outcome(self, outcome, labels):
        """Put the tracker and the worktree in the state one outcome fires from.

        One place, so a transition case names the outcome it wants rather than the four
        facts behind it. Every case that uses it passes a round bound of 3.
        """
        comments = {
            "implementation-complete": [],
            "verdict-approve": [APPROVE],
            "rounds-exhausted": [CHANGES] * 3,
        }[outcome]
        write(self.checklist, TICKED)
        self.write_fixture(comments=comments, labels=labels)

    def stalling(self, comments=(), labels=IMPL):
        """Put the worktree and the tracker in the state a stall fires from.

        Unticked boxes, work product older than the window, and a live process. `comments`
        is what the re-prompt count reads, so a case says how many retries went before it
        rather than how the seam stores them.
        """
        write(self.checklist, UNTICKED)
        self.write_fixture(comments=comments, labels=labels)
        self.backdate(3600)
        self.child_in(self.worktree)

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
        """The flags both subcommands take, in one place.

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

    def phase_cli(self, *extra, expect=0, **flags):
        """Ask the predicate through the command line, for a case that proves it.

        Every outcome case asks `ask` instead. This helper stays for the cases whose
        subject is the CLI: the argv a tracker read builds, a usage error, and the
        exit-code table.
        """
        return self.run_seam("phase", *self.tick_argv(*extra, **flags), expect=expect)

    def tick_cli(self, *extra, expect=EXIT_APPLIED, **flags):
        """Run the whole body of a tick through the command line."""
        return self.run_seam("tick", *self.tick_argv(*extra, **flags), expect=expect)

    def adapter(self):
        """The one Tracker adapter a run builds, over this case's fixture file.

        `main` builds it from `--tracker-cli`, `--tracker-host`, `--repo` and
        `--gh-fixture`. A case that reads the fixture needs only the last of the four. A
        case that needs the other three runs the command line instead.
        """
        return Tracker(fixture=str(self.fixture))

    def ask(
        self,
        *,
        expect=EXIT_DUE,
        rounds=3,
        stall=FOUR_HOURS,
        pattern=PROCESS_PATTERN,
        worktree=None,
        **named,
    ):
        """Ask the predicate in process, through one adapter.

        Five values that describe the worker, then the adapter, then every other
        argument by name. That is the call `main` makes. The four threaded tracker
        values made this call shape impossible for a test.
        """
        code, line = worker_state.phase(
            ITEM,
            worktree or self.worktree,
            pattern,
            rounds,
            stall,
            self.adapter(),
            **named,
        )
        self.assertEqual(code, expect, line)
        self.assertEqual(len(line.splitlines()), 1, line)
        return line

    def position(self, labels, comments=(), verdict_written=None):
        """The computed Position, over the facts one tick reads.

        The checklist write time comes from the real file in this case's worktree, so
        the two review branches compare against a timestamp nothing here invented.
        """
        return worker_state.position_of(
            list(labels),
            list(comments),
            worker_state.checklist_written(self.worktree, ITEM),
            verdict_written=verdict_written,
        )

    def apply(
        self,
        *,
        expect=EXIT_APPLIED,
        rounds=3,
        stall=FOUR_HOURS,
        pattern=PROCESS_PATTERN,
        worktree=None,
        **named,
    ):
        """Run the whole body of a tick in process: the same plan, plus the write.

        The same call shape as `ask`, through one adapter, so a case reads the transition
        as the question it asks. The write lands in `<fixture>.writes`, which `writes`,
        `swaps` and `work_states_after` read back.
        """
        code, line = worker_state.tick(
            ITEM,
            worktree or self.worktree,
            pattern,
            rounds,
            stall,
            self.adapter(),
            **named,
        )
        self.assertEqual(code, expect, line)
        self.assertEqual(len(line.splitlines()), 1, line)
        return line

    def gate(self, *, expect, project=BOARD_PROJECT, owner=BOARD_OWNER, column=None):
        """Ask the start gate in process, through one adapter.

        The item, the adapter, then the three board coordinates. That is the call `main`
        makes. `column=None` means the start column, and a case that wants no board at all
        passes `project=0, owner="", column=""`.
        """
        code, line = worker_state.start(
            ITEM,
            self.adapter(),
            project,
            owner,
            START_COLUMN if column is None else column,
        )
        self.assertEqual(code, expect, line)
        self.assertEqual(len(line.splitlines()), 1, line)
        return line

    def start_cli(self, *extra, expect=EXIT_NOTHING, fixture=True, board=True):
        """Ask the start gate through the command line, for a case that proves the CLI."""
        return self.run_seam(
            "start",
            "--item",
            str(ITEM),
            *(("--gh-fixture", str(self.fixture)) if fixture else ()),
            *(
                (
                    "--board-project",
                    str(BOARD_PROJECT),
                    "--board-owner",
                    BOARD_OWNER,
                    "--start-column",
                    START_COLUMN,
                )
                if board
                else ()
            ),
            *extra,
            expect=expect,
        )

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

    def test_a_ticked_checklist_in_implementation_is_a_due_transition(self):
        """Nothing is running here, so this also proves the Completion signal is
        read before liveness: a worker that finished and exited is not dead."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)

        line = self.ask()

        self.assertTrue(line.startswith("implementation-complete:"), line)
        self.assertIn(str(self.checklist), line)
        self.assertIn("3 of 3", line)

    def test_an_absent_checklist_is_not_a_completed_one(self):
        """Zero boxes is not "every box ticked" — that state holds between the
        worktree and the first prompt, and it must not read as a finish."""
        self.checklist.unlink()
        self.write_fixture(labels=IMPL)
        self.child_in(self.worktree)

        line = self.ask(expect=EXIT_NOTHING)

        self.assertTrue(line.startswith("nothing:"), line)
        self.assertIn("0 of 0 boxes ticked", line)

    # --- the Gate record: the third fact of the Completion signal -----------

    def test_a_ticked_checklist_with_a_green_record_is_a_finish(self):
        """The pass path. Every required layer has a green line at HEAD, so the third
        fact agrees with the ticked box and the finish stands."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        self.write_gates(self.gate_run(QUICK), self.gate_run(FULL))

        line = self.ask(required=REQUIRED)

        self.assertTrue(line.startswith("implementation-complete:"), line)
        self.assertNotIn("gates-unproven", line)

    def test_a_missing_gate_record_is_unproven(self):
        """Cause one of four. Nothing on disk says a gate ever ran, so a ticked
        checklist proves nothing and the item stops before review."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)

        line = self.ask(required=REQUIRED)

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

        line = self.ask(required=REQUIRED)

        self.assertTrue(line.startswith("gates-unproven:"), line)
        self.assertIn("a malformed line", line)
        self.assertIn("line 2", line)

        # A line that is JSON and drops one of the four keys is malformed too.
        self.write_gates(json.dumps({"command": QUICK, "exit": 0}))
        self.assertIn("a malformed line", self.ask(required=REQUIRED))

    def test_a_non_zero_exit_is_unproven(self):
        """Cause three. The gate ran, at this commit, and it was red. So the record
        is what says the work is not done."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        self.write_gates(self.gate_run(QUICK, code=1), self.gate_run(FULL))

        line = self.ask(required=REQUIRED)

        self.assertIn("a non-zero exit", line)
        self.assertIn(repr(QUICK), line)
        self.assertIn("exited 1", line)

        # A red run the worker then fixed at the same commit is a pass: the newest
        # line for a command is the one that counts.
        self.write_gates(
            self.gate_run(QUICK, code=1), self.gate_run(QUICK), self.gate_run(FULL)
        )
        self.assertTrue(
            self.ask(required=REQUIRED).startswith("implementation-complete:")
        )

    def test_a_stale_head_sha_is_unproven(self):
        """Cause four. A green run against an older commit proves nothing about the
        commit the worker is asking a reviewer to read."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        stale = "0" * 40
        self.write_gates(self.gate_run(QUICK, sha=stale), self.gate_run(FULL))

        line = self.ask(required=REQUIRED)

        self.assertIn("a stale head_sha", line)
        self.assertIn(stale, line)
        self.assertIn(self.rev("HEAD")[:7], line)

        # The short sha a gate command can write matches the same commit.
        self.write_gates(
            self.gate_run(QUICK, sha=self.rev("HEAD")[:7]), self.gate_run(FULL)
        )
        self.assertTrue(
            self.ask(required=REQUIRED).startswith("implementation-complete:")
        )

    def test_a_required_layer_with_no_line_is_unproven(self):
        """One green layer does not prove the other. The line names the command it
        wanted, because that is what a maintainer needs to correct one."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        self.write_gates(self.gate_run(QUICK))

        line = self.ask(required=REQUIRED)

        self.assertIn("a missing line", line)
        self.assertIn(repr(FULL), line)

    def test_with_no_required_gate_the_record_is_never_read(self):
        """The flag is the whole of the requirement, so a caller that names no layer
        keeps the behaviour it had before the flag existed. A red record is then not
        read at all, and the seam names no command that could stand in for it."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        self.write_gates(self.gate_run(QUICK, code=1, sha="0" * 40))

        self.assertTrue(self.ask().startswith("implementation-complete:"))

    def test_gates_unproven_never_competes_with_dead_or_stalled(self):
        """It fires in place of the finish, so it needs a ticked checklist. An
        unticked one is what the other two need, and no tick can reach both."""
        self.write_fixture(labels=IMPL)
        self.backdate(3600)

        # No live process and an unticked checklist: `dead` still owns this tick.
        self.assertTrue(
            self.ask(required=REQUIRED, stall=HALF_HOUR).startswith("dead:")
        )

        # A live process and stale work product: `stalled` still owns it.
        self.child_in(self.worktree)
        self.assertTrue(
            self.ask(required=REQUIRED, stall=HALF_HOUR).startswith("stalled:")
        )

        # And the ticked checklist is what hands the tick to the record.
        write(self.checklist, TICKED)
        line = self.ask(required=REQUIRED, stall=HALF_HOUR)
        self.assertTrue(line.startswith("gates-unproven:"), line)

    def test_a_gate_record_that_proves_nothing_refuses_the_transition(self):
        """The finish no command proved must not reach review. Each of the four causes
        refuses, the item stays where it is, and the line names which cause held. A green
        record at HEAD then applies the finish on the next tick."""
        write(self.checklist, TICKED)
        causes = {
            "a missing file": (),
            "a missing line": (self.gate_run(FULL),),
            "a non-zero exit": (self.gate_run(QUICK, code=1), self.gate_run(FULL)),
            "a stale head_sha": (
                self.gate_run(QUICK, sha="0" * 40),
                self.gate_run(FULL),
            ),
        }
        for cause, lines in causes.items():
            self.write_fixture(labels=IMPL)
            self.write_gates(*lines)

            line = self.apply(required=REQUIRED, expect=EXIT_REFUSED)

            self.assertTrue(line.startswith("gates-unproven:"), line)
            self.assertIn(cause, line)
            self.assertIn("stays where it is", line)
            self.assertEqual(self.writes(), [], cause)
            self.assertEqual(self.work_states_after(IMPL), IMPL, cause)

        # And the record that does prove it applies the finish.
        self.write_fixture(labels=IMPL)
        self.write_gates(self.gate_run(QUICK), self.gate_run(FULL))
        fixed = self.apply(required=REQUIRED)
        self.assertTrue(fixed.startswith("implementation-complete:"), fixed)
        self.assertEqual(self.work_states_after(IMPL), [TO_REVIEW])

    def test_the_seam_names_no_gate_command(self):
        """The required layers arrive as a repeatable flag, so the module holds no
        gate command in a default, a help string or a docstring example."""
        source = (REPO_ROOT / "scripts" / "worker_state.py").read_text()

        for command in (QUICK, FULL, "make deep", "checks.sh"):
            self.assertNotIn(command, source, f"{command!r} is named in the seam")

    def test_the_position_picks_the_signal_and_the_two_never_substitute(self):
        """A reviewer ticks no boxes and an implementation worker posts no verdict, so
        neither signal can stand in for the other. The computed Position is what
        chooses, and a `Verdict:` comment is what puts an item in a review round."""
        write(self.checklist, TICKED)
        self.write_fixture(comments=[CHANGES], labels=IMPL)

        line = self.ask()
        self.assertTrue(line.startswith("verdict-request-changes:"), line)
        self.assertNotIn("implementation-complete", line)

        # And the mirror: with no verdict the item is in implementation, where the
        # ticked checklist is the whole signal.
        self.write_fixture(labels=IMPL)
        self.assertTrue(self.ask().startswith("implementation-complete:"))

    def test_a_comment_with_no_verdict_line_is_not_a_review_round(self):
        """The literal is the signal, so prose about a verdict is neither an outcome
        nor a Position. The item stays in implementation, where the checklist is
        read."""
        self.write_fixture(
            comments=[
                "I would approve this, but the verdict comes after the fix round"
            ],
            labels=IMPL,
        )
        self.child_in(self.worktree)

        line = self.ask(expect=EXIT_NOTHING)

        self.assertIn("0 of 3 boxes ticked", line)
        self.assertNotIn("Verdict", line)

    def test_each_verdict_value_is_its_own_due_transition(self):
        """Two verdicts, two responses, so the line must tell them apart."""
        for value, outcome in (
            ("approve", "verdict-approve"),
            ("request-changes", "verdict-request-changes"),
        ):
            self.write_fixture(
                comments=[f"## Findings\n\nnone of note\n\nVerdict: {value}\n"],
                labels=IMPL,
            )
            line = self.ask()

            self.assertTrue(line.startswith(f"{outcome}:"), line)
            self.assertIn(f"Verdict: {value}", line)
            self.assertIn("round 1 of 3", line)
            self.assertIn(f"#{ITEM}", line)

    def test_rounds_exhausted_fires_at_the_passed_in_bound_and_never_at_three(self):
        """The bound is the argument, so the same three rounds are exhausted under
        3 and not under 5, and two rounds are exhausted under 2."""
        self.write_fixture(comments=[CHANGES] * 3, labels=IMPL)

        line = self.ask(rounds=3)
        self.assertTrue(line.startswith("rounds-exhausted:"), line)
        self.assertIn("3 Verdict: comments", line)
        self.assertIn("round bound of 3", line)

        under_five = self.ask(rounds=5)
        self.assertTrue(under_five.startswith("verdict-request-changes:"), under_five)
        self.assertIn("round 3 of 5", under_five)

        self.write_fixture(comments=[CHANGES] * 2, labels=IMPL)
        line = self.ask(rounds=2)
        self.assertTrue(line.startswith("rounds-exhausted:"), line)
        self.assertIn("round bound of 2", line)

    def test_an_approve_at_the_bound_reads_as_approve_and_not_as_exhausted(self):
        """Both hand the item to human review, and approve is the stronger fact:
        the reviewer said yes, so no loop was cut short."""
        self.write_fixture(comments=[CHANGES, CHANGES, "Verdict: approve"], labels=IMPL)

        line = self.ask(rounds=3)

        self.assertTrue(line.startswith("verdict-approve:"), line)
        self.assertIn("round 3 of 3", line)

    def test_the_round_count_comes_from_the_tracker_and_nothing_stores_a_counter(self):
        """A Review round number is the count of Verdict: comments, so two ticks
        read round 1 twice and round 2 arrives with a second comment."""
        self.write_fixture(comments=[CHANGES], labels=IMPL)
        before = self.disk_state()

        self.assertIn("round 1 of 3", self.ask())
        self.assertIn("round 1 of 3", self.ask())
        self.assertEqual(before, self.disk_state())

        self.write_fixture(comments=[CHANGES] * 2, labels=IMPL)
        self.assertIn("round 2 of 3", self.ask())

    def test_a_dead_worker_fires_with_no_stall_window_elapsed(self):
        """Nothing is listening, so a re-prompt cannot help. `dead` needs no stall
        window, so it reports in about a minute rather than in an hour."""
        self.write_fixture(labels=IMPL)

        line = self.ask(stall=FOUR_HOURS)

        self.assertTrue(line.startswith("dead:"), line)
        self.assertIn(str(self.worktree), line)
        self.assertIn(worker_state.IMPLEMENTATION, line)

    def test_a_stall_needs_a_live_process_and_stale_work_product(self):
        """Both halves, because a re-prompt only helps where something listens."""
        self.write_fixture(labels=IMPL)
        self.backdate(3600)
        child = self.child_in(self.worktree)

        line = self.ask(stall=HALF_HOUR)
        self.assertTrue(line.startswith("stalled:"), line)
        self.assertIn(str(child.pid), line)
        self.assertIn("30m", line)

        # The same live worker with fresh work product is neither outcome.
        self.checklist.write_text(UNTICKED + "- [ ] a step added just now\n")
        self.assertTrue(
            self.ask(stall=HALF_HOUR, expect=EXIT_NOTHING).startswith("nothing:")
        )

    def test_dead_and_stalled_never_both_fire(self):
        """`dead` is the absence of the live process `stalled` needs, so stale work
        product with nothing running is dead and never a stall."""
        self.write_fixture(labels=IMPL)
        self.backdate(3600)

        line = self.ask(stall=HALF_HOUR)

        self.assertTrue(line.startswith("dead:"), line)
        self.assertNotIn("stalled", line)

    def test_a_reviewer_before_its_first_verdict_reads_as_implementation(self):
        """The accepted cost of one label family. No label records a review round, so a
        reviewer that has posted no verdict yet reads as an implementation worker. The
        stale commit it inherited can then fire a stall, and a verdict is what moves the
        item into a review round. The fault that matters is still reported: a reviewer
        with no live process is dead, with no window elapsed."""
        self.write_fixture(labels=IMPL)
        self.backdate(3600)
        child = self.child_in(self.worktree)

        line = self.ask(stall=HALF_HOUR)

        self.assertTrue(line.startswith("stalled:"), line)
        quiet = self.ask(stall=FOUR_HOURS, expect=EXIT_NOTHING)
        self.assertIn(worker_state.IMPLEMENTATION, quiet)

        # A verdict arrives, and the same stale worktree is a review round instead.
        self.write_fixture(comments=[APPROVE], labels=IMPL)
        self.assertTrue(self.ask(stall=HALF_HOUR).startswith("verdict-approve:"))

        self.stop(child)
        self.write_fixture(labels=IMPL)
        dead = self.ask(stall=FOUR_HOURS)
        self.assertTrue(dead.startswith("dead:"), dead)
        self.assertIn(worker_state.IMPLEMENTATION, dead)

    def test_a_quiet_minute_is_nothing_to_do(self):
        """The common case, and the one that must cost no tokens."""
        self.write_fixture(labels=IMPL)
        child = self.child_in(self.worktree)

        line = self.ask(stall=FOUR_HOURS, expect=EXIT_NOTHING)

        self.assertTrue(line.startswith("nothing:"), line)
        self.assertIn("0 of 3 boxes ticked", line)
        self.assertIn(str(child.pid), line)
        self.assertNotEqual(EXIT_NOTHING, EXIT_DUE)

    def test_the_review_label_is_human_review_and_nothing_is_due(self):
        """A ticked checklist and a verdict here, so the `to-review` label is what
        answers. The maintainer is reading the pull request, and no pull request for this
        branch is merged, so the tick stays quiet."""
        write(self.checklist, TICKED)
        self.write_fixture(comments=[APPROVE], labels=HUMAN_REVIEW)

        line = self.ask(expect=EXIT_NOTHING)

        self.assertTrue(line.startswith("nothing:"), line)
        self.assertIn("human review", line)
        self.assertIn(f"#{ITEM}", line)

    # --- the merge is the second act (ADR 0057) -----------------------------

    def test_a_merged_pull_request_closes_the_item_and_tears_the_worker_down(self):
        """One tick reads the merge and runs the whole close. Nothing is typed.

        The item closes, its work-state label comes off, and the teardown command runs.
        That command removes the automation and the worktree, so a merged item leaves
        neither behind. The line carries the plan, so the exit code and the reason stay
        together.
        """
        write(self.checklist, TICKED)
        self.write_fixture(labels=HUMAN_REVIEW, pull_requests=self.pull_request())

        line = self.apply(close_flags=self.close_flags())

        self.assertTrue(line.startswith("merged:"), line)
        self.assertIn(f"#{PR}", line)
        self.assertIn(BRANCH, line)
        for step in ("4 pr merged", "5 pull", "6 worktree clean", "7 tracker"):
            self.assertIn(f"{step} done", line)
        self.assertIn("8 teardown done", line)
        self.assertEqual(self.swaps(), [([TO_REVIEW], [])])
        self.assertTrue(
            any("issue close" in one for one in self.writes()), self.writes()
        )
        self.assertTrue(self.teardown_marker().is_file())

    def test_an_open_pull_request_is_a_quiet_tick(self):
        """The maintainer has not merged yet, so nothing is due and nothing is an error."""
        write(self.checklist, TICKED)
        self.write_fixture(
            labels=HUMAN_REVIEW, pull_requests=self.pull_request(state="OPEN")
        )

        line = self.apply(expect=EXIT_NOTHING, close_flags=self.close_flags())

        self.assertIn(f"#{PR}", line)
        self.assertIn("open", line)
        self.assertEqual(self.writes(), [])
        self.assertFalse(self.teardown_marker().exists())

    def test_a_branch_with_no_pull_request_at_all_is_a_quiet_tick(self):
        """No record for this branch is no error either, so the two read the same way."""
        write(self.checklist, TICKED)
        self.write_fixture(
            labels=HUMAN_REVIEW, pull_requests=self.pull_request(head="another-branch")
        )

        line = self.apply(expect=EXIT_NOTHING, close_flags=self.close_flags())

        self.assertIn(BRANCH, line)
        self.assertEqual(self.writes(), [])
        self.assertFalse(self.teardown_marker().exists())

    def test_a_dirty_worktree_refuses_the_close_and_asks_for_a_human(self):
        """Uncommitted work has no reflog, so the one unrecoverable case refuses.

        The refusal is the close seam's own, and this tick adds none. The item wears
        `needs-human`, one comment names the files, and nothing is removed.
        """
        write(self.checklist, TICKED)
        write(self.worktree / "unsaved.txt", "work nobody committed\n")
        self.write_fixture(labels=HUMAN_REVIEW, pull_requests=self.pull_request())

        line = self.apply(expect=EXIT_REFUSED, close_flags=self.close_flags())

        self.assertIn("unsaved.txt", line)
        self.assertEqual(self.work_states_after(HUMAN_REVIEW), [NEEDS_HUMAN])
        comments = [one for one in self.writes() if "issue comment" in one]
        self.assertEqual(len(comments), 1, self.writes())
        self.assertIn("unsaved.txt", comments[0])
        self.assertFalse(any("issue close" in one for one in self.writes()))
        self.assertFalse(self.teardown_marker().exists())

    def test_step_5_really_pulls_the_merge_into_the_checkout(self):
        """The merge is ahead of the checkout, so the pull is a command and not a no-op.

        Every other close case names a merge the checkout already holds, which reads step 5
        as `done`. This one proves the step runs, and it proves the checkout is a real
        checkout on the default branch rather than the item's linked worktree.
        """
        write(self.checklist, TICKED)
        # The clone comes first, so the checkout is behind when the merge lands.
        checkout = self.checkout()
        merged = self.merge_onto_origin()
        self.assertFalse((checkout / "merged.txt").exists())
        self.write_fixture(
            labels=HUMAN_REVIEW, pull_requests=self.pull_request(merge_commit=merged)
        )

        line = self.apply(close_flags=self.close_flags())

        self.assertIn("5 pull done", line)
        self.assertTrue((checkout / "merged.txt").is_file())
        self.assertTrue(self.teardown_marker().is_file())

    def test_a_tick_with_neither_close_flag_closes_nothing(self):
        """Each flag is a condition for the close, so a missing one refuses and names it.

        A teardown that removes no schedule leaves one ticking against a closed item. And
        step 5 cannot run in the item's worktree, so the checkout is not optional either.
        """
        write(self.checklist, TICKED)
        self.write_fixture(labels=HUMAN_REVIEW, pull_requests=self.pull_request())

        line = self.apply(expect=EXIT_REFUSED)

        self.assertIn("--checkout", line)
        self.assertIn("--teardown-command", line)
        self.assertEqual(self.writes(), [])
        self.assertFalse(self.teardown_marker().exists())

    def test_the_three_close_flags_reach_the_close_through_the_command_line(self):
        """The precheck is a string a tool stores, so the flags must wire through `main`.

        The in-process cases call `tick` directly, so none of them crosses the argument
        parser. This one runs the command an **Item automation** really runs.
        """
        write(self.checklist, TICKED)
        self.write_fixture(labels=HUMAN_REVIEW, pull_requests=self.pull_request())

        line = self.tick_cli(
            "--checkout",
            str(self.checkout()),
            "--default-branch",
            "main",
            "--teardown-command",
            f"touch {self.teardown_marker()}",
        )

        self.assertTrue(line.startswith("merged:"), line)
        self.assertIn("8 teardown done", line)
        self.assertTrue(self.teardown_marker().is_file())
        self.assertEqual(self.swaps(), [([TO_REVIEW], [])])

    def test_the_phase_subcommand_takes_none_of_the_three_close_flags(self):
        """`phase` runs no close, so it stays the half that writes nothing at all."""
        for flag in ("--checkout", "--default-branch", "--teardown-command"):
            self.phase_cli(flag, "anything", expect=EXIT_USAGE)

    def test_the_phase_subcommand_reads_the_merge_and_writes_nothing(self):
        """The plan half names the close that is due, and it runs none of it."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=HUMAN_REVIEW, pull_requests=self.pull_request())

        line = self.ask()

        self.assertTrue(line.startswith("merged:"), line)
        self.assertEqual(self.writes(), [])
        self.assertFalse(self.teardown_marker().exists())

    def test_the_label_write_is_what_stops_a_repeat_of_the_same_fire(self):
        """The back-off window and its marker files retired with the wake. The applied
        transition is what stops a repeat now. The item wears the review state after the
        first tick, so the second tick reads human review and stays quiet. Nothing is
        suppressed, because nothing has to be."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)

        first = self.apply()
        self.assertTrue(first.startswith("implementation-complete:"), first)
        self.assertEqual(self.work_states_after(IMPL), [TO_REVIEW])

        # The tracker now holds the label the first tick wrote, so the next tick reads
        # human review and applies nothing.
        self.write_fixture(labels=HUMAN_REVIEW)
        again = self.apply(expect=EXIT_NOTHING)
        self.assertIn("human review", again)
        self.assertEqual(self.writes(), [])

    def test_an_unreadable_tracker_read_is_an_outcome_and_not_a_silence(self):
        """21 failed reads looked like 21 quiet minutes, because a failed read exited
        1. It is an outcome now, and no position gates it: a read that failed cannot say
        where the item sits. A tick refuses on it and writes no label, because a fact it
        never read cannot decide one."""
        self.break_fixture()

        line = self.ask()

        self.assertTrue(line.startswith("unreadable:"), line)
        self.assertIn(f"#{ITEM}", line)
        refused = self.apply(expect=EXIT_REFUSED)
        self.assertTrue(refused.startswith("unreadable:"), refused)
        self.assertIn("stays where it is", refused)

        # The same outcome for the fault that fired it live: the tracker CLI itself
        # failed, so the line carries the command that failed.
        self.fake_cli("gh")
        broken = self.phase_cli("--repo", "owner/name", fixture=False, expect=EXIT_DUE)
        self.assertTrue(broken.startswith("unreadable:"), broken)
        self.assertIn("gh issue view", broken)
        self.assertEqual(len(broken.splitlines()), 1, broken)

    def test_a_proof_box_is_one_more_box_and_it_needs_no_second_signal(self):
        """The proof is a checklist box where the project recipe asks for browser proof.
        So "every box ticked" already covers it. A checklist that ships the box needs one
        more tick, and one without the box finishes on the boxes it has."""
        self.write_fixture(labels=IMPL)
        self.child_in(self.worktree)

        write(self.checklist, TICKED + PROOF_BOX)
        self.assertIn("3 of 4 boxes ticked", self.ask(expect=EXIT_NOTHING))

        write(self.checklist, TICKED + PROOF_BOX.replace("- [ ]", "- [x]"))
        self.assertIn("(4 of 4)", self.ask())

        # A checklist with no proof box finishes on the boxes it has, which is every item
        # in this repo: its `run_recipe` is blank, so the box drops before the send.
        write(self.checklist, TICKED)
        self.assertIn("(3 of 3)", self.ask())

    # --- the computed Position ----------------------------------------------

    def test_each_position_is_computed_from_facts_and_not_from_a_label(self):
        """Three values, three distinct strings, and no label of their own. The one
        label the rule reads is a work-state label."""
        self.assertEqual(len(set(POSITIONS)), 3)

        self.assertEqual(self.position([TO_REVIEW]), worker_state.HUMAN_REVIEW)
        self.assertEqual(
            self.position([IN_PROGRESS], ["Verdict: approve"]),
            worker_state.REVIEW_ROUND,
        )
        self.assertEqual(self.position([IN_PROGRESS]), worker_state.IMPLEMENTATION)

    def test_a_verdict_older_than_the_checklist_write_is_implementation_again(self):
        """The two review branches. A `Verdict:` comment newer than the last checklist
        write is a review round. A checklist written after that comment means the fix
        round started, so the position is implementation again."""
        written = worker_state.checklist_written(self.worktree, ITEM)

        self.assertEqual(
            self.position([IN_PROGRESS], [CHANGES], verdict_written=written + 60),
            worker_state.REVIEW_ROUND,
        )
        self.assertEqual(
            self.position([IN_PROGRESS], [CHANGES], verdict_written=written - 60),
            worker_state.IMPLEMENTATION,
        )
        # A comment with no `Verdict:` line dates nothing, whatever its own age is.
        self.assertEqual(
            self.position([IN_PROGRESS], ["nearly done"], verdict_written=written + 60),
            worker_state.IMPLEMENTATION,
        )

    def test_a_retired_label_reads_as_nothing_and_crashes_no_tick(self):
        """The migration guard. A repo whose label migration has not run yet still ticks,
        and an item there can still wear a deleted label. Each one is an unknown string
        now, so the position comes from the work-state label and the facts beside it."""
        write(self.checklist, TICKED)

        for retired in RETIRED:
            self.write_fixture(labels=[IN_PROGRESS, retired])
            self.assertTrue(self.ask().startswith("implementation-complete:"), retired)

            self.write_fixture(comments=[APPROVE], labels=[IN_PROGRESS, retired])
            self.assertTrue(self.ask().startswith("verdict-approve:"), retired)

            # An item that wears the deleted label alone reads as implementation, and
            # `to-review` beside it is still human review.
            self.assertEqual(self.position([retired]), worker_state.IMPLEMENTATION)
            self.assertEqual(
                self.position([TO_REVIEW, retired]), worker_state.HUMAN_REVIEW
            )

    def test_no_position_is_reachable_from_two_work_state_labels_at_once(self):
        """The guard against the class of bug #155 reported. One work-state label decides
        the position, so a stacked pair answers what one of the two answers alone. No
        pair invents a fourth value, and `human-review` is reachable from `to-review` and
        from no other label."""
        facts = ["Verdict: approve"]

        for pair in itertools.combinations(WORK_STATES, 2):
            stacked = self.position(pair, facts)
            alone = {self.position([label], facts) for label in pair}

            self.assertIn(stacked, POSITIONS, pair)
            self.assertIn(stacked, alone, pair)

        for label in WORK_STATES:
            reaches = self.position([label], facts) == worker_state.HUMAN_REVIEW
            self.assertEqual(reaches, label == TO_REVIEW, label)

    def test_the_computed_position_is_the_only_answer(self):
        """The computed position in place, with no label family behind it. An item that
        wears `in-progress` alone reaches the outcome its own facts name. This holds in
        both positions a worker owns."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=[IN_PROGRESS])

        self.assertTrue(self.ask().startswith("implementation-complete:"))

        self.write_fixture(comments=[APPROVE], labels=[IN_PROGRESS])
        self.assertTrue(self.ask().startswith("verdict-approve:"))

    def test_no_outcome_the_tick_prints_names_two_work_state_labels(self):
        """The guard against the class of bug #155 reported, applied to the printed
        line. One work-state family means one label in play, so no line a tick prints
        can name two of the four values. That is what a session reads to pick its
        response, and two labels in one line is what made it pick the wrong row."""
        lines = []

        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        lines.append(self.ask())
        lines.append(self.ask(required=REQUIRED))

        for comments in ([APPROVE], [CHANGES], [CHANGES] * 3):
            self.write_fixture(comments=comments, labels=IMPL)
            lines.append(self.ask(rounds=3))

        self.write_fixture(comments=[APPROVE], labels=HUMAN_REVIEW)
        lines.append(self.ask(expect=EXIT_NOTHING))

        self.write_fixture(labels=[*IMPL, NEEDS_HUMAN])
        lines.append(self.ask(expect=EXIT_NOTHING))

        write(self.checklist, UNTICKED)
        self.write_fixture(labels=IMPL)
        lines.append(self.ask(stall=FOUR_HOURS))
        self.child_in(self.worktree)
        self.backdate(3600)
        lines.append(self.ask(stall=HALF_HOUR))
        self.break_fixture()
        lines.append(self.ask())

        for line in lines:
            named = [label for label in WORK_STATES if label in line]
            self.assertLessEqual(len(named), 1, f"{named} both named in: {line}")

    def test_a_needs_human_label_keeps_every_tick_quiet(self):
        """The one label that stops the machine. Every other fact in each case here is a
        due transition, and the tick still reports nothing, writes no label and touches no
        file. Only the maintainer clears it."""
        write(self.checklist, TICKED)

        for labels in (
            [NEEDS_HUMAN],
            [*IMPL, NEEDS_HUMAN],
            [*HUMAN_REVIEW, NEEDS_HUMAN],
            [NEEDS_HUMAN, *RETIRED],
        ):
            self.write_fixture(comments=[APPROVE], labels=labels)
            before = {path for path, _ in self.disk_state()}

            line = self.apply(expect=EXIT_NOTHING)

            self.assertTrue(line.startswith("nothing:"), line)
            self.assertIn(NEEDS_HUMAN, line)
            self.assertIn(f"#{ITEM}", line)
            self.assertEqual(self.writes(), [], labels)
            self.assertEqual({path for path, _ in self.disk_state()}, before, labels)

    # --- what the deleted merge-requested outcome leaves behind --------------

    def test_the_board_flags_are_gone_from_both_subcommands(self):
        """They served the merge-requested outcome alone, so the outcome and the three
        coordinates go together. A flag left in the parser is a flag a caller resolves
        for nothing. The board section of the tracker file no longer feeds a tick."""
        for subcommand in ("phase", "tick"):
            # The usage line carries the path of the checkout that runs, and a worktree
            # can be named after this migration. So the path is not text this seam
            # wrote, and it is not what this test reads.
            out = self.run_seam(subcommand, "--help", lines=400).replace(
                str(REPO_ROOT), "<repo>"
            )

            for flag in BOARD_FLAGS:
                self.assertNotIn(flag, out, f"{subcommand} --help still names {flag}")
            self.assertNotIn("board", out.lower(), f"{subcommand} --help names a board")

    def test_a_tick_makes_one_tracker_read_and_never_a_board_read(self):
        """One read answers every fact a tick needs: the labels and the comments. The
        board read was a second command that can fail, and it went with the outcome it
        served. The stub CLI logs one line, so nothing reaches a project board."""
        log = self.fake_cli(
            "gh",
            issue={"labels": [{"name": IN_PROGRESS}], "comments": []},
            project={"items": [{"status": "To land", "content": {"number": ITEM}}]},
        )
        write(self.checklist, TICKED)

        line = self.phase_cli("--repo", "owner/name", fixture=False, expect=EXIT_DUE)

        self.assertTrue(line.startswith("implementation-complete:"), line)
        self.assertEqual(
            log.read_text().splitlines(),
            [f"issue view {ITEM} --json comments,labels --repo owner/name"],
        )

    def test_the_glab_reads_carry_the_host_where_each_one_needs_it(self):
        """Two reads, two places for the host. A bare owner/name in the API path
        resolves against the CLI's default server, which is the fault this closes.
        The stub CLI records the argv, so neither CLI has to be installed."""
        log = self.fake_cli(
            "glab",
            issue={"labels": [IN_PROGRESS]},
            api=[{"body": "Verdict: approve"}],
        )

        line = self.phase_cli(
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
                "labels": [{"name": IN_PROGRESS}],
                "comments": [{"body": "Verdict: approve"}],
            },
        )
        expected = f"issue view {ITEM} --json comments,labels --repo owner/name"

        line = self.phase_cli("--repo", "owner/name", fixture=False, expect=EXIT_DUE)
        self.assertTrue(line.startswith("verdict-approve:"), line)

        self.phase_cli(
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
                self.phase_cli(stall=stall, expect=EXIT_DUE).startswith("stalled:"),
                stall,
            )
        # The same fixture is not a stall under a window that has not passed.
        self.assertTrue(
            self.phase_cli(stall="1h", expect=EXIT_NOTHING).startswith("nothing:")
        )

    def test_a_removed_worktree_is_gone_for_the_predicate_too(self):
        """The existing ordering guarantee, held for this subcommand: a torn-down
        worker is reported as gone and never as a stall."""
        self.write_fixture(labels=IMPL)
        self.backdate(3600)  # old enough to look like a stall, if it were checked
        shutil.rmtree(self.worktree)

        line = self.ask(stall=HALF_HOUR, expect=EXIT_GONE)

        self.assertTrue(line.startswith("gone:"), line)
        self.assertNotIn("stalled", line)
        self.assertNotEqual(EXIT_GONE, EXIT_DUE)

    def test_every_outcome_exits_zero_and_every_quiet_one_does_not(self):
        """The whole exit-code contract in one place, and the whole outcome table with
        it. Eight outcomes, and a due transition is 0 whichever one fired. The printed
        line names which. No quiet outcome can read as a transition."""
        due = {}

        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        due["implementation-complete"] = self.phase_cli(expect=EXIT_DUE)

        # The same ticked checklist, with a required layer nothing on disk proves.
        self.write_fixture(labels=IMPL)
        due["gates-unproven"] = self.phase_cli(*GATES, expect=EXIT_DUE)

        self.write_fixture(comments=["Verdict: approve"], labels=IMPL)
        due["verdict-approve"] = self.phase_cli(expect=EXIT_DUE)

        self.write_fixture(comments=[CHANGES], labels=IMPL)
        due["verdict-request-changes"] = self.phase_cli(expect=EXIT_DUE)

        self.write_fixture(comments=[CHANGES] * 3, labels=IMPL)
        due["rounds-exhausted"] = self.phase_cli(rounds=3, expect=EXIT_DUE)

        write(self.checklist, UNTICKED)
        self.write_fixture(labels=IMPL)
        due["dead"] = self.phase_cli(stall="4h", expect=EXIT_DUE)

        self.child_in(self.worktree)
        self.backdate(3600)
        due["stalled"] = self.phase_cli(stall="30m", expect=EXIT_DUE)

        self.break_fixture()
        due["unreadable"] = self.phase_cli(expect=EXIT_DUE)
        self.write_fixture(labels=IMPL)

        self.assertEqual(
            sorted(due),
            sorted(
                [
                    "implementation-complete",
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

        # A quiet minute and a gone worktree are the two non-zero answers, and each
        # one says which it is.
        self.checklist.write_text(UNTICKED)
        quiet = self.phase_cli(stall="4h", expect=EXIT_NOTHING)

        shutil.rmtree(self.worktree)
        gone = self.phase_cli(expect=EXIT_GONE)

        self.assertEqual(
            [line.split(":")[0] for line in (quiet, gone)], ["nothing", "gone"]
        )

    def test_a_usage_error_can_never_read_as_a_quiet_tick(self):
        """A flag with a typo exits outside the contract, so it is never mistaken for a
        transition or for a quiet minute. Both subcommands take the same flags, so this
        case runs both. A tick without `--claim` still needs all four worker flags."""
        for subcommand in ("phase", "tick"):
            base = (
                subcommand,
                "--item",
                str(ITEM),
                "--worktree",
                str(self.worktree),
                "--process",
                PROCESS_PATTERN,
            )
            for argv in (
                (subcommand, "--item", str(ITEM)),
                (*base, "--stall-after", "1s"),  # no --rounds, and there is no default
                (*base, "--rounds", "3"),  # no --stall-after
                (*base, "--rounds", "3", "--stall-after", "soon"),
                (*base, "--rounds", "0", "--stall-after", "1s"),
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
                self.assertNotIn(
                    proc.returncode,
                    (EXIT_DUE, EXIT_NOTHING, EXIT_REFUSED, EXIT_GONE, EXIT_APPLIED),
                )

    # --- tick: the transition it computed, applied ---------------------------

    def complete_line(self):
        """The line a ticked checklist prints, with the path the seam resolves."""
        checklist = (
            Path(os.path.realpath(self.worktree))
            / ".orchestrator"
            / f"checklist-{ITEM}.md"
        )
        return f"implementation-complete: every box in {checklist} is ticked (3 of 3)"

    def test_a_tick_applies_the_transition_and_names_what_it_wrote(self):
        """The whole of this item. The tick stops printing an outcome for a session to
        act on, and writes the label itself. The line carries the outcome it computed and
        the labels it wrote, so a run history needs no second read."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)

        line = self.tick_cli()

        self.assertTrue(line.startswith(self.complete_line()), line)
        self.assertIn("applied:", line)
        self.assertIn(f"{IN_PROGRESS} → {TO_REVIEW} on work item #{ITEM}", line)
        self.assertEqual(
            self.writes(),
            [
                f"gh issue edit {ITEM} --remove-label {IN_PROGRESS} "
                f"--add-label {TO_REVIEW}"
            ],
        )
        self.assertNotEqual(EXIT_APPLIED, EXIT_DUE)

    def test_each_transition_applies_from_every_legal_predecessor(self):
        """One case per transition, and each one from every work-state label it can
        legally start from. The removals come from the labels the tick read, so a
        transition needs no hardcoded predecessor and every start lands in one place."""
        for outcome, ends_on in TRANSITIONS.items():
            for labels in PREDECESSORS:
                self.set_up_outcome(outcome, labels)

                line = self.apply(rounds=3)

                self.assertTrue(line.startswith(f"{outcome}:"), line)
                self.assertIn("applied:", line)
                self.assertEqual(
                    self.work_states_after(labels), [ends_on], (outcome, labels)
                )

    def test_exactly_one_work_state_label_survives_each_transition(self):
        """The class of bug #155 reported: two work states stacked on one item. The
        removals and the addition are one tracker write, so they can never land apart. An
        item that already wears the label the transition adds keeps exactly one too."""
        starts = (*PREDECESSORS, [READY_FOR_AGENT, IN_PROGRESS])
        for outcome, ends_on in TRANSITIONS.items():
            for labels in starts:
                self.set_up_outcome(outcome, labels)

                self.apply(rounds=3, expect=EXIT_APPLIED)

                self.assertEqual(
                    self.work_states_after(labels), [ends_on], (outcome, labels)
                )
                self.assertEqual(len(self.swaps()), 1, (outcome, labels))

        # And the writer itself, from the one start no outcome can reach: an item that
        # already wears the label the transition adds. There is nothing to remove and
        # nothing to add, so it makes no write at all.
        self.write_fixture(labels=HUMAN_REVIEW)
        swap = worker_state.write_transition(
            self.adapter(), ITEM, HUMAN_REVIEW, TO_REVIEW
        )
        self.assertEqual(swap, ([], []))
        self.assertEqual(self.writes(), [])

    def test_a_tick_applies_at_most_one_transition_per_run(self):
        """The hard rule that bounds a seam that writes the tracker every minute with
        nobody watching. One tick reads one item, computes one outcome and makes one label
        swap. So a wrong computation cannot cascade inside one minute."""
        write(self.checklist, TICKED)
        # Every fact for a finish and for an approve holds at once, and the item wears two
        # work states as well. One run still makes one swap.
        self.write_fixture(comments=[APPROVE], labels=[READY_FOR_AGENT, IN_PROGRESS])

        self.apply()

        self.assertEqual(len(self.swaps()), 1, self.writes())

        # A second run over the same tracker state makes one more swap and never two,
        # and the item still wears one work-state label.
        self.apply()
        self.assertEqual(len(self.swaps()), 2, self.writes())
        self.assertEqual(
            self.work_states_after([READY_FOR_AGENT, IN_PROGRESS]), [TO_REVIEW]
        )

    def test_the_phase_subcommand_writes_nothing_at_all(self):
        """What keeps the dry run honest. `phase` reads the same plan the tick reads, and
        it leaves no `<fixture>.writes` file behind. So a maintainer runs it against a
        live tracker before the first write."""
        log = self.root / "gh.json.writes"
        for outcome in TRANSITIONS:
            self.set_up_outcome(outcome, IMPL)

            line = self.ask(rounds=3)

            self.assertTrue(line.startswith(f"{outcome}:"), line)
            self.assertFalse(log.exists(), f"{outcome} left a tracker write behind")

        # And through the command line, which is the form a maintainer runs.
        self.set_up_outcome("implementation-complete", IMPL)
        self.phase_cli(expect=EXIT_DUE)
        self.assertFalse(log.exists())

    def test_an_outcome_with_no_transition_refuses_and_the_item_stays(self):
        """Four outcomes say something about the worker, about the tracker read or about a
        fix round that is still the same worker's work. None of them decides a label, so
        the tick refuses, the item stays where it is, and the code is the refusal. `stalled`
        is not one of them any more: it carries one re-prompt and then a human."""
        write(self.checklist, UNTICKED)

        self.write_fixture(labels=IMPL)
        dead = self.apply(expect=EXIT_REFUSED)
        self.assertTrue(dead.startswith("dead:"), dead)

        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        unproven = self.apply(required=REQUIRED, expect=EXIT_REFUSED)
        self.assertTrue(unproven.startswith("gates-unproven:"), unproven)

        self.write_fixture(comments=[CHANGES], labels=IMPL)
        changes = self.apply(expect=EXIT_REFUSED)
        self.assertTrue(changes.startswith("verdict-request-changes:"), changes)

        for line in (dead, unproven, changes):
            self.assertIn("stays where it is", line)
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.work_states_after(IMPL), IMPL)

    def test_a_finish_holds_its_write_where_the_review_policy_is_on(self):
        """A Review round comes next there, so a worker still owns the item and the review
        state would read as a lie. The finish refuses, prints why, and leaves the item where
        it is. The round's own verdict writes the label when the loop concludes."""
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)

        on = self.apply(review=True, expect=EXIT_REFUSED)

        self.assertTrue(on.startswith("implementation-complete:"), on)
        self.assertIn("review policy is on", on)
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.work_states_after(IMPL), IMPL)

        # The default is the policy every other flag assumes, so a finish with the review
        # policy off reaches the review state.
        self.apply()
        self.assertEqual(self.work_states_after(IMPL), [TO_REVIEW])

        # The loop concludes on a verdict, and that outcome writes the label the finish
        # held. So the hold costs the item nothing.
        self.write_fixture(comments=[APPROVE], labels=IMPL)
        approved = self.apply(review=True)
        self.assertTrue(approved.startswith("verdict-approve:"), approved)
        self.assertEqual(self.work_states_after(IMPL), [TO_REVIEW])

        # And the predicate answers the same code either way, because a held write is still
        # a transition a caller has to read.
        self.write_fixture(labels=IMPL)
        held = self.ask(review=True)
        self.assertTrue(held.startswith("implementation-complete:"), held)

    def test_a_to_review_item_with_a_verdict_still_routes_a_fix_round(self):
        """The review state stays a legal position through this wave, because adversarial
        review leaves the loop later. A `to-review` item is human review, so the tick moves
        nothing there. The same verdict on an item a worker still owns is the fix round,
        and that round is still that worker's own work, so no label moves."""
        write(self.checklist, TICKED)
        self.write_fixture(comments=[CHANGES], labels=HUMAN_REVIEW)

        quiet = self.apply(expect=EXIT_NOTHING)

        self.assertIn("human review", quiet)
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.work_states_after(HUMAN_REVIEW), HUMAN_REVIEW)

        # The same verdict on the item its worker still owns is the fix round, and it is
        # still that worker's own work, so no label moves.
        self.write_fixture(comments=[CHANGES], labels=IMPL)
        fix = self.apply(expect=EXIT_REFUSED)
        self.assertTrue(fix.startswith("verdict-request-changes:"), fix)
        self.assertIn("round 1 of 3", fix)
        self.assertEqual(self.work_states_after(IMPL), IMPL)

    def test_the_needs_human_writer_writes_the_label_and_one_comment(self):
        """The writer the rest of this wave calls. It writes one label, plus one comment
        that says what the seam saw. A label with no reason leaves the maintainer to
        reconstruct one. The exit code is the refusal, because a seam that asks for a
        human refused to act."""
        self.write_fixture(labels=IMPL)
        saw = "two re-prompts and no ticked box"

        code, line = worker_state.needs_human(self.adapter(), ITEM, IMPL, saw)

        self.assertEqual(code, EXIT_REFUSED, line)
        self.assertTrue(line.startswith(f"{NEEDS_HUMAN}:"), line)
        self.assertIn(saw, line)
        self.assertEqual(
            self.writes(),
            [
                f"gh issue edit {ITEM} --remove-label {IN_PROGRESS} "
                f"--add-label {NEEDS_HUMAN}",
                f"gh issue comment {ITEM} --body {NEEDS_HUMAN}: {saw}",
            ],
        )
        self.assertEqual(self.work_states_after(IMPL), [NEEDS_HUMAN])

        # And the item it wrote stops every later tick.
        self.write_fixture(labels=[NEEDS_HUMAN])
        write(self.checklist, TICKED)
        self.assertIn(NEEDS_HUMAN, self.apply(expect=EXIT_NOTHING))

    # --- one re-prompt, then a human (ADR 0058) -----------------------------

    def test_a_stall_gets_one_re_prompt_and_the_next_one_gets_a_human(self):
        """The whole of this item. The first stalled tick posts one `Re-prompt:` comment and
        moves no label, so the worker keeps its item and the tick records as applied. The
        second writes `needs-human` with one comment, re-prompts nothing, and records as the
        refusal. Nothing between them climbs a rung."""
        self.stalling()

        first = self.apply(stall=HALF_HOUR, expect=EXIT_APPLIED)

        self.assertTrue(first.startswith("stalled:"), first)
        self.assertIn(f"retry 1 of {RE_PROMPTS}", first)
        self.assertEqual(len(self.writes()), 1)
        self.assertIn(RE_PROMPT, self.writes()[0])
        self.assertEqual(self.swaps(), [])
        self.assertEqual(self.work_states_after(IMPL), IMPL)

        # The comment it wrote is the count the next tick reads, so the second stall on the
        # same item asks for a human.
        self.stalling(comments=[SENT])
        second = self.apply(stall=HALF_HOUR, expect=EXIT_REFUSED)

        self.assertTrue(second.startswith(f"{NEEDS_HUMAN}: stalled:"), second)
        self.assertIn(f"1 of {RE_PROMPTS} retries", second)
        self.assertEqual(self.work_states_after(IMPL), [NEEDS_HUMAN])
        self.assertEqual(
            [line.split()[2] for line in self.writes()], ["edit", "comment"]
        )
        # It re-prompts nothing, so no write it made carries the literal again.
        self.assertEqual([line for line in self.writes() if RE_PROMPT in line], [])

        # And the label it wrote stops every later tick on that item.
        self.stalling(comments=[SENT], labels=[NEEDS_HUMAN])
        self.assertIn(NEEDS_HUMAN, self.apply(stall=HALF_HOUR, expect=EXIT_NOTHING))

    def test_the_re_prompt_comment_carries_what_the_tick_saw_and_the_unticked_steps(
        self,
    ):
        """A session that reads the comment needs no second read to compose the retry. So
        the body carries the stall line, the reset, and the steps that are still unticked."""
        write(self.checklist, UNTICKED.replace("- [ ] push the branch", "- [x] push"))
        self.write_fixture(labels=IMPL)
        self.backdate(3600)
        self.child_in(self.worktree)

        self.apply(stall=HALF_HOUR, expect=EXIT_APPLIED)

        body = self.writes()[0]
        self.assertIn(f"gh issue comment {ITEM} --body {RE_PROMPT}", body)
        self.assertIn("Reset the worker's context", body)
        self.assertIn("implement + self-test", body)
        self.assertIn("commit in slices", body)
        # The box the worker already ticked is not re-sent.
        self.assertNotIn("push", body)

    def test_the_re_prompt_count_is_a_tracker_fact_and_no_file_holds_it(self):
        """A fresh `.orchestrator` directory reads the same count, because the count lives on
        the work item. The marker file the old count used died with the worktree, and a
        restart could not read it."""
        self.stalling(comments=[SENT])
        markers = self.checklist.parent
        shutil.rmtree(markers)
        write(self.checklist, UNTICKED)
        self.backdate(3600)

        self.assertEqual(
            sorted(path.name for path in markers.iterdir()), ["checklist-54.md"]
        )
        line = self.apply(stall=HALF_HOUR, expect=EXIT_REFUSED)

        self.assertIn(NEEDS_HUMAN, line)
        self.assertEqual(self.work_states_after(IMPL), [NEEDS_HUMAN])

        # And with no such comment on the item, the same fresh directory reads the first
        # retry instead. So the answer follows the tracker and never the file system.
        self.stalling()
        shutil.rmtree(markers)
        write(self.checklist, UNTICKED)
        self.backdate(3600)
        self.assertIn(
            f"retry 1 of {RE_PROMPTS}", self.apply(stall=HALF_HOUR, expect=EXIT_APPLIED)
        )

    def test_a_comment_that_only_quotes_the_literal_spends_no_retry(self):
        """A review note and this repo's own prose both quote `Re-prompt:` mid-sentence. The
        seam writes it at the start of a line, so only that shape counts. Otherwise writing
        about a re-prompt spends one."""
        quoting = [
            "The tick posts one `Re-prompt:` comment on the first stall.",
            "| stalled | one Re-prompt: comment, and no label |",
        ]
        self.stalling(comments=quoting)

        line = self.apply(stall=HALF_HOUR, expect=EXIT_APPLIED)

        self.assertIn(f"retry 1 of {RE_PROMPTS}", line)
        self.assertEqual(self.swaps(), [])

    def test_the_re_prompt_bound_is_one_and_no_flag_raises_it(self):
        """A bound a caller can raise is a climb under another name. So the seam holds the
        number, and neither subcommand takes a flag for it."""
        self.assertEqual(RE_PROMPTS, 1)

        argv = self.tick_argv()
        for flag in ("--re-prompts", "--stalls", "--retries"):
            for subcommand in ("phase", "tick"):
                self.run_seam(subcommand, *argv, flag, "3", expect=EXIT_USAGE, lines=0)

    def test_a_dead_worker_is_never_re_prompted(self):
        """Nothing listens, so a re-prompt cannot reach it. That outcome keeps the answer it
        has: no label, no comment, and the refusal code."""
        write(self.checklist, UNTICKED)
        self.write_fixture(labels=IMPL)

        line = self.apply(stall=FOUR_HOURS, expect=EXIT_REFUSED)

        self.assertTrue(line.startswith("dead:"), line)
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.work_states_after(IMPL), IMPL)

    def test_the_stall_transition_writes_nothing_through_the_predicate(self):
        """`phase` is the plan half, so a maintainer dry-runs a stalled item and no comment
        and no label lands. Both stalls are due transitions there, and the line names which
        one the tick would apply."""
        log = self.root / "gh.json.writes"

        self.stalling()
        first = self.ask(stall=HALF_HOUR)
        self.assertIn(f"retry 1 of {RE_PROMPTS}", first)
        self.assertFalse(log.exists(), "the predicate wrote a re-prompt")

        self.stalling(comments=[SENT])
        second = self.ask(stall=HALF_HOUR)
        self.assertIn("retries", second)
        self.assertFalse(log.exists(), "the predicate wrote a label")

    def test_the_claim_transition_is_reachable_from_the_command_line(self):
        """One named transition, so a session's spawn claim runs the same writer a tick
        runs and assembles no label command of its own. It reads no worktree and no
        process, so it needs none of the flags that name a worker."""
        self.write_fixture(labels=[READY_FOR_AGENT])

        line = self.run_seam(
            "tick",
            "--claim",
            "--item",
            str(ITEM),
            "--gh-fixture",
            str(self.fixture),
            expect=EXIT_APPLIED,
        )

        self.assertTrue(line.startswith("claim:"), line)
        self.assertIn(f"{READY_FOR_AGENT} → {IN_PROGRESS} on work item #{ITEM}", line)
        self.assertEqual(self.work_states_after([READY_FOR_AGENT]), [IN_PROGRESS])
        self.assertEqual(len(self.swaps()), 1)

        # It reads `needs-human` first, the same as every other path, so a claim cannot
        # restart an item the machine was asked to leave alone.
        self.write_fixture(labels=[READY_FOR_AGENT, NEEDS_HUMAN])
        refused = self.run_seam(
            "tick",
            "--claim",
            "--item",
            str(ITEM),
            "--gh-fixture",
            str(self.fixture),
            expect=EXIT_REFUSED,
        )
        self.assertIn(NEEDS_HUMAN, refused)
        self.assertEqual(self.writes(), [])

    def test_the_wake_is_gone_with_its_five_flags(self):
        """No delivery is left, so no transition can be lost to one and no fact lives in a
        file a restart cannot read. The subcommand is gone, each flag is a usage error, and
        no run of either subcommand writes a file anywhere."""
        self.assertEqual(
            self.run_seam("wake", "--item", str(ITEM), expect=EXIT_USAGE, lines=0), ""
        )

        argv = self.tick_argv()
        for flag in WAKE_FLAGS:
            for subcommand in ("phase", "tick"):
                self.run_seam(subcommand, *argv, flag, "1h", expect=EXIT_USAGE, lines=0)

        # And no marker file, in the worktree or anywhere else under the temp root.
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        before = {path for path, _ in self.disk_state()}
        self.apply()
        added = {path for path, _ in self.disk_state()} - before
        self.assertEqual(added, {str(self.root / "gh.json.writes")}, added)

    def test_one_function_writes_every_work_state_label(self):
        """A grep for a label write finds no second path. There is one call to the
        adapter's label builder, and it sits in the one writer. So the removals and the
        addition cannot drift apart, and a reader has one place to look."""
        tree = ast.parse((REPO_ROOT / "scripts" / "worker_state.py").read_text())
        builders = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "attr", "") == "label_argv"
        ]

        self.assertEqual(len(builders), 1, "the seam builds one label write")

    def test_the_tick_exit_codes_name_what_happened(self):
        """The whole tick contract in one place: applied, refused, quiet and gone. No path
        exits 0, so every run records as skipped and no agent runs on a tick."""
        codes = {}

        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        codes["applied"] = self.tick_cli(expect=EXIT_APPLIED)

        self.write_fixture(labels=IMPL)
        codes["refused"] = self.tick_cli(*GATES, expect=EXIT_REFUSED)

        write(self.checklist, UNTICKED)
        self.write_fixture(labels=[NEEDS_HUMAN])
        codes["quiet"] = self.tick_cli(expect=EXIT_NOTHING)

        shutil.rmtree(self.worktree)
        codes["gone"] = self.tick_cli(expect=EXIT_GONE)

        for what, line in codes.items():
            self.assertEqual(len(line.splitlines()), 1, line)
            self.assertTrue(line, what)
        self.assertEqual(len({EXIT_APPLIED, EXIT_REFUSED, EXIT_NOTHING, EXIT_GONE}), 4)
        self.assertNotIn(
            EXIT_COMPLETE, (EXIT_APPLIED, EXIT_REFUSED, EXIT_NOTHING, EXIT_GONE)
        )

    # --- the two-facts start gate (ADR 0045) --------------------------------

    def test_both_facts_start_the_item(self):
        """The label and the card in the start column. That is act one, and it is the one
        answer that exits 0. The line names both facts, so a maintainer reads why."""
        self.write_fixture(labels=[READY_FOR_AGENT], board=START_COLUMN)

        line = self.gate(expect=EXIT_DUE)

        self.assertTrue(line.startswith(f"{START}:"), line)
        self.assertIn(READY_FOR_AGENT, line)
        self.assertIn(repr(START_COLUMN), line)

    def test_one_fact_is_never_an_error_and_never_a_refusal(self):
        """Either fact on its own starts nothing. A card in the start column with no label
        is not started. A labelled item whose card sits in the lane before it is not
        started either. So that lane stays the maintainer's own, and neither case is an
        error. This is how a maintainer parks a groomed item."""
        self.write_fixture(labels=[READY_FOR_AGENT], board=READY_LANE)
        label_only = self.gate(expect=EXIT_NOTHING)

        self.write_fixture(labels=[], board=START_COLUMN)
        card_only = self.gate(expect=EXIT_NOTHING)

        for line in (label_only, card_only):
            self.assertTrue(line.startswith(f"{ONE_FACT}:"), line)
            self.assertIn("starts nothing", line)
            # An error word appears in neither one, and no tracker write went out.
            for word in ("error", "refused", "unreadable"):
                self.assertNotIn(word, line)
        self.assertEqual(self.writes(), [])

        # The two lines differ, because the missing fact is what a maintainer repairs.
        self.assertNotEqual(label_only, card_only)
        self.assertIn(repr(READY_LANE), label_only)
        self.assertIn(f"no {READY_FOR_AGENT} label", card_only)

    def test_neither_fact_is_where_a_groomed_item_rests(self):
        """No label and no card in the start column. Every open item starts here, so the
        answer is its own quiet state rather than the one-fact state."""
        self.write_fixture(labels=[], board=READY_LANE)
        in_a_lane = self.gate(expect=EXIT_NOTHING)

        self.write_fixture(labels=[])
        no_card = self.gate(expect=EXIT_NOTHING)

        for line in (in_a_lane, no_card):
            self.assertTrue(line.startswith(f"{NO_FACT}:"), line)
        self.assertIn("no card", no_card)

    def test_with_no_board_configured_the_label_alone_decides(self):
        """A tracker that names no board is a supported configuration, and its absence is
        never an error. The label is then the whole gate, so a labelled item starts and an
        unlabelled one does not. It makes no board read either."""
        log = self.fake_cli("gh", issue={"labels": [{"name": READY_FOR_AGENT}]})

        self.write_fixture(labels=[READY_FOR_AGENT], board=READY_LANE)
        started = self.gate(expect=EXIT_DUE, project=0, owner="", column="")

        self.write_fixture(labels=[], board=START_COLUMN)
        stopped = self.gate(expect=EXIT_NOTHING, project=0, owner="", column="")

        self.assertTrue(started.startswith(f"{START}:"), started)
        self.assertTrue(stopped.startswith(f"{NO_FACT}:"), stopped)
        for line in (started, stopped):
            self.assertIn("names no board", line)
        # The card said `Ready` and the item still started, so the board was not read.
        self.assertFalse(log.exists(), "a board read ran with no coordinates")

        # Each coordinate alone stops the board read, so a half-configured board is the
        # same supported configuration and never a crash.
        half_configured: tuple[dict[str, object], ...] = (
            {"project": 0},
            {"owner": ""},
            {"column": ""},
        )
        for missing in half_configured:
            self.write_fixture(labels=[READY_FOR_AGENT], board=READY_LANE)
            self.assertIn("names no board", self.gate(expect=EXIT_DUE, **missing))

    def test_a_failed_board_read_counts_no_card_and_is_never_an_error(self):
        """The labels were read, so a fact is available and the cause rides the line.
        Nothing starts on a card this gate cannot read, which is the safe direction."""
        log = self.fake_cli("gh", issue={"labels": [{"name": READY_FOR_AGENT}]})

        line = self.start_cli("--repo", "owner/name", fixture=False)

        self.assertTrue(line.startswith(f"{ONE_FACT}:"), line)
        self.assertIn("the board read failed", line)
        self.assertIn("starts nothing", line)
        # The board read really ran and really failed: the stub CLI has no project payload.
        self.assertIn("project item-list", log.read_text())

    def test_the_start_gate_reads_the_board_by_name_and_writes_nothing(self):
        """One item read and one board read, and no write of any kind. The column is a
        name and never an option id, because nothing writes a card. The stub CLI records
        the argv, so this case asserts the recipe of docs/agents/issue-tracker.md."""
        log = self.fake_cli(
            "gh",
            issue={"labels": [{"name": READY_FOR_AGENT}], "comments": []},
            project={"items": [{"status": START_COLUMN, "content": {"number": ITEM}}]},
        )
        before = {path for path, _ in self.disk_state()}

        line = self.start_cli("--repo", "owner/name", fixture=False, expect=EXIT_DUE)

        self.assertTrue(line.startswith(f"{START}:"), line)
        self.assertEqual(
            log.read_text().splitlines(),
            [
                f"issue view {ITEM} --json comments,labels --repo owner/name",
                f"project item-list {BOARD_PROJECT} --owner {BOARD_OWNER} "
                f"--format json --limit 100",
            ],
        )
        # The one file this run added is the stub CLI's own argv log, which is this
        # test's instrument. The gate itself writes no file, the same as `phase`.
        added = {path for path, _ in self.disk_state()} - before
        self.assertEqual(added, {str(log)}, added)

    def test_the_start_gate_reads_no_worker_and_takes_no_worker_flag(self):
        """It answers whether an item may start, which is the question before there is a
        worker to read. So the four flags that name a worker are usage errors here, and
        `--item` plus the tracker flags are the whole surface."""
        self.write_fixture(labels=[READY_FOR_AGENT])

        for flag, value in (
            ("--worktree", str(self.worktree)),
            ("--process", PROCESS_PATTERN),
            ("--rounds", "3"),
            ("--stall-after", "30m"),
        ):
            self.run_seam(
                "start",
                "--item",
                str(ITEM),
                "--gh-fixture",
                str(self.fixture),
                flag,
                value,
                expect=EXIT_USAGE,
                lines=0,
            )

        # With no board flags at all it still answers, because the label alone decides.
        self.assertTrue(
            self.start_cli(board=False, expect=EXIT_DUE).startswith(f"{START}:")
        )

    def test_a_failed_item_read_is_quiet_and_never_a_start(self):
        """A read that failed cannot say the item carries the ready state, so nothing
        starts on it. It is quiet rather than a crash, the same as every other read here."""
        self.break_fixture()

        line = self.gate(expect=EXIT_NOTHING)

        self.assertTrue(line.startswith("unreadable:"), line)
        self.assertIn("nothing starts", line)

    # --- what the seam refuses to do ---------------------------------------

    def test_the_seam_writes_no_file_and_touches_no_worker(self):
        """The refusal case for both subcommands. A live child survives every outcome, the
        branch does not move, and the disk stays byte-identical through the predicate. The
        one thing a tick writes is one tracker command, and this seam writes no file at
        all."""
        child = self.child_in(self.worktree)
        write(self.checklist, TICKED)
        self.write_fixture(labels=IMPL)
        head = self.rev("HEAD")
        before = self.disk_state()

        self.ask()  # implementation-complete
        self.assertEqual(before, self.disk_state())

        write(self.checklist, UNTICKED)
        self.backdate(3600)
        stalled_head = self.rev("HEAD")
        stalled_state = self.disk_state()

        self.ask(stall=HALF_HOUR)  # stalled
        self.ask(stall=FOUR_HOURS, expect=EXIT_NOTHING)  # nothing to do
        self.assertEqual(stalled_state, self.disk_state())

        self.write_fixture(comments=[CHANGES], labels=IMPL)
        with_verdict = self.disk_state()
        self.ask()  # verdict-request-changes
        self.assertEqual(with_verdict, self.disk_state())

        # A tick that applies a transition adds one file, and that file is the fixture's
        # own write log. Against a live tracker it is a command and not a file at all.
        self.write_fixture(labels=IMPL)
        write(self.checklist, TICKED)
        paths = {path for path, _ in self.disk_state()}
        self.apply()
        added = {path for path, _ in self.disk_state()} - paths
        self.assertEqual(added, {str(self.root / "gh.json.writes")})

        # The worker is still running: no outcome killed it. The branch is where the
        # worker left it, with nothing staged.
        self.assertIsNone(child.poll())
        self.assertEqual(self.rev("HEAD"), stalled_head)
        self.assertNotEqual(stalled_head, head)  # the backdate moved it, not the seam
        self.assertEqual(self.porcelain(), "")

    def test_the_predicate_holds_no_state_that_changes_an_answer(self):
        """Two identical ticks give the same line, so a restart of the session that
        owns the schedule costs nothing."""
        self.write_fixture(labels=IMPL)
        self.backdate(3600)

        first = self.ask(stall=HALF_HOUR)
        second = self.ask(stall=HALF_HOUR)

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("dead:"), first)
        # And a fix reads as a fix, with no memory of the earlier answer.
        write(self.checklist, TICKED)
        self.assertTrue(
            self.ask(stall=HALF_HOUR).startswith("implementation-complete:")
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

    def test_the_seam_names_no_tracker_cli(self):
        """Every tracker command comes from the adapter, so this seam writes no CLI
        name. `--tracker-cli` carries the name in its argv, and its two values are
        the adapter's own constants, so neither one is a literal in this file."""
        source = (REPO_ROOT / "scripts" / "worker_state.py").read_text()
        literals = [
            node.value
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        for cli in ("gh", "glab"):
            self.assertNotIn(cli, literals, f"{cli!r} is a literal in the seam")

        # And the flag still takes both of them, which is the argv this seam keeps.
        help_text = " ".join(self.run_seam("phase", "--help", lines=400).split())
        self.assertIn("--tracker-cli {gh,glab}", help_text)

    def test_the_seam_builds_one_adapter_and_names_its_long_arguments(self):
        """The failure mode this item is named for. One call forwarded 15 arguments
        positionally, so a reordered parameter type-checked and ran. It then printed a
        plausible wake line. One adapter replaces the four tracker values, and every
        argument past the eighth is a keyword."""
        tree = ast.parse((REPO_ROOT / "scripts" / "worker_state.py").read_text())
        built = 0
        crowded = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
            if name == "Tracker":
                built += 1
            if len(node.args) > 8:
                crowded[name] = len(node.args)

        self.assertEqual(built, 1, "the seam builds one Tracker adapter, in main()")
        self.assertEqual(crowded, {}, "these calls pass more than 8 positionally")

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

    # --- the Touch set (ADR 0046) --------------------------------------------

    def test_parse_touches_reads_the_entries_of_a_present_block(self):
        """A block with entries answers them, in the order the body carries."""
        body = (
            "## Touches\n\n- scripts/worker_state.py\n- docs/agents/orchestrator.md\n"
        )

        self.assertEqual(
            worker_state.parse_touches(body),
            ["scripts/worker_state.py", "docs/agents/orchestrator.md"],
        )

    def test_parse_touches_answers_empty_for_a_body_with_no_block(self):
        """No `## Touches` heading at all is silence, and silence is an empty list."""
        body = "## Blocked by\n\n- #179\n"

        self.assertEqual(worker_state.parse_touches(body), [])

    def test_parse_touches_answers_empty_for_a_block_with_no_entries(self):
        """A heading with nothing under it, before the next one, is still empty."""
        body = "## Touches\n\n## Blocked by\n\n- #179\n"

        self.assertEqual(worker_state.parse_touches(body), [])

    def test_parse_touches_reads_a_glob_entry_unchanged(self):
        """A glob is one more entry, read byte-identical and not expanded here."""
        body = "## Touches\n\n- scripts/*.py\n"

        self.assertEqual(worker_state.parse_touches(body), ["scripts/*.py"])

    def test_touches_overlap_is_false_for_disjoint_lists(self):
        """Two sets that share no path or glob are parallel-safe."""
        self.assertFalse(
            worker_state.touches_overlap(
                ["scripts/worker_state.py"], ["docs/agents/orchestrator.md"]
            )
        )

    def test_touches_overlap_is_true_for_an_exact_path_match(self):
        """The same path on both sides is the plainest overlap there is."""
        self.assertTrue(
            worker_state.touches_overlap(
                ["scripts/worker_state.py"], ["scripts/worker_state.py"]
            )
        )

    def test_touches_overlap_is_true_for_a_glob_matching_a_path(self):
        """Either side can carry the glob, and the match still fires."""
        self.assertTrue(
            worker_state.touches_overlap(["scripts/*.py"], ["scripts/worker_state.py"])
        )
        self.assertTrue(
            worker_state.touches_overlap(["scripts/worker_state.py"], ["scripts/*.py"])
        )

    def test_touches_overlap_is_true_where_either_side_is_empty(self):
        """An undeclared item reads as risk, so silence on either side is an overlap."""
        self.assertTrue(worker_state.touches_overlap([], ["scripts/worker_state.py"]))
        self.assertTrue(worker_state.touches_overlap(["scripts/worker_state.py"], []))
        self.assertTrue(worker_state.touches_overlap([], []))


if __name__ == "__main__":
    unittest.main()
