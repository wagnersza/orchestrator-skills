# The merge train

A **Merge queue** is the set of open work items ready to merge. A **Merge train** is one
ordered run over that set. Both terms are defined in [`../CONTEXT.md`](../CONTEXT.md).

A train runs in the **Orchestrator** session. It resolves an order, then runs one full
**Close transaction** per item in that order, teardown included. Rationale, the rejected
alternatives and the accepted risk:
[ADR 0037](../docs/adr/0037-the-merge-queue-is-an-ordered-train.md). Why no label records
the ask:
[ADR 0053](../docs/adr/0053-one-work-state-label-and-a-computed-position.md).

## The queue

An item is in the queue when the maintainer's ask names it. The ask is typed, and the set is
read fresh when a train starts, which is the rule the **Ready queue** already takes. Nothing
on the tracker records the ask, so a train that runs twice on one ask needs the maintainer to
type it twice.

## The ordering

1. Test-merge each queued branch onto the default branch. A branch that conflicts there is
   parked before the train starts.
2. Rank the rest by how many other queued branches they share a changed file with, fewest
   first. Break a tie by work-item number, ascending.
3. After each real merge, the next branch runs step 1 of the **Close transaction**. That is
   where a late conflict appears, and where the park rule fires again.

File overlap is a cheap proxy, and the test-merge is the real check. The seam does both, so
a wrong ranking costs one extra park and never a wrong merge.

## The order comment

Where the plan holds more than one item, the order is published on the PR/MR of each item in
it. One comment per PR, and it names the neighbours: `merge after #12, before #14`. The first
item names no predecessor and the last names no successor.

Three rules keep it from becoming noise:

- **The comment is rewritten in place, and never posted twice.** It is found by a fixed first
  line, `<!-- orchestrator:merge-order -->`, and that literal is shared by the writer and the
  search. A tick runs once a minute, so a second post is sixty comments an hour.
- **A plan of one item writes nothing.** An order of one is not an order.
- **The session writes it, and the seam does not.** `scripts/merge_train.py` still prints
  JSON and comments nowhere, which is the contract below.

The order is recomputed every time a train starts, because the queue is read fresh. So the
comment is a report of the current plan and not a promise about the next one.

## The park rule

Where a branch conflicts, the session does three things:

- Drop the item back to the review state.
- Comment the conflicting paths on the work item.
- Continue with the next branch.

Nothing unattended resolves a hunk. A parked item is not a failed one. It needs the
judgement that step 1 of the **Close transaction** keeps in prose. So it goes back to the
human who can give that judgement.

## The seam's contract

`scripts/merge_train.py` resolves the order. This file names the seam before it exists: the
contract is declared here, and the file lands with the flow change that consumes it.

- **It plans, and it merges nothing.** There is no `--execute` flag, because there is
  nothing to execute. The merge is the **Close transaction** this repo already holds, run
  once per item in the planned order.
- **It mutates no checkout a session works in.** It creates a temporary checkout,
  test-merges each queued branch there, and removes the checkout again.
- **It prints one JSON object** on stdout: the planned `order`, and a `parked` list that
  names the conflicting paths of each parked branch.
- **It writes no label, closes nothing and comments nowhere.** Every tracker write belongs
  to the session, which is the split a **Worker watch** already takes.
