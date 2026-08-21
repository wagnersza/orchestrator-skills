#!/usr/bin/env python3
"""Behaviour tests for the gate matrix: two reference files in, the list of tools the
matrix promises and the requirements file does not declare out.

A matrix row that names a tool with no install path is a rule with no home. A worker
reads the row, runs the tool, and finds nothing on the machine. So the walk reads the
`Tool` column of every gate matrix in
`orchestrator/references/quality-gates.md`, then reads every dependency name
`orchestrator/references/requirements.md` declares, and reports each tool that is
absent from the second file.

A gate matrix is a table with a `Gate` column and a `Tool` column. The layer table in
the same file has neither, so `make quick` is a command and never a tool. That
distinction has its own test, because a walk that reads every table reports `make` as
an undeclared tool.

Each failure names the file that holds the row, the line, and the tool. Each test
reports every failure it found in one message, so a maintainer fixes a batch instead
of one row per run.

Fixtures are small Markdown files in a temporary directory. So each failure class has
a matrix row behind it that really promises nothing. Two tests read the real files, and
one of them asserts that the matrix names more than a few tools, so no test above
passes because the walk found nothing at all.

    python3 -m pytest scripts/ -q
    python3 -m unittest discover -s scripts -q     # fallback, no pytest
"""

import re
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

MATRIX = REPO_ROOT / "orchestrator" / "references" / "quality-gates.md"
REQUIREMENTS = REPO_ROOT / "orchestrator" / "references" / "requirements.md"

# A row of a pipe table: `| a | b |`. Group 1 is everything between the outer pipes.
ROW = re.compile(r"^ *\|(.+)\| *$")

# The row under a header holds dashes, colons, pipes and spaces, and nothing else.
SEPARATOR = re.compile(r"^[\s|:-]+$")

# A backticked span, which is how both files write a tool name.
CODE = re.compile(r"`([^`]+)`")


def cells(line):
    """The cells of one table row, each one stripped of its outer spaces."""
    return [cell.strip() for cell in ROW.match(line).group(1).split("|")]


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

        self.matrix = self.write("quality-gates.md", self.LAYER_TABLE + self.GATE_MATRIX)
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
            self.LAYER_TABLE
            + "| Gate | Hard threshold | Layer | Tool |\n"
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

    # --- the real files -----------------------------------------------------

    def test_the_real_matrix_names_more_than_a_few_tools(self):
        """The guard against a quiet pass. A walk that finds no row reports no
        failure, so the test below would pass against an empty file."""
        tools = {tool for _, tool in matrix_tools(MATRIX.read_text(encoding="utf-8"))}

        self.assertGreaterEqual(len(tools), 5, sorted(tools))
        self.assertNotIn("make", tools)

    def test_every_tool_in_the_real_matrix_has_a_requirements_row(self):
        """The whole point. The message names each tool the matrix promises and the
        requirements file does not declare."""
        reported = undeclared(MATRIX, REQUIREMENTS)

        if reported:
            self.fail(
                "\n".join(["a matrix row names a tool with no install path:", *reported])
            )


if __name__ == "__main__":
    unittest.main()
