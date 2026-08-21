#!/usr/bin/env python3
"""Answer what the **Worker watch** asks about one worker, in three subcommands.

Each one is the same question at a different moment. *Is a real agent at work in
this worktree, and does that work need a decision now?* Readiness asks it before
the first prompt. The phase predicate asks it once per **Item automation** tick.
The wake asks it and delivers the answer. One seam answers all three, for every
tool and every harness (ADR 0019).

**`ready`** — is a live agent process running with its working directory inside
this worktree? Exit 0 ready, non-zero not:

    python3 <plugin root>/scripts/worker_state.py ready --worktree /path/to/worktree \\
        --process '<the pattern the harness reference gives>'

**`phase`** — read three facts on disk and two on the tracker, and answer one
question: *is a **Phase** transition due for this work item?* This is the predicate
an **Item automation** runs as its `--precheck`, so it blocks on nothing:

    python3 <plugin root>/scripts/worker_state.py phase --item 62 \\
        --worktree /path/to/worktree \\
        --process '<the pattern the harness reference gives>' \\
        --rounds 3 --stall-after 30m --back-off 15m --repo OWNER/NAME \\
        --require-gate '<one command per required layer, from the Config>'

| Code | Meaning |
|---|---|
| 0 | a transition is due — the printed line names which one |
| 1 | nothing to do on this tick, so the run records as skipped |
| 3 | the worktree is gone — nothing left to watch |

**The code is the predicate and the line is the diagnosis.** Zero means a
transition is due, whichever one it is, so a caller reads one bit. The line names
one of nine outcomes, and the item's own `phase:*` label decides which of them a
tick can reach:

| Outcome | Reachable in | The fact that fires it |
|---|---|---|
| `implementation-complete` | `phase:impl` | every box in the **Checklist** is ticked, and the **Gate record** proves every required layer green at `HEAD` |
| `proof-complete` | `phase:e2e` | the same two facts, in the phase that proves the feature works |
| `gates-unproven` | `phase:impl`, `phase:e2e` | the checklist reads complete, and the gate record does not prove it |
| `verdict-approve` | `phase:review` | the newest `Verdict:` comment reads `approve` |
| `verdict-request-changes` | `phase:review` | the newest one reads `request-changes`, inside the round bound |
| `rounds-exhausted` | `phase:review` | `--rounds` `Verdict:` comments, and the newest one asks for changes |
| `dead` | every phase | no live agent process with its working directory inside the worktree |
| `stalled` | `phase:impl`, `phase:e2e` | a live process, and work product older than `--stall-after` |
| `unreadable` | before the phase is read | the tracker read failed, so no fact is available |

A **Review round** count is the number of `Verdict:` comments on the work item. So
nothing stores a counter, and `--rounds` is the whole bound. A work item with no
`phase:*` label is in human review, where nothing is due.

`unreadable` is the one outcome no `phase:*` label gates, because a read that
failed cannot say which phase the item is in. It is an outcome and not a silence:
a broken read for 21 ticks must not look like 21 quiet minutes. It goes through
the same back-off as every other outcome, so it reports once per window.

`dead` and `stalled` can never both fire, because `dead` is the absence of the live
process `stalled` needs. `dead` needs no stall window, so it reports in about a
minute (ADR 0022).

`gates-unproven` fires in place of `implementation-complete` or `proof-complete`, and
only where `--require-gate` names a command. So it needs a ticked checklist, and it
can never compete with `dead` or `stalled`: both of those need an unticked one before
a tick reaches them. Four causes fire it, and the printed line names which — a missing
file, a missing line, a non-zero exit and a stale `head_sha`. The four ask for four
different repairs.

**The record is a record, and not a second enforcement mechanism.** No hook blocks a
push and no script rejects a commit. The item stops before review instead, and the
session re-prompts the worker (ADR 0036).

`--back-off` suppresses a repeat fire of the same outcome for the same work item.
A marker file in the directory `--marker-dir` names holds that window. One marker
per `(item, outcome)` pair, so a `dead` tick is never suppressed by a
`request-changes` fire a moment earlier. The default directory is
`.orchestrator/` in the watched worktree, so a caller that passes nothing behaves
as it did before the argument existed. With no `--back-off` this subcommand writes
nothing at all.

**The directory is an argument because the watched worktree moves.** A schedule can
follow a work item from the implementation worktree to the reviewer's own worktree.
The markers move with it, and an answered wake then fires again from a fresh
directory. So the caller passes one directory that outlives every such move, and
the markers still die with the work item.

The two signals are work product, so neither can report success for a dead worker
(ADR 0018). The item's phase names which one a tick reads, so no flag carries the
worker's role:

- **complete** — in `phase:impl` and `phase:e2e`, every box in
  `.orchestrator/checklist-<item>.md` is ticked, **and** the **Gate record** in
  `.orchestrator/gates-<item>.jsonl` holds a green line for every layer
  `--require-gate` names, at the current `HEAD`. A ticked box is a claim, and the
  record is the fact behind it (ADR 0036). In `phase:review`, a comment on the work
  item carries a `Verdict:` line whose value is `approve` or `request-changes`.
- **stalled** — in `phase:impl` and `phase:e2e`, the newer of the checklist file's
  write time and the branch's last commit time is older than `--stall-after`. This
  is the freshness of work product, not the liveness of a shell. In `phase:review`
  the freshness fact is the newest `Verdict:` comment, and this seam reads no commit
  at all. A reviewer inherits the implementation's commit, so its fresh worktree
  starts life with work product that is already stale. A verdict that exists fires
  its own outcome above. So a review tick that reaches the stall check has no
  verdict, and no stall can be proven. `dead` is the reviewer's signal instead, and
  it needs no window.

**The tracker CLI is an argument.** `--tracker-cli` picks which command reads the
labels and the comments. `--tracker-host` names the server where the tracker is
self-hosted. The caller resolves both from `docs/agents/issue-tracker.md`, the same
way it resolves every other configuration value. So this seam names a tracker in its
argv builders and nowhere else. A project on the other tracker then needs no
wrapper script outside this repo.

**`wake`** — the whole body of a tick. It asks the same `phase` predicate, and on a
due transition it delivers that printed line itself:

    python3 <plugin root>/scripts/worker_state.py wake --item 62 \\
        <every phase flag above> \\
        --handle '<the orchestrator terminal, from operation 9>' \\
        --title orchestrator \\
        --send-command '<operation 4, with {target} and {text} in it>'

| Code | Meaning |
|---|---|
| 4 | delivered — the printed line names the target that took it |
| 5 | no target took the wake, and the seam prints every failure |
| 1 or 3 | what the predicate answered, so there was nothing to deliver |

**No path exits 0.** An **Item automation** starts its agent on exit 0 alone, so
every tick records as skipped and the schedule's own prompt and provider never
load. No agent runs on a tick. The only tokens the loop spends are the ones the
**Orchestrator** session spends when it answers a wake (ADR 0027).

There are three targets, in this order. The first one that succeeds ends the
delivery:

1. **the terminal handle** (`--handle`), which the caller resolves at spawn.
2. **the terminal title** (`--title`), for a caller that resolved no handle.
3. **a comment on the work item**, through `--tracker-cli`. So a transition is
   recorded late rather than lost (ADR 0022, ADR 0024).

`--send-command` is the template the first two targets use. The caller resolves it
from the tool file's operation 4, so this seam names no tool. `{target}` is where
the terminal goes and `{text}` is where the line goes. This seam splits the
template into arguments before it writes either one in. So no shell reads the line,
and a wake that carries a quote or a space stays one argument.

**Delivery is not action.** The line this seam sends is the line it printed, and
nothing in it was decided here. Every prohibition below holds for `wake` exactly as
it holds for `phase`.

**What this seam refuses to do.** It composes no prompt, kills no process, writes
no label, moves no card and spawns nothing. Every destructive act stays in a
session a human can interrupt. It holds no state that changes an answer, which is
what makes a restart after each re-prompt free. The `--back-off` marker is the one
file it writes. It is a suppression window and not an answer. It changes whether an
outcome is reported again, and never which outcome holds.

**The process pattern is an argument.** The caller reads it from
`references/harnesses/<harness>.md`, so this seam names no harness and a sixth
harness stays a Markdown change. Durations are arguments too, so a test needs no
real stall window.
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

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
# Zero means a transition is due, whichever of the nine outcomes fired, and the
# printed line is what names it. Every quiet outcome shares code 1, so a tick that
# has nothing to do records as a skipped automation run. A worktree that is gone
# keeps code 3 here as well.
EXIT_DUE = 0
EXIT_NOTHING = 1

# `wake` is that same predicate plus the delivery of the line it printed, so no path
# through it can exit 0. Exit 0 is what loads an **Item automation**'s provider, and
# an agent on a tick is the cost this subcommand removes (ADR 0027). A delivered wake
# and an undelivered one both exit non-zero, and they carry different codes because
# that difference is the first fact a maintainer needs from a run history.
EXIT_DELIVERED = 4
EXIT_UNDELIVERED = 5

# The two placeholders `--send-command` carries. The caller resolves that template
# from the tool file's operation 4, so this seam names no tool.
TARGET_TOKEN = "{target}"
TEXT_TOKEN = "{text}"

# The literal the review prompt writes and this seam reads. It is quoted in both
# places, so a writing pass leaves it byte-identical (ADR 0018).
VERDICT_VALUES = ("approve", "request-changes")
VERDICT = re.compile(r"Verdict:\**\s*`?(" + "|".join(VERDICT_VALUES) + r")\b")

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

# The directory a worker's own files live in, inside its worktree: the
# **Checklist** a tick reads, and the back-off markers a fire writes. It is also
# the default for `--marker-dir`.
ORCHESTRATOR_DIR = ".orchestrator"

# The two tracker CLIs a caller can pass to `--tracker-cli`. Each one has its own
# argv builders below, and those three functions are the only place in this file that
# knows one tracker from the other: two of them read the labels and the comments, and
# the third posts one comment as the last wake target. Everything else reads two
# lists.
GH = "gh"
GLAB = "glab"


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


def item_facts(item, repo, fixture=None, cli=GH, host=""):
    """The two tracker facts about a work item: `(labels, comment bodies)`.

    One call, because a **Phase** tick needs both. `--tracker-cli` picks which
    builder below runs, and a read that fails raises `TrackerError` for the
    `unreadable` outcome to report.

    A fixture file (`--gh-fixture`) stands in for the read itself, so the tests
    fire a verdict and a phase with no network and no login. It stands in for
    either tracker, because both builders answer with the same two lists.
    `scripts/close_item.py` takes the same kind of file. It holds both facts keyed
    by item number:

        {"comments": {"54": ["Verdict: approve", "an earlier note"]},
         "labels": {"54": ["in-progress", "phase:review"]}}

    An item that is absent from a key reads as an item with none of that fact. A key
    that is absent reads the same way.
    """
    if fixture:
        data = json.loads(Path(fixture).read_text())
        return (
            list((data.get("labels") or {}).get(str(item)) or []),
            list((data.get("comments") or {}).get(str(item)) or []),
        )
    if cli == GLAB:
        return glab_facts(item, repo, host)
    return gh_facts(item, repo)


class TrackerError(RuntimeError):
    """A tracker read failed — reported as the `unreadable` outcome, never raised
    past `phase`."""


def tracker_read(argv):
    """The standard output of one tracker command, or `TrackerError`.

    The part both builders share, so neither one repeats how a failure is
    reported. The command is in the message, because the line a tick prints is
    what a maintainer reads to fix a broken read.
    """
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        raise TrackerError(f"{' '.join(argv)} failed: {proc.stderr.strip()}")
    return proc.stdout


def gh_facts(item, repo):
    """The two facts from `gh`, which reads both of them in one command."""
    argv = [GH, "issue", "view", str(item), "--json", "comments,labels"]
    if repo:
        argv += ["--repo", repo]
    data = json.loads(tracker_read(argv) or "{}")
    return (
        [entry.get("name") or "" for entry in data.get("labels") or []],
        [entry.get("body") or "" for entry in data.get("comments") or []],
    )


def glab_facts(item, repo, host):
    """The two facts from `glab`, which reads them in two commands.

    The host goes in a different place in each command. That difference is why this
    builder exists, and not one command with a flag:

    - the labels come from `glab issue view <n> -F json -R <host>/<owner>/<name>`,
      where the host is part of the repository argument.
    - the comments come from
      `glab api projects/<owner>%2F<name>/issues/<n>/notes --hostname <host>`,
      where the host is a flag and the project path carries no host at all. A bare
      `owner/name` in that path resolves against the CLI's default server, which
      answers 404 or `Unauthenticated` for a project it does not hold.

    With no `--tracker-host` neither command names a host, so both reads go to the
    CLI's own default server.
    """
    if not repo:
        raise TrackerError(
            "a glab read needs --repo as OWNER/NAME, because the project path is "
            "part of both commands"
        )
    labels_argv = [GLAB, "issue", "view", str(item), "-F", "json"]
    labels_argv += ["-R", f"{host}/{repo}" if host else repo]
    notes_argv = [
        GLAB,
        "api",
        f"projects/{repo.replace('/', '%2F')}/issues/{item}/notes",
    ]
    if host:
        notes_argv += ["--hostname", host]
    issue = json.loads(tracker_read(labels_argv) or "{}")
    notes = json.loads(tracker_read(notes_argv) or "[]")
    return (
        # A label is a plain string on this tracker, and an object on the other one.
        [
            entry if isinstance(entry, str) else entry.get("name") or ""
            for entry in issue.get("labels") or []
        ],
        [entry.get("body") or "" for entry in notes or []],
    )


def verdicts_in(bodies):
    """Every `approve` or `request-changes` the comments carry, oldest first.

    The length is the **Review round** number, because one round posts one verdict.
    So the count is read from the tracker and nothing stores a counter (ADR 0022).
    """
    return [match.group(1) for body in bodies if (match := VERDICT.search(body or ""))]


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


def newest_work_product(worktree, item, current):
    """`(timestamp, what it was)` for the freshest work product, or `(None, "")`.

    Two facts, and the newer one wins: the checklist file's write time and the
    branch's last commit time. Where neither is readable there is nothing to
    date, so a stall cannot be proven. That is the reviewer risk ADR 0018
    accepted and ADR 0022 narrows. A healthy reviewer that produces no work
    product still does not read as stalled. A dead one is reported by its absent
    process instead.

    **In `phase:review` this function reads neither fact.** A reviewer's own verdict
    is its work product, and its fresh worktree holds the implementation's commit and
    the implementation's checklist. Both are stale on the reviewer's first minute, so
    a long first read reported as a stall in about three minutes. A verdict that
    exists fires its own outcome before this function runs. So a review tick that
    gets here has no verdict, and no stall to prove.
    """
    if current == PHASE_REVIEW:
        return None, ""
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


# --- the phase predicate (ADR 0022) -----------------------------------------

# The **Phase** label family. Its strings, their swap rule and their
# `gh label create` lines are owned by `docs/agents/issue-tracker.md`, and the
# concept by the Phase entry of `orchestrator/CONTEXT.md`. This seam reads them and
# writes none of them.
PHASE_IMPL = "phase:impl"
PHASE_REVIEW = "phase:review"
PHASE_E2E = "phase:e2e"
PHASES = (PHASE_IMPL, PHASE_REVIEW, PHASE_E2E)


def phase_of(labels):
    """The one `phase:*` label a work item wears, or an empty string.

    The family is mutually exclusive, so the first match is the answer. An empty
    string means human review, where no transition is due.
    """
    for label in PHASES:
        if label in labels:
            return label
    return ""


def marker_path(marker_dir, item, outcome):
    """Where the back-off marker for one `(item, outcome)` pair lives.

    The directory is an argument (`--marker-dir`), and its default is
    `.orchestrator/` in the watched worktree. So the marker still dies with the
    directory that holds it, and no tool-specific run history enters the answer. One
    file per pair, so a `dead` tick is never suppressed by a `request-changes` fire a
    moment earlier.
    """
    return Path(marker_dir) / f"phase-{item}-{outcome}.fired"


def held_back(marker_dir, item, outcome, back_off):
    """The `suppressed` line where this pair already fired inside the window, or None.

    A fire that is not suppressed refreshes the marker, so the window always runs
    from the last fire. With no `--back-off` nothing is read and nothing is written.
    """
    if not back_off:
        return None
    path = marker_path(marker_dir, item, outcome)
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        age = None
    if age is not None and age < back_off:
        return (
            f"suppressed: {outcome} already fired for work item #{item} "
            f"{human(age)} ago, and the back-off window is {human(back_off)}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    return None


def transition(
    item, worktree, current, bodies, rounds, pattern, stall_after, required=()
):
    """`(outcome, detail)` for the transition this tick is due, or `(None, detail)`.

    The order inside a phase is the contract. The **Completion signal** is read
    first, so a worker that finished and then exited reads as finished rather than
    as dead. `dead` comes next and needs no stall window. `stalled` comes last and
    needs the live process `dead` is the absence of, so the two never both fire.

    The **Gate record** is read inside that first step, and only where the checklist
    reads complete. So `gates-unproven` fires in place of the finish it cannot prove,
    and it competes with neither of the other two (ADR 0036).
    """
    if current == PHASE_REVIEW:
        values = verdicts_in(bodies)
        if values:
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
        waiting = "no Verdict: comment yet"
    else:
        path = checklist_path(worktree, item)
        ticked, total = boxes(path)
        if total and ticked == total:
            unproven = unproven_gates(worktree, item, required)
            if unproven:
                return "gates-unproven", (
                    f"{unproven}, and every box in {path} is ticked "
                    f"({ticked} of {total})"
                )
            outcome = (
                "proof-complete" if current == PHASE_E2E else "implementation-complete"
            )
            return outcome, f"every box in {path} is ticked ({ticked} of {total})"
        waiting = f"{ticked} of {total} boxes ticked"

    found = live_process(worktree, pattern)
    if not found:
        return "dead", (
            f"no live process that matches {pattern!r} has a working directory "
            f"inside {worktree}, and work item #{item} is in {current}"
        )
    pid, name, _ = found

    newest, source = newest_work_product(worktree, item, current)
    if newest is not None:
        age = time.time() - newest
        if age > stall_after:
            return "stalled", (
                f"pid {pid} ({name}) is alive, and the newest work product in "
                f"{worktree} is {human(age)} old ({source}), against a stall window "
                f"of {human(stall_after)}"
            )
        freshness = f"its work product is {human(age)} old"
    elif current == PHASE_REVIEW:
        freshness = "no Verdict: comment dates its work yet, so no stall can be proven"
    else:
        freshness = "it has no work product yet"

    return None, (
        f"work item #{item} is in {current} with {waiting}, pid {pid} ({name}) is "
        f"alive, and {freshness}"
    )


def phase(
    item,
    worktree,
    pattern,
    rounds,
    stall_after,
    repo="",
    fixture=None,
    back_off=None,
    marker_dir=None,
    tracker_cli=GH,
    tracker_host="",
    required=(),
):
    """The `phase` answer: `(exit code, the one line to print)`.

    A worktree that is gone is answered first, so a torn-down worker is never
    reported as a stall. A tracker read that fails comes next, and it is the
    `unreadable` outcome. No phase label gates that outcome, because a read that
    failed cannot say which phase the item is in. The **Phase** label follows,
    because it decides which of the other outcomes this tick can reach.
    """
    worktree = Path(os.path.realpath(worktree))
    if not worktree.is_dir():
        return EXIT_GONE, (
            f"gone: there is no worktree at {worktree} — nothing left to watch"
        )

    markers = Path(marker_dir) if marker_dir else worktree / ORCHESTRATOR_DIR

    def fire(outcome, detail):
        """One fire, through the back-off window every outcome shares."""
        line = held_back(markers, item, outcome, back_off)
        if line:
            return EXIT_NOTHING, line
        return EXIT_DUE, f"{outcome}: {detail}"

    try:
        labels, bodies = item_facts(item, repo, fixture, tracker_cli, tracker_host)
    except (TrackerError, OSError, json.JSONDecodeError) as exc:
        # A tick prints one line. The standard error of a failed command can hold
        # many, so the cause collapses to one.
        cause = " ".join(str(exc).split())
        return fire(
            "unreadable",
            f"the labels and comments on work item #{item} are unreadable, so this "
            f"tick can read no transition and the item is unobserved: {cause}",
        )

    current = phase_of(labels)
    if not current:
        return EXIT_NOTHING, (
            f"nothing: work item #{item} wears no phase:* label, so it is in human "
            f"review and no transition is due"
        )

    outcome, detail = transition(
        item, worktree, current, bodies, rounds, pattern, stall_after, required
    )
    if not outcome:
        return EXIT_NOTHING, f"nothing: {detail}"
    return fire(outcome, detail)


# --- the wake (ADR 0027) ----------------------------------------------------


def comment_argv(item, body, repo, cli=GH, host=""):
    """The argv that posts one comment on a work item, which is wake target three.

    One builder per tracker, for the same reason the two reads above have one each:
    the flag that carries the message differs, and so does the place the host goes.
    One CLI takes an optional repository, and falls back to the one the working
    directory holds. For the other CLI the repository is part of the command.
    """
    if cli == GLAB:
        argv = [GLAB, "issue", "note", str(item), "--message", body]
        if repo:
            argv += ["-R", f"{host}/{repo}" if host else repo]
        return argv
    argv = [GH, "issue", "comment", str(item), "--body", body]
    if repo:
        argv += ["--repo", repo]
    return argv


def send_argv(template, target, text):
    """The argv for one send: the template split, then its placeholders filled.

    The split runs before the substitution, so a wake line that carries a space, a
    quote or a `$` stays one argument. Nothing here reaches a shell.
    """
    return [
        token.replace(TARGET_TOKEN, target).replace(TEXT_TOKEN, text)
        for token in shlex.split(template)
    ]


def attempt(argv):
    """None where this command succeeded, or the one line that says why it did not."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True)
    except OSError as exc:
        return f"{argv[0]} did not start: {exc}"
    if proc.returncode == 0:
        return None
    cause = " ".join(proc.stderr.split()) or "it printed nothing"
    return f"{argv[0]} exited {proc.returncode}: {cause}"


