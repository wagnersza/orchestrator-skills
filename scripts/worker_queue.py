#!/usr/bin/env python3
"""Answer which work item starts next, in three subcommands.

Two of them ask the question that comes before every worker: *may this work item start at
all?* `start` reads the facts one item's kind owns and prints the answer. `queue` reads
them for every open item, and starts one (ADR 0045, narrowed by ADR 0062 and ADR 0064).

The third answers no question about one item. `report` reads the whole board and names
every gap between it and the labels. **It is the one whole-board read left, and a human
runs it** (ADR 0064).

**This module is a graph walk over one tracker read.** It touches the file system exactly
once, to fire the spawn command of the one item a tick starts. It reads no worktree, no
process and no git repository, so a test of it needs none of the three. The worker watch
in `scripts/worker_state.py` owns all of those, and **neither file imports the other.**
What the two share is the **Tracker adapter** in `scripts/tracker.py`, which holds every
tracker command, the **Work-state label** family and the flags that name one tracker.

**`start`** — read the labels of one work item and its board card, and answer one
question: *may this item start?* It writes nothing at all:

    python3 <plugin root>/scripts/worker_queue.py start --item 178 \\
        --repo OWNER/NAME \\
        --board-project '<the number the tracker file gives>' \\
        --board-owner '<the owner the tracker file gives>' \\
        --start-column '<the column name the tracker file gives>'

| Code | Meaning |
|---|---|
| 0 | the fact this item's kind owns holds, so it may start |
| 1 | a fact is missing — the printed line names which |

**One table answers three rows, and it reads the item's kind first** (ADR 0062, narrowing
ADR 0045). `start` and `queue` both call it, so the two agree on every row (ADR 0064):

| Item kind | What authorises it |
|---|---|
| `user-story` | its card sits in the start column. **No label, ever.** |
| child of an authorised story | it wears `ready-for-agent`, and every `## Blocked by` edge is closed. **Its own column is not read.** |
| standalone leaf | it wears `ready-for-agent`, **and** its own card sits in the start column. |

**A story is a spec, and no worker implements one.** So one drag of the story card
authorises the whole run. The `ready-for-agent` label then keeps its one meaning: a leaf a
human approved. **On the standalone row both facts are still necessary.** A card in that
column with no label starts nothing. A labelled leaf whose card sits anywhere else starts
nothing either, so the column before the start column stays the maintainer's own lane.

**A missing fact is neither an error nor a refusal.** It is how a maintainer parks a
groomed item, and a forgotten drag reads the same way. So the answer is a quiet code and
a line that names which fact is missing. **A forgotten label is named by `report` and not
by a tick** (ADR 0064): an item with no label is in neither labelled set, so a tick never
sees its card.

**A card arrives with its item, and no board is listed.** `start` reads the card of the one
item it was handed. `queue` reads the two labelled sets, which are the only kinds a card can
authorise. So the read is bounded by the work a maintainer approved rather than by the size
of the board (ADR 0064).

**With no board coordinates the label alone decides.** A tracker that names no board is a
supported configuration, and its absence is never an error. The three coordinates are
arguments, and the caller reads them from `docs/agents/issue-tracker.md`, so this seam
holds no board of its own. **All three subcommands here read a card and write none**, so
`read:project` on the token answers them all (ADR 0067).

**`queue`** — read the whole queue and start at most one work item. This is the whole
body of a **Repo automation** tick, and it is the one subcommand that spawns:

    python3 <plugin root>/scripts/worker_queue.py queue --repo OWNER/NAME \\
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

**No path exits 0 here.** A schedule starts its agent on exit 0 alone, so every run
records as skipped and no model loads on a tick.

The tick reads in one order, and the order is the contract:

| Step | What it reads, and what it decides |
|---|---|
| 1 | one list read answers every open work item, its labels and its body |
| 2 | the worker cap answers first, because it bounds every run at once |
| 3 | two labelled reads answer the card of every item that can start, and no board is listed |
| 4 | one table answers each item by its kind, in two passes |
| 5 | the candidates are the authorised items that nobody owns and nothing blocks |
| 6 | `max_stories` delays a candidate that opens a new **Story run** |
| 7 | the **Touch set** compare delays a candidate that overlaps a live **Worker** |

**One item per tick, always.** A queue that holds ten startable items starts one. A tick
that starts three is a tick that fills a disk while nobody watches. One item a minute is
slow enough for a human to notice and stop it. That is a hard rule and never a tuning
value, so no flag raises it.

**A `user-story` parent is never spawned for the work itself.** It is a spec, so the tick
descends to its unblocked children and spawns one of those. A child that carries the same
label is a nested spec, and the descent continues to the implementable leaves. **A
descended child starts on its `ready-for-agent` label alone**, and its own card is never
read. **The tick writes that label on no child.** So the rule that only a human writes it
survives word for word, and it now gates the descent too. A child with no label stays
stopped, which is how a maintainer parks one ticket under a running story. A child of a
live **Story run** reads the same way, because act one already happened for that story.

**The descent reads the same open-blocker predicate the Ready queue reads.** A blocker
absent from the open items is closed, and only a still-open edge blocks. No second
definition of unblocked is written.

**A live Worker is an item wearing the in-progress label, and no process is read.**
`scripts/spawn_item.py` writes that label before the prompt reaches the worker, and a
**Close transaction** takes it off. A live **Story run** is a `user-story` parent that is
owned itself, or one of whose descendants is. So one list read counts both roofs, and the
lower roof wins. **This is why the queue needs no process check**: the label is the fact,
and the watch is the only seam that reads a process.

**A delay is never a cancellation.** A full roof and a **Touch set** overlap both leave
the item ready. The next tick with a free slot and no live overlap starts it. So no item is
quietly dropped from the queue (ADR 0046).

**This subcommand writes no work-state label of its own.** The spawn is
`--spawn-command`, and the seam behind it writes the one label at its own step, before
the prompt reaches the worker. So a second tick cannot hand the same item out twice. A
spawn that failed is the one write this module makes: `needs-human` with one comment.

**`report`** — read the whole board and name every gap between it and the labels. **A human
runs this, and no schedule does** (ADR 0064):

    python3 <plugin root>/scripts/worker_queue.py report --repo OWNER/NAME \\
        --board-project '<the number the tracker file gives>' \\
        --board-owner '<the owner the tracker file gives>' \\
        --start-column '<the column name the tracker file gives>'

| Code | Meaning |
|---|---|
| 0 | the read answered, and the lines name the counts and each gap |
| 1 | a read failed, and the one line names the cause |

It names four gaps: a card in the start column on an item with no `ready-for-agent` label,
an item wearing that label whose card sits outside that column, an open item with no card,
and a card whose work item is not open. **It writes nothing and it moves no card.**

**The tracker CLI is an argument.** `--tracker-cli` picks which command reads the labels
and the bodies. `--tracker-host` names the server where the tracker is self-hosted. The
caller resolves both from `docs/agents/issue-tracker.md`, the same way it resolves every
other configuration value. `main` builds one **Tracker adapter** from those two values,
`--repo` and `--gh-fixture`, and every function here takes that one object. The adapter
in `scripts/tracker.py` holds every command, so this seam names no tracker at all
(ADR 0040). A project on the other tracker then needs no wrapper script outside this repo.

**One subcommand spawns, and it composes no launch command to do it.** `queue` runs the
`--spawn-command` its caller passed, and it fills the six tokens of one work item into
that string. `start` and `report` spawn nothing.
"""

