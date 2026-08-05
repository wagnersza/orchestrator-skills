#!/usr/bin/env python3
"""Answer the two questions the **Worker watch** asks about one worker.

Both are the same question at two moments: *is a real agent doing real work in
this worktree?* Readiness asks it before the first prompt. The watch asks it
while the work runs. One seam answers both, for every tool and every harness
(ADR 0019).

**`ready`** — is a live agent process running with its working directory inside
this worktree? Exit 0 ready, non-zero not:

    python3 -m scripts.worker_state ready --worktree /path/to/worktree \\
        --process '<the pattern the harness reference gives>'

**`watch`** — block, poll two facts on the file system, and exit with one code per
outcome:

    python3 -m scripts.worker_state watch --item 54 \\
        --worktree /path/to/worktree --done-when checklist \\
        --stall-after 30m --max-wait 4h

| Code | Meaning |
|---|---|
| 0 | complete — the **Completion signal** fired |
| 1 | stalled — no fresh work product inside the stall window |
| 2 | max-wait reached — neither complete nor demonstrably stalled |
| 3 | the worktree is gone — nothing left to watch |

Each exit prints one line that names the outcome. That line and the code are the
only things a caller consumes. A usage error is not one of the four outcomes. It
exits 64 and prints nothing on stdout, so a bad flag can never read as max-wait
reached.

The two signals are work product, so neither can report success for a dead worker
(ADR 0018):

- **complete** — `--done-when checklist`: every box in
  `.orchestrator/checklist-<item>.md` is ticked. `--done-when verdict`: a comment
  on the work item carries a `Verdict:` line whose value is `approve` or
  `request-changes`.
- **stalled** — the newer of the checklist file's write time and the branch's last
  commit time is older than `--stall-after`. This is the freshness of work
  product, not the liveness of a shell.

**What this seam refuses to do.** It composes no prompt, kills no process, writes
no label, moves no card and spawns nothing. Every destructive act stays in a
session a human can interrupt. It holds no state between invocations, which is
what makes a restart after each re-prompt free.

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

EXIT_COMPLETE = 0
EXIT_STALLED = 1
EXIT_MAX_WAIT = 2
EXIT_GONE = 3

# A usage error must not land on one of the four outcomes. `argparse` exits 2 by
# default, which is max-wait, so a flag with a typo reads as a bounded wait that
# expired. 64 is `EX_USAGE`, and it sits outside the contract above.
EXIT_USAGE = 64

# `ready` answers one bit, so every not-ready cause shares one code. A worktree
# that is gone keeps code 3, which means one code has one meaning in both
# subcommands.
EXIT_NOT_READY = 1

# The literal the review prompt writes and this seam reads. It is quoted in both
# places, so a writing pass leaves it byte-identical (ADR 0018).
VERDICT_VALUES = ("approve", "request-changes")
VERDICT = re.compile(
    r"Verdict:\**\s*`?(" + "|".join(VERDICT_VALUES) + r")\b"
)

BOX = re.compile(r"^\s*[-*+]\s*\[([ xX])\]")

UNITS = {"s": 1, "m": 60, "h": 3600}

# ponytail: `gh` is hardcoded, so a verdict is read from GitHub and from no other
# tracker — the same ceiling `scripts/close_item.py` names, and the same upgrade
# path: swap the one command below for its `glab` equivalent, or put a
# `--tracker-cli` argument in front of it. Nothing above it changes, because the
# poll loop does not know which CLI ran.
GH = "gh"


def parse_duration(text):
    """Seconds from `90`, `45s`, `30m` or `4h`. A bare number is seconds."""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smh]?)\s*", str(text))
    if not match:
        raise ValueError(
            f"{text!r} is not a duration — write a number of seconds, or a number "
            f"with one of the units {', '.join(sorted(UNITS))}"
        )
    return float(match.group(1)) * UNITS.get(match.group(2) or "s")


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


def ready(worktree, pattern):
    """The `ready` answer: one line, and the exit code that goes with it."""
    worktree = Path(os.path.realpath(worktree))
    if not worktree.is_dir():
        return EXIT_GONE, f"gone: there is no worktree at {worktree} — nothing to check"
    for pid, name in matching_processes(pattern):
        cwd = process_cwd(pid)
        if inside(cwd, worktree):
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
    return Path(worktree) / ".orchestrator" / f"checklist-{item}.md"


def boxes(path):
    """`(ticked, total)` for the checkboxes in `path`. `(0, 0)` if it is absent."""
    try:
        text = Path(path).read_text()
    except OSError:
        return 0, 0
    marks = [match.group(1) for line in text.splitlines() if (match := BOX.match(line))]
    return sum(1 for mark in marks if mark != " "), len(marks)


def comment_bodies(item, repo, fixture=None):
    """Every comment body on the work item, or a fixture that stands in for them.

    A fixture file (`--gh-fixture`) is how the tests fire a verdict with no
    network and no `gh` login, the same way `scripts/close_item.py` closes an
    item. It holds the bodies keyed by item number:

        {"comments": {"54": ["Verdict: approve", "an earlier note"]}}

    An item absent from the key reads as an item with no comments.
    """
    if fixture:
        data = json.loads(Path(fixture).read_text())
        return list((data.get("comments") or {}).get(str(item)) or [])
    argv = [GH, "issue", "view", str(item), "--json", "comments"]
    if repo:
        argv += ["--repo", repo]
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        raise TrackerError(f"{' '.join(argv)} failed: {proc.stderr.strip()}")
    data = json.loads(proc.stdout or "{}")
    return [entry.get("body") or "" for entry in data.get("comments") or []]


class TrackerError(RuntimeError):
    """A tracker read failed — reported as no verdict yet, never raised past main."""


def verdict_in(bodies):
    """The first `approve` or `request-changes` a comment carries, or None."""
    for body in bodies:
        match = VERDICT.search(body or "")
        if match:
            return match.group(1)
    return None


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
    date, so a stall cannot be proven — which is the reviewer risk `--max-wait`
    carries (ADR 0018).
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


# --- the watch --------------------------------------------------------------


def complete(item, worktree, done_when, repo, fixture, warned):
    """The `complete` line for whichever **Completion signal** was named, or None.

    A tracker read that fails is reported once on stderr, and read as no verdict
    yet. So a read that fails once costs a late report and never a wrong outcome.
    """
    if done_when == "checklist":
        path = checklist_path(worktree, item)
        ticked, total = boxes(path)
        if total and ticked == total:
            return (
                f"complete: every box in {path} is ticked ({ticked} of {total})"
            )
        return None

    try:
        value = verdict_in(comment_bodies(item, repo, fixture))
    except (TrackerError, OSError, json.JSONDecodeError) as exc:
        if not warned:
            warned.append(exc)
            print(
                f"warning: the comments on work item #{item} are unreadable. The "
                f"watch polls on, and --max-wait carries it: {exc}",
                file=sys.stderr,
            )
        return None
    if value:
        return f"complete: a comment on work item #{item} carries Verdict: {value}"
    return None


def watch(
    item,
    worktree,
    done_when,
    stall_after,
    max_wait,
    poll_every,
    repo="",
    fixture=None,
):
    """Block, poll, and return `(exit code, the one line to print)`.

    The order of the four checks is the contract. A worktree that is gone is
    answered first, so a torn-down worker is never reported as a stall. Complete
    comes before stalled, so a worker that finished and then went quiet is
    reported as finished. Max-wait comes last, so it reports only what the three
    signals above cannot answer.
    """
    worktree = Path(os.path.realpath(worktree))
    started = time.time()
    warned = []
    while True:
        if not worktree.is_dir():
            return EXIT_GONE, (
                f"gone: there is no worktree at {worktree} — nothing left to watch"
            )

        line = complete(item, worktree, done_when, repo, fixture, warned)
        if line:
            return EXIT_COMPLETE, line

        newest, source = newest_work_product(worktree, item)
        if newest is not None:
            age = time.time() - newest
            if age > stall_after:
                return EXIT_STALLED, (
                    f"stalled: the newest work product in {worktree} is "
                    f"{human(age)} old ({source}), and the stall window is "
                    f"{human(stall_after)}"
                )

        waited = time.time() - started
        if waited >= max_wait:
            return EXIT_MAX_WAIT, (
                f"max-wait: {human(max_wait)} reached, and worker #{item} is neither "
                f"complete nor demonstrably stalled"
            )
        time.sleep(min(poll_every, max(max_wait - waited, 0)))


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


def main(argv=None):
    parser = UsageExitParser(
        prog="python3 -m scripts.worker_state",
        description=(
            "Answer the two questions the Worker watch asks about one worker: is a "
            "live agent process at work in this worktree, and has that worker "
            "finished or stalled. Reports and never acts — it composes no prompt, "
            "kills no process, writes no label and spawns nothing."
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

    poll = subcommands.add_parser(
        "watch",
        help="block, poll the worker's own work product, and exit with one code "
        "per outcome",
        description=(
            "Poll two facts on the file system until one of four outcomes holds: "
            "0 complete, 1 stalled, 2 max-wait reached, 3 the worktree is gone. "
            "Each exit prints one line naming the outcome. Nothing is held "
            "between invocations, so a restart after a re-prompt is free."
        ),
    )
    poll.add_argument("--item", required=True, type=int, help="the work item number")
    poll.add_argument("--worktree", required=True, help="the worker's worktree")
    poll.add_argument(
        "--done-when",
        required=True,
        choices=("checklist", "verdict"),
        help="which Completion signal this worker's role writes: `checklist` for an "
        "implementation worker, `verdict` for a review worker, which ticks no boxes",
    )
    poll.add_argument(
        "--repo",
        default="",
        help="the tracker repository the verdict comment sits on, as OWNER/NAME. "
        "Only `--done-when verdict` reads it",
    )
    poll.add_argument(
        "--stall-after",
        required=True,
        metavar="DURATION",
        help="how old the newest work product must be to count as a stall "
        "(`45s`, `30m`, `4h`, or a bare number of seconds)",
    )
    poll.add_argument(
        "--max-wait",
        required=True,
        metavar="DURATION",
        help="the bounded maximum wait, so no watch outlives the work it observes",
    )
    poll.add_argument(
        "--poll-every",
        default="30s",
        metavar="DURATION",
        help="how often the two facts are re-read (default: 30s)",
    )
    poll.add_argument(
        "--gh-fixture",
        help="JSON that stands in for the comment read, so a verdict needs no "
        "network (used by the tests)",
    )

    args = parser.parse_args(argv)

    if args.command == "ready":
        code, line = ready(args.worktree, args.process)
        print(line)
        return code

    try:
        durations = [
            parse_duration(value)
            for value in (args.stall_after, args.max_wait, args.poll_every)
        ]
    except ValueError as exc:
        parser.error(str(exc))
    stall_after, max_wait, poll_every = durations

    code, line = watch(
        args.item,
        args.worktree,
        args.done_when,
        stall_after,
        max_wait,
        poll_every,
        args.repo,
        args.gh_fixture,
    )
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
