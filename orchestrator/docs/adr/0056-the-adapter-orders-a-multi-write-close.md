# The adapter orders a multi-write close

[ADR 0040](0040-the-tracker-is-one-adapter-behind-both-seams.md) put every tracker command
behind one adapter. A close of a work item is two commands on one tracker and one on the
other. The adapter held the two halves apart: `close_argv` and `closing_note_argv`.

It held neither the fact that the two are one operation nor the order they run in. The
caller held both. `note_part` in `scripts/close_item.py` asked for the note argv, tested
whether it came back empty, and `tracker_parts` spliced it in front of the close by hand.

So the caller had to know that one tracker needs a second write, and where that write
goes. The order matters: an item that closes first closes with no reason on it.

## The decision

**`close_writes(item, comment)` answers the writes and their order, and a caller iterates
them.** It gives `[note, close]` on the tracker with no reason flag and `[close]` on the
tracker that carries the reason in the close itself. Each entry is the name of the write
and its argv.

**A count of writes is one more difference between two trackers.** ADR 0040 put each such
difference inside the one method that differs. This decision states that the
order of a multi-write operation is one of those differences, so it lives in the adapter
too. The caller assembles nothing, so it cannot assemble the wrong order.

## What this narrows

**It narrows [ADR 0040](0040-the-tracker-is-one-adapter-behind-both-seams.md) on one
point: the adapter owns the order of a multi-write operation, and not only each command
in it.** ADR 0040 said a seam asks for a fact or for an argv. Where one operation is two
argv, that reading left the order with the seam. This decision moves it. Nothing else in
ADR 0040 changes: one module, one class, one fixture format, and no seam names a tracker.

## Considered Options

- **One method that answers the ordered writes** (chosen). The rule has one home, and a
  third tracker with a third write count lands in that one method.
- **Leave the two halves, and state the order in prose** (rejected). This is the state
  before this decision. The rule sat in a docstring, and the code that had to obey it sat
  in another file.
- **One method that runs the writes as well** (rejected). Each write is its own resumable
  part of step 7, with its own status and its own idempotency read. Only the seam knows
  what a part is, so a runner in the adapter takes that plan apart.

## Consequences

- **The branch in the caller shrinks, and it does not vanish.** `note_part` keeps its
  comments read and its `done` answer, because that read is what makes the part
  repeatable. What it loses is the argv fetch, the emptiness test and the splice.
- **Behavior does not change.** The plan a maintainer sees, its step numbering, its
  statuses and its refusal reasons are the same. The existing test that asserts
  `label`, `note`, `close` in that order passes untouched.
- **`close_argv` and `closing_note_argv` stay on the adapter.** Each one still has its
  own test, and `close_writes` composes them. A second caller that wants one half alone
  gets it, and the seam asks for neither.
