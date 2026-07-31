---
name: skill-fork-sync
description: Fork, pin and sync the skill dependencies this repo declares — hold each upstream skill repo at a known-good SHA on your own fork, detect when upstream moves, evaluate only the changed skills this repo actually consumes inside a throwaway worktree, and fast-forward the fork only after you approve. Three modes — bootstrap (create the forks and pin them to the installed SHA), sync (detect a delta, plan and run the evals, recommend promote or hold), promote (fast-forward the fork and update the marketplace + plugin). Use when the user says "skill-fork-sync", "fork the skill dependencies", "bootstrap the forks", "sync the forks", "has upstream moved", "check for skill updates", "is mattpocock/ponytail ahead of my pin", "evaluate the upstream delta", "promote the candidate", or asks how their skill dependencies are pinned.
---

# skill-fork-sync

Every skill this repo declares as a dependency is installed from someone else's
default branch, and `claude plugin marketplace add` accepts no `--ref`,
`--branch` or `--tag` — a marketplace tracks the source's default-branch HEAD,
full stop. So an upstream push changes the skill bodies workers run against, and
this repo delegates **contracts** to those skills (the tracker config, the lazy
posture, all prompt composition), not merely coexists with them.

This skill supplies the missing pieces: **a version dial the maintainer owns**,
and **a way to test a candidate version before turning it**. The dial is a fork
in the maintainer's own account whose default branch sits at a known-good
upstream SHA — see
[ADR 0007](../orchestrator/docs/adr/0007-fork-and-pin-skill-dependencies.md).

The vocabulary — **Fork**, **Upstream**, **Pinned SHA**, **Sync candidate**,
**Consumed skill**, **Sync plan**, **Promote**, **Run budget** — is defined in
the orchestrator's [`CONTEXT.md`](../orchestrator/CONTEXT.md). Use those terms.

```
upstream/main (moves)  ->  sync: plan + evals  ->  you approve  ->  fork/main (the pin)  ->  sessions
```

## Modes

Three, and the mode word is part of the invocation:

| Invoke | Does | Reference |
|--------|------|-----------|
| `/skill-fork-sync bootstrap` | Per declared dependency, idempotently: fork upstream into the maintainer's account, clone the fork under `~/.orchestrator/forks/<marketplace-name>/`, add the `upstream` remote, reset the fork's default branch to the **currently-installed** SHA and force-push, write `FORK.md`, then swap the marketplace registration from upstream to the fork. Behaviour-neutral by construction: day one after bootstrap runs exactly the code that ran before it. | [`references/bootstrap.md`](references/bootstrap.md) |
| `/skill-fork-sync sync [<fork>]` | For one named fork or all of them: resolve the **Pinned SHA** and the **Sync candidate** live from git, diff them, map changed paths to skills, mark each changed skill **consumed** or skipped, allocate the **Run budget**, then evaluate the consumed ones candidate-vs-pinned in a throwaway worktree and report an assertion table with a promote/hold recommendation. A delta touching nothing consumed costs zero runs. | [`references/sync.md`](references/sync.md) |
| `/skill-fork-sync promote` | On explicit approval only: fast-forward and push the fork's default branch to the candidate, rewrite `FORK.md`'s synced SHA, update the marketplace, then update the plugin — using the update command that matches the dependency's install shape. One step, so fork and install never disagree. Ends by stating that the new skill body loads next session. | [`references/promote.md`](references/promote.md) |

Read the mode's reference file before acting. `SKILL.md` names the modes; the
references own the steps.

## Rules that hold across all three modes

- **The maintainer decides every promote.** At most 5 runs per sync is too thin
  a sample to move a live install unattended, and a silent promote reintroduces
  the exact problem the fork exists to prevent. No auto-promote on a clean eval —
  see [ADR 0008](../orchestrator/docs/adr/0008-diff-targeted-run-budget.md).
- **The Pinned SHA comes from git, never from `FORK.md`.** `FORK.md` is a record
  for humans; a stale one must not be able to drive a wrong decision.
- **The live install is never touched during an evaluation.** The candidate is
  read from a worktree path injected into the eval worker's prompt, so a bad
  candidate cannot break the session evaluating it, and rejecting a candidate is
  a `rm -rf` of a worktree with no rollback path to get wrong.
- **Nothing lives under `~/.claude/plugins/marketplaces/`.** That directory is a
  git clone Claude Code owns and may reset or re-clone on `marketplace update`,
  which would take an in-progress candidate worktree with it. Fork clones and
  candidate worktrees go under `~/.orchestrator/forks/`.
- **Marketplace names stay as upstream defines them** — the id comes from the
  `name` field in the source's `.claude-plugin/marketplace.json`, not from the
  repo path. Leaving that file untouched means `mattpocock-skills@mattpocock` and
  `ponytail@ponytail` survive forking, so no existing doc reference needs
  editing and the file never conflicts on a sync.
- **Every sync is explicitly invoked.** Nothing here schedules itself.

## What this skill reuses, and what it deliberately doesn't

It borrows the orchestrator's machinery rather than growing its own: the config
at `docs/agents/orchestrator.md`, the worktree operations in
[`../orchestrator/references/tools/_operations.md`](../orchestrator/references/tools/_operations.md),
the harness launch composition in
[`../orchestrator/references/harnesses/claude.md`](../orchestrator/references/harnesses/claude.md),
`prompt-improver` for prompt composition, and the file-based checklist.

It does **not** use the ready queue, the work-state labels, the MR/evidence
completion contract, or adversarial review. An eval run has no work item, opens
no merge request, and needs no cross-vendor reviewer.

## Implementation status

The three mode reference files are stubs. Each names what will fill it and which
work item does so; the mode names above are fixed, so those items inherit the
invocation surface rather than each inventing one. The deterministic half of a
sync (delta detection, diff-to-skill mapping, the consumption check, budget
allocation) is destined for a single seam — a `scripts/fork_state.py` that emits
the **Sync plan** as JSON and mutates nothing. That script is not in the repo
yet; it lands with the sync-plan work item.
