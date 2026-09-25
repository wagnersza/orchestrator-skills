#!/usr/bin/env python3
"""Answer what the **Worker watch** asks about one worker, in three subcommands.

All three are the same question at a different moment. *Is a real agent at work in
this worktree, and does that work need a decision now?* Readiness asks it before
the first prompt. `phase` asks it and prints the answer. `tick` asks it and applies
the answer. One seam answers all three, for every tool and every harness (ADR 0019).

**This module reads a worktree, a process and a git repository, and nothing else reads
them.** The question that comes before every worker is *may this work item start at
all?*, and it belongs to `scripts/worker_queue.py`, which is a graph walk over one
tracker read. **Neither file imports the other.** What the two share is the **Tracker
adapter** in `scripts/tracker.py`, which holds every tracker command, the **Work-state
label** family and the flags that name one tracker.

**`ready`** — is a live agent process running with its working directory inside
this worktree? Exit 0 ready, non-zero not:

    python3 <plugin root>/scripts/worker_state.py ready --worktree /path/to/worktree \\
        --process '<the pattern the harness reference gives>'

**`phase`** — read three facts on disk and two on the tracker, and answer one
question: *is a transition due for this work item?* This is the plan half of the
seam, and it writes nothing at all:

    python3 <plugin root>/scripts/worker_state.py phase --item 62 \\
        --worktree /path/to/worktree \\
        --process '<the pattern the harness reference gives>' \\
        --stall-after 30m --repo OWNER/NAME \\
        --require-gate '<one command per required layer, from the Config>'

| Code | Meaning |
|---|---|
| 0 | a transition is due — the printed line names which one |
| 1 | nothing to do on this tick, so the run records as skipped |
| 3 | the worktree is gone — nothing left to watch |

**The code is the predicate and the line is the diagnosis.** Zero means a
transition is due, whichever one it is, so a caller reads one bit. The line names
one outcome from the table that follows, and the computed **Position** decides
which of them a tick can reach:

| Outcome | The fact that fires it |
|---|---|
| `implementation-complete` | every box in the **Checklist** is ticked, and the **Gate record** proves every required layer green at `HEAD` |
| `gates-unproven` | the checklist reads complete, and the gate record does not prove it |
| `merged` | the pull request whose head is this worktree's branch reads `MERGED` |
| `dead` | no live agent process with its working directory inside the worktree |
| `stalled` | a live process, and a spawn and work product both older than `--stall-after` |
| `unreadable` | the tracker read failed, so no fact is available |

**No outcome here reads a reviewer's opinion.** An **Adversarial review** is a verb the
maintainer asks for, and the reviewer posts one comment for a human to read. A judgement
has no exit code, so it can never be the input of a deterministic gate (ADR 0066).

**A re-prompt count is the number of `Re-prompt:` comments on the work item.** Nothing
stores it, so a restart reads the number a maintainer reads. The bound is one and it is not
an argument: a bound a caller can raise is a climb, and no rung is a fact a machine can
read (ADR 0058).

**This tick computes the position, and it reads one label to do that.** `position_of`
answers where the item sits in its run, from the **Work-state label**s alone. The rule has
one home, the Position entry of `orchestrator/CONTEXT.md`, and this module restates no part
of it.

**A position of human review reads one fact more: the pull request for this worktree's
branch.** A `MERGED` pull request is the `merged` outcome, and it is a whole **Close
transaction**. An open pull request is a quiet tick, and a branch with no pull request at
all is a quiet tick too. So the maintainer merges on the tracker, and no verb carries their
words (ADR 0057).

**`needs-human` answers before every fact except the tracker read.** The tick reads that
label and exits quiet, whatever the checklist and the process say. Only the maintainer
removes that label, so a paused item costs one cheap read a minute.

`unreadable` is the one outcome no **Position** gates, because a read that
failed cannot say where the item sits. It is an outcome and not a silence:
a broken read for 21 ticks must not look like 21 quiet minutes. This seam writes no
label for it, because a fact it never read cannot decide one.

`dead` and `stalled` can never both fire, because `dead` is the absence of the live
process `stalled` needs. `dead` needs no stall window, so it reports in about a
minute (ADR 0022).

`gates-unproven` fires in place of `implementation-complete`, and
only where `--require-gate` names a command. So it needs a ticked checklist, and it
can never compete with `dead` or `stalled`: both of those need an unticked one before
a tick reaches them. Four causes fire it, and the printed line names which — a missing
file, a missing line, a non-zero exit and a stale `head_sha`. The four ask for four
different repairs.

**The record is a record, and not a second enforcement mechanism.** No hook blocks a
push and no script rejects a commit. The item stops before review instead, and the
session re-prompts the worker (ADR 0036).

The two signals are work product, so neither can report success for a dead worker
(ADR 0018). Every worker a tick watches is an implementation worker, so no flag carries
a role:

- **complete** — every box in `.orchestrator/checklist-<item>.md` is ticked, **and** the
  **Gate record** in `.orchestrator/gates-<item>.jsonl` holds a green line for every layer
  `--require-gate` names, at the current `HEAD`. A ticked box is a claim, and the
  record is the fact behind it (ADR 0036).
- **stalled** — the stall window starts at the newest of three
  facts, and it is older than `--stall-after`: the spawn's own write of the brief,
  the checklist file's write time, and the branch's last commit time. **The spawn is
  in that list so that a fresh worker is never stalled** (ADR 0063). A worktree
  inherits the default branch's commit, which the worker never made, and that commit
  is often older than the window at the moment of the spawn. This
  is the freshness of work product, not the liveness of a shell.

**The tracker CLI is an argument.** `--tracker-cli` picks which command reads the
labels and the comments. `--tracker-host` names the server where the tracker is
self-hosted. The caller resolves both from `docs/agents/issue-tracker.md`, the same
way it resolves every other configuration value. `main` builds one **Tracker adapter**
from those two values, `--repo` and `--gh-fixture`. Every function in this module takes
that one object. The adapter in `scripts/tracker.py` holds every command, so this seam
names no tracker at all (ADR 0040). A project on the other tracker then needs no
wrapper script outside this repo.

**The adapter is what makes the predicate callable.** Four values that describe one
tracker ran down five call levels. Three constructions built the adapter from them, each
from a different subset. Nothing at the call site named the four, so a reordered pair
type-checked, ran, and printed a plausible line.

One object replaces the four, and every argument past the fifth is named at each call. A
test builds one adapter over a fixture file and asks `phase` directly. This suite does
that for every outcome, so the command line is no longer the only way in.

**`tick`** — the same question through the same code path, and then the write. This is
the execute half, and it is the whole body of an **Item automation** tick:

    python3 <plugin root>/scripts/worker_state.py tick --item 62 \\
        <every phase flag above>

| Code | Meaning |
|---|---|
| 1 | a quiet tick, so the run records as skipped |
| 2 | refused — an outcome is due, and this seam carries the work no further |
| 3 | the worktree is gone — nothing left to watch |
| 4 | applied — the printed line names the transition and the labels it wrote |

**No path exits 0.** An **Item automation** starts its agent on exit 0 alone, so
every tick records as skipped and the schedule's own prompt and provider never
load. No agent runs on a tick.

**The tick applies the transition it computed.** It stops printing an outcome for a
session to act on, and it stops delivering that line to a terminal. A status the session
never writes is a status it cannot forget to write. Three outcomes carry a transition, and
every other row of the table above writes nothing:

| Outcome | What the tick writes |
|---|---|
| `implementation-complete` | the review state, in one label swap |
| `merged` | steps 4 to 8 of a **Close transaction**, through `scripts/close_item.py` in this process |
| `stalled` | one `Re-prompt:` comment under the bound, and `needs-human` at it |
| every other outcome | nothing, so the item stays where it is, and the code is 2 |

**A stalled worker gets one re-prompt, and then a human.** The count is the number of
`Re-prompt:` comments on the work item. The first stalled tick posts one of those comments,
which carries what it saw and the unticked boxes, and the item stays where it is. The second
writes `needs-human` and re-prompts nothing. So no rung is climbed and no model diagnoses a
terminal it cannot see (ADR 0058). `dead` keeps its own answer, because nothing listens
there and a re-prompt cannot reach a process that is gone.

**The finish has one behaviour, and nothing holds its write.** A ticked checklist with a
green **Gate record** hands the item to a human, whatever else the project configures. An
**Adversarial review** is a verb outside this loop, so no policy flag reaches this seam
(ADR 0066).

**One function owns every work-state label swap in this seam**, and it runs in the
process that already read the labels. So no second read can disagree with the first, and
a grep for a label write finds no second path. **The removals and the addition are one
tracker write**, so they can never land apart and an item is never left wearing two work
states. **The removals are computed from the labels the tick read**, and never from a
hardcoded predecessor. That is what makes the one-label answer hold from every legal
starting position.

**A tick applies at most one transition per run.** One tick reads one item, computes one
outcome and makes at most one label swap. That is half of what bounds a seam that now
writes the tracker every minute with nobody watching. The other half is `needs-human`,
which stops every tick on that item.

**`phase` and `tick` compute through one code path.** `phase` is the plan and `tick` is
the execute, the same split `scripts/close_item.py` holds. So a test reads a decision with
no mutation, and a maintainer dry-runs one item against a live tracker before trusting the
write.

**`tick --claim` is the one named transition this seam reaches from the CLI.** It swaps
the ready state for the in-progress state on one work item, and computes nothing. An
**Orchestrator** session claims an item this way, so a claim runs the same writer a tick
runs and no session assembles a label command of its own:

    python3 <plugin root>/scripts/worker_state.py tick --claim --item 62 \\
        --repo OWNER/NAME \\
        --board-project '<the number the tracker file gives>' \\
        --board-owner '<the owner the tracker file gives>'

A claim reads `needs-human` first, the same as every other path here, and it refuses
where the item wears it. It reads no worktree and no process, so it needs none of the
worker flags. Every other form of `tick` still requires all four.

**The card moves with the label, at two of the three moments** (ADR 0067). A claim writes
`In progress`, and the tick that writes `to-review` writes `In review`. The close writes
`Done` itself, after its teardown. So `tick` takes the two board coordinates and no start
column: the start column is the maintainer's own lane, and no tick writes it. **A failed
card write is reported in the printed line and it stops nothing**, because the board is a
mirror and the label is the live state.

**`needs-human` is a transition with a comment.** The writer puts the label on the item
and posts one comment saying what the seam saw. A label with no reason leaves the
maintainer to reconstruct one. Only the maintainer removes the label. A close that could not
run writes it, and so does a stall that already spent its one retry.

**What this seam refuses to do.** It composes no prompt, kills no process, moves no card
into a lane the maintainer owns, and merges nothing. `Backlog`, `Ready` and the start column
stay theirs. **The merge stays the maintainer's own act**, and this seam only reads
its result. It holds no state that changes an answer, and it writes no file anywhere, so a
restart after each re-prompt is free.

**One subcommand spawns, and it composes no launch command to do it.** `queue` runs the
`--spawn-command` its caller passed, and it fills the five tokens of one work item into
that string. Every other subcommand spawns nothing.

**It writes one work-state label per run, or one comment, or it runs one close.** The close is the one
destructive act that left a session. It removes the worktree and the schedule of an item
whose pull request is merged. Two gates in `scripts/close_item.py` stand in front of it,
and each one refuses rather than warns. Every other destructive act stays in a session a
human can interrupt.

**The process pattern is an argument.** The caller reads it from
`references/harnesses/<harness>.md`, so this seam names no harness and a sixth
harness stays a Markdown change. Durations are arguments too, so a test needs no
real stall window.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Both invocation forms reach the adapter: `python3 <plugin root>/scripts/worker_state.py`
# puts `scripts/` on the path, and `python3 -m scripts.worker_state` puts the repo root
# there (ADR 0034).
try:
    from . import close_item
    from .tracker import (
        COLUMN_IN_PROGRESS,
        COLUMN_IN_REVIEW,
        IN_PROGRESS,
        NEEDS_HUMAN,
        TO_REVIEW,
        WORK_STATES,
        Tracker,
        TrackerError,
        UsageExitParser,
        add_board_arguments,
        add_tracker_arguments,
        needs_human,
        swap_line,
        write_transition,
    )
except ImportError:  # the type checker reads the package form above
    import close_item  # type: ignore[no-redef, import-not-found]
    from tracker import (  # type: ignore[no-redef, import-not-found]
        COLUMN_IN_PROGRESS,
        COLUMN_IN_REVIEW,
        IN_PROGRESS,
        NEEDS_HUMAN,
        TO_REVIEW,
        WORK_STATES,
        Tracker,
        TrackerError,
        UsageExitParser,
        add_board_arguments,
        add_tracker_arguments,
        needs_human,
        swap_line,
        write_transition,
    )

EXIT_COMPLETE = 0
EXIT_GONE = 3

# `ready` answers one bit, so every not-ready cause shares one code. A worktree
# that is gone keeps code 3, which means one code has one meaning in both
# subcommands.
EXIT_NOT_READY = 1

# `phase` answers one bit too, because a `--precheck` reads one bit (ADR 0022).
# Zero means a transition is due, whichever outcome fired, and the
# printed line is what names it. Every quiet outcome shares code 1, so a tick that
# has nothing to do records as a skipped automation run. A worktree that is gone
# keeps code 3 here as well.
EXIT_DUE = 0
EXIT_NOTHING = 1

# `tick` is that same predicate plus the write it computed, so no path through it can
# exit 0. Exit 0 is what loads an **Item automation**'s provider, and an agent on a tick
# is the cost this subcommand removes. A tick that applied a transition and a tick that
# refused one carry different codes. That difference is the first fact a maintainer needs
# from a run history. A quiet tick and a gone worktree keep the codes
# `phase` gives them, so one code has one meaning in both subcommands.
EXIT_REFUSED = 2
EXIT_APPLIED = 4

# The literal this seam writes on a re-prompt and counts back on the next stall. It is
# quoted here and in `orchestrator/CONTEXT.md`, so a writing pass leaves it byte-identical
# (ADR 0058).
RE_PROMPT = "Re-prompt:"

# A comment counts only where that literal opens a line, which is where this seam writes it.
# A bare substring test counts a review note that quotes the literal, and a maintainer who
# writes about a re-prompt must not spend one.
RE_PROMPTED = re.compile(r"^\s*" + re.escape(RE_PROMPT), re.MULTILINE)

# One re-prompt, and then a human. The bound is not an argument: a bound a caller can raise
# is a climb under another name, and the climb is what ADR 0058 deletes.
RE_PROMPTS = 1

BOX = re.compile(r"^\s*[-*+]\s*\[([ xX])\]")

# The four keys one line of the **Gate record** carries. A line that drops one of them
# is malformed: a run nobody can date, or cannot tie to a commit, proves nothing. The
# format has one home, `references/quality-gates.md` (ADR 0036).
GATE_KEYS = ("command", "exit", "utc", "head_sha")

# The shortest `head_sha` that counts as an identification of a commit. A gate command
# can record a short sha, so the comparison is a prefix test. The floor is what stops a
# one-character value from matching every commit there is.
SHA_PREFIX = 7

UNITS = {"s": 1, "m": 60, "h": 3600}

# The directory a worker's own files live in, inside its worktree: the **Checklist** a
# tick reads and the **Gate record** it reads beside it. This seam writes neither one, and
# it writes no other file anywhere.
ORCHESTRATOR_DIR = ".orchestrator"


def parse_duration(text):
    """Seconds from `90`, `45s`, `30m` or `4h`. A bare number is seconds."""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smh]?)\s*", str(text))
    if not match:
        raise ValueError(
            f"{text!r} is not a duration — write a number of seconds, or a number "
            f"with one of the units {', '.join(sorted(UNITS))}"
        )
    # An index and not `.get()`. The `re.fullmatch` pattern lets through only a unit
    # this map holds. A default would hide a change to that pattern.
    return float(match.group(1)) * UNITS[match.group(2) or "s"]


def human(seconds):
    """A duration a person reads: `45s`, `3m 20s`, `1h 5m`."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {seconds % 3600 // 60}m"


