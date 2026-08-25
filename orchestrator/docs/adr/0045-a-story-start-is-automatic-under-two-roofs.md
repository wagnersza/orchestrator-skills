# A story start is automatic, under two roofs

[ADR 0029](0029-a-work-item-number-is-a-complete-instruction.md) made a work-item number a
complete instruction, and the maintainer supplies that number. The `work on N` flow then
batch-spawns every unblocked child of a **user-story** parent, once, when the maintainer
asks. So a story of ten children costs the maintainer one ask per batch, and each child
carries its own `ready-for-agent` label.

The maintainer wants a story to run without that ask. They also want a lane on the board
for work that no agent can touch.

## The decision

**A story starts by itself when it carries `ready-for-agent` and its card sits in the
board's `To do` column. The automation then owns every child of that story.**

- **The gate is two facts, and both are necessary.** A card in `To do` with no label is not
  started. An item with the label whose card sits in `Ready` is not started either. So the
  `Ready` column becomes the maintainer's own lane, and the agent stays out of it.
- **A child needs neither fact.** The queue tick descends from the story to its unblocked
  children, exactly as the `work on N` flow does today, and spawns them. It writes no
  `ready-for-agent` label on a child, so the safety rule that only a human writes that
  label survives word for word.
- **The `To do` column is intent, in one direction, board to label.** This is the pattern
  [ADR 0038](0038-the-to-merge-column-is-intent.md) already holds for `To merge`, applied a
  second time. The reconcile pass writes no `Status` for an item whose card sits in `To do`.
- **Where the tracker has no board, the label alone is the gate.** The board section of
  `docs/agents/issue-tracker.md` is optional, and its absence is never an error. This is
  the fallback ADR 0038 already states for the merge queue.
- **Two roofs bound the cost, and the lower one wins.** `max_stories` bounds how many
  **Story run**s are live, and its default is 2. The worker cap bounds how many **Worker**s
  are live across all of them, and it drops from 5 to 4. The tick spawns nothing when
  either roof is full.
- **A Story run holds its Story slot until the parent closes**, story proof included. So a
  story with one child left still occupies a slot.
- **A take-back is manual.** No drag removes a label. The maintainer removes
  `ready-for-agent`, or writes `needs-human`, and comments why.

## Considered Options

- **Two facts, story-level, two roofs** (chosen) — one human act starts ten children, the
  board gains a human-only lane, and the cost has a hard ceiling that does not multiply.
- **One fact: the label alone** (rejected by the maintainer) — smaller, and it keeps one
  home for one fact. It was recommended and declined, because it gives the board no column
  that means "groomed, and not for an agent". The absence of a label already means that,
  but it does not *read* that way on a card wall.
- **One fact: the column alone** (rejected) — unreadable on a tracker with no board, which
  the fallback above exists to support.
- **The tick writes `ready-for-agent` on each child** (rejected) — it reverses the safety
  rule that no loop starts work the maintainer did not ask for. Descending to the children
  reaches the same result and writes no label.
- **One roof: `max_stories` only** (rejected) — 2 stories times a worker cap of 5 is 10
  live workers, which is a bill the maintainer did not name. The second roof makes the
  worst case equal to the worker cap.
- **One roof: the worker cap only** (rejected) — it bounds the money correctly and it says
  nothing about how many stories are in flight, so one wide story starves every other.
- **Free the Story slot at the last child** (rejected) — the story proof runs after the
  last child closes, and it is part of the story. A slot freed before the proof lets a
  third story start while the proof of the second story still runs.

## Consequences

- **ADR 0009 is narrowed a second time.** `To do` joins `To merge` as an intent column.
  `Backlog`, `Ready`, `In progress`, `In review` and `Done` stay derived projections, and
  the drag-is-drift sentence holds for all five.
- **The queue tick reads the board every minute.** That is one Projects v2 query per tick,
  repo-wide. The board read becomes a hard dependency of the start path, where before it
  was a side effect of the reconcile pass.
- **Accepted risk: two facts can disagree, and nothing repairs that.** A label with no
  card in `To do` is a story that looks started and is not. There is no error and no
  comment, because a quiet gate is the point: this is how the maintainer parks a groomed
  story. The cost is that a forgotten drag reads as a stalled queue. The queue report names
  every item that holds one fact and not the other, so the disagreement is visible on
  request.
- **`work on N` still works, and stays a manual override.** It writes the label and spawns
  at once, which is what it does today.
- **This ADR records the decision and wires nothing.** The `To do` coordinates, the
  descent in the queue tick, the `max_stories` field and the queue report line are each
  separate work.
