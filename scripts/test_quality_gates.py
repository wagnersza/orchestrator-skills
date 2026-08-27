#!/usr/bin/env python3
"""Behaviour tests for the gate contract. Three parts, one question each.

The first part reads the gate matrices: three reference files in, the list of tools a
matrix promises and the requirements file does not declare out.

A matrix row that names a tool with no install path is a rule with no home. A worker
reads the row, runs the tool, and finds nothing on the machine. So the walk reads the
`Tool` column of every gate matrix in
`orchestrator/references/quality-gates.md` and in
`orchestrator/references/quality-gates-infra.md`, then reads every dependency name
`orchestrator/references/requirements.md` declares, and reports each tool that is
absent from the requirements file.

The application matrix and the infra matrix are two files under one rule. So the walk
runs over both, and each message names the file that holds the row.

A gate matrix is a table with a `Gate` column and a `Tool` column. The layer table in
the same file has neither, so `make quick` is a command and never a tool. That
distinction has its own test, because a walk that reads every table reports `make` as
an undeclared tool.

The second part reads the `gates:` block of
`orchestrator-setup/orchestrator.template.md`, and it asks three things. The block
holds every field the block owes. Every command key is non-empty, or the notes
document the blank as a drop rather than as a gap. And every threshold the block sets
carries the number the matrix states, because config is the source of truth for a
threshold and no number may stand twice with two values.

A blank threshold is no cap, so the walk skips it. That is how a key lands before the
language column that gives it a number.

The third part reads the one writer of the gate record. A gate script that appends the
line proves that a script the worker ran said the gate passed. The record hook reads the
exit code the harness reports, so a green line proves that a command exited zero.

The part runs each gate script in a stub directory, and it asserts that the run writes no
record file. It then drives `hooks/record.py` over that same directory, and it asserts
that the line is there. So the pair holds: the script writes nothing, and the hook writes
the record.

Each failure names the file that holds the row, the line, and the tool or the key.
Each test reports every failure it found in one message, so a maintainer fixes a batch
instead of one row per run.

Fixtures are small Markdown files in a temporary directory. So each failure class has
a matrix row or a config key behind it that really breaks the contract. The tests that
read the real files also guard against a quiet pass: a walk that finds no row reports
every field of the block as absent, which fails loudly.

    python3 -m pytest scripts/ -q
    python3 -m unittest discover -s scripts -q     # fallback, no pytest
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

MATRIX = REPO_ROOT / "orchestrator" / "references" / "quality-gates.md"
MATRIX_INFRA = REPO_ROOT / "orchestrator" / "references" / "quality-gates-infra.md"
REQUIREMENTS = REPO_ROOT / "orchestrator" / "references" / "requirements.md"
TEMPLATE = REPO_ROOT / "orchestrator-setup" / "orchestrator.template.md"

# The one writer of the gate record, and the four files that run a gate command: this
# repo's own pair, and the pair /orchestrator-setup writes for a target repo.
RECORD_HOOK = REPO_ROOT / "hooks" / "record.py"
CHECKS = REPO_ROOT / "scripts" / "checks.sh"
CHECKS_TEMPLATE = REPO_ROOT / "orchestrator-setup" / "templates" / "checks.sh.template"
MAKEFILE = REPO_ROOT / "Makefile"
MAKEFILE_TEMPLATE = REPO_ROOT / "orchestrator-setup" / "templates" / "Makefile.template"

# A gate script the third part runs. The template is a script of its own, so the same
# run answers the same question for a repo the setup skill wrote.
GATE_SCRIPTS = (CHECKS, CHECKS_TEMPLATE)

# Every file that runs a gate command. None of them may write the record.
GATE_RUNNERS = (CHECKS, CHECKS_TEMPLATE, MAKEFILE, MAKEFILE_TEMPLATE)

# A shell append to the gate record. Both gate scripts held one before the record hook
# took the record over.
APPEND = re.compile(r">>[^\n]*gates-")

# Each tool the two fast layers name, in either script. A stub exits 0, so a run reaches
# the end of the layer on a machine that has none of them installed.
STUB_TOOLS = ("ruff", "mypy", "python3", "coverage", "lint-imports", "gitleaks")

# What a stub holds. A gate step is a green command here, because the third part asks
# what the script wrote and never what the tool found.
STUB = "#!/bin/sh\nexit 0\n"

# The layers the third part runs. `deep` is out: its mutation step reads counts from a
# JSON file, so a stubbed runner writes nothing for it to read.
STUB_LAYERS = ("quick", "full")

# The work item the fixture worktree implements. The checklist file name carries it, and
# both the script and the hook read the number from there.
ITEM = "99"

# The `gates:` block the record hook matches a command against, in the shape the
# template writes.
GATE_CONFIG = """# Orchestrator config

