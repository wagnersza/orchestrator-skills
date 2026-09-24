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

The same file holds a second walk, over the ADR ledger. `CLAUDE.md` asks for a new
ADR whenever a decision reverses or narrows an earlier one, and it asks the older
file for one pointer forward. That was prose, so half of it held: the new ADR
existed every time, and the old file stayed silent. A reader then read a retired
decision as current policy. `orchestrator/docs/adr/README.md` is the ledger, with
one row per number, and `ledger_failures` reports every place the ledger and the
files disagree. It reports in both directions: a declared edge with no pointer
behind it, and a pointer with no row in front of it. It also reads the bodies, so
an ADR that states a reversal and skips the ledger fails the suite.

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
# `.orchestrator` is one worker's own scaffolding, and it is gitignored: the brief and
# the checklist a spawn writes there hold links to the tracker, not to this repo.
SKIP_DIRS = {".git", ".orchestrator", ".pytest_cache", "node_modules"}

# An external target needs a request to check, and this suite makes none.
SKIP_SCHEMES = ("http://", "https://", "mailto:")

# The target half of an inline link: `[text](target)`.
LINK = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)")

# A fence opens and closes a code block. Three or more of one character, and the
# closing run is at least as long as the opening one. Group 2 is what follows the
# run: an info string on the opening fence, and nothing on the closing one.
FENCE = re.compile(r"^ *(`{3,}|~{3,})(.*)$")

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

    A closing fence carries no info string. So ```` ```js ```` inside a block opens
    no second block and closes no first one, and a nested example stays inside its
    outer block.
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
        elif (
            marker.startswith(fence[0])
            and len(marker) >= len(fence)
            and not found.group(2).strip()
        ):
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


# --- the ADR ledger ---------------------------------------------------------

# The ledger, and the decision records it indexes.
ADR_DIR = Path("orchestrator") / "docs" / "adr"
LEDGER = "README.md"

# `0045-a-story-start-is-automatic-under-two-roofs.md`, and the number it carries.
ADR_NAME = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")

# A ledger row opens with its number, as a link where a file carries that number.
ROW = re.compile(r"^\| *\[?(\d{4})\b")

# A number no file carries says so in its subject cell.
VOID_ROW = re.compile(r"^\| *\d{4} *\| *Void\b")

# The target half of a link to another decision record, from inside their directory.
ADR_TARGET = re.compile(r"\((\d{4})-[a-z0-9-]+\.md\)")

# One decision record, in the three forms these files use to name each other.
NAMED = r"(?:\[ADR (\d{4})\]|ADR (\d{4})\b|`(\d{4})-[a-z0-9-]+\.md`)"

# A claim in the body of a decision record: the verb, then the record it acts on.
# Bold markers and one short qualifier can stand between the two, and nothing else
# can. So `It narrows **[ADR 0026](...)**` is a claim, and so is `reverses one
# decision of ADR 0005`. `It narrows nothing in `0054-...`` is no claim, because
# `nothing in` is no qualifier. The rule is tight on purpose. It reads the sentence
# shape these files already use and it parses no English past it, so it reports no
# claim that a reader would not read as one. A claim it misses still needs its row,
# and the row is what the pointer walk reads.
CLAIM = re.compile(
    r"(?:supersedes|narrows|reverses)\*{0,2} *"
    r"(?:\*{0,2} *(?:one decision of|one paragraph of|part of|again"
    r"|the [a-z][a-z -]{0,30} of) *)?"
    r"\*{0,2} *" + NAMED
)

# `and ADR 0008`, so one sentence can name a second record.
CLAIM_MORE = re.compile(r"^ *,? *and +" + NAMED)


def adr_files(root):
    """Every decision record under the ADR directory, keyed by its number."""
    found = {}
    for path in sorted((Path(root) / ADR_DIR).glob("*.md")):
        number = ADR_NAME.match(path.name)
        if number:
            found[number.group(1)] = path
    return found


def prose(path):
    """The body of one Markdown file, with every fenced code block dropped."""
    return "\n".join(line for _, line in body_lines(path.read_text(encoding="utf-8")))


def preamble(path):
    """The part of one decision record above its first `##` heading.

    A pointer forward lives here, so a reader who opens the file meets it before the
    decision. Everything under the first heading is the decision itself, and no walk
    in this file reads a pointer out of it.
    """
    lines = []
    for line in prose(path).splitlines():
        if line.startswith("## "):
            break
        lines.append(line)
    return "\n".join(lines)