# --- the process check (ADR 0019) -------------------------------------------


def process_cwd(pid):
    """The working directory of `pid`, or an empty string where it is unreadable.

    `/proc/<pid>/cwd` first, because it needs no subprocess. Where there is no
    `/proc`, which is macOS and every BSD, `lsof -a -d cwd -p <pid> -Fn` answers
    the same question. Its `n` line holds the path.
    """
    if Path("/proc").is_dir():
        try:
            return os.readlink(f"/proc/{pid}/cwd")
        except OSError:
            return ""
    proc = subprocess.run(
        ["lsof", "-a", "-d", "cwd", "-p", str(pid), "-Fn"],
        capture_output=True,
        text=True,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("n"):
            return line[1:]
    return ""


def matching_processes(pattern):
    """Every live `(pid, name)` whose process name matches `pattern`.

    The pattern is a regular expression, so a caller that needs an exact name
    passes an anchored one. The process name comes from `ps -o comm=`, and never
    from `pgrep -x`. An agent started with its flags can be absent from
    `pgrep -x` output and present in `ps -o comm=` for the same pid. That is a
    false negative, and it stalls a spawn the gate must let through. The
    measurement is in `references/tools/orca.md`.

    This process is left out of the answer. Otherwise a seam that runs inside the
    worktree it is asked about can report itself as the worker.
    """
    matcher = re.compile(pattern)
    proc = subprocess.run(
        ["ps", "-A", "-o", "pid=,comm="], capture_output=True, text=True
    )
    found = []
    for line in proc.stdout.splitlines():
        pid, _, name = line.strip().partition(" ")
        name = name.strip()
        if not pid.isdigit() or int(pid) == os.getpid():
            continue
        if matcher.search(name):
            found.append((int(pid), name))
    return found


def inside(path, root):
    """Whether `path` is `root` or sits under it, with both links resolved."""
    if not path:
        return False
    resolved = Path(os.path.realpath(path))
    root = Path(os.path.realpath(root))
    return resolved == root or root in resolved.parents


def live_process(worktree, pattern):
    """The first live agent process at work inside this worktree, or None.

    Returns `(pid, name, cwd)`. Two subcommands ask this one question: `ready`
    before the first prompt, and `phase` for the `dead` outcome on every tick. So
    the check is written once and read twice (ADR 0019, ADR 0022).
    """
    for pid, name in matching_processes(pattern):
        cwd = process_cwd(pid)
        if inside(cwd, worktree):
            return pid, name, cwd
    return None


def ready(worktree, pattern):
    """The `ready` answer: one line, and the exit code that goes with it."""
    worktree = Path(os.path.realpath(worktree))
    if not worktree.is_dir():
        return EXIT_GONE, f"gone: there is no worktree at {worktree} — nothing to check"
    found = live_process(worktree, pattern)
    if found:
        pid, name, cwd = found
        return EXIT_COMPLETE, (
            f"ready: pid {pid} ({name}) matches {pattern!r}, and its working "
            f"directory {cwd} is inside {worktree}"
        )
    return EXIT_NOT_READY, (
        f"not ready: no live process that matches {pattern!r} has a working "
        f"directory inside {worktree}"
    )


# --- the Completion signal (ADR 0018) ---------------------------------------


def checklist_path(worktree, item):
    """Where a worker's **Checklist** lives, which is its completion contract."""
    return Path(worktree) / ORCHESTRATOR_DIR / f"checklist-{item}.md"


def boxes(path):
    """`(ticked, total)` for the checkboxes in `path`. `(0, 0)` if it is absent."""
    try:
        text = Path(path).read_text()
    except OSError:
        return 0, 0
    marks = [match.group(1) for line in text.splitlines() if (match := BOX.match(line))]
    return sum(1 for mark in marks if mark != " "), len(marks)


def unticked(path):
    """The first line of each unticked box in `path`, in file order.

    What a re-prompt re-sends. A box in this repo's **Checklist** runs over several lines,
    and the first one carries the step. So the answer is the steps that are left, short
    enough for one comment body (ADR 0058).
    """
    try:
        text = Path(path).read_text()
    except OSError:
        return []
    return [
        line.strip()
        for line in text.splitlines()
        if (match := BOX.match(line)) and match.group(1) == " "
    ]


def re_prompts_in(bodies):
    """How many `Re-prompt:` comments the work item carries.

    The re-prompt count. It is scoped to the item and to nothing else, so no re-spawn
    resets it and a restart reads the number a maintainer reads. Nothing stores it
    (ADR 0058).

    **The literal has to open a line**, which is where this seam writes it. So a review note
    or a maintainer's comment that quotes the literal spends no retry.
    """
    return sum(1 for body in bodies if RE_PROMPTED.search(body or ""))


# --- the Gate record (ADR 0036) ---------------------------------------------


def gate_record_path(worktree, item):
    """Where a worker's **Gate record** lives, beside its **Checklist**."""
    return Path(worktree) / ORCHESTRATOR_DIR / f"gates-{item}.jsonl"


def gate_runs(path):
    """`(runs, malformed)` for the **Gate record** at `path`.

    `runs` holds one dict per readable line, in the order a gate command appended
    them. So the newest run of a command is the last one in the list, and no line
    has to be sorted by its `utc` value.

    `malformed` is the number of the first line that is not one JSON object with the
    four keys, or 0 where every line reads. A blank line is how a text file ends, so
    it is neither a run nor a fault. The walk stops at the first malformed line,
    because one unreadable line puts the lines around it in doubt as well.
    """
    # A line is whatever `json.loads` returns, so the value type is `Any`. The walk
    # that follows narrows it to the four keys.
    runs: list[dict[str, Any]] = []
    try:
        text = Path(path).read_text()
    except OSError:
        return runs, 0
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            run = json.loads(line)
        except ValueError:
            return runs, number
        if not isinstance(run, dict) or any(key not in run for key in GATE_KEYS):
            return runs, number
        try:
            run["exit"] = int(run["exit"])
        except (TypeError, ValueError):
            return runs, number
        run["command"] = str(run["command"])
        run["head_sha"] = str(run["head_sha"])
        runs.append(run)
    return runs, 0


def head_sha(worktree):
    """The commit the worktree is on, or an empty string where there is none."""
    proc = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "--verify", "--quiet", "HEAD"],
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def at_head(recorded, head):
    """Whether a recorded `head_sha` names the commit `head`.

    A gate command can write a short sha, so this is a prefix test and never an
    equality. `SHA_PREFIX` is the floor under it.
    """
    return bool(head) and len(recorded) >= SHA_PREFIX and head.startswith(recorded)


