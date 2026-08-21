# An Item automation replaces the blocking watch, and the seam becomes a predicate

A **Worker watch** starts as a background process of the orchestrator session's own
shell (`scripts/worker_state.py watch ... &`). Close the session, restart the
harness, or reboot the machine, and every watch is gone. Nothing reports that. **A
watch that dies with the session watches nothing**, which is the defect
[ADR 0018](0018-the-worker-watch-is-a-stateless-seam.md) built the watch to close.

The observer becomes an **Item automation** ([`orchestrator/CONTEXT.md`](../../CONTEXT.md)):
one schedule per **Work item**, named `orchestrator-item-<N>`, owned by the **Tool**
rather than by a shell. It ticks once a minute. Its precheck is the same seam, asked as
a predicate instead of run as a loop: exit 0 means a transition is due, and any other
code means nothing to do. On exit 0 it sends one line to the live orchestrator terminal,
and this session runs the transition.

## This narrows ADR 0018, and keeps its split

ADR 0018's decision is **the watch decides when, and the session decides what** —
[ADR 0015](0015-close-is-a-deterministic-transaction.md)'s ordering-in-code,
judgement-in-prose applied a second time. That split is unchanged here, and applied a
third time. The automation decides when. The session decides what. The automation
composes no prompt, writes no label, spawns nothing and merges nothing, so every
destructive act stays in a session a human can interrupt.

**What narrows is the mechanism of the trigger, and nothing else.** The seam survives,
its exit-code contract survives, and the statelessness survives. Only the blocking poll
loop retires, because the loop is the part that lives in a process.

This is a new ADR and not an edit to
[`0018-the-worker-watch-is-a-stateless-seam.md`](0018-the-worker-watch-is-a-stateless-seam.md),
per [`CLAUDE.md`](../../../CLAUDE.md): a decision that narrows an earlier one gets a new
ADR. That is the move [ADR 0019](0019-readiness-is-a-tool-agnostic-process-check.md)
made on ADR 0017's placement. ADR 0018 keeps its own text and gains a pointer to this
one.

## Why this is neither option ADR 0018 rejected

ADR 0018 rejected two options that a reader will recognise in this design. Both
rejections stand, and this design is neither of them.

**"Cron, or a scheduled wake-up, with no seam"** was rejected because "the schedule
solves only the trigger. Each wake-up must then read the checklist, compare two
timestamps and decide, which puts the poll logic back in prose." The words that carry
the rejection are **with no seam**. This design takes the schedule *with* the seam. The
schedule fires, the seam reads the two facts and decides, and the wake-up carries a
decision that was already made in code. No timestamp comparison enters prose.

**"A sub-agent that polls"** was rejected because "its context dies before it can act
… To act, it needs the round counter, the routed skill and the role resolution handed
to it. That is half of `SKILL.md` re-implemented in a prompt." The words that carry that
rejection are **to act**. The agent on a tick does not act. Its whole job is to relay
one line to the live orchestrator session, which holds the routed skill, the role
resolution and the flows. The round counter is read from the tracker rather than handed
over, per the **Completion signal** entry of `CONTEXT.md`. So nothing from `SKILL.md` is
copied into a prompt.

## The precheck is what makes a one-minute tick affordable

The seam becomes a **predicate**, and the precheck contract stays binary: exit 0 means a
transition is due, and non-zero means nothing to do and the run records as skipped. So a
quiet minute runs one bounded command, loads no model and reads no context. Watching
five siblings all day costs five bounded commands a minute.

**Which transition it is rides on the printed line, not on a second exit code.** The
line names one of seven outcomes: implementation complete, verdict `approve`, verdict
`request-changes`, rounds exhausted, proof complete, `dead`, `stalled`. Adding a code
per outcome would break the binary contract the precheck needs, and the session already
answers a printed line with a lookup.

`EXIT_USAGE` stays 64. A flag with a typo must never read as a due transition.

The affordability is also why the parent spec's original cheap-model requirement
disappeared rather than being met. `orca automations create` takes `--provider` and no
model or effort flag. A design that needs a model choice cannot be expressed on this
surface at all. A relay needs none.

## Stuck splits into dead and stalled

ADR 0018 had one stall outcome, reached by one signal: no fresh work product inside the
stall window. The one-minute tick makes a cheaper distinction worth drawing, because two
causes of "stuck" have opposite responses.

- **`dead`** — no live agent process with its working directory inside the worktree.
  This is [ADR 0019](0019-readiness-is-a-tool-agnostic-process-check.md)'s readiness
  check, re-run every tick. It needs no stall window, so it fires in about a minute, and
  a re-prompt cannot help, because nothing is listening.