def ledger_rows(path):
    """The ledger as `{number: (void, [numbers it declares changed that number])}`."""
    rows = {}
    for line in prose(path).splitlines():
        found = ROW.match(line)
        if found:
            cells = line.split("|")
            rows[found.group(1)] = (
                VOID_ROW.match(line) is not None,
                ADR_TARGET.findall(cells[3]) if len(cells) > 3 else [],
            )
    return rows


def claims(path, number):
    """Every earlier decision record the body of `path` claims that it changes."""
    text = prose(path)
    found: set[str] = set()
    for claim in CLAIM.finditer(text):
        named = [n for n in claim.groups() if n]
        rest = text[claim.end() :]
        while True:
            more = CLAIM_MORE.match(rest)
            if not more:
                break
            named += [n for n in more.groups() if n]
            rest = rest[more.end() :]
        found.update(n for n in named if n < number)
    return found


def row_failures(files, rows):
    """Every number between the first record and the last that the ledger misreads.

    A number a file carries needs a subject. A number no file carries needs a void
    note, so a gap in the sequence reads as void and never as a deleted file.
    """
    failures = []
    for count in range(1, int(max(files)) + 1):
        number = f"{count:04d}"
        if number not in rows:
            failures.append(
                ("missing row", f"the ledger holds no row for ADR {number}")
            )
        elif rows[number][0] and number in files:
            failures.append(
                (
                    "wrong row",
                    f"the ledger calls ADR {number} void, and "
                    f"{files[number].name} carries that number",
                )
            )
        elif not rows[number][0] and number not in files:
            failures.append(
                (
                    "wrong row",
                    f"the ledger gives ADR {number} a subject, and no file "
                    f"carries that number",
                )
            )
    return failures


def pointer_failures(files, rows):
    """Both directions of one edge: the row in front of it, the pointer behind it."""
    failures = []
    for number, path in sorted(files.items()):
        declared = set(rows.get(number, (False, []))[1])
        pointed = {n for n in ADR_TARGET.findall(preamble(path)) if n > number}
        for newer in sorted(declared - pointed):
            failures.append(
                (
                    "missing pointer",
                    f"the ledger says ADR {newer} changed ADR {number}, and "
                    f"{path.name} names no ADR {newer} above its first heading",
                )
            )
        for newer in sorted(pointed - declared):
            failures.append(
                (
                    "stray pointer",
                    f"{path.name} points forward at ADR {newer}, and the ledger "
                    f"declares no such edge",
                )
            )
    return failures


def claim_failures(files, rows):
    """Every body that states a reversal the ledger does not carry."""
    failures = []
    for number, path in sorted(files.items()):
        for older in sorted(claims(path, number)):
            if number not in set(rows.get(older, (False, []))[1]):
                failures.append(
                    (
                        "unledgered claim",
                        f"{path.name} says it changes ADR {older}, and the ledger "
                        f"declares no such edge",
                    )
                )
    return failures


