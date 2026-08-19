# The tick delivers its own wake, so no agent runs on a tick

[ADR 0022](0022-item-automation-replaces-the-blocking-watch.md) put a **relay** between
the precheck and the **Orchestrator**: on exit 0 the **Item automation** starts a bounded
agent, and that agent sends one line to the session. `orca automations create` requires
`--prompt` and `--provider`, so a precheck that exits 0 has no other way to reach anybody.

**That agent is the only model cost in the tick loop, and it buys nothing a command cannot
do.** A quiet minute already loads no model, because the precheck exits non-zero and the
run records as skipped. So the cost falls exactly on the minute a transition is due, which
is the minute the session is about to spend real tokens anyway. And the whole job is a
send.

The seam gains a third subcommand, `wake`, which is the whole body of a tick. It asks the
same `phase` predicate, with the same eight outcomes, the same order and the same
`--back-off` window. Where a transition is due it delivers the printed line itself, to the
first target that succeeds. **It exits non-zero on every path**, so the provider never
loads and no agent runs on a tick. The automation keeps `--prompt` and `--provider`
because the CLI demands them, and both stay inert.

The three targets are ADR 0024's three, in ADR 0024's order: the terminal handle, then the
terminal title, then a comment on the **Work item**.

## Why delivery is not action

The line the seam sends is the line the seam printed. Nothing in it was decided by the
send, and nothing new is decided by the target that takes it.

Every prohibition in the **Item automation** and **Worker watch** entries of
[`orchestrator/CONTEXT.md`](../../CONTEXT.md) holds unchanged. The tick writes no label,
composes no worker prompt, kills no process, moves no card, spawns nothing and merges
nothing. **The tick decides when, and the session decides what.** That split comes from
ADR 0022, and from [ADR 0015](0015-close-is-a-deterministic-transaction.md) before it.
This ADR applies it once more. The one file the tick writes is still the `--back-off`
marker, which changes whether an outcome is reported again and never which outcome holds.

**This accepts one tension: a send into a terminal is a submission.** The line arrives in
a live session's input, and that session then acts. So the seam is one step closer to the
act than a printed line is. What keeps the split intact is that the seam chooses nothing
about the act. It knows one outcome word and one target, and it holds no round bound, no
routed skill and no role resolution. Every decision stays with the session that reads the
line, which is the session a human can interrupt. A relay agent had the same reach and
cost a model run to have it.

## The seam still names no Tool

`--send-command` is a template, and the spawn resolves it from the tool file's operation 4.
`{target}` is where the terminal goes and `{text}` is where the line goes. The seam splits
that template into arguments before it writes either one in, so no shell reads the wake
line.

That is the posture every other value in the precheck already takes: **"Configuration is
resolved once, at spawn, into the precheck flags"** (ADR 0022). The handle is one such
value (ADR 0024), the process pattern is another, and the tracker CLI is a third. So a
sixth **Tool** stays a Markdown change. The prohibition in
[ADR 0019](0019-readiness-is-a-tool-agnostic-process-check.md) on copying a seam command
into three tool files is untouched.

## This narrows ADR 0022 and ADR 0024, and both keep their text

ADR 0022's accepted risk stands as written, and its fallback is target three here. ADR
0024's three targets and their order stand as written. **What narrows is who delivers, and
nothing else.** The relay agent retires. The targets, the order, the fallback and the
reason for each are unchanged.

ADR 0024 wrote that the handle "goes into the relay prompt, which is operation 11's
`--prompt`". It now goes into operation 11's `--precheck`, as `--handle`. That is the same
resolution at the same moment, into the other flag on the same command.

This is a new ADR and not an edit to either of them, per
[`CLAUDE.md`](../../../CLAUDE.md): a decision that narrows an earlier one gets a new ADR.
Both keep their own text.

## Considered Options

- **The tick delivers its own wake** (chosen) — a due transition costs one bounded
  command, the same command a quiet minute costs. An item that runs a full review loop
  then costs zero agent runs on its ticks. The seam already prints the line, and the
  delivery is the last step of the same act.
- **Keep the relay agent, which is ADR 0022 as written** (rejected) — the state this ADR
  narrows. It was correct against the failure it was written for, a watch that dies with
  its shell, and it kept every act in the session. It also loads a model to send one
  line. A bounded agent can fail at that send in ways a command cannot. It can read the
  prompt loosely, answer in prose, or exit before it sends.
- **Carry the handle in the relay prompt, which is ADR 0024 as written** (rejected) — the
  target is right and the carrier is one indirection too many. A handle in a prompt needs
  an agent to read the prompt and act on it. A handle in a flag needs neither.
- **Replace the tool's schedule with `cron` or `launchd`** (rejected) — a schedule outside
  the tool loses the teardown that step 8 of a **Close transaction** already owns
  ([ADR 0015](0015-close-is-a-deterministic-transaction.md)). A closed item then leaves a
  live schedule behind, and nothing names it. It also gives the precheck a bare
  environment: no worktree binding, and none of the login state the tracker read and the
  send both need. The run history that records a skipped tick is also gone.
- **A precheck that exits 0 and a prompt that says nothing** (rejected) — it keeps the
  provider, so it keeps the model run. The cost is what this ADR removes.

## Consequences

- **An item costs zero agent runs on its ticks.** The **Orchestrator** session spends
  tokens, and only when a transition is due. A watch on five siblings all day costs five
  bounded commands a minute, and nothing else.
- **`wake` exits 4 where it delivered the wake, and 5 where no target took it.** Both are
  non-zero, so both record as skipped. Two codes rather than one, because a run history
  that says "skipped" is where a maintainer looks first. A wake delivered late and a wake
  never delivered ask for different repairs. A delivery that fails everywhere prints each
  failure.
- **The wake goes into a terminal that can be busy, and the tick does not wait for idle.**
  That is the accepted risk. A line sent into a working session lands in its input and
  waits there, and a harness that is mid-turn can drop it. A wait for idle puts a second
  condition and a timeout inside the tick, which is a loop again. And a busy session is
  one that already works on this item. The `--back-off` window is the mitigation: the same
  outcome is delivered again after it, and not sixty times inside it.
- **The seam writes the back-off marker before it attempts the delivery.** So a wake that
  no target took stays suppressed for the window, as an unanswered wake does. The printed
  failures are what a maintainer reads instead. A marker written only on a successful
  delivery makes a busy terminal retry every minute. That is the flood the window exists
  to stop.
- **A tool with no automation surface changes nothing.** Operations 11 and 12 stay
  optional, `cmux` and `herdr` still record them as unsupported, and the spawn report still
  says the tick is unavailable there.
- **One work item wires this ADR. Nothing here is declared and deferred.** The `wake` subcommand,
  the precheck in *Start the tick* of [`orchestrator/SKILL.md`](../../SKILL.md), operation
  11's example in [`references/tools/orca.md`](../../references/tools/orca.md) and step 5a
  of [`orchestrator-setup/SKILL.md`](../../../orchestrator-setup/SKILL.md) land with it.