def unproven_gates(worktree, item, required):
    """Why the **Gate record** does not prove this finish, or an empty string.

    Four causes, and the first one that holds is the answer, because the four ask for
    four different repairs: a missing file, a missing line, a non-zero exit, and a
    green run against a stale commit. The line names which one it was.

    With no `--require-gate` there is nothing to prove, so nothing is read and this
    returns nothing. A caller that names no layer keeps the behaviour it had before
    the flag existed (ADR 0036).
    """
    if not required:
        return ""
    path = gate_record_path(worktree, item)
    runs, malformed = gate_runs(path)
    if malformed:
        keys = ", ".join(GATE_KEYS)
        return (
            f"a malformed line — {path} line {malformed} is not one JSON object with "
            f"the keys {keys}, so this tick cannot read the record"
        )
    if not path.is_file():
        return (
            f"a missing file — there is no gate record at {path}, so no gate run has "
            f"left a trace at all"
        )
    head = head_sha(worktree)
    if not head:
        return (
            f"a stale head_sha — {worktree} has no readable HEAD, so no run in {path} "
            f"ties to a commit"
        )
    for command in required:
        mine = [run for run in runs if run["command"] == command]
        if not mine:
            return f"a missing line — {path} holds no run of {command!r}"
        at_this_commit = [run for run in mine if at_head(run["head_sha"], head)]
        if not at_this_commit:
            return (
                f"a stale head_sha — the newest run of {command!r} in {path} names "
                f"{mine[-1]['head_sha']}, and HEAD is {head[:SHA_PREFIX]}"
            )
        code = at_this_commit[-1]["exit"]
        if code != 0:
            return (
                f"a non-zero exit — the newest run of {command!r} in {path} exited "
                f"{code} at HEAD {head[:SHA_PREFIX]}"
            )
    return ""


