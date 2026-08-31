# The tick applies the transition it computed

The decision layer was already deterministic. `scripts/worker_state.py` read the facts,
computed the **Position** and printed one outcome, under test. **The action after that
decision was prose.**

A tick printed a line and delivered it to a terminal. A session then read a table and
performed the follow-up by hand: write one label, remove another, maybe spawn a reviewer.
**A write a session performs is a write a session can skip.** That is the whole of bug
#155, where one item wore two work states at once. The delivery had its own fault, which
is bug #156: an undelivered wake burned its back-off window, so the transition went
unreported for the length of that window.

## The decision

**The tick applies the transition it computed.** `wake` is replaced by `tick`, and the
seam keeps three subcommands. `tick` reads the same plan `phase` reads, and then it
applies the one transition that plan carries.

**One function inside the seam owns every work-state label swap.** It runs in the process
that already read the labels, so no second read can disagree with the first. There is no
fourth file, because a split would add exactly that second read.

**The removals and the addition are one tracker write.** Both go into one `label_argv`
call, which `scripts/tracker.py` already builds, so the two can never land apart.
**The removals are computed from the labels the tick read**, and never from a hardcoded
predecessor. That is what makes the one-label answer hold from every legal starting
position.

**Three outcomes carry a transition, and every other outcome refuses.**
`implementation-complete`, `verdict-approve` and `rounds-exhausted` write the review state
in one swap. The rest say something about the worker, about the tracker read, or about a
fix round that is still the same worker's work. None of those decides a label, so the item
stays where it is and the exit code is the refusal.

**The finish is the one row with more than one branch, and the tick honours both.** That
row already held them. Where `--review` says the review policy is on, a **Review round**
comes next and a worker still owns the item. On a `user-story` parent, the layer 5 story
gate reads the evidence first
([ADR 0047](0047-the-story-proof-runs-before-the-story-gate.md)). Each of the two holds the
swap, prints why, and leaves the item where it is. So the outcome table gains a write and
loses no branch, and `to-review` still means only that a human owns the item.

**A tick applies at most one transition per run.** One tick reads one item, computes one
outcome and makes at most one label swap. So a wrong computation cannot cascade inside one
minute. This is a mechanism with its own test, and not advice.

**`phase` is the plan and `tick` is the execute.** That is the split
[`scripts/close_item.py`](../../../scripts/close_item.py) already holds
([ADR 0015](0015-close-is-a-deterministic-transaction.md)). One test reads a decision with
no mutation, another proves `phase` leaves no tracker write behind, and a maintainer
dry-runs one item against a live tracker before the first write.

**`needs-human` is read before any other fact, and this seam owns its writer.** An item
that wears the label gets a quiet tick, whatever the checklist, the verdicts and the
process say. The writer puts the label on the item and posts one comment saying what the
seam saw, because a label with no reason leaves the maintainer to reconstruct one. Only
the maintainer removes it.

**One named transition is reachable from the CLI: `tick --claim`.** It swaps the ready
state for the in-progress state and computes nothing. So an **Orchestrator** session's
spawn claim runs the same writer a tick runs, and it assembles no label command of its
own. This closes the gap #236 was filed for. It is one named transition and not a
general-purpose label tool, so no caller can invent a swap of its own.

**The wake is deleted, with `--handle`, `--title`, `--send-command`, `--back-off` and
`--marker-dir`.** There is no delivery left, so no transition can be lost to one. **The
applied label is what stops a repeat fire**, because the next tick reads the state the
last one wrote. So the suppression window and its marker files retire with the delivery
they served, and no fact lives in a file a restart cannot read. The seam now writes one
tracker command and no file at all.

**The exit code names what happened.** `tick` exits 4 applied, 2 refused, 1 quiet and 3
for a worktree that is gone. No path exits 0, so an **Item automation** records every run
as skipped and its prompt and provider stay inert. Usage errors keep exit 64, so a flag
with a typo can never read as a quiet tick.

**No hook denies this write.** `hooks/refuse.py` denies a work-state label write in a
`Bash` command from a session, and a tick runs from a schedule rather than from a
session's tool call ([ADR 0055](0055-the-label-denial-reads-its-caller.md)). The claim
command carries no label flag and no label string, so the denial's own test does not fire
on it. #238 holds that exemption hole.

## What this supersedes

**It supersedes [ADR 0024](0024-the-wake-target-is-a-resolved-handle.md) in full.** That
ADR chose a resolved terminal handle over a title, and added a comment on the work item as
target three. There is no delivery left, so the three targets, their order, the spawn-time
resolution of the handle and the spawn report of which mode is live all retire together.
Its accepted risk was a transition recorded late rather than delivered. Nothing is
recorded late now, because the write *is* the record.

