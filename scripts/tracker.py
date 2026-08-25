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
item and reads a phase with no network and no login. It holds one record per work
item and one per pull request:

    {"items": {"54": {"state": "OPEN",
                      "labels": ["in-progress", "phase:review"],
                      "comments": ["Verdict: approve", "an earlier note"],
                      "board": "To merge",
                      "card": "PVTI_x"}},
     "pull_requests": {"48": {"state": "MERGED", "merge_commit": "a1b2c3d"}}}

`board` is the `Status` option name on that item's card, and `card` is the id that
addresses the card. Every key is optional. An item that is absent from a key reads
as an item with none of that fact, and a key that is absent reads the same way.

In fixture mode a write runs nothing. It appends its command to
`<fixture path>.writes`, one per line. That file is what a test reads to see which
tracker writes a run made.
"""

import json
import subprocess
from pathlib import Path

# The two tracker CLIs a caller can name. Each method below that both of them answer
# holds one branch per CLI. Nothing outside this module tells one tracker from the
# other.
GH = "gh"
GLAB = "glab"

# How many cards one board read asks for. The number is part of the recipe in
# `docs/agents/issue-tracker.md`, so it is no bound this module chose.
BOARD_LIMIT = 100


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
        self.fixture = json.loads(self.path.read_text()) if self.path else None

    def _item(self, number):
        """One work item's fixture record, or an empty one where it is absent."""
        return (self.fixture.get("items") or {}).get(str(number)) or {}

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
        argv = [GH, "issue", "view", str(item), "--json", "comments,labels"]
        if self.repo:
            argv += ["--repo", self.repo]
        data = read_json(argv)
        return (
            [entry.get("name") or "" for entry in data.get("labels") or []],
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
        labels_argv += ["-R", f"{self.host}/{self.repo}" if self.host else self.repo]
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
            # A label is a plain string on this tracker, and an object on the other one.
            [
                entry if isinstance(entry, str) else entry.get("name") or ""
                for entry in issue.get("labels") or []
            ],
            [entry.get("body") or "" for entry in notes or []],
        )

    def issue(self, number):
        """One work item's state and its label names."""
        if self.fixture is not None:
            record = self._item(number)
            return {
                "state": record.get("state"),
                "labels": list(record.get("labels") or []),
            }
        argv = [self.cli, "issue", "view", str(number), "--json", "state,labels"]
        data = read_json(argv)
        return {
            "state": data.get("state"),
            "labels": [label["name"] for label in data.get("labels") or []],
        }

    def pull_request(self, number):
        """The pull request's state, and the commit its merge landed as."""
        if self.fixture is not None:
            record = (self.fixture.get("pull_requests") or {}).get(str(number)) or {}
            return {
                "state": record.get("state"),
                "merge_commit": str(record.get("merge_commit") or ""),
            }
        data = read_json(self.pr_read_argv(number))
        return {
            "state": data.get("state"),
            "merge_commit": (data.get("mergeCommit") or {}).get("oid") or "",
        }

    def board_status(self, item, project, owner):
        """The `Status` option name on this work item's card, or an empty string.

        An empty string covers two facts: an item with no card, and a card with no
        status. A caller compares the name it wants, so neither fact is an error.
        """
        if self.fixture is not None:
            return str(self._item(item).get("board") or "")
        data = read_json(self._board_list_argv(project, owner))
        for entry in data.get("items") or []:
            if (entry.get("content") or {}).get("number") == item:
                return str(entry.get("status") or "")
        return ""

    def board_card(self, item, project, owner):
        """The id that addresses this work item's card, or an empty string.

        The filter runs in the CLI here, because the caller wants the one card. The
        walk in `board_status` answers the other question from the same read.
        """
        if self.fixture is not None:
            return str(self._item(item).get("card") or "")
        return run(
            self._board_list_argv(
                project,
                owner,
                f".items[] | select(.content.number=={item}) | .id",
            )
        ).strip()

    # --- the argv a seam runs or prints

    def pr_read_argv(self, number):
        """The argv of the merged-state read, which a plan also prints."""
        return [self.cli, "pr", "view", str(number), "--json", "state,mergeCommit"]

    def label_argv(self, item, remove=(), add=()):
        """The argv that swaps the labels on one work item.

        The caller passes the names it wants and no flag. The flag that carries a
        label is one of the things the two trackers disagree about.
        """
        flags = []
        for name in remove:
            flags += ["--remove-label", name]
        for name in add:
            flags += ["--add-label", name]
        return [self.cli, "issue", "edit", str(item), *flags]

    def close_argv(self, item):
        """The argv that closes one work item."""
        return [self.cli, "issue", "close", str(item)]

    def card_argv(self, card, project_id, field_id, option_id):
        """The argv that writes one card's `Status`.

        A repeat of this write changes nothing, so a part-applied close is
        resumable.
        """
        return [
            GH,
            "project",
            "item-edit",
            "--id",
            card,
            "--project-id",
            project_id,
            "--field-id",
            field_id,
            "--single-select-option-id",
            option_id,
        ]

    def comment_argv(self, item, body):
        """The argv that posts one comment on a work item.

        One branch per tracker, for the same reason the reads above have one each:
        the flag that carries the message differs, and so does the place the host
        goes. One CLI takes an optional repository, and falls back to the one the
        working directory holds. For the other CLI the repository is part of the
        command.
        """
        if self.cli == GLAB:
            argv = [GLAB, "issue", "note", str(item), "--message", body]
            if self.repo:
                argv += ["-R", f"{self.host}/{self.repo}" if self.host else self.repo]
            return argv
        argv = [GH, "issue", "comment", str(item), "--body", body]
        if self.repo:
            argv += ["--repo", self.repo]
        return argv

    def _board_list_argv(self, project, owner, jq=""):
        """The argv of the one board read, which is the recipe the tracker file holds.

        A project board is one tracker's own surface, so this builder names that CLI
        and the CLI name on this object does not reach it. A repo on the other
        tracker has no such board, so it passes no board argument and this read
        never runs there.
        """
        argv = [
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
        if jq:
            argv += ["--jq", jq]
        return argv

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
