<!--
Shared rules for composing a worker prompt. Read this FIRST, then the
per-model guide named in ../models.md. Distilled from the wsza/prompt-improver
skill and the vendored opus-5 / sonnet-5 guides.
-->

# Composing a worker prompt

A worker prompt is an **agentic-pipeline prompt**, not an open research question:
it must be deterministic, complete, and finishable unattended. So the
senior-partner / open-synthesis framing does **not** apply — keep the tight task
framing and the checklist. What *does* apply is everything below.

## Front-load the whole spec

One turn. Task, intent, constraints, acceptance criteria, the checklist, the
recipe, the evidence bar — all in the first message. A spec dribbled out over
later turns costs tokens and sometimes quality on every model here, and a worker
runs with no human to answer follow-ups. If something is genuinely unknown, say
what assumption to take rather than leaving a hole.

## Flashlight: center + edges

- **Center** — what this item is for, in one line: the outcome, not the steps.
- **Edges** — what is explicitly out of scope. Name the neighbouring files,
  features, or refactors the worker must *not* touch. Both models widen scope on
  their own judgment when the boundary is unstated.

## Name the artifacts

Point at concrete things: the work-item id, the files/dirs to change, the
acceptance criteria, the run recipe and its ports, the migration dir, the tracker
command for the review note. Vague pointers ("the API", "our tests") make the
model pick one source and dive.

## Positive examples, not prohibitions

Show the shape you want. Every "don't be verbose / don't skip the MR / don't over-
engineer" is weaker than one line of the wanted shape. Exception: the scope
**edges** above — those are legitimately negative and belong in the prompt.

## State scope explicitly, per item

Neither model generalizes an instruction from one item to a sibling, and Sonnet-
class models are strictly literal at lower effort. Write "apply this to every
route, not just the first" — not "apply this to the routes".

## Drop stale scaffolding

Delete from any prompt template:

- **Verification steps** — "add a final verification step", "use a subagent to verify", "double-check before responding". These models verify themselves; the instruction causes over-verification, more tokens, no quality gain. The checklist's evidence step is the contract, not a re-check instruction.
- **Forced status cadence** — "summarize progress every 3 tool calls". Both narrate well unprompted. If the cadence is wrong, describe the shape instead: *"Before your first tool call, say in one sentence what you're about to do. While working, update only on something important or a change of direction. When you finish, lead with the outcome."*
- **Negative style rules** — rewrite as a positive example (above).
- **Thinking-off / "don't reason" rules** — never; they increase tag leakage.

## Cap delegation

A worker inside a worktree shouldn't fan out. If the harness has subagents:

```text
Delegate to a subagent only for a large, genuinely independent, parallelizable
track such as a wide multi-file investigation. Do not delegate work you can
finish in a handful of tool calls, and do not use subagents to verify your own
work. Keep spawn counts low.
```

## Calibrate written length

The review note, the PR/MR description, and any doc the worker writes run long by
default:

```text
Match the length of written documents to what the task needs: cover the
substance, but do not pad with filler sections, redundant summaries, or
boilerplate.
```

## Review prompts: coverage first, filter later

For the adversarial reviewer, **never** write "only report high-severity issues",
"be conservative", or "don't nitpick" — every model here now follows that
literally and silently drops real bugs. Ask for coverage:

```text
Report every issue you find, including ones you are uncertain about or consider
low-severity. Do not filter for importance or confidence at this stage - a
separate verification step will do that. Your goal here is coverage: it is
better to surface a finding that later gets filtered out than to silently drop a
real bug. For each finding, include your confidence level and an estimated
severity so a downstream filter can rank them.
```

The orchestrator (or the impl worker) does the ranking when it reads the verdict.
If a single-pass filter is genuinely wanted, set a **concrete** bar instead of a
qualitative one: *"report any bug that could cause incorrect behavior, a test
failure, or a misleading result; omit pure style or naming nits."*

## Effort is a dial, not prose

Pick the role's effort from [`../models.md`](../models.md) and pass it via the
harness flag. Don't simulate effort in prose ("think really hard"), and don't
carry a previous model's default over.

## Before sending — check

- Whole spec in one turn; no "I'll tell you the rest later".
- Center stated; edges stated.
- Every artifact named concretely (item, files, recipe, ports, tracker command).
- No verification step, no forced status cadence, no thinking-off rule.
- Scope stated per item, not generalized.
- Effort chosen for the role and legal on this harness.
