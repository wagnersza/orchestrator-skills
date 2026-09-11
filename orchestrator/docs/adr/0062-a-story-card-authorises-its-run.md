# A story card authorises its run, and a child label starts the work

`0045-a-story-start-is-automatic-under-two-roofs.md` gave the start gate two facts: the
`ready-for-agent` label, and the item's card in the board's start column. Both are
necessary, and the gate asks the same pair of every open work item. It also let a child of
a live **Story run** start with no fact at all.

That single rule is wrong at both ends.

It is wrong for a `user-story`. A story is a spec, and no worker implements one. The
maintainer drags a story card to `To do` to mean "run this whole story now". Under the old
gate that card starts nothing, because the story wears no `ready-for-agent` label. The
label means "a leaf a human approved", so putting it on a spec spends the one label that
carries that meaning.

It is also too loose for a child. The descent reached every unblocked child of an
authorised story, labelled or not. So a ticket nobody approved started because its parent
moved.

Both faults were live on this repo's own board on 2026-09-11. Story #252 sat in `To do` with
no label, so every tick named it as a forgotten label and started nothing. Its one open child
wore no label, and the old descent reaches an unlabelled child anyway. So the gate gave the
wrong answer twice on one story.

## The decision

**The gate reads the item's kind first, then asks the fact that kind owns.**

| Item kind | What authorises it |
|---|---|
| `user-story` | its card sits in the start column. **No label, ever.** |
| child of an authorised story | it wears `ready-for-agent`, and every `## Blocked by` edge is closed. **Its own column is not read.** |
| standalone leaf | it wears `ready-for-agent`, **and** its own card sits in the start column. Unchanged. |

- **A story card is the authorisation for the whole run.** One drag makes every labelled,
  unblocked child of that story startable. That is the usual way to work: one story, then
  every ticket under it, until the story is done.
- **The label keeps its one meaning, and only a human writes it.** No pass writes
  `ready-for-agent` on a story or on a child. So the safety rule of ADR 0045 survives word
  for word, and it now also gates the descent.
- **A child's own card is never read.** The maintainer drags the story card, and no child
  card.
- **The standalone leaf path does not change.** Both facts still apply, so the set of
  standalone items that start is byte-identical.
- **A story is never named as a forgotten label.** A story with no label is the correct
  resting state, so a queue report that names it is noise. This narrows the report
  [ADR 0061](0061-the-board-is-read-before-the-label.md) already narrowed once.
- **Where the tracker names no board, the label alone is the whole gate.** That fallback
  stands, and a story then authorises nothing through a column that does not exist.

This ADR reverses one decision of ADR 0045. The gate is no longer one pair of facts asked of
every item, and a child no longer starts with no fact. The rest of ADR 0045 stands. That rest
is the two roofs, the label as the maintainer's own write, `work on N` as the manual override,
and the no-board fallback. It narrows nothing in
`0054-the-board-is-an-input-not-a-mirror.md`: nothing writes a card here either.

## Considered Options

- **Kind first, then the fact that kind owns** (chosen) — it matches how the maintainer
  already works, and it makes an unapproved child stop. It spends no new label. The cost is
  one branch on the item's kind ahead of the two-fact compare.
- **Put `ready-for-agent` on the story** (rejected) — the smallest change, and the gate
  then needs no branch at all. Rejected because the label means "a leaf a human approved".
  A story is a spec, so the label on a story reads as an invitation to implement the spec
  itself. The one label that answers "can a worker start this ticket" then stops answering
  only that.
- **A pass that promotes a `To do` card to the label** (rejected) — the tick reads the
  column and writes the label. The old two-fact gate then keeps working unchanged. Rejected
  because it reverses the safety rule that only a human writes that label. It also makes a
  drag, which is a cheap gesture, into a durable approval that outlives the drag.
- **Read a child's own card as a third fact** (rejected) — the maintainer then holds one
  child back by dragging its card out. Rejected because it asks for one drag per child,
  which is the cost ADR 0045 removed. Removing the child's label already parks one child,
  and that needs no board read.
- **Keep the old gate and label every child by hand** (rejected) — no code changes, and the
  maintainer pays one write per ticket. Rejected because the story card is the gesture they
  already make, and the labels then say nothing the parent does not.

## Consequences

- **A child with no label now stops.** That is the point, and it is a behaviour change on a
  live run. A maintainer who labelled no child of an authorised story sees no worker start.
- **A story card outside the start column authorises nothing**, so none of its children
  becomes a candidate through it. A parked story is silent, as a parked leaf already is.
- **The gate answers three shapes, and a caller reads the item's kind.** `user-story` on the
  item is that read, and there is no new label and no new field.
- **This ADR records the contract and wires nothing.** The seam that answers these rows is
  separate work, and it holds the old rule until that work lands.
