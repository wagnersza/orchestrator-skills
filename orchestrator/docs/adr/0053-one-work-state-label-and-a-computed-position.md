# One work-state label, and the position is computed

Two label families described one run. The **Work-state labels** said what a work item
is. The `phase:*` family cached where inside an owned run it sat. Every fact the second
family cached was already on disk or on the tracker, so the cache can disagree with the
truth, and nothing repaired a disagreement. A session that read the wrong phase ran the
wrong row of a table.

One more label recorded an approval the maintainer had already given. `to-merge` existed
because a machine could not tell whether the maintainer wanted a branch merged. A merged
pull request answers the same question, and nobody can forget it, because doing it *is*
the act.

## The decision

**One work-state family, four values, and it never stacks.** `ready-for-agent`,
`in-progress`, `to-review` and `needs-human`. The strings, the swap rule and the
`gh label create` lines stay in
[`docs/agents/issue-tracker.md`](../../../docs/agents/issue-tracker.md), which owns every
label vocabulary ([ADR 0002](0002-delegate-tracker-to-mattpocock-skills.md)).

**`needs-human` is new, and it is the only label that stops every tick.** The tick reads
it first and exits quiet, whatever the checklist, the verdicts and the process say. It
writes no back-off marker there, because a quiet tick is not a fire. So a paused item
costs one cheap read a minute and wakes nobody. It carries one comment that says why, and
only the maintainer removes it. No seam writes it: a session writes it where it refuses.

**The `phase:*` family is deleted, all three values.** The **Position** entry of
[`orchestrator/CONTEXT.md`](../../CONTEXT.md) holds the rule that replaces it, and
`position_of` in `scripts/worker_state.py` computes it from facts the tick already read:
the work-state label, the `Verdict:` comment list and the last write to the
**Checklist**. A cached answer can be stale, and a computed one cannot.

**`to-merge` is deleted, and the repo writes no `To merge` card.** The typed close stays
the route to closed. A later item makes the tick read a merged pull request instead, so
**land them in that order**: this one removes the label, and the item after it adds the
read.

**The outcome table drops to eight rows, and it holds no phase-gating column.**
`proof-complete` goes, because the proof is one more box on the **Checklist** and
"every box ticked" already covers it. `merge-requested` goes with `to-merge`. The eight
that stay fire on computed facts, and the seam docstring is the one table of them.

**Three flags go with `merge-requested`.** `--board-project`, `--board-owner` and
`--board-option` served that outcome alone. So one tracker read answers every fact a tick
needs, and no tick makes a second command that can fail.

**Setup gains the label migration, and it is the only step that can run one.** It runs
once and it touches the whole tracker. It names every item that wears a deleted label
before it deletes the family, so the maintainer reads what changed. It lands in the same
change that deletes the family, or two vocabularies are live at once.

## What this supersedes

**It supersedes [ADR 0021](0021-phase-is-a-second-label-family.md) in full.** That ADR
declared the second family and argued for two independent axes over one item. The second
axis is gone, so every claim in it that names a `phase:*` label is retired: the three
values, the stacking rule, the tracker as the store for the phase, and the absence of a
phase label as the transition to human review. Its own accepted risk was that an owned
item which loses its label reads as human review. A computed position holds no label to
lose, so that risk retires with the family.

**One claim of ADR 0021 survives, in a new home.** Human review is a work state and not
a position a worker owns, so nothing restates `to-review`. That is now the first line of
the **Position** rule.

**It narrows three ADRs, each where the ADR names a deleted label.**

- **[ADR 0037](0037-the-merge-queue-is-an-ordered-train.md)** — the `to-merge` label is
  no longer the standing authorisation, and the board column is no longer an entry. A
  **Merge queue** is the set of items the maintainer asked to merge. The train itself is
  unchanged: the ordering, the park rule and one full **Close transaction** per item all
  stand.
- **[ADR 0045](0045-a-story-start-is-automatic-under-two-roofs.md)** — `To merge` is no
  longer an intent column, so `To do` is the only one. The two roofs, the descent to a
  story's children and the rule that only a human writes `ready-for-agent` are unchanged.
- **[ADR 0047](0047-the-story-proof-runs-before-the-story-gate.md)** — a `user-story`
  parent wears no `phase:e2e` label while its **Story proof** runs, and the proof reports
  `implementation-complete` rather than `proof-complete`. The trigger, the fresh worktree,
  the two durable artifacts and the failed-proof block are unchanged.

**No old ADR file is edited here.** The ledger pass that marks every retired ADR is a
later item. This one writes its own record, and the live surfaces are what stop naming a
deleted label.

## Considered Options

- **One family, four values, and a computed position** (chosen) — one label answers
  "what is this item", and the facts answer "where inside its run". Nothing caches an
  answer, so nothing can disagree with itself.
- **Keep the `phase:*` family and fix the drift** (rejected) — there is nothing to fix.
  The family is a second copy of an answer, and a repair pass is a third place the same
  fact lives.
- **Fold the phases into the work-state family** (rejected, again) — ADR 0021 rejected
  this for six mutually exclusive values, and the reason stands. Every consumer of
  `in-progress` grows a list.
- **Split this into four items** (rejected) — a split leaves two vocabularies live at
  once. A session that reads one file and writes the other produces an item that no later
  read can resolve. One big diff is cheaper than that.
- **Keep `to-merge` until the merged-PR read lands** (rejected) — the label and the read
  answer the same question, so both live at once means two entries to one queue. The
  typed close covers the gap, and it needs no label.
- **A `stopped:*` family instead of one `needs-human` value** (rejected) — the reason a
  seam refused belongs in the comment it writes, not in a label string. One value is the
  whole stop.

## Consequences

- **One label write per transition, so nothing can stack.** A session that swaps one
  label cannot leave two work states on an item, which is the class of bug #155 reported.
  `scripts/test_worker_state.py` asserts it twice: no position is reachable from two
  work-state labels at once, and no outcome the tick prints names two of them.
- **Accepted risk: a reviewer before its first verdict reads as an implementation
  worker.** No label records a review round now, and the position reads the verdict that
  starts it. So a reviewer's own worktree, which holds the implementation's commit, can
  fire a `stalled` outcome inside the stall window. ADR 0021's family was what covered
  that state, and ADR 0018 accepted the weaker reviewer signal before it. A false stall
  costs one report to the maintainer and destroys nothing. `dead` still fires for a dead
  reviewer with no window elapsed, which is the fault that matters.
- **Accepted risk: the one-way door needs no worker in flight.** Every open item that
  wears a `phase:*` label loses it in one item, and the deletion cannot be half done. The
  guard is to land this with the queue read first. An item at `to-review` is safe, and an
  item at `in-progress` is not. A read of an item that still wears a deleted label crashes
  no tick, which is the mitigation for a repo whose migration has not run.
- **The maintainer deletes the `To merge` column by hand.** That is a board edit, and the
  repo stops writing the column here rather than removing it.
- **The rollback is a revert plus a few labels by hand.** The labels this deletes are
  cheap to write back on the few open items that wore them.
