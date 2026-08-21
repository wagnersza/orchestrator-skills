# The To merge column is intent, for one column and in one direction

[ADR 0009](0009-labels-drive-board-status.md) made the **Work-state labels** the source
of truth, and the Projects v2 `Status` field a projection of them. One of its consequences
carries that rule for a human who moves a card:

> **A human drag is not intent, it's drift.** Moving a card by hand is overwritten on the
> next reconcile. The way to move an item is to change its label.

A **Merge queue** needs an entry the maintainer reaches from the surface they already
review in. A drag of a reviewed card to the board's `To merge` column is that act. Under
the quoted sentence the drag is drift, and the next **Ready queue** read overwrites it.

## The decision

**The `To merge` column is intent. One column, and one direction.**

- **One column.** `Backlog`, `Ready`, `In progress`, `In review` and `Done` stay derived
  projections of the labels. The quoted sentence holds for all five of them, unchanged.
- **One direction, board to label, once, at promotion.** The session reads a card that
  sits in `To merge` and writes the `to-merge` label on the item. After that write the
  label is the source of truth for every later read, exactly as before.
- **Never label to board for that column.** The reconcile pass writes no `Status` for an
  item that carries `to-merge`. The card already sits where the maintainer put it, so
  there is nothing to write and nothing to overwrite.

The board coordinates for the column live with every other board coordinate, in
`docs/agents/issue-tracker.md`. That is ADR 0009's answer and
[ADR 0002](0002-delegate-tracker-to-mattpocock-skills.md)'s, and this decision moves no
coordinate into a skill body.

## Why a second state machine is still rejected

ADR 0009 rejected "Both authoritative, reconciled on conflict" for one reason: two
writers and no tiebreak. That reason does not reach this decision, because no fact here
has two writers.

The column is read once, and then converted. It is never read again, because the queue,
the train and the **Close transaction** all read the label. And no write ever targets the
column. So there is no loop to reconcile, and no race that needs a tiebreak. A second
state machine needs one fact that two surfaces both own. After the promotion the label
owns this fact alone.

The promotion is also idempotent. A card the session already promoted carries the label,
and the label is the queue's other entry condition. So a second read of the same card
changes nothing and adds no item twice.

## Considered Options

- **One column, one direction, board to label** (chosen) — the approval is recorded where
  the maintainer already works, and one surface still owns each fact. The exception is
  small enough to state in three bullets.
- **The label is the only entry** (rejected) — the maintainer then types `gh issue edit`,
  or hunts the label picker. That is friction on an item they are already looking at on
  the board. It keeps ADR 0009 whole, and it moves the friction rather than removing it.
  The label stays a supported entry, so this option survives as the fallback for a repo
  with no board.
- **Every column becomes intent** (rejected) — that is the "board authoritative" option
  ADR 0009 already rejected, and its reasons are unchanged. `Backlog` and `Ready` split on
  a live blocker count, which no card stores, so neither one is readable as intent at all.
  A drag to `In progress` must also spawn a worker, and no drag carries the context that
  decision needs.
- **Both directions for `To merge`** (rejected) — the session writes `Status` from the
  label, and it reads intent from the column. That is the two-writers case ADR 0009
  rejected, and the loser of the race is silent.
- **A second board field for intent** (rejected) — one more field to create, to resolve ids
  for, and to keep in `issue-tracker.md`. It buys the separation that the one-direction
  rule already gives for free.
- **A checkbox or a comment on the work item** (rejected) — both sit outside the board.
  The board is the surface the maintainer is in when they make the decision. The label is
  already that shape, and it needs no new vocabulary.

## Consequences

- **ADR 0009 keeps its body.** The quoted sentence stays where it is, narrowed to one
  column and no further. Per [`CLAUDE.md`](../../../CLAUDE.md), a decision that narrows an
  earlier one gets a new ADR and never a silent edit.
- **The derivation table gains no row for `to-merge`.** It gains an absence: an item that
  carries the label gets no `Status` write at all. That table lives in
  `docs/agents/issue-tracker.md`, which is separate work.
- **A dragged card stays in `To merge` until the item closes.** Step 7 of a **Close
  transaction** then writes `Done`, the same as for every other item.
- **No board is still a supported configuration.** With no board section in
  `issue-tracker.md` the column does not exist, the label is the only entry, and that
  absence is never an error.
- **Accepted risk: a card dropped there by mistake is an ask.** The column now authorises
  a merge, so a mis-drop reads as approval. The blast radius is one item, the park rule
  still stops a branch that does not merge clean, and a revert recovers a wrong merge.
  Nothing here finds a mis-drop.
- **This ADR records the decision and wires nothing.** The board coordinates, the
  promotion pass and the tick outcome are each separate work.
