# The stall count is a tracker comment, and no session remembers it

[ADR 0018](0018-the-worker-watch-is-a-stateless-seam.md) put the stall count in one
place: "The stall counter lives in the session's report to the maintainer, because the
count is what the maintainer decides against." That held while one session owned one
blocking watch from the spawn to the wake.

[ADR 0022](0022-item-automation-replaces-the-blocking-watch.md) removes that guarantee.
An **Item automation** outlives the session that created it. So the session that answers a
`stalled` wake is often not the session that answered the last one. **A restart destroys a
count that lives only in context, and the tick exists to survive a restart.** The
maintainer then sees `stall 1 of 2` twice, and the second stall never reaches its teardown.

The count moves to the **Tracker**. On every stall re-prompt the **Orchestrator** posts one
comment on the **Work item**. That comment carries the literal `Stall:`, plus the worker's
model and effort. The stall count is the number of those comments that name the worker's
current `(Model, Effort)` pair.

## This is the shape the round number already has

Nothing here is new. A **Review round** number is the count of `Verdict:` comments on the
work item, per the **Completion signal** entry of
[`orchestrator/CONTEXT.md`](../../CONTEXT.md). Both counts are now one tracker read of one
fixed literal. So a report restates both, and the maintainer remembers neither.

**The `(Model, Effort)` pair is what makes a re-spawn start again.** The stall rule tears
a worker down on its second stall and re-spawns a rung up, and a rung up is a different
pair. So the new worker's first stall reads as its first, with no reset to write and no
counter to clear. At `max` there is no rung above, so a third stall reads as three. That
is the case where the pending decision belongs to a human rather than to another rung.

## This narrows ADR 0018 and keeps its split

**The seam still never learns what a stall count is.** It reports one outcome per tick and
counts nothing, which is the statelessness ADR 0018 made load-bearing. What narrows is
where the *session* reads the count from. The report is still where the maintainer sees
it. So this keeps ADR 0018's reason: "the count is what the maintainer decides against".

This is a new ADR and not an edit to
[`0018-the-worker-watch-is-a-stateless-seam.md`](0018-the-worker-watch-is-a-stateless-seam.md),
per [`CLAUDE.md`](../../../CLAUDE.md).

## Considered Options

- **A `Stall:` comment on the work item, counted per `(Model, Effort)` pair** (chosen) —
  the tracker is the store this repo already declares for a durable fact
  ([ADR 0021](0021-phase-is-a-second-label-family.md)), and a comment is the shape the
  round number already takes. A human also reads the count on the issue, with no
  transcript to open. It costs one write, on the stall path only.
- **The session's own context** (rejected) — the state this ADR narrows. It is correct
  until the session restarts, and the tick exists because sessions restart.
- **The `--back-off` marker file the seam writes** (rejected) — it is a suppression window
  and not an answer, and its own docstring says so. It refreshes on each fire, so it
  cannot tell a second stall from a fifth. It also lives in the worktree.
- **A file in the worktree written by the session** (rejected) — ADR 0021 rejected a
  worktree file as the store for the **Phase**, and the reason carries over. It dies with
  the worktree, and a maintainer who reads the card cannot see it.
- **A `stall:1` / `stall:2` label family** (rejected) — two more labels for a fact a count
  already answers. ADR 0021 rejected a label that flips once per round for the same reason:
  each flip is a network write that can fail.

## Consequences

- **One tracker write joins the stall response**, in the same step as the re-prompt. A
  stall is rare, so the cost is a write per stall rather than a write per tick.
- **The count survives a restart, a reboot and a teardown.** So does the round number, and
  a session reads both the same way.
- **The literal `Stall:` is quoted here and in
  [`orchestrator/SKILL.md`](../../SKILL.md).** A writing pass leaves it byte-identical, the
  same rule `Verdict:` already carries.
- **The bound stays two, and the stall rule is otherwise unchanged.** The first stall
  re-prompts and stays unconfirmed. The second tears the worker down and re-spawns a rung
  up, and that teardown keeps its confirmation.
- **The seam reads no `Stall:` comment.** Nothing in `scripts/worker_state.py` changes. The
  `stalled` outcome stays the same two facts: a live process, and work product older than
  the stall window.