def wake_targets(line, item, handle, title, send_command, repo, cli, host):
    """The wake targets in order, as `(what it is, argv)` pairs.

    The terminal handle first, because the tool issued it and no display string can
    move it. The terminal title second, for a caller that resolved no handle. A
    comment on the work item last, so a transition is recorded late rather than lost
    (ADR 0024). A target with nothing to address stays out of the list. So a caller
    that passes no handle costs no failed send.
    """
    found = []
    for what, target in (
        ("the terminal handle", handle),
        ("the terminal title", title),
    ):
        if send_command and target:
            found.append((f"{what} {target}", send_argv(send_command, target, line)))
    found.append(
        (
            f"a comment on work item #{item}",
            comment_argv(item, line, repo, cli, host),
        )
    )
    return found


def deliver(line, item, handle, title, send_command, repo, cli, host):
    """Deliver one line to the first target that succeeds.

    Returns `(exit code, the lines to print)`. A delivery that fails everywhere
    prints every failure. A maintainer who got no wake has to read why, and the three
    causes ask for three different repairs.
    """
    failures = []
    for what, argv in wake_targets(
        line, item, handle, title, send_command, repo, cli, host
    ):
        why = attempt(argv)
        if why is None:
            return EXIT_DELIVERED, [f"delivered: {line} — {what} took it"]
        failures.append(f"no wake to {what}: {why}")
    return EXIT_UNDELIVERED, [f"undelivered: {line} — no target took it", *failures]


