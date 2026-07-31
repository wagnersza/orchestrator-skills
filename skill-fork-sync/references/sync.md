# Mode: sync

`/skill-fork-sync sync [<fork>]` — detect whether upstream moved past the
**Pinned SHA**, work out what the delta actually touches, spend the **Run
budget** only where this repo is exposed, and hand back evidence plus a
promote-or-hold recommendation.

> **Status: implemented.** The deterministic half is in the repo
> (`scripts/fork_state.py`, issues #3 and #4); the judgment half is
> [below](#the-judgment-half). Neither half has yet run against a real fork —
> bootstrap is a human step and has not been performed, so `~/.orchestrator/forks/`
> is empty today and a sync reports that cleanly rather than failing.

## The deterministic half: `scripts/fork_state.py`

Everything derivable is worked out by one seam that emits the **Sync plan** as
JSON and **mutates nothing** — it only reads (`git rev-parse`, `git diff
--name-only`, `git ls-tree`, `gh repo view --json parent`), so a sync can call it
as often as it likes. It never fetches: refreshing the `upstream` remote is the
caller's step, because it is a mutation.

```
python3 -m scripts.fork_state                    # every discovered fork
python3 -m scripts.fork_state --fork mattpocock  # one fork
python3 -m scripts.fork_state --evals            # the same plan, turned into runs
```

The same script also emits the **bootstrap plan** under `--bootstrap`, which is
the dry run [`bootstrap.md`](bootstrap.md) documents. One seam, several plans: all
of them read the same config and all of them mutate nothing.

All of them are run from this repo's root, matching `skill-creator`'s
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
   this repo to drift. (Bootstrap needs the complementary view — declared
   dependencies whose marketplace still points at upstream, so `parent` is empty —
   which is `--bootstrap`'s job.)
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

### The eval plan: `--evals`

The same seam turns a **Sync plan** into the runs a sync may actually spend. It
adds no run of its own and creates nothing:

```
python3 -m scripts.fork_state --evals                    # every fork
python3 -m scripts.fork_state --evals --fork mattpocock  # one fork
```

Per **Consumed skill** that the budget covers, it names: the candidate and pinned
worktree paths and the skill directory inside each (what gets injected into the
worker's prompt), the committed eval set the sync extends and the assertion names
already in it, the two transcript paths, and whether the assertions must target the
skill body's *content* rather than its runtime behaviour. Per fork it names a
verdict — `promotable`, `needs evaluation` or `cannot evaluate` — and at the plan
level the budget: `runs_planned`, `spent_on`, `remaining`, and `uncovered` with
every skipped and every budget-dropped skill listed at `cost: 0`.

Two other flags exist for the judgment half's benefit, both of which write nothing:

```
python3 -m scripts.fork_state --merge-eval-set --fork mattpocock \
    --skill code-review --new-assertions drafted.json --first-seen <candidate-sha>
python3 -m scripts.fork_state --check-path <path>        # exit 2 if inside ~/.claude/plugins
```

`--results-root` moves where transcripts would go and `--plugin-root` moves the
directory the guard protects; the tests use both, and a real sync needs neither.

### Tests

Twenty-four cases in `scripts/test_fork_state.py`, each building throwaway git repos
and config files in a temp directory and asserting on the emitted JSON — external
behaviour at the seam, not helper return values. Stdlib only, no network, no `gh`,
no agent runs:

```
python3 -m pytest scripts/ -q                 # if pytest is present
python3 -m unittest discover -s scripts -q    # the guaranteed fallback
```

Seven for the sync plan (`SyncPlanTestCase`):

| Test | Covers |
|------|--------|
| `test_no_delta_reports_up_to_date_and_zero_runs` | no delta — pin equals candidate, zero runs |
| `test_unconsumed_delta_allocates_zero_runs` | delta touching only unreferenced skills |
| `test_consumed_delta_is_listed_for_eval` | a referenced skill is listed with runs |
| `test_mixed_delta_splits_consumed_and_skipped` | both kinds split correctly |
| `test_budget_ceiling_never_exceeds_five_and_names_drops` | ceiling holds, drops named |
| `test_pinned_sha_comes_from_git_not_fork_md` | a wrong `FORK.md` SHA changes nothing |
| `test_script_mutates_nothing` | refs, worktree and consuming repo unchanged |

Seven for the bootstrap plan (`BootstrapPlanTestCase`), which stands the `gh`
reads up with `--gh-fixture`:

| Test | Covers |
|------|--------|
| `test_fork_targets_are_declared_deps_still_pointing_at_upstream` | the target set: declared, registered, not already the maintainer's own |
| `test_pin_is_the_installed_sha_not_upstream_head` | the pin comes from `installed_plugins.json`, and upstream's head appears nowhere |
| `test_dry_run_prints_all_six_actions_and_takes_none` | all six actions printed in order, nothing on disk or in the config touched |
| `test_fork_md_records_the_five_fields` | `FORK.md` carries upstream, date, SHA, why, local changes |
| `test_rerun_against_a_bootstrapped_fork_is_a_no_op_per_step` | every step reads `done` on a re-run, with `FORK.md` one commit past the pin |
| `test_a_moved_default_branch_is_not_reported_as_pinned` | a promoted branch is not mistaken for the pin |
| `test_a_plugin_with_no_installed_sha_blocks_the_pin` | no `gitCommitSha` blocks the pin instead of guessing |

Ten for the eval plan (`EvalPlanTestCase`), which builds two fork clones — one in
`mattpocock`'s invoked-skill shape, one in `ponytail`'s hook-loaded shape:

| Test | Covers |
|------|--------|
| `test_consumed_delta_plans_a_worktree_pair_at_candidate_and_pin` | the delta is reported and both worktrees are planned, candidate against pin |
| `test_unconsumed_delta_is_promotable_with_zero_runs` | an unconsumed delta is promotable at zero runs |
| `test_no_planned_path_falls_inside_the_plugin_directory` | the plugin-root guard, on both a planned and a tool-chosen path |
| `test_assertions_are_named_and_the_eval_set_is_per_fork_per_skill` | every assertion named; the set keyed by fork and skill |
| `test_eval_set_is_extended_not_rewritten` | a later sync appends and keeps the old assertions verbatim |
| `test_budget_accounting_names_the_spend_and_what_is_uncovered` | the ceiling holds, and the spend and the gaps are both named |
| `test_a_hook_loaded_plugin_asserts_on_body_content` | a hooks manifest switches the assertion target to body content |
| `test_the_plan_promotes_nothing_and_rejecting_is_a_worktree_removal` | advisory only; reject = remove a worktree |
| `test_a_fork_with_no_clone_reports_cleanly_and_spends_nothing` | an un-bootstrapped fork is reported, not a blocker |
| `test_it_runs_for_one_named_fork_or_for_all_of_them` | `--fork <name>` and no argument |

Running them is part of this repo's `evidence` bar whenever a Python file is
touched — see `docs/agents/orchestrator.md`.

## The judgment half

Seven steps. The first three are cheap and the sync often stops inside them; only
step 4 onward spends anything.

### 1. Refresh the upstream remote, then read the plan

The seam never fetches — refreshing is a mutation, so it is the caller's. Per fork
in scope, through the configured tool's shell, then read the plan:

```bash
git -C ~/.orchestrator/forks/<fork> fetch upstream
python3 -m scripts.fork_state --evals [--fork <name>]
```

No `--fork` means every fork; `--fork <name>` means exactly one, and a named fork
gets the whole ceiling rather than a share of it. **A fork whose clone is missing
is reported, not fatal** — its entry carries `bootstrapped: false`, a verdict of
`cannot evaluate` and the instruction to run bootstrap, and every other fork is
still planned. Today that is the live case: bootstrap has never been run for real,
so `~/.orchestrator/forks/` is empty and a sync's honest answer is "nothing is
bootstrapped yet".

### 2. Present the delta before spending anything

Show, per fork: the **Pinned SHA**, the **Sync candidate**, the changed paths,
which skills they map to, which of those are **Consumed skills** and which were
skipped with the reason. This is the maintainer's chance to say "that is not worth
evaluating" before a single run is spent, so it comes first and it is never
skipped.

### 3. Stop here if there is nothing consumed

Two verdicts end the sync at zero runs:

| Plan says | Report |
|-----------|--------|
| `up_to_date: true` | Nothing to do: the pin is already the candidate. |
| `verdict: promotable`, `evals: []` | **Promotable, zero eval runs spent.** The delta touched only skills this repo never references, each one named with its reason. |

Say the number out loud and still end in the explicit recommendation of step 7 —
the short report has the same sections as the long one, with an empty assertion
table:

```
## mattpocock: 91aae53 -> f8adfd8

Delta: 1 file, 1 skill. Consumed: none. Skipped: wayfinder (not referenced by
this repo).

### Assertions — candidate vs pinned

None. No consumed skill changed, so there was nothing to assert on.

### Budget (per sync, across every fork)

0 of 5 runs spent.

Not covered:
- mattpocock/wayfinder — not referenced by this repo (0 runs)

### Transcripts

None — no run was launched.

### Recommendation: PROMOTE

The delta touches only `skills/wayfinder/`, which nothing in this repo
references, so no contract this repo depends on can have moved.

Nothing was promoted. The pin is unchanged at 91aae53. To take the candidate:
`/skill-fork-sync promote`.
```

Routine upstream churn costing nothing is the point of the diff targeting
([ADR 0008](../../orchestrator/docs/adr/0008-diff-targeted-run-budget.md)), not an
edge case to gloss over.

### 4. Cut the worktree pair, through the tool

Per covered skill the plan names two worktrees — one at the candidate, one at the
**Pinned SHA**. Cut them with the configured tool's **worktree-create** operation
from [`_operations.md`](../../orchestrator/references/tools/_operations.md), never
with raw `git worktree`: the tool owns worktree paths, and for `orca` the path is
whatever `worktree.path` comes back as, not the one guessed here. Then verify it:

```bash
python3 -m scripts.fork_state --check-path "$WORKTREE_PATH"
```

Exit 2 means the path landed inside `~/.claude/plugins` and the eval must not
proceed. This is what makes "the live plugin cache is untouched" a guarantee rather
than an intention — `--evals` refuses to emit a plan naming such a path, and
`--check-path` re-checks the one the tool actually chose. See
[Why nothing lives under the plugin directory](#why-nothing-lives-under-the-plugin-directory).

**Both sides are worktrees.** The baseline is not the installed copy: reading the
live cache would make the comparison depend on a directory `marketplace update`
can change underneath the sync.

### 5. Draft or extend the assertions

The eval set for a fork's skill lives at `evals/<fork>/<skill>.json`, committed —
per fork *and* per skill, so two forks that ship a same-named skill never collide.
The plan says whether the sync is creating it or extending it, and lists the
assertion names already there.

```json
{
  "skill_name": "code-review",
  "fork": "mattpocock",
  "assertions": [
    {
      "name": "names-both-axes",
      "prompt": "Review the staged diff in this repo.",
      "assert": "the output has a Standards section and a Spec section",
      "check": "both headings appear in the transcript",
      "why_this_repo_cares": "docs/agents/orchestrator.md reads both axes",
      "first_seen_candidate": "aaaaaaa"
    }
  ]
}
```

`name` is the only required field and the only one the merge keys on. `evals/` is
un-ignored in `.gitignore` precisely so these files are tracked; the results and
transcripts they produce are not.

**Every assertion is individually named and objectively verifiable.** The name is
what the table's rows are read by, so it has to survive without the transcripts;
the check has to be something a reader can confirm from the transcript without
sharing the drafter's taste. A good assertion names a token, a section, a file, a
count or an ordering:

| Good | Why | Bad |
|------|-----|-----|
| `names-both-axes` — the review output has a Standards section and a Spec section | two headings, present or absent | "the review is thorough" |
| `stops-at-first-rung` — the transcript reaches a solution without proposing an abstraction | one observable event | "the answer feels lazy" |
| `keeps-tracker-doc-path` — the body still cites `docs/agents/issue-tracker.md` | an exact path this repo's contract depends on | "the tracker section is fine" |

Assertions come from what **this repo's contract actually depends on**, which is
why `referenced_by` in the plan matters: the files that mention the skill are the
files a regression would break. A changed skill this repo consumes for exactly one
guarantee needs an assertion on that guarantee, not a survey of the skill.

Extend, never redraft:

```bash
python3 -m scripts.fork_state --merge-eval-set --fork <fork> --skill <skill> \
    --new-assertions drafted.json --first-seen <candidate-sha>
```

It appends by name, keeps every existing assertion's text and its
`first_seen_candidate` verbatim, and reports an incoming assertion that reuses an
existing name as `unchanged_kept_as_is` rather than overwriting it — a redraft
under an old name would silently break comparability with every earlier sync. It
prints the merged set and writes nothing; the caller writes it to `write_to`.

### 6. Run the pair, and read the transcripts

Compose each worker prompt through `prompt-improver`, which
[`requirements.md`](../../orchestrator/references/requirements.md) makes the sole
owner of prompt composition — this file holds no prompting rules. What the prompt
must carry is the eval's content, not its phrasing:

- the **skill directory path** inside the worktree, given as a path to read (the
  `Skill path: <path>` shape `skill-creator` uses), never installed;
- the eval's task;
- nothing about which side is the candidate. A worker told it is judging "the new
  version" is being handed the answer.

Launch each run with the configured harness (`harnesses/<h>.md`) at the config's
model and effort, and save the two transcripts to the paths the plan names under
`.orchestrator/fork-sync/<fork>-<candidate-sha>/` — gitignored, because they are
machine-local noise.

Then grade each assertion against each transcript, **candidate against pinned**.
The question is only ever *did upstream regress*: an assertion that fails on both
sides is a pre-existing gap and not a reason to hold, and an assertion that passes
on both sides is not evidence the change is good — it is evidence it broke nothing.

**A hook-loaded plugin is graded differently.** When the plan reports
`loads_via_hook: true` — `ponytail`, whose `plugin.json` declares a `hooks` file —
the skill reaches a session through SessionStart, and **path injection cannot
exercise a hook**: nothing in a worktree makes a hook fire. So its assertions test
the skill body's *content* (does the ladder still say what this repo's completion
contract assumes) rather than its runtime behaviour. That is structurally weaker
evidence, the plan says so per eval in `assertion_target`, and the report must
repeat it rather than presenting a content check as a behavioural one.

### 7. The report

Fixed shape, and it ends in the recommendation:

```
## <fork>: <pinned-sha-7> -> <candidate-sha-7>

Delta: 6 files, 3 skills. Consumed: code-review, tdd. Skipped: wayfinder
(not referenced by this repo).

### Assertions — candidate vs pinned

| Skill | Assertion | Pinned | Candidate | Verdict |
|-------|-----------|--------|-----------|---------|
| code-review | names-both-axes | pass | pass | held |
| code-review | reports-no-findings-explicitly | pass | FAIL | REGRESSED |
| tdd | red-before-green | pass | pass | held |
| tdd | one-assertion-per-test | fail | fail | pre-existing gap |

### Budget (per sync, across every fork)

4 of 5 runs spent — code-review (1 candidate + 1 pinned), tdd (1 candidate + 1
pinned). 1 run held as a tiebreak, unspent.

Not covered:
- mattpocock/wayfinder — not referenced by this repo (0 runs)
- ponytail/ponytail — run budget exhausted (5 runs per sync) (0 runs)

### Transcripts

.orchestrator/fork-sync/mattpocock-51128af/code-review-candidate.md
.orchestrator/fork-sync/mattpocock-51128af/code-review-pinned.md
.orchestrator/fork-sync/mattpocock-51128af/tdd-candidate.md
.orchestrator/fork-sync/mattpocock-51128af/tdd-pinned.md

### Recommendation: HOLD

`reports-no-findings-explicitly` passed on the pin and failed on the candidate.
This repo's completion contract reads a review's "no findings" statement, so the
regression is on a guarantee it depends on.

Nothing was promoted. The pin is unchanged at 91aae53 and the live install is
untouched. To reject: remove the candidate worktree — there is no rollback,
because nothing was installed. To promote anyway: `/skill-fork-sync promote`.
```

Four rules for the report, all of them load-bearing:

- **The budget section states the spend and the gaps together.** Every skipped and
  every budget-dropped skill is named with its reason at 0 runs, so "tested" never
  silently means "partially tested". An unspent tiebreak run stays unspent — it is
  a reserve, not a quota to fill.
- **The recommendation is explicit and terminal.** `PROMOTE` or `HOLD`, never
  "looks fine". A candidate whose covered assertions all hold is a *recommend
  promote*, not a promote.
- **Hold on any regression on a consumed guarantee**, and hold on thin evidence
  too: an eval that could not be graded, a transcript that shows the worker never
  read the injected path, or a hook-loaded skill whose content check cannot speak
  to the behaviour that changed. Recommend promote only when the evidence actually
  covers what moved.
- **The report says what it did not do.** It promoted nothing, moved no pin and
  modified no install — and the maintainer decides, on a clean table as much as a
  dirty one ([ADR 0008](../../orchestrator/docs/adr/0008-diff-targeted-run-budget.md)).

### Rejecting a candidate

**Remove the worktree. That is the whole cleanup.** No rollback, no reinstall, no
`marketplace remove`, no pin to rewind — the candidate was only ever a path handed
to a worker, so nothing outside the worktree ever knew about it. Use the tool's
**teardown** operation, and the fork clone stays: the candidate is still on the
`upstream` remote for a later sync to reconsider.

That property is the reason path injection was chosen over installing the candidate
to evaluate it. An install would need an uninstall, and an uninstall is a rollback
path that can be got wrong at exactly the moment something is already broken.

### Why nothing lives under the plugin directory

`~/.claude/plugins/marketplaces/<name>/` is a real git clone Claude Code owns and
may reset or re-clone on `marketplace update`, and
`~/.claude/plugins/cache/<owner>/<plugin>/<version>/` is the copy sessions load. A
candidate worktree under either would be destroyed by an unrelated
`marketplace update` mid-evaluation, and a worktree under the *cache* would change
what the evaluating session itself is running. So fork clones live under
`~/.orchestrator/forks/`, candidate worktrees under
`~/.orchestrator/forks/.worktrees/<fork>/`, and results under
`.orchestrator/fork-sync/` in this repo (ADR 0007).

Stated as a guarantee rather than an intention: `--evals` raises rather than emits
a plan naming a path inside the plugin directory, and `--check-path` applies the
same check to a worktree path the configured tool chose. The one thing a sync does
touch there is a read — `known_marketplaces.json`, to discover the fork set.

## Fixed here, inherited there

- Mode word: `sync`, with an optional single fork name; no argument means all
  forks.
- Budget: 5 worker runs per sync, pinned-baseline runs included, with the
  allocation and the drops reported —
  [ADR 0008](../../orchestrator/docs/adr/0008-diff-targeted-run-budget.md).
- Results and transcripts live under `.orchestrator/fork-sync/` and are
  gitignored; the eval sets under `evals/<fork>/<skill>.json` are committed.
- Worktree operations come from the configured tool's reference, not from raw
  git:
  [`_operations.md`](../../orchestrator/references/tools/_operations.md). The
  harness and its model/effort come from
  [`docs/agents/orchestrator.md`](../../docs/agents/orchestrator.md) and
  `references/harnesses/<h>.md`.
- Prompt composition belongs to `prompt-improver`, the sole owner
  ([`requirements.md`](../../orchestrator/references/requirements.md)). Nothing in
  this file is a prompting rule.
- Not used, deliberately: the ready queue, the work-state labels, the MR/evidence
  completion contract, and adversarial review. An eval run has no work item and
  produces no merge request.
- What the promote itself does, once the maintainer approves:
  [`promote.md`](promote.md).