import fnmatch
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

# Both invocation forms reach the adapter: `python3 <plugin root>/scripts/worker_queue.py`
# puts `scripts/` on the path, and `python3 -m scripts.worker_queue` puts the repo root
# there (ADR 0034).
try:
    from .tracker import (
        IN_PROGRESS,
        NEEDS_HUMAN,
        READY_FOR_AGENT,
        TO_REVIEW,
        Tracker,
        TrackerError,
        UsageExitParser,
        add_board_arguments,
        add_tracker_arguments,
        needs_human,
    )
except ImportError:  # the type checker reads the package form above
    from tracker import (  # type: ignore[no-redef, import-not-found]
        IN_PROGRESS,
        NEEDS_HUMAN,
        READY_FOR_AGENT,
        TO_REVIEW,
        Tracker,
        TrackerError,
        UsageExitParser,
        add_board_arguments,
        add_tracker_arguments,
        needs_human,
    )

# `report` answers a read that worked, and `start` answers the fact the item's kind owns.
# Both are exit 0, and each name says which question was answered.
EXIT_COMPLETE = 0
EXIT_DUE = 0

# Every quiet answer shares one code: a fact that is missing, a candidate that waits, and
# a read that failed. So a caller reads one bit and the printed line names the cause.
EXIT_NOTHING = 1

