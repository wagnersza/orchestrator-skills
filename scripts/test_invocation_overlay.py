"""Tests for the invocation overlay. Stdlib only: `python3 -m unittest`."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.invocation_overlay import (
    plan,
    strip_frontmatter_flag,
    strip_policy_block,
)

SKILL_WITH_FLAG = """---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user.
"""

YAML_WITH_POLICY = """interface:
  display_name: "Implement"
  short_description: "Build work from a spec or tickets"
policy:
  allow_implicit_invocation: false
"""


def scaffold(root, skills):
    """A fork clone holding `skills` — {relpath: (skill_md, openai_yaml_or_None)}."""
    manifest = root / ".claude-plugin"
    manifest.mkdir(parents=True)
    (manifest / "plugin.json").write_text(json.dumps({"skills": list(skills)}))
    for rel, (skill_md, yaml) in skills.items():
        directory = root / rel
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(skill_md)
        if yaml is not None:
            (directory / "agents").mkdir()
            (directory / "agents" / "openai.yaml").write_text(yaml)
    return root


class TestStripping(unittest.TestCase):
    def test_the_flag_line_goes_and_nothing_else_does(self):
        out = strip_frontmatter_flag(SKILL_WITH_FLAG)
        self.assertNotIn("disable-model-invocation", out)
        self.assertIn("name: implement", out)
        self.assertIn("Implement the work described by the user.", out)
        self.assertEqual(
            len(out.splitlines()), len(SKILL_WITH_FLAG.splitlines()) - 1
        )

    def test_a_skill_with_no_flag_is_a_no_op(self):
        """So a re-run after a promote changes nothing it already changed."""
        self.assertIsNone(strip_frontmatter_flag("---\nname: tdd\n---\n\nBody.\n"))

    def test_the_policy_block_goes_and_interface_stays(self):
        out = strip_policy_block(YAML_WITH_POLICY)
        self.assertNotIn("policy:", out)
        self.assertNotIn("allow_implicit_invocation", out)
        self.assertIn('display_name: "Implement"', out)
        self.assertIn('short_description: "Build work from a spec or tickets"', out)

    def test_a_policy_holding_other_keys_is_left_alone(self):
        """Upstream may grow policy fields unrelated to invocation — don't guess."""
        text = YAML_WITH_POLICY + "  some_other_policy: true\n"
        self.assertIsNone(strip_policy_block(text))


class TestPlan(unittest.TestCase):
    def test_only_manifest_registered_skills_are_touched(self):
        """An in-progress skill loads in no session, so stripping it is diff for nothing."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scaffold(
                root,
                {
                    "./skills/engineering/implement": (
                        SKILL_WITH_FLAG,
                        YAML_WITH_POLICY,
                    )
                },
            )
            unregistered = root / "skills" / "in-progress" / "wizard"
            unregistered.mkdir(parents=True)
            (unregistered / "SKILL.md").write_text(SKILL_WITH_FLAG)

            edits, skipped = plan(root)

            self.assertEqual(skipped, [])
            self.assertEqual(
                sorted(str(path.relative_to(root)) for path, _ in edits),
                [
                    "skills/engineering/implement/SKILL.md",
                    "skills/engineering/implement/agents/openai.yaml",
                ],
            )

    def test_a_clone_already_overlaid_plans_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = scaffold(
                Path(tmp),
                {"./skills/engineering/tdd": ("---\nname: tdd\n---\n", "interface: {}\n")},
            )
            self.assertEqual(plan(root), ([], []))

    def test_an_unownable_policy_block_is_reported_not_edited(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = scaffold(
                Path(tmp),
                {
                    "./skills/engineering/implement": (
                        "---\nname: implement\n---\n",
                        YAML_WITH_POLICY + "  some_other_policy: true\n",
                    )
                },
            )
            edits, skipped = plan(root)
            self.assertEqual(edits, [])
            self.assertEqual(
                [str(path.relative_to(root)) for path in skipped],
                ["skills/engineering/implement/agents/openai.yaml"],
            )


if __name__ == "__main__":
    unittest.main()
