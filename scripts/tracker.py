#!/usr/bin/env python3
"""Every tracker command the seams above run or print, behind one adapter.

`scripts/worker_state.py` asks what state one worker is in, `scripts/worker_queue.py`
asks which work item starts next, and `scripts/close_item.py` closes one. Each seam held
its own tracker code until this module existed. One had a `gh` builder and a `glab`
builder, and another hardcoded `gh`. So one concept had two interfaces in one repo, and
two fixture formats came with them (ADR 0040).

**Three things live here because more than one seam needs them, and no seam imports
another.** The **Work-state label** family and `write_transition` are the first: the watch
swaps those labels and the queue reads them. The `--repo`, `--tracker-cli`,
`--tracker-host`, `--gh-fixture` and board flags are the second, so two `main` functions
build one adapter from one set of names. `UsageExitParser` is the third. A value either
seam held alone is a value the other cannot reach.

**Every command here is one of the verified reads.** The commands live as prose in
`orchestrator/references/tracker-reads.md`, and this module is where the same
commands live as code (ADR 0039). A read is also checked before it is parsed: `run`
raises on a non-zero exit, so no caller parses an error block.

**A card arrives with its item, and the whole board is one read a human asks for.** The
start gate needs the card of a `user-story` and of a `ready-for-agent` leaf, and of nothing
else. So `labelled_items` reads one of those sets by label and the card comes back in the
same command. `board_cards` is the whole-board list, and the `report` verb is its one caller
(ADR 0064).

**A column is a card on one tracker and a scoped label on the other.** So the other
tracker's column read is a filter over labels the adapter already holds, and it makes no
call of its own: no second command, no page to fill and no page-limit refusal.
`scoped_column` is that filter (ADR 0070).

**The board is also written, at three moments, through one method.** `card_write` moves one
item's card to one column, and a caller names that column rather than an id. The spawn claim
writes `In progress`, the tick that writes `to-review` writes `In review`, and the close
writes `Done` after its teardown (ADR 0067).

**Every list read here refuses rather than truncate.** A page that comes back full can be
one page of a longer list, so no row on it can be counted and no absent row is absent.
`check_page` raises `TrackerError` on that count, and it names the constant to raise. A
truncated read then reads as `unreadable` and never as a missing item.

**One class, and the tracker is four values on it**: the CLI name, the host, the
repository and the fixture. Where two trackers disagree, the branch is inside the
one method that differs. So a new tracker lands here and in no seam.

**One fixture format.** A fixture file stands in for every read, so a test closes an
item and reads its position with no network and no login. It holds one record per work
item and one per pull request:

    {"items": {"54": {"state": "OPEN",
                      "title": "The queue subcommand",
                      "body": "## Parent\n\n#178\n",
                      "parent": 178,
                      "labels": ["in-progress"],
                      "comments": ["Re-prompt: 0 of 10 boxes", "an earlier note"],
                      "board": "To do"}},
     "pull_requests": {"48": {"state": "MERGED",
                              "merge_commit": "a1b2c3d",
                              "head": "someone/54-a-branch"}}}

`board` is that item's own column, which is the `Status` option name on its card on one
tracker and its scoped label on the other. One key covers both, because a fixture holds the
fact and not the wire shape. It is held for a read alone: a card write in fixture mode
records its command and leaves this key as it found it (ADR 0067). `head` is the branch that pull
request was opened from, and it is what a caller matches to find the pull request for
a branch. `title` and `body` are what a queue read asks for, and the body is where the
`## Parent`, `## Blocked by` and `## Touches` edges live. `parent` is the native
parent link, which is the other half of the **Parent edge**, and a fixture holds it as
a plain work item number (ADR 0065). The record above carries both halves, and a
fixture can hold either one alone. Every key is optional. An item that is absent from
a key reads as an item with none of that fact, and a key that is absent reads the same
way. **A record with no `state` reads as open**, because a fixture that lists one item
is a fixture about a live queue.

In fixture mode a write runs nothing. It appends its command to
`<fixture path>.writes`, one per line. That file is what a test reads to see which
tracker writes a run made.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

# The two tracker CLIs a caller can name. Each method below that both of them answer
# holds one branch per CLI. Nothing outside this module tells one tracker from the
# other.
GH = "gh"
GLAB = "glab"

# How many cards one board read asks for, and which cards it asks for. Both are part of
# the recipe in `docs/agents/issue-tracker.md`, so neither one is a bound this module
# chose. The filter is the Projects filter syntax, and it keeps the answer to the cards a
# gate can act on: a board of 188 cards answers 54 rows. `report` is the one caller
# (ADR 0064).
BOARD_LIMIT = 500
BOARD_QUERY = "-status:Done"

# How many work items one list read asks for. Both numbers are part of the recipe
# in `orchestrator/references/tracker-reads.md`, so neither one is a bound this module
# chose. One tracker pages with a limit and the other with a page size. Both the open
# items and one labelled set take them, because both reads list work items.
ITEM_LIMIT = 200
PAGE_SIZE = 100

# The field that carries a work item's project cards, and the single-select field on one
# card that answers the `Status` name. A project board is one tracker's own surface, so
# only that tracker's reads name either of them.
CARD_FIELD = "projectItems"
STATUS_FIELD = "status"

# The same single-select field as `STATUS_FIELD`, spelled the way a field list answers it.
# An item read answers the field in lower case and a field list answers it capitalised, so
# a card write names this constant and a card read names the one above.
STATUS_FIELD_NAME = "Status"

# The three columns a seam writes, one per moment of the work (ADR 0067). The spawn claim
# writes the first, the tick that writes `to-review` writes the second, and the close writes
# the third after its teardown. The start column and the two lanes before it are the
# maintainer's own, and nothing here writes one.
COLUMN_IN_PROGRESS = "In progress"
COLUMN_IN_REVIEW = "In review"
COLUMN_DONE = "Done"

# The **Work-state label** family: one family, four values, and it never stacks. The
# strings and the swap rule are owned by `docs/agents/issue-tracker.md`, which is this
# adapter's own reference. The whole family is named here because a swap removes every
# value it finds on the item, rather than one hardcoded predecessor.
#
# **The family lives with the adapter because the watch and the queue read the same
# four strings.** The watch swaps them on a transition, and the queue reads them to tell an
# owned item from a free one. Neither of those two files imports the other, so a value
# either one held alone is a value the other cannot reach (ADR 0040).
READY_FOR_AGENT = "ready-for-agent"
IN_PROGRESS = "in-progress"

# The value that means a human is reading the pull request, and the one label a
# **Position** reads.
TO_REVIEW = "to-review"

# The value that stops every tick. Only the maintainer removes it, so a paused item costs
# one cheap read a minute and moves nowhere.
NEEDS_HUMAN = "needs-human"

WORK_STATES = (READY_FOR_AGENT, IN_PROGRESS, TO_REVIEW, NEEDS_HUMAN)

# A usage error must not land on one of a seam's outcome codes. `argparse` exits 2 by
# default, which is non-zero, so a flag with a typo reads as a quiet tick and records as a
# skipped run that nobody sees. 64 is `EX_USAGE`, and it sits outside every contract above
# a seam (ADR 0022).
EXIT_USAGE = 64

# How a board column arrives on the tracker that has no card at all. A column there is a
# **scoped label** on the item, and the scope is everything up to and including the `::`.
# `COLUMN_SCOPE` is that prefix, and `SCOPED_COLUMNS` is the four column names in lower
# case. Both are part of the recipe in `docs/agents/issue-tracker.md`, so this module chose
# neither. The four names are read for one purpose only, which is the refusal in
# `scoped_column`: a board built on plain labels rather than scoped ones (ADR 0070).
COLUMN_SCOPE = "status::"
SCOPED_COLUMNS = ("to do", "in progress", "in review", "done")

# The field that carries a work item's native parent link, which is one half of the
# **Parent edge**. The `## Parent` line in the body is the other half, and the descent
# unions the two (ADR 0065). One tracker answers this field, and the other has no parent
# link between two issues at all.
PARENT_FIELD = "parent"

# The `## Parent` block, in the two forms this module needs. `PARENT_BLOCK` is the heading
# a write adds, and `PARENT_MATCH` is deliberately the same pattern the reader in
# `scripts/worker_state.py` holds. So a block this module writes is a block that seam finds
# (ADR 0065).
PARENT_BLOCK = "## Parent"
PARENT_MATCH = re.compile(r"^##\s*Parent\s*$", re.MULTILINE)

# The five fields a queue read asks of each work item, plus the card field the start gate
# reads with them. The board is never listed for this, so the card rides the item
# (ADR 0064). The parent rides it too, so the union read costs no second command.
ITEM_FIELDS = f"number,title,labels,body,{PARENT_FIELD}"
CARDED_FIELDS = f"{ITEM_FIELDS},{CARD_FIELD}"

# The two spellings of an open work item. One tracker answers `OPEN` and the other
# answers `opened`, so no caller compares either string itself.
OPEN_STATES = ("OPEN", "OPENED")


class TrackerError(RuntimeError):
    """A tracker command failed.

    Each seam reports it and neither one raises it past its own CLI: the watch
    answers `unreadable`, and the close puts the cause in the plan.
    """


def run(argv):
    """The standard output of one tracker command, or `TrackerError`.

    This is the one place that reports a failed command, so no builder repeats it.
    The command is in the message, because that line is what a maintainer reads to
    repair a broken read.
    """
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        raise TrackerError(f"{' '.join(argv)} failed: {proc.stderr.strip()}")
    return proc.stdout


def read_json(argv, empty="{}"):
    """The parsed answer of one tracker read, checked before it is parsed.

    `empty` is what an answer of no output reads as, because one read asks for an
    object and another asks for a list.
    """
    return json.loads(run(argv) or empty)


def check_page(rows, limit, constant):
    """`rows`, or `TrackerError` where the read filled its own page.

    **Every list read here goes through this, and a full page is never an answer.** A read
    that asks for `limit` rows and gets `limit` rows can be one page of a longer list. So no
    row on it can be counted, and a row that is absent from it is not absent from the
    tracker. A gate that reads such a page answers "no" to a question it never saw
    (ADR 0064).

    The message names the count, the limit and the constant a maintainer raises. That line
    is what turns a stopped queue into a one-line repair.
    """
    if len(rows) >= limit:
        raise TrackerError(
            f"a list read answered {len(rows)} row(s) against its limit of {limit}, so the "
            f"answer can be one page of a longer list and no row can be counted. Raise "
            f"{constant} in scripts/tracker.py"
        )
    return rows


def card_status(entry):
    """The `Status` name on the first card one work item read answers, or an empty string.

    **The read names each board by title and never by number**, so the two board
    coordinates cannot pick one card out of two. One board per repo is the shape
    `docs/agents/issue-tracker.md` describes, so the first card that carries a status is the
    only one a supported configuration holds (ADR 0064).

    An empty string covers an item with no card, a card with no status, and a tracker with
    no board at all. A caller compares the name it wants, so none of the three is an error.
    """
    for card in entry.get(CARD_FIELD) or []:
        name = (card.get(STATUS_FIELD) or {}).get("name") or ""
        if name:
            return name
    return ""


def scoped_column(labels):
    """The board column one item's labels carry, or an empty string.

    **This is the whole board read on the tracker that has no card** (ADR 0070). A column
    there is a scoped label, `status::to do` and its siblings, and every label already
    arrives with the item read the adapter makes for its **Work-state label**. So this reads
    a fact the caller is holding: it runs no command, it has no page to fill, and it has no
    page-limit refusal.

    The answer is the label with `COLUMN_SCOPE` stripped, so a caller compares a column name
    whichever tracker it read. A label outside that scope is not a column, and an item with
    no label in the scope answers empty. Neither one is an error, the same as an item with no
    card. The tracker keeps one label per scope, so the first match is the only one a
    supported board holds.

    **One case refuses rather than guesses: a board built on plain column labels.** A plain
    label carries no scope, so the tracker swaps nothing and two column labels can sit on one
    item at once. No one of them is then the column. The message names the prefix it expected,
    and the caller reports the board as unreadable.
    """
    for name in labels or []:
        if name.startswith(COLUMN_SCOPE):
            column = name[len(COLUMN_SCOPE) :].strip()
            if column:
                return column
    for name in labels or []:
        if name.strip().lower() in SCOPED_COLUMNS:
            raise TrackerError(
                f"the label {name!r} is a column name outside {COLUMN_SCOPE!r}, so this "
                f"board is not scoped: it is built on plain column labels. A plain label "
                f"carries no scope, so two column labels can sit on one item at once and "
                f"neither one is the column. Name the columns {COLUMN_SCOPE}<column>, or "
                f"name no board in docs/agents/issue-tracker.md"
            )
    return ""


def label_names(labels):
    """The label names in one tracker answer.

    A label is a plain string on one tracker and an object with a `name` on the other.
    So one reader serves both answers, and no caller learns which shape it holds.
    """
    return [
        entry if isinstance(entry, str) else entry.get("name") or ""
        for entry in labels or []
    ]


def parent_number(entry):
    """The work item number of one native parent link, or 0 where the entry holds none.

    The link arrives as an object with a number on it, and an item with no parent answers
    a null. So one reader covers both, and a tracker that has no parent link at all
    answers 0 the same way (ADR 0065).
    """
    return int((entry.get(PARENT_FIELD) or {}).get("number") or 0)


def parent_body(body, parent):
    """One child body carrying its `## Parent` block, added where the body holds none.

    **This is what lets one command write both halves of the Parent edge** (ADR 0065). The
    external `to-tickets` template already writes the block, so the common case answers the
    body unchanged and nothing is duplicated. A body filed without the block gains it here,
    so the write cannot land the native link alone.
    """
    if PARENT_MATCH.search(body or ""):
        return body or ""
    return f"{PARENT_BLOCK}\n\n#{int(parent or 0)}\n\n{body or ''}".rstrip() + "\n"


def item_record(number, title, labels, body, parent=0):
    """One work item in the shape a queue read answers, whatever tracker it came from.

    Five facts, and a queue tick reads no sixth: the number, the title a worktree name
    is built from, the labels the start gate reads, the body that carries the
    `## Parent`, `## Blocked by` and `## Touches` edges, and the native parent link.

    **Both halves of the Parent edge ride one record.** The body carries the
    `## Parent` line and `parent` carries the native link, so the descent unions the two
    with no second read (ADR 0065). A tracker with no parent link between two issues
    answers 0 there.
    """
    return {
        "number": int(number or 0),
        "title": str(title or ""),
        "labels": label_names(labels),
        "body": str(body or ""),
        PARENT_FIELD: int(parent or 0),
    }


class Tracker:
    """The tracker one seam talks to: a CLI, a host, a repository and a fixture.

    A caller passes the four values once and then asks for a fact or an argv. It
    names no CLI and no flag of its own.
    """

    def __init__(self, cli=GH, host="", repo="", fixture=None):
        self.cli = cli
        self.host = host
        self.repo = repo
        self.path = Path(fixture) if fixture else None
        # The parse lives in `fixture`, and not in a line here. A caller builds one
        # adapter before it makes a read. A constructor that reads a file turns a failed
        # read into a traceback out of that construction.
        self._fixture: Any = None
        # The cards of one board, held after the first read of them. `board_cards`
        # explains why they are held.
        self._cards: Any = None

    @property
    def fixture(self):
        """The parsed fixture file, read on the first fact a caller asks for.

        A file that is absent or malformed raises where every other failed read raises.
        So the caller reports it the way it reports one of those. In the watch that is
        the `unreadable` outcome, and in the close it is the cause in the plan.
        """
        if self.path is not None and self._fixture is None:
            self._fixture = json.loads(self.path.read_text())
        return self._fixture

    def _item(self, number):
        """One work item's fixture record, or an empty one where it is absent."""
        return (self.fixture.get("items") or {}).get(str(number)) or {}

    def _repo_flag(self):
        """The repository argument, in the form and the place each CLI wants it.

        One CLI takes `--repo OWNER/NAME`. The other takes `-R`, and its host is part
        of that argument rather than a flag of its own. With no repository neither one
        names it, so every command goes to the clone the working directory holds.
        """
        if not self.repo:
            return []
        if self.cli == GLAB:
            return ["-R", f"{self.host}/{self.repo}" if self.host else self.repo]
        return ["--repo", self.repo]

    # --- the facts a seam reads

    def item_facts(self, item):
        """The two facts a phase tick needs: `(labels, comment bodies)`.

        One call, because a tick needs both. A read that fails raises
        `TrackerError` for the `unreadable` outcome to report.
        """
        if self.fixture is not None:
            record = self._item(item)
            return (
                list(record.get("labels") or []),
                list(record.get("comments") or []),
            )
        if self.cli == GLAB:
            return self._glab_facts(item)
        return self._gh_facts(item)

    def _gh_facts(self, item):
        """The two facts from `gh`, which reads both of them in one command."""
        data = read_json(
            [
                GH,
                "issue",
                "view",
                str(item),
                "--json",
                "comments,labels",
                *self._repo_flag(),
            ]
        )
        return (
            label_names(data.get("labels")),
            [entry.get("body") or "" for entry in data.get("comments") or []],
        )

    def _glab_facts(self, item):
        """The two facts from `glab`, which reads them in two commands.

        The host goes in a different place in each command. That difference is why
        this builder exists, and not one command with a flag:

        - the labels come from
          `glab issue view <n> -F json -R <host>/<owner>/<name>`, where the host is
          part of the repository argument.
        - the comments come from
          `glab api projects/<owner>%2F<name>/issues/<n>/notes --hostname <host>`,
          where the host is a flag and the project path carries no host at all. A
          bare `owner/name` in that path resolves against the CLI's default server,
          which answers 404 or `Unauthenticated` for a project it does not hold.

        With no host neither command names one, so both reads go to the CLI's own
        default server.
        """
        if not self.repo:
            raise TrackerError(
                "a glab read needs --repo as OWNER/NAME, because the project path is "
                "part of both commands"
            )
        labels_argv = [GLAB, "issue", "view", str(item), "-F", "json"]
        labels_argv += self._repo_flag()
        notes_argv = [
            GLAB,
            "api",
            f"projects/{self.repo.replace('/', '%2F')}/issues/{item}/notes",
        ]
        if self.host:
            notes_argv += ["--hostname", self.host]
        issue = read_json(labels_argv)
        notes = read_json(notes_argv, "[]")
        return (
            label_names(issue.get("labels")),
            [entry.get("body") or "" for entry in notes or []],
        )

    def issue(self, number):
        """One work item's state and its label names.

        The state reads as the caller's own case, because one tracker answers `OPEN`
        and `CLOSED` and the other answers `opened` and `closed`.
        """
        if self.fixture is not None:
            record = self._item(number)
            return {
                "state": record.get("state"),
                "labels": list(record.get("labels") or []),
            }
        if self.cli == GLAB:
            argv = [GLAB, "issue", "view", str(number), "-F", "json"]
        else:
            argv = [GH, "issue", "view", str(number), "--json", "state,labels"]
        data = read_json([*argv, *self._repo_flag()])
        return {"state": data.get("state"), "labels": label_names(data.get("labels"))}

    def open_items(self):
        """Every open work item, lowest number first, in the `item_record` shape.

        **The widest list read, and a queue tick makes it once a minute.** The body comes
        with it, because the `## Parent`, `## Blocked by` and `## Touches` edges live
        there and a second read per item costs one command per item. The native parent
        link comes with it for the same reason, so the union of the two parent edges
        needs no command of its own (ADR 0065). It asks for no card:
        the tick needs the card of the items that can start, and `labelled_items` answers
        those with the item (ADR 0064).

        The order is by number, so a caller that starts one item per tick starts the
        oldest candidate first. That is what makes an overlap a delay rather than a
        cancellation (ADR 0046).

        **A fixture record with no `state` reads as open.** A fixture that lists a work
        item is a fixture about a live queue, so the common case needs no key.
        """
        if self.fixture is not None:
            found = [
                item_record(
                    number,
                    record.get("title"),
                    record.get("labels"),
                    record.get("body"),
                    record.get(PARENT_FIELD),
                )
                for number, record in (self.fixture.get("items") or {}).items()
                if str(record.get("state") or OPEN_STATES[0]).upper() in OPEN_STATES
            ]
        elif self.cli == GLAB:
            found = self._glab_open_items()
        else:
            found = self._gh_open_items()
        return sorted(found, key=lambda item: item["number"])

    def _gh_open_items(self):
        """The open items from `gh`, which answers all five fields in one command."""
        return [
            item_record(
                entry.get("number"),
                entry.get("title"),
                entry.get("labels"),
                entry.get("body"),
                parent_number(entry),
            )
            for entry in check_page(
                read_json(self._gh_list_argv(ITEM_FIELDS), "[]") or [],
                ITEM_LIMIT,
                "ITEM_LIMIT",
            )
        ]

    def _gh_list_argv(self, fields, label=""):
        """The argv of one `gh` list read: the open work items, or one labelled set.

        Both reads are the same command with the same limit, and the labelled one adds one
        flag. So the two can never drift apart on the state they ask for or the page they
        take.
        """
        return [
            GH,
            "issue",
            "list",
            "--state",
            "open",
            *(["--label", label] if label else []),
            "--limit",
            str(ITEM_LIMIT),
            "--json",
            fields,
            *self._repo_flag(),
        ]

    def _glab_open_items(self):
        """The open items from `glab`, through its API rather than its issue list.

        `glab issue list` is the flag trap `orchestrator/references/tracker-reads.md`
        records: its JSON flag has another spelling, and it takes no `--state` at all.
        So this read goes through `glab api`, and the project path is part of the URL.
        That path is why the repository is required here, the same as it is for the two
        other `glab api` reads above. The body arrives under its own name there.

        **This tracker has no parent link between two issues**, so the record's native
        parent is 0 and the `## Parent` line is the whole edge (ADR 0065).
        """
        return [
            item_record(
                entry.get("iid"),
                entry.get("title"),
                entry.get("labels"),
                entry.get("description"),
            )
            for entry in check_page(
                read_json(self._glab_list_argv(), "[]") or [], PAGE_SIZE, "PAGE_SIZE"
            )
        ]

    def _glab_list_argv(self, label=""):
        """The argv of one `glab` list read: the open work items, or one labelled set."""
        if not self.repo:
            raise TrackerError(
                "a glab read of the open work items needs --repo as OWNER/NAME, "
                "because the project path is part of the command"
            )
        query = f"state=opened&per_page={PAGE_SIZE}"
        if label:
            query += f"&labels={quote(label, safe='')}"
        argv = [GLAB, "api", f"projects/{self.repo.replace('/', '%2F')}/issues?{query}"]
        if self.host:
            argv += ["--hostname", self.host]
        return argv

    def labelled_items(self, label):
        """Every open work item wearing one label, with its card, in the record shape.

        **One command answers the set and each item's card status** (ADR 0064). The start
        gate needs the card of a `user-story` and of a `ready-for-agent` leaf, and of no
        other item. So the read is bounded by the work a maintainer approved rather than by
        the size of a board, and the tick lists no board at all.

        The record is the `item_record` shape plus a `board` key, which is that item's own
        column. On one tracker it is the `Status` name on the item's card, and on the other it
        is the scoped label the labels already carry (ADR 0070). An item with no column
        answers an empty string either way.

        The order is by number, the same as `open_items`, so a caller that reads both sees
        one order.
        """
        if self.fixture is not None:
            found = [
                {
                    **item_record(
                        number,
                        record.get("title"),
                        record.get("labels"),
                        record.get("body"),
                        record.get(PARENT_FIELD),
                    ),
                    "board": str(record.get("board") or ""),
                }
                for number, record in (self.fixture.get("items") or {}).items()
                if str(record.get("state") or OPEN_STATES[0]).upper() in OPEN_STATES
                and label in label_names(record.get("labels"))
            ]
        elif self.cli == GLAB:
            # No card on this tracker, so the column is a scoped label and the read asks
            # for no field of one. It arrives with the labels this read already carries, so
            # the column costs no second command (ADR 0070). No parent link either, so the
            # native half of the **Parent edge** is 0 (ADR 0065).
            found = [
                {
                    **item_record(
                        entry.get("iid"),
                        entry.get("title"),
                        entry.get("labels"),
                        entry.get("description"),
                    ),
                    "board": scoped_column(label_names(entry.get("labels"))),
                }
                for entry in check_page(
                    read_json(self._glab_list_argv(label), "[]") or [],
                    PAGE_SIZE,
                    "PAGE_SIZE",
                )
            ]
        else:
            found = [
                {
                    **item_record(
                        entry.get("number"),
                        entry.get("title"),
                        entry.get("labels"),
                        entry.get("body"),
                        parent_number(entry),
                    ),
                    "board": card_status(entry),
                }
                for entry in check_page(
                    read_json(self._gh_list_argv(CARDED_FIELDS, label), "[]") or [],
                    ITEM_LIMIT,
                    "ITEM_LIMIT",
                )
            ]
        return sorted(found, key=lambda item: item["number"])

    def item_card(self, item):
        """The `Status` name on one work item's own card, or an empty string.

        **One item, one call, and no list.** `start --item N` asks about the item a human
        named, and that item can wear no label at all. So its card cannot arrive through a
        labelled set, and a whole-board list to answer one card is the read ADR 0064
        removed.

        **On the other tracker the column is a scoped label, so the same one item read
        answers it** (ADR 0070). `issue` is that read, and it already asks for every label.
        """
        if self.fixture is not None:
            return str(self._item(item).get("board") or "")
        if self.cli == GLAB:
            return scoped_column(self.issue(item)["labels"])
        return card_status(
            read_json(
                [
                    GH,
                    "issue",
                    "view",
                    str(item),
                    "--json",
                    CARD_FIELD,
                    *self._repo_flag(),
                ]
            )
        )

    def pull_request(self, number):
        """The pull request's state, and the commit its merge landed as.

        Both answers say the same two things under different names. One tracker
        answers `MERGED` and a `mergeCommit` object, and the other answers `merged`
        and a `merge_commit_sha` string. The caller compares the state in its own
        case, so only the commit needs a branch here.
        """
        if self.fixture is not None:
            record = (self.fixture.get("pull_requests") or {}).get(str(number)) or {}
            return {
                "state": record.get("state"),
                "merge_commit": str(record.get("merge_commit") or ""),
            }
        data = read_json(self.pr_read_argv(number))
        if self.cli == GLAB:
            return {
                "state": data.get("state"),
                "merge_commit": str(data.get("merge_commit_sha") or ""),
            }
        return {
            "state": data.get("state"),
            "merge_commit": (data.get("mergeCommit") or {}).get("oid") or "",
        }

    def pull_request_for_branch(self, branch):
        """The pull request whose head is `branch`: `{"number", "state"}`.

        A caller that holds a branch and no number asks this. A **Worker watch** tick is
        that caller. It knows the worktree it watches, so it can read the branch, and
        nothing hands it a pull request number.

        **A branch with no pull request is no error.** The answer is a number of 0 and an
        empty state. So the caller reads one shape whichever fact holds, and a quiet tick
        is one comparison away from a merged one.

        **A merged pull request wins where a branch has more than one.** A branch that
        was closed and opened again carries two records. The merge is the fact the caller
        asked about.
        """
        found: list[tuple[int, str]]
        if self.fixture is not None:
            found = [
                (int(number), str(record.get("state") or ""))
                for number, record in (self.fixture.get("pull_requests") or {}).items()
                if str(record.get("head") or "") == branch
            ]
        else:
            # One tracker names the number `number`, and the other names it `iid`,
            # because it numbers a merge request in a sequence of its own.
            key = "iid" if self.cli == GLAB else "number"
            found = [
                (int(entry.get(key) or 0), str(entry.get("state") or ""))
                for entry in read_json(self.pr_for_branch_argv(branch), "[]") or []
            ]
        merged = [one for one in found if one[1].upper() == "MERGED"]
        number, state = (merged or found or [(0, "")])[0]
        return {"number": number, "state": state}

    def board_cards(self, project, owner):
        """Every card on one board as `{work item number: Status name}`, read once.

        **This is the whole-board read, and the `report` verb is its one caller**
        (ADR 0064). `card_write` makes an unfiltered read of its own. No gate reads it:
        a gate needs the card of an item that can start, and `labelled_items` answers that
        with the item.

        The answer is held after the first read, so a report that asks twice queries once.
        A caller that asks about a second board reads again, because the held answer names
        the board it came from.

        **The read is filtered.** It asks for the cards that are not `Done`, so the answer
        holds every card a gate can act on and none of the archive. A board of 188 cards
        answers 54 rows through that filter.

        **A read that fills the limit refuses rather than answers**, through `check_page`.
        The answer can then be one page of a longer board, and a card past that page is
        invisible. So the caller reads `unreadable` and never a missing card.

        **A host that does not support the filter fails the read, which is also loud.**
        The filter needs github.com or GitHub Enterprise Server 3.20 and later. An older
        host answers a non-zero exit, so `read_json` raises and the caller reads
        `unreadable`. No older host answers "no card".

        A card with no work item behind it, which is a draft card, carries no number and it
        is left out.
        """
        if self.fixture is not None:
            return {
                int(number): str(record.get("board") or "")
                for number, record in (self.fixture.get("items") or {}).items()
                if record.get("board")
            }
        key = (project, owner)
        if self._cards is None or self._cards[0] != key:
            data = read_json(self._board_list_argv(project, owner))
            cards = check_page(
                list(data.get("items") or []), BOARD_LIMIT, "BOARD_LIMIT"
            )
            self._cards = (
                key,
                {
                    int((entry.get("content") or {}).get("number") or 0): str(
                        entry.get("status") or ""
                    )
                    for entry in cards
                    if (entry.get("content") or {}).get("number")
                },
            )
        return self._cards[1]

    def card_write(self, item, column, project, owner):
        """Move one work item's card to `column`, and answer the clause a caller prints.

        **The board is a mirror, and a seam writes the card at the moment the work moves**
        (ADR 0067). This is that write, and it sits beside the card read above because the
        two are one concept. Three callers reach it: the spawn claim, the tick that writes
        `to-review`, and the close after its teardown.

        **A caller holds the column name, and this resolves every id the write needs.** So
        no configuration file holds a `Status` field id or an option id, and a renamed column
        is one edit. The resolution costs three reads: the project's own id, the field list
        that carries the option ids, and the card list that carries this item's card id.

        **It is safe to call twice with the same column.** The card list already answers the
        `Status` name, so a card that sits in the target column costs the reads and no write.
        That is what makes the `Done` write safe beside the board's own
        **item closed to Done** workflow, which writes the same column for most items.

        **Three cases answer without raising**, because each one is a supported
        configuration: a tracker with no project board, an item with no card, and a column
        name the board does not hold. A command that fails raises `TrackerError`, the way
        every other write here does, and the caller reports it.

        **In fixture mode the write is recorded and no id is resolved.** A fixture holds no
        project id and no option id, so the recorded line names the item and the column
        rather than the four ids the live command carries. That line is what a test reads.
        """
        if self.cli != GH or not (column and project and owner):
            return ""
        if self.path is not None:
            self.write(
                [
                    GH,
                    "project",
                    "item-edit",
                    "--item",
                    str(item),
                    "--project",
                    str(project),
                    "--owner",
                    owner,
                    "--status",
                    column,
                ]
            )
            return f"the card of work item #{item} moved to {column!r}"
        card_id, status = self._card_ids(project, owner).get(int(item), ("", ""))
        if not card_id:
            return (
                f"work item #{item} has no card on project {project}, so nothing moved"
            )
        if status == column:
            return f"the card of work item #{item} already sits in {column!r}"
        field_id, option_id = self._status_option(project, owner, column)
        if not option_id:
            return (
                f"the board has no {column!r} column, so the card of work item #{item} "
                f"did not move"
            )
        self.write(
            [
                GH,
                "project",
                "item-edit",
                "--id",
                card_id,
                "--project-id",
                self._project_id(project, owner),
                "--field-id",
                field_id,
                "--single-select-option-id",
                option_id,
            ]
        )
        was = status or "no column"
        return f"the card of work item #{item} moved from {was!r} to {column!r}"

    def _card_ids(self, project, owner):
        """Every card on one board as `{work item number: (card id, Status name)}`.

        **This read carries no filter, and `board_cards` does.** A write needs the id of the
        card it moves, and the filtered read leaves out every card in `Done`. A repeat write
        of `Done` would then read as an item with no card, so the repeat would be silent
        rather than safe (ADR 0067).

        A read that fills its own page refuses, through `check_page`, for the reason every
        other list read here refuses: a card past the page is invisible, and a caller must
        never read that as a missing card.

        A card with no work item behind it is a draft card. It carries no number, and it is
        left out.
        """
        data = read_json(
            [
                GH,
                "project",
                "item-list",
                str(project),
                "--owner",
                owner,
                "--format",
                "json",
                "--limit",
                str(BOARD_LIMIT),
            ]
        )
        rows = check_page(list(data.get("items") or []), BOARD_LIMIT, "BOARD_LIMIT")
        return {
            int((entry.get("content") or {}).get("number") or 0): (
                str(entry.get("id") or ""),
                str(entry.get("status") or ""),
            )
            for entry in rows
            if (entry.get("content") or {}).get("number")
        }

    def _status_option(self, project, owner, column):
        """`(field id, option id)` for one column name, or a pair of empty strings.

        **A write needs the option id, and a caller holds the name** (ADR 0067). So the
        resolution lives here and no caller learns an id. A board with no `Status` field,
        and a name that field does not offer, both answer the empty pair.
        """
        data = read_json(
            [
                GH,
                "project",
                "field-list",
                str(project),
                "--owner",
                owner,
                "--format",
                "json",
            ]
        )
        for field in data.get("fields") or []:
            if (field.get("name") or "") != STATUS_FIELD_NAME:
                continue
            for option in field.get("options") or []:
                if (option.get("name") or "") == column:
                    return str(field.get("id") or ""), str(option.get("id") or "")
        return "", ""

    def _project_id(self, project, owner):
        """The board's own id, which the card write names beside the field id.

        The project number and the owner address a board for a human. The write takes the
        board's id instead, and this is the one read that answers it.
        """
        return str(
            read_json(
                [
                    GH,
                    "project",
                    "view",
                    str(project),
                    "--owner",
                    owner,
                    "--format",
                    "json",
                ]
            ).get("id")
            or ""
        )

    # --- the argv a seam runs or prints

    def pr_read_argv(self, number):
        """The argv of the merged-state read, which a plan also prints.

        The two trackers disagree three ways about this one read, and no way is a
        rename. The object has its own subcommand, the JSON flag has its own spelling,
        and the number belongs to its own sequence. One tracker numbers a merge request
        apart from an issue, so `number` there is the merge request's own number and
        never the item's.
        """
        if self.cli == GLAB:
            return [GLAB, "mr", "view", str(number), "-F", "json", *self._repo_flag()]
        return [
            GH,
            "pr",
            "view",
            str(number),
            "--json",
            "state,mergeCommit",
            *self._repo_flag(),
        ]

    def pr_for_branch_argv(self, branch):
        """The argv that lists the pull requests opened from one branch.

        Every state, because the caller asks whether one of them is merged. One tracker
        filters on the head branch with a flag of its own. The other takes the branch as
        a query parameter on its API. So the read never touches `glab mr list`, and it
        never meets the flag trap `references/tracker-reads.md` records.

        **The branch is escaped in that query.** A `+` in a branch name reads as a space on
        the server, and an `&` splits the query. Either one answers an empty list, which a
        caller reads as a branch with no pull request.
        """
        if self.cli == GLAB:
            if not self.repo:
                raise TrackerError(
                    "a glab read of the merge requests for a branch needs --repo as "
                    "OWNER/NAME, because the project path is part of the command"
                )
            argv = [
                GLAB,
                "api",
                f"projects/{self.repo.replace('/', '%2F')}/merge_requests"
                f"?source_branch={quote(branch, safe='')}&state=all",
            ]
            if self.host:
                argv += ["--hostname", self.host]
            return argv
        return [
            GH,
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "all",
            "--json",
            "number,state",
            *self._repo_flag(),
        ]

    def label_argv(self, item, remove=(), add=()):
        """The argv that swaps the labels on one work item.

        The caller passes the names it wants and no flag. The subcommand that takes a
        label, and the flag that carries one, are two of the things the two trackers
        disagree about. One name per flag, so no CLI splits a name on a comma.
        """
        flags = []
        if self.cli == GLAB:
            for name in add:
                flags += ["--label", name]
            for name in remove:
                flags += ["--unlabel", name]
            return [GLAB, "issue", "update", str(item), *flags, *self._repo_flag()]
        for name in remove:
            flags += ["--remove-label", name]
        for name in add:
            flags += ["--add-label", name]
        return [GH, "issue", "edit", str(item), *flags, *self._repo_flag()]

    def parent_link_argv(self, item, parent, body):
        """The argv that writes both halves of the **Parent edge** on one child work item.

        **One command, so it cannot write only one edge** (ADR 0065). It sets the native
        parent link, and it sends the body that carries the `## Parent` line. `parent_body`
        adds that block where the body holds none, so neither half can be left behind.

        **The body is a required argument, because the command replaces the body.** A caller
        writes the link right after it filed the child, so it already holds the body and
        reads nothing first. A caller with no body erases one, which is why this argument
        takes no default.

        **This runs once per child, at the create.** A second run fails, because the tracker
        refuses a duplicate sub-issue, and the body write fails with it. A caller reports that
        failure and carries on, because the `## Parent` line already carries the meaning.

        The other tracker has no parent link between two issues. So there this writes the
        description alone, the `## Parent` line is the whole edge, and this claims no parity.
        """
        text = parent_body(body, parent)
        if self.cli == GLAB:
            return [
                GLAB,
                "issue",
                "update",
                str(item),
                "--description",
                text,
                *self._repo_flag(),
            ]
        return [
            GH,
            "issue",
            "edit",
            str(item),
            "--parent",
            str(parent),
            "--body",
            text,
            *self._repo_flag(),
        ]

    def close_argv(self, item, comment=""):
        """The argv that closes one work item, with the reason where the CLI takes one.

        One CLI closes an item and records the reason in the same command. The other
        has no such flag, so there the reason is its own write and
        `closing_note_argv` builds it.
        """
        if self.cli == GLAB:
            return [GLAB, "issue", "close", str(item), *self._repo_flag()]
        argv = [GH, "issue", "close", str(item)]
        if comment:
            argv += ["--comment", comment]
        return [*argv, *self._repo_flag()]

    def closing_note_argv(self, item, body):
        """The argv that posts a closing reason as its own write, or an empty list.

        Where the close command carries the reason itself, there is no second write, so
        this answers nothing. `close_writes` is what a seam asks, and it is the one
        caller that reads this answer.
        """
        if not body or self.cli != GLAB:
            return []
        return self.comment_argv(item, body)

    def close_writes(self, item, comment=""):
        """The writes that close one work item, in the one order they hold.

        One CLI closes an item and records the reason in the same command, so there is
        one write. The other has no reason flag, so the reason is a write of its own. It
        goes first, because an item that closes first closes with no reason on it.

        **The order is here, and not in a caller.** A caller that assembles two writes
        can assemble them the wrong way round. A count of writes is one more difference
        between two trackers (ADR 0056). So this answers the name and the argv of each
        write, in order, and a caller iterates them.
        """
        note = self.closing_note_argv(item, comment)
        close = ("close", self.close_argv(item, comment))
        return [("note", note), close] if note else [close]

    # The card write is `card_write`, and it sits beside the card read rather than here,
    # because a read and a write of one surface are one concept (ADR 0067).

    def comment_argv(self, item, body):
        """The argv that posts one comment on a work item.

        One branch per tracker, for the same reason each read here has one: the
        subcommand differs, and so does the flag that carries the message. The
        repository argument differs as well, and `_repo_flag` holds that difference.
        """
        if self.cli == GLAB:
            return [
                GLAB,
                "issue",
                "note",
                str(item),
                "--message",
                body,
                *self._repo_flag(),
            ]
        return [
            GH,
            "issue",
            "comment",
            str(item),
            "--body",
            body,
            *self._repo_flag(),
        ]

    def _board_list_argv(self, project, owner):
        """The argv of the one board read, which is the recipe the tracker file holds.

        **The filter rides in the argv, and it names no column.** `-status:Done` is every
        card that is not finished, so this read never needs the start column and the
        caller still compares the `Status` name it wants. A card in any other column
        answers its own name, the same as before the filter.

        **`report` is the one caller** (ADR 0064). No gate reaches this read.

        A project board is one tracker's own surface, so this builder names that CLI
        and the CLI name on this object does not reach it. A repo on the other
        tracker has no such board, so it passes no board argument and this read
        never runs there.

        **One caller, and it walks the answer in Python.** A `--jq` filter here was a
        second parser of the same recipe (ADR 0054). `_card_ids` builds the unfiltered form
        of this argv, because a card write must see a card in `Done` too (ADR 0067).
        """
        return [
            GH,
            "project",
            "item-list",
            str(project),
            "--owner",
            owner,
            "--format",
            "json",
            "--limit",
            str(BOARD_LIMIT),
            "--query",
            BOARD_QUERY,
        ]

    # --- the writes a seam makes

    def write(self, argv):
        """Run one tracker write, or record it where a fixture stands in."""
        # The path and the parsed fixture arrive together, so one guard covers both.
        # The next line reads the path, so the path is what this guard names.
        if self.path is not None:
            log = self.path.parent / (self.path.name + ".writes")
            with log.open("a") as handle:
                handle.write(" ".join(argv) + "\n")
            return
        proc = subprocess.run(argv, capture_output=True, text=True)
        if proc.returncode != 0:
            raise TrackerError(f"{' '.join(argv)} failed: {proc.stderr.strip()}")


