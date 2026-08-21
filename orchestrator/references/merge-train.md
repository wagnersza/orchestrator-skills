# The merge train

A **Merge queue** is the set of open work items ready to merge. A **Merge train** is one
ordered run over that set. Both terms are defined in [`../CONTEXT.md`](../CONTEXT.md).

A train runs in the **Orchestrator** session. It resolves an order, then runs one full
**Close transaction** per item in that order, teardown included. Rationale, the rejected
alternatives and the accepted risk:
[ADR 0037](../docs/adr/0037-the-merge-queue-is-an-ordered-train.md). Why a dragged card is
the ask: [ADR 0038](../docs/adr/0038-the-to-merge-column-is-intent.md).

## The queue

An item is in the queue when it carries the `to-merge` label, or when its card sits in the
board's `To merge` column. The set is read fresh when a train starts, which is the rule the
**Ready queue** already takes. A repo with no board has the label as its only entry.

## The ordering

1. Test-merge each queued branch onto the default branch. A branch that conflicts there is
   parked before the train starts.
2. Rank the rest by how many other queued branches they share a changed file with, fewest
   first. Break a tie by work-item number, ascending.
3. After each real merge, the next branch runs step 1 of the **Close transaction**. That is
   where a late conflict appears, and where the park rule fires again.

File overlap is a cheap proxy, and the test-merge is the real check. The seam does both, so
a wrong ranking costs one extra park and never a wrong merge.

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
