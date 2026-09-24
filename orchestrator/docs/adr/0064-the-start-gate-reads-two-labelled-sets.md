# The start gate reads two labelled sets, and the whole board is a report

**The six subcommands below are two files now. See
[ADR 0070](0070-the-watch-and-the-queue-are-two-seams.md).** This ADR chose a reading
strategy, and every rule of it stands: `start` and a queue tick still call one gate
function, so the two cannot disagree about one item. What moved is the file boundary. The
three subcommands this ADR describes live in `scripts/worker_queue.py`.

`0061-the-board-is-read-before-the-label.md` put the card ahead of the label in the start
gate. `0062-a-story-card-authorises-its-run.md` gave that gate three rows, one per kind of
work item. Neither ADR changed the read behind the card, and that read is a list of the
whole board.

The list is the fault. `Tracker._board` asks a project board for its cards, up to a
constant, and it holds the answer for the rest of the tick. A board grows every week, so
the constant is a race the board wins. It was 100, and a board of 188 cards answered 100
of them. Every card past the page read as an item with no card, and a new card sits at the
end of the page, so the gate stopped every new item. #298 is that failure on this repo's
own board.

#299 patched it. The limit went to 500 and the read now carries `-status:Done`, so the
answer holds the live cards alone. That patch buys time and it does not change the shape.
The read is still a whole-board list behind a constant, and a board of 500 live cards
brings the same silent failure back.

The gate also holds two decision tables, not one. `start_gate` answers the story row and
the standalone row. The child row lives in `queue_candidates`, which walks the descendants
of an authorised story. So `start --item N` and the queue tick disagree: the tick starts a
labelled child of an authorised story, and the gate that is supposed to answer the same
question calls that child parked. A contract with two implementations has no contract.

## The decision

**The gate asks the tracker for the two labelled sets, and each item's card arrives in the
same call.**

A `user-story` and a `ready-for-agent` leaf are the only kinds a card can authorise. So the
adapter reads those two sets by label, and it asks for the `Status` name on each item's own
card in the same command. `gh issue list --label <name> --json ...,projectItems` is that
command. **The tick lists no board.**

**One table answers the three rows of ADR 0062, and it reads the item's kind first.**

| Item kind | What authorises it |
|---|---|
| `user-story` | its card sits in the start column. **No label, ever.** |
| child of an authorised story | it wears `ready-for-agent`, and every `## Blocked by` edge is closed. **Its own column is not read.** |
| standalone leaf | it wears `ready-for-agent`, **and** its own card sits in the start column. |

`start_gate` takes the story fact as an argument, so one function answers all three rows.
`start --item N` and the queue tick call it with the same facts, and they can no longer
disagree.

**A list read that fills its own page refuses.** One helper checks every list read in the
adapter: the two labelled sets, the open work items, and the board read that is left. A
count equal to the limit raises `TrackerError`, and the message names the count, the limit
and the constant to raise. So a truncated read is never an answer of "no".

**The whole board read becomes a `report` verb that a human runs.** It prints the board, the
open items and every gap between them: a card in the start column with no label, a labelled
item parked outside that column, an open item with no card, and a card whose item is
closed. Nothing schedules it.

This ADR narrows ADR 0061 twice, and both narrowings follow from the read.

- **A forgotten label leaves the tick.** An item with no label and no `user-story` label is
  in neither labelled set, so the tick cannot see its card. So the `ONE_FACT` clause of
  `queue_report` has nothing to count, and the function goes. `report` names that item
  instead, because `report` reads the board.
- **`BOARD_UNREAD` goes with it.** The card read is now one call per tick rather than one
  per item, so a failed read raises out of the plan and the tick answers `unreadable`. That
  is louder than the quiet line the phrase carried, and it costs one string constant less.

`ONE_FACT` keeps its name and its meaning in the gate itself. `start --item N` still answers
it, because that command reads the card of the one item it was handed.

It narrows nothing in `0054-the-board-is-an-input-not-a-mirror.md`. Nothing writes a card
here either, and the read still needs `read:project` and no write scope. The one reader
changes name: `Tracker.board_status` answered one item from a board list, and
`Tracker.labelled_items` now answers the card with the item. `Tracker.board_cards` is the
board list, and `report` is its one caller.

## Considered Options

- **Two labelled reads, with the card on the item** (chosen) — the read is bounded by the
  work a maintainer approved rather than by the size of the board, and the card needs no
  second query. It costs one new adapter command and a signature change on the gate.
- **Raise the limit again** (rejected) — the cheapest change, and it is the patch #299
  already made. Rejected because the next board outgrows the next constant. A bound that a
  growing board crosses is a scheduled failure, and the failure is silent.
- **Walk the pages of the board** (rejected) — `--paginate` answers every card, so no card
  is missed. Rejected because it makes the read cost grow with the archive. A board holds
  every card it ever held, and the tick needs the handful a human approved.
- **Put the card on every open item** (rejected) — add `projectItems` to the one open-items
  read, and no labelled read is needed. Rejected because that read is already the widest one
  the tick makes. Asking it for a project field per item widens it again, and the tick needs
  the card of the startable items alone.
- **Keep the two tables and copy the child row into the gate** (rejected) — the smallest fix
  for the disagreement. Rejected because two copies of one rule drift, which is how the
  disagreement arrived.

## Consequences

- **A quiet tick names no forgotten label.** A maintainer who drags a card and forgets the
  label sees nothing on the tick line. They see it in `report`, and that is a command they
  run rather than a line they read every minute.
- **`report` is the only whole-board reader left**, so the board read runs when a human asks
  and never once a minute.
- **A truncated list read stops the tick.** A queue of more open items than `ITEM_LIMIT`
  used to start the oldest of the first page. It now refuses and names the constant. That is
  a behaviour change, and it is the point: a read that cannot answer must never answer "no".
- **An item on two project boards reads the first card its item read answers.** The item
  read names each board by title and not by number, so the two board coordinates cannot
  filter it. One board per repo is the shape `docs/agents/issue-tracker.md` describes, so no
  configuration this repo supports reaches the second card.
- **`start --item N` makes three reads rather than two.** It reads the item's labels, the
  item's own card, and the open items for the story tree above it. It is a command a human
  runs, so the cost is one round trip nobody waits on.
