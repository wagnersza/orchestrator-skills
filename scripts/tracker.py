#!/usr/bin/env python3
"""Every tracker command the two seams run or print, behind one adapter.

`scripts/worker_state.py` asks what state a work item is in, and
`scripts/close_item.py` closes one. Each seam held its own tracker code until this
module existed. The first had a `gh` builder and a `glab` builder, and the second
hardcoded `gh`. So one concept had two interfaces in one repo, and two fixture
formats came with them (ADR 0040).

**Every command here is one of the verified reads.** The commands live as prose in
`orchestrator/references/tracker-reads.md`, and this module is where the same
commands live as code (ADR 0039). A read is also checked before it is parsed: `run`
raises on a non-zero exit, so no caller parses an error block.

**One class, and the tracker is four values on it**: the CLI name, the host, the
repository and the fixture. Where two trackers disagree, the branch is inside the
one method that differs. So a new tracker lands here and in no seam.

**One fixture format.** A fixture file stands in for every read, so a test closes an
item and reads its position with no network and no login. It holds one record per work
item and one per pull request:

    {"items": {"54": {"state": "OPEN",
                      "title": "The queue subcommand",
                      "body": "## Parent\n\n#178\n",
                      "labels": ["in-progress"],
                      "comments": ["Verdict: approve", "an earlier note"],
                      "board": "To do"}},
     "pull_requests": {"48": {"state": "MERGED",
                              "merge_commit": "a1b2c3d",
                              "head": "someone/54-a-branch"}}}

`board` is the `Status` option name on that item's card. It is the one fact the board
answers, and no caller writes it back (ADR 0054). `head` is the branch that pull
request was opened from, and it is what a caller matches to find the pull request for
a branch. `title` and `body` are what a queue read asks for, and the body is where the
`## Parent`, `## Blocked by` and `## Touches` edges live. Every key is optional. An
item that is absent from a key reads as an item with none of that fact, and a key that
is absent reads the same way. **A record with no `state` reads as open**, because a
fixture that lists one item is a fixture about a live queue.

In fixture mode a write runs nothing. It appends its command to
`<fixture path>.writes`, one per line. That file is what a test reads to see which
tracker writes a run made.
"""

import json
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote

# The two tracker CLIs a caller can name. Each method below that both of them answer
# holds one branch per CLI. Nothing outside this module tells one tracker from the
# other.
GH = "gh"
GLAB = "glab"

# How many cards one board read asks for. The number is part of the recipe in
# `docs/agents/issue-tracker.md`, so it is no bound this module chose.
BOARD_LIMIT = 100

# How many open work items one queue read asks for. Both numbers are part of the recipe
# in `orchestrator/references/tracker-reads.md`, so neither one is a bound this module
# chose. One tracker pages with a limit and the other with a page size.
ITEM_LIMIT = 200
PAGE_SIZE = 100

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


def label_names(labels):
    """The label names in one tracker answer.

    A label is a plain string on one tracker and an object with a `name` on the other.
    So one reader serves both answers, and no caller learns which shape it holds.
    """
    return [
        entry if isinstance(entry, str) else entry.get("name") or ""
        for entry in labels or []
    ]


def item_record(number, title, labels, body):
    """One work item in the shape a queue read answers, whatever tracker it came from.

    Four facts, and a queue tick reads no fifth: the number, the title a worktree name
    is built from, the labels the start gate reads, and the body that carries the
    `## Parent`, `## Blocked by` and `## Touches` edges.
    """
    return {
        "number": int(number or 0),
        "title": str(title or ""),
        "labels": label_names(labels),
        "body": str(body or ""),
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
        # The cards of one board, held after the first read of them. `_board` explains
        # why they are held.
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

        **The one list read, and a queue tick makes it once a minute.** The body comes
        with it, because the `## Parent`, `## Blocked by` and `## Touches` edges live
        there and a second read per item costs one command per item.

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
        """The open items from `gh`, which answers all four fields in one command."""
        return [
            item_record(
                entry.get("number"),
                entry.get("title"),
                entry.get("labels"),
                entry.get("body"),
            )
            for entry in read_json(
                [
                    GH,
                    "issue",
                    "list",
                    "--state",
                    "open",
                    "--limit",
                    str(ITEM_LIMIT),
                    "--json",
                    "number,title,labels,body",
                    *self._repo_flag(),
                ],
                "[]",
            )
            or []
        ]

    def _glab_open_items(self):
        """The open items from `glab`, through its API rather than its issue list.

        `glab issue list` is the flag trap `orchestrator/references/tracker-reads.md`
        records: its JSON flag has another spelling, and it takes no `--state` at all.
        So this read goes through `glab api`, and the project path is part of the URL.
        That path is why the repository is required here, the same as it is for the two
        other `glab api` reads above. The body arrives under its own name there.
        """
        if not self.repo:
            raise TrackerError(
                "a glab read of the open work items needs --repo as OWNER/NAME, "
                "because the project path is part of the command"
            )
        argv = [
            GLAB,
            "api",
            f"projects/{self.repo.replace('/', '%2F')}/issues"
            f"?state=opened&per_page={PAGE_SIZE}",
        ]
        if self.host:
            argv += ["--hostname", self.host]
        return [
            item_record(
                entry.get("iid"),
                entry.get("title"),
                entry.get("labels"),
                entry.get("description"),
            )
            for entry in read_json(argv, "[]") or []
        ]

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

    def board_status(self, item, project, owner):
        """The `Status` option name on this work item's card, or an empty string.

        **This is the one question the board answers, and nothing writes it back**
        (ADR 0054). A caller asks whether the name is the start column.

        An empty string covers three facts: no board at all, an item with no card, and
        a card with no status. A caller compares the name it wants, so none of the
        three is an error.
        """
        if self.fixture is not None:
            return str(self._item(item).get("board") or "")
        for entry in self._board(project, owner):
            if (entry.get("content") or {}).get("number") == item:
                return str(entry.get("status") or "")
        return ""

    def _board(self, project, owner):
        """Every card on one board, read once per adapter.

        **The read answers every card, so it is made once and held.** A queue tick asks
        for the card of every open work item, and one call per item is one Projects query
        per item every minute. So this adapter makes one query per tick whatever
        the queue holds (ADR 0045). A caller that asks about a second board reads again,
        because the held answer names the board it came from.
        """
        key = (project, owner)
        if self._cards is None or self._cards[0] != key:
            data = read_json(self._board_list_argv(project, owner))
            self._cards = (key, list(data.get("items") or []))
        return self._cards[1]

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

    # There is no card write here. The board is an input, so this adapter holds one
    # board read and no board write (ADR 0054).

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

        A project board is one tracker's own surface, so this builder names that CLI
        and the CLI name on this object does not reach it. A repo on the other
        tracker has no such board, so it passes no board argument and this read
        never runs there.

        **One caller, and it walks the answer in Python.** A `--jq` filter here was a
        second parser of the same recipe, and it served the card write alone (ADR 0054).
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