# --- the work-state label swap ----------------------------------------------


def write_transition(tracker, item, labels, add, comment=""):
    """Swap the **Work-state label**s on one work item, and answer what it wrote.

    **This is the one function in this repo that writes a work-state label.** It runs in
    the process that already read `labels`, so no second read can disagree with the first.
    A second copy of it would add exactly that second read.

    **The removals and the addition are one tracker write.** Both go into one `label_argv`
    call, so they can never land apart and an item is never left wearing two work states.
    **The removals are computed from `labels`**, which is what this run read, and never
    from a hardcoded predecessor. So the one-label answer holds from every legal starting
    position, including an item that already wears the label the transition adds.

    `comment` is the one comment a transition carries where it has something to say. It is
    its own write, because a comment is not a label. `needs-human` is the transition that
    needs one.

    Returns `(removed, added)`: the label names it took off, and the one it put on or an
    empty list. Nothing to remove and nothing to add is no write at all. So an item
    already in the right state costs one read and no command.
    """
    remove = [name for name in WORK_STATES if name in labels and name != add]
    added = [add] if add and add not in labels else []
    if remove or added:
        tracker.write(tracker.label_argv(item, remove=remove, add=added))
    if comment:
        tracker.write(tracker.comment_argv(item, comment))
    return remove, added


