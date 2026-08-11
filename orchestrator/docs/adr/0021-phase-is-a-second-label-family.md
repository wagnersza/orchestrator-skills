# Phase is a second label family, not a second state machine

A **Work item** owned by a worker wears `in-progress` from the spawn to the end of the
review loop. The **Work-state labels** entry of
[`orchestrator/CONTEXT.md`](../../CONTEXT.md) says so on purpose: the item holds that
one label through the whole adversarial-review loop, and it flips to the review label
only when the loop concludes. So one label covers implementation, up to three
**Review round**s, and every fix round between them.

That leaves *"is #129 ready for review?"* with nothing to read. The orchestrator
answers it from context, and context is the least durable store in this system. A
fresh session cannot say whether an item is on round 1 or round 3. The
adversarial-review section of [`orchestrator/SKILL.md`](../../SKILL.md) opens on the
condition "When a work item reaches the review state". No label records which part of an
owned run the item is in.

A work item now also wears a **Phase** ([`orchestrator/CONTEXT.md`](../../CONTEXT.md)):
`phase:impl`, `phase:review` or `phase:e2e`. Three values, mutually exclusive inside
the family, worn beside the work-state label. An owned item therefore carries
`in-progress` and exactly one `phase:*` label, and its phase is a fact any session
reads with one tracker call.

## Two axes over one item

[ADR 0009](0009-labels-drive-board-status.md) settled half of this question already:
labels are the source of truth, and a surface derived from them is a projection and
never a second state machine. This ADR takes the other half. **Phase does not derive
from the work state, and the work state does not derive from phase.** They are two
independent axes over one item. So nothing here adds a state to the existing machine.

Two properties follow, and both keep that machine intact.

**The Board status derivation is untouched.** `Status` keeps deriving from the
work-state labels alone. A phase change moves no card, ADR 0009 needs no edit, and the
derivation table in `docs/agents/issue-tracker.md` stays as written.

**No work state is restated.** Folding the phases into the work-state family would
make five or six mutually exclusive values. The board must then map each one, and every
query that asks "does a worker own this?" must then list each one. The families cross
instead: `in-progress` says a worker owns the item, and the phase says what the worker
is doing.

The precedent is in the tracker config already. The triage roles are a separate
vocabulary beside the work states, in the same file, with their own table
(`docs/agents/triage-labels.md`). Phase is the third such vocabulary, and it costs what
the second one costs: one section and three `gh label create` lines.

## Human review carries no phase label

The three phases are what a **Worker** does. Human review is what a human does, and it
is already a work state — `to-review`, "waiting on a human". A fourth phase value for
it would write one fact in two places, and two records of one fact drift.

So **removing the phase label is the transition to human review**, and the item wears
`to-review` alone. The absence is the value, which is the cheapest transition in the
family: one label write that deletes rather than swaps.

## The tracker is the only store

A label survives a restart of the orchestrator session, a reboot of the machine, and
the teardown of the worktree. A human also reads it on the card and in the issue list,
with no transcript to open. So a session with no memory of the spawn recovers the phase
with one read.

## Considered Options

- **A second label family, stacked beside the work-state family** (chosen) — two
  independent axes, each with one owner. The board derivation stays as ADR 0009 wrote
  it, and the store is the tracker for both. The cost is one section in the file that
  already owns every label vocabulary.
- **More values in the work-state family** (rejected) — one machine with six states,
  where three of them mean "a worker owns this and is doing something". Every consumer
  of `in-progress` then grows a list, and the board derivation table grows three rows
  for a fact it does not need.
- **A phase file on disk in the worktree** (rejected) — it dies with the worktree. A
  torn-down or restarted item is exactly when the phase is most needed. It is also
  invisible: a maintainer answering *what is happening to #129* must find the worktree
  and read a file, rather than look at the card.
- **A `Phase` field on the project board card** (rejected) — ADR 0009 makes the card a
  projection, and a field that only the card holds inverts that. It also makes a
  Projects v2 board a hard dependency of the phase axis, which the same ADR refused for
  the ready queue: a board-less repo is a supported configuration and would lose the
  axis entirely.
- **A fourth `phase:human` value** (rejected) — it restates `to-review`. The two must
  then be written together and read together. A run that sets one and not the other is
  a state no reader can resolve.
- **A `phase:fix` value for a fix round** (rejected) — a fix round is inside
  `phase:review`. A label that flips six times in one item is six network writes that
  can fail, for a fact already readable: the round number is the count of `Verdict:`
  comments on the item, per the **Completion signal** entry of `CONTEXT.md`.

## Consequences

- **Three labels to create, and no other tracker change.** The strings, the swap rule
  and the `gh label create` lines live in `docs/agents/issue-tracker.md`, beside the
  work-state table. That is [ADR 0002](0002-delegate-tracker-to-mattpocock-skills.md)'s
  rule: the tracker config owns the labels.
- **A phase change is one label write and no board write.** The phase axis adds no
  `gh project` call, and a card never moves for a reason a human did not expect.
- **The absence of a phase label is meaningful, and that is the accepted risk.** An
  owned item that loses its `phase:*` label reads as human review. The mitigation is
  ordering, not a mechanism: the session writes the phase label as the first act of
  every transition. That is the existing rule that a card is written wherever a label is
  written. A wrong reading costs one early hand-off to a human, and it destroys nothing.
- **`phase:e2e` is reachable only where the Project recipe boots something.** This
  repo's `run_recipe` is blank. So an item here goes `phase:impl`, then `phase:review`,
  then human review, and never wears `phase:e2e`.
- **This ADR declares the axis and wires nothing.** The seam that reads the labels, the
  operations that create the schedule, and the flow changes in `SKILL.md` are separate
  work. No item wears a phase label until they land.