# --- the stall signal (ADR 0018) --------------------------------------------


def last_commit_time(worktree):
    """The branch's last commit time as a unix timestamp, or None."""
    proc = subprocess.run(
        ["git", "-C", str(worktree), "log", "-1", "--format=%ct"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip().isdigit():
        return None
    return int(proc.stdout.strip())


def newest_work_product(worktree, item):
    """`(timestamp, what it was)` for the freshest work product, or `(None, "")`.

    Two facts, and the newer one wins: the checklist file's write time and the
    branch's last commit time. Where neither is readable there is nothing to
    date, so a stall cannot be proven. A worker that produces no work product at all is
    reported by its absent process instead, which is the `dead` outcome.
    """
    facts = []
    path = checklist_path(worktree, item)
    try:
        facts.append((path.stat().st_mtime, f"the checklist {path.name}"))
    except OSError:
        pass
    commit = last_commit_time(worktree)
    if commit is not None:
        facts.append((float(commit), "the last commit"))
    if not facts:
        return None, ""
    return max(facts)


def prompt_path(worktree, item):
    """Where the worker's own brief lives, beside its **Checklist**."""
    return Path(worktree) / ORCHESTRATOR_DIR / f"prompt-{item}.md"


def spawn_written(worktree, item):
    """When this worker was spawned, or None where there is no brief to read.

    `scripts/spawn_item.py` writes the brief once, at its own step, and no worker
    rewrites it. So the write time of that file is when the worker started, and this
    seam needs no clock of its own.
    """
    try:
        return prompt_path(worktree, item).stat().st_mtime
    except OSError:
        return None


def window_start(worktree, item):
    """`(timestamp, what it was)` for when the stall window starts, or `(None, "")`.

    **The window starts at the later of the spawn and the newest work product**, and
    never at the work product alone (ADR 0063). A worktree is cut from the default
    branch, so it inherits a commit the worker never made. That commit can be hours
    old at the spawn, and no amount of work makes it younger. Measured from it alone,
    a worker one minute into its first turn reads as `stalled` on its first tick.

    So a fresh worker is never stalled, whatever it inherited. A real stall still
    fires, because the window must pass since the spawn as well.

    Where neither fact is readable there is nothing to date, so a stall cannot be
    proven. The `dead` outcome answers that worker instead, and it needs no window.
    """
    facts = []
    newest, source = newest_work_product(worktree, item)
    if newest is not None:
        facts.append((newest, source))
    spawn = spawn_written(worktree, item)
    if spawn is not None:
        facts.append((spawn, f"the spawn {prompt_path(worktree, item).name}"))
    if not facts:
        return None, ""
    return max(facts)


# --- the computed Position --------------------------------------------------

# The two values of a **Position**. The concept has one home, the Position entry of
# `orchestrator/CONTEXT.md`, and this seam restates no part of the rule.
HUMAN_REVIEW = "human-review"
IMPLEMENTATION = "implementation"


def position_of(labels):
    """The **Position** of one work item, computed from facts and cached nowhere.

    Two values, and the rule has one home: the Position entry of
    `orchestrator/CONTEXT.md`. The fact is the one a tick already read, and it is the
    **Work-state label**s on the item.

    **The review-round value retired with the round it named.** It was computed from a
    reviewer's comment, and no seam reads one now. A reviewer's opinion has no exit code,
    so an **Adversarial review** is a verb a maintainer asks for rather than a position
    the loop can reach (ADR 0066).
    """
    return HUMAN_REVIEW if TO_REVIEW in labels else IMPLEMENTATION


def transition(item, worktree, current, pattern, stall_after, required=()):
    """`(outcome, detail)` for the transition this tick is due, or `(None, detail)`.

    `current` is the computed **Position**, and human review never reaches here. The
    order inside a position is the contract. The **Completion signal** is read
    first, so a worker that finished and then exited reads as finished rather than
    as dead. `dead` comes next and needs no stall window. `stalled` comes last and
    needs the live process `dead` is the absence of, so the two never both fire.

    The **Gate record** is read inside that first step, and only where the checklist
    reads complete. So `gates-unproven` fires in place of the finish it cannot prove,
    and it competes with neither of the other two (ADR 0036).

    **Implementation is the one position that reaches here.** Human review is answered
    before this call, and no third position exists (ADR 0066).
    """
    path = checklist_path(worktree, item)
    ticked, total = boxes(path)
    if total and ticked == total:
        unproven = unproven_gates(worktree, item, required)
        if unproven:
            return "gates-unproven", (
                f"{unproven}, and every box in {path} is ticked ({ticked} of {total})"
            )
        return (
            "implementation-complete",
            f"every box in {path} is ticked ({ticked} of {total})",
        )
    waiting = f"{ticked} of {total} boxes ticked"

    found = live_process(worktree, pattern)
    if not found:
        return "dead", (
            f"no live process that matches {pattern!r} has a working directory "
            f"inside {worktree}, and work item #{item} is in {current}"
        )
    pid, name, _ = found

    newest, source = window_start(worktree, item)
    if newest is not None:
        age = time.time() - newest
        if age > stall_after:
            return "stalled", (
                f"pid {pid} ({name}) is alive, and {source} in {worktree} is "
                f"{human(age)} old, against a stall window of {human(stall_after)}"
            )
        freshness = f"{source} is {human(age)} old"
    else:
        freshness = "it has neither a spawn time nor a work product yet"

    return None, (
        f"work item #{item} is in {current} with {waiting}, pid {pid} ({name}) is "
        f"alive, and {freshness}"
    )


# The outcome that reads a **Completion signal** of a ticked **Checklist**. It is the one
# outcome that ends in a label swap, so it is named rather than repeated.
FINISH = "implementation-complete"

# The transition each outcome carries: the **Work-state label** the item ends on. An
# outcome that is absent from this map writes nothing, and the item stays where it is.
# One outcome hands the work to a human, and every other one says something about the
# worker or about the tracker read rather than about the item.
APPLIES = {FINISH: TO_REVIEW}

# The outcome that reads a merged pull request on the item's own branch. It is the one
# outcome whose transition is a whole **Close transaction** rather than a label swap.
MERGED = "merged"

# The outcome that reads a live process with stale work product. It is the one outcome whose
# transition depends on a count, so it is named rather than repeated.
STALLED = "stalled"

# What one tick does with the outcome it computed. `phase` prints the line and stops at
# any of the seven. `tick` maps each one to its own exit code, so a run history names what
# happened without parsing prose.
GONE = "gone"
QUIET = "quiet"
REFUSED = "refused"
APPLIED = "applied"
CLOSE = "close"
RETRY = "retry"
HUMAN = "human"


def decision(disposition, outcome, line, labels=(), add="", pr=0):
    """One tick's answer, in the shape both subcommands read.

    `disposition` is one of the five above. `outcome` is the tick's own word, or an empty
    string where no outcome fired. `line` is the one line to print. `labels` are the
    **Work-state label**s the item wore when this tick read it, and `add` is the label the
    transition puts on. The last two are what an `APPLIED` decision hands to the writer,
    and they are empty on every other one.

    `pr` is the merged pull request a `CLOSE` decision carries, and it is 0 on every other
    one. The close needs the number, and the tick read it from the branch.
    """
    return {
        "disposition": disposition,
        "outcome": outcome,
        "line": line,
        "labels": list(labels),
        "add": add,
        "pr": pr,
    }


def in_human_review(item, worktree, tracker, labels):
    """The answer for an item the maintainer is reading: a close, or a quiet tick.

    **The merge is the second act, and nothing is typed.** A pull request that reads
    `MERGED` is a deterministic fact. So this tick reads that fact, and no verb carries the
    maintainer's words (ADR 0057).

    **The branch is what this tick holds, and never a pull request number.** It watches one
    worktree, so git answers the branch and the **Tracker adapter** answers the pull
    request for it.

    An open pull request is a quiet tick. A branch with no pull request at all is a quiet
    tick too, and neither one is an error. A read that failed is the `unreadable` outcome,
    the same as a failed read of the item.
    """
    branch = close_item.current_branch(worktree)
    if not branch:
        return decision(
            QUIET,
            "",
            f"nothing: git reads no branch in {worktree}, so this tick can find no pull "
            f"request for work item #{item}",
        )
    try:
        pull = tracker.pull_request_for_branch(branch)
    except (TrackerError, OSError, json.JSONDecodeError) as exc:
        cause = " ".join(str(exc).split())
        return decision(
            REFUSED,
            "unreadable",
            f"unreadable: the pull requests for {branch} are unreadable, so this tick "
            f"cannot read whether work item #{item} is merged: {cause}",
            labels=labels,
        )
    state = (pull["state"] or "").upper()
    if state != "MERGED":
        seen = (
            f"pull request #{pull['number']} for {branch} is {state.lower()}"
            if pull["number"]
            else f"no pull request is open for {branch}"
        )
        return decision(
            QUIET,
            "",
            f"nothing: work item #{item} is in human review and {seen}, so no transition "
            f"is due",
        )
    return decision(
        CLOSE,
        MERGED,
        f"{MERGED}: pull request #{pull['number']} for {branch} is merged, so a Close "
        f"transaction is due for work item #{item}",
        labels=labels,
        pr=pull["number"],
    )


def stall_answer(item, detail, bodies, labels):
    """The answer for a stalled worker: one re-prompt, and then a human.

    **The count is the number of `Re-prompt:` comments on the work item**, read from the
    bodies this tick already holds. Under the bound the answer is a re-prompt, and the item
    stays where it is. At the bound the answer is a human, so `needs-human` goes on and every
    later tick leaves the item alone.

    **Nothing here computes a rung.** A bigger model is a judgement about a terminal this
    seam cannot see, and the count no longer resets when a worker is re-spawned (ADR 0058).
    """
    sent = re_prompts_in(bodies)
    if sent >= RE_PROMPTS:
        return decision(
            HUMAN,
            STALLED,
            f"{STALLED}: {detail}, and work item #{item} already carries {sent} of "
            f"{RE_PROMPTS} retries",
            labels=labels,
        )
    return decision(
        RETRY,
        STALLED,
        f"{STALLED}: {detail}, on retry {sent + 1} of {RE_PROMPTS}",
        labels=labels,
    )


def plan(item, worktree, pattern, stall_after, tracker, required=()):
    """What this tick would do, computed and applied by nothing.

    **This is the one code path both subcommands read.** `phase` prints the line and
    stops, and `tick` prints the same line and then applies the write. So a dry run can
    never disagree with the run it stands for, which is the plan and execute split
    `scripts/close_item.py` already holds.

    `tracker` is the built **Tracker adapter**, and not the values it is made of. A caller
    passes the object. So the CLI name, the host, the repository and the fixture are read
    in one place. That is what makes this callable: a test builds one adapter over a
    fixture file and asks the question in process (ADR 0040).

    A worktree that is gone is answered first, so a torn-down worker is never reported as
    a stall. A tracker read that fails comes next, and it is the `unreadable` outcome. No
    **Position** gates that outcome, because a read that failed cannot say where the item
    sits. `needs-human` follows, and it stops the tick whatever the other facts say. The
    computed position comes after that, because it decides which of the other outcomes
    this tick can reach. An item in human review reaches one of them, and that one is the
    merged pull request `in_human_review` reads.
    """
    worktree = Path(os.path.realpath(worktree))
    if not worktree.is_dir():
        return decision(
            GONE,
            "",
            f"gone: there is no worktree at {worktree} — nothing left to watch",
        )

    try:
        labels, bodies = tracker.item_facts(item)
    except (TrackerError, OSError, json.JSONDecodeError) as exc:
        # A tick prints one line. The standard error of a failed command can hold
        # many, so the cause collapses to one.
        cause = " ".join(str(exc).split())
        return decision(
            REFUSED,
            "unreadable",
            f"unreadable: the labels and comments on work item #{item} are unreadable, "
            f"so this tick can read no transition and the item is unobserved: {cause}",
        )

    if NEEDS_HUMAN in labels:
        return decision(
            QUIET,
            "",
            f"nothing: work item #{item} carries the {NEEDS_HUMAN} label, so this tick "
            f"reads no further and only the maintainer clears it",
        )

    current = position_of(labels)
    if current == HUMAN_REVIEW:
        return in_human_review(item, worktree, tracker, labels)

    outcome, detail = transition(
        item, worktree, current, pattern, stall_after, required=required
    )
    if not outcome:
        return decision(QUIET, "", f"nothing: {detail}")
    if outcome == STALLED:
        return stall_answer(item, detail, bodies, labels)
    add = APPLIES.get(outcome, "")
    if not add:
        return decision(REFUSED, outcome, f"{outcome}: {detail}", labels=labels)
    return decision(APPLIED, outcome, f"{outcome}: {detail}", labels=labels, add=add)


# --- the transition writer --------------------------------------------------

# The column each **Work-state label** moves the card to. **The board is a mirror, so the
# card and the label move in the same tick** (ADR 0067). A label that is absent from this
# map moves no card: `needs-human` is a stop rather than a lane, `ready-for-agent` is the
# maintainer's own drag, and the close writes `Done` itself, after its teardown.
#
# **The label swap itself lives with the **Tracker adapter**.** `write_transition` there is
# the one function in this repo that writes a work-state label, and the queue seam writes
# the same family on a failed spawn. So the swap sits where both can reach it and neither
# file imports the other (ADR 0040).
CARD_COLUMNS = {TO_REVIEW: COLUMN_IN_REVIEW}


def card_line(tracker, item, column, board):
    """Write one work item's card, and answer the clause the caller's line carries.

    **A failed card write is reported and it stops nothing** (ADR 0067). The board is a
    mirror of the work, and the work is what the label and the worktree carry. So a board
    that cannot be written leaves a stale card and nothing else: the claim still writes its
    label, and the transition still lands.

    `board` is `(project, owner)`. With either one missing, or with no column to write,
    there is no card to move and the clause is empty. That is the same supported
    configuration the start gate already reads as "the label alone decides".
    """
    project, owner = board
    try:
        wrote = tracker.card_write(item, column, project, owner)
    except (TrackerError, OSError, json.JSONDecodeError) as exc:
        cause = " ".join(str(exc).split())
        return f", and the card write to {column!r} failed: {cause}"
    return f", and {wrote}" if wrote else ""


def asks_for_a_human(tracker, item, labels, saw):
    """Write `needs-human`, and answer `(exit code, the one line to print)`.

    The **Tracker adapter** makes the write and answers the line, because the queue seam
    writes the same label on a failed spawn. The code is this seam's own: a refusal,
    because a seam that asks for a human refused to act. Only the maintainer removes the
    label.
    """
    return EXIT_REFUSED, needs_human(tracker, item, labels, saw)


def re_prompt(item, worktree, tracker, answer):
    """Post one `Re-prompt:` comment on a stalled worker's item, and answer how it went.

    **The comment is the whole write.** It carries what this tick saw and the steps that are
    still unticked, so a session that reads it needs no second read to compose the retry. No
    label moves, because a stalled worker still owns its item.

    **This seam composes no prompt and delivers nothing.** The reset of the worker's context
    and the send stay a session's act, so no transition here depends on a delivery that can
    fail (ADR 0058).

    Returns `(exit code, the one line to print)`. The code is the applied one, because the
    tick wrote the fact the next tick counts.
    """
    path = checklist_path(worktree, item)
    steps = "; ".join(unticked(path)) or "no unticked box"
    tracker.write(
        tracker.comment_argv(
            item,
            f"{RE_PROMPT} {answer['line']}. Reset the worker's context, then re-send these "
            f"steps of {path.name}: {steps}",
        )
    )
    return EXIT_APPLIED, (
        f"{answer['line']} — applied: one {RE_PROMPT} comment on work item #{item}, which "
        f"carries the unticked steps"
    )


def close_transaction(item, worktree, tracker, answer, close_flags, board=(0, "")):
    """Run steps 4 to 8 of a **Close transaction**, and answer how the run went.

    **The close runs in this process.** This function imports `scripts/close_item.py` and
    calls its plan and its execute, rather than running it as a second process. So one
    **Tracker adapter** serves both seams, and one read of the item serves both. The plan
    the close emits becomes the line this tick prints, so the exit code and the reason stay
    together.

    **That seam keeps its five steps and their order, and this function adds none.** The
    dirty-tree refusal is its own, and it protects uncommitted work, which has no reflog.

    **A refusal writes `needs-human` with one comment.** The comment carries the plan's own
    reason, so a dirty tree names its files and the maintainer repairs the one thing that
    stopped the close.

    `close_flags` is `(checkout, default branch, teardown command)`. **The checkout and the
    teardown command are both conditions for a close, and neither one has a default.** With
    one of them missing this tick closes nothing and names the flag it wants.

    A teardown that removes no schedule leaves a schedule that ticks against a closed item.
    And **step 5 cannot run inside the item's worktree**: that worktree is a linked one, and
    `git fetch origin <branch>:<branch>` there exits 128 with `refusing to fetch into
    branch`, because the sibling checkout holds that branch. So the checkout is where the
    merge lands, and it is never this worktree.

    `board` is `(project, owner)`, and it rides into that seam's own namespace. **The close
    writes `Done` itself, after its teardown**, so this function writes no card of its own
    (ADR 0067).
    """
    checkout, default_branch, teardown_command = close_flags
    missing = [
        flag
        for flag, value in (
            ("--checkout", checkout),
            ("--teardown-command", teardown_command),
        )
        if not value
    ]
    if missing:
        return EXIT_REFUSED, (
            f"{answer['line']} — refused: this tick carries no {', '.join(missing)}, so it "
            f"closes nothing and work item #{item} stays where it is"
        )
    args = argparse.Namespace(
        issue=item,
        pr=answer["pr"],
        repo=checkout,
        default_branch=default_branch,
        worktree=str(worktree),
        remove_label=[name for name in WORK_STATES if name in answer["labels"]],
        add_label=[],
        close_comment=(
            f"pull request #{answer['pr']} is merged, so the tick closed this work item"
        ),
        teardown_command=teardown_command,
        teardown=True,
        execute=True,
        board_project=board[0],
        board_owner=board[1],
    )
    try:
        closing = close_item.build(args, tracker)
    # The same four causes the tick's own reads catch. `close_item.build` makes three more
    # tracker reads, and a command that exits 0 with no JSON raises out of the parser. A
    # traceback here would exit 1, which is the code a quiet tick already owns.
    except (
        close_item.GitError,
        TrackerError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        cause = " ".join(str(exc).split())
        return asks_for_a_human(
            tracker,
            item,
            answer["labels"],
            f"the close of work item #{item} could not be planned: {cause}",
        )
    code = close_item.execute(closing, tracker)
    ran = ", ".join(
        f"{entry['step']} {entry['name']} {entry['status']}"
        for entry in closing["steps"]
    )
    if code != close_item.EXIT_OK:
        reason = (
            (closing.get("refused") or {}).get("reason")
            or closing.get("error")
            or "the close transaction did not complete"
        )
        return asks_for_a_human(
            tracker, item, answer["labels"], f"{reason} The plan ran: {ran}"
        )
    return EXIT_APPLIED, f"{answer['line']} — applied: the close ran: {ran}"


def claim(item, tracker, board=(0, "")):
    """The `--claim` answer: the ready state swapped for the in-progress state.

    The one named transition this seam reaches from the CLI, so an **Orchestrator**
    session's spawn claim runs the same writer a tick runs. It computes nothing and reads
    no worktree, because a claim happens before there is any work to read.

    `needs-human` answers first here too, so a claim can never restart an item the machine
    was asked to leave alone.

    **The card moves to `In progress` here, and the label follows it** (ADR 0067). The card
    write comes after the `needs-human` read and before the label, so a paused item's card
    never moves and a card in the start column always means no worker has taken the item.
    `board` is `(project, owner)`, and with either one missing no card moves.
    """
    try:
        labels, _ = tracker.item_facts(item)
    except (TrackerError, OSError, json.JSONDecodeError) as exc:
        cause = " ".join(str(exc).split())
        return EXIT_REFUSED, (
            f"unreadable: the labels on work item #{item} are unreadable, so this claim "
            f"can write no label: {cause}"
        )
    if NEEDS_HUMAN in labels:
        return EXIT_REFUSED, (
            f"refused: work item #{item} carries the {NEEDS_HUMAN} label, so no claim "
            f"runs until the maintainer clears it"
        )
    card = card_line(tracker, item, COLUMN_IN_PROGRESS, board)
    removed, added = write_transition(tracker, item, labels, IN_PROGRESS)
    return EXIT_APPLIED, f"claim: applied: {swap_line(item, removed, added)}{card}"


# --- the two subcommands over that one plan ---------------------------------


def phase(item, worktree, pattern, stall_after, tracker, required=()):
    """The `phase` answer: `(exit code, the one line to print)`.

    The plan half of the seam, so it writes nothing at all: no tracker command and no
    file. Exit 0 means a transition is due, whichever outcome fired, and the line names
    it. So a caller reads one bit and a maintainer dry-runs one item against a live
    tracker.
    """
    answer = plan(item, worktree, pattern, stall_after, tracker, required=required)
    if answer["disposition"] == GONE:
        return EXIT_GONE, answer["line"]
    if answer["disposition"] == QUIET:
        return EXIT_NOTHING, answer["line"]
    return EXIT_DUE, answer["line"]


def tick(
    item,
    worktree,
    pattern,
    stall_after,
    tracker,
    required=(),
    close_flags=("", "main", ""),
    board=(0, ""),
):
    """The `tick` answer: `(exit code, the one line to print)`.

    The execute half. It reads the same plan `phase` reads, and then it applies the one
    transition that plan carries. **At most one transition per run**: one tick reads one
    item, computes one outcome and makes at most one label swap. So a wrong computation
    cannot cascade inside one minute.

    **The `merged` outcome is the one transition that is not a label swap.** It is a whole
    **Close transaction**, and `close_transaction` runs it in this process.

    **The `stalled` outcome is the one transition a count decides.** Under the bound it is
    one `Re-prompt:` comment and no label. At the bound it is `needs-human`, and the code is
    the refusal because a seam that asks for a human refused to act (ADR 0058).

    An outcome with no transition is a refusal, and the item stays where it is. Three
    facts reach that branch:

    1. A **Gate record** that is not green at `HEAD`.
    2. A dead worker, which no re-prompt can reach.
    3. A tracker read that failed.

    Each one keeps its printed line, so a maintainer reads which it was.

    **The card moves with the label, in this same tick** (ADR 0067). `CARD_COLUMNS` maps the
    label the transition writes to the column the card moves to, and the finish is the one
    transition in that map. A refusal moves no card, and neither does a re-prompt. The close
    writes its own column, after its teardown.
    """
    answer = plan(item, worktree, pattern, stall_after, tracker, required=required)
    if answer["disposition"] == GONE:
        return EXIT_GONE, answer["line"]
    if answer["disposition"] == QUIET:
        return EXIT_NOTHING, answer["line"]
    if answer["disposition"] == CLOSE:
        return close_transaction(item, worktree, tracker, answer, close_flags, board)
    if answer["disposition"] == RETRY:
        return re_prompt(item, worktree, tracker, answer)
    if answer["disposition"] == HUMAN:
        return asks_for_a_human(tracker, item, answer["labels"], answer["line"])
    if answer["disposition"] == REFUSED:
        return EXIT_REFUSED, (
            f"{answer['line']} — refused: this seam writes no label for "
            f"{answer['outcome']}, so work item #{item} stays where it is"
        )
    removed, added = write_transition(tracker, item, answer["labels"], answer["add"])
    card = card_line(tracker, item, CARD_COLUMNS.get(answer["add"], ""), board)
    return EXIT_APPLIED, (
        f"{answer['line']} — applied: {swap_line(item, removed, added)}{card}"
    )


# --- CLI --------------------------------------------------------------------


def add_tick_arguments(parser, worker_required=True):
    """Every flag the plan reads, added to one subcommand.

    `phase` and `tick` both take all of them, because the two read one plan. Written
    once, so the two can never drift apart.

    `worker_required` is False for `tick`, because `tick --claim` names one transition
    and reads no worker at all. Every other form of `tick` still needs the three, and
    `main` is where that check lives. So a flag with a typo still exits 64.
    """
    parser.add_argument("--item", required=True, type=int, help="the work item number")
    parser.add_argument(
        "--worktree", required=worker_required, help="the worker's worktree"
    )
    parser.add_argument(
        "--process",
        required=worker_required,
        metavar="PATTERN",
        help="a regular expression for the agent's process name. The `dead` outcome "
        "fires when no process that matches it works inside the worktree. The caller "
        "reads it from references/harnesses/<harness>.md, so this seam names no "
        "harness",
    )
    parser.add_argument(
        "--stall-after",
        required=worker_required,
        metavar="DURATION",
        help="how old the newest work product must be to count as a stall "
        "(`45s`, `30m`, `4h`, or a bare number of seconds). Only `stalled` reads it, "
        "because `dead` needs no window",
    )
    add_tracker_arguments(parser)
    parser.add_argument(
        "--require-gate",
        action="append",
        metavar="COMMAND",
        help="one gate command this item's finish must prove green at HEAD. "
        "Repeat the flag once per required layer. The caller resolves the list from the "
        "gates: block of the Config, so this seam names no command of its own. With no "
        "--require-gate nothing is required, and gates-unproven can never fire",
    )


def main(argv=None):
    parser = UsageExitParser(
        # The usage block prints the command that ran. So a reader copies a form
        # that resolves from their own working directory. The module form resolves
        # only at the plugin root
        # (orchestrator/docs/adr/0034-the-seam-invocation-carries-a-resolved-plugin-root.md).
        prog=f"python3 {Path(__file__).resolve()}",
        description=(
            "Answer what the Worker watch asks about one worker: is a live agent "
            "process at work in this worktree, and is a transition due for its "
            "work item. The phase subcommand computes and writes nothing. The tick "
            "subcommand computes through the same code path and then applies the one "
            "transition it computed. A merged pull request is one of those transitions, "
            "and it closes the item. The tick also writes the board card that goes with "
            "the label it wrote, and a failed card write stops nothing. It composes no "
            "prompt, kills no process, moves no card into a lane the maintainer owns "
            "and merges nothing. The question before all of these, may this work item "
            "start at all, belongs to scripts/worker_queue.py. That seam is also the one "
            "that spawns."
        ),
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    gate = subcommands.add_parser(
        "ready",
        help="is a live agent process running with its working directory inside "
        "this worktree? Exit 0 ready, non-zero not",
        description=(
            "The readiness gate between the terminal's creation and the first "
            "prompt. It is a process check and not a screen check, because a "
            "screen read reports a live worker for a terminal whose agent has "
            "exited. Exit 0 ready, 1 not ready, 3 the worktree is gone."
        ),
    )
    gate.add_argument("--worktree", required=True, help="the worker's worktree")
    gate.add_argument(
        "--process",
        required=True,
        metavar="PATTERN",
        help="a regular expression for the agent's process name. The caller reads "
        "it from references/harnesses/<harness>.md, so this seam names no harness",
    )

    predicate = subcommands.add_parser(
        "phase",
        help="is a transition due for this work item? Exit 0 due, non-zero "
        "nothing to do. It writes nothing at all",
        description=(
            "The plan half of the seam, and the dry run of a tick. Exit 0 means a "
            "transition is due, and the printed line names which one: "
            "implementation-complete, gates-unproven, merged, "
            "dead, stalled, unreadable. "
            "Exit 1 means nothing to do, so the run records as skipped at no token "
            "cost. Exit 3 means the worktree is gone. It writes no tracker command and "
            "no file, so it can be run against a live tracker. The computed Position "
            "decides which outcomes a tick can reach, and it reads no label of its "
            "own. An item in human review reaches one of them, and that one is merged. "
            "The one outcome no position gates is unreadable, because a "
            "read that failed cannot say where the item sits."
        ),
    )
    add_tick_arguments(predicate)

    applier = subcommands.add_parser(
        "tick",
        help="the whole body of a tick: compute the same transition, then apply it. "
        "No path exits 0",
        description=(
            "The command an Item automation runs as its --precheck. It reads the same "
            "plan the phase subcommand reads, and then it applies the one transition "
            "that plan carries. Exit 4 means applied, and the line names the "
            "transition and the labels it wrote. Where that transition is a merged pull "
            "request, the line carries the plan of the close that ran. A stalled worker "
            "gets one re-prompt comment, and then needs-human. Exit 2 means "
            "refused: an outcome is "
            "due and this seam writes no label for it, so the item stays where it is. "
            "Exit 1 is a quiet tick and exit 3 is a worktree that is gone. No path "
            "exits 0, so every run records as skipped and the automation's own prompt "
            "and provider never load. No agent runs on a tick. At most one transition "
            "lands per run. "
            "The board card moves with the label: a claim writes In progress, and the "
            "tick that writes to-review writes In review. The close writes Done itself, "
            "after its teardown. So this subcommand takes the two board coordinates and "
            "no start column, because the start column is the maintainer's own lane. A "
            "failed card write is reported in the line and it stops nothing. The card "
            "write needs the project scope on the token."
        ),
    )
    add_tick_arguments(applier, worker_required=False)
    add_board_arguments(applier, column=False)
    applier.add_argument(
        "--claim",
        action="store_true",
        help="apply one named transition instead of computing: swap the ready state "
        "for the in-progress state on --item. This is the spawn claim, so a session "
        "runs the same writer a tick runs and assembles no label command of its own. "
        "It moves the card to In progress first, so a card in the start column always "
        "means no worker has taken the item. "
        "It reads no worktree and no process, so it needs none of the four flags that "
        "name a worker",
    )
    applier.add_argument(
        "--checkout",
        default="",
        help="the checkout that receives the merge, where a merged pull request runs a "
        "close. --repo names the tracker project, so the checkout takes an argument of its "
        "own. It is never the item's worktree: that worktree is a linked one, and git "
        "refuses to fetch into a branch a sibling checkout holds. With no value a merged "
        "pull request closes nothing, and the tick says so",
    )
    applier.add_argument(
        "--default-branch",
        default="main",
        help="the branch the merge landed on, which the close pulls into (default: main)",
    )
    applier.add_argument(
        "--teardown-command",
        default="",
        help="the command that removes the automation and the worktree, with the ids "
        "already in it. The caller reads it from its tool reference, so this seam holds no "
        "command of its own. With no value a merged pull request closes nothing, because a "
        "close with no teardown leaves a schedule that ticks against a closed item",
    )

    args = parser.parse_args(argv)

    if args.command == "ready":
        code, line = ready(args.worktree, args.process)
        print(line)
        return code

    # This run builds one **Tracker adapter**, from the four flags that name the
    # tracker. Every read and every write past this point goes through it. So no function
    # past here carries a CLI name, a host, a repository or a fixture path (ADR 0040). The
    # construction reads nothing, so an unreadable fixture is still an outcome and never a
    # traceback. `ready` returned above, because it reads a process and no tracker.
    tracker = Tracker(args.tracker_cli, args.tracker_host, args.repo, args.gh_fixture)

    # `phase` and `tick` are the last two subcommands, and they read one plan, so one
    # validation serves both. **A claim reads no worker.** It names one transition and
    # applies it, so `tick --claim` is the one form that can leave the three worker flags
    # out. Every other form still needs all three, and a missing one is a usage error
    # rather than a quiet tick.
    claiming = args.command == "tick" and args.claim
    stall_after = None
    if not claiming:
        missing = [
            flag
            for flag, value in (
                ("--worktree", args.worktree),
                ("--process", args.process),
                ("--stall-after", args.stall_after),
            )
            if value is None
        ]
        if missing:
            parser.error(
                f"{', '.join(missing)}: a tick that computes reads a worker, so every "
                f"one of those flags is required without --claim"
            )
        try:
            stall_after = parse_duration(args.stall_after)
        except ValueError as exc:
            parser.error(str(exc))

    # A repeatable flag with no value is `None`, and the required list is a tuple of
    # every value it carried. So the seam holds no gate command of its own, and a
    # caller that names no layer requires none (ADR 0036).
    required = tuple(args.require_gate or ())

    if claiming:
        code, line = claim(args.item, tracker, (args.board_project, args.board_owner))
        print(line)
        return code

    # `ready` and a claim each returned above, so `phase` and `tick` are the two cases
    # left. The last branch is unconditional rather than a second `if`. That is what
    # keeps a fall-through out of the exit contract: an implicit `None` would exit 0 and
    # read as a due transition.
    #
    # **The three close flags reach `tick` alone.** `phase` runs no close, so it takes
    # none of them and it stays the half that writes nothing at all.
    if args.command == "phase":
        code, line = phase(
            args.item,
            args.worktree,
            args.process,
            stall_after,
            tracker,
            required=required,
        )
    else:
        code, line = tick(
            args.item,
            args.worktree,
            args.process,
            stall_after,
            tracker,
            required=required,
            close_flags=(args.checkout, args.default_branch, args.teardown_command),
            board=(args.board_project, args.board_owner),
        )
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
