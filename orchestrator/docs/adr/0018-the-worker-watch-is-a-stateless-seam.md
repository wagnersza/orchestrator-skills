# The Worker watch is a stateless seam, and every action stays in the session

An orchestrator session spawns a worker, sends the prompt, and then pays it no more
attention. Nothing in this skill watches a live worker. The monitor section of
[`orchestrator/SKILL.md`](../../SKILL.md) is four bullets the maintainer runs by hand,
when they remember. The adversarial-review section opens with "When a work item reaches
the review state" — a condition that no actor here detects.

Three failures land on the maintainer because of that:

1. **A finished worker that nobody notices.** It ticks its last box, flips its label,
   and goes idle. Review never starts, even where config enables it.
2. **A stalled worker that stays stalled.** The stall rule and its response are already
   written down. They are prose, and nothing executes prose.
3. **A batch that multiplies both.** Five siblings spawned together are five workers
   nobody observes, and they finish in an order nobody predicted.

The answer is a **Worker watch** ([`orchestrator/CONTEXT.md`](../../CONTEXT.md)): one
process per live worker that observes the worker's own work product and wakes the
session when something needs a decision.

## The split is the whole decision

The watch decides **when**, and the session decides **what**. That is
[ADR 0015](0015-close-is-a-deterministic-transaction.md)'s precedent applied a second
time: **ordering in code, judgement in prose.**

The watch blocks, polls two facts on the file system, and exits with a code per
outcome. It composes no prompt, kills no process, writes no label, and spawns nothing.
On the wake, the session runs the flows `SKILL.md` already holds — adversarial review
on a finish, the existing stall rule on a stall.

The ordering half is a seam, `scripts/worker_state.py`. This ADR names it before it
exists, the way [ADR 0015](0015-close-is-a-deterministic-transaction.md) named
`scripts/close_item.py`: the decision lands here, and the file lands with the flow
change that consumes it.

Two properties follow from the split, and both are load-bearing.

**The watch holds no state between invocations.** Every fact it needs is on disk when
it starts. So the session can stop a watch, re-prompt the worker, and start a new watch
with no handover. The stall counter lives in the session's report to the maintainer,
because the count is what the maintainer decides against.

**Every destructive act stays in a session a human can interrupt.** A watch with the
authority to kill is the one part of this design with no witness.

## The two signals cannot report success for a dead worker

[ADR 0017](0017-gate-worker-readiness-on-a-process-check.md) names the family this
design has to avoid: **a failure mode that reports success.** Both signals a tool
already offers are members of it. On the run that produced that ADR, the agent exited
first. `orca terminal read` then returned `status: running` for the terminal, and
`orca terminal wait --for tui-idle` returned `satisfied: true` for the same one. An idle
shell is idle. A dead worker reads as a live one.

The two signals here are chosen because a dead worker cannot produce either:

- **Complete** — the **Completion signal** fired. Every box in
  `.orchestrator/checklist-<item>.md` is ticked, or a `Verdict:` comment sits on the
  work item.
- **Stalled** — no fresh work product inside the stall window. The watch reads the
  freshness of the checklist file and of the branch's last commit, and not the liveness
  of a shell.

Both are **work product**. A worker writes them by doing the work, so neither one
outlives the worker that produced it. Neither one is true of a terminal that merely
still exists.

## The accepted risk: a reviewer is watched less closely

A review worker ticks no checklist and can reach its verdict with no commit. So the
stall side of the watch is weaker for a reviewer than for an implementation worker: for
a long stretch, a healthy reviewer and a dead one produce the same absence of work
product.

**`--max-wait` carries that risk.** A reviewer that neither posts a verdict nor moves
reaches the bounded maximum wait and wakes the session with a distinct code. So the
outcome is a late report rather than a lost round, which is what the failure costs
today. This is written down as accepted risk for two reasons. A later reader must not
read it as an oversight, and must not repair it with a screen check.

## A re-prompt resets the worker's context first

Every re-prompt resets the worker's context before it sends — a stall recovery and a
review fix round alike. A worker that burned a long attempt carries that whole attempt
into its retry, and the retry is the turn that most needs headroom.

The reset is what makes the re-prompt **self-contained**. A cleared worker no longer
holds its spawn prompt. So the re-prompt must carry four things again: the routed skill
as a literal invocation, the worker's own harness plus model plus effort plus role, the
acceptance criteria, and the scope edges. That is the same requirement the
adversarial-review section of [`orchestrator/SKILL.md`](../../SKILL.md) already puts on
a fix prompt, reached from a second direction. So the reset costs no new contract.

The reset is safe because of the **Checklist**. Progress lives on disk, so a reset
loses the worker's reasoning and never its position. The command is harness-shaped: on
`claude` it is `/clear`, and where a harness offers no reset the step is skipped and the
report says so.

## Considered Options

- **A stateless process that blocks and polls, with every action in the session**
  (chosen) — the
  observation is an ordering problem and the response is a judgement. So each half gets
  the mechanism that fits it. It is also the only option here that a test can drive to
  a fixed exit code.
- **A sub-agent that polls** (rejected) — its context dies before it can act, which is
  the failure it was chosen to fix. To act, it needs the round counter, the routed
  skill and the role resolution handed to it. That is half of `SKILL.md` re-implemented
  in a prompt. A copied rule set drifts from the body that maintains it, and this copy
  lives in a prompt nobody reviews.
- **A poll loop in the orchestrator's own turn** (rejected) — a turn spent on a poll
  cannot answer the maintainer. The session is the one part of this system a human talks
  to. A poll loop blocks it to read a file, which spends the scarcest thing here.
- **Cron, or a scheduled wake-up, with no seam** (rejected) — the schedule solves only
  the trigger. Each wake-up must then read the checklist, compare two timestamps and
  decide, which puts the poll logic back in prose. That is the state this ADR exists to
  leave.
- **An unconfirmed kill on the second stall** (rejected) — a watch cannot read intent in
  an uncommitted diff. A dirty tree is this skill's named data-loss case. A re-prompt is
  additive and stays unconfirmed. A teardown destroys, so it keeps its confirmation.
- **An opt-in watch** (rejected) — an opt-in watch is off exactly when the maintainer
  forgets, which is the scenario the whole change exists for. So a watch is a mandatory
  step of every spawn, impl and review alike.

## Consequences

- **One more process per live worker.** It costs a blocked poll of two file-system
  facts. The cost it replaces is a finished item that sits idle, and a stall that lasts
  as long as the maintainer is away.
- **The exit code is the contract, and one printed line goes with it.** The session
  responds with a lookup and not an interpretation. So the response stays in `SKILL.md`
  where a reader can change it, and the watch never learns what a review round is.
- **A vanished worktree is its own outcome.** A torn-down worker is reported, and it is
  never treated as a stall. So nothing re-prompts a worker that no longer exists.
- **The stall rule now runs.** It is unchanged, and this is the first actor that fires
  it. A rule that no actor performs is the defect this ADR closes. Apply that test to
  the next rule in this repo that describes behaviour nothing performs.
- **This ADR declares the design and wires nothing.** The vocabulary lands with it. The
  seam, its tests and the flow changes in `SKILL.md` are separate work. Until they land,
  a worker is watched exactly as it is today.
