# Mode: sync

`/skill-fork-sync sync [<fork>]` — detect whether upstream moved past the
**Pinned SHA**, work out what the delta actually touches, spend the **Run
budget** only where this repo is exposed, and hand back evidence plus a
promote-or-hold recommendation.

> **Status: half implemented.** The deterministic half below is in the repo
> (`scripts/fork_state.py`, issue #3). The judgment half is still a stub, filled
> by issue #5 (*Sync and gate: detect delta, eval candidate, recommend*).

## The deterministic half: `scripts/fork_state.py`

Everything derivable is worked out by one seam that emits the **Sync plan** as
JSON and **mutates nothing** — it only reads (`git rev-parse`, `git diff
--name-only`, `git ls-tree`, `gh repo view --json parent`), so a sync can call it
as often as it likes. It never fetches: refreshing the `upstream` remote is the
caller's step, because it is a mutation.

```
python3 -m scripts.fork_state                    # every discovered fork
python3 -m scripts.fork_state --fork mattpocock  # one fork
```

Both are run from this repo's root, matching `skill-creator`'s
`python3 -m scripts.<name>` convention. `--repo <path>` overrides which repo is
grepped for references (default: the working directory); `--budget N` overrides
the ceiling; `--clone <path> --upstream-repo <owner/repo>` plans a clone directly
and skips discovery, which is how the tests avoid needing `gh`. Exit status is
`1` when any fork entry carries an `error` — a missing clone means bootstrap has
not run — and `0` otherwise.

What it derives, in order:

1. **The fork set**, from `~/.claude/plugins/known_marketplaces.json` cross-referenced
   against `gh repo view --json parent`: a registered marketplace whose repo has
   a GitHub parent is a **Fork**, and its clone is expected at
   `~/.orchestrator/forks/<marketplace-name>/`. There is no registry of forks in
   this repo to drift.
2. **Pinned SHA** as `git rev-parse main` and **Sync candidate** as
   `git rev-parse upstream/main`, both in the fork clone. `FORK.md` is never
   read, so a stale or wrong record cannot change the plan.
3. **The delta**: `git diff --name-only pinned..candidate`, with each path
   attributed to the innermost directory holding a `SKILL.md` at either SHA.
   Paths belonging to no skill land in `unmapped_paths` and spend nothing.
4. **Consumption**: each changed skill's directory name is grepped across this
   repo (`.git`, `.orchestrator`, `node_modules`, `__pycache__`, `.venv`
   excluded). A hit makes it a **Consumed skill** and records which files
   referenced it; no hit skips it with `"reason": "not referenced by this repo"`.
5. **Run budget** allocation, global across all forks in the plan and in fork
   order: 2 runs per consumed skill (one candidate, one pinned baseline), so a
   5-run ceiling covers two skills and leaves one run as a tiebreak reserve.
   Anything past the ceiling gets `runs: 0` and is named in
   `dropped_for_budget`, at both the skill and the plan level — silent
   truncation would read as full coverage
   ([ADR 0008](../../orchestrator/docs/adr/0008-diff-targeted-run-budget.md)).

### Plan shape

```json
{
  "generated_by": "scripts.fork_state",
  "mutates": "nothing",
  "consuming_repo": "/path/to/orchestrator-skills",
  "run_budget": {
    "ceiling": 5,
    "runs_per_skill": 2,
    "runs_per_skill_note": "one candidate run plus one pinned-baseline run",
    "allocated": 2,
    "tiebreak_reserve": 3,
    "dropped_for_budget": []
  },
  "forks": [
    {
      "fork": "mattpocock",
      "fork_repo": "wagnersza/skills",
      "upstream": "mattpocock/skills",
      "clone": "/Users/me/.orchestrator/forks/mattpocock",
      "pinned_sha": "ed37663...",
      "candidate_sha": "2ab9580...",
      "sha_source": "git rev-parse (FORK.md is never read)",
      "up_to_date": false,
      "changed_paths": ["README.md", "skills/engineering/code-review/SKILL.md"],
      "unmapped_paths": ["README.md"],
      "skills": [
        {
          "skill": "code-review",
          "path": "skills/engineering/code-review",
          "changed_paths": ["skills/engineering/code-review/SKILL.md"],
          "consumed": true,
          "referenced_by": ["docs/agents/orchestrator.md"],
          "runs": 2
        }
      ],
      "consumed": ["code-review"],
      "skipped": [],
      "allocated_runs": 2,
      "dropped_for_budget": []
    }
  ]
}
```

An up-to-date fork reports `"up_to_date": true` with empty `changed_paths`,
`skills`, `consumed` and `skipped`, and `allocated_runs: 0`. A skipped skill
carries `"consumed": false`, a `reason`, and `runs: 0` instead of
`referenced_by`. A fork whose clone is missing carries only `error`.

### Tests

Seven cases in `scripts/test_fork_state.py`, each building throwaway git repos in
a temp directory and asserting on the emitted JSON — external behaviour at the
seam, not helper return values. Stdlib only, no network, no `gh`, no agent runs:

```
python3 -m pytest scripts/ -q                 # if pytest is present
python3 -m unittest discover -s scripts -q    # the guaranteed fallback
```

| Test | Covers |
|------|--------|
| `test_no_delta_reports_up_to_date_and_zero_runs` | no delta — pin equals candidate, zero runs |
| `test_unconsumed_delta_allocates_zero_runs` | delta touching only unreferenced skills |
| `test_consumed_delta_is_listed_for_eval` | a referenced skill is listed with runs |
| `test_mixed_delta_splits_consumed_and_skipped` | both kinds split correctly |
| `test_budget_ceiling_never_exceeds_five_and_names_drops` | ceiling holds, drops named |
| `test_pinned_sha_comes_from_git_not_fork_md` | a wrong `FORK.md` SHA changes nothing |
| `test_script_mutates_nothing` | refs, worktree and consuming repo unchanged |

Running them is part of this repo's `evidence` bar whenever a Python file is
touched — see `docs/agents/orchestrator.md`.

## The judgment half

Still a stub, owned by issue #5. What belongs here is what actually needs prose:

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
