#!/usr/bin/env python3
"""Answer what the **Worker watch** asks about one worker, in five subcommands.

Three of them are the same question at a different moment. *Is a real agent at work in
this worktree, and does that work need a decision now?* Readiness asks it before
the first prompt. `phase` asks it and prints the answer. `tick` asks it and applies
the answer. One seam answers all three, for every tool and every harness (ADR 0019).

The other two ask the question that comes before all of them: *may this work item start
at all?* `start` reads the two facts of a story start for one item and prints the answer.
`queue` reads them for every open item, and starts one (ADR 0045).

**`ready`** — is a live agent process running with its working directory inside
this worktree? Exit 0 ready, non-zero not:

    python3 <plugin root>/scripts/worker_state.py ready --worktree /path/to/worktree \\
        --process '<the pattern the harness reference gives>'

**`start`** — read the labels of one work item and its board card, and answer one
question: *may this item start?* It writes nothing at all:

    python3 <plugin root>/scripts/worker_state.py start --item 178 \\
        --repo OWNER/NAME \\
        --board-project '<the number the tracker file gives>' \\
        --board-owner '<the owner the tracker file gives>' \\
        --start-column '<the column name the tracker file gives>'

| Code | Meaning |
|---|---|
| 0 | both facts hold, so this item may start |
| 1 | one fact holds, or neither — the printed line names which |

**A start is two facts, and both are necessary** (ADR 0045). The item carries the ready
state, and its board card sits in the start column. A card in that column with no label
starts nothing. A labelled item whose card sits anywhere else starts nothing either, so
the column before the start column stays the maintainer's own lane.

**Exactly one fact is neither an error nor a refusal.** It is how a maintainer parks a
groomed item, and a forgotten drag reads the same way. So the answer is a quiet code and
a line that names which fact is missing. A queue report names every item in that state,
which is what keeps the disagreement visible.

**With no board coordinates the label alone decides.** A tracker that names no board is a
supported configuration, and its absence is never an error. The three coordinates are
arguments, and the caller reads them from `docs/agents/issue-tracker.md`, so this seam
holds no board of its own. **The board read needs `read:project` on the token and no write
scope**, because nothing here writes a card.

**`queue`** — read the whole queue and start at most one work item. This is the whole
body of a **Repo automation** tick, and it is the one subcommand that spawns:

    python3 <plugin root>/scripts/worker_state.py queue --repo OWNER/NAME \\
        --board-project '<the number the tracker file gives>' \\
        --board-owner '<the owner the tracker file gives>' \\
        --start-column '<the column name the tracker file gives>' \\
        --max-stories 2 --max-workers 4 --parallel-check touches \\
        --spawn-command '<the scripts/spawn_item.py invocation, with its tokens>'

| Code | Meaning |
|---|---|
| 1 | nothing is due — the printed line names why each candidate waits |
| 2 | refused — the spawn failed, so the item wears `needs-human` with one comment |
| 4 | a worker was started — the line names the item and the command that ran |
| 64 | a flag has a typo, or a roof under 1 |

**No path exits 0 here either**, for the same reason `tick` has none. A schedule starts
its agent on exit 0 alone, so every run records as skipped and no model loads on a tick.

The tick reads in one order, and the order is the contract:

| Step | What it reads, and what it decides |
|---|---|
| 1 | one list read answers every open work item, its labels and its body |
| 2 | the worker cap answers first, because it bounds every run at once |
| 3 | the start gate answers each item, over one board read |
| 4 | the candidates are the authorised leaves that nobody owns and nothing blocks |
| 5 | `max_stories` delays a candidate that opens a new **Story run** |
| 6 | the **Touch set** compare delays a candidate that overlaps a live **Worker** |

**One item per tick, always.** A queue that holds ten startable items starts one. A tick
that starts three is a tick that fills a disk while nobody watches. One item a minute is
slow enough for a human to notice and stop it. That is a hard rule and never a tuning
value, so no flag raises it.

**A `user-story` parent is never spawned for the work itself.** It is a spec, so the tick
descends to its unblocked children and spawns one of those. A child that carries the same
label is a nested spec, and the descent continues to the implementable leaves. **The tick
writes no `ready-for-agent` label on any child**, so the rule that only a human writes
that label survives word for word. A child of a live **Story run** needs neither fact.

**The descent reads the same open-blocker predicate the Ready queue reads.** A blocker
absent from the open items is closed, and only a still-open edge blocks. No second
definition of unblocked is written.

**A live Worker is an item wearing the in-progress label, and no process is read.**
`scripts/spawn_item.py` writes that label before the prompt reaches the worker, and a
**Close transaction** takes it off. A live **Story run** is a `user-story` parent that is
owned itself, or one of whose descendants is. So one list read counts both roofs, and the
lower roof wins.

**A delay is never a cancellation.** A full roof and a **Touch set** overlap both leave
the item ready. The next tick with a free slot and no live overlap starts it. So no item is
quietly dropped from the queue (ADR 0046).

**This subcommand writes no work-state label of its own.** The spawn is
`--spawn-command`, and the seam behind it writes the one label at its own step, before
the prompt reaches the worker. So a second tick cannot hand the same item out twice.

**`phase`** — read three facts on disk and two on the tracker, and answer one
question: *is a transition due for this work item?* This is the plan half of the
seam, and it writes nothing at all:

    python3 <plugin root>/scripts/worker_state.py phase --item 62 \\
        --worktree /path/to/worktree \\
        --process '<the pattern the harness reference gives>' \\
        --rounds 3 --stall-after 30m --repo OWNER/NAME \\
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
| `verdict-approve` | the newest `Verdict:` comment reads `approve` |
| `verdict-request-changes` | the newest one reads `request-changes`, inside the round bound |
| `rounds-exhausted` | `--rounds` `Verdict:` comments, and the newest one asks for changes |
| `dead` | no live agent process with its working directory inside the worktree |
| `stalled` | a live process, and work product older than `--stall-after` |
| `unreadable` | the tracker read failed, so no fact is available |

A **Review round** count is the number of `Verdict:` comments on the work item. So
nothing stores a counter, and `--rounds` is the whole bound.

**A re-prompt count is the number of `Re-prompt:` comments on the same item.** It takes that
same shape, so nothing stores it either, and a restart reads the number a maintainer reads.
The bound is one and it is not an argument: a bound a caller can raise is a climb, and no
rung is a fact a machine can read (ADR 0058).

**This tick computes the position, and it reads no label of its own to do that.**
`position_of` answers where the item sits in its run, from the work-state label, the
`Verdict:` comment list and the last write to the **Checklist**. The rule has one home,
the Position entry of `orchestrator/CONTEXT.md`, and this module restates no part of it.

**A position of human review reads one fact more: the pull request for this worktree's
branch.** A `MERGED` pull request is the `merged` outcome, and it is a whole **Close
transaction**. An open pull request is a quiet tick, and a branch with no pull request at
all is a quiet tick too. So the maintainer merges on the tracker, and no verb carries their
words (ADR 0057).

**`needs-human` answers before every fact except the tracker read.** The tick reads that
label and exits quiet, whatever the checklist, the verdicts and the process say. Only the
maintainer removes that label, so a paused item costs one cheap read a minute.

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
(ADR 0018). The item's **Position** names which one a tick reads, so no flag carries
the worker's role:

- **complete** — in implementation, every box in
  `.orchestrator/checklist-<item>.md` is ticked, **and** the **Gate record** in
  `.orchestrator/gates-<item>.jsonl` holds a green line for every layer
  `--require-gate` names, at the current `HEAD`. A ticked box is a claim, and the
  record is the fact behind it (ADR 0036). In a review round, a comment on the work
  item carries a `Verdict:` line whose value is `approve` or `request-changes`.
- **stalled** — in implementation, the newer of the checklist file's
  write time and the branch's last commit time is older than `--stall-after`. This
  is the freshness of work product, not the liveness of a shell. In a review round
  the freshness fact is the newest `Verdict:` comment, and this seam reads no commit
  at all. A reviewer inherits the implementation's commit, so its fresh worktree
  starts life with work product that is already stale. A verdict that exists fires
  its own outcome above. So a review tick that reaches the stall check has no
  verdict, and no stall can be proven. `dead` is the reviewer's signal instead, and
  it needs no window.

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
| `implementation-complete` | the review state, in one label swap. It holds where `--review` says the policy is on |
| `verdict-approve` | the review state, in one label swap |
| `rounds-exhausted` | the review state, in one label swap |
| `merged` | steps 4 to 8 of a **Close transaction**, through `scripts/close_item.py` in this process |
| `stalled` | one `Re-prompt:` comment under the bound, and `needs-human` at it |
| every other outcome | nothing, so the item stays where it is, and the code is 2 |

**A stalled worker gets one re-prompt, and then a human.** The count is the number of
`Re-prompt:` comments on the work item. The first stalled tick posts one of those comments,
which carries what it saw and the unticked boxes, and the item stays where it is. The second
writes `needs-human` and re-prompts nothing. So no rung is climbed and no model diagnoses a
terminal it cannot see (ADR 0058). `dead` keeps its own answer, because nothing listens
there and a re-prompt cannot reach a process that is gone.

**The finish is the one row that can hold its write.** A **Review round** comes next where
`--review` says the policy is on. A worker still owns the item there, so the review state
would read as a lie. The hold prints why, and the item stays where it is. The round's own
verdict writes the review state when the loop concludes.

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
        --repo OWNER/NAME

A claim reads `needs-human` first, the same as every other path here, and it refuses
where the item wears it. It reads no worktree and no process, so it needs none of the
worker flags. Every other form of `tick` still requires all four.

**`needs-human` is a transition with a comment.** The writer puts the label on the item
and posts one comment saying what the seam saw. A label with no reason leaves the
maintainer to reconstruct one. Only the maintainer removes the label. A close that could not
run writes it, and so does a stall that already spent its one retry.

**What this seam refuses to do.** It composes no prompt, kills no process, moves no card
and merges nothing. **The merge stays the maintainer's own act**, and this seam only reads
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
import fnmatch
import json
import os
import re
import shlex
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
    from .tracker import GH, GLAB, Tracker, TrackerError
except ImportError:  # the type checker reads the package form above
    import close_item  # type: ignore[no-redef, import-not-found]
    from tracker import (  # type: ignore[no-redef, import-not-found]
        GH,
        GLAB,
        Tracker,
        TrackerError,
    )

EXIT_COMPLETE = 0
EXIT_GONE = 3

# A usage error must not land on one of the outcomes. `argparse` exits 2 by
# default, which is non-zero, so a flag with a typo reads as a quiet tick and
# records as a skipped run that nobody sees. 64 is `EX_USAGE`, and it sits outside
# the contract above (ADR 0022).
EXIT_USAGE = 64

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

# The literal the review prompt writes and this seam reads. It is quoted in both
# places, so a writing pass leaves it byte-identical (ADR 0018).
VERDICT_VALUES = ("approve", "request-changes")
VERDICT = re.compile(r"Verdict:\**\s*`?(" + "|".join(VERDICT_VALUES) + r")\b")

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


def verdicts_in(bodies):
    """Every `approve` or `request-changes` the comments carry, oldest first.

    The length is the **Review round** number, because one round posts one verdict.
    So the count is read from the tracker and nothing stores a counter (ADR 0022).
    """
    return [match.group(1) for body in bodies if (match := VERDICT.search(body or ""))]


def re_prompts_in(bodies):
    """How many `Re-prompt:` comments the work item carries.

    The re-prompt count, in the shape the **Review round** count already takes. It is
    scoped to the item and to nothing else, so no re-spawn resets it and a restart reads
    the number a maintainer reads. Nothing stores it (ADR 0058).

    **The literal has to open a line**, which is where this seam writes it. So a review note
    or a maintainer's comment that quotes the literal spends no retry.
    """
    return sum(1 for body in bodies if RE_PROMPTED.search(body or ""))


# --- the Touch set (ADR 0046) ------------------------------------------------

TOUCHES_HEADING = re.compile(r"^##\s*Touches\s*$", re.MULTILINE)
NEXT_HEADING = re.compile(r"^##\s", re.MULTILINE)


def heading_block(body, heading):
    """The text under one `##` heading of a work item body, or an empty string.

    Every block a **Work item** carries takes one shape: a heading line, then one entry
    per line, until the next heading or the end of the text. `## Touches`, `## Parent`
    and `## Blocked by` are the three, so one reader serves all of them and no second
    parse of that shape is written.
    """
    match = heading.search(body)
    if not match:
        return ""
    tail = body[match.end() :]
    next_heading = NEXT_HEADING.search(tail)
    return tail[: next_heading.start()] if next_heading else tail


def parse_touches(body):
    """Every path or glob a `## Touches` block names, in the item body's own order.

    The block sits beside `## Blocked by` and `## Parent`, and `heading_block` reads all
    three.

    A body with no block, or a block with no lines under it, answers an empty list.
    `touches_overlap` reads an empty list as risk, so an undeclared item runs alone
    (ADR 0046). This function reads no tracker and no file system. The caller already
    holds the body it passes in.
    """
    entries = []
    for line in heading_block(body, TOUCHES_HEADING).splitlines():
        entry = re.sub(r"^\s*[-*+]\s*", "", line).strip()
        if entry:
            entries.append(entry)
    return entries


def touches_overlap(one, other):
    """Whether two Touch sets name a shared path or glob.

    This function matches each entry with `fnmatch` in both directions, because
    either side can hold the glob. `src/*.py` in one set matches `src/main.py` in the
    other, and the reverse pairing gives the same answer.

    **An empty list on either side is an overlap**, so a work item that declares
    nothing reads as risk and not as safety (ADR 0046). This function reads no
    tracker and no file system, so its test needs no fixture.
    """
    if not one or not other:
        return True
    return any(
        fnmatch.fnmatch(mine, theirs) or fnmatch.fnmatch(theirs, mine)
        for mine in one
        for theirs in other
    )


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
    date, so a stall cannot be proven. That is the reviewer risk ADR 0018
    accepted and ADR 0022 narrows. A healthy reviewer that produces no work
    product still does not read as stalled. A dead one is reported by its absent
    process instead.

    **Only implementation reaches this function.** A review round always has a verdict
    behind it, because that verdict is what computes the position. The verdict fires its
    own outcome first. So a reviewer that has posted none is in implementation here, and
    the commit it inherited is what dates its work.
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


# --- the computed Position --------------------------------------------------

# The **Work-state label** family: one family, four values, and it never stacks. The
# strings and the swap rule are owned by `docs/agents/issue-tracker.md`, the same as every
# other label this seam reads. The whole family is named here because a transition removes
# every value it finds on the item, rather than one hardcoded predecessor.
READY_FOR_AGENT = "ready-for-agent"
IN_PROGRESS = "in-progress"

# The value that means a human is reading the pull request, and the one label a
# **Position** reads.
TO_REVIEW = "to-review"

# The value that stops every tick. Only the maintainer removes it, so a paused item costs
# one cheap read a minute and moves nowhere.
NEEDS_HUMAN = "needs-human"

WORK_STATES = (READY_FOR_AGENT, IN_PROGRESS, TO_REVIEW, NEEDS_HUMAN)


# The three values of a **Position**. The concept has one home, the Position entry of
# `orchestrator/CONTEXT.md`, and this seam restates no part of the rule.
HUMAN_REVIEW = "human-review"
REVIEW_ROUND = "review-round"
IMPLEMENTATION = "implementation"


def checklist_written(worktree, item):
    """When the **Checklist** was last written, or None where there is no file.

    One of the three facts a **Position** reads. The tick already reads the same file
    for the **Completion signal**, so a position needs no fact of its own.
    """
    try:
        return checklist_path(worktree, item).stat().st_mtime
    except OSError:
        return None


def position_of(labels, bodies, written, verdict_written=None):
    """The **Position** of one work item, computed from facts and read from no label.

    Three values, and the rule has one home: the Position entry of
    `orchestrator/CONTEXT.md`. The facts are the ones a tick already read: the
    **Work-state label**s and the `Verdict:` comment list. `written` is the third one,
    and it is when the **Checklist** file was last written.

    `verdict_written` is when the newest `Verdict:` comment arrived. The **Tracker
    adapter** answers comment bodies and no dates, so a tick passes nothing here and a
    verdict that exists reads as a review round. Where a caller does date the verdict, a
    checklist written after it means the fix round started, so the position is
    implementation again.
    """
    if TO_REVIEW in labels:
        return HUMAN_REVIEW
    if not verdicts_in(bodies):
        return IMPLEMENTATION
    if verdict_written is None or written is None or verdict_written > written:
        return REVIEW_ROUND
    return IMPLEMENTATION


def transition(
    item, worktree, current, bodies, rounds, pattern, stall_after, required=()
):
    """`(outcome, detail)` for the transition this tick is due, or `(None, detail)`.

    `current` is the computed **Position**, and human review never reaches here. The
    order inside a position is the contract. The **Completion signal** is read
    first, so a worker that finished and then exited reads as finished rather than
    as dead. `dead` comes next and needs no stall window. `stalled` comes last and
    needs the live process `dead` is the absence of, so the two never both fire.

    The **Gate record** is read inside that first step, and only where the checklist
    reads complete. So `gates-unproven` fires in place of the finish it cannot prove,
    and it competes with neither of the other two (ADR 0036).

    **A review round always answers.** `position_of` reads that position off a
    `Verdict:` comment, so the comment list here can never be empty. One of the three
    verdict outcomes always fires. That is why only implementation reads the checklist,
    the process and the stall window that follow.
    """
    if current == REVIEW_ROUND:
        values = verdicts_in(bodies)
        number = len(values)
        if values[-1] == "approve":
            return "verdict-approve", (
                f"a comment on work item #{item} carries Verdict: approve on "
                f"round {number} of {rounds}"
            )
        if number >= rounds:
            return "rounds-exhausted", (
                f"work item #{item} carries {number} Verdict: comments against a "
                f"round bound of {rounds}, and the newest one asks for changes"
            )
        return "verdict-request-changes", (
            f"a comment on work item #{item} carries Verdict: request-changes on "
            f"round {number} of {rounds}"
        )

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

    newest, source = newest_work_product(worktree, item)
    if newest is not None:
        age = time.time() - newest
        if age > stall_after:
            return "stalled", (
                f"pid {pid} ({name}) is alive, and the newest work product in "
                f"{worktree} is {human(age)} old ({source}), against a stall window "
                f"of {human(stall_after)}"
            )
        freshness = f"its work product is {human(age)} old"
    else:
        freshness = "it has no work product yet"

    return None, (
        f"work item #{item} is in {current} with {waiting}, pid {pid} ({name}) is "
        f"alive, and {freshness}"
    )


# The outcome that reads a **Completion signal** of a ticked **Checklist**. It is the one
# outcome whose transition can hold, so it is named rather than repeated.
FINISH = "implementation-complete"

# The transition each outcome carries: the **Work-state label** the item ends on. An
# outcome that is absent from this map writes nothing, and the item stays where it is.
# Three outcomes hand the work to a human, and every other one says something about the
# worker or about the tracker read rather than about the item.
APPLIES = {
    FINISH: TO_REVIEW,
    "verdict-approve": TO_REVIEW,
    "rounds-exhausted": TO_REVIEW,
}

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


def plan(
    item, worktree, pattern, rounds, stall_after, tracker, required=(), review=False
):
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

    current = position_of(labels, bodies, checklist_written(worktree, item))
    if current == HUMAN_REVIEW:
        return in_human_review(item, worktree, tracker, labels)

    outcome, detail = transition(
        item, worktree, current, bodies, rounds, pattern, stall_after, required=required
    )
    if not outcome:
        return decision(QUIET, "", f"nothing: {detail}")
    if outcome == STALLED:
        return stall_answer(item, detail, bodies, labels)
    if outcome == FINISH and review:
        return decision(
            REFUSED,
            outcome,
            f"{outcome}: {detail}, and the review policy is on, so a Review round comes "
            f"before the review state",
            labels=labels,
        )
    add = APPLIES.get(outcome, "")
    if not add:
        return decision(REFUSED, outcome, f"{outcome}: {detail}", labels=labels)
    return decision(APPLIED, outcome, f"{outcome}: {detail}", labels=labels, add=add)


# --- the transition writer --------------------------------------------------


def write_transition(tracker, item, labels, add, comment=""):
    """Swap the **Work-state label**s on one work item, and answer what it wrote.

    **This is the one function in this seam that writes a work-state label.** It runs in
    the process that already read `labels`, so no second read can disagree with the first.
    A split into another file would add exactly that second read.

    **The removals and the addition are one tracker write.** Both go into one `label_argv`
    call, so they can never land apart and an item is never left wearing two work states.
    **The removals are computed from `labels`**, which is what this run read, and never
    from a hardcoded predecessor. So the one-label answer holds from every legal starting
    position, including an item that already wears the label the transition adds.

    `comment` is the one comment a transition carries where it has something to say. It is
    its own write, because a comment is not a label. `needs-human` is the transition that
    needs one.

    Returns `(removed, added)`: the label names it took off, and the one it put on or an
    empty list. Nothing to remove and nothing to add is no write at all. So an item
    already in the right state costs one read and no command.
    """
    remove = [name for name in WORK_STATES if name in labels and name != add]
    added = [add] if add and add not in labels else []
    if remove or added:
        tracker.write(tracker.label_argv(item, remove=remove, add=added))
    if comment:
        tracker.write(tracker.comment_argv(item, comment))
    return remove, added


def swap_line(item, removed, added):
    """How one label swap reads, for the line a tick prints."""
    was = ", ".join(removed) or "no work-state label"
    now = ", ".join(added) or "the label it already wore"
    return f"{was} → {now} on work item #{item}"


def needs_human(tracker, item, labels, saw):
    """Write `needs-human` on one work item, plus one comment saying what the seam saw.

    The one label that stops every tick, and the one transition that carries a comment. A
    label with no reason leaves the maintainer to reconstruct one, so the comment is part
    of the transition rather than a courtesy.

    Returns `(exit code, the one line to print)`. The code is the refusal, because a seam
    that asks for a human refused to act. Only the maintainer removes the label.
    """
    removed, added = write_transition(
        tracker, item, labels, NEEDS_HUMAN, comment=f"{NEEDS_HUMAN}: {saw}"
    )
    return EXIT_REFUSED, (
        f"{NEEDS_HUMAN}: {saw} — applied: {swap_line(item, removed, added)}, with one "
        f"comment that says what this tick saw"
    )


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


def close_transaction(item, worktree, tracker, answer, close_flags):
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
        return needs_human(
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
        return needs_human(
            tracker, item, answer["labels"], f"{reason} The plan ran: {ran}"
        )
    return EXIT_APPLIED, f"{answer['line']} — applied: the close ran: {ran}"


def claim(item, tracker):
    """The `--claim` answer: the ready state swapped for the in-progress state.

    The one named transition this seam reaches from the CLI, so an **Orchestrator**
    session's spawn claim runs the same writer a tick runs. It computes nothing and reads
    no worktree, because a claim happens before there is any work to read.

    `needs-human` answers first here too, so a claim can never restart an item the machine
    was asked to leave alone.
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
    removed, added = write_transition(tracker, item, labels, IN_PROGRESS)
    return EXIT_APPLIED, f"claim: applied: {swap_line(item, removed, added)}"


