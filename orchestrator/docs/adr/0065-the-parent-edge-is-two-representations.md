# The parent edge is two representations, and the child read unions both

The **Work item** entry of `CONTEXT.md` says a child carries its parent as a `## Parent`
line of prose, per the external `to-tickets` template. That line was the whole edge, and it
has two costs.

A maintainer opens a `user-story` on the tracker and sees no tree. The link from a story to
its children lives in text inside each child, so reading the shape of a run means reading
eight bodies. The tracker has a native parent link, and on #178, #200 and #201 that link
exists because a person added it by hand. A run the inline lane files tomorrow gets none.
The practice is real and the contract is missing.

The seams have the mirror of that fault. `children_of` finds a child by matching a regular
expression against every open body. A link a maintainer makes in the tracker UI is invisible
to it, so the tracker and the queue tick can disagree about which children belong to a
story, and the tick answers the smaller set.

## The decision

**The parent edge has two representations, and both are written at the moment the child
gains a parent.**

1. The **native parent link**. On GitHub this is a sub-issue on the parent. This is the one
   a human sees.
2. The **`## Parent` line**, exactly as the external `to-tickets` template already writes
   it. This is the portable one, because it is the only form that works on every tracker.

**One adapter command writes both, so it cannot write only one.** `Tracker.parent_link_argv`
builds `gh issue edit <child> --parent <parent> --body <body>`. The method composes the body
itself: it adds the `## Parent` block where the body carries none, and it leaves a body that
already carries one untouched. So a create path runs one command and lands both edges, and
there is no window in which the child is half-linked.

**The child read unions the two, and it prefers neither.** `parent_edges` answers the native
link and every `## Parent` number of one item, native first, with no duplicates. A child
that carries both counts once. Where the two disagree, both parents keep the child, so a
wrong edge shows up as an extra child and never as a missing one. A preference order hides
that disagreement.

**The union costs no second read.** `gh issue list --json parent` answers the native link
beside the body, so the one list read a tick already makes carries both edges. `ITEM_FIELDS`
gains one field and the tick gains no command.

**The upward walk reads the same union.** `story_above` and `authorised_above` follow
`parent_of`, which is the first edge of that union. So a child linked only in the tracker UI
still finds the story above it, and the start gate authorises it.

**GitLab has no parent link between two issues, and this claims no parity.** Its issue links
endpoint offers `relates_to`, `blocks` and `is_blocked_by` only, and its real hierarchy is
an epic or a work item, which is a different object. So there the `## Parent` line stays the
whole edge, the adapter writes the body alone, and the native half of the union is always
empty.

**A failed link write is reported and is not a stop.** The session names the child and the
parent and carries on. The text edge already carries the meaning, so no `needs-human` label
is written for it.

This ADR narrows `0002-delegate-tracker-to-mattpocock-skills.md`. That ADR leaves the item
body to the external template, and this one keeps that: the `## Parent` section stays
exactly as the template writes it, and no template is forked. What changes is that the
orchestrator writes a second edge beside it.

It also narrows `0040-the-tracker-is-one-adapter-behind-both-seams.md` in scope, not in
shape. That ADR bounds the adapter to the commands the two seams run or print, and this
command is run by a session in the **inline** lane. It lands there anyway, because the read
half of the edge is already adapter code and two halves of one contract in two homes drift.

## Considered Options

- **Two representations, one write, a union read** (chosen) — a maintainer sees the tree, a
  hand-made link counts, and nothing that reads the text line today breaks. It costs one
  adapter command, one field on the list read, and one union in the descent.
- **Move to the native link alone** (rejected) — one edge, one home, no union. Rejected
  because the native link does not exist on every tracker, so the portable form has to
  survive, and because it needs a backfill of every open child.
- **Prefer the native link and fall back to the text line** (rejected) — cheaper than a
  union and it reads as the obvious order. Rejected because it hides a disagreement between
  the two edges. A child whose native link points at the wrong parent then vanishes
  from the right one.
- **Two commands, a create and then a link** (rejected) — this is the shape a session
  improvises. Rejected because a failed second write leaves a child with one edge, and
  nothing later notices.
- **A second read for the native children** (rejected) — `gh api
  repos/<owner>/<name>/issues/<N>/sub_issues` answers them directly. Rejected because the
  list read already carries the field, so the second read buys one command per parent and no
  fact.

## Consequences

- **A child can answer two parents.** `parent_edges` keeps both, so `children_of` files that
  child under each one. The descent can then reach it twice, and `descendants` already
  guards a repeat with `seen`.
- **One more field on the widest read.** The open-items read asks for `parent` on every open
  item, once a minute. It is one field on a read that already asks for the whole body.
- **The write rewrites the child body.** `parent_link_argv` sends `--body`, so a caller
  passes the body it holds. The body is a required argument for that reason. A caller with
  no body erases one.
- **A GitLab run sees no change.** The native half of the union is empty there and the write
  edits the description alone, so the edge behaves exactly as it did before this ADR.
- **No backfill.** #178, #200 and #201 already carry their native links, and every other
  parent keeps its text edge, which the union still reads.
