#!/usr/bin/env python3
"""The `PreToolUse` hook for `Bash`: deny the three commands a session must not run.

Every other rule in this repo is advice, so it holds where a model remembers it and
it fails where the model does not. This hook is the one layer that refuses a command
before it runs.

**Three denials, and no more.**

1. **A work-state label write from any session.** Only a seam writes one. The
   vocabulary comes from `docs/agents/issue-tracker.md`, so no label string is
   copied into this file.
2. **The teardown command outside `scripts/close_item.py`.** Step 8 of the close
   transaction removes a worktree, and nothing else does.
3. **A `git push` while a configured gate has no green line at `HEAD`.** The
   `gates:` block of config names the commands. `hooks/record.py` writes the record
   a machine can trust, so this denial reads a fact rather than a claim. The message
   names each failing gate and the command to run, because a worker that reads
   "denied" and no command guesses.

**It exits fast where it does not apply.** The hook fires on every `Bash` call in
every session on the machine. So the first check is the repo marker:
`docs/agents/orchestrator.md`, or an `.orchestrator/` directory. With no marker the
hook prints nothing and exits 0.

**It fails open.** A command this hook cannot parse is a command it permits. A hook
that guesses denies correct work, and that is worse than a rule a session breaks.

The plane law is `orchestrator/references/hooks.md` and
`orchestrator/docs/adr/0051-a-hook-refuses-and-a-seam-performs.md`.

    python3 <plugin root>/hooks/refuse.py < event.json

The tests are `hooks/test_refuse.py`, and both gate commands run them:

    python3 -m pytest hooks/ -q
    python3 -m unittest discover -s hooks -t . -q     # fallback, no pytest
"""

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

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

# The operators that end one command and start the next. `make full && git push` holds
# two commands, and the push in its tail is still a push.
OPERATORS = ("&&", "||", ";", "|", "&")

# The `git` verb this hook reads, and the global flags that take the next word as their
# value. Skipping a flag with its value is what lets `git -C /repo push` read as a push.
GIT = "git"
PUSH = "push"
GIT_VALUE_FLAGS = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path")

# The three layer keys of the `gates:` block, and one line of that block: the key, then
# a quoted or a bare value. A trailing comment is not part of the command. Layer 5 is
# not a Gate, because it has no exit code
# (`orchestrator/references/quality-gates.md`).
GATE_LINE = re.compile(
    r"""^\s+(quick|full|deep):\s*(?:"([^"]*)"|'([^']*)'|([^#\n]*))"""
)

# Where the record lives, beside the checklist the worker ticks. `hooks/record.py` is
# its one writer, and the format has one home: the gate record section of
# `orchestrator/references/quality-gates.md`.
GATE_RECORD = "gates-{item}.jsonl"

# The shortest `head_sha` that counts as an identification of a commit. A recorded sha
# can be short, so the comparison is a prefix test. The floor is what stops a
# one-character value from matching every commit there is.
SHA_PREFIX = 7


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
    """The reason a work-state label write is denied, or an empty string.

    The close seam is the one caller allowed to make this write. `teardown_denial`
    runs the same test for its own write. A command that names the seam anywhere is
    read as that seam's call, so a hand-typed write beside it goes through too.
    """
    if any(CLOSE_SEAM in word for word in words):
        return ""
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


def commands(words):
    """The words of each command in the line, split at every shell operator."""
    found: list[list[str]] = [[]]
    for word in words:
        if word in OPERATORS:
            found.append([])
            continue
        found[-1].append(word)
    return found


def pushes(words):
    """Whether one of these commands is a `git push`.

    A command is read as a push where `git` is the program and `push` is the verb it
    was given. So a quoted sentence that holds the two words is not a push, and a
    review note that names the rule goes through.
    """
    for segment in commands(words):
        if not segment or Path(segment[0]).name != GIT:
            continue
        rest = iter(segment[1:])
        for word in rest:
            if word in GIT_VALUE_FLAGS:
                next(rest, "")
                continue
            if word.startswith("-"):
                continue
            if word == PUSH:
                return True
            break
    return False