# --- the two-facts start gate (ADR 0045) ------------------------------------

# The three answers the start gate gives. `START` is both facts, so the item may start.
# `ONE_FACT` is a card in the start column with no label, which is a forgotten label, and
# it is never an error. `NO_FACT` is every item whose card sits outside that column. A
# groomed item rests there, and a parked one rests there too (ADR 0061).
START = "start"
ONE_FACT = "one-fact"
NO_FACT = "no-fact"

# The phrase a failed board read puts in its detail line. A failed read counts no card, so
# the gate answers `NO_FACT` and starts nothing. That answer is quiet by design, so the
# queue report reads this phrase back to say the board went unread (ADR 0061).
BOARD_UNREAD = "the board read failed"


def start_gate(item, labels, tracker, project=0, owner="", column=""):
    """`(answer, detail)` for whether one work item may start: the two facts of act one.

    Three answers and no fourth: `START`, `ONE_FACT`, `NO_FACT`. **Both facts are
    necessary** (ADR 0045). The first is the ready state, which the caller already read
    this tick. The second is the board card, read through the three coordinates.

    **The card is read first, and the label answers only for a card in `column`** (ADR
    0061). Both facts are still necessary, so the set of items that start does not move.
    What moves is which item a queue report names. The board is the narrower fact of the
    two, and a label outside `column` is the ordinary resting state of a groomed backlog.

    - **`START`** — the item carries the ready state, and its card sits in `column`.
    - **`ONE_FACT`** — its card sits in `column` and it carries no label. That is a
      forgotten label, and it is the one disagreement a maintainer repairs. This is
      **never an error and never a refusal**. A queue report names every item here.
    - **`NO_FACT`** — its card sits outside `column`, whatever the label says. A groomed
      item rests here, and so does one a maintainer parked with the label on. Neither
      needs reporting, because the board already says where each one sits.

    **With no coordinates the label alone decides.** A tracker that names no board is a
    supported configuration, so the board read asks nothing and its absence is never an
    error. The label then answers `START` on its own, and one fact is the whole gate.

    **A board read that fails counts no card**, and it is no error either. Nothing starts
    on a card this seam cannot read, whatever the label says, so the answer is `NO_FACT`
    and the cause rides the detail line. A queue report reads `BOARD_UNREAD` back out of
    that line, so one failed read still names itself on a quiet tick (ADR 0061).

    The board read goes through the same **Tracker adapter** the labels came from, so the
    two reads can never name different repositories. It needs `read:project` on the token
    and no write scope, because nothing writes a card (ADR 0054).
    """
    labelled = READY_FOR_AGENT in labels
    wearing = (
        f"work item #{item} carries the {READY_FOR_AGENT} label"
        if labelled
        else f"work item #{item} carries no {READY_FOR_AGENT} label"
    )
    if not (project and owner and column):
        no_board = "the tracker names no board, so the label alone is the whole gate"
        if labelled:
            return START, f"{wearing}, and {no_board}"
        return NO_FACT, f"{wearing}, and {no_board}. So it starts nothing"

    try:
        status = tracker.board_status(item, project, owner)
    except (TrackerError, OSError, json.JSONDecodeError) as exc:
        # One line is printed, and the standard error of a failed command can hold many,
        # so the cause collapses to one.
        cause = " ".join(str(exc).split())
        return NO_FACT, (
            f"{wearing}, and {BOARD_UNREAD}, so no card is counted and this item "
            f"starts nothing: {cause}"
        )

    carded = status == column
    sits = f"its card sits in the {column!r} column of project {project}"
    elsewhere = (
        f"its card sits in {status!r} rather than {column!r}"
        if status
        else f"it has no card in the {column!r} column"
    )
    if not carded:
        return NO_FACT, f"{wearing}, and {elsewhere}"
    if labelled:
        return START, f"{wearing}, and {sits}"
    return ONE_FACT, f"{wearing}, and {sits}, so it starts nothing"


