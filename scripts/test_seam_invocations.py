#!/usr/bin/env python3
"""Behaviour tests for every seam invocation this plugin prints: the Markdown tree
in, the list of invocations that cannot run out.

`scripts/` sits at the **plugin root**, and that directory is never the working
directory of either caller. A session runs in a target repo checkout or in a worker
worktree. So `python3 -m scripts.worker_state` finds no module there, and the seam is
unreachable as documented. The sanctioned form carries the resolved plugin root
(`orchestrator/docs/adr/0034-the-seam-invocation-carries-a-resolved-plugin-root.md`).

Two halves, one question each.

The first half is the ban. Every Markdown file in the repo goes through it, and it
reports each line that prints `python3 -m scripts.<module>`. The module form is banned
whether or not a prefix makes it work, because one form stands everywhere and that form
is the file path. A `PYTHONPATH=` prefix is worse than useless here: `-m` puts the
working directory ahead of `PYTHONPATH` on the import path, so inside a checkout of
this plugin it runs the checkout's copy instead of the installed one. That is a command
that reports success and reads the wrong file.

The second half is the positive. The repo prints the sanctioned form at least once. So
the ban cannot be satisfied by deleting every invocation, which would leave a session
with no command to run.

**The walk reads fenced code blocks.** A command lives inside one, so a walk that skips
them reads no invocation at all. That is the opposite of `test_links.py`, where a link
inside a fence is example output. Each half has a test for that difference.

The walk holds no list of files, so a new Markdown file is covered the moment someone
writes it, with no edit here. It holds no exemption list either. Each failure names the
file that holds the line and the line number, and each test reports every failure it
found in one message.

**Two boundaries, and both are the pattern rather than an exemption.** A line that names
the form with a `<module>` placeholder is prose about the ban, not a command, so the
pattern needs a real module name. And the walk reads Markdown only. The two seam test
suites run the module form as a subprocess on purpose: they run from the repo root, where
it resolves, and they test the file in this checkout.

Fixtures are small Markdown files in a temporary directory. So each failure class has a
line behind it that really cannot run.

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

# The banned form: the `scripts` package reached as a module. Group 1 is the module.
MODULE_FORM = re.compile(r"python3\s+-m\s+scripts\.(\w+)")

# The sanctioned form: `python3` and a path under the resolved plugin root. The root is
# a placeholder in a skill body, the same way `<the path from op 2>` is.
PATH_FORM = "<plugin root>/scripts/"


def markdown_files(root):
    """Every Markdown file under `root`, minus the directories that hold no prose."""
    root = Path(root)
    for path in sorted(root.rglob("*.md")):
        if SKIP_DIRS.isdisjoint(path.relative_to(root).parts):
            yield path


def scan(root):
    """Return every line under `root` that prints an unreachable seam invocation.

    Each item names the file, the line number and the module the line reaches for,
    because those three are what a maintainer needs to fix it. Fenced code blocks are
    read rather than skipped: a command lives inside one.
    """
    root = Path(root).resolve()
    failures = []
    for path in markdown_files(root):
        try:
            where = str(path.relative_to(root))
        except ValueError:
            where = str(path)
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            for module in MODULE_FORM.findall(line):
                failures.append(
                    f"{where}:{number} runs scripts.{module} as a module, and "
                    f"`{PATH_FORM}{module}.py` is the form that resolves"
                )
    return failures


class SeamInvocationTestCase(unittest.TestCase):
    """Four small Markdown files in a temporary directory. The four cases are:

    - the bare module form, which fails everywhere but the plugin root
    - the module form behind a prefix that makes it run, which is still banned
    - the sanctioned path form
    - `python3 -m pytest scripts/`, which names a directory and not the package
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        self.write("bare.md", "```bash\npython3 -m scripts.worker_state ready\n```\n")
        self.write(
            "prefixed.md",
            "```bash\n"
            "PYTHONPATH=/a/root python3 -m scripts.worker_state ready\n"
            "cd /a/root && python3 -m scripts.close_item --help\n"
            "```\n",
        )
        self.write(
            "resolved.md",
            f"```bash\npython3 {PATH_FORM}worker_state.py ready\n```\n",
        )
        self.write("suite.md", "```bash\npython3 -m pytest scripts/ -q\n```\n")

    # --- helpers ------------------------------------------------------------

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def reported_in(self, name):
        """Every failure reported against one fixture file."""
        return [message for message in scan(self.root) if message.startswith(name)]

    # --- the ban ------------------------------------------------------------

    def test_a_bare_module_invocation_is_reported_with_its_file_and_line(self):
        """The defect itself. The message names the file, the line and the module,
        because those three are what a maintainer needs to fix it."""
        reported = self.reported_in("bare.md")

        self.assertEqual(len(reported), 1, reported)
        self.assertIn("bare.md:2", reported[0])
        self.assertIn("scripts.worker_state", reported[0])
        self.assertIn(f"{PATH_FORM}worker_state.py", reported[0])

    def test_a_prefix_that_makes_the_module_form_run_does_not_excuse_it(self):
        """Both working prefixes, one line each. `PYTHONPATH=` still reads a local
        `scripts/` first, and `cd` moves the working directory out from under every
        other argument. One form stands everywhere, and it is the path form."""
        reported = self.reported_in("prefixed.md")

        self.assertEqual(len(reported), 2, reported)
        self.assertIn("prefixed.md:2", reported[0])
        self.assertIn("prefixed.md:3", reported[1])
        self.assertIn("scripts.close_item", reported[1])

    def test_the_sanctioned_form_is_not_reported(self):
        """The fixture that must stay quiet, so the tests above pass on the form and
        not on the word `scripts`."""
        self.assertEqual(self.reported_in("resolved.md"), [])

    def test_running_the_suite_is_not_a_seam_invocation(self):
        """`python3 -m pytest scripts/ -q` names a directory to collect, not the
        package to import. Every module docstring in this directory prints it."""
        self.assertEqual(self.reported_in("suite.md"), [])

    def test_a_fenced_code_block_is_read_and_not_skipped(self):
        """A command lives inside a fence, so a walk that skips fences reports
        nothing. This is where the walk differs from `test_links.py`."""
        self.assertEqual(len(self.reported_in("bare.md")), 1)

        # The same line outside a fence is reported too, so the fence changed
        # nothing rather than the walk finding it by accident.
        self.write("prose.md", "Run `python3 -m scripts.worker_state ready` first.\n")
        self.assertEqual(len(self.reported_in("prose.md")), 1)

    def test_the_skipped_directories_hold_no_checked_line(self):
        """Machinery, not prose. A vendored copy of this plugin under one of them is
        invisible, and the walk reports the same file one level up."""
        for directory in sorted(SKIP_DIRS):
            self.write(f"{directory}/vendored.md", "python3 -m scripts.worker_state\n")

        for directory in sorted(SKIP_DIRS):
            self.assertEqual(self.reported_in(directory), [], directory)

    # --- the real repo ------------------------------------------------------

    def test_no_markdown_file_in_this_plugin_prints_an_unreachable_invocation(self):
        """The whole tree. The message names every line that has to change."""
        failures = scan(REPO_ROOT)

        if failures:
            self.fail(
                "\n".join(
                    [f"{len(failures)} seam invocations cannot run:", *failures]
                )
            )

    def test_the_walk_reaches_the_markdown_of_this_plugin(self):
        """A guard against a quiet pass. A walk that finds no file reports no failure,
        and the test above then passes on an empty tree."""
        found = list(markdown_files(REPO_ROOT))

        self.assertGreaterEqual(len(found), 40, len(found))
        self.assertIn(REPO_ROOT / "orchestrator" / "SKILL.md", found)

    def test_this_plugin_prints_the_sanctioned_form(self):
        """The positive half. The ban alone is satisfied by a repo that prints no
        invocation at all, which leaves a session with no command to run."""
        printing = [
            str(path.relative_to(REPO_ROOT))
            for path in markdown_files(REPO_ROOT)
            if PATH_FORM in path.read_text(encoding="utf-8")
        ]

        self.assertIn("orchestrator/SKILL.md", printing)


if __name__ == "__main__":
    unittest.main()