# `queue` is the one subcommand here that writes. A tick that started a worker and a tick
# that refused one carry different codes, and that difference is the first fact a
# maintainer needs from a run history. **No path through `queue` exits 0**, because exit 0
# is what loads a **Repo automation**'s provider and an agent on a tick is the cost this
# subcommand removes (ADR 0022).
EXIT_REFUSED = 2
EXIT_APPLIED = 4


# --- the Touch set (ADR 0046) ------------------------------------------------

TOUCHES_HEADING = re.compile(r"^##\s*Touches\s*$", re.MULTILINE)
NEXT_HEADING = re.compile(r"^##\s", re.MULTILINE)


def heading_block(body, heading):
    """The text under one `##` heading of a work item body, or an empty string.

    Every block a **Work item** carries takes one shape: a heading line, then one entry
    per line, until the next heading or the end of the text. `## Touches`, `## Parent`
    and `## Blocked by` are the three, so one reader serves all of them and no second
    parse of that shape is written.

    **All three callers live in this module**, which is why the reader does too. The watch
    reads no block of a work item body at all.
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


# --- the start gate (ADR 0045, narrowed by ADR 0062 and ADR 0064) -----------

# The three answers the start gate gives. `START` means the fact the item's kind owns
# holds, so the item may start. That fact is the card for a `user-story`, the label for a
# child of an authorised story, and both for a standalone leaf. `ONE_FACT` is a leaf card
# in the start column with no label, which is a forgotten label, and it is never an error.
# `NO_FACT` is every item whose card sits outside that column. A groomed item rests there,
# and a parked one rests there too (ADR 0061).
START = "start"
ONE_FACT = "one-fact"
NO_FACT = "no-fact"

# The label that makes a work item a spec rather than a leaf. The gate reads it first,
# because a story and a leaf are authorised by different facts (ADR 0062). A story is never
# spawned for the work itself: the tick descends to its children. A child that carries the
# same label is a nested spec, and the descent continues through it.
USER_STORY = "user-story"


def board_column(board):
    """The start column where the tracker names a whole board, and `""` where it does not.

    **A tracker that names no board is a supported configuration**, and any one of the
    three coordinates missing reads that way. So one derived value answers "is there a
    column to compare", and the gate branches on that alone (ADR 0045).
    """
    project, owner, column = board
    return column if project and owner and column else ""


def gate_cards(tracker, board):
    """The `Status` name on the card of every item that can start, keyed by number.

    **Two labelled reads, and no board list** (ADR 0064). A `user-story` and a
    `ready-for-agent` leaf are the only kinds a card can authorise, so the adapter is asked
    for those two sets by label and each item's card arrives in the same call. The read is
    then bounded by the work a maintainer approved rather than by the size of the board.

    A read that fails raises out of here, so a tick answers `unreadable` and never a quiet
    line. A read that filled its page raises the same way.

    With no board there is no card to read, so this answers an empty map and the label alone
    decides.
    """
    if not board_column(board):
        return {}
    cards = {}
    for label in (USER_STORY, READY_FOR_AGENT):
        for record in tracker.labelled_items(label):
            cards[record["number"]] = record["board"]
    return cards


def start_gate(item, labels, status, column="", story=0):
    """`(answer, detail)` for whether one work item may start: the fact its kind owns.

    **One table answers the three rows of ADR 0062, and it reads the item's kind first**
    (ADR 0064). `start --item N` and a queue tick both call this, with the same facts, so
    the two can no longer disagree about one item.

    `status` is the `Status` name on this item's own card, and `story` is the authorised
    `user-story` above it, or 0. Both arrive as arguments, so this function makes no read.

    | Item kind | What authorises it |
    |---|---|
    | `user-story` | its card sits in `column`. **No label, ever.** |
    | child of an authorised story | it wears `ready-for-agent`. **Its own column is not read.** |
    | standalone leaf | it wears `ready-for-agent`, **and** its own card sits in `column`. |

    **A story is a spec, and no worker implements one.** So one drag of the story card
    authorises the whole run, and the label keeps its one meaning: a leaf a human approved.
    **On the standalone row the card is read first** (ADR 0061), because the board is the
    narrower fact and a label outside `column` is the resting state of a groomed backlog.

    Three answers and no fourth:

    - **`START`** — the fact this item's kind owns holds.
    - **`ONE_FACT`** — a **standalone leaf** whose card sits in `column` and that carries no
      label. That is a forgotten label, and it is the one disagreement a maintainer repairs.
      This is **never an error and never a refusal**. A queue tick cannot reach it, because
      an unlabelled item is in neither labelled set. `report` names it instead (ADR 0064).
    - **`NO_FACT`** — every other shape: a parked story, an unlabelled child, and a leaf
      whose card sits outside `column`. None of these needs reporting on a tick, because
      the board already says where each one sits.

    **With no column the label alone decides.** A story then authorises nothing through a
    column that does not exist, and a labelled leaf starts on one fact.
    """
    labelled = READY_FOR_AGENT in labels
    wearing = (
        f"work item #{item} carries the {READY_FOR_AGENT} label"
        if labelled
        else f"work item #{item} carries no {READY_FOR_AGENT} label"
    )
    if not column:
        no_board = "the tracker names no board, so the label alone is the whole gate"
        if labelled:
            return START, f"{wearing}, and {no_board}"
        return NO_FACT, f"{wearing}, and {no_board}. So it starts nothing"

    carded = status == column
    sits = f"its card sits in the {column!r} column"
    elsewhere = (
        f"its card sits in {status!r} rather than {column!r}"
        if status
        else f"it has no card in the {column!r} column"
    )
    if USER_STORY in labels:
        spec = (
            f"work item #{item} is a {USER_STORY} spec, so its card is the whole gate"
        )
        if carded:
            return START, f"{spec}, and {sits}, so it authorises its own children"
        return NO_FACT, f"{spec}, and {elsewhere}, so it authorises nothing"
    if story:
        under = f"work item #{story} is an authorised {USER_STORY} above it"
        if labelled:
            return START, f"{wearing}, and {under}. Its own column is not read"
        return NO_FACT, f"{wearing}, and {under}. So this child stays stopped"
    if not carded:
        return NO_FACT, f"{wearing}, and {elsewhere}"
    if labelled:
        return START, f"{wearing}, and {sits}"
    return ONE_FACT, f"{wearing}, and {sits}, so it starts nothing"


def start(item, tracker, project=0, owner="", column=""):
    """The `start` answer: `(exit code, the one line to print)`.

    It writes nothing at all. Exit 0 means the fact this item's kind owns holds, and every
    other answer is the quiet code. So a caller reads one bit, and the printed line names
    which fact is missing.

    **It reads the same table the tick reads, so the two agree on every row** (ADR 0064).
    That costs three reads: the labels of this item, this item's own card, and the open
    items for the story tree above it. This is a command a human runs, so no schedule pays
    for them.

    **The item's own card is one read and never a board list.** A human can name an item
    that wears no label at all, and such an item is in neither labelled set.

    **A failed read is quiet too, and it is never a start.** A read that failed cannot say
    the item carries the ready state, so nothing starts on it.
    """
    board = (project, owner, column)
    try:
        labels, _ = tracker.item_facts(item)
        gate_column = board_column(board)
        story = 0
        status = tracker.item_card(item) if gate_column else ""
        if gate_column:
            items = tracker.open_items()
            by_number = {one["number"]: one for one in items}
            _, _, authorised = story_gates(
                items,
                gate_cards(tracker, board),
                by_number,
                children_of(items),
                gate_column,
            )
            story = authorised_above(item, by_number, authorised)
    except (TrackerError, OSError, json.JSONDecodeError) as exc:
        cause = " ".join(str(exc).split())
        return EXIT_NOTHING, (
            f"unreadable: the labels on work item #{item} are unreadable, so this gate "
            f"reads no fact and nothing starts: {cause}"
        )
    answer, detail = start_gate(item, labels, status, gate_column, story)
    return (EXIT_DUE if answer == START else EXIT_NOTHING), f"{answer}: {detail}"


# --- the queue tick (ADR 0045, ADR 0046) ------------------------------------

# The **Work-state label**s that say somebody already owns the item — a **Worker**, a
# reviewer, or the maintainer. An item wearing one of them is never a queue candidate.
# The family itself lives with the **Tracker adapter**, because the watch swaps the same
# four strings.
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


def parent_edges(item):
    """Every parent one work item names, the native link first, with no duplicates.

    **The Parent edge has two representations, and this unions them rather than preferring
    one** (ADR 0065). The native parent link is the tracker's own, and it is
    what a maintainer sees as a tree. The `## Parent` line is the prose the `to-tickets`
    template writes, and it is the form every tracker holds.

    A child that carries both counts once, because the union is keyed on the number.
    Where the two disagree, both parents keep the child, so a wrong edge shows up as an
    extra child and never as a missing one. A tracker with no parent link answers 0 for
    the native half, so the prose line is the whole edge there.
    """
    found: list[int] = []
    for number in [
        int(item.get("parent") or 0),
        *parse_edges(item.get("body", ""), PARENT_HEADING),
    ]:
        if number and number not in found:
            found.append(number)
    return found


def parent_of(item):
    """The parent work item of one item, or 0 where it names none.

    **The native link leads, because `parent_edges` puts it first.** So a child linked
    only in the tracker UI still finds the story above it. An item that names more than
    one parent takes the first, because one child has one parent, and the whole union is
    what `children_of` reads.
    """
    edges = parent_edges(item)
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

    One list read answers the whole tree, so the descent makes no read per item. That read
    carries both halves of the **Parent edge**, so this needs no command of its own.

    **The two edges are unioned per item** (ADR 0065). A child that carries both counts
    once under that parent. A child whose two edges disagree is filed under each parent, so
    a wrong edge shows up as an extra child and never as a missing one.
    """
    found: dict[int, list[int]] = {}
    for item in items:
        for parent in parent_edges(item):
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
    at = parent_of(by_number.get(number) or {})
    while at and at not in seen:
        seen.add(at)
        item = by_number.get(at) or {}
        if USER_STORY in item.get("labels", ()):
            return at
        at = parent_of(item)
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


