#!/usr/bin/env python3
"""The `PostToolUse` hook for `Bash`: append one gate record line per gate run.

Where the command that just ran is a configured gate command, this hook appends one
line to `.orchestrator/gates-<item>.jsonl`. The line holds the command, the exit
code, a UTC timestamp and `head_sha`. The format's home in prose is
`orchestrator/references/quality-gates.md`, and its home in code is
`hooks/gate_record.py`, which holds the write this hook calls.

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
import re
import sys

try:
    from . import gate_record, repo
except ImportError:  # the hook runs as a plain script, with no package around it
    import gate_record  # type: ignore[no-redef, import-not-found]
    import repo  # type: ignore[no-redef, import-not-found]

# How a failed command reports its exit code. The tool answers with a string on that
# path, and the first line carries the number.
FAILED = re.compile(r"^Error: Exit code (\d+)\b")


def gate_that_ran(root, command):
    """The configured gate command this `Bash` call ran, or an empty string.

    The match is on a word boundary, so `make quick` does not match `make quicker`.
    The name that reaches the record is the one config holds, and never the whole
    command line. The record reads as the `gates:` block names it.
    """
    for _, gate in repo.gate_commands(root):
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
    root = repo.project_dir()
    if not repo.orchestrated(root):
        return 0
    item = repo.item_number(root)
    if not item:
        return 0
    gate = gate_that_ran(root, (event.get("tool_input") or {}).get("command") or "")
    if not gate:
        return 0
    code = exit_code(event.get("tool_response"))
    if code is None:
        return 0
    gate_record.append(root, item, gate, code)
    return 0


if __name__ == "__main__":
    sys.exit(main())
