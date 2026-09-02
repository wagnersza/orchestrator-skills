#!/usr/bin/env python3
"""Behaviour tests for the `models:` block contract. The two config files in, the
list of ways a block breaks the contract out.

A config that names only `heavy` and `light` today stays green, because no test
reads the `models:` block against the model registry. So a half-done rollout of
the three-Role change (`heavy` / `medium` / `light` / `review`) is invisible.
This walk reads the `models:` block of
`orchestrator-setup/orchestrator.template.md` and of
`docs/agents/orchestrator.md`. It then reads the model registry and the effort
ladder in `orchestrator/references/models.md`, and reports every mismatch.

`scripts/test_quality_gates.py` reads the `gates:` block and reports each field
the block owes. This is the same shape on a different block.
`scripts/test_links.py` shows the walk that starts at the repo root and holds
no list of files.

Six failure classes, one test method each:

1. A `models:` block that does not name all four Roles.
2. A model in a block that the registry table does not list.
3. An effort in a block that is not on the effort ladder.
4. A Role in a block that the Role table does not hold.
5. A Cost profile row that does not name a `model` @ `effort` pair for each of
   the three implementation Roles (`heavy`, `medium`, `light`).
6. Any Markdown file that still names `role_default`, the key that
   `docs/adr/0059-medium-is-the-default-role.md` records as deleted.

A `models:` block lives inside a fenced code block, same as a `gates:` block.
So the walk reads the first fenced block of a file and nothing outside it. A
dedicated test proves this: a `models:`-shaped mapping in plain prose, outside
any fence, is not a config block and is not read as one.

Each failure names the file that holds the fault, the line where it stands, and
the value that caused it. Each test reports every failure it found in one
message. Fixtures are small Markdown files in a temporary directory, so each
failure class has one behind it that really breaks the contract.

    python3 -m pytest scripts/ -q
    python3 -m unittest discover -s scripts -q     # fallback, no pytest
"""

import re
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

TEMPLATE = REPO_ROOT / "orchestrator-setup" / "orchestrator.template.md"
CONFIG = REPO_ROOT / "docs" / "agents" / "orchestrator.md"
MODELS_REF = REPO_ROOT / "orchestrator" / "references" / "models.md"

# The two files whose `models:` block must hold the contract.
TARGETS = (TEMPLATE, CONFIG)

# The four Roles a `models:` block owes. Three of them do the implementation work.
FOUR_ROLES = ("heavy", "medium", "light", "review")
IMPL_ROLES = ("heavy", "medium", "light")

# A directory of machinery, not of prose. None of it is this repo's Markdown.
SKIP_DIRS = {".git", ".pytest_cache", "node_modules"}

# The line that opens or closes a fenced block.
FENCE = re.compile(r"^ *```")

# A YAML mapping line: the indent, the key, and the rest of the line.
KEY = re.compile(r"^( *)([A-Za-z_][A-Za-z0-9_.-]*): ?(.*)$")

# A backticked span, which is how every table below writes a model, an effort or
# a Role name.
CODE = re.compile(r"`([^`]+)`")

# A row of a pipe table: `| a | b |`. Group 1 is everything between the outer pipes.
ROW = re.compile(r"^ *\|(.+)\| *$")

# The row under a header holds dashes, colons, pipes and spaces, and nothing else.
SEPARATOR = re.compile(r"^[\s|:-]+$")


# --- shared parsing (the same shape as scripts/test_quality_gates.py) -------


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


def scalar(rest):
    """The value of a YAML scalar, without its quotes and without its comment."""
    rest = rest.strip()
    if rest[:1] in ('"', "'"):
        end = rest.find(rest[0], 1)
        return rest[1:end] if end > 0 else rest[1:]
    return rest.split("#")[0].strip()


def parse_models_block(lines):
    """The `models:` mapping of a fenced block, or `None` where there is none.

    Each Role name maps to its own `line`, and its `model` and `effort` children
    as `(number, value)` pairs, or `None` where a child is absent. Reads only the
    lines the caller passes in, so a `models:`-shaped mapping outside a fence
    never reaches this function at all.
    """
    lines = list(lines)
    for index, (_, line) in enumerate(lines):
        match = KEY.match(line)
        if match and match.group(2) == "models":
            parent = len(match.group(1))
            break
    else:
        return None

    roles = {}
    role_indent = None
    child_indent = None
    current = None
    for number, line in lines[index + 1 :]:
        match = KEY.match(line)
        if not match:
            continue
        indent = len(match.group(1))
        if indent <= parent:
            break
        if role_indent is None:
            role_indent = indent
        if indent == role_indent:
            current = match.group(2)
            roles[current] = {"line": number, "model": None, "effort": None}
            child_indent = None
        elif current is not None and indent > role_indent:
            if child_indent is None:
                child_indent = indent
            if indent == child_indent and match.group(2) in ("model", "effort"):
                roles[current][match.group(2)] = (number, scalar(match.group(3)))
    return roles


