# An item-writing flow writes `ready-for-agent`, and the drag stays the authorisation

`0045-a-story-start-is-automatic-under-two-roofs.md` made one rule a safety rule: only a
human writes `ready-for-agent`. `0053-one-work-state-label-and-a-computed-position.md` and
`0062-a-story-card-authorises-its-run.md` both restate it. The rule is what stops a pass
from starting work nobody approved, and it has held through every change since.

It also makes the maintainer type the same label on every item an agent just wrote. An
inline item-writing flow does the specification: `/to-tickets` splits a plan into tickets,
`/to-spec` writes a spec, `/triage` sorts an item and writes its brief. Each one files the
item, writes its `## Touches` block, writes its parent edge, and stops. The maintainer then
opens each item and adds one label.

That label means one thing: the item is fully specified. The flow that wrote the
specification is the one that knows it. So the rule sends the fact to a human who reads it
back off the item the flow just wrote.

## The decision

**Every inline item-writing flow writes `ready-for-agent` on each item it files.**

`/to-tickets`, `/to-spec` and `/triage` are those flows. The write happens once, on create,
beside the `## Touches` block and the parent edge each flow already writes. A `user-story`
parent takes no work-state label at all, which is the rule
`0062-a-story-card-authorises-its-run.md` holds, and this changes nothing there.

**The drag stays the maintainer's, and it stays the authorisation.** A standalone leaf needs
two facts to start: the label, and its own card in the start column. So the label on its own
starts nothing, and an item this flow files waits in `Backlog` until the maintainer drags its
card. That is the whole safety argument, and it is why this narrowing is safe: the fact the
flow writes is not the fact that authorises a run.

**One consequence follows, and it is worth naming.** A child of a story whose card already
sits in the start column needs only the label, because a child's own column is never read.
So a child filed under an authorised story becomes startable as soon as it is filed. That is
`0062-a-story-card-authorises-its-run.md` working as designed: one drag authorises the whole
run, at any depth, for any child the maintainer did not park. A maintainer who does not want
that files the child under a story they have not dragged yet, or removes the label.

**The take-back is unchanged.** The maintainer removes `ready-for-agent`, or writes
`needs-human` with a comment that says why. No drag removes a label.

This ADR narrows `0045-a-story-start-is-automatic-under-two-roofs.md` and
`0053-one-work-state-label-and-a-computed-position.md`. Neither file is edited. What both of
them say becomes: only a human, or the inline flow that wrote the item's specification,
writes `ready-for-agent`. **No seam and no schedule writes it**, and that is the half of the
rule that carries the safety. A queue tick still writes the label on no child, which is the
sentence `0045` holds.

## Considered Options

- **The inline flow writes the label on create** (chosen) — the flow holds the fact at the
  moment it becomes true, and the drag is still the authorisation. It costs one flag on a
  write the flow already makes.
- **Leave it to the maintainer** (rejected) — what ships today, and it costs nothing to keep.
  Rejected because it is a manual step on every item, and the step re-reads a fact the agent
  that filed the item already knew. A manual step on every item is a step that gets skipped.
- **A schedule that labels every item with a `## Touches` block** (rejected) — it would catch
  items filed by hand too. Rejected because it is a pass that writes the label with no
  specification behind it. A block of paths is not a proof that an item is fully specified,
  and a pass that guesses at that is the thing `0045` refuses.
- **Write the label and drag the card too** (rejected) — the flow would then start the run
  outright. Rejected because it reverses `0045` rather than narrowing it. The drag is the one
  act that says a human approved the work, and an agent that makes it leaves no approval in
  the loop at all.
- **A new label for "specified by a flow"** (rejected) — it keeps `ready-for-agent` human-only
  and records the flow's judgement separately. Rejected because the start gate would then read
  two labels for one fact, and a second label family is what
  `0053-one-work-state-label-and-a-computed-position.md` removed.

## Consequences

- **A filed item is one drag from starting.** The maintainer reads the item, drags the card,
  and the queue tick does the rest. That is the shortest act one the loop has had.
- **A child of a live story run starts as soon as it is filed.** A flow that files ten
  children under an authorised story makes all ten startable, bounded by the two roofs and by
  the `## Touches` overlap check. That is the intended behaviour of
  `0062-a-story-card-authorises-its-run.md`, and it is faster than before.
- **A flow that files a badly specified item labels it anyway.** The label records the flow's
  own judgement, and a flow can be wrong. The maintainer's read before the drag is where that
  is caught, and on the child-of-a-story row there is no such read. `needs-human` is the
  repair.
- **The `report` verb gets quieter.** It names a card in the start column on an item with no
  label, which was the forgotten-label gap. A flow that writes the label as it files removes
  the common cause of that gap.
- **`hooks/refuse.py` gains one exemption, and it is the create.** That hook denies a
  **Work-state label** write from a Bash command in any session, and `--label` on a create
  carries the same flag a swap carries. So the hook denied the very write this ADR asks for.
  A create writes an item's first state rather than moving an existing one, so a command that
  creates an item is exempt. Every write on an existing item is still denied, which is the
  half of the hook that protects the loop.
