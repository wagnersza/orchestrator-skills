"""The invocation overlay: make a fork's user-invoked skills model-invocable.

A skill a model cannot reach autonomously never runs in an unattended worker, and
the orchestrator's workers are unattended by definition. Upstream marks some
skills user-invoked-only in two places — `disable-model-invocation: true` in
`SKILL.md` frontmatter, and `policy.allow_implicit_invocation: false` in
`agents/openai.yaml` — so this overlay deletes those two keys in a **fork clone**
and nothing else. See ADR 0010.

Two keys, deleted, never rewritten: no body, description, name or reference file
is touched, which is what keeps a promote a fast-forward-shaped merge and keeps
`fast_forwardable()` in `fork_state.py` able to recognise the divergence as the
overlay rather than a rogue local commit.

Prints its plan and changes nothing unless `--apply` is given.
"""

import argparse
import json
import re
import sys
from pathlib import Path

# The two keys the overlay owns. `fork_state.overlay_only()` matches the same
# strings against a real diff, so a change here is a change to what a promote
# will accept — keep the two in step.
FRONTMATTER_KEY = "disable-model-invocation"
YAML_POLICY_KEY = "allow_implicit_invocation"

_FRONTMATTER_LINE = re.compile(rf"^\s*{FRONTMATTER_KEY}\s*:\s*true\s*$")
_POLICY_LINE = re.compile(r"^\s*policy\s*:\s*$")
_POLICY_BODY_LINE = re.compile(rf"^\s+{YAML_POLICY_KEY}\s*:\s*false\s*$")


def registered_skills(clone):
    """The skill directories the plugin manifest actually loads.

    Scoped to the manifest on purpose: a `SKILL.md` under `skills/in-progress/`
    or `skills/deprecated/` is not registered, so it loads in no session and
    stripping its flag would be diff for nothing.
    """
    manifest = json.loads((clone / ".claude-plugin" / "plugin.json").read_text())
    return [clone / rel for rel in manifest.get("skills", [])]


def strip_frontmatter_flag(text):
    """`SKILL.md` with the `disable-model-invocation` line removed, or None.

    None means the file already has no flag — the overlay is a no-op there, which
    is what makes a re-run after a promote safe.
    """
    lines = text.splitlines(keepends=True)
    kept = [line for line in lines if not _FRONTMATTER_LINE.match(line)]
    return "".join(kept) if len(kept) != len(lines) else None


def strip_policy_block(text):
    """`agents/openai.yaml` with the `policy:` block removed, or None.

    The block is only dropped when its sole child is the one key this overlay
    owns. A `policy:` holding anything else is left alone and reported, rather
    than guessed at — upstream may grow policy fields that have nothing to do
    with invocation.
    """
    lines = text.splitlines(keepends=True)
    out, i, changed = [], 0, False
    while i < len(lines):
        if _POLICY_LINE.match(lines[i]):
            body, j = [], i + 1
            while j < len(lines) and lines[j].startswith((" ", "\t")):
                body.append(lines[j])
                j += 1
            if body and all(_POLICY_BODY_LINE.match(line) for line in body):
                i = j
                changed = True
                continue
        out.append(lines[i])
        i += 1
    return "".join(out) if changed else None


def plan(clone):
    """Per registered skill, the files the overlay would rewrite. Read-only.

    Returns `(edits, skipped)` — the rewrites, and any `openai.yaml` that still
    carries the key after stripping, meaning its `policy:` block holds something
    this overlay does not own.
    """
    edits, skipped = [], []
    for skill in registered_skills(clone):
        for name, strip in (
            ("SKILL.md", strip_frontmatter_flag),
            ("agents/openai.yaml", strip_policy_block),
        ):
            path = skill / name
            if not path.exists():
                continue
            text = path.read_text()
            new = strip(text)
            if new is not None:
                edits.append((path, new))
            elif YAML_POLICY_KEY in text:
                skipped.append(path)
    return edits, skipped


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clone", required=True, type=Path, help="fork clone root")
    parser.add_argument(
        "--apply", action="store_true", help="write the edits (default: print them)"
    )
    args = parser.parse_args(argv)

    edits, skipped = plan(args.clone)
    if not edits:
        print(f"invocation overlay: nothing to strip in {args.clone} — already applied")
    for path, new in edits:
        print(f"{'strip' if args.apply else 'would strip'} {path.relative_to(args.clone)}")
        if args.apply:
            path.write_text(new)
    for path in skipped:
        print(
            f"LEFT ALONE {path.relative_to(args.clone)} — its `policy:` holds more "
            f"than {YAML_POLICY_KEY}; decide by hand",
            file=sys.stderr,
        )
    return 1 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