def cells(line):
    """The cells of one table row, each one stripped of its outer spaces."""
    row = ROW.match(line)
    assert row, f"this line is not a table row: {line!r}"
    return [cell.strip() for cell in row.group(1).split("|")]


def tables(text):
    """Yield `(header, rows)` for each pipe table in `text`."""

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


def backticked_column(text, name):
    """Every backticked span in the column headed `name`, across every table."""
    found = []
    for header, rows in tables(text):
        index = column(header, name)
        if index is None:
            continue
        for _, row in rows:
            if len(row) > index:
                found.extend(CODE.findall(row[index]))
    return found


# --- the models.md registry -------------------------------------------------


def known_models(text):
    return set(backticked_column(text, "model"))


def known_efforts(text):
    return set(backticked_column(text, "effort"))


def known_roles(text):
    return set(backticked_column(text, "role"))


def cost_profile_rows(text):
    """Yield `(number, profile, {role: cell})` for each row of the Cost profiles
    table, one cell per implementation Role."""
    for header, rows in tables(text):
        role_cols = {role: column(header, role) for role in IMPL_ROLES}
        if any(index is None for index in role_cols.values()):
            continue
        profile_col = column(header, "profile")
        for number, row in rows:
            profile = row[profile_col] if profile_col is not None else ""
            yield (
                number,
                profile,
                {
                    role: (row[index] if len(row) > index else "")
                    for role, index in role_cols.items()
                },
            )


# --- the failure classes -----------------------------------------------------


def missing_roles(path):
    """Every Role that a `models:` block does not name."""
    roles = parse_models_block(fenced(path.read_text(encoding="utf-8")))
    if roles is None:
        return [f"{path.name} holds no `models:` block inside a fenced code block"]
    return [
        f"{path.name} names no `{role}` Role in its `models:` block"
        for role in FOUR_ROLES
        if role not in roles
    ]


def unknown_models(path, registry):
    """Every model a `models:` block names that the registry does not list."""
    roles = parse_models_block(fenced(path.read_text(encoding="utf-8"))) or {}
    return [
        f"{path.name}:{number} names the model `{value}` for the `{role}` Role, "
        f"and {MODELS_REF.name} lists no such model"
        for role, fields in roles.items()
        if fields["model"]
        for number, value in [fields["model"]]
        if value not in registry
    ]


def unknown_efforts(path, ladder):
    """Every effort a `models:` block names that is not on the effort ladder."""
    roles = parse_models_block(fenced(path.read_text(encoding="utf-8"))) or {}
    return [
        f"{path.name}:{number} names the effort `{value}` for the `{role}` Role, "
        f"and {MODELS_REF.name} holds no rung for it on the effort ladder"
        for role, fields in roles.items()
        if fields["effort"]
        for number, value in [fields["effort"]]
        if value not in ladder
    ]


def unlisted_roles(path, roles_table):
    """Every Role a `models:` block names that the Role table does not hold."""
    roles = parse_models_block(fenced(path.read_text(encoding="utf-8"))) or {}
    return [
        f"{path.name}:{fields['line']} names the Role `{role}` in its `models:` "
        f"block, and {MODELS_REF.name} holds no Role row for it"
        for role, fields in roles.items()
        if role not in roles_table
    ]


def cost_profile_gaps(path):
    """Every Cost profile row that does not name a pair for an implementation Role."""
    text = path.read_text(encoding="utf-8")
    return [
        f"{path.name}:{number} the `{profile}` Cost profile names no "
        f"`model` @ `effort` pair for the `{role}` Role"
        for number, profile, row in cost_profile_rows(text)
        for role, cell in row.items()
        if len(CODE.findall(cell)) < 2
    ]


ROLE_DEFAULT = re.compile(r"role_default")


def role_default_uses(root):
    """Every Markdown file that still names `role_default` inside a fenced block."""
    root = Path(root)
    failures = []
    for path in sorted(root.rglob("*.md")):
        if not SKIP_DIRS.isdisjoint(path.relative_to(root).parts):
            continue
        text = path.read_text(encoding="utf-8")
        for number, line in fenced(text):
            if ROLE_DEFAULT.search(line):
                failures.append(
                    f"{path.relative_to(root)}:{number} names `role_default` "
                    f"inside a fenced code block"
                )
    return failures


