# Mode: sync

`/skill-fork-sync sync [<fork>]` — detect whether upstream moved past the
**Pinned SHA**, work out what the delta actually touches, spend the **Run
budget** only where this repo is exposed, and hand back evidence plus a
promote-or-hold recommendation.

> **Status: stub.** Filled by issue #5 (*Sync and gate: detect delta, eval
> candidate, recommend*), which depends on issue #3 (*Sync-plan seam:
> fork_state script + test suite*) for the deterministic half. Nothing here is
> implemented yet.

## What will fill this file

**The deterministic half** is not prose — it belongs to `scripts/fork_state.py`,
which emits the **Sync plan** as JSON and mutates nothing: enumerate the forks,
resolve pinned (`git rev-parse main` in the fork clone) and candidate
(`git rev-parse upstream/main`), diff pinned..candidate, map changed paths to
skill directories, grep this repo for each changed skill's name to decide whether
it is **consumed**, allocate the budget, and name what was dropped. Testable with
plain asserts and zero agent runs, which keeps the whole budget for real evals.

**This file will own the judgment half**, which is what actually needs prose:

- Reading the sync plan and presenting the delta — which files, which skills,
  consumed versus skipped — before spending anything.
- Drafting objectively verifiable named assertions per eval, extending the
  committed eval sets under `evals/<marketplace-name>/` rather than redrafting
  them each sync, so coverage compounds and results stay comparable.
- Running each eval **candidate versus the pinned version**, not versus no skill
  at all: the question is whether upstream regressed, not whether the skill is
  useful.
- Path injection as the eval mechanism — the worker is handed the candidate
  worktree path and reads `SKILL.md` as a file, so the live plugin cache is never
  modified during an evaluation.
- Reporting the assertion pass/fail table, links to the transcripts under
  `.orchestrator/fork-sync/<fork>-<candidate-sha>/`, how the budget was
  allocated, and what coverage was dropped for budget — so "tested" never
  silently means "partially tested".
- The terminal recommendation: promote or hold. The decision stays the
  maintainer's.

An empty-or-unconsumed delta is the cheap path: promotable immediately with zero
runs, so routine upstream churn costs nothing.

## Fixed here, inherited there

- Mode word: `sync`, with an optional single fork name; no argument means all
  forks.
- Budget: 5 worker runs per sync, pinned-baseline runs included, with the
  allocation and the drops reported —
  [ADR 0008](../../orchestrator/docs/adr/0008-diff-targeted-run-budget.md).
- Results and transcripts live under `.orchestrator/fork-sync/` and are
  gitignored; the eval sets under `evals/` are committed.
- Worktree operations come from the configured tool's reference, not from raw
  git:
  [`_operations.md`](../../orchestrator/references/tools/_operations.md).
