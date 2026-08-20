#!/usr/bin/env python3
"""Behaviour tests for every Markdown link in this repo: the tree in, the list of
targets that do not resolve out.

A dangling cross-reference is this repo's named failure mode, and the repo is
mostly Markdown. So the walk starts at the repo root and finds every `*.md`. It
holds no list of files, so a new Markdown file is covered the moment someone
writes it, with no edit here.

Two failure classes, one test method each. A relative path that is not on disk is
one. An anchor that matches no heading in the file it points at is the other. Where
a link carries both halves, the walk checks both. Each test reports every failure
it found in one message, so a maintainer fixes a batch instead of one link per
run. Each failure names the file that holds the link and the target it points at.

The anchor slug follows GitHub's rule. First the heading goes to lower case. Then
the rule removes every character that is not a word character, a space or a hyphen.
Then it replaces each space with one hyphen. Nothing collapses: `## On the wake —
one response per outcome` makes `#on-the-wake--one-response-per-outcome`, with two
hyphens where the em dash stood. A checker that collapses whitespace reports four
live links in `orchestrator/SKILL.md` as failures, so that trap has its own test.

A link inside a fenced code block is example output rather than a cross-reference,
so the walk skips it. The walk skips a link whose scheme is `http`, `https` or
`mailto` as well, which is what keeps the suite offline.

Fixtures are small Markdown files in a temporary directory. So each failure class
has a link behind it that really dangles. Every test asserts on the reported
failures, and none of them asserts on a helper.

    python3 -m pytest scripts/ -q
    python3 -m unittest discover -s scripts -q     # fallback, no pytest
"""

import re
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# A directory of machinery, not of prose. None of it is this repo's Markdown.
SKIP_DIRS = {".git", ".pytest_cache", "node_modules"}

# An external target needs a request to check, and this suite makes none.
SKIP_SCHEMES = ("http://", "https://", "mailto:")

# The target half of an inline link: `[text](target)`.
LINK = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)")

# A fence opens and closes a code block. Three or more of one character, and the
# closing run is at least as long as the opening one.
FENCE = re.compile(r"^ *(`{3,}|~{3,})")

ATX_HEADING = re.compile(r"^ {0,3}#{1,6} +(.+?) *$")


def slug(heading):
    """The anchor GitHub makes for a heading.

    Lower case first. Then out goes every character that is not a word character, a
    space or a hyphen. Then one hyphen per space, so two spaces make two hyphens.
    """
    return re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")


def markdown_files(root):
    """Every Markdown file under `root`, minus the directories that hold no prose."""
    for path in sorted(Path(root).rglob("*.md")):
        if SKIP_DIRS.isdisjoint(path.relative_to(root).parts):
            yield path


def body_lines(text):
    """Yield `(number, line)` for each line that sits outside a fenced code block.

    Both the links and the headings come through here. So a `#` comment in a shell
    example is no heading, and a path in example output is no cross-reference.
    """
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        found = FENCE.match(line)
        marker = found.group(1) if found else ""
        if fence is None:
            if marker:
                fence = marker
            else:
                yield number, line
        elif marker.startswith(fence[0]) and len(marker) >= len(fence):
            fence = None


def anchors(path):
    """Every anchor the headings of one file make."""
    text = path.read_text(encoding="utf-8")
    found = set()
    for _, line in body_lines(text):
        heading = ATX_HEADING.match(line)
        if heading:
            found.add(slug(heading.group(1)))
    return found


def scan(root):
    """Return every link under `root` that does not resolve.

    Each item is a `(kind, message)` pair. `kind` is `missing file` for a path that
    is not on disk, and `missing heading` for an anchor that its target file does
    not hold. The message names the file that holds the link, its line, and the
    target.
    """
    # Resolved, so a root behind a symlink still holds the paths a link resolves to.
    root = Path(root).resolve()
    failures = []
    known = {}

    def name(path):
        """The path as a maintainer reads it: relative to the root where it can be."""
        try:
            return str(path.relative_to(root))
        except ValueError:
            return str(path)

    for path in markdown_files(root):
        for number, line in body_lines(path.read_text(encoding="utf-8")):
            for raw in LINK.findall(line):
                if raw.startswith(SKIP_SCHEMES):
                    continue
                where = f"{name(path)}:{number}"
                target, _, anchor = raw.partition("#")
                resolved = (path.parent / target).resolve() if target else path
                if not resolved.exists():
                    failures.append(
                        (
                            "missing file",
                            f"{where} links to {raw}, and no file is at {name(resolved)}",
                        )
                    )
                    continue
                if not anchor or not resolved.is_file():
                    continue
                if resolved not in known:
                    known[resolved] = anchors(resolved)
                if slug(anchor) not in known[resolved]:
                    failures.append(
                        (
                            "missing heading",
                            f"{where} links to {raw}, and {name(resolved)} has no "
                            f"heading with that anchor",
                        )
                    )
    return failures


