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

**What it reads about the repo, it reads through `hooks/repo.py`**, and the gate record
it reads through `hooks/gate_record.py`. This hook holds no copy of either read, and it
keeps the wording of every line it prints.

The plane law is `orchestrator/references/hooks.md` and
`orchestrator/docs/adr/0051-a-hook-refuses-and-a-seam-performs.md`. This hook
refuses nothing and performs nothing. It answers with one block of context.

    python3 <plugin root>/hooks/context.py < event.json

The tests are `hooks/test_context.py`, and both gate commands run them:

    python3 -m pytest hooks/ -q
    python3 -m unittest discover -s hooks -t . -q     # fallback, no pytest
"""

import json
import sys

try:
    from . import gate_record, repo
except ImportError:  # the hook runs as a plain script, with no package around it
    import gate_record  # type: ignore[no-redef, import-not-found]
    import repo  # type: ignore[no-redef, import-not-found]

# The checklist of one work item, beside the gate record in the worktree the worker
# owns. `hooks/gate_record.py` names the record itself.
CHECKLIST = "checklist-{item}.md"
TICKED = "- [x]"
UNTICKED = "- [ ]"


def label_of(root, item):
    """The one work-state label the item wears, and how the read went.

    The answer is a pair: the label and the reason there is none. A tracker that
    cannot be reached is a named gap, and never a silent one, because a session
    that reads no reason assumes the item wears nothing.
    """
    sys.path.insert(0, str(repo.plugin_root()))
    try:
        from scripts import tracker
    except ImportError as exc:  # pragma: no cover - a broken install
        return "", f"the tracker adapter did not import ({exc})"
    family = repo.work_state_labels(root)
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
    path = root / repo.ORCHESTRATOR_DIR / CHECKLIST.format(item=item)
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    ticked = text.count(TICKED)
    return f"{ticked} of {ticked + text.count(UNTICKED)}"


def gate_verdict(root, item):
    """Whether every gate command in the record is green at `HEAD`.

    The newest line each command wrote is the one that counts, because a worker runs
    a command again after it corrects a fault. A missing line, a malformed line, a
    non-zero exit or a stale sha each read as not green, and the answer names which.

    Every command the record holds is read, and no command is required. A worker that
    ran one layer so far is not yet green, and it is not at fault either.
    """
    record = gate_record.path(root, item)
    if not record.is_file():
        return "no gate command left a line yet"
    runs, malformed = gate_record.runs(record)
    if malformed:
        return "the record holds a line that is not JSON with the four keys"
    latest = gate_record.newest(runs)
    if not latest:
        return "no gate command left a line yet"
    head = repo.head_sha(root)
    for command, run in sorted(latest.items()):
        if run["exit"] != 0:
            return f"`{command}` exited {run['exit']}"
        if not gate_record.at_head(run["head_sha"], head):
            return f"`{command}` ran against another commit"
    return ""


def facts(root):
    """The lines this hook injects, in the order a session reads them."""
    lines = [
        "The orchestrator plugin root is "
        f"`{repo.plugin_root()}`. Substitute it into every seam invocation.",
    ]
    item = repo.item_number(root)
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
    root = repo.project_dir()
    if not repo.orchestrated(root):
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