- **`stalled`** — a live agent process with work product older than the stall window.
  Here a re-prompt is the response that works, and it is ADR 0018's rule unchanged.

The two never both fire, because a dead worker has no live process and a stalled one
does. **This also repairs the risk ADR 0018 accepted**, that a reviewer is watched less
closely than an implementation worker. A reviewer that dies is now reported in about a
minute by its process, rather than at the bounded maximum wait by its silence. The
accepted risk narrows to the case it was really about: a healthy reviewer that thinks
for a long time still produces no work product, and it is still not read as stalled.

## Two optional operations, because an automation is genuinely tool-shaped

`references/tools/_operations.md` gains `automation-create` (11) and
`automation-remove` (12), **optional** in the same sense as `tab-open` (7). `orca.md`
fills them in. `cmux.md` and `herdr.md` record them as unsupported, and a spawn there
skips the tick and says so in the report. So the tick is an addition and never a
requirement.

That file's prohibition does not apply here, and the distinction matters. The
prohibition ([ADR 0019](0019-readiness-is-a-tool-agnostic-process-check.md)) is about
copying **one identical seam command** into three tool files. An automation command
genuinely differs per tool: one tool has the surface and two do not. That is the exact
shape a tool row exists for.

Removal folds into step 8 of the **Close transaction**: the teardown command the session
passes to `scripts/close_item.py --teardown-command` removes the worktree and the
automation together. So the eight steps and their order stand, and ADR 0015 needs no
edit. A refusal at any earlier step leaves the automation in place, with the item still
observed.

## Considered Options

- **A tool-owned schedule whose precheck is the seam** (chosen) — the observer outlives
  the session that created it, which is the defect. The seam and its contract are
  reused rather than replaced, and a quiet tick costs one bounded command. The relay
  keeps every act in the session.
- **Keep the blocking watch, as ADR 0018 wrote it** (rejected) — the state this ADR
  narrows. It was correct against the failure it was written for, a finished worker
  nobody notices. It cannot survive a restart of the shell that owns it, and it reports
  nothing when it dies.
- **Keep the blocking watch and re-launch it on session start** (rejected) — a session
  that starts fresh does not know which items were live. So the re-launch needs a
  registry of live watches. That is a second store of a fact the tracker already holds,
  and it is wrong exactly when a session died without writing it.
- **A schedule with no seam** (rejected, again) — ADR 0018's rejection stands and the
  reason is unchanged: the poll logic moves back into prose, and prose is what nothing
  executes.
- **A polling sub-agent that acts** (rejected, again) — ADR 0018's rejection stands. A
  relay is not that agent: it decides nothing and needs no part of `SKILL.md` handed to
  it.
- **A single automation for every live item** (rejected) — one schedule that must
  discover its own item set, and a leaked one names no item. One per item makes the name
  the diagnosis. It also makes removal part of the close transaction that already tears
  the item down.
- **A back-off in the tool's run history** (rejected) — run history is tool-specific and
  the seam names no tool. A marker file in the worktree suppresses a repeat fire inside
  the window. It dies with the worktree, which is when the suppression stops mattering.

## Consequences

- **`worker_state watch` retires, and no caller revives it.** The seam gains `phase`,
  the predicate. `ready` is unchanged, and `phase` reuses its process check for the
  `dead` outcome.
- **The exit code stays the contract, and it narrows to a predicate.** Zero means a
  transition is due, and every other code means nothing to do. The seven outcomes ride
  on the printed line, and the session answers each with a lookup rather than an
  interpretation.
- **Configuration is resolved once, at spawn, into the precheck flags.** The session
  reads four values from `docs/agents/orchestrator.md` and writes them into the command
  string: the round bound, whether the proof phase applies, the harness process pattern,
  and the stall window. So the seam parses no configuration file and names no harness.
  That is the posture every existing argument already takes.
- **A tool with no automation surface loses nothing it has today.** The spawn works
  unchanged, and the report says the tick was skipped.
- **The wake needs a resolvable orchestrator terminal, and that is the accepted risk.**
  Where none exists, the automation posts the same line as a comment on the work item. So
  a transition is recorded late rather than lost.
- **This ADR declares the design and wires nothing.** The `phase` subcommand, the two
  operation rows, and the flow changes in `SKILL.md` are separate work. Until they land,
  a worker is watched exactly as it is today, by the blocking watch this ADR retires.