def authorised_above(number, by_number, authorised):
    """The nearest ancestor of one work item that authorises a run, or 0.

    **A nested story is walked through, authorised or not** (ADR 0062). A story a
    maintainer dragged authorises every labelled leaf under it at any depth, so the walk
    stops at the first ancestor in `authorised` rather than at the first `user-story`.

    `seen` guards a body that names an ancestor of its own, so a cycle in the `## Parent`
    edges cannot become a cycle here.
    """
    seen = {number}
    at = parent_of(by_number.get(number) or {})
    while at and at not in seen:
        seen.add(at)
        if at in authorised:
            return at
        at = parent_of(by_number.get(at) or {})
    return 0


def story_gates(items, cards, by_number, children, column):
    """The gate answer of every `user-story`, the live runs, and the authorised set.

    Returns `(the gate answer per story, the live Story run numbers, the authorised ones)`.

    **A story's own row reads no story above it**, so this pass runs before the rest of the
    queue and its answers feed the child row (ADR 0064). A story authorises its children
    where its own card sits in the start column, or where its **Story run** is already live.
    A live run keeps authorising, because act one already happened for that story.
    """
    gates = {
        item["number"]: start_gate(
            item["number"], item["labels"], cards.get(item["number"], ""), column
        )
        for item in items
        if USER_STORY in item["labels"]
    }
    live = {number for number in gates if story_is_live(number, by_number, children)}
    authorised = {
        number for number, (answer, _) in gates.items() if answer == START
    } | live
    return gates, live, authorised


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


