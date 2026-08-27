# A hook refuses, and a seam performs

Every rule in this repo is advice. A skill body states it, a checklist repeats it, and
a review note claims it was kept. So a rule holds where a model remembers it, and it
is skipped where the model does not. That is the defect behind the original report:
the orchestrator did not move the work state, and it did not review at the right
moment.

No layer of the stack said no. A **Seam** performs a step and reports an exit code, but
it runs only where a session invokes it. Nothing sat between a session and the command
it was about to run.

The plugin manifest gains one key, `"hooks": "./hooks/hooks.json"`, so a third plane
installs with the skill and needs no step from the maintainer.

## The decision

**A hook answers, and a seam performs.** The boundary is hard, and each side has one
job:

| Plane | What it can do | What it must not do |
|---|---|---|
| the tracker | hold the state | nothing else holds it |
| a seam | change the state, and report an exit code | decide when it runs |
| a hook | answer yes or no, or inject a fact | mutate the tracker, merge, or spawn |

A hook never writes a label, never merges a pull request and never starts a worker.
That is what keeps a hook fast, safe, and testable through one JSON payload. The three
hooks, their events and the failure each one kills are in
[`orchestrator/references/hooks.md`](../../references/hooks.md).

**`record.py` is the one named exception, and the reason is stated rather than
hidden: a record a model writes is a record a model can fake.** That hook appends one
line to `.orchestrator/gates-<item>.jsonl`. It is not a mutation of the tracker, and
it is not a decision. It is an append-only note of what a command already did, in the
format [`orchestrator/references/quality-gates.md`](../../references/quality-gates.md)
already holds. No other hook writes a file, and a second exception needs an ADR of its
own.

**Every hook exits fast where it does not apply.** A hook fires in every session on
the machine once the plugin is installed. So the first check is the repo marker:
`docs/agents/orchestrator.md`, or an `.orchestrator/` directory. With no marker a hook
prints nothing, writes nothing and exits 0.

**A hook fails open.** `refuse.py` permits a command it cannot parse, and it denies
nothing where the label vocabulary cannot be read. A hook that guesses stops correct
work, which costs more than the rule it was protecting.

## What this supersedes

**It supersedes [ADR 0034](0034-the-seam-invocation-carries-a-resolved-plugin-root.md)
on one question: who resolves the plugin root.** That ADR made the session resolve the
root itself, with a glob over two install shapes. The reason was that
`$CLAUDE_PLUGIN_ROOT` is unset in the shell a skill body opens. The harness does set it
for a hook. So `context.py` is handed the root and injects it, and the glob has one
fewer caller.

**The rest of ADR 0034 stands.** The invocation form is still
`python3 <plugin root>/scripts/<module>.py`, the module form is still banned, and
`scripts/test_seam_invocations.py` still enforces both. The variable reaches a hook and
not a skill body, which is the same scope the `_Avoid_` note on **Plugin root** in
[`orchestrator/CONTEXT.md`](../../CONTEXT.md) already carries. So no skill body names
the variable, and nothing about that entry changes.

**It supersedes no part of [ADR 0036](0036-a-gate-run-is-work-product.md).** A gate run
is still work product here, and no hook denies a push yet. The item that makes a gate
deterministic carries that supersession, and it needs a gate record no model wrote.

## Considered Options

- **A hook answers, a seam performs, with one named exception** (chosen) — the
  boundary is one sentence, so a reader places a new rule with no table. The law names
  its own exception. So a second exception cannot arrive quietly.
- **No hook plane, and prose keeps every rule** (rejected) — this is the state this ADR
  replaces. The report that opened this work is the evidence: a rule a model must
  remember is a rule that will be skipped.
- **Every hook can write** (rejected) — the plane then has no boundary. Two writers
  reach the tracker with no order between them. A hook also has no exit code a caller
  reads, so a failed write is invisible.
- **A seam writes the gate record** (rejected) — a seam is not present when a gate
  runs. The gate command is run by a worker, and the closest seam runs minutes later.
- **The worker keeps the record** (rejected) — that is the state that makes a green
  line prove a model said so, rather than prove a command exited zero.
- **A `PreToolUse` hook that blocks a gate command instead of recording it** (rejected)
  — the exit code does not exist before the command runs, so the hook has nothing to
  judge.
- **A `Stop` hook that reconciles the board** (rejected for now) — nothing writes the
  board on a stop, so it would reconcile a field no session moved. Add it where a real
  failure asks for it.
- **A merge guard** (rejected) — the maintainer merges, and a hook that guards a human
  act guards the wrong actor
  ([ADR 0016](0016-the-orchestrator-merges-when-asked.md)).

## Consequences

- **The rollback is one line: delete the `hooks` key from
  `.claude-plugin/plugin.json`.** Nothing in the loop was changed, so every flow keeps
  working with the plane off. That is why this plane can land before anything depends
  on it.
- **Accepted risk: the label denial narrows
  [ADR 0025](0025-the-session-writes-the-review-state.md).** That ADR has the
  orchestrator session write the review state, in one call with the removal of the
  `phase:review` label. `refuse.py` denies the work-state half of that call, because
  only a seam writes a work-state label. Until the tick applies the transition itself,
  the maintainer writes that label or turns the key off. The narrowing is deliberate,
  and it is the reason the rollback is one line.
- **Accepted risk: the exit code in a gate record line is derived.** The payload a
  `PostToolUse` hook receives carries no field for it. A completed command answers with
  an object, and a failed one answers with a string whose first line reads
  `Error: Exit code <N>`. Where neither shape yields a code, `record.py` writes no
  line. So a call the harness stopped leaves a gap, and the worker's own append still
  covers it. The item that removes that append is where this risk needs a second look.
- **Two writers reach the gate record, on purpose and for one item.** The worker's
  `scripts/checks.sh` appends its line and `record.py` appends another. Both lines
  carry the same four keys and the same `head_sha`. So a reader that takes the last
  line per command reads the same verdict either way.
- **A hook is stdlib-only Python with a suite of its own**, which is the bar the two
  seams already hold. A test drives a hook through the real payload and asserts the
  exit code and what the hook emitted. No test reaches for a helper inside a hook, so
  the suite holds the contract a running session holds.
- **`context.py` reads the tracker, so a session start can cost one `gh` call.** The
  read goes through the **Tracker adapter**
  ([ADR 0040](0040-the-tracker-is-one-adapter-behind-both-seams.md)), so the hook names
  no CLI. A failed read is a named gap in the injected block, and never a silent one.
- **No hook copies a vocabulary.** `refuse.py` and `context.py` read the work-state
  label family from `docs/agents/issue-tracker.md`, which owns it. A repo whose file
  names no family gets no denial and a named gap, rather than four guessed strings.
- **Accepted risk: a hook needs a session restart.** The manifest is read once, at
  start. So a fresh `hooks/hooks.json` reaches the session after the restart, and
  `/orchestrator-setup` names that restart where it reports the plane.
