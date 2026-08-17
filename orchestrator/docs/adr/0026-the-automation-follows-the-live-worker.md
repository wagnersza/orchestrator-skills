# The Item automation follows the live worker, and one per item stands

An **Item automation**'s precheck names one worktree and one harness process pattern
([ADR 0022](0022-item-automation-replaces-the-blocking-watch.md)). Both are resolved at
spawn, against the implementation worker. A **Phase** transition then moves the work to a
different **Worker**: `phase:review` runs a reviewer, in its own worktree, often under a
different **Harness**. The schedule keeps watching the worktree it was created against.

The first live run left the reviewer unwatched. A second fault hid that one: the seam read
the implementation's inherited commit as the reviewer's newest work product and reported
`stalled` about three minutes in. That second fault belongs to the freshness fact, and the
seam owns its fix. **A repoint does not remove the need for that fix**, because a
reviewer's fresh worktree carries an inherited commit whichever schedule watches it.

**One automation per item stands.** The session **repoints** its precheck at each
transition. `implementation-complete` points it at the reviewer's worktree, with the review
harness's process pattern. `verdict-request-changes` points it back at the implementation
worktree. The repoint is a step of the row in *On the wake*, beside the phase-label write.

## The item is the unit that lives, and the worker is not

ADR 0022 chose one schedule per item and rejected "a single automation for every live
item", because "a leaked one names no item. One per item makes the name the diagnosis."

A schedule per *worker* breaks both halves of that. One item then owns two or three
schedules over its life. Each one names a worker that stops existing at the end of its
round. A **Close transaction** must then find every one of them, and a leak leaves a
schedule whose name has to encode a round.

The item is what lives from the spawn to the close. So step 8 removes one schedule under
one name it can compute, `orchestrator-item-<N>`. The schedule stays bound to the item, and
its precheck follows the worker.

## The repoint is a step of the transition, not a repair

A repoint the maintainer must remember is a repoint the maintainer forgets. It goes in the
same row of *On the wake* as the phase-label write, so one transition is one step with two
acts.

That row is already the right home, and it already writes a label. The repoint needs two values:
the reviewer's worktree and the review harness's process pattern. That same row resolves
both, because it spawns the reviewer.

## What narrows, and what stays

**The split survives.** The automation decides when. The session decides what. The repoint
is written *by the session*, inside a transition a human can interrupt, so the automation
gains no authority. It still writes no label, composes no prompt, spawns nothing and merges
nothing.

**One per item survives, and so does the name.** A leaked schedule still names the item it
leaked from, and step 8 of a **Close transaction** still removes one schedule by one name.

**What narrows is that a precheck is no longer written once.** ADR 0022 says
"Configuration is resolved once, at spawn, into the precheck flags." Two of those flags now
move at a transition. The rest do not, because none of them belongs to a worker: the round
bound, the stall window, the back-off window and the tracker repository all belong to the
item.

This is a new ADR and not an edit to
[`0022-item-automation-replaces-the-blocking-watch.md`](0022-item-automation-replaces-the-blocking-watch.md),
per [`CLAUDE.md`](../../../CLAUDE.md). ADR 0022 keeps its own text.

## One more optional operation, for the reason 11 and 12 already carry

`references/tools/_operations.md` gains optional operation 13, **automation-repoint**:
`automation id, precheck command, worktree → repointed`. `orca.md` fills it in. `cmux.md`
and `herdr.md` record it unsupported, as they do for 11 and 12.

That file's prohibition does not apply, on ADR 0022's own reasoning: it forbids copying
**one identical seam command** into three tool files, and an automation command genuinely
differs per tool. **A tool with no automation surface loses nothing.** It has no schedule,
so it has nothing to repoint, and its spawn already reports that the tick is unavailable.

## Considered Options

- **One automation per item, repointed at each transition** (chosen) — the schedule binds
  to the thing that lives. The precheck follows the thing that works. Removal stays one act
  in the close transaction, and the name stays the diagnosis.
- **One automation per worker** (rejected) — two or three schedules per item, each outliving
  the worker it names. The close transaction must discover a set instead of computing a
  name, which is the "single automation for every live item" failure inverted.
- **Leave the automation on the implementation worktree for the whole run** (rejected) —
  the state this ADR narrows. A reviewer is then unobserved for its whole round, which is
  the failure the tick exists to close. And `dead` cannot fire for the worker that is
  actually live.
- **Give the precheck both worktrees** (rejected) — the reviewer's worktree does not exist
  at spawn, so no flag can carry it. The seam also needs a second process pattern. So the
  flag count grows for values that are half-used at best.
- **A second automation for the reviewer** (rejected) — a fix round then removes one
  schedule and creates another at every transition. That doubles the acts that can fail,
  and a failure between them leaves the item with no observer at all.
- **Remove and recreate the one automation at each transition** (rejected) — two acts where
  one will do, with the same unobserved window between them. An edit fails closed instead:
  a failed repoint leaves the old precheck running.

## Consequences

- **Two precheck flags become per-worker, and the rest stay per item.** `--worktree` and
  `--process` move at a transition. `--rounds`, `--stall-after`, `--back-off` and `--repo`
  are resolved once at spawn, as ADR 0022 wrote them.
- **Only two wake rows gain the act.** `implementation-complete` and
  `verdict-request-changes` repoint. `verdict-approve` and `rounds-exhausted` end the phase
  axis, so there is no next worker to point at. The schedule then ticks quietly until step 8
  of a **Close transaction** removes it.
- **The suppression markers must stop living in the watched worktree.** They live there
  today, so a repoint moves them. An answered wake can then fire again from a fresh
  directory. Moving them out is separate work on the seam. Until it lands, a repoint costs
  at most one repeated wake, which the session answers in one line and nothing else.
- **A skipped repoint leaves the schedule on the wrong worktree, and that is the accepted
  risk.** Nothing checks that a precheck matches the item's phase. A session that answers
  the wake and skips the repoint watches a worker that finished. The mitigation is
  placement rather than a mechanism: the repoint sits in the same row as the label write, so
  the two are one step. The cost is one unobserved round, which the maintainer closes by
  hand, and no work is lost.
- **This ADR declares the repoint and wires nothing.** Operation 13 in
  `references/tools/_operations.md`, its row in the three tool files, and the two wake rows
  in [`orchestrator/SKILL.md`](../../SKILL.md) are separate work. Until they land, an
  automation watches the worktree it was created against, exactly as it does today.