def swap_line(item, removed, added):
    """How one label swap reads, for the line a seam prints."""
    was = ", ".join(removed) or "no work-state label"
    now = ", ".join(added) or "the label it already wore"
    return f"{was} → {now} on work item #{item}"


def needs_human(tracker, item, labels, saw):
    """Write `needs-human` on one work item, plus one comment saying what the seam saw.

    The one label that stops every tick, and the one transition that carries a comment. A
    label with no reason leaves the maintainer to reconstruct one, so the comment is part
    of the transition rather than a courtesy.

    **The watch and the queue both write it**, and each one pairs it with its own exit
    code. The watch writes it when a close cannot run and when a stall has spent its one
    retry. The queue writes it when a spawn fails. So the line is what this returns, and
    the code stays with the caller that owns the contract.

    Only the maintainer removes the label.
    """
    removed, added = write_transition(
        tracker, item, labels, NEEDS_HUMAN, comment=f"{NEEDS_HUMAN}: {saw}"
    )
    return (
        f"{NEEDS_HUMAN}: {saw} — applied: {swap_line(item, removed, added)}, with one "
        f"comment that says what this tick saw"
    )


# --- the CLI surface the seams share ----------------------------------------


class UsageExitParser(argparse.ArgumentParser):
    """An `argparse` parser whose usage errors stay outside the exit contract.

    `add_subparsers` builds each subcommand from `type(self)`, so every subcommand
    inherits this without naming it.
    """

    def exit(self, status=0, message=None):
        if message:
            self._print_message(message, sys.stderr)
        sys.exit(EXIT_USAGE if status else status)


