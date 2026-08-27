#!/usr/bin/env python3
"""The `PreToolUse` hook for `Bash`: deny the two writes a session must not make.

Every other rule in this repo is advice, so it holds where a model remembers it and
it fails where the model does not. This hook is the one layer that refuses a command
before it runs.

**Two denials, and no more.**

1. **A work-state label write from any session.** Only a seam writes one. The
   vocabulary comes from `docs/agents/issue-tracker.md`, so no label string is
   copied into this file.
2. **The teardown command outside `scripts/close_item.py`.** Step 8 of the close
   transaction removes a worktree, and nothing else does.

**It denies no `git push`.** That denial needs a gate record a machine wrote, and
the worker still writes its own. So it lands with the item that makes the record
deterministic, and never here.

**It exits fast where it does not apply.** The hook fires on every `Bash` call in
every session on the machine. So the first check is the repo marker:
`docs/agents/orchestrator.md`, or an `.orchestrator/` directory. With no marker the
hook prints nothing and exits 0.

**It fails open.** A command this hook cannot parse is a command it permits. A hook
that guesses denies correct work, and that is worse than a rule a session breaks.

The plane law is `orchestrator/references/hooks.md` and
`orchestrator/docs/adr/0050-a-hook-refuses-and-a-seam-performs.md`.

    python3 <plugin root>/hooks/refuse.py < event.json

The tests are `hooks/test_refuse.py`, and both gate commands run them:

    python3 -m pytest hooks/ -q
    python3 -m unittest discover -s hooks -t . -q     # fallback, no pytest
"""

import json
import os
import re
import shlex
import sys
from pathlib import Path

# The two facts that say this repo is orchestrated. Either one is enough.
CONFIG = Path("docs") / "agents" / "orchestrator.md"
ORCHESTRATOR_DIR = ".orchestrator"

# The work-state label family, read from the file that owns it. The strings are not
# copied here, because two copies of a vocabulary drift.
LABEL_SECTION = "## Work-state labels"
TABLE_LABEL = re.compile(r"^\|[^|]*\|\s*`([^`]+)`\s*\|")

# The flags either tracker CLI writes a label with. A command that carries none of
# them writes no label, whatever strings it holds.
LABEL_FLAGS = ("--add-label", "--remove-label", "--label", "--unlabel")

# The teardown verb, as two consecutive words. One tool says `worktree rm` and
# another says `worktree remove`, so the pair matches every tool that spells the
# operation out (`orchestrator/references/tools/_operations.md`, operation 10).
TEARDOWN_VERBS = (("worktree", "remove"), ("worktree", "rm"))

# The one seam that is permitted to tear a worktree down. Its own invocation
# carries the teardown command as an argument, so the seam is named before the
# verb is matched.
CLOSE_SEAM = "close_item.py"


def project_dir():
    """The repository this session opened."""
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())


def orchestrated(root):
    """Whether this repo is one the orchestrator skill runs on."""
    return (root / CONFIG).is_file() or (root / ORCHESTRATOR_DIR).is_dir()


def work_state_labels(root):
    """The work-state label family, from the file that owns the vocabulary.

    A table row holds the label in its second cell. Where the file is absent, this
    reads as an empty family and the hook denies no label write.
    """
    path = root / "docs" / "agents" / "issue-tracker.md"
    if not path.is_file():
        return []
    labels = []
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line.strip() == LABEL_SECTION
            continue
        if inside:
            match = TABLE_LABEL.match(line)
            if match:
                labels.append(match.group(1))
    return labels


def tokens(command):
    """The words of one shell command, or an empty list.

    A command this splitter cannot read is a command the hook permits, so an
    unbalanced quote denies nothing.
    """
    try:
        return shlex.split(command)
    except ValueError:
        return []


def labels_written(words):
    """Every label value the command hands to a label flag.

    A flag takes its value as the next word or after an `=`, and one value can hold
    several labels separated by a comma.
    """
    written = []
    expecting = False
    for word in words:
        if expecting:
            written += word.split(",")
            expecting = False
            continue
        if word in LABEL_FLAGS:
            expecting = True
            continue
        for flag in LABEL_FLAGS:
            if word.startswith(f"{flag}="):
                written += word[len(flag) + 1 :].split(",")
    return [value.strip() for value in written if value.strip()]


def label_denial(root, words):
    """The reason a work-state label write is denied, or an empty string."""
    written = labels_written(words)
    if not written:
        return ""
    family = work_state_labels(root)
    named = [label for label in written if label in family]
    if not named:
        return ""
    return (
        f"This command writes the work-state label `{named[0]}`. A seam writes that "
        "label, and a session never writes one by hand. Run "
        "`python3 <plugin root>/scripts/close_item.py` for the labels of a close. "
        "The rule is orchestrator/references/hooks.md."
    )


def teardown_denial(words):
    """The reason a teardown outside the close seam is denied, or an empty string."""
    if any(CLOSE_SEAM in word for word in words):
        return ""
    pairs = set(zip(words, words[1:]))
    if not pairs & set(TEARDOWN_VERBS):
        return ""
    return (
        "This command removes a worktree. Step 8 of the close transaction owns that "
        "step, and it runs after the pull request is merged and the tree is clean. "
        "Run `python3 <plugin root>/scripts/close_item.py --execute --teardown` with "
        "the command in `--teardown-command`. The rule is "
        "orchestrator/references/hooks.md."
    )


def denial(root, command):
    """The reason this command is denied, or an empty string for a permitted one."""
    words = tokens(command)
    return label_denial(root, words) or teardown_denial(words)


def main():
    """Deny one of the two writes, or print nothing.

    The exit code is 0 on every path. The denial travels in the payload, and never
    in the exit code, so a permitted command costs one silent process.
    """
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if event.get("tool_name") != "Bash":
        return 0
    root = project_dir()
    if not orchestrated(root):
        return 0
    reason = denial(root, (event.get("tool_input") or {}).get("command") or "")
    if not reason:
        return 0
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                },
                "systemMessage": reason,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
