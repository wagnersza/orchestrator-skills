# The board is read before the label, so only a card in the start column reports a gap

`0045-a-story-start-is-automatic-under-two-roofs.md` gave the queue tick a start
gate of two facts: the `ready-for-agent` label, and the item's card in the board's
start column. Both are necessary. It also made the gate name every item that holds
one fact and not the other. So a forgotten drag did not read as an empty queue.

That report treats the two facts as interchangeable. Take a labelled item whose card
sits in `Backlog`, and an unlabelled card in `To do`. Both answer `ONE_FACT`, and
both ride the line of a quiet tick. The symmetry looked right and it is wrong,
because the two facts do not carry the same weight.

The label is the wide fact. A maintainer writes it once, during grooming, and it
stays on the item for as long as the item is groomed. So a healthy backlog carries
that label on most of its open items. The card is the narrow fact. A maintainer
drags it when they want the work started now, and the start column holds a handful
of cards at a time.

On this repo on 2026-09-03 that asymmetry read as 25 labelled items sitting outside
`To do`, against 1 card sitting in `To do` with no label. Every tick, once a minute,
printed the 25 as a disagreement to repair. They are not a disagreement. They are a
groomed backlog at rest, which is where a groomed item is supposed to be. The one
item that did need a hand was buried in the count.

The gate now reads the card first. A card outside the start column answers
`NO_FACT`, whatever the label says, so the backlog is quiet. A card inside it with
no label answers `ONE_FACT`, because that is a forgotten label and it is the one
disagreement a maintainer acts on.

**No item's start decision changes.** The gate is still an `and` of the same two
facts, and the set of items that start is byte-identical. What changes is which
item a quiet tick names. The board read was already made once per tick and held
(`scripts/tracker.py`, `_board`), so reading it first costs nothing either.

This ADR reverses one decision of ADR 0045, and that is the symmetry of the one-fact
report. The rest of ADR 0045 stands. That rest is the two necessary facts, the two
roofs, the label as the maintainer's own write, and the fallback to the label alone
where the tracker names no board. It narrows nothing in
`0054-the-board-is-an-input-not-a-mirror.md`: nothing writes a card here either.

## Considered Options

- **Read the card first, and report only a card in the start column with no label**
  (chosen) — it keeps both facts necessary and moves only what gets reported. The
  narrow fact gates the report, so the report names as many items as a maintainer
  can act on. It costs one reordered branch in `start_gate` and one changed clause
  in `queue_report`.
- **Keep the symmetry and raise the report cap** — leave the gate alone and print
  more of the parked items. Rejected because the count is the problem, not the cap.
  25 rows of groomed backlog is worse than 5 rows of it, and both bury the one row
  that matters.
- **Drop the label from the gate, so a card in the start column starts on its own** —
  one fact, and the drag is the whole decision. Rejected by the maintainer. It
  reverses the half of ADR 0045 that keeps a start deliberate. A drag is a cheap
  gesture, and an accidental one can then spawn a worker with no second confirmation.
  It also leaves a tracker with no board unable to start anything.
- **Keep the symmetry and report the two cases as two separate clauses** — name the
  forgotten labels and the parked labels apart, so a reader can skip one. Rejected
  because it prints the backlog every minute to be skipped every minute. A clause
  nobody reads is a clause that trains a reader to skip the whole line.
- **Report the parked labels once a day rather than once a tick** — keep the fact
  and cut the frequency. Rejected because the tick holds no state between runs, so
  "once a day" needs somewhere to record the last report. That is a new file for a
  line nobody asked for.

## Consequences

- **A labelled item parked outside the start column is now silent.** That is the
  intent. A maintainer who wants to know what is groomed reads the board, which is
  the thing that holds the answer.
- **A forgotten drag is no longer reported.** A groomed, labelled item nobody drags
  reads as a quiet tick, and it did not before. The trade is deliberate: that case
  is indistinguishable from a deliberate park, and ADR 0045 guessed it was a
  mistake. The board shows both the same way, so the guess had no evidence behind
  it.
- **A failed board read gets a clause of its own.** It counts no card, so under the
  new order it answers `NO_FACT` for every item. Without a clause it then prints the
  same quiet line as a tick with nothing to do. `queue_report` reads the failure
  phrase back out of the detail line and says so. That is one string constant,
  `BOARD_UNREAD`, and no fourth gate answer.
- **`ONE_FACT` keeps its name and changes its meaning.** It now names one case
  rather than two. The three answers stay three, so no caller reads a fourth.
- **A tracker with no board is unaffected.** The label is still the whole gate
  there, and that path never reaches the card branch.