def queue_gates(items, cards, by_number, children, column):
    """The gate answer for every open work item, and the live **Story run**s.

    Returns `(the answer per item number, the live Story run numbers)`.

    **One table answers all three rows, in two passes** (ADR 0064). The first pass answers
    every `user-story`, because a story's row reads no story above it. The second pass
    answers every other item, and it hands each one the authorised story above it. So a
    child of an authorised story is answered by the same function `start --item N` calls,
    and the two can no longer disagree.
    """
    gates, live, authorised = story_gates(items, cards, by_number, children, column)
    for number, item in by_number.items():
        if number in gates:
            continue
        gates[number] = start_gate(
            number,
            item["labels"],
            cards.get(number, ""),
            column,
            authorised_above(number, by_number, authorised),
        )
    return gates, live


def queue_candidates(gates, by_number):
    """Every work item this tick can start, lowest number first.

    A candidate is an item the gate answered `START` for that nobody owns and nothing
    blocks. Both roads to a `START` are in the one table: a standalone leaf holding both
    facts, and a labelled child of an authorised story (ADR 0064).

    **A child with no label stays stopped**, whatever its parent holds. That is how a
    maintainer parks one ticket under a running story, and the tick writes the label on no
    child. So the rule that only a human writes that label survives word for word, and it
    gates the descent too.
    """
    open_numbers = set(by_number)
    return [
        number
        for number in sorted(open_numbers)
        if gates[number][0] == START and startable(number, by_number, open_numbers)
    ]