def wake(
    item,
    worktree,
    pattern,
    rounds,
    stall_after,
    repo="",
    fixture=None,
    back_off=None,
    marker_dir=None,
    tracker_cli=GH,
    tracker_host="",
    required=(),
    handle="",
    title="",
    send_command="",
):
    """The `wake` answer: `(exit code, the lines to print)`.

    The whole body of a tick. It asks `phase()`: the same predicate, the same nine
    outcomes, the same order and the same `--back-off` window. Where a transition is
    due it delivers that line itself. Where nothing is due it delivers nothing, and it
    answers exactly what the predicate answered. No path exits 0, so no agent runs on
    a tick (ADR 0027).
    """
    code, line = phase(
        item,
        worktree,
        pattern,
        rounds,
        stall_after,
        repo,
        fixture,
        back_off,
        marker_dir,
        tracker_cli,
        tracker_host,
        required,
    )
    if code != EXIT_DUE:
        return code, [line]
    return deliver(
        line, item, handle, title, send_command, repo, tracker_cli, tracker_host
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


def add_tick_arguments(parser):
    """Every flag the predicate reads, added to one subcommand.

    `phase` and `wake` both take all of them, because `wake` is that predicate plus
    a delivery. Written once, so the two can never drift apart (ADR 0027).
    """
    parser.add_argument("--item", required=True, type=int, help="the work item number")
    parser.add_argument("--worktree", required=True, help="the worker's worktree")
    parser.add_argument(
        "--process",
        required=True,
        metavar="PATTERN",
        help="a regular expression for the agent's process name. The `dead` outcome "
        "fires when no process that matches it works inside the worktree. The caller "
        "reads it from references/harnesses/<harness>.md, so this seam names no "
        "harness",
    )
    parser.add_argument(
        "--rounds",
        required=True,
        type=int,
        metavar="N",
        help="the Review round bound, which the caller resolves from `review.rounds` "
        "in the Config. There is no default, so the bound is never hardcoded here",
    )
    parser.add_argument(
        "--stall-after",
        required=True,
        metavar="DURATION",
        help="how old the newest work product must be to count as a stall "
        "(`45s`, `30m`, `4h`, or a bare number of seconds). Only `stalled` reads it, "
        "because `dead` needs no window",
    )
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
        help="which CLI reads the labels and the comments, and posts the wake comment "
        "where no terminal takes it. The caller resolves it from "
        "docs/agents/issue-tracker.md. So this seam names a tracker in its argv "
        "builders and nowhere else",
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
        "--back-off",
        metavar="DURATION",
        help="how long one outcome stays suppressed after it fires, so an "
        "unanswered wake does not repeat every minute. A marker file per "
        "(item, outcome) pair holds it. With no --back-off this subcommand writes "
        "nothing",
    )
    parser.add_argument(
        "--marker-dir",
        default=None,
        metavar="DIR",
        help="where the --back-off marker files live. The default is .orchestrator/ "
        "inside --worktree, so a caller that passes nothing behaves as it did before "
        "this argument existed. Pass a directory that outlives a move of the watched "
        "worktree. Otherwise an answered wake fires again from a fresh directory",
    )
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
        "--gh-fixture",
        help="JSON that stands in for any tracker read, so a verdict and a phase "
        "need no network and no login (used by the tests). It keeps this name "
        "because scripts/close_item.py takes the same kind of file",
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
            "process at work in this worktree, and is a Phase transition due for its "
            "work item. Reports and never acts — it composes no prompt, kills no "
            "process, writes no label and spawns nothing. Its wake delivers the line "
            "it printed, and every decision stays with the session that reads it."
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

    tick = subcommands.add_parser(
        "phase",
        help="is a Phase transition due for this work item? Exit 0 due, non-zero "
        "nothing to do",
        description=(
            "The predicate an Item automation runs as its --precheck. Exit 0 means a "
            "transition is due, and the printed line names which one. There are "
            "nine: implementation-complete, proof-complete, gates-unproven, "
            "verdict-approve, verdict-request-changes, rounds-exhausted, dead, "
            "stalled, unreadable. "
            "Exit 1 means nothing to do, so the run records as skipped at no token "
            "cost. Exit 3 means the worktree is gone. The item's own phase:* label "
            "decides which outcomes a tick can reach. An item with no phase:* label "
            "is in human review, where nothing is due. The one outcome no label "
            "gates is unreadable, because a read that failed cannot say which phase "
            "the item is in."
        ),
    )
    add_tick_arguments(tick)

    delivery = subcommands.add_parser(
        "wake",
        help="the whole body of a tick: ask the same predicate, and deliver the line "
        "where a transition is due. No path exits 0",
        description=(
            "The command an Item automation runs as its --precheck. It asks the phase "
            "predicate, and on a due transition it delivers the printed line to the "
            "first target that succeeds: the terminal handle, then the terminal "
            "title, then a comment on the work item. Exit 4 means delivered, and the "
            "line names the target that took it. Exit 5 means no target took it, and "
            "every failure is printed. Exit 1 and exit 3 are what the predicate "
            "answered, so there was nothing to deliver. No path exits 0, so every "
            "run records as skipped and the automation's own prompt and provider "
            "never load. No agent runs on a tick."
        ),
    )
    add_tick_arguments(delivery)
    delivery.add_argument(
        "--handle",
        default="",
        help="the orchestrator terminal, as the identifier the tool issued. This is "
        "the first target. The caller resolves it at spawn from operation 9, so this "
        "seam names no tool",
    )
    delivery.add_argument(
        "--title",
        default="",
        help="the orchestrator terminal's title, which is the second target. A title "
        "is a display string that a harness can rename, so it is a second chance and "
        "never the mechanism",
    )
    delivery.add_argument(
        "--send-command",
        default="",
        metavar="TEMPLATE",
        help="how to send one line to a terminal, which the caller resolves from the "
        f"tool file's operation 4. {TARGET_TOKEN} is where the terminal goes and "
        f"{TEXT_TOKEN} is where the line goes. This seam splits the template into "
        "arguments before it writes either one in, so no shell reads the line. With "
        "no template the comment is the only target",
    )

    args = parser.parse_args(argv)

    if args.command == "ready":
        code, line = ready(args.worktree, args.process)
        print(line)
        return code

    # `phase` and `wake` are the other two subcommands, and they share every flag
    # above, so one validation serves both. `required=True` leaves no fourth case, so
    # the last branch is unconditional rather than a third `if`. That is what keeps a
    # fall-through out of the exit contract: an implicit `None` would exit 0 and read
    # as a due transition.
    if args.rounds < 1:
        parser.error(f"--rounds must be a bound of 1 or more, not {args.rounds}")
    try:
        stall_after = parse_duration(args.stall_after)
        back_off = parse_duration(args.back_off) if args.back_off else None
    except ValueError as exc:
        parser.error(str(exc))

    # A repeatable flag with no value is `None`, and the required list is a tuple of
    # every value it carried. So the seam holds no gate command of its own, and a
    # caller that names no layer requires none (ADR 0036).
    required = tuple(args.require_gate or ())

    if args.command == "phase":
        code, line = phase(
            args.item,
            args.worktree,
            args.process,
            args.rounds,
            stall_after,
            args.repo,
            args.gh_fixture,
            back_off,
            args.marker_dir,
            args.tracker_cli,
            args.tracker_host,
            required,
        )
        print(line)
        return code

    if args.send_command:
        try:
            shlex.split(args.send_command)
        except ValueError as exc:
            parser.error(f"--send-command has an unbalanced quote: {exc}")
        for token in (TARGET_TOKEN, TEXT_TOKEN):
            if token not in args.send_command:
                parser.error(
                    f"--send-command must carry both {TARGET_TOKEN} and "
                    f"{TEXT_TOKEN}, and this one has no {token}"
                )
    code, lines = wake(
        args.item,
        args.worktree,
        args.process,
        args.rounds,
        stall_after,
        args.repo,
        args.gh_fixture,
        back_off,
        args.marker_dir,
        args.tracker_cli,
        args.tracker_host,
        required,
        args.handle,
        args.title,
        args.send_command,
    )
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
