#!/usr/bin/env python3
"""The `SessionStart` hook: inject the plugin root, the role and the item facts.

A session that starts with no facts works from memory, and a session that lost its
facts to a compaction does the same. This hook reads those facts from disk and from
the tracker, and it puts them in the session's context. It changes nothing.

**It exits fast where it does not apply.** The hook fires in every session on the
machine once the plugin is installed. So the first check is the repo marker:
`docs/agents/orchestrator.md`, or an `.orchestrator/` directory. With no marker the
hook prints nothing and exits 0, which costs the session nothing.

**Three facts reach a worker session**: the work-state label, the checklist
position, and whether the gate record is green at `HEAD`. An orchestrator session
owns no work item, so it gets the plugin root and the role alone.

The plane law is `orchestrator/references/hooks.md` and
`orchestrator/docs/adr/0050-a-hook-refuses-and-a-seam-performs.md`. This hook
refuses nothing and performs nothing. It answers with one block of context.

    python3 <plugin root>/hooks/context.py < event.json

The tests are `hooks/test_context.py`, and both gate commands run them:

    python3 -m pytest hooks/ -q
    python3 -m unittest discover -s hooks -t . -q     # fallback, no pytest
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# The two facts that say this repo is orchestrated. Either one is enough: a main
# checkout carries the config, and a worker worktree carries the checklist
# directory. A directory with neither is a repo this plugin has nothing to say
# about.
CONFIG = Path("docs") / "agents" / "orchestrator.md"
ORCHESTRATOR_DIR = ".orchestrator"

# The work-state label family, read from the file that owns it. The strings are not
# copied here, because two copies of a vocabulary drift
# (`docs/agents/issue-tracker.md`).
LABEL_SECTION = "## Work-state labels"
TABLE_LABEL = re.compile(r"^\|[^|]*\|\s*`([^`]+)`\s*\|")

# The checklist and the gate record of one work item, beside each other in the
# worktree the worker owns.
CHECKLIST = "checklist-{item}.md"
GATE_RECORD = "gates-{item}.jsonl"
TICKED = "- [x]"
UNTICKED = "- [ ]"


def project_dir():
    """The repository this session opened.

    The harness passes it, and the working directory answers where it did not.
    """
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())


def plugin_root():
    """The directory this plugin is installed in.

    The harness passes it to every hook. This file sits one level under that root,
    so the parent answers where the variable is unset.
    """
    return Path(
        os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent
    )


def orchestrated(root):
    """Whether this repo is one the orchestrator skill runs on."""
    return (root / CONFIG).is_file() or (root / ORCHESTRATOR_DIR).is_dir()


def item_number(root):
    """The work item this worktree implements, or an empty string.

    The checklist file names it, so no field of config reaches this hook. A
    directory with no checklist is not a worker's worktree.
    """
    found = sorted((root / ORCHESTRATOR_DIR).glob("checklist-*.md"))
    return found[0].stem[len("checklist-") :] if found else ""


def work_state_labels(root):
    """The work-state label family, from the file that owns the vocabulary.

    A table row holds the label in its second cell. Where the file is absent or
    holds no such table, this reads as an empty family and the caller says so.
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
        if not inside:
            continue
        match = TABLE_LABEL.match(line)
        if match:
            labels.append(match.group(1))
    return labels


def label_of(root, item):
    """The one work-state label the item wears, and how the read went.

    The answer is a pair: the label and the reason there is none. A tracker that
    cannot be reached is a named gap, and never a silent one, because a session
    that reads no reason assumes the item wears nothing.
    """
    sys.path.insert(0, str(plugin_root()))
    try:
        from scripts import tracker
    except ImportError as exc:  # pragma: no cover - a broken install
        return "", f"the tracker adapter did not import ({exc})"
    family = work_state_labels(root)
    if not family:
        return "", "docs/agents/issue-tracker.md names no work-state label"
    try:
        worn = tracker.Tracker().issue(item)["labels"]
    except (OSError, ValueError, tracker.TrackerError) as exc:
        return "", f"the tracker read failed ({exc})"
    for label in family:
        if label in worn:
            return label, ""
    return "", "the item wears no work-state label"


def checklist_position(root, item):
    """How far the checklist is, as `<ticked> of <total>`."""
    path = root / ORCHESTRATOR_DIR / CHECKLIST.format(item=item)
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    ticked = text.count(TICKED)
    return f"{ticked} of {ticked + text.count(UNTICKED)}"


def head_sha(root):
    """The commit this worktree sits on, or an empty string."""
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def gate_verdict(root, item):
    """Whether every gate command in the record is green at `HEAD`.

    The last line each command wrote is the one that counts, because a worker runs
    a command again after it corrects a fault. A short sha reads as a prefix, so
    either form matches. A missing line, a malformed line, a non-zero exit or a
    stale sha each read as not green, and the answer names which.
    """
    path = root / ORCHESTRATOR_DIR / GATE_RECORD.format(item=item)
    if not path.is_file():
        return "no gate command left a line yet"
    latest = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            return "the record holds a line that is not JSON"
        latest[entry.get("command", "")] = entry
    if not latest:
        return "no gate command left a line yet"
    head = head_sha(root)
    for command, entry in sorted(latest.items()):
        if entry.get("exit") != 0:
            return f"`{command}` exited {entry.get('exit')}"
        seen = str(entry.get("head_sha") or "")
        if not head or not seen or not (head.startswith(seen) or seen.startswith(head)):
            return f"`{command}` ran against another commit"
    return ""


def facts(root):
    """The lines this hook injects, in the order a session reads them."""
    lines = [
        "The orchestrator plugin root is "
        f"`{plugin_root()}`. Substitute it into every seam invocation.",
    ]
    item = item_number(root)
    if not item:
        lines.append(
            "This session owns no work item, so there are no item facts. It is an "
            "orchestrator session, or a checkout with no worker checklist."
        )
        return lines
    lines.append(f"This session is a worker on work item {item}.")
    label, gap = label_of(root, item)
    lines.append(
        f"Its work-state label is `{label}`."
        if label
        else f"Its work-state label is unknown: {gap}."
    )
    position = checklist_position(root, item)
    lines.append(
        f"Its checklist is at {position} boxes."
        if position
        else "Its checklist file is absent."
    )
    reason = gate_verdict(root, item)
    lines.append(
        "Its gate record is green at HEAD."
        if not reason
        else f"Its gate record is not green: {reason}."
    )
    return lines


def main():
    """Print the item facts as context, or print nothing.

    The exit code is 0 on every path. A hook that stops a session start is worse
    than a hook that says nothing.
    """
    try:
        json.load(sys.stdin)
    except ValueError:
        return 0
    root = project_dir()
    if not orchestrated(root):
        return 0
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "\n".join(facts(root)),
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
