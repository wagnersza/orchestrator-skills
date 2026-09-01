#!/usr/bin/env python3
"""Behaviour tests for the worker prompt template: four inputs in, one rendered
prompt out.

A prompt a model wrote by hand had no check on it. A model that held too much could
drop the acceptance criteria, or the scope edges, or the invocation of the routed
skill, and nothing said so. This suite is the check that replaces it.

`orchestrator/references/prompt.template.md` takes four inputs and no more: the
**Work item**, the **Checklist**, the gate commands of **Config**, and the routed
skill. `INPUTS` below names them, one key each, so a fifth input cannot be added to
the template without a test failing.

Two render rules, one test each. A missing input raises `MissingInput`, because a
prompt with a field missing must never reach a worker. A blank value drops the line
that holds it, because a **Layer** whose command is blank in **Config** is a
supported configuration.

`render` is a fixture, not a seam. `scripts/spawn_item.py` is the caller of the
template, and it does not exist yet. So the two render rules live here as prose in
the template and as code in this file, and the caller implements them again against
this suite. A renderer that this file imported from the caller would test the caller
and not the template.

The fixture is one work item in memory. There is no network, no login and no agent
run.

    python3 -m pytest scripts/ -q
    python3 -m unittest discover -s scripts -q     # fallback, no pytest
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / "orchestrator" / "references" / "prompt.template.md"

# The render marker. One name per pair of braces, and nothing else is substituted.
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")

# The header of the template documents the inputs, so it holds a placeholder of its
# own. The render drops the whole comment, so the documentation never reaches a worker.
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

# The target half of an inline Markdown link: `[text](target)`.
LINK = re.compile(r"\[[^\]]*\]\(")

# The four inputs, and the placeholders each one fills. The keys are the inputs, so a
# fifth key here is a visible change and never an accident.
INPUTS = {
    "item": ("item_number", "item_title", "item_body"),
    "checklist": ("checklist",),
    "gates": ("gate_quick", "gate_full", "gate_deep"),
    "skill": ("skill",),
}

# One work item, small enough to read in the assertions below.
FIXTURE = {
    "item": {
        "item_number": "4242",
        "item_title": "The widget cache key carries the tenant",
        "item_body": (
            "## Acceptance criteria\n\n"
            "- [ ] the cache key carries the tenant\n\n"
            "## Touches\n\n"
            "- src/widget_cache.py\n"
        ),
    },
    "checklist": {"checklist": "- [ ] implement + self-test\n- [ ] push the branch"},
    "gates": {
        "gate_quick": "make quick",
        "gate_full": "make full",
        "gate_deep": "make deep",
    },
    "skill": {"skill": "/implement"},
}

# Every part of the completion contract the prompt carries, and the text that proves
# each one reached the render.
CONTRACT_PARTS = {
    "the acceptance criteria": "## Acceptance criteria",
    "the scope edges": "## Scope edges",
    "the Browser surface edge": "playwright-cli",
    "the Delegation cap": "At most 5 sub-agents",
    "the Commit slice rule": "## Commit in slices",
    "the writing pass in pragmatic mode": "**pragmatic** mode",
}


class MissingInput(Exception):
    """A placeholder the template holds that the caller passed no value for."""


def template_body(text):
    """`text` without the HTML comment header that documents it."""
    return COMMENT.sub("", text)


def render(text, inputs):
    """`text` with every placeholder replaced by its value.

    A placeholder with no value raises `MissingInput`. A placeholder whose value is
    blank drops the whole line that holds it.
    """
    values = {}
    for group in inputs.values():
        values.update(group)
    lines = []
    for line in template_body(text).splitlines():
        names = PLACEHOLDER.findall(line)
        missing = sorted(name for name in names if name not in values)
        if missing:
            raise MissingInput(", ".join(missing))
        if any(not values[name].strip() for name in names):
            continue
        lines.append(PLACEHOLDER.sub(lambda hit: values[hit.group(1)], line))
    return "\n".join(lines)


class PromptTemplateTest(unittest.TestCase):
    """The template on disk, rendered against the fixture work item."""

    def setUp(self):
        self.text = TEMPLATE.read_text(encoding="utf-8")

    def test_the_template_holds_the_four_inputs_and_no_fifth(self):
        expected = {name for group in INPUTS.values() for name in group}
        found = set(PLACEHOLDER.findall(template_body(self.text)))
        self.assertEqual(
            found,
            expected,
            "the template renders from exactly the four documented inputs",
        )

    def test_every_field_reaches_the_rendered_prompt(self):
        prompt = render(self.text, FIXTURE)
        for group in FIXTURE.values():
            for name, value in group.items():
                for line in value.splitlines():
                    with self.subTest(field=name, line=line):
                        self.assertIn(line, prompt)
        self.assertNotIn("{{", prompt, "no placeholder is left unrendered")

    def test_a_missing_input_is_an_error(self):
        for name in INPUTS:
            with self.subTest(missing=name):
                inputs = {key: value for key, value in FIXTURE.items() if key != name}
                with self.assertRaises(MissingInput):
                    render(self.text, inputs)

    def test_a_blank_gate_command_drops_its_line(self):
        inputs = dict(FIXTURE)
        inputs["gates"] = dict(FIXTURE["gates"], gate_deep="")
        prompt = render(self.text, inputs)
        self.assertNotIn("Layer 4", prompt)
        self.assertNotIn("make deep", prompt)
        self.assertIn("Layer 3", prompt)
        self.assertIn("make full", prompt)

    def test_the_routed_skill_is_a_literal_imperative(self):
        body = template_body(self.text)
        holders = [line for line in body.splitlines() if "{{skill}}" in line]
        self.assertEqual(holders, ["Run {{skill}}."], "one line, and it is a command")
        self.assertIn("Run /implement.", render(self.text, FIXTURE))

    def test_the_completion_contract_ships_whole(self):
        prompt = render(self.text, FIXTURE)
        for part, proof in CONTRACT_PARTS.items():
            with self.subTest(part=part):
                self.assertIn(proof, prompt)

    def test_the_rendered_prompt_carries_no_markdown_link(self):
        prompt = render(self.text, FIXTURE)
        self.assertIsNone(
            LINK.search(prompt),
            "a relative link resolves to nothing in the worker's own worktree",
        )


if __name__ == "__main__":
    unittest.main()