# --- fixtures ----------------------------------------------------------------


VALID_MODELS_BLOCK = (
    "# Orchestrator config\n"
    "\n"
    "```yaml\n"
    "models:\n"
    "  heavy:\n"
    "    model:  opus-5\n"
    "    effort: high\n"
    "  medium:\n"
    "    model:  sonnet-5\n"
    "    effort: medium\n"
    "  light:\n"
    "    model:  sonnet-5\n"
    "    effort: low\n"
    "  review:\n"
    "    model:  gpt-5.6-terra\n"
    "    effort: high\n"
    "```\n"
)

REGISTRY = set(("opus-5", "sonnet-5", "gpt-5.6-terra", "gpt-5.6-sol"))
LADDER = set(("max", "xhigh", "high", "medium", "low"))
ROLES_TABLE = set(FOUR_ROLES)


class ModelsBlockTestCase(unittest.TestCase):
    """One small Markdown file per test, holding a `models:` block that breaks
    exactly one rule of the contract."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write(self, text, name="orchestrator.template.md"):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    # --- the baseline --------------------------------------------------

    def test_the_valid_fixture_breaks_no_rule(self):
        path = self.write(VALID_MODELS_BLOCK)

        self.assertEqual(missing_roles(path), [])
        self.assertEqual(unknown_models(path, REGISTRY), [])
        self.assertEqual(unknown_efforts(path, LADDER), [])
        self.assertEqual(unlisted_roles(path, ROLES_TABLE), [])

    # --- the failure classes --------------------------------------------

    def test_a_block_with_a_missing_role_is_reported(self):
        """Today's real gap: a block that names only `heavy` and `light`."""
        path = self.write(
            "```yaml\n"
            "models:\n"
            "  heavy:\n"
            "    model:  opus-5\n"
            "    effort: high\n"
            "  light:\n"
            "    model:  sonnet-5\n"
            "    effort: low\n"
            "```\n"
        )

        reported = missing_roles(path)

        self.assertEqual(len(reported), 2, reported)
        self.assertIn("names no `medium` Role", reported[0])
        self.assertIn("names no `review` Role", reported[1])
        self.assertTrue(all(path.name in message for message in reported))

    def test_a_model_the_registry_does_not_list_is_reported(self):
        path = self.write(VALID_MODELS_BLOCK.replace("sonnet-5", "sonnet-4"))

        reported = unknown_models(path, REGISTRY)

        self.assertEqual(len(reported), 2, reported)
        self.assertIn("`sonnet-4`", reported[0])
        self.assertIn(path.name, reported[0])
        self.assertIn(MODELS_REF.name, reported[0])

    def test_an_effort_not_on_the_ladder_is_reported(self):
        path = self.write(VALID_MODELS_BLOCK.replace("effort: medium", "effort: mega"))

        reported = unknown_efforts(path, LADDER)

        self.assertEqual(len(reported), 1, reported)
        self.assertIn("`mega`", reported[0])
        self.assertIn(path.name, reported[0])

    def test_a_role_the_role_table_does_not_hold_is_reported(self):
        path = self.write(VALID_MODELS_BLOCK.replace("  heavy:", "  extreme:"))

        reported = unlisted_roles(path, ROLES_TABLE)

        self.assertEqual(len(reported), 1, reported)
        self.assertIn("`extreme`", reported[0])
        self.assertIn(path.name, reported[0])

        # The block is also missing `heavy` now, which is the other failure class.
        self.assertIn("heavy", " ".join(missing_roles(path)))

    # --- what the walk skips --------------------------------------------

    def test_a_models_mapping_outside_a_fence_is_not_read(self):
        """The dedicated proof that the walk reads a `models:` block only inside
        a fenced code block. The same shape in plain prose parses to nothing."""
        prose_only = self.write(
            "models:\n  heavy:\n    model:  opus-5\n    effort: high\n"
        )

        self.assertIsNone(
            parse_models_block(fenced(prose_only.read_text(encoding="utf-8")))
        )

        fenced_version = self.write(VALID_MODELS_BLOCK, name="fenced.md")
        text = fenced_version.read_text(encoding="utf-8")

        self.assertIsNotNone(parse_models_block(fenced(text)))