```yaml
tool:     orca
harness:  claude
gates:
  profile: lite
  langs:   [python]
  quick:   "make quick"
  full:    "make full"
  deep:    ""
  story:   "/improve-codebase-architecture"
```
"""

# Every file that holds a gate matrix. An application Gate reads code and an infra Gate
# reads a plan, so the two matrices live in two files. The tool rule is one rule, so a
# later column joins this tuple and needs no other edit here.
MATRICES = (MATRIX, MATRIX_INFRA)

# What the `gates:` block owes, one tuple per mapping.
GATES_KEYS = (
    "profile",
    "langs",
    "quick",
    "full",
    "deep",
    "story",
    "thresholds",
    "infra",
)
COMMAND_KEYS = ("quick", "full", "deep", "story")
THRESHOLD_KEYS = ("complexity", "cognitive", "funlen", "coverage", "branch", "mutation")
INFRA_KEYS = ("plan_role", "policy_dir", "fixtures", "halt_on", "zero_changes")

# A row of a pipe table: `| a | b |`. Group 1 is everything between the outer pipes.
ROW = re.compile(r"^ *\|(.+)\| *$")

# The row under a header holds dashes, colons, pipes and spaces, and nothing else.
SEPARATOR = re.compile(r"^[\s|:-]+$")

# A backticked span, which is how both files write a tool name.
CODE = re.compile(r"`([^`]+)`")


def cells(line):
    """The cells of one table row, each one stripped of its outer spaces."""
    row = ROW.match(line)
    assert row, f"this line is not a table row: {line!r}"
    return [cell.strip() for cell in row.group(1).split("|")]


def tables(text):
    """Yield `(header, rows)` for each pipe table in `text`.

    `header` is a list of cells. `rows` holds one `(number, cells)` pair per row under
    the separator. A run of fewer than three rows, or a run with no separator under its
    first row, is no table.
    """

    def table(run):
        if len(run) >= 3 and SEPARATOR.match(run[1][1]):
            yield cells(run[0][1]), [(number, cells(line)) for number, line in run[2:]]

    run = []
    for number, line in enumerate(text.splitlines(), 1):
        if ROW.match(line):
            run.append((number, line))
            continue
        yield from table(run)
        run = []
    yield from table(run)


def column(header, name):
    """The index of the column with this heading, or `None` where there is none."""
    lowered = [cell.lower() for cell in header]
    return lowered.index(name) if name in lowered else None


def matrix_tools(text):
    """Yield `(number, tool)` for every tool a gate matrix row names.

    A cell can hold a command (`ruff format --check`) rather than a bare name, so the
    tool is the first word of the backticked span.
    """
    for header, rows in tables(text):
        gate, tool = column(header, "gate"), column(header, "tool")
        if gate is None or tool is None:
            continue
        for number, row in rows:
            if len(row) <= tool:
                continue
            for span in CODE.findall(row[tool]):
                first = span.split()
                if first:
                    yield number, first[0]


def declared(text):
    """Every dependency name a table in the requirements file declares.

    The name is the first cell of a row, minus the bold marks, the backticks and any
    parenthetical after it. So `**mattpocock-skills** (plugin)` declares
    `mattpocock-skills`.
    """
    names = set()
    for _, rows in tables(text):
        for _, row in rows:
            name = row[0].split("(")[0] if row else ""
            name = name.replace("*", "").replace("`", "").strip().lower()
            if name:
                names.add(name)
    return names


def undeclared(matrix_path, requirements_path):
    """Every tool the matrix names that the requirements file does not declare.

    Each item is one message. It names the file that holds the row, the line and the
    tool, because those three are what a maintainer needs to correct it.
    """
    known = declared(requirements_path.read_text(encoding="utf-8"))
    return [
        f"{matrix_path.name}:{number} names the tool `{tool}`, and "
        f"{requirements_path.name} declares no row for it"
        for number, tool in matrix_tools(matrix_path.read_text(encoding="utf-8"))
        if tool.lower() not in known
    ]


# The line that opens or closes a fenced block.
FENCE = re.compile(r"^ *```")

# A YAML mapping line: the indent, the key, and the rest of the line.
KEY = re.compile(r"^( *)([A-Za-z_][A-Za-z0-9_]*): ?(.*)$")

# A sentence that documents a blank command as a drop and not as a gap.
DROP_RULE = re.compile(r"blank[^.]*drop|drop[^.]*blank", re.IGNORECASE)

# The first whole number in a threshold cell. `85% of lines` states 85.
NUMBER = re.compile(r"\d+")


def fenced(text):
    """Yield `(number, line)` for each line inside the first fenced block."""
    inside = False
    for number, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            if inside:
                return
            inside = True
        elif inside:
            yield number, line


def prose(text):
    """The text under the first fenced block, which is where the notes live."""
    return text.partition("```")[2].partition("```")[2]


def scalar(rest):
    """The value of a YAML scalar, without its quotes and without its comment.

    A `#` inside quotes belongs to the value, so a quoted value is read first.
    """
    rest = rest.strip()
    if rest[:1] in ('"', "'"):
        end = rest.find(rest[0], 1)
        return rest[1:end] if end > 0 else rest[1:]
    return rest.split("#")[0].strip()


def mapping(text, name):
    """Yield `(number, key, value)` for each direct child of the `name:` key.

    The walk reads the first fenced block alone, so no sentence of the notes can look
    like a key. The children are the lines at the indent of the first child, and the
    mapping ends at the first key indented no deeper than `name:` itself.
    """
    lines = list(fenced(text))
    for index, (_, line) in enumerate(lines):
        match = KEY.match(line)
        if not match or match.group(2) != name:
            continue
        parent, child = len(match.group(1)), None
        for number, line in lines[index + 1 :]:
            match = KEY.match(line)
            if not match:
                continue
            indent = len(match.group(1))
            if indent <= parent:
                return
            child = indent if child is None else child
            if indent == child:
                yield number, match.group(2), scalar(match.group(3))
        return


def missing_keys(template_path):
    """Every key the `gates:` block owes and does not hold.

    This is also the guard against a quiet pass. A walk that reads no key at all
    reports every field of the block, so the two checks below cannot pass on nothing.
    """
    text = template_path.read_text(encoding="utf-8")
    reported = []
    for block, owed in (
        ("gates", GATES_KEYS),
        ("thresholds", THRESHOLD_KEYS),
        ("infra", INFRA_KEYS),
    ):
        held = {key for _, key, _ in mapping(text, block)}
        reported += [
            f"{template_path.name} holds no `{key}` under `{block}:`"
            for key in owed
            if key not in held
        ]
    return reported


def undocumented_drops(template_path):
    """Every command key that is blank and has no drop rule behind it.

    A blank command is a supported configuration: the layer's checklist box goes away
    before the orchestrator sends the checklist. It is a gap only where the notes
    never say so.
    """
    text = template_path.read_text(encoding="utf-8")
    documented = DROP_RULE.search(prose(text))
    return [
        f"{template_path.name}:{number} leaves the command `{key}` blank, and the "
        f"notes document no drop for it"
        for number, key, value in mapping(text, "gates")
        if key in COMMAND_KEYS and not value and not documented
    ]


def matrix_thresholds(text):
    """Yield `(number, gate, threshold)` for each gate matrix row."""
    for header, rows in tables(text):
        gate, hard = column(header, "gate"), column(header, "hard threshold")
        if gate is None or hard is None:
            continue
        for number, row in rows:
            if len(row) > hard:
                yield number, row[gate].lower(), row[hard]


def threshold_mismatches(template_path, matrix_path):
    """Every threshold that the matrix contradicts, or holds no row for.

    Config is the source of truth for a threshold, so a mismatch means the default in
    the matrix is stale. The message states both numbers, because a maintainer needs
    both to correct one. A blank threshold is no cap, so the walk skips it.

    A config key matches the matrix row whose Gate name starts with it, so the key
    `mutation` reads the row `mutation score`.
    """
    matrix = list(matrix_thresholds(matrix_path.read_text(encoding="utf-8")))
    reported = []
    for _, key, value in mapping(
        template_path.read_text(encoding="utf-8"), "thresholds"
    ):
        if not value:
            continue
        rows = [(number, cell) for number, gate, cell in matrix if gate.startswith(key)]
        if not rows:
            reported.append(
                f"{template_path.name} sets the threshold `{key}` to {value}, and "
                f"{matrix_path.name} holds no gate row for it"
            )
        for number, cell in rows:
            found = NUMBER.search(cell)
            if found and found.group() != value:
                reported.append(
                    f"{template_path.name} sets the threshold `{key}` to {value}, and "
                    f"{matrix_path.name}:{number} states {found.group()}"
                )
    return reported


class GateMatrixTestCase(unittest.TestCase):
    """Two small Markdown files in a temporary directory. The matrix holds a layer
    table and a gate matrix, and the requirements file declares one of the two tools
    the matrix names.
    """

    LAYER_TABLE = (
        "# Quality gates\n"
        "\n"
        "| Layer | Command | Budget | What it answers |\n"
        "|---|---|---|---|\n"
        "| 1 · static | `make quick` | under 1s | Is the code lint-clean? |\n"
        "\n"
    )

    GATE_MATRIX = (
        "| Gate | Hard threshold | Layer | Tool |\n"
        "|---|---|---|---|\n"
        "| lint | 0 findings | 1 | `ruff` |\n"
        "| types | 0 errors | 1 | `nosuchtool` |\n"
    )

    REQUIREMENTS_TEXT = (
        "# Requirements\n"
        "\n"
        "| Dep | Why | Check | Install |\n"
        "|-----|-----|-------|---------|\n"
        "| **ruff** | the lint gate | `command -v ruff` | `uv tool install ruff` |\n"
    )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        self.matrix = self.write(
            "quality-gates.md", self.LAYER_TABLE + self.GATE_MATRIX
        )
        self.requirements = self.write("requirements.md", self.REQUIREMENTS_TEXT)

    # --- helpers ------------------------------------------------------------

    def write(self, name, text):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def reported(self):
        return undeclared(self.matrix, self.requirements)

    # --- the failure class --------------------------------------------------

    def test_a_matrix_tool_with_no_requirements_row_is_reported(self):
        """One message, and it names the file, the line and the tool. The declared
        tool in the row above stays quiet, so the row is what fired and not the
        table."""
        reported = self.reported()

        self.assertEqual(len(reported), 1, reported)
        self.assertIn("quality-gates.md:10", reported[0])
        self.assertIn("nosuchtool", reported[0])
        self.assertIn("requirements.md declares no row for it", reported[0])

    def test_a_tool_that_gains_a_requirements_row_stops_being_reported(self):
        """The same matrix against a requirements file that declares both tools. So
        the test above reports a real gap and not the shape of the fixture."""
        self.write(
            "requirements.md",
            self.REQUIREMENTS_TEXT
            + "| **nosuchtool** | the types gate | `command -v nosuchtool` | (verify) |\n",
        )

        self.assertEqual(self.reported(), [])

    def test_a_tool_cell_that_holds_a_command_names_the_first_word(self):
        """`ruff format --check` promises `ruff`. A walk that reads the whole cell
        reports a tool no requirements row can ever declare."""
        self.write(
            "quality-gates.md",
            self.LAYER_TABLE + "| Gate | Hard threshold | Layer | Tool |\n"
            "|---|---|---|---|\n"
            "| format | 0 files to reformat | 1 | `ruff format --check` |\n",
        )

        self.assertEqual(self.reported(), [])

    # --- what the walk skips ------------------------------------------------

    def test_a_table_with_no_gate_column_names_no_tool(self):
        """The layer table holds commands. `make quick` is one, and the requirements
        file declares no `make` row, so a walk over every table reports it."""
        self.write("quality-gates.md", self.LAYER_TABLE)

        self.assertEqual(self.reported(), [])
        self.assertEqual(list(matrix_tools(self.LAYER_TABLE)), [])

    def test_the_message_names_the_matrix_file_that_holds_the_row(self):
        """Two matrix files under one rule, so the message names the file it read. A
        maintainer then knows which matrix to correct."""
        infra = self.write(
            "quality-gates-infra.md",
            "| Gate | Hard threshold | Layer | Tool |\n"
            "|---|---|---|---|\n"
            "| plan diff | exit code 0 | 3 | `nosuchtool` |\n",
        )

        reported = undeclared(infra, self.requirements)

        self.assertEqual(len(reported), 1, reported)
        self.assertIn("quality-gates-infra.md:3", reported[0])
        self.assertIn("nosuchtool", reported[0])

    # --- the real files -----------------------------------------------------

    def test_every_real_matrix_names_more_than_a_few_tools(self):
        """The guard against a quiet pass. A walk that finds no row reports no
        failure, so the test below would pass against an empty file."""
        for path in MATRICES:
            with self.subTest(matrix=path.name):
                tools = {
                    tool for _, tool in matrix_tools(path.read_text(encoding="utf-8"))
                }

                self.assertGreaterEqual(len(tools), 5, sorted(tools))
                self.assertNotIn("make", tools)

    def test_every_tool_in_every_real_matrix_has_a_requirements_row(self):
        """The whole point. The message names each tool a matrix promises and the
        requirements file does not declare, plus the file that holds the row."""
        reported = [
            message for path in MATRICES for message in undeclared(path, REQUIREMENTS)
        ]

        if reported:
            self.fail(
                "\n".join(
                    ["a matrix row names a tool with no install path:", *reported]
                )
            )


class GatesBlockTestCase(unittest.TestCase):
    """A small config template and a small gate matrix in a temporary directory. The
    template holds a whole `gates:` block, so each test below breaks one line of it and
    reads what the walk reports.
    """

    CONFIG = (
        "# Orchestrator config\n"
        "\n"
        "```yaml\n"
        'evidence:   "make deep green + real-data proof"\n'
        "gates:\n"
        "  profile: strict         # strict | lite\n"
        "  langs:   python\n"
        '  quick:   "make quick"\n'
        '  full:    "make full"\n'
        '  deep:    "make deep"\n'
        '  story:   "/improve-codebase-architecture"\n'
        "  thresholds:\n"
        "    complexity: 10\n"
        '    cognitive:  ""\n'
        '    funlen:     ""\n'
        "    coverage:   85\n"
        '    branch:     ""\n'
        "    mutation:   70\n"
        "  infra:\n"
        '    plan_role:    ""\n'
        '    policy_dir:   ""\n'
        '    fixtures:     ""\n'
        '    halt_on:      ""\n'
        '    zero_changes: ""\n'
        "```\n"
        "\n"
        "## Notes\n"
        "\n"
        "- A blank command field drops that layer's box from the checklist.\n"
    )

    DROP_LINE = "- A blank command field drops that layer's box from the checklist.\n"

    MATRIX_TEXT = (
        "| Gate | Hard threshold | Layer | Tool |\n"
        "|---|---|---|---|\n"
        "| complexity | 10 cyclomatic per function | 2 | `ruff` |\n"
        "| coverage | 85% of lines | 3 | `coverage` |\n"
        "| mutation score | 70% | 4 | `mutmut` |\n"
    )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        self.template = self.write("orchestrator.template.md", self.CONFIG)
        self.matrix = self.write("quality-gates.md", self.MATRIX_TEXT)

    # --- helpers ------------------------------------------------------------

    def write(self, name, text):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def edit(self, *replacements):
        """The template with one replacement per pair, and the path to it."""
        text = self.CONFIG
        for old, new in replacements:
            self.assertIn(old, text)
            text = text.replace(old, new)
        return self.write("orchestrator.template.md", text)

    # --- the baseline -------------------------------------------------------

    def test_the_fixture_template_breaks_no_rule(self):
        """Each test below changes one line. So what it reports is that line, and
        never the shape of the fixture."""
        self.assertEqual(missing_keys(self.template), [])
        self.assertEqual(undocumented_drops(self.template), [])
        self.assertEqual(threshold_mismatches(self.template, self.matrix), [])

    # --- the failure classes ------------------------------------------------

    def test_a_blank_command_with_no_drop_rule_is_reported(self):
        """One message, and it names the file, the line and the key."""
        reported = undocumented_drops(
            self.edit(('  deep:    "make deep"', '  deep:    ""'), (self.DROP_LINE, ""))
        )

        self.assertEqual(len(reported), 1, reported)
        self.assertIn("orchestrator.template.md:10", reported[0])
        self.assertIn("`deep`", reported[0])
        self.assertIn("notes document no drop for it", reported[0])

    def test_a_blank_command_the_notes_document_is_no_gap(self):
        """The same blank command, with the drop rule back in the notes. So the test
        above reports a missing rule and not a blank field. A blank command is a
        supported configuration."""
        blank = self.edit(('  deep:    "make deep"', '  deep:    ""'))

        self.assertEqual(undocumented_drops(blank), [])

    def test_a_command_key_the_block_drops_is_reported(self):
        """A key the block never states reads as no command at all, so the block owes
        it whatever the notes say."""
        reported = missing_keys(self.edit(('  deep:    "make deep"\n', "")))

        self.assertEqual(len(reported), 1, reported)
        self.assertIn("holds no `deep` under `gates:`", reported[0])

    def test_a_threshold_the_matrix_contradicts_is_reported(self):
        """Config wins by policy, so the message states both numbers and leaves the
        maintainer to correct one."""
        reported = threshold_mismatches(
            self.edit(("    coverage:   85", "    coverage:   90")), self.matrix
        )

        self.assertEqual(len(reported), 1, reported)
        self.assertIn("the threshold `coverage` to 90", reported[0])
        self.assertIn("quality-gates.md:4 states 85", reported[0])

    def test_a_threshold_with_no_matrix_row_is_reported(self):
        """A number in config that no gate row reads is a rule with no home."""
        reported = threshold_mismatches(
            self.edit(('    cognitive:  ""', "    cognitive:  12")), self.matrix
        )

        self.assertEqual(len(reported), 1, reported)
        self.assertIn("the threshold `cognitive` to 12", reported[0])
        self.assertIn("holds no gate row for it", reported[0])

    def test_a_blank_threshold_is_no_mismatch(self):
        """`cognitive` ships blank, and the matrix holds no row for it. A blank
        threshold is no cap, so the walk skips it and the test above fires on the
        number alone."""
        self.assertEqual(threshold_mismatches(self.template, self.matrix), [])

    # --- the real files -----------------------------------------------------

    def test_the_real_gates_block_holds_every_required_key(self):
        """This is also the guard against a quiet pass. A walk that reads no key
        reports every field of the block."""
        reported = missing_keys(TEMPLATE)

        if reported:
            self.fail("\n".join(["the gates: block owes a field:", *reported]))

    def test_the_real_notes_document_the_blank_command_as_a_drop(self):
        """A blank command is a supported configuration and not a gap, so the notes
        have to say so once."""
        self.assertTrue(DROP_RULE.search(prose(TEMPLATE.read_text(encoding="utf-8"))))

    def test_no_real_command_key_is_an_undocumented_drop(self):
        """Every command key in the real block is non-empty, or the notes document the
        blank as a drop."""
        self.assertEqual(undocumented_drops(TEMPLATE), [])

    def test_every_real_threshold_matches_the_matrix(self):
        """The whole point of the second part. No number stands twice with two
        values."""
        reported = threshold_mismatches(TEMPLATE, MATRIX)

        if reported:
            self.fail(
                "\n".join(["a threshold stands twice with two values:", *reported])
            )


class GateRecordWriterTestCase(unittest.TestCase):
    """A worktree in a temporary directory, a real gate run, and the record after it.

    The directory holds what a worker's worktree holds while it runs a gate: the config
    with the `gates:` block, and the checklist that names the item. So a script that
    appends the line has everything it needs. A run that writes no file wrote none
    because the script holds no append.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

        self.orchestrator = self.root / ".orchestrator"
        self.orchestrator.mkdir()
        self.checklist = self.orchestrator / f"checklist-{ITEM}.md"
        self.checklist.write_text("- [ ] go\n", encoding="utf-8")
        self.record = self.orchestrator / f"gates-{ITEM}.jsonl"

        config = self.root / "docs" / "agents" / "orchestrator.md"
        config.parent.mkdir(parents=True)
        config.write_text(GATE_CONFIG, encoding="utf-8")

        self.bin = self.root / "bin"
        self.bin.mkdir()
        for tool in STUB_TOOLS:
            stub = self.bin / tool
            stub.write_text(STUB, encoding="utf-8")
            stub.chmod(0o755)

    # --- the fixture ---------------------------------------------------------

    def run_gate(self, script, layer):
        """One layer of one gate script, with a stub for every tool it names."""
        proc = subprocess.run(
            ["sh", str(script), layer],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            },
        )
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        return proc

    def run_hook(self, command):
        """The record hook, driven through a real `PostToolUse` event."""
        event = {
            "session_id": "fixture",
            "cwd": str(self.root),
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "tool_response": {"stdout": "", "stderr": "", "interrupted": False},
        }
        proc = subprocess.run(
            [sys.executable, str(RECORD_HOOK)],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            cwd=str(self.root),
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)},
        )
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        return proc

    def records(self):
        """Every gate record file the fixture holds."""
        return sorted(self.orchestrator.glob("gates-*.jsonl"))

    # --- the one writer -------------------------------------------------------

    def test_a_gate_run_writes_no_record(self):
        """The gate command runs and it exits. A file here is a second writer."""
        for script in GATE_SCRIPTS:
            for layer in STUB_LAYERS:
                with self.subTest(script=script.name, layer=layer):
                    self.run_gate(script, layer)

                    self.assertEqual(
                        self.records(), [], f"{script.name} wrote a record"
                    )

    def test_the_record_hook_writes_the_line_after_a_gate_run(self):
        """The pair, in the order a worker meets it. The script runs the layer, and the
        hook appends the line the watch reads."""
        self.run_gate(CHECKS, "quick")
        self.run_hook("make quick")

        self.assertEqual(self.records(), [self.record])
        lines = self.record.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1, lines)
        held = json.loads(lines[0])
        self.assertEqual(held["command"], "make quick")
        self.assertEqual(held["exit"], 0)
        self.assertEqual(sorted(held), ["command", "exit", "head_sha", "utc"])

    def test_no_gate_runner_appends_to_the_record(self):
        """The source of every file that runs a gate command. The stubbed run proves the
        two scripts write nothing, and this test reaches the two Makefiles too."""
        self.assertTrue(APPEND.search('>>"$GATE_DIR/gates-99.jsonl"'), "the guard")

        reported = [
            path.name
            for path in GATE_RUNNERS
            if APPEND.search(path.read_text(encoding="utf-8"))
        ]

        if reported:
            self.fail("\n".join(["a gate runner appends to the record:", *reported]))

    def test_the_record_hook_is_the_one_writer(self):
        """The hook holds the append the scripts lost. A pass with no append in the hook
        reads as a repo where nothing writes the record at all."""
        self.assertTrue(
            re.search(r"""open\(["']a["']""", RECORD_HOOK.read_text(encoding="utf-8")),
            "hooks/record.py opens the record in append mode",
        )


if __name__ == "__main__":
    unittest.main()
