#!/usr/bin/env python3
"""Behaviour tests for the tracker adapter: what argv it builds, and what it reads.

The adapter is a library and not a seam, so these cases import it. A command that
runs is a real `subprocess` against a shell script this file writes onto `PATH`. So
no mocking framework stands between a case and the argv the adapter built. The
script logs every call, which is what an argv assertion reads.

The seam suites cover the two callers end to end. This file covers the part they
share: one command per read, one fixture format, and a non-zero exit that raises
before anything parses.

    python3 -m pytest scripts/ -q
    python3 -m unittest discover -s scripts -t . -q     # fallback, no pytest
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts import tracker

ITEM = 54
PR = 48
BRANCH = "someone/54-a-branch"
HOST = "git.example.com"
REPO = "team/thing"


class TrackerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.path = os.environ["PATH"]
        os.environ["PATH"] = f"{self.bin}{os.pathsep}{self.path}"
        self.addCleanup(self.restore_path)
        self.addCleanup(self.tmp.cleanup)

    def restore_path(self):
        os.environ["PATH"] = self.path

    def fake_cli(self, name, answer="", code=0, stderr="", **payloads):
        """A tracker CLI of `name` on `PATH`, and the file it logs its argv to.

        Each keyword is a first argument the adapter can send (`issue`, `api`), and
        its value is what that command prints. With no keyword every command prints
        `answer`.
        """
        log = self.root / f"{name}.argv"
        cases = "\n".join(
            f"  {first}) printf '%s' '{json.dumps(payload)}' ;;"
            for first, payload in payloads.items()
        )
        answers = (
            f'case "$1" in\n{cases}\nesac\n'
            if payloads
            else f"printf '%s' '{answer}'\n"
        )
        script = self.bin / name
        script.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' \"$*\" >> '{log}'\n"
            f"{answers}"
            f"printf '%s' '{stderr}' >&2\n"
            f"exit {code}\n"
        )
        script.chmod(0o755)
        return log

    def write_fixture(self, **items):
        """One fixture file in the one format, and the path to it."""
        path = self.root / "tracker.json"
        path.write_text(json.dumps(items))
        return path

    # --- one fixture format, read by every fact the two seams ask for

    def test_one_fixture_record_answers_every_fact_about_one_item(self):
        """A test author writes one record, and both seams read it."""
        path = self.write_fixture(
            items={
                str(ITEM): {
                    "state": "OPEN",
                    "labels": ["in-progress"],
                    "comments": ["Verdict: approve"],
                    "board": "To do",
                }
            },
            pull_requests={
                str(PR): {
                    "state": "MERGED",
                    "merge_commit": "a1b2c3d",
                    "head": BRANCH,
                }
            },
        )
        one = tracker.Tracker(fixture=path)

        self.assertEqual(
            one.item_facts(ITEM),
            (["in-progress"], ["Verdict: approve"]),
        )
        self.assertEqual(
            one.issue(ITEM),
            {"state": "OPEN", "labels": ["in-progress"]},
        )
        self.assertEqual(one.board_status(ITEM, 6, "someone"), "To do")
        self.assertEqual(
            one.pull_request(PR), {"state": "MERGED", "merge_commit": "a1b2c3d"}
        )
        self.assertEqual(
            one.pull_request_for_branch(BRANCH), {"number": PR, "state": "MERGED"}
        )

    def test_an_absent_item_and_an_absent_key_read_the_same_way(self):
        """No record is not an error, because a repo with no board reads this way."""
        one = tracker.Tracker(fixture=self.write_fixture())

        self.assertEqual(one.item_facts(ITEM), ([], []))
        self.assertEqual(one.issue(ITEM), {"state": None, "labels": []})
        self.assertEqual(one.board_status(ITEM, 6, "someone"), "")
        self.assertEqual(one.pull_request(PR), {"state": None, "merge_commit": ""})
        self.assertEqual(
            one.pull_request_for_branch(BRANCH), {"number": 0, "state": ""}
        )

    def test_a_fixture_write_runs_nothing_and_is_recorded(self):
        """The log is how a test sees which writes an execute run made."""
        path = self.write_fixture()
        one = tracker.Tracker(fixture=path)
        self.fake_cli("gh", code=9)

        one.write(one.close_argv(ITEM))
        one.write(one.label_argv(ITEM, remove=["to-review"]))

        log = path.parent / (path.name + ".writes")
        self.assertEqual(
            log.read_text().splitlines(),
            [
                f"gh issue close {ITEM}",
                f"gh issue edit {ITEM} --remove-label to-review",
            ],
        )
        self.assertFalse((self.root / "gh.argv").exists())

    # --- the argv of every command the close seam runs or prints

    def test_the_close_seam_argv_is_one_command_per_write(self):
        one = tracker.Tracker()

        self.assertEqual(
            one.pr_read_argv(PR),
            ["gh", "pr", "view", str(PR), "--json", "state,mergeCommit"],
        )
        self.assertEqual(
            one.label_argv(ITEM, remove=["in-progress"], add=["to-review"]),
            [
                "gh",
                "issue",
                "edit",
                str(ITEM),
                "--remove-label",
                "in-progress",
                "--add-label",
                "to-review",
            ],
        )
        self.assertEqual(one.close_argv(ITEM), ["gh", "issue", "close", str(ITEM)])

    def test_a_label_swap_with_no_name_builds_no_flag(self):
        """The caller passes names, so an empty pair leaves a bare edit command."""
        self.assertEqual(
            tracker.Tracker().label_argv(ITEM), ["gh", "issue", "edit", str(ITEM)]
        )

    def test_the_close_seam_argv_on_the_other_tracker_is_no_rename(self):
        """Four commands, and each one differs by more than the CLI name."""
        one = tracker.Tracker(cli=tracker.GLAB, host=HOST, repo=REPO)
        where = ["-R", f"{HOST}/{REPO}"]

        # The merge request has its own subcommand and its own JSON flag.
        self.assertEqual(
            one.pr_read_argv(PR), ["glab", "mr", "view", str(PR), "-F", "json", *where]
        )
        # The label swap has its own subcommand and its own two flags.
        self.assertEqual(
            one.label_argv(ITEM, remove=["in-progress"], add=["to-review"]),
            [
                "glab",
                "issue",
                "update",
                str(ITEM),
                "--label",
                "to-review",
                "--unlabel",
                "in-progress",
                *where,
            ],
        )
        # The close takes no reason, whatever reason the caller passes.
        self.assertEqual(
            one.close_argv(ITEM, "the work is merged"),
            ["glab", "issue", "close", str(ITEM), *where],
        )
        # So the reason is its own write, and it is the note command.
        self.assertEqual(
            one.closing_note_argv(ITEM, "the work is merged"),
            one.comment_argv(ITEM, "the work is merged"),
        )

    def test_the_close_command_carries_the_reason_where_the_cli_takes_one(self):
        """One tracker records the reason in the close itself, so there is one write."""
        one = tracker.Tracker()

        self.assertEqual(
            one.close_argv(ITEM, "the work is merged"),
            ["gh", "issue", "close", str(ITEM), "--comment", "the work is merged"],
        )
        self.assertEqual(one.closing_note_argv(ITEM, "the work is merged"), [])

    def test_the_close_writes_arrive_in_order_so_no_caller_orders_them(self):
        """The reason goes before the close, and the adapter is what puts it there.

        A caller reads the list and never the CLI name. So it cannot get the order
        wrong, because there is no order left for it to assemble (ADR 0056).
        """
        gh = tracker.Tracker()
        glab = tracker.Tracker(cli=tracker.GLAB)

        # The tracker with a reason flag: one write, and the reason rides it.
        self.assertEqual(
            gh.close_writes(ITEM, "the work is merged"),
            [("close", gh.close_argv(ITEM, "the work is merged"))],
        )
        # The tracker with no reason flag: two writes, the note first.
        self.assertEqual(
            glab.close_writes(ITEM, "the work is merged"),
            [
                ("note", glab.comment_argv(ITEM, "the work is merged")),
                ("close", glab.close_argv(ITEM, "the work is merged")),
            ],
        )
        # No reason means one write on either tracker, and it is the close.
        for one in (gh, glab):
            self.assertEqual([name for name, _ in one.close_writes(ITEM)], ["close"])

    def test_no_reason_leaves_the_close_bare_on_either_tracker(self):
        """A caller that passes no reason posts nothing and closes as it did before."""
        for cli in (tracker.GH, tracker.GLAB):
            one = tracker.Tracker(cli=cli)
            self.assertEqual(one.close_argv(ITEM), [cli, "issue", "close", str(ITEM)])
            self.assertEqual(one.closing_note_argv(ITEM, ""), [])

    def test_the_repository_argument_goes_where_each_cli_wants_it(self):
        """One CLI takes a flag of its own for the host, and the other joins the two."""
        self.assertEqual(
            tracker.Tracker(repo=REPO).close_argv(ITEM)[-2:], ["--repo", REPO]
        )
        self.assertEqual(
            tracker.Tracker(cli=tracker.GLAB, host=HOST, repo=REPO).close_argv(ITEM)[
                -2:
            ],
            ["-R", f"{HOST}/{REPO}"],
        )
        # With no repository, neither CLI names one: both read the clone the working
        # directory holds.
        for cli in (tracker.GH, tracker.GLAB):
            self.assertEqual(
                tracker.Tracker(cli=cli).close_argv(ITEM),
                [cli, "issue", "close", str(ITEM)],
            )

    # --- the reads, one command per tracker

    def test_the_gh_facts_read_is_one_command(self):
        log = self.fake_cli(
            "gh",
            answer=json.dumps(
                {"labels": [{"name": "in-progress"}], "comments": [{"body": "a note"}]}
            ),
        )

        facts = tracker.Tracker(repo=REPO).item_facts(ITEM)

        self.assertEqual(facts, (["in-progress"], ["a note"]))
        self.assertEqual(
            log.read_text().splitlines(),
            [f"issue view {ITEM} --json comments,labels --repo {REPO}"],
        )

    def test_the_glab_facts_read_carries_the_host_where_each_command_needs_it(self):
        """One command takes the host in its repository argument, and one as a flag."""
        log = self.fake_cli(
            "glab",
            issue={"labels": ["in-progress"]},
            api=[{"body": "a note"}],
        )

        facts = tracker.Tracker(cli=tracker.GLAB, host=HOST, repo=REPO).item_facts(ITEM)

        self.assertEqual(facts, (["in-progress"], ["a note"]))
        self.assertEqual(
            log.read_text().splitlines(),
            [
                f"issue view {ITEM} -F json -R {HOST}/{REPO}",
                f"api projects/team%2Fthing/issues/{ITEM}/notes --hostname {HOST}",
            ],
        )

    def test_a_glab_read_without_a_repository_says_why_it_cannot_run(self):
        """The project path is part of both commands, so the name is not optional."""
        with self.assertRaises(tracker.TrackerError) as caught:
            tracker.Tracker(cli=tracker.GLAB).item_facts(ITEM)

        self.assertIn("--repo", str(caught.exception))

    def test_the_merged_state_read_answers_the_same_two_facts_on_either_tracker(self):
        """One tracker says `merged` and `merge_commit_sha`, the other says neither."""
        self.fake_cli("gh", answer=json.dumps({"state": "MERGED", "mergeCommit": None}))
        self.assertEqual(
            tracker.Tracker().pull_request(PR), {"state": "MERGED", "merge_commit": ""}
        )

        self.fake_cli(
            "gh",
            answer=json.dumps({"state": "MERGED", "mergeCommit": {"oid": "a1b2c3d"}}),
        )
        self.assertEqual(
            tracker.Tracker().pull_request(PR),
            {"state": "MERGED", "merge_commit": "a1b2c3d"},
        )

        log = self.fake_cli(
            "glab",
            answer=json.dumps({"state": "merged", "merge_commit_sha": "e4f5a6b"}),
        )
        self.assertEqual(
            tracker.Tracker(cli=tracker.GLAB, host=HOST, repo=REPO).pull_request(PR),
            {"state": "merged", "merge_commit": "e4f5a6b"},
        )
        self.assertEqual(
            log.read_text().splitlines(),
            [f"mr view {PR} -F json -R {HOST}/{REPO}"],
        )

    def test_the_pull_request_for_a_branch_answers_a_number_and_a_state(self):
        """The caller holds a branch, so the adapter is what finds the number."""
        log = self.fake_cli(
            "gh", answer=json.dumps([{"number": PR, "state": "MERGED"}])
        )

        one = tracker.Tracker(repo=REPO)

        self.assertEqual(
            one.pull_request_for_branch(BRANCH), {"number": PR, "state": "MERGED"}
        )
        self.assertEqual(
            log.read_text().splitlines(),
            [f"pr list --head {BRANCH} --state all --json number,state --repo {REPO}"],
        )

    def test_a_branch_with_no_pull_request_is_no_error(self):
        """An empty list is the quiet answer, and the caller reads one shape."""
        self.fake_cli("gh", answer="[]")

        self.assertEqual(
            tracker.Tracker(repo=REPO).pull_request_for_branch(BRANCH),
            {"number": 0, "state": ""},
        )

    def test_a_merged_pull_request_wins_over_an_older_closed_one(self):
        """A branch closed and opened again carries two records, and one merged."""
        self.fake_cli(
            "gh",
            answer=json.dumps(
                [{"number": 99, "state": "CLOSED"}, {"number": PR, "state": "MERGED"}]
            ),
        )

        self.assertEqual(
            tracker.Tracker(repo=REPO).pull_request_for_branch(BRANCH),
            {"number": PR, "state": "MERGED"},
        )

    def test_the_branch_read_on_the_other_tracker_goes_through_its_api(self):
        """`glab mr list` has the flag trap, so the API answers this read instead."""
        log = self.fake_cli("glab", answer=json.dumps([{"iid": 7, "state": "merged"}]))

        one = tracker.Tracker(cli=tracker.GLAB, host=HOST, repo=REPO)

        self.assertEqual(
            one.pull_request_for_branch(BRANCH), {"number": 7, "state": "merged"}
        )
        # The branch is escaped in the query, so a `/` reads as one path segment and a
        # `+` cannot arrive as a space.
        self.assertEqual(
            log.read_text().splitlines(),
            [
                "api projects/team%2Fthing/merge_requests"
                "?source_branch=someone%2F54-a-branch"
                f"&state=all --hostname {HOST}"
            ],
        )

    def test_a_branch_name_that_would_break_the_query_is_escaped(self):
        """A `+` reads as a space on the server, and an `&` splits the query."""
        argv = tracker.Tracker(cli=tracker.GLAB, repo=REPO).pr_for_branch_argv(
            "feat/a+b&c"
        )

        self.assertIn("?source_branch=feat%2Fa%2Bb%26c&state=all", argv[2])

    def test_a_glab_branch_read_without_a_repository_says_why_it_cannot_run(self):
        """The project path is part of the command, so the name is not optional."""
        with self.assertRaises(tracker.TrackerError) as caught:
            tracker.Tracker(cli=tracker.GLAB).pull_request_for_branch(BRANCH)

        self.assertIn("--repo", str(caught.exception))

    def test_the_item_read_on_the_other_tracker_is_one_command_with_plain_labels(self):
        """A label is a string there, and the state is the caller's to compare."""
        log = self.fake_cli(
            "glab", answer=json.dumps({"state": "closed", "labels": ["to-review"]})
        )

        one = tracker.Tracker(cli=tracker.GLAB, host=HOST, repo=REPO)

        self.assertEqual(one.issue(ITEM), {"state": "closed", "labels": ["to-review"]})
        self.assertEqual(
            log.read_text().splitlines(),
            [f"issue view {ITEM} -F json -R {HOST}/{REPO}"],
        )

    def test_the_board_read_names_one_tracker_whichever_cli_is_set(self):
        """A board is one tracker's own surface, so the CLI name does not reach it."""
        log = self.fake_cli(
            "gh",
            answer=json.dumps(
                {"items": [{"status": "In review", "content": {"number": ITEM}}]}
            ),
        )

        one = tracker.Tracker(cli=tracker.GLAB, host=HOST, repo=REPO)

        self.assertEqual(one.board_status(ITEM, 6, "someone"), "In review")
        self.assertEqual(
            log.read_text().splitlines(),
            ["project item-list 6 --owner someone --format json --limit 100"],
        )

    def test_a_card_for_another_item_is_not_this_item_s_card(self):
        self.fake_cli(
            "gh",
            answer=json.dumps(
                {"items": [{"status": "In review", "content": {"number": 99}}]}
            ),
        )

        self.assertEqual(tracker.Tracker().board_status(ITEM, 6, "someone"), "")

    def test_the_adapter_holds_a_board_read_and_no_board_write(self):
        """The board is an input, so the two methods that only wrote a card are gone.

        `board_card` answered the id a write addresses, and `card_argv` was the write.
        Neither one has a caller now (ADR 0054).
        """
        one = tracker.Tracker()

        self.assertTrue(hasattr(one, "board_status"))
        for name in ("board_card", "card_argv"):
            self.assertFalse(hasattr(one, name), f"{name} is still on the adapter")

    def test_a_board_read_with_no_board_configured_answers_an_empty_name(self):
        """A tracker file that names no board is a supported configuration.

        The caller then holds no coordinates to pass, and the answer is the same empty
        name that a card with no status gives. Neither one is an error, so no caller
        branches on which of the two it got.
        """
        path = self.write_fixture(items={str(ITEM): {"state": "OPEN"}})

        self.assertEqual(tracker.Tracker(fixture=path).board_status(ITEM, "", ""), "")

    def test_the_comment_argv_differs_by_tracker(self):
        self.assertEqual(
            tracker.Tracker(repo=REPO).comment_argv(ITEM, "a line"),
            ["gh", "issue", "comment", str(ITEM), "--body", "a line", "--repo", REPO],
        )
        self.assertEqual(
            tracker.Tracker(cli=tracker.GLAB, host=HOST, repo=REPO).comment_argv(
                ITEM, "a line"
            ),
            [
                "glab",
                "issue",
                "note",
                str(ITEM),
                "--message",
                "a line",
                "-R",
                f"{HOST}/{REPO}",
            ],
        )

    # --- a read is checked before it is parsed (ADR 0039)

    def test_a_failed_read_names_the_command_and_parses_nothing(self):
        """The exit code is the check, so no error block reaches a parser."""
        self.fake_cli("gh", code=1, stderr="Unknown flag: --nope.")

        with self.assertRaises(tracker.TrackerError) as caught:
            tracker.Tracker().issue(ITEM)

        message = str(caught.exception)
        self.assertIn("gh issue view", message)
        self.assertIn("Unknown flag", message)

    def test_a_read_that_prints_no_json_fails_as_a_parse_and_not_as_a_fact(self):
        """A clean exit is no proof of JSON, so the parser is the second check."""
        self.fake_cli("gh", answer="a text table")

        with self.assertRaises(json.JSONDecodeError):
            tracker.Tracker().issue(ITEM)


if __name__ == "__main__":
    unittest.main()