def start(item, tracker, project=0, owner="", column=""):
    """The `start` answer: `(exit code, the one line to print)`.

    It writes nothing at all, the same as `phase`. Exit 0 means both facts hold, and every
    other answer is the quiet code. So a caller reads one bit, and the printed line names
    which fact is missing.

    **A failed read of the item is quiet too, and it is never a start.** A read that failed
    cannot say the item carries the ready state, so nothing starts on it.
    """
    try:
        labels, _ = tracker.item_facts(item)
    except (TrackerError, OSError, json.JSONDecodeError) as exc:
        cause = " ".join(str(exc).split())
        return EXIT_NOTHING, (
            f"unreadable: the labels on work item #{item} are unreadable, so this gate "
            f"reads no fact and nothing starts: {cause}"
        )
    answer, detail = start_gate(item, labels, tracker, project, owner, column)
    return (EXIT_DUE if answer == START else EXIT_NOTHING), f"{answer}: {detail}"


# --- the queue tick (ADR 0045, ADR 0046) ------------------------------------

# The label that makes a work item a spec rather than a leaf. A story is never spawned
# for the work itself: the tick descends to its children. A child that carries the same
# label is a nested spec, and the descent continues through it.
USER_STORY = "user-story"

# The **Work-state label**s that say somebody already owns the item — a **Worker**, a
# reviewer, or the maintainer. An item wearing one of them is never a queue candidate.
OWNED = (IN_PROGRESS, TO_REVIEW, NEEDS_HUMAN)

