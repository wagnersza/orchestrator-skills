# The board is a mirror, and a seam writes the card at three moments

> Narrowed by [ADR 0070](0070-a-board-column-is-a-card-or-a-scoped-label.md). One read,
> three writes, and a card that moves with the work: all three stand. What narrows is how
> a column is addressed, because on the other tracker a column is a scoped label on the
> item and not a card field.

`0054-the-board-is-an-input-not-a-mirror.md` took every card write out of this repo. It had
a good reason. The writes it removed were seven, they were spread across four call sites,
and each one wrote a column that a **Work-state label** already carried. A derived value
with four writers drifts, and a reconcile pass then overwrote the maintainer's own drag.

That ADR also named the price it paid, in its own last consequence: **a card nobody moves
reads as stale.** Live now for six weeks, the price is higher than the note implies. `In
progress` and `In review` hold nothing for the whole life of an item. `Done` fills only
because the board's own **item closed to Done** workflow writes it. So a maintainer who
opens the board sees every live item sitting in `To do`, and cannot tell which item a
worker owns. The board is the surface they open, and it is the one surface the loop says
nothing to.

The old writes were also not the only shape a write can take. Every one of them derived a
column from a label, on a pass of its own, after the fact. A seam that already knows the
work changed is a different writer: it holds the fact, it holds it once, and it writes at
the moment the fact becomes true.

## The decision

**The board is a mirror of the work state, and the orchestrator writes the card at three
moments. Each write sits in the seam that already owns that moment.**

| Moment | Column | The seam that writes it |
|---|---|---|
| the spawn claim | `In progress` | `scripts/worker_state.py`, in `claim` |
| the finish | `In review` | `scripts/worker_state.py`, in the tick that writes `to-review` |
| after the teardown | `Done` | `scripts/close_item.py`, after step 8 |

**The card and the label move in the same process.** The finish write runs in the tick that
computed the transition and read the labels, which is the rule
`0056-the-tick-applies-the-transition-it-computed.md` already holds. So there is no second
pass, no derivation table and no reconcile command. A column with no moment gets no write.

**The drag into the start column is still the authorisation, and this ADR does not touch
it.** `Backlog`, `Ready` and the start column stay the maintainer's own lanes, and nothing
here writes one. A card in the start column still means "an agent can start this now", by
the three rows of `0062-a-story-card-authorises-its-run.md`. So the board is now read in
one column and written in three, and the two sets do not overlap.

**A write needs the option id, and a caller holds the name.** `docs/agents/issue-tracker.md`
records the three target columns by name, the way it already records the start column. The
adapter resolves the ids at run time: the project id, the `Status` field id, and the option
id of that column name. So no id is written into a configuration file, and a renamed column
is one edit.

**A failed card write is reported and it stops nothing.** The board is a mirror, and the
work is what the label and the worktree carry. So a board that cannot be written leaves a
stale card and nothing else. The spawn still spawns, the transition still lands, and the
close still closes.

**The `Done` write is safe to repeat.** The board's own **item closed to Done** workflow
already writes that column for most items, and it stays on. So the adapter reads the card
before it writes: a card that already sits in the target column costs one read and no write.
That also makes every one of the three writes safe to run twice.

**Three cases answer without an error**: a tracker with no project board, an item with no
card, and a column name the board does not hold. Each one is a supported configuration, the
same way `0054` made the absent board supported, so none of the three raises.

This ADR reverses `0054-the-board-is-an-input-not-a-mirror.md`, and it reverses the part of
it that says nothing writes the board. Two parts of `0054` survive word for word: the board
is read in the start column alone, and a drag is intent in every column. The token now needs
the `project` scope, because there is now a write.

## Considered Options

- **Three writes, one per moment, each inside the seam that owns it** (chosen) — the writer
  already holds the fact, so there is no second read that can disagree with the first, and
  there is no pass to schedule. It costs three reads per write to resolve the ids, and those
  run once per moment rather than once a minute.
- **Leave the board an input** (rejected) — the cheapest option, and it is what ships today.
  Rejected because the stale card is not a cosmetic fault. The board is where a maintainer
  looks to see what the loop is doing, and the answer there is wrong for every live item.
- **A reconcile pass that derives the column from the label** (rejected) — one writer, run
  on a schedule, reading the labels and writing the columns. Rejected because it is the shape
  `0054` removed, for the reason `0054` gives: a pass that writes a card overwrites the
  maintainer's drag, and the drag is the authorisation.
- **Write the card and let a failure stop the caller** (rejected) — it keeps the board and
  the labels in step, always. Rejected because a board outage would then stop every spawn and
  every finish. A mirror that can stop the thing it mirrors is not a mirror.
- **Record the option ids in `docs/agents/issue-tracker.md`** (rejected) — the write needs
  the ids, so a file that holds them saves three reads per write. Rejected because that is
  the five-id board step `0054` deleted. An id in a file goes stale silently, and a renamed
  column then writes to a column that is gone.

## Consequences

- **A card in `To do` now means no worker has taken the item.** That is a stronger statement
  than before, and a maintainer can read the board as progress.
- **A card in `Done` means the worktree is gone**, because the write follows the teardown of
  step 8. A card that reaches `Done` through the board's own workflow carries no such
  promise, and the two are indistinguishable on the board.
- **A failed spawn can leave a card in `In progress` with no `in-progress` label.** The
  `report` verb already names that disagreement, so nothing rolls the card back.
- **The token needs the `project` scope.** `read:project` alone answers every read and no
  write, so a token that is not refreshed fails every card write and stops nothing else.
  `gh auth refresh -s project` is the repair, and the line a failed write prints says so.
- **Each write costs three reads.** The project id, the field list and the card list are
  three commands before the write. They run once per moment, so the cost lands on the spawn,
  the finish and the close, and never on a quiet tick.
- **`Backlog` and `Ready` are still written by nobody**, so an item the maintainer parks
  there stays parked. A card the loop wrote to `In progress` and the maintainer drags back to
  `Ready` also stays there, because no pass reads it.
