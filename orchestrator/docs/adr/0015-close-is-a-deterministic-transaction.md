# Closing an item is a deterministic transaction, and code owns its order

Closing a work item is where this skill loses the maintainer's confidence. An item
reaches review, the maintainer says "task done, you can merge and close", and eight
things must then happen in a fixed order. Sometimes one of them does not happen, or
happens in the wrong order. The label says done and the PR is not merged. The item
closes and the local default branch never received the merge. Teardown removes a
worktree whose tree nobody checked.

The rules were not missing. The close section of
[`orchestrator/SKILL.md`](../../SKILL.md) already states each one, and states it
correctly:

- Pull the merge into the local default branch **first**, then flip to done.
- Never write `Done` for an unmerged PR.
- Make sure that the worktree is clean before you remove it.

The order still drifted.

That is the finding this ADR records. **Ordering is what code holds perfectly and
prose holds poorly.** A prose contract is an instruction to a model, and a model drops
one line out of eight with no error. A rule that is correct, written down, and still
skipped is an enforcement problem and not a wording problem. Apply that test to the
next prose contract in this repo that starts to fail.

The flow is now one **Close transaction**, defined in
[`orchestrator/CONTEXT.md`](../../CONTEXT.md). It splits by what each step needs.
Steps 1 to 3 need judgement, so they stay prose and they invoke the
`resolving-merge-conflicts` skill. Steps 4 to 8 need no judgement at all — they are
predicates and an order — so they move into one seam, which owns the order. The seam
is `scripts/close_item.py`. This ADR names it before it exists: the decision lands
here, and the file lands with the flow change that consumes it.

## The four decisions this records

**The ordering lives in code.** Steps 4 to 8 hold three predicates, a pull, two
tracker writes and a passed-in command. No step contains a decision. A model that
reads them in prose can still run them in the wrong order, and a script cannot. This
is the smallest change that removes the failure: the order becomes a property of the
seam rather than a sentence a reader must obey.

**Teardown sits inside the seam, not beside it.** A teardown outside the seam was the
more conservative option, and it loses the property the change is for: one entry point
means one order. A separate teardown command can run before the gates that protect it.
The argument against a teardown inside the seam was tool coupling, and the mechanism
removes that argument. The teardown command arrives as a string argument,
which the orchestrator reads from `references/tools/<tool>.md` and passes in. So the
seam never learns what orca is, and a new tool stays a Markdown change. The safety
lost by moving teardown in is bought back by two explicit flags and by the
dirty-tree gate.

**The seam refuses, and it does not warn.** Prose can say "refuse if the tree is
dirty", and only an exit code can refuse. A warning appears in output the reader can
miss, and the destructive step then runs anyway. So an unmerged PR and a dirty worktree
each stop the transaction with a distinct non-zero exit code, and the orchestrator
reports the cause without parsing prose. A refused close leaves the item at the review
state, with its card at `In review`. So a partial close never puts the board in a state
no label produced ([ADR 0009](0009-labels-drive-board-status.md)).

**The default mutates nothing.** A bare invocation resolves every precondition and
emits a JSON plan with each step marked. Teardown needs `--execute` and `--teardown`
together, so no single flag is destructive. This is also what makes refuse-not-warn
testable: every refusal is asserted against a fixture with zero side effects. It is
the posture `scripts/fork_state.py` already takes, and it recovers the property that
made this repo's first seam cheap to test.

## Harness hooks were considered and rejected for this path

A hook is the obvious mechanism for "stop a step that must not run", and it is the
wrong one here. **A hook gates a Worker, and every failing step in this transaction
belongs to the Orchestrator.** The session that merges and closes is the one the
maintainer is talking to. A `PreToolUse` hook in a worker session sees none of it.
Hook coverage is also uneven across the harnesses this skill supports. The portable
event set is `PreToolUse`, `Stop` and `UserPromptSubmit`, and `pi` has no hook system
at all. So a hook-based gate holds on some harnesses and not on others, for a step
that has nothing to do with the harness.

**A worker-side `Stop` hook is still a live idea, for a different contract.** Such a
hook blocks a worker's turn while a **Checklist** box is unchecked. That is a real
opportunity, and it gates the right actor. It needs its own item and its own ADR.
This ADR closes the hook option for the close path with a reason. A later reader
therefore finds the reason, rather than an open question to re-litigate.

## Considered Options

- **Split by judgement: prose for steps 1 to 3, one seam for steps 4 to 8**
  (chosen) — each half gets the mechanism that fits it. The half that needs a
  decision keeps a reader who can make one, and the half that needs an order gets an
  owner that cannot forget it.
- **Keep all eight steps in prose and write the ordering more firmly** (rejected) —
  the state before this ADR, and the defect. The rules are already explicit and
  already correct. More words on a rule a model can drop buys nothing.
- **Move all eight steps into the seam** (rejected) — step 1 is a decision about what
  a merged file means. No script makes that decision, and a script that pretends to
  resolves a conflict by picking a side.
- **The orchestrator session is the actor** (chosen) — the maintainer is present and
  the session already holds the context of the review. The item's worktree also still
  exists, because teardown has not run.
- **Prompt the already-running worker to close its own item** (rejected) — the worker
  can be idle or out of context when the maintainer says "merge and close". Then the
  orchestrator rebuilds the context it already holds. The worker's worktree is also
  about to be removed.
- **Let a worker run the seam** (rejected) — the seam's last act removes the worktree
  the worker runs inside. The worker kills its own terminal in the middle of the
  command, and no exit code comes back.
- **A harness hook as the gate** (rejected) — see the section above.
- **Extend `scripts/fork_state.py` instead of adding a second seam** (rejected) —
  that script mutates nothing by construction, which is the property its tests rely
  on. This flow mutates. A second seam of the same shape keeps both testable.

## This ADR restates no rule of `resolving-merge-conflicts`

Steps 1 to 3 name the skill and say when to enter it. How to read the conflicting
hunks, what to preserve, and which checks to run afterwards belong to that skill.
This repo copies none of it. That is [ADR 0006](0006-delegate-prompting-to-prompt-improver.md)
and [ADR 0011](0011-delegate-technical-writing-to-simple-english.md) applied a third
time, for the same reason: a copied rule set drifts from the upstream that maintains
it. The skill therefore joins the always-required table in
[`orchestrator/references/requirements.md`](../../references/requirements.md), so a
close never begins against a missing dependency.

## Consequences

- **The seam count grows by one, and stops there.** This repo gets a Python surface
  per enforcement need, not per feature. `scripts/close_item.py` is the second seam,
  and the bar it meets is `fork_state.py`'s: stdlib only, plan mode by default,
  tested as a subprocess against its emitted JSON.
- **The seam knows nothing about the tool, the board, or any tracker but GitHub.**
  The teardown command, the board coordinates and the item id all arrive as
  arguments. `gh` is hardcoded with its ceiling named in a comment.
- **A partially applied close is resumable.** Both tracker writes are idempotent, so
  re-running after a refusal finishes the transaction instead of failing.
- **This ADR declares the transaction and wires nothing.** The vocabulary lands with
  it. The seam, its tests, and the rewritten close section of `SKILL.md` are separate
  work, and until they land the close flow behaves exactly as it does today.