def queue_plan(tracker, board, roofs, parallel_check=TOUCHES):
    """The one work item this tick starts, or None, plus the line that says why.

    **One item per tick, always.** A queue that holds ten startable items starts one. A
    tick that starts three is a tick that fills a disk while nobody watches. One item a
    minute is slow enough for a human to notice and stop it. That is a hard rule and never
    a tuning value, so no flag raises it.

    The order of the reads is the contract:

    1. One list read answers every open work item, its labels and its body.
    2. The worker cap answers first, because it bounds every run at once.
    3. Two labelled reads answer the card of every item that can start. **No board is
       listed** (ADR 0064).
    4. One table answers each item by its kind, in two passes.
    5. The candidates are the items the table answered `START` for that nobody owns and
       nothing blocks.
    6. `max_stories` delays a candidate that opens a new **Story run**.
    7. The **Touch set** compare delays a candidate that overlaps a live **Worker**.

    **A delay at step 6 or step 7 cancels nothing.** The next tick with a free slot and
    no live overlap starts that item, so no item is quietly dropped from the queue
    (ADR 0046).

    **A read that failed raises out of here.** So a tick that cannot see the queue or the
    cards answers `unreadable`, and it never prints the quiet line of a tick with nothing
    to do.
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
    gates, live_stories = queue_gates(
        items,
        gate_cards(tracker, board),
        by_number,
        children,
        board_column(board),
    )
    candidates = queue_candidates(gates, by_number)
    if not candidates:
        return None, (
            f"nothing: none of the {len(items)} open work item(s) is startable on this "
            f"tick"
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
    return None, f"nothing: every candidate waits — {delayed}"


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
    it rather than reconstructing a reason. The **Tracker adapter** owns that write, and
    the code beside it is this module's own.
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
        refusal = needs_human(
            tracker,
            item["number"],
            item["labels"],
            f"the spawn of work item #{item['number']} exited {proc.returncode}: "
            f"{cause}",
        )
        return EXIT_REFUSED, f"{line} — {refusal}"
    return EXIT_APPLIED, f"{line} — applied: the spawn ran: {command}"


# --- the board report (ADR 0064) --------------------------------------------


def gap_clause(what, numbers):
    """One gap of a board report as one line, or nothing where the gap is empty.

    The cap is the one every other report takes, and the count is the whole count. So a
    reader sees how large the gap is even where the line names five of it.
    """
    if not numbers:
        return []
    named = ", ".join(f"#{number}" for number in sorted(numbers)[:REPORT_CAP])
    return [f"{len(numbers)} {what}: {named}"]


def board_report(tracker, board):
    """`(exit code, the lines to print)`: the whole board, and every gap in it.

    **This is the one whole-board read left, and a human runs it** (ADR 0064). No schedule
    reaches it. The tick reads two labelled sets instead, so it cannot see an item that
    wears no label at all, and this verb is where such an item is named.

    Four gaps, and each one is a disagreement between the board and the labels:

    - a card in the start column on an item with no `ready-for-agent` label, which is a
      forgotten label
    - an item wearing that label whose card sits outside the start column, which is a
      groomed item at rest or a forgotten drag
    - an open work item with no card at all
    - a card whose work item is not open, which is a card the board's own workflow left
      behind

    **It writes nothing and it moves no card.** A gap here is a disagreement a human reads
    and judges, so this verb reports it and never repairs it. The three writes a seam does
    make happen at the moment the work moves, and none of them is a repair pass (ADR 0067).

    Exit 0 means the read answered. A read that failed is the quiet code with one line, the
    same as every other read in this seam.
    """
    project, owner, column = board
    try:
        items = tracker.open_items()
        cards = tracker.board_cards(project, owner) if column and project else {}
    except (TrackerError, OSError, json.JSONDecodeError) as exc:
        cause = " ".join(str(exc).split())
        return EXIT_NOTHING, (
            f"unreadable: the board or the open work items are unreadable, so this "
            f"report names no gap: {cause}"
        )
    by_number = {item["number"]: item for item in items}
    if not column:
        return EXIT_COMPLETE, "\n".join(
            [
                f"{len(items)} open work item(s), and the tracker names no board, so the "
                f"{READY_FOR_AGENT} label is the whole gate",
                *gap_clause(
                    f"item(s) carry the {READY_FOR_AGENT} label",
                    [
                        number
                        for number, item in by_number.items()
                        if READY_FOR_AGENT in item["labels"]
                    ],
                ),
            ]
        )
    lines = [
        f"{len(cards)} live card(s) on project {project} of {owner!r}, "
        f"{len(items)} open work item(s), and {column!r} is the start column"
    ]
    lines += gap_clause(
        f"card(s) sit in {column!r} with no {READY_FOR_AGENT} label",
        [
            number
            for number, status in cards.items()
            if status == column
            and number in by_number
            and READY_FOR_AGENT not in by_number[number]["labels"]
            and USER_STORY not in by_number[number]["labels"]
        ],
    )
    lines += gap_clause(
        f"item(s) carry the {READY_FOR_AGENT} label with a card outside {column!r}",
        [
            number
            for number, item in by_number.items()
            if READY_FOR_AGENT in item["labels"] and cards.get(number, "") != column
        ],
    )
    lines += gap_clause(
        "open item(s) have no card at all",
        [one for one in by_number if one not in cards],
    )
    lines += gap_clause(
        "card(s) belong to an item that is not open",
        [one for one in cards if one not in by_number],
    )
    return EXIT_COMPLETE, "\n".join(lines)


# --- CLI --------------------------------------------------------------------


def main(argv=None):
    parser = UsageExitParser(
        # The usage block prints the command that ran. So a reader copies a form
        # that resolves from their own working directory. The module form resolves
        # only at the plugin root
        # (orchestrator/docs/adr/0034-the-seam-invocation-carries-a-resolved-plugin-root.md).
        prog=f"python3 {Path(__file__).resolve()}",
        description=(
            "Answer which work item starts next. The start subcommand reads one item's "
            "kind first, then the fact that kind owns: the board card for a user-story, "
            "and both facts for a leaf. It writes nothing. The queue subcommand asks the "
            "same question of every open item, through the same table, and starts at most "
            "one of them. The report subcommand reads the whole board and names every gap "
            "between it and the labels, which is the one whole-board read a human runs. "
            "This seam reads no worktree and no process: it is a graph walk over one "
            "tracker read, and the worker watch in scripts/worker_state.py owns every "
            "process check. It moves no card and it descends into no story it was not "
            "handed. One subcommand spawns, and it runs the spawn command its caller "
            "passed rather than a command of its own."
        ),
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    opener = subcommands.add_parser(
        "start",
        help="may this work item start? Exit 0 the fact its kind owns holds, non-zero a "
        "fact is missing. It writes nothing at all",
        description=(
            "The start gate. It reads the item's kind first, then asks the fact that kind "
            "owns. A user-story is authorised by its card in the start column alone, and "
            "it needs no ready-for-agent label ever. A leaf needs both facts: the label, "
            "and its own card in that column. Exit 0 means the item may start, and the "
            "printed line names why. Exit 1 means a fact is missing, and the line names "
            "which one. A one-fact answer is a leaf card in the start column with no "
            "label, which is a forgotten drag. A no-fact answer is where a groomed item "
            "rests, and a parked story authorises nothing from there. "
            "A missing fact is never an error and never a refusal, so the column "
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
            "the start gate by the item's kind. It descends through any authorised "
            "user-story parent to its unblocked children, and it starts one that wears "
            "ready-for-agent. It counts the live story runs and the live workers "
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

    reporter = subcommands.add_parser(
        "report",
        help="read the whole board and name every gap between it and the labels. Exit 0 "
        "means the read answered. It writes nothing at all",
        description=(
            "The one whole-board read left, and a human runs it. No schedule reaches it. "
            "A queue tick reads two labelled sets instead, so it cannot see an item that "
            "wears no label at all, and this verb is where such an item is named. It "
            "names four gaps: a card in the start column on an item with no "
            "ready-for-agent label, an item wearing that label whose card sits outside "
            "that column, an open item with no card, and a card whose item is not open. "
            "It writes nothing and it moves no card: a gap is a disagreement a human reads "
            "and judges, so this verb reports it and never repairs it. Exit "
            "0 means the read answered, and exit 1 means a read failed."
        ),
    )
    add_tracker_arguments(reporter)
    add_board_arguments(reporter)

    args = parser.parse_args(argv)

    # This run builds one **Tracker adapter**, from the four flags that name the
    # tracker. Every read and every write past this point goes through it. So no function
    # past here carries a CLI name, a host, a repository or a fixture path (ADR 0040). The
    # construction reads nothing, so an unreadable fixture is still an outcome and never a
    # traceback.
    tracker = Tracker(args.tracker_cli, args.tracker_host, args.repo, args.gh_fixture)

    if args.command == "start":
        code, line = start(
            args.item,
            tracker,
            args.board_project,
            args.board_owner,
            args.start_column,
        )
    elif args.command == "queue":
        # The two roofs are this subcommand's own bounds, and a roof under 1 starts
        # nothing at all. So a bad value is a usage error rather than a silent tick.
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
    # `report` is the last of the three, so the branch is unconditional rather than a
    # third `if`. That is what keeps a fall-through out of the exit contract: an implicit
    # `None` would exit 0 and read as an answered read.
    else:
        code, line = board_report(
            tracker,
            (args.board_project, args.board_owner, args.start_column),
        )
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
