# The story gate is advisory

Layers 1 to 4 each read one work item, inside one worker worktree. None of them reads what
a whole user story left behind. So ten green items can leave a shallow module, with an
interface as wide as its implementation, and every box is ticked.

A fifth layer reads that shape. It runs once per user story, on the close of the last
child, and it runs `/improve-codebase-architecture` in the main checkout. The layer model
is [`orchestrator/references/quality-gates.md`](../../references/quality-gates.md), and
the trigger is the story-gate section of
[`orchestrator/SKILL.md`](../../SKILL.md#the-layer-5-story-gate).

## The decision

**Layer 5 is a step, and never a Gate.** It emits candidate work items instead of an exit
code, so it fails no push and no merge. A **Gate** is one command with one exit code
([`orchestrator/CONTEXT.md`](../../CONTEXT.md)), and depth is a judgement. The skill ends
by asking which candidate to explore, which is a question and not a verdict.

**The threshold is 0 untriaged `Strong` candidates, and not 0 findings.** A codebase with
findings is the normal state, so a threshold of 0 findings is a wall no story clears. The
fault this layer closes is a finding that dies in a report. So the bar sits on the triage.
Each `Strong` candidate becomes a work item through `/to-tickets`. Each `Worth exploring`
one goes to the backlog with its card. Each `Speculative` one is dropped with a one-line
reason.

**The orchestrator session checks that threshold, in prose.** `scripts/close_item.py` owns
the judgement-free steps of a **Close transaction**
([ADR 0015](0015-close-is-a-deterministic-transaction.md)), and triage is judgement. So
that seam gains no code from this decision.

**The report format stays with the skill.** This repo names what to hand the skill and
what to do with each candidate strength. It restates no heading and no section of the
report the skill writes. A second copy of that shape drifts from the maintained one.

## One routing row, and no new dependency

`improve-codebase-architecture` ships inside `mattpocock-skills`, which
[`orchestrator/references/requirements.md`](../../references/requirements.md) already
declares **Always required**. So the note on
[`orchestrator/references/skill-routing.md`](../../references/skill-routing.md) still
holds: every routed skill ships in that plugin. This row needs **no** new dependency row,
and `requirements.md` is unchanged by this decision.

The row does one more thing. The skill carries `disable-model-invocation: true`, and step
0b of `orchestrator-setup` strips that line from every skill the routing table names
([ADR 0031](0031-setup-unblocks-the-routed-skills.md)). So the row is what makes the strip
reach it. Without the row the trigger is prose, because no model can enter the skill.

## Considered Options

- **An advisory step, with the threshold on the triage** (chosen) — the finding reaches
  the backlog as a work item, and no story waits on an opinion.
- **A hard gate on the candidate list** (rejected) — a story then stalls until a human
  rejects the last candidate. Depth is a judgement, so an exit code here encodes one
  reading of it. The skill emits no exit code, so a hard gate must invent one.
- **A threshold of 0 findings** (rejected) — every real codebase has findings, so the bar
  is unreachable. An unreachable bar is then ignored, and the layer goes back to prose.
- **File every candidate as a work item** (rejected) — three strengths and one answer
  buries the `Strong` one under the speculative ones. The three strengths exist so that a
  session can sort them.
- **Run the skill per work item, inside the worker worktree** (rejected) — a worker reads
  one item, which is what layers 1 to 4 already do. The whole point is the shape a story
  left, and the run costs minutes on every item.
- **Let `scripts/close_item.py` check the threshold** (rejected) — the seam refuses rather
  than warns, so it then blocks a close on a judgement call
  ([ADR 0015](0015-close-is-a-deterministic-transaction.md)).
- **No fifth layer** (rejected) — the state this ADR replaces. Nothing then reads a module
  that ten green items made shallow.

## Consequences

- **Enforcement is documentary, the same as the rest of this repo.** The trigger prose and
  the report to the user are the whole guard. No hook and no script runs this layer
  ([ADR 0032](0032-quality-gates-are-a-layered-contract.md)).
- **The work items are the record.** The skill writes its report outside the repo, so
  nothing of the run survives the session. A `Strong` candidate that reaches no ticket is
  lost, and that is why the threshold sits on the triage.
- **Accepted risk: the skill's own body invokes `/codebase-design`.** That skill carries no
  `disable-model-invocation: true` today. If upstream adds one, layer 5 degrades quietly,
  because step 0b strips only skills the routing table names
  ([ADR 0031](0031-setup-unblocks-the-routed-skills.md)). A `codebase-design` row needs a
  verb no maintainer types, so the risk is accepted and named here instead.
- **Accepted risk: nothing proves the triage happened.** The threshold is prose in a
  session, so a story can close with a `Strong` candidate unfiled. The mitigation is the
  report to the user, which names each candidate and where it went.