# The two values `parallel_check` in the **Config** takes. `TOUCHES` compares the
# declared **Touch set**s before a second item starts, and `OFF` compares nothing, which
# is the behaviour before ADR 0046.
TOUCHES = "touches"
OFF = "off"

# The two Roles a tick can derive, and the one countable `heavy` signal.
# `orchestrator/CONTEXT.md` names four Roles; `role_for` says why the other two are never
# derived. `scripts/spawn_item.py` owns the full list, because it owns the `--role` flag.
HEAVY = "heavy"
MEDIUM = "medium"
HEAVY_TOUCHES = 3

# The two other `##` blocks a **Work item** body carries. Each one takes the shape
# `heading_block` reads, so this seam writes no second parse of it.
PARENT_HEADING = re.compile(r"^##\s*Parent\s*$", re.MULTILINE)
BLOCKED_HEADING = re.compile(r"^##\s*Blocked by\s*$", re.MULTILINE)

# A work-item reference inside one of those blocks. A number the prose of the block
# mentions reads as an edge too, which is the rule
# `orchestrator/references/tracker-reads.md` already records for the blockers.
EDGE = re.compile(r"#(\d+)")

# How many parked items one queue report names. The cap is the one every other report in
# `orchestrator/SKILL.md` takes.
REPORT_CAP = 5

