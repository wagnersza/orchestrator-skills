# One re-prompt, then a human

A model diagnosed a stalled worker. The **Orchestrator** read a `stalled` outcome, reset the
worker's context, re-prompted it, and posted one `Stall:` comment. At the second such comment
it declared the item mis-routed, tore the worker down, and re-spawned it a rung up: `light` to
`heavy`, or `heavy` at `max`.

**Two facts in that rule are not facts.** The rung is a judgement about a terminal the session
cannot see. It reads one outcome word and infers that a bigger model is the repair. The cause
is as often a busy port or a question nobody answered. The count also named the worker's
current `(Model, Effort)` pair, so a re-spawn reset it by design. A worker that stalled four
times across three rungs read as *stall 1 of 2* on the fourth.

**A stalled worker also had no owner.** `stalled` carried no label, so the tick exited 2 and
left the item at `in-progress`. Nothing then woke a session
([ADR 0056](0056-the-tick-applies-the-transition-it-computed.md) deleted the wake). So the
re-prompt waited for a maintainer who had no reason to look.

## The decision

**One re-prompt, then a human.** The `stalled` outcome now carries a transition, and the tick
applies it.

**The count is the number of `Re-prompt:` comments on the work item.** `Tracker.item_facts()`
already returns the comment bodies, so the count needs no second read. It names the item and
nothing else. So no re-spawn resets it, and a restart reads the number a maintainer reads.

**The first stalled tick posts one `Re-prompt:` comment and exits 4.** The comment carries
what the tick saw and the unticked boxes of the **Checklist**, so the retry is
self-contained. No label moves, because a stalled worker still owns its item.

**The second stalled tick writes `needs-human` with one comment, and exits 2.** It re-prompts
nothing. Only the maintainer removes that label, and every later tick leaves the item alone
while it is there.

**The bound is one, and it is not an argument.** A bound a caller can raise is a climb under
another name, and the climb is what this decision deletes.

**The model ladder and the stall diagnosis leave
[`orchestrator/SKILL.md`](../../SKILL.md).** Nothing computes a rung, and no session diagnoses
why a worker stopped. The effort step a fix round takes after a review round is a different
rule with a different trigger, and it stays where it is
([`references/models.md`](../../references/models.md)).

## What the seam still refuses to do

**The seam composes no prompt and delivers nothing.** It writes one comment on the tracker.
The reset of the worker's context and the send of the unticked boxes stay a session's act.
The comment is what tells a session that the act is due. So no transition here depends on a
delivery that can fail. That is the guarantee
[ADR 0056](0056-the-tick-applies-the-transition-it-computed.md) bought when it deleted the
wake.

**`dead` keeps the answer it has.** No live agent process has its working directory inside the
worktree, so nothing listens and a re-prompt cannot reach one. That outcome still carries no
transition, and the pending decision is still a teardown a human confirms.

## This supersedes ADR 0023 and narrows ADR 0018

[ADR 0023](0023-the-stall-count-is-a-tracker-comment.md) chose the `Stall:` comment, counted
per `(Model, Effort)` pair. **This keeps its store and drops its scope.** The tracker is still
where the count lives, for the reason that ADR gives: a count in a session's context dies with
the session. What goes is the pair, which existed to let a re-spawn start the count again. The
literal changes with it. `Re-prompt:` names what the comment records, and a stall is the fact
that fires it.

[ADR 0018](0018-the-worker-watch-is-a-stateless-seam.md) said the seam counts nothing.
**It now counts one literal, and it stores nothing to do it.** It reads the count from the
comment bodies each tick already reads. So the seam still holds no state between reads, and a
restart is still free. That is the guarantee ADR 0018 made load-bearing, and this keeps it.

This is a new ADR and not an edit to either of them, per
[`CLAUDE.md`](../../../CLAUDE.md).

## Considered Options

- **One re-prompt, then `needs-human`** (chosen) — the retry is cheap, and the second stop is
  a fact rather than a guess. `needs-human` already stops every tick, so the machine leaves
  the item alone with no second mechanism.
- **Keep the rung climb, and count per item** (rejected) — it fixes the count and keeps the
  judgement. A rung up costs two spawns plus a review cycle
  ([`references/models.md`](../../references/models.md)), and nothing on the tracker says a
  bigger model is the repair.
- **Re-prompt with no bound** (rejected) — a worker that cannot finish then burns a comment a
  minute, and no tick ever asks for a human.
- **A marker file in the worktree that counts the attempts** (rejected) — the store
  [ADR 0023](0023-the-stall-count-is-a-tracker-comment.md) already rejected. It dies with the
  worktree, a restart cannot read it, and a maintainer who reads the item cannot see it.
- **A `re-prompt:1` label** (rejected) — one more label for a fact a count answers, and each
  flip is a write that can fail.

## Consequences

- **The `stalled` outcome carries a transition, so the tick writes on it.** One comment on the
  first stall, and one label plus one comment on the second. A stall is rare, so the cost is a
  write per stall rather than a write per tick.
- **Four outcomes now carry no label**: `gates-unproven`, `verdict-request-changes`, `dead`
  and `unreadable`.
- **The literal counts only where it opens a line**, which is where the tick writes it. A
  bare substring test counted a review note that quotes the literal, and a maintainer who
  writes about a re-prompt must not spend one. `Verdict:` is narrow for the same reason: its
  pattern needs one of two values after the literal.
- **The literal `Re-prompt:` is quoted here, in the Completion signal entry of
  [`orchestrator/CONTEXT.md`](../../CONTEXT.md), and in
  [`references/tracker-reads.md`](../../references/tracker-reads.md).** A writing pass leaves
  it byte-identical, the same rule `Verdict:` already carries.
- **A maintainer reads both counts the same way.** The **Review round** number is the count of
  `Verdict:` comments, and the retry count is the count of `Re-prompt:` comments. One tracker
  read of one fixed literal answers each.
- **An item that wears `needs-human` needs a human to clear it.** That is the point of the
  label, and it is the one place this decision costs the maintainer a step.