def ledger_failures(root):
    """Return every place the ADR ledger and the records it indexes disagree.

    Each item is a `(kind, message)` pair, the shape `scan` returns. Five kinds:

    - `missing row`, a number with no row in the ledger.
    - `wrong row`, a row that calls a number void where a file carries it, or a row
      with a subject where no file does.
    - `missing pointer`, an edge the ledger declares where the older record does not
      name the newer one above its first heading.
    - `stray pointer`, a pointer forward that the ledger declares no edge for.
    - `unledgered claim`, a body that says it changes an earlier record where the
      ledger declares no edge for it.
    """
    root = Path(root).resolve()
    ledger = root / ADR_DIR / LEDGER
    if not ledger.is_file():
        return [("missing ledger", f"no ADR ledger is at {ADR_DIR / LEDGER}")]

    files = adr_files(root)
    if not files:
        return [("missing records", f"no decision record is under {ADR_DIR}")]

    rows = ledger_rows(ledger)
    return (
        row_failures(files, rows)
        + pointer_failures(files, rows)
        + claim_failures(files, rows)
    )


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

    def assert_resolves(self, root):
        """Fail once, with every link that does not resolve in the message."""
        failures = [f"{found}: {message}" for found, message in scan(root)]
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

    def test_a_line_with_an_info_string_closes_no_fence(self):
        """A closing fence carries no info string, so a nested example inside a
        block of the same width leaves the block open. Without this rule the lines
        after the inner example read as prose, and their links read as
        cross-references."""
        self.write(
            "info.md",
            "```markdown\n```js\n[example output](no-such-file.md)\n```\n",
        )

        self.assertEqual(self.reported_in("info.md"), [])

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
        """The trap a whitespace-collapsing checker falls into. The file holds 3
        distinct internal anchors today, since the wave-5 rewrite moved most of the
        body into reference files, and one of them still carries two hyphens in a
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

        self.assertGreaterEqual(len(internal), 3, sorted(internal))
        self.assertGreaterEqual(len(doubled), 1, sorted(doubled))
        self.assertEqual(
            [message for message in self.reported(REPO_ROOT) if "SKILL.md" in message],
            [],
        )


class AdrLedgerTestCase(unittest.TestCase):
    """Four decision records and a ledger, in a temporary directory.

    ADR 0001 is changed by two later records and points at both. ADR 0002 is changed
    by ADR 0005 and points at it. ADR 0003 is void. So the fixture holds one record
    with two edges, one gap, and a record with no edge at all, and every test below
    breaks exactly one of those.
    """

    LEDGER = (
        "# The ADR ledger\n\n"
        "| ADR | Subject | Changed by |\n"
        "| --- | --- | --- |\n"
        "| [0001](0001-first.md) | The first one | narrowed by [0004](0004-fourth.md)"
        ", reversed by [0005](0005-fifth.md) |\n"
        "| [0002](0002-second.md) | The second one | narrowed by [0005](0005-fifth.md) |\n"
        "| 0003 | Void. Never used, and no file ever carried this number. | |\n"
        "| [0004](0004-fourth.md) | The fourth one | — |\n"
        "| [0005](0005-fifth.md) | The fifth one | — |\n"
    )

    RECORDS = {
        "0001-first.md": "# The first one\n\n"
        "> Narrowed by [ADR 0004](0004-fourth.md). The gate stands.\n"
        ">\n"
        "> Reversed by [ADR 0005](0005-fifth.md). The signal stands.\n\n"
        "## The decision\n\nA rule.\n",
        "0002-second.md": "# The second one\n\n"
        "> Narrowed by [ADR 0005](0005-fifth.md). The split stands.\n\n"
        "## The decision\n\nA rule.\n",
        "0004-fourth.md": "# The fourth one\n\n"
        "It narrows [ADR 0001](0001-first.md) on one point.\n",
        "0005-fifth.md": "# The fifth one\n\n"
        "This ADR reverses one decision of ADR 0001.\n"
        "It narrows `0002-second.md` in scope.\n"
        "It narrows nothing in `0004-fourth.md`.\n",
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        self.write(LEDGER, self.LEDGER)
        for name, text in self.RECORDS.items():
            self.write(name, text)

    # --- helpers ------------------------------------------------------------

    def write(self, name, text):
        path = self.root / ADR_DIR / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def reported(self, root=None, kind=None):
        return [
            message
            for found, message in ledger_failures(root or self.root)
            if kind is None or found == kind
        ]

    # --- the fixture as written --------------------------------------------

    def test_a_ledger_that_agrees_with_every_record_reports_nothing(self):
        """No test below can pass by accident, because this one holds first."""
        self.assertEqual(self.reported(), [])

    # --- the five failure classes, one test each ----------------------------

    def test_a_declared_edge_with_no_pointer_on_the_older_record_is_reported(self):
        """The class this walk exists for. ADR 0001 loses one of its two pointers,
        and the ledger still declares both edges."""
        self.write(
            "0001-first.md",
            "# The first one\n\n"
            "> Narrowed by [ADR 0004](0004-fourth.md). The gate stands.\n\n"
            "## The decision\n\nA rule.\n",
        )
        reported = self.reported(kind="missing pointer")

        self.assertEqual(len(reported), 1, reported)
        self.assertIn("ADR 0005 changed ADR 0001", reported[0])
        self.assertIn("0001-first.md", reported[0])

    def test_a_pointer_below_the_first_heading_does_not_count(self):
        """A reader who opens a retired record must meet the pointer before the
        decision. So a pointer under a heading is no pointer."""
        self.write(
            "0002-second.md",
            "# The second one\n\n## The decision\n\n"
            "> Narrowed by [ADR 0005](0005-fifth.md). The split stands.\n",
        )

        self.assertEqual(len(self.reported(kind="missing pointer")), 1)

    def test_a_pointer_the_ledger_does_not_declare_is_reported(self):
        """The other direction. ADR 0004 points forward at ADR 0005, and the ledger
        holds no edge for it."""
        self.write(
            "0004-fourth.md",
            "# The fourth one\n\n"
            "> Narrowed by [ADR 0005](0005-fifth.md). Something stands.\n\n"
            "It narrows [ADR 0001](0001-first.md) on one point.\n",
        )
        reported = self.reported(kind="stray pointer")

        self.assertEqual(len(reported), 1, reported)
        self.assertIn("0004-fourth.md points forward at ADR 0005", reported[0])

    def test_a_body_that_states_a_reversal_the_ledger_misses_is_reported(self):
        """A new record that reverses an old one and skips the ledger. This is what
        stops the ledger going stale the next time somebody writes an ADR."""
        self.write(
            "0005-fifth.md",
            "# The fifth one\n\nThis ADR reverses ADR 0004 in full.\n",
        )
        reported = self.reported(kind="unledgered claim")

        self.assertIn("0005-fifth.md says it changes ADR 0004", reported[0])

    def test_a_number_with_no_row_is_reported_and_so_is_a_wrong_row(self):
        """Both halves of the row check. A record with no row, then a void note on a
        number a file carries."""
        self.write(
            LEDGER,
            self.LEDGER.replace(
                "| [0004](0004-fourth.md) | The fourth one | — |\n", ""
            ),
        )
        self.assertEqual(len(self.reported(kind="missing row")), 1)

        self.write(
            LEDGER,
            self.LEDGER.replace(
                "| [0004](0004-fourth.md) | The fourth one | — |",
                "| 0004 | Void. Never used. | |",
            ),
        )
        reported = self.reported(kind="wrong row")
        self.assertEqual(len(reported), 1, reported)
        self.assertIn("calls ADR 0004 void", reported[0])

    def test_a_gap_with_no_row_at_all_is_reported(self):
        """A gap with no row at all reads as a deleted file, so it is reported."""
        self.write(
            LEDGER,
            self.LEDGER.replace(
                "| 0003 | Void. Never used, and no file ever carried this number. | |\n",
                "",
            ),
        )
        reported = self.reported(kind="missing row")

        self.assertEqual(len(reported), 1, reported)
        self.assertIn("ADR 0003", reported[0])

    # --- what the claim reader does not read as a claim ----------------------

    def test_a_sentence_that_denies_a_change_is_no_claim(self):
        """`It narrows nothing in` is in the fixture already, and the walk stays
        quiet on it. A record that claimed every ADR it mentions would ask for a
        pointer on every one, and the ledger would then say the opposite of the
        files."""
        self.write(
            "0005-fifth.md",
            "# The fifth one\n\n"
            "It narrows nothing in `0004-fourth.md`.\n"
            "It supersedes no part of [ADR 0004](0004-fourth.md).\n"
            "This narrows no earlier decision.\n",
        )

        self.assertEqual(self.reported(kind="unledgered claim"), [])

    def test_a_claim_inside_a_fenced_code_block_is_no_claim(self):
        """Example output, the same rule the link walk follows."""
        self.write(
            "0005-fifth.md",
            "# The fifth one\n\n```markdown\nIt supersedes ADR 0004 in full.\n```\n",
        )

        self.assertEqual(self.reported(kind="unledgered claim"), [])

    def test_a_claim_sentence_that_names_two_records_reports_both(self):
        """`This supersedes ADR 0007 and ADR 0008` is how one real record words it."""
        self.write(
            "0005-fifth.md",
            "# The fifth one\n\nThis supersedes ADR 0003 and ADR 0004.\n",
        )
        reported = self.reported(kind="unledgered claim")

        self.assertEqual(len(reported), 2, reported)
        self.assertIn("ADR 0003", reported[0])
        self.assertIn("ADR 0004", reported[1])

    # --- the real repo ------------------------------------------------------

    def test_the_adr_ledger_and_every_record_in_this_repo_agree(self):
        """The whole ledger, all five classes. The message says which class broke.

        A pass here is the invariant `CLAUDE.md` states: a decision that reverses or
        narrows an earlier one gets a new ADR, and the older file points forward at
        it.
        """
        failures = [
            f"{found}: {message}" for found, message in ledger_failures(REPO_ROOT)
        ]
        if failures:
            self.fail("\n".join([f"{len(failures)} ledger facts disagree:", *failures]))


if __name__ == "__main__":
    unittest.main()
