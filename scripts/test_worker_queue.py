#!/usr/bin/env python3
"""Behaviour tests for the queue seam: one tracker answer in, an exit code and a line out.

Every case here reads one tracker fixture file and asserts on the exit code and the
printed line. Those are the two things a caller consumes. **No case builds a worktree, a
git repository or a live agent process**, because the queue half reads none of the three.
It is a graph walk over one tracker read, and the one file it touches is the marker the
stub spawn command leaves. So this suite is fast, and the worker watch keeps the slow
fixtures in `scripts/test_worker_state.py`.

**A gate case asks the start gate in process** (`gate`). It builds one **Tracker adapter**
over the fixture file and calls `start` with it, the way `main` calls it.

**A queue case runs the whole tick through the command line** (`queue_cli`), because the
spawn is a real command through a shell and the marker file it leaves is the proof the
spawn ran. `spawned` reads that marker back, so a case proves the spawn happened rather
than that a printed line said so.

**A case whose subject is a tracker read puts a fake CLI on `PATH`** (`fake_cli`,
`fake_gh`). Each one records the argv it received and prints canned JSON. That keeps the
black-box shape of every other case: the seam runs the command it built, and the assertion
is on what the command received. Neither CLI has to be installed. `PATH` starts with that
directory for every case, so no case here can reach a real `gh` or `glab` by accident.

**A write case reads the tracker writes back out of the `<fixture>.writes` file.** One
subcommand here writes: `queue` puts `needs-human` on an item whose spawn failed.
`scripts/tracker.py` appends one line per write in fixture mode, and `writes`, `swaps` and
`work_states_after` parse that file.

    python3 -m pytest scripts/ -q
    python3 -m unittest discover -s scripts -t . -q     # fallback, no pytest
"""