def add_tracker_arguments(parser):
    """The four flags that name one tracker, added to one subcommand.

    Every subcommand that reads the tracker takes all four, because a seam's `main` builds
    one **Tracker adapter** out of them. Written once here, so no two subcommands in this
    repo can drift apart on the tracker they read (ADR 0040).
    """
    parser.add_argument(
        "--repo",
        default="",
        help="the tracker repository the labels and the comments sit on, as OWNER/NAME",
    )
    parser.add_argument(
        "--tracker-cli",
        default=GH,
        choices=(GH, GLAB),
        help="which CLI reads the labels and the comments, and writes the label a "
        "transition swaps. The caller resolves it from "
        "docs/agents/issue-tracker.md. This seam passes the name to the tracker "
        "adapter, which holds every command, so this seam names no tracker",
    )
    parser.add_argument(
        "--tracker-host",
        default="",
        metavar="HOST",
        help="the tracker host, for a server the CLI does not reach by default. Each "
        "read carries it in the place that read needs. With no host, every read goes "
        "to the CLI's own default server",
    )
    parser.add_argument(
        "--gh-fixture",
        help="JSON that stands in for any tracker read, so a label and a position "
        "need no network and no login (used by the tests). It keeps this name "
        "because scripts/close_item.py reads the same file in the same format",
    )