# How a worktree name is built from a title: the number, then the first words of the
# title in lower case. The number leads, so the name says which item the worktree holds.
SLUG_WORDS = 6
NOT_SLUG = re.compile(r"[^a-z0-9]+")

# The two skills a type label routes to. The one mapping is
# `orchestrator/references/skill-routing.md`, and this adds no label family: `bug` is a
# label every tracker ships.
BUG = "bug"
DIAGNOSE_SKILL = "/diagnosing-bugs"
IMPLEMENT_SKILL = "/implement"

# How much of a failed spawn's own output rides the comment a refusal posts. A command
# can print a whole traceback, and a comment carries the first cause rather than all of
# it.
CAUSE_LIMIT = 400


def parse_edges(body, heading):
    """Every work-item number one `##` block of a body names, in the body's own order.

    `## Parent` and `## Blocked by` both carry `#<n>` references, so one reader answers
    both and no second definition of an edge is written. A body with no such block
    answers an empty list.
    """
    return [int(number) for number in EDGE.findall(heading_block(body, heading))]


def parent_of(body):
    """The `## Parent` work item of one body, or 0 where the body names none.

    The edge is the `## Parent` line of the child, per the `to-tickets` template. A body
    that names more than one takes the first, because one child has one parent.
    """
    edges = parse_edges(body, PARENT_HEADING)
    return edges[0] if edges else 0


def open_blockers(item, open_numbers):
    """Every `## Blocked by` edge of one work item that is still open.

    **This is the predicate the Ready queue already reads, and no second definition of
    unblocked is written.** A blocker that is absent from the open items is closed, and
    only a still-open edge blocks.
    """
    return [
        number
        for number in parse_edges(item.get("body", ""), BLOCKED_HEADING)
        if number in open_numbers
    ]


def slug_of(number, title):
    """The worktree name of one work item: the number, then the first words of its title.

    The number leads, so a worktree name says which item it holds and two items with the
    same title still get two names. A title with no word characters answers the number
    alone.
    """
    words = [word for word in NOT_SLUG.split(title.lower()) if word][:SLUG_WORDS]
    return "-".join([str(number), *words])


def skill_for(labels):
    """The skill one work item's type label routes to.

    A verb comes from a person who typed it, and a queue tick has no verb. So the tick
    reads the type label the item already carries, and it resolves to the same skills the
    verb table names. The mapping has one home,
    `orchestrator/references/skill-routing.md`, and this seam restates no other row of
    it.
    """
    return DIAGNOSE_SKILL if BUG in labels else IMPLEMENT_SKILL


def children_of(items):
    """Every open work item's children, keyed by the parent's number.

    One list read answers the whole tree, so the descent makes no read per item.
    """
    found: dict[int, list[int]] = {}
    for item in items:
        parent = parent_of(item["body"])
        if parent:
            found.setdefault(parent, []).append(item["number"])
    return found


def descendants(number, children, seen=None):
    """Every open work item under `number`, at any depth, lowest number first.

    **A nested `user-story` child is descended through too**, down to the implementable
    leaves, which is the rule the `work on N` flow already holds. `seen` guards a body
    that names an ancestor of its own, so a cycle in the edges cannot become a cycle
    here.
    """
    seen = set() if seen is None else seen
    found = []
    for child in children.get(number, ()):
        if child in seen:
            continue
        seen.add(child)
        found.append(child)
        found += descendants(child, children, seen)
    return sorted(found)


def story_above(number, by_number):
    """The nearest open `user-story` ancestor of one work item, or 0.

    The walk follows `## Parent` upward and stops at the first item that carries the
    label. A leaf with no such ancestor belongs to no **Story run**, so it holds no
    **Story slot**.
    """
    seen = {number}
    at = parent_of((by_number.get(number) or {}).get("body", ""))
    while at and at not in seen:
        seen.add(at)
        item = by_number.get(at) or {}
        if USER_STORY in item.get("labels", ()):
            return at
        at = parent_of(item.get("body", ""))
    return 0


def live_workers(items):
    """Every open work item a **Worker** is at work on: the in-progress ones.

    **The label is the fact, and no process is read.** `scripts/spawn_item.py` writes
    that label at its step 5, before the prompt reaches the worker, and a **Close
    transaction** takes it off. So one list read counts every live worker across every
    run, and the tick holds no worktree of its own.
    """
    return [item for item in items if IN_PROGRESS in item["labels"]]


def story_is_live(number, by_number, children):
    """Whether the **Story run** of one `user-story` parent is live.

    A run begins when its first child starts, and it holds its **Story slot** until the
    parent closes, story proof included. The observable fact is a **Work-state label**:
    the run is live where the parent itself is owned, which is the story proof, or where
    one of its descendants is. ADR 0045 names the roof and leaves this count to the seam.

    **A story whose every child has closed reads as no longer live, until the proof
    claims the parent.** That window is a tick or two, and it can free a slot early. A
    slot freed early costs one extra live story, and the worker cap still holds.
    """
    return any(
        name in OWNED
        for one in [number, *descendants(number, children)]
        for name in (by_number.get(one) or {}).get("labels", ())
    )


def startable(number, by_number, open_numbers):
    """Whether one open work item is a leaf this tick can start now.

    Three facts: it is no `user-story` spec, nobody owns it yet, and every
    `## Blocked by` edge of it is closed.
    """
    item = by_number.get(number) or {}
    labels = item.get("labels", ())
    if USER_STORY in labels or any(name in OWNED for name in labels):
        return False
    return not open_blockers(item, open_numbers)


def overlapping_worker(item, live, parallel_check):
    """The first live **Worker** whose **Touch set** overlaps `item`, or 0.

    **With `parallel_check` set to `off` no comparison runs at all**, and the behaviour
    before ADR 0046 stands. Under `touches` the compare reads the `## Touches` block of
    each side, and an empty list on either side is an overlap: an item that declares
    nothing runs alone, because silence reads as risk and not as safety.
    """
    if parallel_check != TOUCHES:
        return 0
    mine = parse_touches(item["body"])
    for worker in live:
        if touches_overlap(mine, parse_touches(worker["body"])):
            return worker["number"]
    return 0


def queue_report(gates):
    """The parked items a queue read names, as one clause of the line a tick prints.

    An item whose card sits in the start column with no label is a forgotten label. It
    otherwise reads as an empty queue, and nothing repairs the disagreement on its own. So
    the count and the first numbers ride the line. **It is never an error and never a
    comment**, and the cap is the one every other report takes (ADR 0045).

    **A card outside the start column is not named here, whatever its label says** (ADR
    0061). That is the resting state of a groomed backlog, so naming it made every tick
    recite the backlog instead of the one item a maintainer acts on.

    A failed board read answers `NO_FACT` for every item, so it names itself instead. One
    clause says so, because a tick that cannot see the board otherwise prints the same
    quiet line as a tick with nothing to do.
    """
    if any(BOARD_UNREAD in detail for _, detail in gates.values()):
        return f". {BOARD_UNREAD}, so no card was counted on this tick"
    parked = sorted(
        number for number, (answer, _) in gates.items() if answer == ONE_FACT
    )
    if not parked:
        return ""
    named = ", ".join(f"#{number}" for number in parked[:REPORT_CAP])
    return f". {len(parked)} item(s) sit in the start column with no label: {named}"


