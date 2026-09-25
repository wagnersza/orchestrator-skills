#!/usr/bin/env python3
"""The **Gate record**: the one write, the one read, and the one at-`HEAD` test.

A gate run leaves a machine record behind, one JSON object per line, in
`.orchestrator/gates-<item>.jsonl` beside the checklist the worker ticks. The format's
home in prose is the gate record section of
`orchestrator/references/quality-gates.md`, and **this module is its home in code**.

Four callers share it, and each one keeps its own message wording, because that is the
part that legitimately differs:

- `hooks/record.py` appends one line per gate run. It is the one writer
  (`orchestrator/docs/adr/0052-a-gate-blocks-and-a-hook-writes-its-record.md`).
- `hooks/refuse.py` denies a `git push` while a configured gate has no green line at
  `HEAD`.
- `hooks/context.py` injects that same verdict at session start.
- `scripts/worker_state.py` fires the `gates-unproven` outcome from the same read.

It refuses nothing and it performs nothing, so the plane law holds
(`orchestrator/docs/adr/0051-a-hook-refuses-and-a-seam-performs.md`). It is a library of
the plane rather than a hook, so the manifest names nothing
(`orchestrator/docs/adr/0060-the-manifest-names-no-standard-hook-file.md`).

The suite is `hooks/test_gate_record.py`, and both gate commands run it:

    python3 -m pytest hooks/ -q
    python3 -m unittest discover -s hooks -t . -q     # fallback, no pytest
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from . import repo
except ImportError:  # each hook runs as a plain script, with no package around it
    import repo  # type: ignore[no-redef, import-not-found]

# The four keys one line carries, in the order the format writes them. A line that drops
# one of them is malformed: a run nobody can date, or cannot tie to a commit, proves
# nothing (ADR 0036).
KEYS = ("command", "exit", "utc", "head_sha")

# The shortest `head_sha` that counts as an identification of a commit. A recorded sha
# can be short, so the comparison is a prefix test. The floor is what stops a
# one-character value from matching every commit there is. It is declared here once.
SHA_PREFIX = 7

# The record of one work item, beside that item's checklist.
FILE = "gates-{item}.jsonl"

# How the timestamp reads: UTC, to the second, as the format's one home writes it.
UTC = "%Y-%m-%dT%H:%M:%SZ"


def path(root, item):
    """Where the record of one work item lives."""
    return Path(root) / repo.ORCHESTRATOR_DIR / FILE.format(item=item)


def line(command, code, sha):
    """One record line, with the four keys in the order the format holds."""
    return json.dumps(
        {
            "command": command,
            "exit": code,
            "utc": datetime.now(timezone.utc).strftime(UTC),
            "head_sha": sha,
        }
    )


def append(root, item, command, code):
    """Append one line for a finished gate run, and answer with the file it went to.

    The record is append-only, so a second run of the same command leaves both lines
    readable. The commit comes from `repo.head_sha`. An unreadable commit is written as
    an empty value, and it is never a reason to drop the line. A run with no commit
    behind it still happened, and a reader then sees a line that ties to nothing.
    """
    record = path(root, item)
    with record.open("a", encoding="utf-8") as handle:
        handle.write(f"{line(command, code, repo.head_sha(root))}\n")
    return record


def runs(source):
    """`(runs, malformed)` for the record at `source`.

    **A read keeps every run**, in the order a gate command appended them, and it keeps
    no run in place of another. So the newest run of a command is the last one in the
    list, and no line has to be sorted by its `utc` value.

    Every run serves both readers. The `gates-unproven` outcome needs the whole list,
    because its message names the newest recorded sha whether or not that run sits at
    `HEAD`. The push denial and the session-start verdict each want one run per command,
    and `newest` hands them that from the same list.

    `malformed` is the number of the first line that does not read, or 0 where every line
    does. A line reads where it is one JSON object with the four keys and an integer
    exit. A blank line is how a text file ends, so it is neither a run nor a fault. The
    walk stops at the first malformed line, because one unreadable line puts the lines
    around it in doubt as well. A file that cannot be read at all holds no run and no
    fault, and the caller reads the missing file itself.
    """
    # A line is whatever `json.loads` returns, so the value type is `Any`. The walk that
    # follows narrows it to the four keys.
    found: list[dict[str, Any]] = []
    try:
        text = Path(source).read_text(encoding="utf-8")
    except OSError:
        return found, 0
    for number, text_line in enumerate(text.splitlines(), 1):
        if not text_line.strip():
            continue
        try:
            run = json.loads(text_line)
        except ValueError:
            return found, number
        if not isinstance(run, dict) or any(key not in run for key in KEYS):
            return found, number
        try:
            run["exit"] = int(run["exit"])
        except (TypeError, ValueError):
            return found, number
        run["command"] = str(run["command"])
        run["head_sha"] = str(run["head_sha"])
        found.append(run)
    return found, 0


def newest(found):
    """The newest run of each command, keyed by the command.

    The last line a command wrote is its verdict, because a worker runs a command again
    after it corrects a fault.
    """
    return {run["command"]: run for run in found}


def at_head(recorded, head):
    """Whether a recorded `head_sha` names the commit `head`.

    A recorded sha can be short, so this is a prefix test and never an equality.
    `SHA_PREFIX` is the floor under it, and an unreadable `HEAD` matches nothing.
    """
    return bool(head) and len(recorded) >= SHA_PREFIX and head.startswith(recorded)