class LinkTestCase(unittest.TestCase):
    """Six small Markdown files in a temporary directory. The six cases are:

    - a link that resolves
    - a link that does not resolve
    - a link inside a fenced code block
    - an anchor that resolves
    - an anchor that does not resolve
    - an anchor whose heading holds a dash and a question mark
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        self.write(
            "target.md",
            "# The target\n\n## A dash - and a question mark?\n",
        )
        self.write("resolves.md", "[a link that resolves](target.md)\n")
        self.write("dangles.md", "[a link that does not resolve](no-such-file.md)\n")
        self.write(
            "fenced.md",
            "```markdown\n[example output](no-such-file.md)\n```\n",
        )
        self.write(
            "anchors.md",
            "# Its own top heading\n\n"
            "[a same-file anchor](#its-own-top-heading)\n"
            "[a path and an anchor](target.md#the-target)\n"
            "[a dash and a question mark](target.md#a-dash---and-a-question-mark)\n",
        )
        self.write(
            "bad-anchors.md",
            "# Its own top heading\n\n"
            "[no such heading here](#no-such-heading)\n"
            "[no such heading there](target.md#no-such-heading)\n",
        )

    # --- helpers ------------------------------------------------------------

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def assert_resolves(self, root, kind=None):
        """Fail once, with every link that does not resolve in the message."""
        failures = [
            f"{found}: {message}"
            for found, message in scan(root)
            if kind is None or found == kind
        ]
        if failures:
            self.fail("\n".join([f"{len(failures)} links do not resolve:", *failures]))

    def reported(self, root=None, kind=None):
        return [
            message
            for found, message in scan(root or self.root)
            if kind is None or found == kind
        ]

    def reported_in(self, name):
        """Every failure reported against one fixture file."""
        return [message for message in self.reported() if message.startswith(name)]

    # --- the two failure classes, one test each -----------------------------

    def test_a_link_target_that_is_not_a_file_on_disk_is_reported(self):
        """The first class. The message names the file that holds the link and the
        target, because both are what a maintainer needs to fix it."""
        reported = self.reported(kind="missing file")

        self.assertEqual(len(reported), 1, reported)
        self.assertIn("dangles.md:1", reported[0])
        self.assertIn("no-such-file.md", reported[0])

    def test_an_anchor_that_matches_no_heading_is_reported(self):
        """The second class. Both halves of it: an anchor in its own file, and an
        anchor in the file a path points at."""
        reported = self.reported(kind="missing heading")

        self.assertEqual(len(reported), 2, reported)
        self.assertIn("bad-anchors.md:3", reported[0])
        self.assertIn("#no-such-heading", reported[0])
        self.assertIn("bad-anchors.md:4", reported[1])
        self.assertIn("target.md#no-such-heading", reported[1])
        self.assertIn("target.md has no heading", reported[1])

    def test_every_other_fixture_link_resolves(self):
        """The fixtures that must stay quiet, so no test above passes by accident.
        Four cases: a link that resolves, an anchor in its own file, a path with an
        anchor on it, and a heading that holds a dash and a question mark."""
        for name in ("resolves.md", "anchors.md"):
            self.assertEqual(self.reported_in(name), [], name)

    # --- what the walk skips ------------------------------------------------

    def test_a_link_inside_a_fenced_code_block_is_skipped(self):
        """Example output rather than a cross-reference. Line 272 of
        `playwright-cli/SKILL.md` is that case, and the fixture copies it."""
        self.assertEqual(self.reported_in("fenced.md"), [])

        # The same target outside the fence is reported, so the fence is what
        # skipped it and not the target.
        self.write("fenced.md", "[a plain link](no-such-file.md)\n")
        self.assertEqual(len(self.reported_in("fenced.md")), 1)

    def test_a_fence_of_four_backticks_closes_on_four_and_not_on_three(self):
        """`playwright-cli/references/installation.md` holds a four-backtick block
        with three-backtick blocks inside it. A checker that closes on the first
        fence it sees reads the inner example as prose."""
        self.write(
            "nested.md",
            "````markdown\n```\n[example output](no-such-file.md)\n```\n````\n",
        )

        self.assertEqual(self.reported_in("nested.md"), [])

    def test_an_indented_fence_still_opens_a_code_block(self):
        """A fenced block inside a list item is indented, and two files here hold
        one."""
        self.write(
            "listed.md",
            "- a step\n\n  ```markdown\n  [example output](no-such-file.md)\n  ```\n",
        )

        self.assertEqual(self.reported_in("listed.md"), [])

    def test_an_external_scheme_is_skipped_so_the_suite_needs_no_network(self):
        """Three schemes, and the walk checks none of them."""
        self.write(
            "external.md",
            "[a page](https://example.com/no-such-page)\n"
            "[a page](http://example.com/no-such-page)\n"
            "[a mailbox](mailto:nobody@example.com)\n",
        )

        self.assertEqual(self.reported_in("external.md"), [])

    def test_the_skipped_directories_hold_no_checked_link(self):
        """Machinery, not prose. A dangling link in any of the three is invisible,
        and the walk reports the same file one level up."""
        for directory in sorted(SKIP_DIRS):
            self.write(f"{directory}/vendored.md", "[nothing](no-such-file.md)\n")

        for directory in sorted(SKIP_DIRS):
            self.assertEqual(self.reported_in(directory), [], directory)

        # The same file one level up is reported, so the directory is what skipped
        # it and not the link.
        self.write("vendored.md", "[nothing](no-such-file.md)\n")
        self.assertEqual(len(self.reported_in("vendored.md")), 1)

    # --- the slug rule ------------------------------------------------------

    def test_two_spaces_in_a_heading_make_two_hyphens(self):
        """Nothing collapses. The em dash goes, and the space on each side of it
        stays, so the anchor holds two hyphens in a row."""
        self.write(
            "spaced.md",
            "# On the wake — one response per outcome\n\n"
            "## The prompt: checklist + completion contract\n\n"
            "[the wake](#on-the-wake--one-response-per-outcome)\n"
            "[the prompt](#the-prompt-checklist--completion-contract)\n",
        )

        self.assertEqual(self.reported_in("spaced.md"), [])

        # One hyphen for those two spaces is a failure. That is what makes the
        # line above a check on the rule rather than on a loose match.
        self.write(
            "collapsed.md",
            "# On the wake — one response per outcome\n\n"
            "[the wake](#on-the-wake-one-response-per-outcome)\n",
        )
        self.assertEqual(len(self.reported_in("collapsed.md")), 1)

    # --- the real repo ------------------------------------------------------

    def test_no_link_in_this_repo_dangles(self):
        """The whole tree, both classes. The message says which class broke."""
        self.assert_resolves(REPO_ROOT)

    def test_the_internal_anchors_in_the_orchestrator_skill_all_resolve(self):
        """The trap a whitespace-collapsing checker falls into. The file holds 16
        distinct internal anchors today, and four of them carry two hyphens in a
        row. The test asserts that every one resolves, so a new link is covered
        with no edit here."""
        skill = REPO_ROOT / "orchestrator" / "SKILL.md"
        internal = {
            raw
            for _, line in body_lines(skill.read_text(encoding="utf-8"))
            for raw in LINK.findall(line)
            if raw.startswith("#")
        }
        doubled = {raw for raw in internal if "--" in raw}

        self.assertGreaterEqual(len(internal), 16, sorted(internal))
        self.assertGreaterEqual(len(doubled), 4, sorted(doubled))
        self.assertEqual(
            [message for message in self.reported(REPO_ROOT) if "SKILL.md" in message],
            [],
        )


if __name__ == "__main__":
    unittest.main()
