# The orchestrator merges and closes when the maintainer asks it to

The **Close transaction** ([`orchestrator/CONTEXT.md`](../../CONTEXT.md)) makes the
orchestrator session the actor for all eight of its steps. The session resolves the
conflicts against the default branch, pushes the mergeable branch, merges the PR, and
then runs the seam. No worker is prompted for any of it, and
[ADR 0015](0015-close-is-a-deterministic-transaction.md) records why: a worker that
runs the seam removes the worktree it runs inside.

That actor choice contradicts three sentences this skill already ships. This ADR
narrows all three. A future reader who finds the surviving sentences and no ADR
reverts the change.

## The three sentences

1. **"Never do implementation work here — spawn a worker and prompt it"** —
   [`orchestrator/SKILL.md`](../../SKILL.md), the opening paragraph. Resolving a merge
   conflict edits source files, so step 1 of the transaction is implementation work in
   the orchestrator session.
2. **"Merging is a human step"** — `orchestrator/SKILL.md`, in the close section,
   beside the rule that an item never advances to done before its PR is merged.
3. **"merge stays a human step"** — the **Review round** entry of
   `orchestrator/CONTEXT.md`, at the end of the sentence that hands a reviewed item to
   the human.

Each narrows to the same shape: **the human still decides, and the session can now
carry out the decision it was given.**

## Why it narrows rather than breaks

The rule protects against one specific case, and that case is not this one. A
**Worker** runs in **Yolo mode**, unattended, with no human to approve a tool prompt.
The human-merge rule stops such a worker from landing code on the default branch with
nobody watching. It is a rule about **absence**.

A session acting on an explicit "merge and close" from the maintainer in the room is
the opposite situation. The maintainer read the PR, made the decision, and stated it.
A second request to confirm that same merge is friction, and it is not safety. So the
decision stays the human's, and this ADR moves only the hands.

The same reasoning narrows sentence 1. **[ADR 0014](0014-route-verbs-to-skills-in-two-lanes.md)
already reads that law as "the orchestrator never writes source" in the general
case**, and holds it with the two-lane split. This ADR carves one bounded exception out
of it. The exception is a conflict resolution, inside the item's own worktree, on a
branch that already has a PR. It needs an instruction the maintainer gave in this turn.
It writes no source in the main checkout, and it opens no new work. It finishes work a
worker already did. Every other verb that writes source still takes the `worker` lane.

**The maintainer's words are the gate.** "task done, merge and close", "close 20" and
"wrap up 20" authorise the transaction, teardown included. "flip 20 to review" and
"advance 20" do not. Anything ambiguous, or unsaid, means ask before doing.

## The risk accepted, and the mitigation that carries it

**An orchestrator session can now write to the default branch.** So a wrong reading of
an ambiguous instruction is a wrong merge, and it lands on the branch the whole repo
builds on. That is a real loss of a property the old rule gave for free, and this ADR
does not pretend otherwise.

**The mitigation is that an ambiguous instruction means ask first.** The
authorisation is one explicit sentence from the maintainer, and the session asks
whenever it does not have one. That is the single mechanism this risk rests on, which
is why the ambiguous case resolves to a question rather than to a best guess.

Two gates in the seam limit the damage that a wrong reading can do. The transaction
refuses to close an unmerged PR, and it refuses to tear down a dirty worktree. So an
exit code stops the two unrecoverable outcomes, rather than prose. Neither gate stops a
merge the maintainer did not ask for. A revert recovers a wrong merge, which is why
this risk is accepted rather than closed.

## Considered Options

- **Narrow the three sentences, and record the narrowing here** (chosen) — the rule
  keeps its protection where it was written for, and the close flow gets an actor
  that can complete it. Per [`CLAUDE.md`](../../../CLAUDE.md), a decision that
  narrows an earlier one gets a new ADR, not a silent edit to the old one.
- **Delete the human-merge rule** (rejected) — it protects the unattended-worker case,
  which is unchanged and still the common case. A rule with a live purpose does not go
  away because one exception was found.
- **Keep the rule whole and have the maintainer merge by hand** (rejected) — the state
  before this decision, and the friction it removes. The maintainer already read the
  PR and already said to merge it. A second act by hand adds a step and no judgement.
- **Ask for a second confirmation before every merge** (rejected) — a confirmation of
  a decision the maintainer stated in the same turn. The dirty-tree gate is what
  actually protects the data-loss case, and it is a refusal rather than a prompt.
- **Auto-merge when the checks are green** (rejected) — that removes the human
  decision, rather than narrowing who carries it out. Removing the decision is the one
  thing the rule exists to prevent.
- **Let the maintainer authorise a whole session** (rejected) — a standing
  authorisation is the absence the rule was written against. Each transaction needs
  its own sentence.

## Consequences

- **The three sentences are amended, not deleted.** Each keeps the part that
  survives: the human decides. The **Review round** entry of `CONTEXT.md` is amended
  in the same commit range as this ADR. The two sentences in `SKILL.md` are amended
  with the close section itself, which is separate work.
- **The teardown-confirmation line narrows with them.** An explicit "merge and close"
  is the confirmation. `SKILL.md`'s **Safety** section keeps the dirty-tree case,
  which becomes a refusal in the seam.
- **The exception is bounded and stated in one place.** It covers the close
  transaction only. It is not a licence for the orchestrator to fix a bug, apply a
  review finding, or write any source outside a conflict resolution during a close.
- **ADR 0003 keeps its own text.** Its "merge is always a human step" sentence
  describes the review loop it decides, where no maintainer instruction to merge
  exists yet. It reads correctly inside its own scope, and this ADR is where a reader
  learns the bound.
- **This ADR records the decision and wires nothing.** The sentence edits in
  `SKILL.md` are separate work.
