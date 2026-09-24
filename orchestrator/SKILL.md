---
name: orchestrator
description: Orchestrate agent worker sessions across any workspace tool (orca/cmux/herdr), harness (claude/codex/pi/copilot/cursor), and frontier model. Pick the next ready work item, read whether it is a user story or a leaf task, spawn a worker in its own worktree on the right model and effort for the job, prompt/monitor it via a file-based checklist, run cross-vendor adversarial review on demand, then report finished work for the maintainer to merge. Use this skill for every work-item action, and never wait for the user to type /orchestrator. A work verb plus a work-item number N is enough, with or without a "#". Trigger on "work on N", "work on #N", "implement N", "build N", "start N", "do N", "implement X", "spawn a worker", "start a session for X", "prompt worker Y", "what next", "what should I run/work on", "what's ready", "what are the workers doing", "list workers", "review N adversarially", "merge and close N", "merge N and close it", "close N", "close task #N", "it's done", "wrap up N", "orchestrate". A bare number after a work verb always means a tracked work item, so route it here rather than reading it as a file or a line number.
---

# Orchestrator

This session is the **orchestrator**. It coordinates **worker** sessions. A worker is
a `(Tool, Harness, Model)` triple running against one work item in its own
worktree/terminal. The vocabulary is defined in [`CONTEXT.md`](CONTEXT.md).

```
one work item  ->  one worktree (branch + checkout + terminal)  ->  one worker (tool, harness, model)
```

**Never do implementation work here — spawn a worker and prompt it. There is no
exception.** The maintainer merges on the tracker
([`docs/adr/0057-the-merge-is-the-second-act.md`](docs/adr/0057-the-merge-is-the-second-act.md)).

## Where a request goes

| Request | Where it goes |
|---|---|
| a queue question ("what next", "what's ready") | ["What next?"](#what-next--pick-the-next-work) |
| a work verb + item number, item carries `user-story` | batch-spawn its unblocked children — [Spawn a worker](#spawn-a-worker) |
| a work verb + item number, no `user-story` | one worker, one worktree — [Spawn a worker](#spawn-a-worker) |
| an item-writing verb (ticket, spec, triage) | [`references/skill-routing.md`](references/skill-routing.md), lane `inline` |
| a code-writing verb (implement, debug, TDD, review-diff, prototype) | [`references/skill-routing.md`](references/skill-routing.md), lane `worker`, spliced into the spawn prompt |
| a review, close or merge-train ask | [Adversarial review](#adversarial-review-is-a-verb) below. Close and the train are questions, answered in [`references/reporting.md`](references/reporting.md) |

## "What next?" — pick the next work

Resolve the **ready queue** fresh — states change live, never cache. Read the item's
kind first: a `user-story` card in the start column authorises its whole run with no
label; a leaf needs `ready-for-agent` and, unless a live story already owns it, its own
card in the start column too. The **Ready queue** and **Board status** entries in
[`CONTEXT.md`](CONTEXT.md) hold the full gate. A schedule named `orchestrator-queue`
already asks this every minute and starts at most one item —
`python3 <plugin root>/scripts/worker_queue.py queue --help` holds the roofs and the
descent, and `python3 <plugin root>/scripts/worker_queue.py start --help` answers the
gate for one item. Report per
[`references/reporting.md`](references/reporting.md): every ready item first, then
enough blocked ones to reach 5, then every item at `to-review` beside them.

## Board status

The board mirrors the work, and a seam writes the card at three moments: the spawn claim
writes `In progress`, the tick that writes `to-review` writes `In review`, and the close
writes `Done` after the teardown. **Write no card yourself** — each write rides in the seam
that owns that moment, and a failed write is reported and stops nothing. `Backlog`, `Ready`
and the start column stay the maintainer's lanes, so the drag is still what authorises a
start. The rule is the **Board status** entry in [`CONTEXT.md`](CONTEXT.md), and the
rationale is [ADR 0067](docs/adr/0067-the-board-is-a-mirror-at-three-moments.md).

## Spawn a worker

One item with no `user-story` label is one worker in one worktree. A `user-story`
parent batch-spawns every unblocked child at once, each classified separately — a
batch that mixes a bug and a feature splices a different skill into each prompt, and
one blanket model for the whole batch is the same defect. **Never hardcode a model.**
Classify the item's role first — `heavy` on a named signal, `light` where all three
light conditions hold, `medium` otherwise — then resolve `(model, effort)` from
[`references/models.md`](references/models.md). `scripts/spawn_item.py` runs the rest
in its own seven ordered steps (worktree, terminal, rendered prompt, readiness gate,
the `in-progress` label, the panel, the item schedule); read its `--help` and its
module docstring, and never restate that order here. Preflight the routed skill and the
plugin dependencies before the first spawn of a session
([`references/requirements.md`](references/requirements.md)). Report four fields per
child, in order: the routed skill, the role, the model, the effort.

## Adversarial review is a verb

`review N` spawns a reviewer on the item's branch — a cross-vendor `(model, effort)`
pair from `models.review` — and the reviewer posts one comment on the work item.
There is no round, no fix loop and no counter: a judgement has no exit code, so
nothing parses the comment and nothing re-prompts the impl worker with it. The spawn
steps, the vendor assert and the four prompt substitutions a review draft needs are in
[`references/models.md`](references/models.md#running-an-adversarial-review). Run it
whenever the maintainer asks, at any point in the item's life.

## Resolve the verb before you act

A verb the table above does not name can still match a row in
[`references/skill-routing.md`](references/skill-routing.md) — read it at the moment
you need it, never from memory, and never copy a row into this body. Lane `inline`
runs the skill here, in the main checkout. **An inline item-writing flow writes
`ready-for-agent` on each item it files**, beside the `## Touches` block and the parent edge
— so do not add the label afterwards, and add none to a `user-story` parent. **The drag into
the start column stays the maintainer's act**, so a filed leaf waits in `Backlog`, and a
child of a story they already dragged is startable at once
([`docs/adr/0068-an-item-writing-flow-writes-the-start-label.md`](docs/adr/0068-an-item-writing-flow-writes-the-start-label.md)).
Lane `worker` splices the skill into the spawn
prompt instead. A verb that matches no row costs one line: name the closest row and
ask whether to route there, then answer freehand on a decline. A queue question and a
flow this skill owns directly are not verbs, and never reach this question.

## Monitor workers

- **Topology / handles:** map slug → worktree → handle through the tool's own list
  operations.
- **Exact progress:** read `.orchestrator/checklist-<item>.md` — which boxes are
  ticked.
- **Busy vs idle:** trust the checklist plus idle state over scraping a TUI's sparse
  read-tail.
- **Stall detection:** unchecked boxes and an idle terminal mean the worker stopped
  early. Reset its context, then re-prompt with the remaining steps. **One re-prompt,
  and then a human** — a stalled worker keeps its Role, and the tick applies both
  swaps itself ([`references/reporting.md`](references/reporting.md)).

## Safety

- The maintainer's own merge authorises the teardown that follows it, and no session
  asks a second time. A dirty worktree refuses rather than warns.
- Confirm before any teardown this session runs by hand — it kills a live worker
  terminal and can drop uncommitted work.
- A second stall goes to `needs-human`, written by the tick itself, and no teardown
  runs on it. A `dead` worker still asks, because a tick cannot read intent in an
  uncommitted diff.
- Keep the main checkout (config's `repo`) on the default branch — all tracker and
  git-state ops run there.
- Never advance an item to done before its PR/MR is actually merged.
