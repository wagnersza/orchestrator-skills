# The wake target is a terminal handle, resolved at spawn

[ADR 0022](0022-item-automation-replaces-the-blocking-watch.md) gave the relay one
target: the orchestrator terminal, found **by title**. The first live run of an **Item
automation** found no terminal by the title `orchestrator`. So the relay posted its line
as a comment on the **Work item**. No session read it, and the item held `phase:impl`
after its worker had finished. The tick worked. The wake reached nobody.

**A title is a display string, and the harness owns it.** The `claude` harness renames
its own tab while the session runs, and that is the harness the **Orchestrator** itself
runs under. So the one target ADR 0022 chose is the one the orchestrator's own harness
overwrites.

The relay now takes three targets, in this order:

1. **The terminal handle**, resolved at spawn and written into the relay prompt.
2. **The terminal title**, for a session that cannot resolve a handle.
3. **A comment on the work item**, which is ADR 0022's fallback unchanged.

**The spawn report names which of the three is live.** A comment-only wake is then a fact
the maintainer reads at spawn, rather than a silence they find many runs later.

## The handle is a fact the spawn already reads

Nothing new is discovered here. `references/tools/_operations.md` calls a handle
**stable** in operation 3, and it requires the handle to survive TUI boot. Operation 9
returns `{handle, title}` for a worktree, so both facts come from one call. A session that
can list a worker can also list itself.

The handle then goes into the relay prompt, which is operation 11's `--prompt`. That is
the posture every other value already takes: **"Configuration is resolved once, at spawn,
into the precheck flags"** (ADR 0022). The target is one more such value, and it is an
argument rather than a store.

## This narrows ADR 0022, and keeps its fallback

ADR 0022's accepted risk stands as written: "The wake needs a resolvable orchestrator
terminal, and that is the accepted risk. Where none exists, the automation posts the same
line as a comment on the work item." That comment is fallback three here, for the same
reason it was the fallback there: a transition is recorded late rather than lost.

**What narrows is how the terminal is found, and nothing else.** The relay still carries
no judgement. It still sends one line. It writes no label, spawns nothing and merges
nothing, so the prohibition in the **Item automation** entry of
[`orchestrator/CONTEXT.md`](../../CONTEXT.md) is untouched.

This is a new ADR and not an edit to
[`0022-item-automation-replaces-the-blocking-watch.md`](0022-item-automation-replaces-the-blocking-watch.md),
per [`CLAUDE.md`](../../../CLAUDE.md): a decision that narrows an earlier one gets a new
ADR. That is the move
[ADR 0023](0023-the-stall-count-is-a-tracker-comment.md) made on ADR 0018's stall
counter. ADR 0022 keeps its own text.

## The rename in setup survives, and stops being the only target

Step 5a of [`orchestrator-setup/SKILL.md`](../../../orchestrator-setup/SKILL.md) renames
the orchestrator terminal to `orchestrator`. That step stays. Fallback two needs it, and a
titled terminal is what a human recognises in a tab list. What changes is its weight: the
title becomes a second chance instead of the mechanism.

## Considered Options

- **A handle resolved at spawn, with two fallbacks** (chosen) — the target is the
  identifier the **Tool** issued, so no display string moves it. The title and the comment
  stay, so a session that cannot resolve a handle keeps working. A session with no
  terminal at all still records the transition.
- **The title alone, as ADR 0022 wrote it** (rejected) — the state this ADR narrows. It
  was correct against the failure it was written for, a wake with nowhere to go. It fails
  against the harness the orchestrator runs under, which renames the tab the title names.
- **The handle alone** (rejected) — a handle is stable and not immortal. A maintainer can
  close the orchestrator terminal and open a new one. The handle then points at nothing,
  and a single target has no fallback. It also breaks a repo configured before the handle
  existed.
- **Resolve the handle at each tick, inside the relay** (rejected) — the relay must then
  decide which terminal is the orchestrator's. That is judgement, and the relay carries
  none. It also puts the tool's listing surface inside a bounded agent prompt, which is
  the "sub-agent that acts" ADR 0018 and ADR 0022 both rejected.
- **A file that holds the current handle** (rejected) —
  [ADR 0021](0021-phase-is-a-second-label-family.md) rejected a worktree file as a store,
  and [ADR 0023](0023-the-stall-count-is-a-tracker-comment.md) repeated the rejection. A
  file is a second record of a fact the tool already holds, and it is wrong exactly when a
  session died without writing it. An argument resolved at spawn holds no such promise to
  keep.
- **Wake by comment only, and poll the work item** (rejected) — a session that polls is
  the blocking watch again, in a slower form. ADR 0022 retired the loop because a loop
  lives in a process.

## Consequences

- **The spawn resolves one more value, and the seam gains nothing.**
  `scripts/worker_state.py` never learns what a handle is. The target rides in the relay
  prompt, so the predicate and its exit-code contract are unchanged.
- **The spawn report gains one line: which wake mode is live.** Handle, title or comment.
  So a degraded wake is reported at the moment it is chosen, which is the only moment a
  human can act on it cheaply.
- **A handle that outlives its terminal wakes nothing, and that is the accepted risk.**
  The maintainer can close the orchestrator terminal and open a new one. The handle from
  the spawn then points at a terminal that is gone. Fallback two catches that where the
  new terminal carries the title, and fallback three catches the rest. So a stale handle
  costs one wake delivered late, and it destroys nothing. A re-resolution mechanism costs
  a state to keep fresh, for a failure that already has two catches.
- **A tool that issues no handle loses nothing it has today.** It falls to the title, and
  the report says so.
- **This ADR declares the target and wires nothing.** The resolution step in
  [`orchestrator/SKILL.md`](../../SKILL.md)'s *Start the tick*, the wording of step 5a in
  `orchestrator-setup/SKILL.md`, and operation 11's example in
  `references/tools/orca.md` are separate work. Until they land, a wake is found by title
  exactly as it is today.
