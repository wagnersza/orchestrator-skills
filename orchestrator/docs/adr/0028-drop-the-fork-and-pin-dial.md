# Drop the fork-and-pin dial, and take upstream drift as it comes

[ADR 0007](0007-fork-and-pin-skill-dependencies.md) made every declared skill
dependency a fork this repo owns, and pinned the fork's default branch.
[ADR 0008](0008-diff-targeted-run-budget.md) capped what one sync can spend, and aimed
that budget with the diff. The mechanism worked as designed.

**It never paid for itself.** The dial turned zero times: no promote ran, and it caught
no upstream regression. What it cost is standing, not occasional. The cost is one skill
body plus three mode references, one 1700-line Python seam, and a 32-case test suite.
It is also one eval fixture, and eight glossary terms in
[`orchestrator/CONTEXT.md`](../../CONTEXT.md). Every other entry in that file has to
stay consistent with those eight terms. Every **Work item** in this repo pays that
consistency cost, and the dial never paid it back.

So the dial is removed, and not paused.

## What leaves

- `skill-fork-sync/`, which is `SKILL.md` and the three mode references.
- `scripts/fork_state.py`, the **Sync plan** seam, and `scripts/test_fork_state.py`.
- `evals/skill-fork-sync/sync-judgment.json`, and the `evals/` tree with it. That eval
  set had one member, and it was the dial's own self-eval.
- The `./skill-fork-sync` entry in `.claude-plugin/plugin.json`, the fork vocabulary
  section in `CONTEXT.md`, and every live reference in `README.md`, `CLAUDE.md`,
  `references/requirements.md` and `docs/agents/orchestrator.md`.

Nothing replaces it. `claude plugin update` and `claude plugin marketplace update` are
the version control again.

## This supersedes ADR 0007 and ADR 0008, and both keep their text

A decision that reverses an earlier one gets a new ADR, per
[`CLAUDE.md`](../../../CLAUDE.md). So ADR 0007 and ADR 0008 each get one
`> Superseded by ADR 0028` line at the top, and nothing else in either one changes.
Their bodies name paths this ADR deletes. That is history, and it stays.
[ADR 0011](0011-delegate-technical-writing-to-simple-english.md) and
[ADR 0015](0015-close-is-a-deterministic-transaction.md) mention the dial in passing,
and this change leaves both untouched for the same reason. An ADR records what was true
when it was written.

One finding in ADR 0007 is still correct, and still worth having on the record:
**`claude plugin marketplace add` accepts no `--ref`, `--branch` or `--tag`.** Anybody
who reaches for a pin again starts there.

## Considered Options

- **Delete the skill, the seam and the fixture** (chosen) — this repo pays the cost of
  the dial on every item, and the risk it covers lands rarely. No other option stops
  that payment. The mechanism finding survives in ADR 0007, so a later attempt does not
  start from nothing.
- **Keep the skill and stop invoking it** (rejected) — an unused skill still loads its
  description into every session, and every vocabulary edit still has to stay
  consistent with its eight terms. A dial nobody turns is worse than no dial, because
  it reads as a guarantee this repo does not have.
- **Keep the seam and delete the skill** (rejected) — `scripts/fork_state.py` computes
  a **Sync plan** for a sync that no longer exists. The test suite then passes and
  proves nothing, which is a rule with no home.
- **Keep the `evals/` tree for a later subject** (rejected) — git tracks no empty
  directory, so the tree cannot survive its one member. An eval set for a different
  subject is new work, and it picks its own home then.

## Consequences

- **A declared dependency now moves under this repo with no gate. That is the accepted
  risk.** ADR 0007 named this exact failure. An upstream rename of
  `docs/agents/issue-tracker.md`, or a rewrite of the `ponytail` ladder, changes worker
  behaviour here with no failing test anywhere. The discovery path is the one that
  existed before ADR 0007: a worker behaves differently, and somebody notices. This
  repo takes that risk deliberately.
- **An install still holds a SHA, so drift needs an act.** A plugin install sits at the
  commit it came from, and `claude plugin update` moves it. The fork bought two things
  over that. One is the freedom to hold one dependency back while another moves
  forward. The other is an eval gate before the move. Neither is worth the standing
  cost.
- **The Python bar survives, re-anchored.** Two seams remain, `scripts/close_item.py`
  and `scripts/worker_state.py`, and both have test suites. So "run the tests when you
  touch a Python file" is unchanged in `CLAUDE.md`, and the `evidence` bar in
  `docs/agents/orchestrator.md` keeps its Python clause.
- **Eight glossary terms leave `CONTEXT.md`**: **Fork**, **Upstream**, **Pinned SHA**,
  **Sync candidate**, **Consumed skill**, **Sync plan**, **Promote** and **Run budget**.
  Two live entries used **Pinned SHA** as an example of a term a writing pass keeps.
  Both now name a term that still exists.
- **The plugin ships three skills instead of four**, and `version` goes to `0.26.0`.
  Minor, because this story removes a contract.