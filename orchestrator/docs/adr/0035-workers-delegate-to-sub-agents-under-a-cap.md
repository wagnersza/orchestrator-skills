# Workers delegate to sub-agents, under a cap of 5 at once

A **Worker** gets one worktree, one harness and one context window, and it does every part
of a **Work item** in that one context. The spawn prompt says so on purpose.
[`orchestrator/SKILL.md`](../../SKILL.md) holds the line, in the *Three things
`prompt-improver` can't know* list:

> - **Cap delegation.** A worker already inside a worktree shouldn't fan out;
>   `prompt-improver`'s subagent cap is the wording to use.

That line costs more than it saves. A heavy item reads six reference files, greps the
repo, runs the suites and writes prose, all in one context. The reads take the space that
the work needs. The worker then loses the early part of the spec, or it asks the
orchestrator for a re-prompt. A re-prompt costs the maintainer one more round trip.

A sub-agent is the cheap answer, and a `claude` worker already has one. A read-only search
agent spends its own context on the reads and returns the file and the line. The worker
keeps its context for the spec and the edit. None of that needs a second worktree, a
second branch or a second work item.

## The decision

A worker **delegates to sub-agents when the work splits**, and **at most 5 sub-agents run
at once inside one worktree**.

The cap counts **concurrent** sub-agents, and it applies **per worktree**. So it is not a
total. A worker can run 5, collect their reports, and then run 5 more. And five
batch-spawned siblings are five worktrees, so each sibling gets its own 5.

Two bounds hold with the number, because each one changes what a worker can do:

1. **The harness must have a sub-agent surface.** `claude` has one. A harness with none
   reads the same instruction, delegates nothing, and satisfies it. So the instruction
   never asks for a tool the worker does not have.
2. **A sub-agent reads, searches and reports. It never writes the item's source.** The
   worker owns every edit, every **Commit slice** and every **Gate**, because those three
   are the worker's contract and a sub-agent has no branch.

The vocabulary lands with this ADR, in [`orchestrator/CONTEXT.md`](../../CONTEXT.md):
**Delegation cap**.

## A number replaces a prohibition, and unbounded fan-out stays rejected

The old line is right about one thing. Twenty sub-agents in one worktree read the same
files twenty times, and no human can interrupt work at that width. So this ADR **narrows**
the line, and it does not delete it.

A prohibition cannot say how much. It gives one answer to the worker that needs a single
search and to the worker that wants twenty. So one worker asks the orchestrator whether
fan-out is allowed, and that question is the round trip this ADR removes. Another worker
delegates with no number and hopes. A number answers both workers in one sentence, and a
worker reads that sentence without a question. The number is 5, and fan-out with no
ceiling is still refused.

## The number is not a config field

A threshold in config is the **Gate** pattern
([`references/quality-gates.md`](../../references/quality-gates.md),
[ADR 0032](0032-quality-gates-are-a-layered-contract.md)). A coverage bar earns that
place, because a coverage bar is a property of the target repo. The maintainer of that
repo sets it, and setup writes the number into the tool that reads it.

**A delegation cap is a property of a harness context window, and not of a target repo.**
The same 5 is correct in every project the same harness runs in. A per-project field then
holds the same value in every project. So the number ships in the vocabulary and the
reference layer, and config gets no block for it. This is the one case that deliberately
does not copy the Gate threshold pattern. If a real project needs a different number, that
is what reopens this decision.

## Considered Options

- **Delegate by default, capped at 5 concurrent per worktree** (chosen) — the reads leave
  the worker's context, and the ceiling stays low enough for a human to interrupt the
  work. One number covers both the worker that needs one search and the worker that wants
  twenty.
- **Leave the prohibition** (rejected) — the state this ADR replaces. It keeps the
  worktree bounded, and the cost is a lost spec and one more re-prompt. It also refuses a
  tool the worker already holds.
- **Put the cap in config** (rejected) — a cap is a property of a harness context window,
  so every project carries the same number. A field for it also invites a per-project
  answer to a question no project asks.
- **Delegate with no cap** (rejected) — twenty sub-agents read the same files twenty
  times, and no human can interrupt work at that width. The old line named this risk
  correctly, and this ADR keeps it rejected.
- **Let a sub-agent write the item's source** (rejected) — the commit slice, the gates and
  the checklist are the worker's contract, and a sub-agent has no branch to hold them. Two
  writers on one worktree also mean two authors for one commit.
- **Count the cap as a total per item, and not as a concurrency** (rejected) — a total
  makes a worker ration searches near the end of an item, which is where a search is worth
  most. The risk is about concurrency.
- **Drop the reviewer's carve-out for one rule everywhere** (rejected) — the reviewer is
  the second opinion, so a sub-agent's finding inside a review arrives unattributed and
  costs a **Review round**. One rule for both jobs has to be the weaker one.

## Consequences

- **The adversarial reviewer of [ADR 0003](0003-cross-vendor-adversarial-review.md) keeps
  its no-sub-agent rule.** The review prompt's `Do not spawn sub-agents` bullet in
  [`orchestrator/SKILL.md`](../../SKILL.md) stands, unchanged. It is the one exception to
  the cap, and nothing in ADR 0003 changes.
- **Accepted risk: enforcement is documentary.** The term, this ADR and the spawn prompt
  are the whole guard. Nothing counts the sub-agents a worker runs, so a worker can run
  ten and no check fails. That is the posture of the **Browser surface** rule as well
  ([ADR 0012](0012-playwright-cli-is-the-only-browser-surface.md)) and of the **Commit
  slice** rule ([ADR 0013](0013-workers-commit-in-contextualised-slices.md)).
- **The wording of the prompt stays `prompt-improver`'s.** This ADR says what a spawn
  prompt must carry, and never how it reads
  ([ADR 0006](0006-delegate-prompting-to-prompt-improver.md)).
- **No flow changes with this ADR.** The `Cap delegation` bullet and the harness lines
  that consume the term are the next work item of the same story. So this ADR and the
  vocabulary land first, and the prompt reads them after.
