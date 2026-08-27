#!/usr/bin/env python3
"""The `PostToolUse` hook for `Bash`: append one gate record line per gate run.

Where the command that just ran is a configured gate command, this hook appends one
line to `.orchestrator/gates-<item>.jsonl`. The line holds the command, the exit
code, a UTC timestamp and `head_sha`. The format has one home, and that is
`orchestrator/references/quality-gates.md`.

**This hook is the one named exception to the plane law.** Every other hook only
answers, and this one writes a file. The reason is stated and not hidden: **a record
a model writes is a record a model can fake.** It is not a mutation of the tracker.
It is an append-only note of what a command already did
(`orchestrator/docs/adr/0051-a-hook-refuses-and-a-seam-performs.md`).

**It is also the one writer of that file.** The gate script runs the command and
exits, and no script and no `Makefile` appends a line
(`orchestrator/docs/adr/0052-a-gate-blocks-and-a-hook-writes-its-record.md`).

**A line is written whatever the exit code is.** A red run that writes no line reads
as a run that never happened.

**The exit code is derived, because the payload carries no field for it.** A
completed command answers with an object, and a failed one answers with a string
whose first line reads `Error: Exit code <N>`. Where neither shape gives a code, and
where the command was interrupted, this hook writes no line. A line it cannot stand
behind is worse than no line.

**It exits fast where it does not apply.** The hook fires on every `Bash` call in
every session on the machine. So the first check is the repo marker:
`docs/agents/orchestrator.md`, or an `.orchestrator/` directory. With no marker the
hook writes nothing, prints nothing and exits 0.

    python3 <plugin root>/hooks/record.py < event.json

The tests are `hooks/test_record.py`, and both gate commands run them:

    python3 -m pytest hooks/ -q
    python3 -m unittest discover -s hooks -t . -q     # fallback, no pytest
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# The two facts that say this repo is orchestrated. Either one is enough.
CONFIG = Path("docs") / "agents" / "orchestrator.md"
ORCHESTRATOR_DIR = ".orchestrator"

# The three layer commands of the `gates:` block. Layer 5 is not a Gate: it has no
# exit code, so it stops nothing and it records nothing
# (`orchestrator/references/quality-gates.md`).
GATE_KEYS = ("quick", "full", "deep")

# One line of that block: the key, then a quoted or a bare value. A trailing
# comment is not part of the command.
GATE_LINE = re.compile(
    r"""^\s+(quick|full|deep):\s*(?:"([^"]*)"|'([^']*)'|([^#\n]*))"""
)

# How a failed command reports its exit code. The tool answers with a string on that
# path, and the first line carries the number.
FAILED = re.compile(r"^Error: Exit code (\d+)\b")

# Where the record lives, beside the checklist the worker ticks.
GATE_RECORD = "gates-{item}.jsonl"

# What a commit that cannot be read is recorded as. A reader that compares it to `HEAD`
# sees no match, so an unreadable commit reads as not green.
UNKNOWN_SHA = "unknown"


def project_dir():
    """The repository this session opened."""
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())


def orchestrated(root):
    """Whether this repo is one the orchestrator skill runs on."""
    return (root / CONFIG).is_file() or (root / ORCHESTRATOR_DIR).is_dir()


def item_number(root):
    """The work item this worktree implements, or an empty string.

    The checklist file names it, so no field of config reaches this hook. A checkout
    with no checklist writes no record, which is what leaves a run outside a
    worktree with nothing to append to.
    """
    found = sorted((root / ORCHESTRATOR_DIR).glob("checklist-*.md"))
    return found[0].stem[len("checklist-") :] if found else ""


def gate_commands(root):
    """Every gate command the config names, in the order the layers run.

    The `gates:` block of `docs/agents/orchestrator.md` is the one source. A blank
    field is a dropped layer, so it names no command and matches nothing.
    """
    path = root / CONFIG
    if not path.is_file():
        return []
    commands = []
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
                commands.append(value.strip())
    return commands


def gate_that_ran(root, command):
    """The configured gate command this `Bash` call ran, or an empty string.

    The match is on a word boundary, so `make quick` does not match `make quicker`.
    The name that reaches the record is the one config holds, and never the whole
    command line. The record reads as the `gates:` block names it.
    """
    for gate in gate_commands(root):
        if re.search(rf"(?<!\w){re.escape(gate)}(?!\w)", command):
            return gate
    return ""


def exit_code(response):
    """The exit code the command returned, or `None` where none can be read.

    A completed command answers with an object, and the tool reports no code with
    it, so a completed command is a zero. A failed command answers with a string
    that names its code. Anything else is a command that reached no verdict: a
    denied call, a rejected call, or a call the harness stopped.
    """
    if isinstance(response, str):
        match = FAILED.match(response)
        return int(match.group(1)) if match else None
    if isinstance(response, dict):
        return None if response.get("interrupted") else 0
    return None


def head_sha(root):
    """The commit the run saw, or `unknown`."""
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() or UNKNOWN_SHA if proc.returncode == 0 else UNKNOWN_SHA


def line(gate, code, root):
    """One gate record line, with the four keys in the order the format holds."""
    return json.dumps(
        {
            "command": gate,
            "exit": code,
            "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "head_sha": head_sha(root),
        }
    )


def main():
    """Append one line for a gate run, or write nothing.

    The exit code is 0 on every path. A hook that stops a tool call it only observes
    would turn a green gate into a failed command.
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
    item = item_number(root)
    if not item:
        return 0
    gate = gate_that_ran(root, (event.get("tool_input") or {}).get("command") or "")
    if not gate:
        return 0
    code = exit_code(event.get("tool_response"))
    if code is None:
        return 0
    record = root / ORCHESTRATOR_DIR / GATE_RECORD.format(item=item)
    with record.open("a", encoding="utf-8") as handle:
        handle.write(f"{line(gate, code, root)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