def item_number(root):
    """The work item this worktree implements, or an empty string.

    The checklist file names it, so no field of config reaches this hook. A checkout
    with no checklist proves no gate, because the record belongs to one item.
    """
    found = sorted((root / ORCHESTRATOR_DIR).glob("checklist-*.md"))
    return found[0].stem[len("checklist-") :] if found else ""


def gate_commands(root):
    """Every `(layer, command)` pair the `gates:` block of config names.

    The block is the one source. **A blank command is not a Gate**: a layer the
    profile dropped names no command, so it is left out here. Otherwise a repo on the
    `lite` profile, where `deep` is blank, can never push.
    """
    path = root / CONFIG
    if not path.is_file():
        return []
    gates = []
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("gates:"):
            inside = True
            continue
        if inside and line.strip() and not line.startswith((" ", "\t")):
            break
        if not inside:
            continue
        match = GATE_LINE.match(line)
        if match:
            value = next(group for group in match.groups()[1:] if group is not None)
            if value.strip():
                gates.append((match.group(1), value.strip()))
    return gates


def latest_runs(path):
    """`(newest run per command, the first malformed line number)`.

    The last line a command wrote is the one that counts, because a worker runs a
    command again after it corrects a fault. The walk stops at the first line that is
    not one JSON object, because one unreadable line puts the lines around it in
    doubt as well. This is the rule the `gates-unproven` outcome already uses
    (`scripts/worker_state.py`).
    """
    # A line is whatever `json.loads` returns, so the value type is `Any`.
    latest: dict[str, Any] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return latest, 0
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            run = json.loads(line)
        except ValueError:
            return latest, number
        if not isinstance(run, dict):
            return latest, number
        latest[str(run.get("command", ""))] = run
    return latest, 0


def head_sha(root):
    """The commit this worktree sits on, or an empty string."""
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def not_green(run, head):
    """Why this run is not a green line at `HEAD`, or an empty string.

    Three causes, and each one asks for the same repair: run the command again. A
    recorded sha reads as a prefix, so a short one matches.
    """
    if run is None:
        return "the record holds no line of it"
    seen = str(run.get("head_sha") or "")
    if not head or len(seen) < SHA_PREFIX or not head.startswith(seen):
        return f"its newest line names another commit, {seen or 'none'}"
    if run.get("exit") != 0:
        return f"its newest line exited {run.get('exit')}"
    return ""


def push_denial(root, words):
    """The reason a `git push` is denied, or an empty string.

    A push is denied while any configured gate lacks a line with exit `0` at the
    current `HEAD`. A checkout with no work item and a config with no gate command
    each prove nothing, so each one permits the push.
    """
    if not pushes(words):
        return ""
    item = item_number(root)
    gates = gate_commands(root)
    if not item or not gates:
        return ""
    record = root / ORCHESTRATOR_DIR / GATE_RECORD.format(item=item)
    latest, malformed = latest_runs(record)
    runs = f"Run {', '.join(f'`{command}`' for _, command in gates)}."
    if malformed:
        return (
            f"This command pushes, and line {malformed} of {record} is not one JSON "
            f"object. So the record proves no gate green at HEAD. {runs} The rule is "
            "orchestrator/references/hooks.md."
        )
    head = head_sha(root)
    faults = []
    for layer, command in gates:
        reason = not_green(latest.get(command), head)
        if reason:
            faults.append(
                f"the `{layer}` gate has no green line at HEAD, because {reason} — "
                f"run `{command}`"
            )
    if not faults:
        return ""
    return (
        "This command pushes, and the gate record does not prove every gate green at "
        f"HEAD: {'; '.join(faults)}. Run each command named here. Then this push goes "
        "through. The rule is orchestrator/references/hooks.md."
    )


def denial(root, command):
    """The reason this command is denied, or an empty string for a permitted one."""
    words = tokens(command)
    return (
        label_denial(root, words) or teardown_denial(words) or push_denial(root, words)
    )


def main():
    """Deny one of the three commands, or print nothing.

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
