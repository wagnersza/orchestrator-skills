# Skill dependencies track upstream, and `/skill-fork-sync` is removed

This repo installs each declared skill dependency from the upstream repo its
author maintains. There is no fork, no pin, and no evaluation gate. This ADR
supersedes [ADR 0007](0007-fork-and-pin-skill-dependencies.md) and
[ADR 0008](0008-diff-targeted-run-budget.md), and it deletes the skill those two
ADRs specified.

ADR 0007 gave the maintainer a version dial. Fork each upstream repo, hold the
fork's default branch at a known-good commit, and promote only after an
evaluation. The mechanism worked on paper, and the cost was the whole of
`/skill-fork-sync`: three modes, four reference files, a 1700-line seam
(`scripts/fork_state.py`), its test suite, and an eval set. **None of it ever
ran.** Bootstrap was a human step that nobody performed, so `~/.orchestrator/forks/`
stayed empty and no sync ever planned against a real fork. Nobody ran the eval set
that gates the judgement half either. The defence had a maintenance cost and no
record of a catch.

ADR 0011 already accepted one risk for `simple-english`, and that risk now applies
to every dependency: **an upstream change reaches the next session through no
evaluation gate.** The trade is deliberate. The dependency set is small, and each
upstream is a skill repo whose author publishes the change history. A worker that
behaves differently after an update is visible in the review note. A pin that
nobody turns holds a version nobody chose.

## Considered Options

- **Track upstream, remove the skill** (chosen) — the marketplace points at the
  author's repo, `claude plugin marketplace update` is the only version verb, and
  the repo carries no machinery for a gate it never used. It deletes about 3000
  lines and one Python seam.
- **Keep the fork machinery, change the account** — the smallest diff, and it keeps
  the maintenance cost of a mechanism that never ran. Rejected: the problem is the
  unused gate, not who owns the fork.
- **Keep the gate, drop the fork** — compare the installed `gitCommitSha` against
  upstream HEAD, evaluate the delta, then run `marketplace update`. It keeps the
  evaluation and loses the version dial, because an update is all-or-nothing and
  you can read the delta only after it lands. Discipline is not a pin, and the
  evaluation half is the part that nobody ever ran.

## Consequences

- **Upstream changes arrive on the next `claude plugin marketplace update`.** No
  approval step gates them. A dependency that breaks the completion contract
  appears as a worker that behaves differently, which is the failure ADR 0007
  describes.
- **These files are gone:** `skill-fork-sync/`, `scripts/fork_state.py`,
  `scripts/test_fork_state.py`, and `evals/`. Eight glossary terms leave
  `orchestrator/CONTEXT.md` with them: Fork, Upstream, Pinned SHA, Sync candidate,
  Consumed skill, Sync plan, Promote, and Run budget.
- **The repo is still not markdown-only.** Two seams stay: `scripts/close_item.py`
  (ADR 0015) and `scripts/worker_state.py` (ADR 0018). The `evidence` bar in
  `docs/agents/orchestrator.md` keeps its rule that a touched Python file needs a
  green test run.
- **ADR 0007, 0008 and 0011 keep their own text.** Each one records a decision that
  was true when the maintainer made it, and this ADR reverses all three in one
  place. This ADR also removes their links to the deleted files, because a dangling
  cross-reference is this repo's main failure mode. **Where any ADR names
  `/skill-fork-sync` or `scripts/fork_state.py` in prose, read it as history.**
  ADR 0015 compares its own seam to that one, and the comparison still explains the
  bar that a new seam must meet.
- **`prompt-improver` is unaffected.** It is already `wagnersza/prompt-improver`,
  which the maintainer owns outright. That is a repo, not a pin, and no promote step
  ever applied to it.