class CostProfileTestCase(unittest.TestCase):
    """One small Markdown file per test, holding a Cost profiles table."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write(self, text, name="models.md"):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    VALID_TABLE = (
        "| Profile | heavy | medium | light | review | Relative cost |\n"
        "|---|---|---|---|---|---|\n"
        "| **balanced** | `opus-5` @ `high` | `sonnet-5` @ `medium` | "
        "`sonnet-5` @ `low` | `gpt-5.6-terra` @ `high` | ~2-3x |\n"
    )

    def test_the_valid_fixture_breaks_no_rule(self):
        self.assertEqual(cost_profile_gaps(self.write(self.VALID_TABLE)), [])

    def test_a_row_missing_a_pair_for_an_implementation_role_is_reported(self):
        broken = self.VALID_TABLE.replace("`sonnet-5` @ `medium`", "sonnet-5")
        path = self.write(broken)

        reported = cost_profile_gaps(path)

        self.assertEqual(len(reported), 1, reported)
        self.assertIn("balanced", reported[0])
        self.assertIn("`medium`", reported[0])
        self.assertIn(path.name, reported[0])

    def test_a_table_with_no_role_columns_is_skipped(self):
        """A table that is not the Cost profiles table names no Role columns, so
        the walk over every table in the file reports nothing for it."""
        other = "| Model | Vendor |\n|---|---|\n| `opus-5` | anthropic |\n"

        self.assertEqual(cost_profile_gaps(self.write(other)), [])


class RoleDefaultTestCase(unittest.TestCase):
    """Two small Markdown files: a fenced config block that still names
    `role_default`, and prose that only talks about its deletion."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_live_config_key_is_reported(self):
        self.write(
            "orchestrator.md",
            "```yaml\nrole_default: light\n```\n",
        )

        reported = role_default_uses(self.root)

        self.assertEqual(len(reported), 1, reported)
        self.assertIn("orchestrator.md:2", reported[0])

    def test_prose_that_only_discusses_the_deletion_is_not_reported(self):
        """The real ADR mentions `role_default` in a backticked span, in prose,
        to explain that the key is gone. That mention sits outside any fence, so
        it must stay quiet."""
        self.write(
            "0059-medium-is-the-default-role.md",
            "`role_default` is deleted. The key existed to invert a default.\n",
        )

        self.assertEqual(role_default_uses(self.root), [])

    def test_the_skipped_directories_hold_no_checked_mention(self):
        self.write(".git/vendored.md", "```yaml\nrole_default: light\n```\n")

        self.assertEqual(role_default_uses(self.root), [])


class RealRepoTestCase(unittest.TestCase):
    """The real files. Each test reports every failure it found in one message,
    so a maintainer fixes a batch instead of one row per run."""

    def setUp(self):
        registry_text = MODELS_REF.read_text(encoding="utf-8")
        self.registry = known_models(registry_text)
        self.ladder = known_efforts(registry_text)
        self.roles_table = known_roles(registry_text)
        self.registry_text = registry_text

    def fail_on(self, reported, header):
        if reported:
            self.fail("\n".join([header, *reported]))

    def test_every_real_models_block_names_all_four_roles(self):
        self.fail_on(
            [message for path in TARGETS for message in missing_roles(path)],
            "a `models:` block does not name all four Roles:",
        )

    def test_every_real_model_is_in_the_registry(self):
        self.fail_on(
            [
                message
                for path in TARGETS
                for message in unknown_models(path, self.registry)
            ],
            "a `models:` block names a model the registry does not list:",
        )

    def test_every_real_effort_is_on_the_ladder(self):
        self.fail_on(
            [
                message
                for path in TARGETS
                for message in unknown_efforts(path, self.ladder)
            ],
            "a `models:` block names an effort that is not on the ladder:",
        )

    def test_every_real_role_is_in_the_role_table(self):
        self.fail_on(
            [
                message
                for path in TARGETS
                for message in unlisted_roles(path, self.roles_table)
            ],
            "a `models:` block names a Role the Role table does not hold:",
        )

    def test_the_real_role_table_holds_all_four_roles(self):
        """The guard against a quiet pass on the registry side too."""
        self.assertEqual(self.roles_table, ROLES_TABLE)

    def test_every_real_cost_profile_row_names_a_pair_for_each_implementation_role(
        self,
    ):
        self.fail_on(
            cost_profile_gaps(MODELS_REF),
            "a Cost profile row names no pair for an implementation Role:",
        )

    def test_no_real_markdown_file_still_names_role_default(self):
        self.fail_on(
            role_default_uses(REPO_ROOT),
            "a Markdown file still names `role_default` inside a fenced block:",
        )


if __name__ == "__main__":
    unittest.main()