import ast
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import worker_queue
from scripts.tracker import (
    BOARD_LIMIT,
    BOARD_QUERY,
    CARD_FIELD,
    CARDED_FIELDS,
    ITEM_FIELDS,
    ITEM_LIMIT,
    Tracker,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

# The module under test, as a path and as the form a subprocess runs. Both are named once,
# because three invariants below read the source file and every CLI case runs the module.
SEAM = REPO_ROOT / "scripts" / "worker_queue.py"
SEAM_MODULE = "scripts.worker_queue"

ITEM = 54

EXIT_COMPLETE = 0
EXIT_USAGE = 64

# `start` answers the fact the item's kind owns, and every quiet answer shares one code.
EXIT_DUE = 0
EXIT_NOTHING = 1

# `queue` is that predicate plus the spawn it fired, and no path through it exits 0.
EXIT_REFUSED = 2
EXIT_APPLIED = 4

# The one Work-state family, whose four values come from docs/agents/issue-tracker.md.
# `needs-human` is the one a failed spawn writes.
READY_FOR_AGENT = "ready-for-agent"
IN_PROGRESS = "in-progress"
TO_REVIEW = "to-review"
NEEDS_HUMAN = "needs-human"
WORK_STATES = (READY_FOR_AGENT, IN_PROGRESS, TO_REVIEW, NEEDS_HUMAN)

# The board coordinates and the two column names a start gate reads. They come from the
# Project board section of docs/agents/issue-tracker.md, so the seam holds none of them.
# `READY_LANE` is the column before the start column, which is the maintainer's own lane.
BOARD_PROJECT = 6
BOARD_OWNER = "someone"
START_COLUMN = "To do"
READY_LANE = "Ready"

# The three answers the start gate gives, named by the seam rather than by this file.
START = worker_queue.START
ONE_FACT = worker_queue.ONE_FACT
NO_FACT = worker_queue.NO_FACT

# The queue a tick reads. One story with two leaves, and a nested leaf under the first
# one. Then a second story with a leaf of its own, and one standalone item. The numbers
# order the candidates, so `LEAF_ONE` is the item a tick reaches first.
STORY = 300
LEAF_ONE = 301
LEAF_TWO = 302
NESTED_LEAF = 310
STANDALONE = 400
SECOND_STORY = 500
SECOND_LEAF = 501

# The label that makes a work item a spec rather than a leaf, and the two values
# `parallel_check` takes. All three are named by the seam rather than by this file.
USER_STORY = worker_queue.USER_STORY
TOUCHES = worker_queue.TOUCHES
OFF = worker_queue.OFF

# A value for each of the three flags that name a worker. No subcommand here takes one,
# so a case passes them only to prove each is a usage error. The pattern is the one the
# harness reference gives, and nothing here starts a process to match it.
PROCESS_PATTERN = "[Pp]ython"

# What the spawn command touches, one file per item it ran for. A queue case reads the
# disk for that, so it proves the spawn ran rather than that a line said so.
SPAWN_MARKER = "spawned-"


def body(parent=0, blocked=(), touches=()):
    """One work item body, holding the three `##` blocks a queue tick reads.

    Each block takes the shape the `to-tickets` template writes, so a case names the edges
    it wants rather than the Markdown behind them.
    """
    text = ""
    if parent:
        text += f"## Parent\n\n#{parent}\n\n"
    if blocked:
        text += "## Blocked by\n\n" + "".join(f"- #{one}\n" for one in blocked) + "\n"
    if touches:
        text += "## Touches\n\n" + "".join(f"- {one}\n" for one in touches) + "\n"
    return text


def story_queue():
    """A queue holding one authorised story, its two leaves, and one standalone item.

    Each record carries the fact its kind owns (ADR 0062). The story wears no label and its
    card sits in the start column, which is the whole gate for a spec. Its two leaves wear
    `ready-for-agent` with no card of their own, and they declare disjoint Touch sets. The
    standalone item holds both facts of its own and belongs to no story run. Each case takes
    this and edits the records it is about.
    """
    return {
        str(STORY): {
            "labels": [USER_STORY],
            "board": START_COLUMN,
            "title": "the story",
        },
        str(LEAF_ONE): {
            "labels": [READY_FOR_AGENT],
            "title": "the first leaf",
            "body": body(parent=STORY, touches=["scripts/one.py"]),
        },
        str(LEAF_TWO): {
            "labels": [READY_FOR_AGENT],
            "title": "the second leaf",
            "body": body(parent=STORY, touches=["scripts/two.py"]),
        },
        str(STANDALONE): {
            "labels": [READY_FOR_AGENT],
            "board": START_COLUMN,
            "title": "a standalone item",
            "body": body(touches=["docs/one.md"]),
        },
    }


def listed(number, labels=(), board="", title="an item", body=""):
    """One work item in the shape a live `gh issue list` answers, plus its card.

    `board` is the `Status` name on that item's card. A labelled read carries it back as a
    project field, and the open-items read asks for no such field, so the stub below drops
    it there.
    """
    return {
        "number": number,
        "title": title,
        "labels": [{"name": one} for one in labels],
        "body": body,
        "board": board,
    }


class WorkerQueueTestCase(unittest.TestCase):
    """One tracker answer, and nothing else on disk.

    This is the whole state the queue reads: a fixture file that stands in for every
    tracker read, and a stub CLI directory on `PATH`. No worktree, no git repository and
    no agent process, because the queue half reads none of them.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.write_fixture()

        # A stub CLI written here wins over an installed one, so no case can reach
        # a real tracker.
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}"}

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

    def fake_gh(self, labels=(), card="", open_items=(), sets=None):
        """A `gh` that answers each read a start gate makes, and its argv log.

        Four reads, told apart the way the adapter builds them: an item view for the
        labels, an item view for the card, a list of the open work items, and one list per
        labelled set. `sets` maps a label name to the `listed` records that set holds, and
        the `board` value of each record becomes that item's card.

        A command the gate never makes exits non-zero. So a board read that reaches this
        stub fails the case rather than answering it.
        """
        log = self.root / "gh.argv"
        script = self.bin / "gh"
        script.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            f"open({str(log)!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
            f"labels, card = {list(labels)!r}, {card!r}\n"
            f"open_items, sets = {list(open_items)!r}, {dict(sets or {})!r}\n"
            "argv = sys.argv[1:]\n"
            "def carded(rows):\n"
            "    return [dict(one, projectItems=[{'status': {'name': one['board']},\n"
            "                                     'title': 'the board'}]\n"
            "                                   if one['board'] else [])\n"
            "            for one in rows]\n"
            "if argv[:2] == ['issue', 'view']:\n"
            "    print(json.dumps({'projectItems': [{'status': {'name': card},\n"
            "                                        'title': 'the board'}] if card else []}\n"
            "                     if 'projectItems' in argv else\n"
            "                     {'labels': [{'name': one} for one in labels],\n"
            "                      'comments': []}))\n"
            "elif argv[:2] == ['issue', 'list'] and '--label' in argv:\n"
            "    print(json.dumps(carded(sets.get(argv[argv.index('--label') + 1], []))))\n"
            "elif argv[:2] == ['issue', 'list']:\n"
            "    print(json.dumps(open_items))\n"
            "else:\n"
            "    print('stub: the gate makes no such read', file=sys.stderr)\n"
            "    raise SystemExit(9)\n"
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

    def run_seam(self, *argv, expect=0, lines=1):
        """Run the seam and return what it printed, with the line count asserted."""
        proc = subprocess.run(
            [sys.executable, "-m", SEAM_MODULE, *argv],
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

    def adapter(self):
        """The one Tracker adapter a run builds, over this case's fixture file.

        `main` builds it from `--tracker-cli`, `--tracker-host`, `--repo` and
        `--gh-fixture`. A case that reads the fixture needs only the last of the four. A
        case that needs the other three runs the command line instead.
        """
        return Tracker(fixture=str(self.fixture))

    def gate(self, *, expect, project=BOARD_PROJECT, owner=BOARD_OWNER, column=None):
        """Ask the start gate in process, through one adapter.

        The item, the adapter, then the three board coordinates. That is the call `main`
        makes. `column=None` means the start column, and a case that wants no board at all
        passes `project=0, owner="", column=""`.
        """
        code, line = worker_queue.start(
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

    def report_cli(
        self, *extra, expect=EXIT_COMPLETE, fixture=True, board=True, lines=6
    ):
        """Run the board report through the command line.

        A human reads this one, so it prints one line per gap rather than one line in all.
        `lines` is the ceiling `run_seam` asserts: one head line and one per gap.
        """
        return self.run_seam(
            "report",
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
            lines=lines,
        )

    def disk_state(self):
        return sorted(
            (str(path), path.stat().st_mtime if path.is_file() else 0)
            for path in self.root.rglob("*")
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

    def test_one_fact_is_the_card_in_the_start_column_with_no_label(self):
        """The card is read first, so the one-fact state is a card in the start column
        that carries no label. That is a forgotten label, and it is the one disagreement a
        maintainer repairs. It is never an error and never a refusal (ADR 0061)."""
        self.write_fixture(labels=[], board=START_COLUMN)

        card_only = self.gate(expect=EXIT_NOTHING)

        self.assertTrue(card_only.startswith(f"{ONE_FACT}:"), card_only)
        self.assertIn("starts nothing", card_only)
        self.assertIn(f"no {READY_FOR_AGENT} label", card_only)
        self.assertIn(repr(START_COLUMN), card_only)
        # An error word appears nowhere, and no tracker write went out.
        for word in ("error", "refused", "unreadable"):
            self.assertNotIn(word, card_only)
        self.assertEqual(self.writes(), [])

    def test_a_user_story_is_authorised_by_its_card_and_never_by_a_label(self):
        """The first row of the gate table. A story is a spec, and no worker implements one.
        So its card in the start column is the whole gate, and it needs no `ready-for-agent`
        label ever. A story card outside that column authorises nothing (ADR 0062)."""
        self.write_fixture(labels=[USER_STORY], board=START_COLUMN)
        authorised = self.gate(expect=EXIT_DUE)

        self.write_fixture(labels=[USER_STORY], board=READY_LANE)
        parked = self.gate(expect=EXIT_NOTHING)

        self.assertTrue(authorised.startswith(f"{START}:"), authorised)
        self.assertIn("authorises its own children", authorised)
        self.assertTrue(parked.startswith(f"{NO_FACT}:"), parked)
        self.assertIn("authorises nothing", parked)
        # The label is never asked for on this row, so neither line names a missing label
        # and neither answer is the forgotten-label state.
        for line in (authorised, parked):
            self.assertIn(f"is a {USER_STORY} spec", line)
            self.assertNotIn(ONE_FACT, line)
            self.assertNotIn(f"no {READY_FOR_AGENT} label", line)
        self.assertEqual(self.writes(), [])

    def test_a_card_outside_the_start_column_rests_whatever_its_label_says(self):
        """The board is the narrower fact, so a card outside the start column is the quiet
        state. A labelled item parked in the lane before it reads the same way as an
        unlabelled one, because the board already says where each sits. This is the case
        ADR 0061 moved off the one-fact state, and nothing about what starts moved."""
        self.write_fixture(labels=[READY_FOR_AGENT], board=READY_LANE)
        label_only = self.gate(expect=EXIT_NOTHING)

        self.write_fixture(labels=[], board=READY_LANE)
        in_a_lane = self.gate(expect=EXIT_NOTHING)

        self.write_fixture(labels=[])
        no_card = self.gate(expect=EXIT_NOTHING)

        for line in (label_only, in_a_lane, no_card):
            self.assertTrue(line.startswith(f"{NO_FACT}:"), line)
        self.assertIn(repr(READY_LANE), label_only)
        self.assertIn("no card", no_card)
        self.assertEqual(self.writes(), [])

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

    def test_a_failed_card_read_is_unreadable_and_never_a_start(self):
        """Nothing starts on a card this gate cannot read, which is the safe direction. The
        card read is one call per gate now rather than one per item, so a failure raises out
        of the gate and the answer names itself (ADR 0064)."""
        log = self.fake_cli("gh", api={})

        line = self.start_cli("--repo", "owner/name", fixture=False)

        self.assertTrue(line.startswith("unreadable:"), line)
        self.assertIn("nothing starts", line)
        # The read really ran and really failed: the stub CLI has no issue payload.
        self.assertIn("issue view", log.read_text())

    def test_the_start_gate_reads_the_card_with_the_item_and_lists_no_board(self):
        """The card arrives with the item, and no whole board is listed (ADR 0064). One item
        view for the labels, one for this item's own card, and the labelled sets plus the
        open items for the story tree above it. No write of any kind, and the column is a
        name and never an option id."""
        log = self.fake_gh(
            labels=[READY_FOR_AGENT],
            card=START_COLUMN,
            open_items=[listed(ITEM, [READY_FOR_AGENT])],
            sets={READY_FOR_AGENT: [listed(ITEM, [READY_FOR_AGENT], START_COLUMN)]},
        )
        before = {path for path, _ in self.disk_state()}

        line = self.start_cli("--repo", "owner/name", fixture=False, expect=EXIT_DUE)

        self.assertTrue(line.startswith(f"{START}:"), line)
        ran = log.read_text().splitlines()
        self.assertEqual(
            ran,
            [
                f"issue view {ITEM} --json comments,labels --repo owner/name",
                f"issue view {ITEM} --json {CARD_FIELD} --repo owner/name",
                f"issue list --state open --limit {ITEM_LIMIT} "
                f"--json {ITEM_FIELDS} --repo owner/name",
                f"issue list --state open --label {USER_STORY} --limit {ITEM_LIMIT} "
                f"--json {CARDED_FIELDS} --repo owner/name",
                f"issue list --state open --label {READY_FOR_AGENT} --limit {ITEM_LIMIT} "
                f"--json {CARDED_FIELDS} --repo owner/name",
            ],
        )
        self.assertNotIn("project item-list", log.read_text())
        # The one file this run added is the stub CLI's own argv log, which is this
        # test's instrument. The gate itself writes no file, the same as `phase`.
        added = {path for path, _ in self.disk_state()} - before
        self.assertEqual(added, {str(log)}, added)

    def test_the_gate_answers_whatever_the_size_of_the_board(self):
        """The board grows every week and a new card sits last, so a whole-board list
        stopped at its limit and answered "no card" for every card past it. The card rides
        the item now, so no size of board reaches this answer and the gate lists none
        (ADR 0064)."""
        log = self.fake_gh(
            labels=[READY_FOR_AGENT],
            card=START_COLUMN,
            open_items=[listed(ITEM, [READY_FOR_AGENT])],
            sets={READY_FOR_AGENT: [listed(ITEM, [READY_FOR_AGENT], START_COLUMN)]},
        )

        line = self.start_cli("--repo", "owner/name", fixture=False, expect=EXIT_DUE)

        self.assertTrue(line.startswith(f"{START}:"), line)
        self.assertIn(repr(START_COLUMN), line)
        # No card limit gates this answer, because no read here asks a board for its cards.
        self.assertNotIn("item-list", log.read_text())
        self.assertNotIn("--limit 500", log.read_text())

    def test_the_start_gate_reads_no_worker_and_takes_no_worker_flag(self):
        """It answers whether an item may start, which is the question before there is a
        worker to read. So the three flags that name a worker are usage errors here, and
        `--item` plus the tracker flags are the whole surface."""
        self.write_fixture(labels=[READY_FOR_AGENT])

        for flag, value in (
            ("--worktree", str(self.root)),
            ("--process", PROCESS_PATTERN),
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
        starts on it. It is quiet rather than a crash, the same as every other read here.
        """
        self.break_fixture()

        line = self.gate(expect=EXIT_NOTHING)

        self.assertTrue(line.startswith("unreadable:"), line)
        self.assertIn("nothing starts", line)

    def test_the_seam_names_no_tool(self):
        """The send command is a template the spawn resolves from the tool file's
        operation 4, so the module names no Tool in a command, a default or an
        example. The one place a tool name may appear is a citation of the reference
        file that records a measurement, and this asserts every hit is one of those."""
        source = SEAM.read_text().lower()
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
            worker_queue.parse_touches(body),
            ["scripts/worker_state.py", "docs/agents/orchestrator.md"],
        )

    def test_parse_touches_answers_empty_for_a_body_with_no_block(self):
        """No `## Touches` heading at all is silence, and silence is an empty list."""
        body = "## Blocked by\n\n- #179\n"

        self.assertEqual(worker_queue.parse_touches(body), [])

    def test_parse_touches_answers_empty_for_a_block_with_no_entries(self):
        """A heading with nothing under it, before the next one, is still empty."""
        body = "## Touches\n\n## Blocked by\n\n- #179\n"

        self.assertEqual(worker_queue.parse_touches(body), [])

    def test_parse_touches_reads_a_glob_entry_unchanged(self):
        """A glob is one more entry, read byte-identical and not expanded here."""
        body = "## Touches\n\n- scripts/*.py\n"

        self.assertEqual(worker_queue.parse_touches(body), ["scripts/*.py"])

    def test_touches_overlap_is_false_for_disjoint_lists(self):
        """Two sets that share no path or glob are parallel-safe."""
        self.assertFalse(
            worker_queue.touches_overlap(
                ["scripts/worker_state.py"], ["docs/agents/orchestrator.md"]
            )
        )

    def test_touches_overlap_is_true_for_an_exact_path_match(self):
        """The same path on both sides is the plainest overlap there is."""
        self.assertTrue(
            worker_queue.touches_overlap(
                ["scripts/worker_state.py"], ["scripts/worker_state.py"]
            )
        )

    def test_touches_overlap_is_true_for_a_glob_matching_a_path(self):
        """Either side can carry the glob, and the match still fires."""
        self.assertTrue(
            worker_queue.touches_overlap(["scripts/*.py"], ["scripts/worker_state.py"])
        )
        self.assertTrue(
            worker_queue.touches_overlap(["scripts/worker_state.py"], ["scripts/*.py"])
        )

    def test_touches_overlap_is_true_where_either_side_is_empty(self):
        """An undeclared item reads as risk, so silence on either side is an overlap."""
        self.assertTrue(worker_queue.touches_overlap([], ["scripts/worker_state.py"]))
        self.assertTrue(worker_queue.touches_overlap(["scripts/worker_state.py"], []))
        self.assertTrue(worker_queue.touches_overlap([], []))

    # --- the queue tick (ADR 0045, ADR 0046) --------------------------------

    def write_queue(self, items):
        """Write a fixture holding a whole queue, and reset the write log beside it.

        `write_fixture` holds one item, because every other case here reads one item. A
        queue case reads them all, so it passes the records itself. Each value is the
        record `scripts/tracker.py` documents, and a record with no `state` reads as open.
        """
        self.fixture = self.root / "gh.json"
        self.fixture.write_text(json.dumps({"items": items}))
        (self.root / "gh.json.writes").unlink(missing_ok=True)

    def spawn_command(self):
        """A spawn command that touches one file per item, and starts no agent at all."""
        return f"touch {self.root / SPAWN_MARKER}{{item}}"

    def spawned(self):
        """Every work item the spawn command ran for, lowest number first."""
        return sorted(
            int(path.name[len(SPAWN_MARKER) :])
            for path in self.root.glob(f"{SPAWN_MARKER}*")
        )

    def clear_spawned(self):
        """Forget the earlier ticks, so the next assertion reads one tick's own spawns."""
        for path in self.root.glob(f"{SPAWN_MARKER}*"):
            path.unlink()

    def queue_cli(
        self,
        *extra,
        expect=EXIT_APPLIED,
        stories=2,
        workers=4,
        check=TOUCHES,
        spawn=None,
        board=True,
        fixture=True,
        lines=1,
    ):
        """Run the whole body of a queue tick through the command line."""
        return self.run_seam(
            "queue",
            *(("--gh-fixture", str(self.fixture)) if fixture else ()),
            "--max-stories",
            str(stories),
            "--max-workers",
            str(workers),
            "--parallel-check",
            check,
            "--spawn-command",
            self.spawn_command() if spawn is None else spawn,
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
            lines=lines,
        )

    def test_an_empty_queue_starts_nothing(self):
        """No open work item is no error. The tick is quiet, so the run records as
        skipped and the schedule's own prompt and provider never load."""
        self.write_queue({})

        line = self.queue_cli(expect=EXIT_NOTHING)

        self.assertTrue(line.startswith("nothing:"), line)
        self.assertEqual(self.spawned(), [])
        self.assertEqual(self.writes(), [])

    def test_one_startable_item_starts_and_the_tick_writes_no_label(self):
        """The item that holds both facts starts. **The tick writes no work-state label of
        its own**: the spawn seam writes the one label at its own step, before the prompt
        reaches the worker. So a grep for a label write finds no path here."""
        items = story_queue()
        for gone in (STORY, LEAF_ONE, LEAF_TWO):
            items.pop(str(gone))
        self.write_queue(items)

        line = self.queue_cli()

        self.assertTrue(line.startswith(f"{START}:"), line)
        self.assertIn(f"#{STANDALONE}", line)
        self.assertIn("applied: the spawn ran:", line)
        self.assertEqual(self.spawned(), [STANDALONE])
        self.assertEqual(self.writes(), [])

    def test_one_item_per_tick_whatever_the_queue_holds(self):
        """A queue holding three startable items starts one. A tick that starts three is
        a tick that fills a disk while nobody watches, and no flag raises the rule."""
        self.write_queue(story_queue())

        self.queue_cli()

        self.assertEqual(self.spawned(), [LEAF_ONE])

    def test_a_started_parent_is_never_spawned_for_the_work_itself(self):
        """A `user-story` parent whose card sits in the start column is a spec. The tick
        descends to its unblocked children and starts one of those, and it writes no
        `ready-for-agent` label on any child. So the rule that only a human writes that
        label survives."""
        self.write_queue(story_queue())

        line = self.queue_cli()

        self.assertIn(f"work item #{LEAF_ONE} is the one item", line)
        self.assertEqual(self.spawned(), [LEAF_ONE])
        self.assertEqual(self.writes(), [])

        # A live story run keeps authorising its children. The parent's card can go back to
        # the maintainer's lane and the run still owns them, on their own labels.
        items = story_queue()
        items[str(LEAF_ONE)]["labels"] = [IN_PROGRESS]
        items[str(STORY)]["board"] = READY_LANE
        items.pop(str(STANDALONE))
        self.write_queue(items)
        self.clear_spawned()

        self.queue_cli()

        self.assertEqual(self.spawned(), [LEAF_TWO])

    def test_a_nested_user_story_child_is_descended_through(self):
        """A child that carries the label is a nested spec, so the descent continues to
        the implementable leaves."""
        items = story_queue()
        items.pop(str(LEAF_TWO))
        items.pop(str(STANDALONE))
        items[str(LEAF_ONE)]["labels"] = [USER_STORY]
        items[str(NESTED_LEAF)] = {
            "labels": [READY_FOR_AGENT],
            "title": "the nested leaf",
            "body": body(parent=LEAF_ONE, touches=["scripts/three.py"]),
        }
        self.write_queue(items)

        line = self.queue_cli()

        self.assertIn(f"work item #{NESTED_LEAF} is the one item", line)
        self.assertEqual(self.spawned(), [NESTED_LEAF])

    # --- the two representations of the Parent edge (ADR 0065) ---------------

    def test_a_child_linked_only_in_the_tracker_ui_is_still_descended_to(self):
        """The native parent link is one half of the **Parent edge**, and the descent unions
        the two. So a child a maintainer linked by hand, with no `## Parent` line in its
        body at all, is a real child of that story and the tick reaches it."""
        items = story_queue()
        items.pop(str(STANDALONE))
        items.pop(str(LEAF_TWO))
        items[str(LEAF_ONE)]["body"] = body(touches=["scripts/one.py"])
        items[str(LEAF_ONE)]["parent"] = STORY
        self.write_queue(items)

        line = self.queue_cli()

        self.assertIn(f"work item #{LEAF_ONE} is the one item", line)
        self.assertEqual(self.spawned(), [LEAF_ONE])

    def test_the_two_parent_edges_union_and_a_child_that_carries_both_counts_once(self):
        """The union is keyed on the work item number, so a child that carries both
        representations counts once. Where the two disagree, both parents keep the child, so
        a wrong edge shows up as an extra child and never as a missing one."""
        both = {"number": 9, "body": body(parent=STORY), "parent": STORY}
        split = {"number": 11, "body": body(parent=LEAF_ONE), "parent": STORY}

        self.assertEqual(worker_queue.parent_edges(both), [STORY])
        self.assertEqual(worker_queue.parent_edges(split), [STORY, LEAF_ONE])
        # The upward walk takes one parent, and the native link leads.
        self.assertEqual(worker_queue.parent_of(split), STORY)
        # An item with neither edge names no parent, and an absent key is not an error.
        self.assertEqual(worker_queue.parent_edges({"body": ""}), [])
        self.assertEqual(worker_queue.parent_of({}), 0)
        # A disagreeing child is filed under each parent, once under each.
        self.assertEqual(
            worker_queue.children_of([both, split]),
            {STORY: [9, 11], LEAF_ONE: [11]},
        )

    # --- the three rows of the gate table (ADR 0062) -------------------------

    def test_a_story_card_authorises_the_whole_run_with_no_label_on_the_story(self):
        """The first row, through a whole tick. The story wears no `ready-for-agent` label
        and its card sits in the start column, and that one drag authorises the run. The
        story itself is never spawned, because it is a spec."""
        items = story_queue()
        items.pop(str(STANDALONE))
        self.assertNotIn(READY_FOR_AGENT, items[str(STORY)]["labels"])
        self.write_queue(items)

        line = self.queue_cli()

        self.assertIn(f"work item #{LEAF_ONE} is the one item", line)
        self.assertEqual(self.spawned(), [LEAF_ONE])
        self.assertEqual(self.writes(), [])

        # The next tick reaches the second child, and no tick reaches the story itself.
        items[str(LEAF_ONE)]["labels"] = [IN_PROGRESS]
        self.write_queue(items)

        self.queue_cli()

        self.assertEqual(self.spawned(), [LEAF_ONE, LEAF_TWO])

    def test_a_child_of_an_authorised_story_is_started_on_its_label_alone(self):
        """The second row. The child's own column is never read, so a maintainer drags the
        story card and no child card. A card in the maintainer's own lane starts the same
        way as no card at all."""
        items = story_queue()
        items.pop(str(STANDALONE))
        items.pop(str(LEAF_TWO))
        items[str(LEAF_ONE)]["board"] = READY_LANE
        self.write_queue(items)

        line = self.queue_cli()

        self.assertIn(f"work item #{LEAF_ONE} is the one item", line)
        self.assertEqual(self.spawned(), [LEAF_ONE])

        # The base fixture gives that child no card at all, and it starts the same way.
        items = story_queue()
        items.pop(str(STANDALONE))
        items.pop(str(LEAF_TWO))
        self.write_queue(items)
        self.clear_spawned()

        self.queue_cli()

        self.assertEqual(self.spawned(), [LEAF_ONE])

    def test_an_unlabelled_child_of_an_authorised_story_is_no_candidate(self):
        """The guard on the second row, and the behaviour ADR 0062 narrowed. The descent
        once reached every unblocked child, so a ticket nobody approved started because its
        parent moved. Now a child with no label stays stopped, and that is how a maintainer
        parks one ticket under a running story."""
        items = story_queue()
        items.pop(str(STANDALONE))
        items[str(LEAF_ONE)]["labels"] = []
        self.write_queue(items)

        self.queue_cli()

        # The labelled sibling started, so the story was authorised and the descent ran.
        self.assertEqual(self.spawned(), [LEAF_TWO])

        items.pop(str(LEAF_TWO))
        self.write_queue(items)
        self.clear_spawned()

        line = self.queue_cli(expect=EXIT_NOTHING)

        self.assertIn("is startable on this tick", line)
        self.assertEqual(self.spawned(), [])
        self.assertEqual(self.writes(), [])

    def test_a_standalone_leaf_still_needs_both_facts(self):
        """The third row, unchanged. One fact starts nothing on its own, whichever fact it
        is. This is the path a maintainer takes to run one ticket and nothing else."""
        items = story_queue()
        for gone in (STORY, LEAF_ONE, LEAF_TWO):
            items.pop(str(gone))
        items[str(STANDALONE)]["board"] = READY_LANE
        self.write_queue(items)

        label_only = self.queue_cli(expect=EXIT_NOTHING)

        self.assertEqual(self.spawned(), [])

        items[str(STANDALONE)]["board"] = START_COLUMN
        items[str(STANDALONE)]["labels"] = []
        self.write_queue(items)

        card_only = self.queue_cli(expect=EXIT_NOTHING)

        # A tick reads the two labelled sets, so an unlabelled item is in neither of them
        # and no tick can name its card. `report` names it (ADR 0064).
        self.assertTrue(card_only.startswith("nothing:"), card_only)
        self.assertEqual(self.spawned(), [])
        self.assertNotIn("no label", label_only)

        items[str(STANDALONE)]["labels"] = [READY_FOR_AGENT]
        self.write_queue(items)

        self.queue_cli()

        self.assertEqual(self.spawned(), [STANDALONE])

    def test_a_story_card_outside_the_start_column_authorises_nothing(self):
        """A parked story is silent, as a parked leaf already is. None of its children
        becomes a candidate through it, whatever label each child wears."""
        items = story_queue()
        items.pop(str(STANDALONE))
        items[str(STORY)]["board"] = READY_LANE
        self.write_queue(items)

        line = self.queue_cli(expect=EXIT_NOTHING)

        self.assertEqual(self.spawned(), [])
        self.assertEqual(self.writes(), [])

        # The card is the one fact that moved, so the same queue starts a child once the
        # story card is back in the start column.
        items[str(STORY)]["board"] = START_COLUMN
        self.write_queue(items)

        self.queue_cli()

        self.assertEqual(self.spawned(), [LEAF_ONE])
        self.assertNotIn(f"#{STORY}", line)

    def test_a_quiet_tick_names_no_forgotten_label_at_all(self):
        """A tick reads the two labelled sets, so an unlabelled item is in neither of them
        and the tick cannot see its card. The forgotten label moved to `report`, which is
        the one command that reads the board (ADR 0064)."""
        items = story_queue()
        items[str(LEAF_ONE)]["labels"] = []
        items[str(LEAF_TWO)]["labels"] = []
        items[str(STANDALONE)]["labels"] = []
        self.write_queue(items)

        line = self.queue_cli(expect=EXIT_NOTHING)

        self.assertTrue(line.startswith("nothing:"), line)
        self.assertNotIn("no label", line)
        self.assertNotIn(f"#{STANDALONE}", line)
        self.assertNotIn(f"#{STORY}", line)
        self.assertEqual(self.spawned(), [])
        self.assertEqual(self.writes(), [])

    def test_a_child_with_an_open_blocker_stays_unstarted(self):
        """The descent reads the open-blocker predicate the Ready queue already reads. A
        blocker absent from the open items is closed, and only a still-open edge blocks.
        """
        items = story_queue()
        items.pop(str(STANDALONE))
        items[str(LEAF_ONE)]["body"] = body(
            parent=STORY, blocked=[LEAF_TWO], touches=["scripts/one.py"]
        )
        self.write_queue(items)

        self.queue_cli()

        self.assertEqual(self.spawned(), [LEAF_TWO])

        # The blocker is closed once it is absent from the open items, so the same edge
        # blocks nothing on the next tick.
        items.pop(str(LEAF_TWO))
        self.write_queue(items)
        self.clear_spawned()

        self.queue_cli()

        self.assertEqual(self.spawned(), [LEAF_ONE])

    def test_an_overlapping_touch_set_delays_the_item_and_cancels_nothing(self):
        """Two startable items whose Touch sets overlap run one after the other. The
        second tick reads the first as a live worker and waits. **The delay cancels
        nothing**: the item starts on the next tick with no live overlap."""
        items = story_queue()
        items.pop(str(STANDALONE))
        items[str(LEAF_TWO)]["body"] = body(parent=STORY, touches=["scripts/one.py"])
        self.write_queue(items)

        self.queue_cli()

        self.assertEqual(self.spawned(), [LEAF_ONE])

        items[str(LEAF_ONE)]["labels"] = [IN_PROGRESS]
        self.write_queue(items)
        self.clear_spawned()

        delayed = self.queue_cli(expect=EXIT_NOTHING)

        self.assertIn("every candidate waits", delayed)
        self.assertIn(f"#{LEAF_TWO} overlaps live worker #{LEAF_ONE}", delayed)
        self.assertEqual(self.spawned(), [])
        self.assertEqual(self.writes(), [])

        items.pop(str(LEAF_ONE))
        self.write_queue(items)

        self.queue_cli()

        self.assertEqual(self.spawned(), [LEAF_TWO])

    def test_two_disjoint_touch_sets_run_in_parallel(self):
        """Nothing delays the second item where the two blocks name no shared path. One
        tick still starts one item, so the two start a minute apart."""
        items = story_queue()
        items.pop(str(STANDALONE))
        self.write_queue(items)

        self.queue_cli()

        items[str(LEAF_ONE)]["labels"] = [IN_PROGRESS]
        self.write_queue(items)

        self.queue_cli()

        self.assertEqual(self.spawned(), [LEAF_ONE, LEAF_TWO])

    def test_with_parallel_check_off_no_comparison_runs(self):
        """`off` compares nothing, and the behaviour before ADR 0046 stands. So the
        overlap that delays under `touches` starts here."""
        items = story_queue()
        items.pop(str(STANDALONE))
        items[str(LEAF_TWO)]["body"] = body(parent=STORY, touches=["scripts/one.py"])
        items[str(LEAF_ONE)]["labels"] = [IN_PROGRESS]
        self.write_queue(items)

        self.queue_cli(expect=EXIT_NOTHING, check=TOUCHES)

        self.assertEqual(self.spawned(), [])

        self.queue_cli(check=OFF)

        self.assertEqual(self.spawned(), [LEAF_TWO])

    def test_either_roof_full_on_its_own_starts_nothing(self):
        """`max_stories` bounds live story runs, and the worker cap bounds live workers
        across every run. Either one full starts nothing, so the lower roof wins. Both
        delay and neither cancels."""
        items = story_queue()
        items.pop(str(LEAF_TWO))
        items.pop(str(STANDALONE))
        items[str(LEAF_ONE)]["labels"] = [IN_PROGRESS]
        items[str(SECOND_STORY)] = {
            "labels": [USER_STORY],
            "board": START_COLUMN,
            "title": "the second story",
        }
        items[str(SECOND_LEAF)] = {
            "labels": [READY_FOR_AGENT],
            "title": "the leaf of the second story",
            "body": body(parent=SECOND_STORY, touches=["scripts/four.py"]),
        }
        self.write_queue(items)

        capped = self.queue_cli(expect=EXIT_NOTHING, workers=1)

        self.assertIn("against a worker cap of 1", capped)
        self.assertEqual(self.spawned(), [])

        roofed = self.queue_cli(expect=EXIT_NOTHING, stories=1)

        self.assertIn(f"#{SECOND_LEAF} opens a story run past the roof of 1", roofed)
        self.assertEqual(self.spawned(), [])
        self.assertEqual(self.writes(), [])

        # With room for the second run it starts, so each roof delayed and cancelled
        # nothing.
        self.queue_cli(stories=2, workers=4)

        self.assertEqual(self.spawned(), [SECOND_LEAF])

    def test_a_standalone_item_holds_no_story_slot(self):
        """The roof bounds story runs. An item with no `user-story` ancestor is no story
        run, so a full story roof leaves it startable."""
        items = story_queue()
        items.pop(str(LEAF_TWO))
        items[str(LEAF_ONE)]["labels"] = [IN_PROGRESS]
        self.write_queue(items)

        line = self.queue_cli(stories=1)

        self.assertIn(f"work item #{STANDALONE} is the one item", line)
        self.assertEqual(self.spawned(), [STANDALONE])

    def test_a_card_parked_outside_the_start_column_is_not_named(self):
        """The board is the narrower fact, so a labelled item whose card sits in the lane
        before the start column is the resting state of a groomed backlog. Naming it made
        every tick recite the backlog instead of the one item a maintainer acts on, so ADR
        0061 took it off the line. Nothing about what starts moved."""
        items = story_queue()
        items[str(STORY)]["board"] = READY_LANE
        items[str(STANDALONE)]["board"] = READY_LANE
        self.write_queue(items)

        line = self.queue_cli(expect=EXIT_NOTHING)

        self.assertNotIn("no label", line)
        self.assertNotIn(f"#{STORY}", line)
        self.assertNotIn(f"#{STANDALONE}", line)
        self.assertEqual(self.spawned(), [])
        self.assertEqual(self.writes(), [])

    def test_start_and_the_queue_agree_on_a_child_of_an_authorised_story(self):
        """One table answers all three rows, so the two subcommands cannot disagree about
        one item (ADR 0064). A labelled child of an authorised story is the row that used to
        split: the tick started it, and the gate that answers the same question called it
        parked, because the child row lived in the tick alone."""
        items = story_queue()
        items.pop(str(STANDALONE))
        self.write_queue(items)

        started = self.queue_cli()
        child = worker_queue.start(
            LEAF_ONE, self.adapter(), BOARD_PROJECT, BOARD_OWNER, START_COLUMN
        )

        self.assertEqual(self.spawned(), [LEAF_ONE])
        self.assertIn(f"work item #{LEAF_ONE} is the one item", started)
        self.assertEqual(child[0], EXIT_DUE, child[1])
        self.assertTrue(child[1].startswith(f"{START}:"), child[1])
        self.assertIn(f"#{STORY} is an authorised {USER_STORY}", child[1])

        # The child carries no card of its own, and the gate says so rather than reading one.
        self.assertIn("Its own column is not read", child[1])

        # Take the label off that child and both answers move together.
        items[str(LEAF_ONE)]["labels"] = []
        self.write_queue(items)
        self.clear_spawned()

        self.queue_cli()
        stopped = worker_queue.start(
            LEAF_ONE, self.adapter(), BOARD_PROJECT, BOARD_OWNER, START_COLUMN
        )

        self.assertEqual(self.spawned(), [LEAF_TWO])
        self.assertEqual(stopped[0], EXIT_NOTHING, stopped[1])
        self.assertTrue(stopped[1].startswith(f"{NO_FACT}:"), stopped[1])
        self.assertIn("stays stopped", stopped[1])

    # --- the report verb (ADR 0064) -----------------------------------------

    def test_the_report_names_the_four_gaps_and_writes_nothing(self):
        """The one whole-board read left, and a human runs it. A forgotten label cannot ride
        a tick line any more, because a tick reads the two labelled sets. So this verb is
        where each disagreement between the board and the labels is named."""
        items = story_queue()
        # A card in the start column with no label, which is the forgotten label.
        items[str(STANDALONE)]["labels"] = []
        # A labelled leaf with a card in the lane before the start column.
        items[str(LEAF_ONE)]["board"] = READY_LANE
        # A labelled leaf with no card at all, which `story_queue` already gives LEAF_TWO.
        self.write_queue(items)

        line = self.report_cli()

        self.assertIn(f"{len(items) - 1} live card(s) on project {BOARD_PROJECT}", line)
        self.assertIn(f"{len(items)} open work item(s)", line)
        self.assertIn(f"with no {READY_FOR_AGENT} label", line)
        self.assertIn(f"#{STANDALONE}", line)
        self.assertIn(f"card outside {START_COLUMN!r}", line)
        self.assertIn("no card at all", line)
        self.assertIn(f"#{LEAF_TWO}", line)
        self.assertEqual(self.writes(), [])

    def test_the_report_names_no_user_story_as_a_forgotten_label(self):
        """A story with no label is its correct resting state, so naming it is noise
        (ADR 0062). A leaf in the same column with no label is named, so the narrowing is
        for one kind and for nothing else."""
        items = story_queue()
        items[str(STANDALONE)]["labels"] = []
        self.write_queue(items)

        line = self.report_cli()

        self.assertIn(f"with no {READY_FOR_AGENT} label", line)
        self.assertIn(f"#{STANDALONE}", line)
        self.assertNotIn(
            f"1 card(s) sit in {START_COLUMN!r} with no", line.split("\n")[0]
        )
        forgotten = [
            one
            for one in line.splitlines()
            if f"with no {READY_FOR_AGENT} label" in one
        ]
        self.assertEqual(
            forgotten,
            [
                f"1 card(s) sit in {START_COLUMN!r} "
                f"with no {READY_FOR_AGENT} label: #{STANDALONE}"
            ],
        )

    def test_the_report_reads_the_whole_board_and_a_tick_reads_none(self):
        """The board read moved here whole, and the tick lists no board at all. So the one
        `gh project item-list` call in this repo has one caller (ADR 0064)."""
        rows = [listed(STANDALONE, [READY_FOR_AGENT], START_COLUMN)]
        board = self.fake_cli(
            "gh",
            issue=[dict(one, board=None) for one in rows],
            project={
                "items": [
                    {"status": START_COLUMN, "content": {"number": STANDALONE}},
                    {"status": READY_LANE, "content": {"number": 999}},
                ]
            },
        )

        line = self.report_cli("--repo", "owner/name", fixture=False)

        ran = board.read_text().splitlines()
        self.assertEqual(
            [one for one in ran if one.startswith("project")],
            [
                f"project item-list {BOARD_PROJECT} --owner {BOARD_OWNER} "
                f"--format json --limit {BOARD_LIMIT} --query {BOARD_QUERY}"
            ],
        )
        self.assertIn("2 live card(s)", line)
        self.assertIn("#999", line)
        self.assertIn("not open", line)

    def test_the_report_with_no_board_says_so_and_names_the_labelled_items(self):
        """A tracker that names no board is a supported configuration, so this verb answers
        there too. The label is then the whole gate, and the report says which items hold
        it."""
        self.write_queue(story_queue())

        line = self.report_cli(board=False)

        self.assertIn("names no board", line)
        self.assertIn(f"carry the {READY_FOR_AGENT} label", line)
        self.assertIn(f"#{LEAF_ONE}", line)
        self.assertEqual(self.writes(), [])

    def test_a_report_read_that_failed_names_the_cause(self):
        """A read that failed cannot name a gap, so the report says so rather than printing
        an empty board."""
        self.write_queue(story_queue())
        self.break_fixture()

        line = self.report_cli(expect=EXIT_NOTHING, lines=1)

        self.assertTrue(line.startswith("unreadable:"), line)
        self.assertIn("names no gap", line)

    def test_a_labelled_set_that_fills_its_page_stops_the_tick(self):
        """A read that cannot answer must never answer "no". A labelled set as large as the
        limit can be one page of a longer set, so the tick refuses rather than start the
        oldest item of that page (ADR 0064)."""
        crowded = [
            listed(number, [READY_FOR_AGENT], START_COLUMN)
            for number in range(1, ITEM_LIMIT + 1)
        ]
        self.fake_gh(
            open_items=[dict(one) for one in crowded],
            sets={READY_FOR_AGENT: crowded},
        )

        line = self.queue_cli(
            "--repo", "owner/name", fixture=False, expect=EXIT_REFUSED
        )

        self.assertTrue(line.startswith("unreadable:"), line)
        self.assertIn("Raise ITEM_LIMIT", line)
        self.assertEqual(self.spawned(), [])

    def test_a_failed_spawn_refuses_with_needs_human_and_one_comment(self):
        """A spawn that exited non-zero is a refusal. The item takes `needs-human` plus one
        comment that says what this tick ran, so the maintainer repairs the one thing that
        stopped it. **Exactly one work-state label lands.**"""
        items = story_queue()
        for gone in (STORY, LEAF_ONE, LEAF_TWO):
            items.pop(str(gone))
        self.write_queue(items)

        line = self.queue_cli(expect=EXIT_REFUSED, spawn="exit 9")

        self.assertIn(NEEDS_HUMAN, line)
        self.assertIn("exited 9", line)
        self.assertEqual(self.work_states_after([READY_FOR_AGENT]), [NEEDS_HUMAN])
        self.assertEqual(len(self.swaps()), 1)
        self.assertEqual(len([one for one in self.writes() if "comment" in one]), 1)

        # And the item it wrote is no candidate on the next tick.
        items[str(STANDALONE)]["labels"] = [NEEDS_HUMAN]
        self.write_queue(items)

        self.queue_cli(expect=EXIT_NOTHING)

        self.assertEqual(self.spawned(), [])

    def test_the_skill_comes_from_the_type_label_of_the_item(self):
        """A queue tick has no verb, so it reads the type label the item already carries.
        The one mapping is orchestrator/references/skill-routing.md: a `bug` reaches the
        diagnosis skill, and every other type label reaches the implementation one."""
        items = story_queue()
        for gone in (STORY, LEAF_ONE, LEAF_TWO):
            items.pop(str(gone))
        self.write_queue(items)

        routed = self.queue_cli(spawn="echo {skill} > " + str(self.root / "skill"))
        implement = (self.root / "skill").read_text().strip()

        items[str(STANDALONE)]["labels"] = [READY_FOR_AGENT, "bug"]
        self.write_queue(items)
        self.queue_cli(spawn="echo {skill} > " + str(self.root / "skill"))
        diagnose = (self.root / "skill").read_text().strip()

        self.assertEqual(implement, "/implement")
        self.assertEqual(diagnose, "/diagnosing-bugs")
        self.assertNotIn("/implement", routed.split("the spawn ran:")[0])

    def test_the_role_comes_from_the_declared_touch_set_of_the_item(self):
        """One schedule starts items of different classes, so `{role}` is a token.

        `orchestrator/CONTEXT.md` says a spawn takes `medium`, and takes `heavy` where one
        signal fires. Three or more files is the one countable signal, and the item already
        declares its files. So the tick counts the `## Touches` block and fills the token.
        """
        items = story_queue()
        for gone in (STORY, LEAF_ONE, LEAF_TWO):
            items.pop(str(gone))
        self.write_queue(items)

        self.queue_cli(spawn="echo {role} > " + str(self.root / "role"))
        one_file = (self.root / "role").read_text().strip()

        items[str(STANDALONE)]["body"] = body(
            touches=["docs/one.md", "docs/two.md", "docs/three.md"]
        )
        self.write_queue(items)
        self.queue_cli(spawn="echo {role} > " + str(self.root / "role"))
        three_files = (self.root / "role").read_text().strip()

        self.assertEqual(one_file, "medium")
        self.assertEqual(three_files, "heavy")

    def test_an_item_with_no_touch_block_takes_the_default_role(self):
        """A `light` spawn is never derived: two of its three conditions are prose."""
        items = story_queue()
        for gone in (STORY, LEAF_ONE, LEAF_TWO):
            items.pop(str(gone))
        items[str(STANDALONE)]["body"] = "no block here"
        self.write_queue(items)

        self.queue_cli(spawn="echo {role} > " + str(self.root / "role"))

        self.assertEqual((self.root / "role").read_text().strip(), "medium")

    def test_the_worktree_name_carries_the_item_number_first(self):
        """`{slug}` is the number and then the first words of the title, so a worktree
        name says which item it holds and two items with one title still get two names.
        """
        self.assertEqual(
            worker_queue.slug_of(
                212, "The queue subcommand, and the schedule at setup"
            ),
            "212-the-queue-subcommand-and-the-schedule",
        )
        self.assertEqual(worker_queue.slug_of(212, "!!!"), "212")

    def test_the_title_and_the_body_reach_the_spawn_command_shell_quoted(self):
        """An item body holds quotes, newlines and backticks, and the command runs through
        a shell. So the two arrive quoted and no body can break the command apart."""
        item = {
            "number": 7,
            "title": "it's a $HOME `title`",
            "labels": [],
            "body": "## Touches\n\n- a.py\n",
        }

        filled = worker_queue.fill_spawn("run --title {title} --body {body}", item)

        self.assertEqual(
            shlex.split(filled),
            ["run", "--title", item["title"], "--body", item["body"]],
        )

    def test_two_labelled_reads_answer_every_card_and_no_board_is_listed(self):
        """A tick asks for the two labelled sets, and each item's card arrives in the same
        call. So the read is bounded by the work a maintainer approved rather than by the
        size of the board, and the tick lists no board at all (ADR 0064)."""
        rows = [
            listed(
                number,
                [READY_FOR_AGENT],
                START_COLUMN,
                body=body(touches=[f"scripts/{number}.py"]),
            )
            for number in (STANDALONE, SECOND_LEAF)
        ]
        log = self.fake_gh(
            open_items=[dict(one) for one in rows],
            sets={READY_FOR_AGENT: rows},
        )

        line = self.queue_cli("--repo", "owner/name", fixture=False)

        self.assertIn(f"work item #{STANDALONE} is the one item", line)
        ran = log.read_text().splitlines()
        self.assertEqual([one for one in ran if one.startswith("project")], [])
        self.assertEqual(
            ran,
            [
                f"issue list --state open --limit {ITEM_LIMIT} "
                f"--json {ITEM_FIELDS} --repo owner/name",
                f"issue list --state open --label {USER_STORY} --limit {ITEM_LIMIT} "
                f"--json {CARDED_FIELDS} --repo owner/name",
                f"issue list --state open --label {READY_FOR_AGENT} "
                f"--limit {ITEM_LIMIT} --json {CARDED_FIELDS} --repo owner/name",
            ],
        )

    def test_a_queue_read_that_failed_starts_nothing(self):
        """A read that failed cannot name a startable item, so nothing starts on it. It is
        a refusal rather than a quiet tick, because a broken read for 21 ticks must not
        read as 21 quiet minutes."""
        self.write_queue(story_queue())
        self.break_fixture()

        line = self.queue_cli(expect=EXIT_REFUSED)

        self.assertTrue(line.startswith("unreadable:"), line)
        self.assertIn("starts nothing", line)
        self.assertEqual(self.spawned(), [])

    def test_the_queue_tick_reads_no_worker_and_a_bad_roof_is_a_usage_error(self):
        """It answers which item starts next, which is the question before there is a
        worker to read. So the three flags that name a worker are usage errors here. A roof
        under 1 starts nothing at all, so it is a usage error too, and never a quiet tick
        that nobody sees."""
        self.write_queue(story_queue())

        for flag, value in (
            ("--worktree", str(self.root)),
            ("--process", PROCESS_PATTERN),
            ("--stall-after", "30m"),
        ):
            self.queue_cli(flag, value, expect=EXIT_USAGE, lines=0)

        for roof in ({"stories": 0}, {"workers": 0}, {"stories": -1}):
            self.queue_cli(expect=EXIT_USAGE, lines=0, **roof)

        # No path exits 0, because exit 0 is what loads a schedule's own provider.
        for code in (EXIT_NOTHING, EXIT_REFUSED, EXIT_APPLIED, EXIT_USAGE):
            self.assertNotEqual(code, EXIT_COMPLETE)

    # --- what this seam holds, and what the adapter holds -------------------

    def test_this_seam_writes_no_label_of_its_own(self):
        """A grep for a label write finds no path in this file. The one writer lives with
        the **Tracker adapter**, because the watch swaps the same four labels and neither
        seam imports the other. So a failed spawn and a finish cannot drift apart."""
        tree = ast.parse(SEAM.read_text())
        builders = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "attr", "") == "label_argv"
        ]

        self.assertEqual(builders, [], "this seam builds no label write of its own")

    def test_this_seam_reads_no_worktree_and_no_process(self):
        """The leverage of the split, asserted rather than claimed. This half touches the
        file system exactly once, to fire the spawn, so it starts one subprocess and no
        more. It runs no `git` and it reads no process listing, which is why this suite
        needs no worktree, no git repository and no agent process."""
        tree = ast.parse(SEAM.read_text())
        started = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "attr", "") in ("run", "Popen")
        ]
        self.assertEqual(len(started), 1, "this seam starts one subprocess: the spawn")

        # And no read of a worktree, a commit or a process listing reaches this file.
        source = SEAM.read_text()
        for command in ('"git"', '"ps"', '"lsof"', "os.readlink", "st_mtime"):
            self.assertNotIn(command, source, f"{command} is read in this seam")

    def test_this_seam_names_no_tracker_cli(self):
        """Every tracker command comes from the adapter, so this seam writes no CLI
        name. `--tracker-cli` carries the name in its argv, and its two values are
        the adapter's own constants, so neither one is a literal in this file."""
        literals = [
            node.value
            for node in ast.walk(ast.parse(SEAM.read_text()))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        for cli in ("gh", "glab"):
            self.assertNotIn(cli, literals, f"{cli!r} is a literal in the seam")

        # And the flag still takes both of them, which is the argv this seam keeps.
        help_text = " ".join(self.run_seam("queue", "--help", lines=400).split())
        self.assertIn("--tracker-cli {gh,glab}", help_text)

    def test_this_seam_builds_one_adapter_and_names_its_long_arguments(self):
        """One adapter per run, built in `main` from the four flags that name a tracker.
        Every argument past the eighth is a keyword, so a reordered pair cannot
        type-check, run and print a plausible line."""
        tree = ast.parse(SEAM.read_text())
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