**It supersedes [ADR 0027](0027-the-tick-delivers-its-own-wake.md) in full.** That ADR
gave the seam a third subcommand which delivered the line it printed, so that no agent ran
on a tick. `tick` replaces that subcommand and keeps the one claim that mattered: no path
exits 0, so no model loads on a tick. Its accepted risk was a wake landing in a busy
terminal, with `--back-off` as the mitigation. Both retire with the delivery.

**It supersedes [ADR 0025](0025-the-session-writes-the-review-state.md) on who writes the
label.** The seam writes the review state now, and the session writes none. Two claims of
that ADR survive in a new home. A **Worker** still writes no work-state label at all, and
its last act is still the review note on the work item.

**It narrows [ADR 0026](0026-the-automation-follows-the-live-worker.md) on the trigger,
and keeps its mechanism.** One **Item automation** per item stands, operation 13 stands,
and the precheck still follows the live worker. What retires is the trigger: the repoint
was a second act inside a wake response, and there is no wake to respond to. A session
repoints when it spawns the next worker instead. The edit still fails closed, so a
rejected repoint leaves the item observed.

**No old ADR file is edited here.** The ledger pass that marks every retired ADR is a
later item, the same posture
[ADR 0054](0054-the-board-is-an-input-not-a-mirror.md) took.

## Considered Options

- **The tick applies the transition it computed** (chosen) — the write happens in the
  process that read the facts, so there is no moment at which a session can forget it.
- **Keep the wake and state the rule more firmly** (rejected) — the fault is not that the
  session was told too softly. It is that the write was a separate act, and a separate act
  can be skipped.
- **A fourth file for the writer** (rejected) — it would read the labels a second time,
  and a second read can disagree with the first. The removals depend on that read.
- **Two tracker writes, one removal and one addition** (rejected) — the two can land
  apart, and an item then wears two work states. That is bug #155 exactly.
- **A general-purpose label subcommand for sessions** (rejected) — every caller then
  assembles its own transition, which is the shape this ADR removes. One named transition
  keeps the swap in one place.
- **Apply a transition for `dead` and `stalled` too** (rejected for now) — #216 owns those
  under one re-prompt and then a human. A stop written with no re-prompt rule gives up on
  a worker that needed one nudge.
- **Keep `--back-off` beside the label write** (rejected) — the label is the
  acknowledgement, so a second suppression window is a second answer to one question. The
  two can then disagree.
- **Write the review state on every finish, review policy or not** (rejected) — a review
  round would then run on an item labelled as waiting on a human, and that label would
  lie. The review policy arrives as a flag instead, the way `--rounds` and
  `--require-gate` already do.

## Consequences

- **The one-way door is a seam that writes the tracker on a schedule.** A wrong transition
  lands every minute with nobody watching. Two mechanisms bound it, and both hold a test:
  `needs-human` stops every tick on that item, and a tick applies at most one transition
  per run.
- **The gate record is what stands between a ticked box and a write.** A finish with no
  green line for every required layer at the current `HEAD` refuses, and the printed line
  names which of the four causes held. So a claim no command proved cannot reach review.
- **Accepted risk: a wrong finish now moves an item with no human in the turn.** Nobody
  reads a line first. The mitigation is the gate record above, and the cost of the fault
  is one label a maintainer swaps back.
- **Accepted risk: five outcomes report to a run history and to nobody else.** `dead`,
  `stalled`, `gates-unproven`, `verdict-request-changes` and `unreadable` exit 2 and write
  nothing. Until #216 lands, a stalled worker is a line in the schedule's run history
  rather than a message. The wake it replaces could fail silently too, so this is a
  narrower gap than it reads.
- **Assumption: `to-review` still means human review, and the tick leaves such an item
  alone.** The **Position** rule of
  [`orchestrator/CONTEXT.md`](../../CONTEXT.md) puts that label first, and
  [ADR 0053](0053-one-work-state-label-and-a-computed-position.md) owns the rule. So a fix
  round routes from an item a worker still owns, and the review round stays a legal
  position through this wave. Adversarial review leaves the loop in a later wave, and
  reversing the position rule would need its own ADR.
- **Two bug reports close with this record.** #155, two stacked work states, and #156, an
  undelivered wake burning its window.
- **The rollback is to remove the schedule.** The manual flow that
  [`orchestrator/SKILL.md`](../../SKILL.md) still holds then answers, because the rewrite
  of that prose is a later wave. That is the reason the rewrite is last.