def queue_candidates(items, gates, by_number, children):
    """Every work item this tick can start, lowest number first, and the live stories.

    Returns `(the candidate numbers, the live Story run numbers)`.

    Two roads reach a candidate, and both end at a leaf:

    - **A leaf that holds both facts of a start gate is a candidate on its own.**
    - **A `user-story` parent that holds both facts is never spawned for the work
      itself.** The tick descends to its unblocked children instead, and it writes no
      `ready-for-agent` label on any of them. So the rule that only a human writes that
      label survives word for word.

    **A child of a live Story run needs neither fact**, because act one already happened
    for that story.
    """
    live_stories = {
        item["number"]
        for item in items
        if USER_STORY in item["labels"]
        and story_is_live(item["number"], by_number, children)
    }
    authorised = {
        item["number"]
        for item in items
        if USER_STORY in item["labels"]
        and (gates[item["number"]][0] == START or item["number"] in live_stories)
    }
    from_stories = {
        leaf for story in authorised for leaf in descendants(story, children)
    }
    open_numbers = set(by_number)
    candidates = [
        number
        for number in sorted(open_numbers)
        if (number in from_stories or gates[number][0] == START)
        and startable(number, by_number, open_numbers)
    ]
    return candidates, live_stories


def queue_plan(tracker, board, roofs, parallel_check=TOUCHES):
    """The one work item this tick starts, or None, plus the line that says why.

    **One item per tick, always.** A queue that holds ten startable items starts one. A
    tick that starts three is a tick that fills a disk while nobody watches. One item a
    minute is slow enough for a human to notice and stop it. That is a hard rule and never
    a tuning value, so no flag raises it.

    The order of the reads is the contract:

    1. One list read answers every open work item, its labels and its body.
    2. The worker cap answers first, because it bounds every run at once.
    3. The start gate answers each item, over one board read.
    4. The candidates are the authorised leaves that nobody owns and nothing blocks.
    5. `max_stories` delays a candidate that opens a new **Story run**.
    6. The **Touch set** compare delays a candidate that overlaps a live **Worker**.

    **A delay at step 5 or step 6 cancels nothing.** The next tick with a free slot and
    no live overlap starts that item, so no item is quietly dropped from the queue
    (ADR 0046).
    """
    max_stories, max_workers = roofs
    items = tracker.open_items()
    by_number = {item["number"]: item for item in items}
    children = children_of(items)
    live = live_workers(items)
    if len(live) >= max_workers:
        return None, (
            f"nothing: {len(live)} live worker(s) against a worker cap of "
            f"{max_workers}, so this tick starts nothing"
        )
    gates = {
        item["number"]: start_gate(item["number"], item["labels"], tracker, *board)
        for item in items
    }
    candidates, live_stories = queue_candidates(items, gates, by_number, children)
    report = queue_report(gates)
    if not candidates:
        return None, (
            f"nothing: none of the {len(items)} open work item(s) is startable on this "
            f"tick{report}"
        )
    waiting = []
    for number in candidates:
        story = story_above(number, by_number)
        if story and story not in live_stories and len(live_stories) >= max_stories:
            waiting.append(
                f"#{number} opens a story run past the roof of {max_stories}"
            )
            continue
        clash = overlapping_worker(by_number[number], live, parallel_check)
        if clash:
            waiting.append(f"#{number} overlaps live worker #{clash}")
            continue
        return by_number[number], (
            f"{START}: work item #{number} is the one item this tick starts, with "
            f"{len(live)} of {max_workers} worker(s) and {len(live_stories)} of "
            f"{max_stories} story run(s) live"
        )
    delayed = ". ".join(waiting[:REPORT_CAP])
    return None, f"nothing: every candidate waits — {delayed}{report}"


def role_for(body):
    """The Role one work item's own facts name.

    `orchestrator/CONTEXT.md` names four Roles and says a spawn takes **medium**. It
    takes **heavy** where **one** listed signal fires, and **light** only where **all
    three** listed conditions hold.

    One `heavy` signal is countable: three or more files. The item already declares its
    files, in the `## Touches` block ADR 0046 added, so this reads that block and counts
    it. The other `heavy` signals are prose — a contract, a schema, a code seam, an open
    decision — and a tick cannot read prose. An item that fires only one of those reads
    **medium** here, which is the documented default and the cheaper of the two answers.

    **`light` is never derived.** Two of its three conditions are prose ("criteria fully
    enumerated", "no open decision"), and the vocabulary needs all three. So a one-file
    item reads **medium**, and a maintainer who wants `light` spawns it by hand. A Role
    guessed one rung too low burns a round trip; a Role guessed one rung too high only
    costs tokens.
    """
    return HEAVY if len(parse_touches(body)) >= HEAVY_TOUCHES else MEDIUM


def fill_spawn(template, item):
    """`--spawn-command` with every token of one work item filled in.

    Six tokens, and each one is a value only this tick holds: `{item}`, `{slug}`,
    `{title}`, `{body}`, `{skill}` and `{role}`. **The title and the body arrive
    shell-quoted**, because an item body holds quotes, newlines and backticks and the
    command runs through a shell. A token the template does not use is never replaced.

    **`{role}` exists so that one schedule can start items of different classes.** With
    no token the Role would be a literal in the stored command string, and every item the
    loop ever started would take that one Role. The skill body calls one model for a whole
    batch a defect, so the automatic loop must not hold it.

    **This composes no launch command.** The whole invocation is the caller's own string,
    the way `scripts/close_item.py` takes its teardown command. So this seam holds no
    path to `scripts/spawn_item.py` and no flag of it, and a spawn that grows a flag
    stays a Markdown change.
    """
    values = {
        "item": str(item["number"]),
        "slug": slug_of(item["number"], item["title"]),
        "title": shlex.quote(item["title"]),
        "body": shlex.quote(item["body"]),
        "skill": skill_for(item["labels"]),
        "role": role_for(item["body"]),
    }
    filled = template
    for token, value in values.items():
        filled = filled.replace("{" + token + "}", value)
    return filled


def queue(tracker, board, roofs, spawn_command, parallel_check=TOUCHES):
    """The `queue` answer: `(exit code, the one line to print)`.

    **This subcommand starts a worker, and it writes no work-state label of its own.**
    The spawn is `--spawn-command`, and `scripts/spawn_item.py` runs the seven ordered
    steps behind it. That seam writes the one label, at its step 5 and before the prompt
    reaches the worker. So a second tick cannot hand the same item out twice, and a grep
    for a label write finds no path here.

    **A spawn that failed is a refusal.** The item takes `needs-human` with one comment
    that carries what this tick ran, so the maintainer repairs the one thing that stopped
    it rather than reconstructing a reason.
    """
    try:
        item, line = queue_plan(tracker, board, roofs, parallel_check)
    except (TrackerError, OSError, json.JSONDecodeError) as exc:
        cause = " ".join(str(exc).split())
        return EXIT_REFUSED, (
            f"unreadable: the open work items are unreadable, so this tick reads no "
            f"queue and starts nothing: {cause}"
        )
    if item is None:
        return EXIT_NOTHING, line
    command = fill_spawn(spawn_command, item)
    proc = subprocess.run(command, shell=True, capture_output=True, text=True)
    if proc.returncode != 0:
        cause = " ".join((proc.stderr or proc.stdout).split())[:CAUSE_LIMIT]
        _, refusal = needs_human(
            tracker,
            item["number"],
            item["labels"],
            f"the spawn of work item #{item['number']} exited {proc.returncode}: "
            f"{cause}",
        )
        return EXIT_REFUSED, f"{line} — {refusal}"
    return EXIT_APPLIED, f"{line} — applied: the spawn ran: {command}"


