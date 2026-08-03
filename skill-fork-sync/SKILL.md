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
**Consumed skill**, **Sync plan**, **Promote**, **Run budget**, **Invocation
overlay** — is defined in the orchestrator's
[`CONTEXT.md`](../orchestrator/CONTEXT.md). Use those terms.

```
upstream/main (moves)  ->  sync: plan + evals  ->  you approve  ->  fork/main (the pin)  ->  sessions
```

## Modes

Three, and the mode word is part of the invocation:

| Invoke | Does | Reference |
|--------|------|-----------|
| `/skill-fork-sync bootstrap` | Per declared dependency, idempotently: fork upstream into the maintainer's account, clone the fork under `~/.orchestrator/forks/<marketplace-name>/`, add the `upstream` remote, reset the fork's default branch to the **currently-installed** SHA and force-push, write `FORK.md`, swap the marketplace registration from upstream to the fork, then apply the **Invocation overlay**. Version-neutral by construction: day one after bootstrap runs exactly the code that ran before it, and the only thing that changes is *who* may invoke a skill. | [`references/bootstrap.md`](references/bootstrap.md) |
| `/skill-fork-sync sync [<fork>]` | For one named fork or all of them: resolve the **Pinned SHA** and the **Sync candidate** live from git, diff them, map changed paths to skills, mark each changed skill **consumed** or skipped, allocate the **Run budget**, then evaluate the consumed ones candidate-vs-pinned in a throwaway worktree and report an assertion table with a promote/hold recommendation. A delta touching nothing consumed costs zero runs. | [`references/sync.md`](references/sync.md) |
| `/skill-fork-sync promote` | On explicit approval only, four ordered steps plus an overlay re-apply: advance and push the fork's default branch to the candidate as a **fast-forward** — refusing rather than force-pushing if it cannot — rewrite `FORK.md`'s synced SHA, update the marketplace, then update the plugin with the command that matches the dependency's install shape. Marketplace before plugin, because the plugin installs out of the marketplace's clone. One act, so the fork and the install never disagree; ends by stating that the new skill body loads next session. | [`references/promote.md`](references/promote.md) |

Read the mode's reference file before acting. `SKILL.md` names the modes; the
references own the steps.

## Rules that hold across all three modes

- **The maintainer decides every promote.** At most 5 runs per sync is too thin
  a sample to move a live install unattended, and a silent promote reintroduces
  the exact problem the fork exists to prevent. No auto-promote on a clean eval —
  see [ADR 0008](../orchestrator/docs/adr/0008-diff-targeted-run-budget.md).
- **The Pinned SHA comes from git, never from `FORK.md`.** `FORK.md` is a record
  for humans; a stale one must not be able to drive a wrong decision.
- **A fork carries exactly one local change: the invocation overlay.** Two keys
  deleted so an unattended worker can reach every registered skill — no skill
  body, name or description is edited. It is re-applied after every promote,
  because an upstream commit adding a user-invoked skill re-introduces the keys.
  Anything beyond those two keys means the dial moved and the promote is refused —
  see [ADR 0010](../orchestrator/docs/adr/0010-invocation-overlay-on-the-forks.md).
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

All three modes are implemented. Their deterministic halves live in one seam,
`scripts/fork_state.py`, which emits every plan as JSON and mutates nothing —
`--bootstrap` for the fork targets and their pins, the default and `--evals` for
the **Sync plan** and the runs it may spend, `--promote` for the ordered promote
steps with the fast-forward check and the install-shape decision. Its stdlib-only
test suite is `scripts/test_fork_state.py`. The **Invocation overlay** is the one
piece that writes: `scripts/invocation_overlay.py`, dry unless given `--apply`,
tested by `scripts/test_invocation_overlay.py`.

**`mattpocock` is bootstrapped and overlaid; `ponytail` is not.**
`wagnersza/skills` exists, is pinned at the SHA that was installed on 2026-07-31
(`ed37663`, 1.2.0), carries `FORK.md` and the overlay, and is the registered source
for the `mattpocock` marketplace. `DietrichGebert/ponytail` is still un-forked —
its skills are all model-invocable upstream, so it needed no overlay, and bootstrap
reports its six steps as `todo` rather than failing.
