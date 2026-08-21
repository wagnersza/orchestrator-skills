# The merge queue is an ordered train a session runs

An owned run ends at the review state. A worker finishes, the **Orchestrator** writes
`to-review`, and nothing moves until the maintainer types `close 20`. That is
[ADR 0016](0016-the-orchestrator-merges-when-asked.md) working as designed.

The consent half of that decision is still right. No session merges unasked. The typing
half is the cost. A maintainer who reviewed five items types five closes, and picks an
order for them. Nothing computes that order. So item 2 merges into a default branch that
item 1 already moved, and one file is resolved twice. The order that prevents the second
resolution is a property of the five branches, and it is knowable before the first merge.

## The two sentences this narrows

Both sentences are ADR 0016's, and both carry the typing requirement. The first names
the gate:

> **The maintainer's words are the gate.** "task done, merge and close", "close 20" and
> "wrap up 20" authorise the transaction, teardown included.

The second rejects an authorisation that outlives one item:

> - **Let the maintainer authorise a whole session** (rejected) — a standing
>   authorisation is the absence the rule was written against. Each transaction needs
>   its own sentence.

**The consent rule survives both.** A human still decides, per item, before anything
merges. What retires is the requirement that the decision arrives as typed words in a
chat turn.

The ask becomes an act on the item itself. The maintainer drags the card to the board's
`To merge` column, or writes the `to-merge` **Work-state label**. Either one is the ask,
and [ADR 0038](0038-the-to-merge-column-is-intent.md) holds the column half of it.

**A drag is not the standing authorisation that sentence 2 rejects.** A standing
authorisation covers items the maintainer never looked at. A drag covers one item, and
the maintainer performs one drag per item after they read the PR. So each transaction
still has its own act behind it. What changed is where that act is recorded. It goes on
the work item, where a later session reads it, and not in a chat message that scrolls
away.

## The train

The **Merge queue** is the set of items ready to merge. A **Merge train** is one ordered
run over that set, and a session runs it.

The order comes from a seam, `scripts/merge_train.py`, because ordering is what code
holds perfectly and prose holds poorly. That is the reason
[ADR 0015](0015-close-is-a-deterministic-transaction.md) gave the close transaction a
seam. The new seam test-merges each queued branch in a throwaway checkout, then prints a
plan. **It plans, and it merges nothing.** The three ordering steps, the park rule and
the seam's contract live in `orchestrator/references/merge-train.md`.

The train then runs one full **Close transaction** per item in the planned order,
teardown included. **None of the eight steps changes, and their order does not change.**
The whole change is that one session calls the same transaction once per queued item.

**A branch that conflicts is parked, and the train keeps moving.** The session drops that
item back to the review state, comments the conflicting paths on the work item, and
carries on with the next branch. Nothing unattended decides what a merged file means.
That is the line ADR 0015 drew when it kept steps 1 to 3 in prose.

## The risk accepted, and the two mitigations that carry it

**A merge lands with no human watching that minute.** The maintainer drags a card and
walks away, and the train runs on a later tick. So the property ADR 0016 gave for free is
gone: a maintainer in the room at the moment of the merge. This ADR does not pretend
otherwise.

Two mitigations carry that risk, and there is no third:

- **The `to-merge` label is the authorisation, and it is per item.** No item enters the
  queue that the maintainer did not put there. An empty queue is the resting state, so a
  train merges nothing by default.
- **The park rule stops every case that needs judgement.** A branch that does not merge
  clean goes back to the review state, with its conflicting paths named on the item. So
  the unattended part of a train is the part with no decision in it.

The two refusals in `scripts/close_item.py` still hold under a train. It refuses to close
an unmerged PR, and it refuses to tear down a dirty worktree. A revert recovers a wrong
merge, which is why this risk is accepted rather than closed.

## Considered Options

- **A dragged card or the label is the ask, and a session runs the train** (chosen) — the
  decision stays the maintainer's. The order comes from a seam, and every destructive act
  stays in a session a human can interrupt. **The automation decides when, and the
  session decides what**, which is the split a **Close transaction**, a **Worker watch**
  and an **Item automation** already take.
- **The automation merges by itself** (rejected) — the tick runs the merge on its own
  schedule. An **Item automation** writes no label, spawns nothing and merges
  nothing, and this option breaks all three at once
  ([ADR 0022](0022-item-automation-replaces-the-blocking-watch.md)). A tick is also no
  place to ask a question, because it has no session a human can answer in.
- **The maintainer keeps typing `close N` per item** (rejected) — the state before this
  decision. It costs one typed line per item, and it makes the maintainer rank the
  branches by eye. The ranking is the part a machine does better, and the typed line
  carries no judgement that the drag does not carry.
- **The maintainer types one `merge train` command** (rejected) — it keeps the typing and
  buys only the ordering. The approval then still lives nowhere a later session reads it,
  which is the second half of the problem.
- **Merge in work-item number order** (rejected) — cheap, and wrong exactly where it
  matters. Two items that touch one file conflict in whichever order they land, and the
  number says nothing about which pair those two are.
- **Rank the branches in prose, inside the session** (rejected) — a session that ranks
  five branches by eye is the failure ADR 0015 named. Ordering is what prose holds poorly.
- **Resolve every conflict unattended, and merge the whole queue** (rejected) — that puts
  a judgement call inside an unattended run. It is the one outcome the park rule exists
  to prevent.
- **Give the seam an `--execute` flag** (rejected) — the merge is the **Close
  transaction** this repo already holds. A second merge path is a second place to fix a
  bug in the close order.

## Consequences

- **ADR 0016 keeps its body.** Both quoted sentences stay where they are, narrowed to the
  extent named here and no further. Per [`CLAUDE.md`](../../../CLAUDE.md), a decision that
  narrows an earlier one gets a new ADR and never a silent edit.
- **The label satisfies the teardown confirmation the Safety section asks for.** A close
  inside a train runs all eight steps, teardown included, because the maintainer already
  said yes. So no step of a train asks a second time.
- **A repo with no board is a supported configuration**, the same as today. The `to-merge`
  label is then the only entry to the queue, and the maintainer writes it by hand.
- **A tool with no automation surface loses the trigger and not the flow.** Nothing wakes
  where no schedule exists, so the **Ready queue** read reports the merge queue beside the
  ready queue.
- **This ADR records the decision and wires nothing.** The vocabulary lands with it. The
  tracker config, the seam and the flow change are each separate work.