# --- the two subcommands over that one plan ---------------------------------


def phase(
    item, worktree, pattern, rounds, stall_after, tracker, required=(), review=False
):
    """The `phase` answer: `(exit code, the one line to print)`.

    The plan half of the seam, so it writes nothing at all: no tracker command and no
    file. Exit 0 means a transition is due, whichever outcome fired, and the line names
    it. So a caller reads one bit and a maintainer dry-runs one item against a live
    tracker.
    """
    answer = plan(
        item,
        worktree,
        pattern,
        rounds,
        stall_after,
        tracker,
        required=required,
        review=review,
    )
    if answer["disposition"] == GONE:
        return EXIT_GONE, answer["line"]
    if answer["disposition"] == QUIET:
        return EXIT_NOTHING, answer["line"]
    return EXIT_DUE, answer["line"]


def tick(
    item,
    worktree,
    pattern,
    rounds,
    stall_after,
    tracker,
    required=(),
    review=False,
    close_flags=("", "main", ""),
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

    An outcome with no transition is a refusal, and the item stays where it is. Four facts
    reach that branch:

    1. A **Gate record** that is not green at `HEAD`.
    2. A dead worker, which no re-prompt can reach.
    3. A fix round, which is still the same worker's own work.
    4. A tracker read that failed.

    Each one keeps its printed line, so a maintainer reads which it was.
    """
    answer = plan(
        item,
        worktree,
        pattern,
        rounds,
        stall_after,
        tracker,
        required=required,
        review=review,
    )
    if answer["disposition"] == GONE:
        return EXIT_GONE, answer["line"]
    if answer["disposition"] == QUIET:
        return EXIT_NOTHING, answer["line"]
    if answer["disposition"] == CLOSE:
        return close_transaction(item, worktree, tracker, answer, close_flags)
    if answer["disposition"] == RETRY:
        return re_prompt(item, worktree, tracker, answer)
    if answer["disposition"] == HUMAN:
        return needs_human(tracker, item, answer["labels"], answer["line"])
    if answer["disposition"] == REFUSED:
        return EXIT_REFUSED, (
            f"{answer['line']} — refused: this seam writes no label for "
            f"{answer['outcome']}, so work item #{item} stays where it is"
        )
    removed, added = write_transition(tracker, item, answer["labels"], answer["add"])
    return EXIT_APPLIED, (
        f"{answer['line']} — applied: {swap_line(item, removed, added)}"
    )


# --- CLI --------------------------------------------------------------------


class UsageExitParser(argparse.ArgumentParser):
    """An `argparse` parser whose usage errors stay outside the exit contract.

    `add_subparsers` builds each subcommand from `type(self)`, so both
    subcommands inherit this without naming it.
    """

    def exit(self, status=0, message=None):
        if message:
            self._print_message(message, sys.stderr)
        sys.exit(EXIT_USAGE if status else status)


def add_tracker_arguments(parser):
    """The four flags that name one tracker, added to one subcommand.

    Every subcommand that reads the tracker takes all four, because `main` builds one
    **Tracker adapter** out of them. Written once, so `start`, `phase` and `tick` can never
    drift apart on the tracker they read (ADR 0040).
    """
    parser.add_argument(
        "--repo",
        default="",
        help="the tracker repository the labels and the verdict comments sit on, as "
        "OWNER/NAME",
    )
    parser.add_argument(
        "--tracker-cli",
        default=GH,
        choices=(GH, GLAB),
        help="which CLI reads the labels and the comments, and writes the label a "
        "transition swaps. The caller resolves it from "
        "docs/agents/issue-tracker.md. This seam passes the name to the tracker "
        "adapter, which holds every command, so this seam names no tracker",
    )
    parser.add_argument(
        "--tracker-host",
        default="",
        metavar="HOST",
        help="the tracker host, for a server the CLI does not reach by default. Each "
        "read carries it in the place that read needs. With no host, every read goes "
        "to the CLI's own default server",
    )
    parser.add_argument(
        "--gh-fixture",
        help="JSON that stands in for any tracker read, so a verdict and a position "
        "need no network and no login (used by the tests). It keeps this name "
        "because scripts/close_item.py reads the same file in the same format",
    )


def add_board_arguments(parser):
    """The three coordinates that name one board, added to one subcommand.

    `start` reads one card and `queue` reads one per open item, so both take all three.
    Written once, so the two can never drift apart on the board they read. With any one of
    them missing the label alone decides, which is a supported configuration and never an
    error (ADR 0045).
    """
    parser.add_argument(
        "--board-project",
        default=0,
        type=int,
        metavar="NUMBER",
        help="the project number of the board that holds the card. The caller reads it "
        "from the Project board section of docs/agents/issue-tracker.md, so this seam "
        "holds no board of its own. With this flag missing the label alone decides",
    )
    parser.add_argument(
        "--board-owner",
        default="",
        metavar="OWNER",
        help="the owner the board belongs to, from the same section. With this flag "
        "missing the label alone decides",
    )
    parser.add_argument(
        "--start-column",
        default="",
        metavar="NAME",
        help="the name of the start column, from the same section. It is a name and "
        "never an option id, because nothing writes a card. With this flag missing the "
        "label alone decides",
    )


def add_tick_arguments(parser, worker_required=True):
    """Every flag the plan reads, added to one subcommand.

    `phase` and `tick` both take all of them, because the two read one plan. Written
    once, so the two can never drift apart.

    `worker_required` is False for `tick`, because `tick --claim` names one transition
    and reads no worker at all. Every other form of `tick` still needs the four, and
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
        "--rounds",
        required=worker_required,
        type=int,
        metavar="N",
        help="the Review round bound, which the caller resolves from `review.rounds` "
        "in the Config. There is no default, so the bound is never hardcoded here",
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
    parser.add_argument(
        "--review",
        action="store_true",
        help="the review policy is on, which the caller resolves from `review.enabled` "
        "in the Config. A finish then holds the swap to the review state, because a "
        "Review round comes first and a worker still owns the item. With no --review a "
        "finish reaches the review state, which is the policy every other flag assumes",
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
            "work item. The start subcommand answers the question before all of those: "
            "may this work item start at all. It reads two facts, the ready-for-agent "
            "label and the board card, and it writes nothing. The queue subcommand reads "
            "those same two facts for every open item, and starts at most one of them. "
            "The phase subcommand computes and writes nothing. The tick "
            "subcommand computes through the same code path and then applies the one "
            "transition it computed. A merged pull request is one of those transitions, "
            "and it closes the item. It composes no prompt, kills no process, moves no "
            "card and merges nothing. One subcommand spawns, and it runs the spawn "
            "command its caller passed rather than a command of its own."
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

    opener = subcommands.add_parser(
        "start",
        help="may this work item start? Exit 0 both facts, non-zero one fact or "
        "neither. It writes nothing at all",
        description=(
            "The two-facts start gate. A work item may start when it carries the "
            "ready-for-agent label and its board card sits in the start column. Exit 0 "
            "means both facts hold, and the printed line names them. Exit 1 means one "
            "fact holds or neither does, and the line names which one. A one-fact answer "
            "is a parked item or a forgotten drag. A no-fact answer is where a groomed "
            "item rests. "
            "Exactly one fact is never an error and never a refusal, so the column "
            "before the start column stays the maintainer's own lane. With no board "
            "coordinates the label alone decides, and that absence is never an error. "
            "It writes no tracker command and moves no card, so it can be run against a "
            "live tracker. The board read needs read:project on the token and no write "
            "scope."
        ),
    )
    opener.add_argument("--item", required=True, type=int, help="the work item number")
    add_tracker_arguments(opener)
    add_board_arguments(opener)

    queuer = subcommands.add_parser(
        "queue",
        help="read the whole queue and start at most one work item. No path exits 0",
        description=(
            "The whole body of a queue tick. It reads every open work item and applies "
            "the two-facts start gate. It descends through any user-story parent to its "
            "unblocked children. It counts the live story runs and the live workers "
            "against the two roofs. It compares the declared Touch sets against every "
            "live worker. Then it runs --spawn-command for at most one item. "
            "One item per tick is a hard rule and never a tuning value, so no flag "
            "raises it. Exit 4 means a worker was started, and the line names the item "
            "and the command that ran. Exit 1 means nothing is due, and the line names "
            "why each candidate waits. Exit 2 means refused: the spawn failed, so the "
            "item wears needs-human with one comment. Exit 64 is a flag with a typo. No "
            "path exits 0, so every run records as skipped and the schedule's own prompt "
            "and provider never load. "
            "It writes no work-state label of its own: the spawn seam writes the one "
            "label, before the prompt reaches the worker. It moves no card and it "
            "descends into no story it was not handed."
        ),
    )
    add_tracker_arguments(queuer)
    add_board_arguments(queuer)
    queuer.add_argument(
        "--max-stories",
        required=True,
        type=int,
        metavar="N",
        help="the roof on live story runs, which the caller resolves from `max_stories` "
        "in the Config. There is no default, so the roof is never hardcoded here",
    )
    queuer.add_argument(
        "--max-workers",
        required=True,
        type=int,
        metavar="N",
        help="the roof on live workers across every story run, which the caller resolves "
        "from the worker cap in the Config. The lower of the two roofs wins. There is no "
        "default, so the roof is never hardcoded here either",
    )
    queuer.add_argument(
        "--parallel-check",
        default=TOUCHES,
        choices=(TOUCHES, OFF),
        help=f"whether a declared Touch set gates a second spawn, which the caller "
        f"resolves from `parallel_check` in the Config. With {TOUCHES} the tick compares "
        f"the ## Touches block of the candidate against every live worker, and an item "
        f"with no block runs alone. With {OFF} nothing is compared "
        f"(default: {TOUCHES})",
    )
    queuer.add_argument(
        "--spawn-command",
        required=True,
        help="the command that turns one work item into a live worker, which the caller "
        "reads from scripts/spawn_item.py. It takes {item}, {slug}, {title}, {body}, "
        "{skill} and {role}. This tick fills all six, and the title and the body arrive "
        "shell-quoted. {role} is heavy where the item declares three or more paths in its "
        "## Touches block, and medium otherwise, so one schedule starts items of "
        "different classes. So this seam holds no spawn flag of its own and composes no "
        "launch command",
    )

    predicate = subcommands.add_parser(
        "phase",
        help="is a transition due for this work item? Exit 0 due, non-zero "
        "nothing to do. It writes nothing at all",
        description=(
            "The plan half of the seam, and the dry run of a tick. Exit 0 means a "
            "transition is due, and the printed line names which one: "
            "implementation-complete, gates-unproven, merged, "
            "verdict-approve, verdict-request-changes, rounds-exhausted, "
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
            "lands per run."
        ),
    )
    add_tick_arguments(applier, worker_required=False)
    applier.add_argument(
        "--claim",
        action="store_true",
        help="apply one named transition instead of computing: swap the ready state "
        "for the in-progress state on --item. This is the spawn claim, so a session "
        "runs the same writer a tick runs and assembles no label command of its own. "
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

    # **`start` reads no worker at all.** It answers whether an item may start, which is
    # the question before there is any worker to read. So it takes none of the four worker
    # flags, and it returns before the validation that requires them.
    if args.command == "start":
        code, line = start(
            args.item,
            tracker,
            args.board_project,
            args.board_owner,
            args.start_column,
        )
        print(line)
        return code

    # **`queue` reads no worker either.** It answers which item starts next, so it takes
    # none of the four worker flags and it returns before the validation that requires
    # them. The two roofs are its own bounds, and a roof under 1 starts nothing at all.
    # So a bad value is a usage error rather than a silent tick.
    if args.command == "queue":
        for flag, value in (
            ("--max-stories", args.max_stories),
            ("--max-workers", args.max_workers),
        ):
            if value < 1:
                parser.error(f"{flag} must be a roof of 1 or more, not {value}")
        code, line = queue(
            tracker,
            (args.board_project, args.board_owner, args.start_column),
            (args.max_stories, args.max_workers),
            args.spawn_command,
            parallel_check=args.parallel_check,
        )
        print(line)
        return code

    # `phase` and `tick` are the last two subcommands, and they read one plan, so one
    # validation serves both. **A claim reads no worker.** It names one transition and
    # applies it, so `tick --claim` is the one form that can leave the four worker flags
    # out. Every other form still needs all four, and a missing one is a usage error
    # rather than a quiet tick.
    claiming = args.command == "tick" and args.claim
    stall_after = None
    if not claiming:
        missing = [
            flag
            for flag, value in (
                ("--worktree", args.worktree),
                ("--process", args.process),
                ("--rounds", args.rounds),
                ("--stall-after", args.stall_after),
            )
            if value is None
        ]
        if missing:
            parser.error(
                f"{', '.join(missing)}: a tick that computes reads a worker, so every "
                f"one of those flags is required without --claim"
            )
        if args.rounds < 1:
            parser.error(f"--rounds must be a bound of 1 or more, not {args.rounds}")
        try:
            stall_after = parse_duration(args.stall_after)
        except ValueError as exc:
            parser.error(str(exc))

    # A repeatable flag with no value is `None`, and the required list is a tuple of
    # every value it carried. So the seam holds no gate command of its own, and a
    # caller that names no layer requires none (ADR 0036).
    required = tuple(args.require_gate or ())

    if claiming:
        code, line = claim(args.item, tracker)
        print(line)
        return code

    # `ready`, `start` and a claim each returned above, so `phase` and `tick` are the two
    # cases left. The last branch is unconditional rather than a second `if`. That is what
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
            args.rounds,
            stall_after,
            tracker,
            required=required,
            review=args.review,
        )
    else:
        code, line = tick(
            args.item,
            args.worktree,
            args.process,
            args.rounds,
            stall_after,
            tracker,
            required=required,
            review=args.review,
            close_flags=(args.checkout, args.default_branch, args.teardown_command),
        )
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