def add_board_arguments(parser, column=True):
    """The coordinates that name one board, added to one subcommand.

    `start` reads one card and `queue` reads one per open item, so both take all three.
    Written once, so the two can never drift apart on the board they read. With any one of
    them missing the label alone decides, which is a supported configuration and never an
    error (ADR 0045).

    `column` is False for `tick`, which writes a card and reads none. The start column is
    the maintainer's own lane and no tick writes it, so a tick that took that flag would
    take a flag it cannot use (ADR 0067). The two coordinates below are written once for
    every subcommand, so a reader and a writer can never name two different boards.
    """
    parser.add_argument(
        "--board-project",
        default=0,
        type=int,
        metavar="NUMBER",
        help="the project number of the board that holds the card. The caller reads it "
        "from the Project board section of docs/agents/issue-tracker.md, so this seam "
        "holds no board of its own. With this flag missing no card is read and none is "
        "written",
    )
    parser.add_argument(
        "--board-owner",
        default="",
        metavar="OWNER",
        help="the owner the board belongs to, from the same section. With this flag "
        "missing no card is read and none is written",
    )
    if column:
        parser.add_argument(
            "--start-column",
            default="",
            metavar="NAME",
            help="the name of the start column, from the same section. It is a name and "
            "never an option id: a write resolves the id from the name at run time. With "
            "this flag missing the label alone decides",
        )
