# A sync spends at most 5 worker runs, targeted by the diff

> Superseded by [ADR 0028](0028-drop-the-fork-and-pin-dial.md)

Evaluating a **Sync candidate** costs real agent runs, and the useful question is
narrow: *did upstream regress something this repo relies on?* So a sync is capped
at **5 worker runs total, pinned-baseline runs included** — either two paired
candidate-vs-pinned comparisons plus a tiebreak, or up to five candidate runs.
The allocation and anything dropped for budget is always reported, never silent.

The budget is spent where the diff points. `scripts/fork_state.py` maps each
changed path to a skill directory, and a changed skill is evaluated only if it is
**consumed** — if this repo references it. A delta touching nothing consumed costs
zero runs and is promotable immediately, which is what makes routine upstream
churn free.

Baseline is the **pinned version**, not no-skill: comparing against nothing
answers "is this skill useful", which nobody is asking. Comparing against the pin
answers "did upstream regress", which is the whole point. That is
`skill-creator`'s improving-an-existing-skill mode rather than its new-skill mode.

**Consumption is decided by grep, and grep over-tests.** Generic skill names
(`implement`, `research`, `code-review`) match text that has nothing to do with
the skill, so false positives are expected. That direction is deliberate: a false
positive spends budget on a skill that did not need testing, while a false
negative ships an unevaluated change to a contract this repo depends on. Grep is
also self-maintaining — a new reference added to any doc is covered by the next
sync with no registry to update.

## Considered Options

- **Diff-targeted, 5-run ceiling, baseline included** (chosen) — bounded and
  predictable cost, spent on the skills the diff actually touched. Counting the
  baseline runs inside the ceiling is what keeps the bound honest: a "5 candidate
  runs plus however many baselines" budget is really a 10-run budget.
- **A fixed contract-floor suite that runs every sync regardless of the diff** —
  attractive because it would catch a regression the diff mapping missed, and
  rejected because of the arithmetic: with a 5-run ceiling the floor can consume
  the entire budget and leave nothing for the change that triggered the sync. A
  floor is only affordable with a much larger ceiling, which is a different
  decision to make later, not a default to adopt now.
- **No ceiling — evaluate every consumed skill the diff touched** — best coverage,
  unbounded cost. A large upstream refactor touching a dozen consumed skills
  turns a routine sync into an expensive one at the worst possible moment, and
  the cost is discovered mid-run.
- **A registry of which skills this repo consumes, maintained by hand** — no
  false positives, and it drifts the first time someone adds a doc reference
  without updating it. That drift fails in the dangerous direction: a skill
  silently drops out of coverage.
- **Auto-promote when every assertion passes** — removes the human step, on
  evidence far too thin to carry it. At most 5 runs is not a pass rate, and a
  silent promote reintroduces exactly the problem the fork was created to
  prevent (ADR 0007).

## Consequences

- **"Tested" is always qualified.** Every sync report states how the budget was
  allocated and what was dropped, so partial coverage is visible rather than
  implied.
- **The promote decision stays with the maintainer**, every time, including on a
  clean assertion table.
- **The deterministic half must be free.** Delta detection, diff-to-skill mapping,
  the consumption check and budget allocation all live in one seam
  (`scripts/fork_state.py`) that spawns no agent, so the whole 5-run budget is
  available for actual evaluation. That seam is testable with plain asserts, and
  its test suite is why this repo is no longer markdown-only — see the evidence
  bar in `docs/agents/orchestrator.md`.
- **Eval sets accrete.** They are committed under `evals/<marketplace-name>/` and
  extended rather than rewritten each sync, so coverage compounds and results
  stay comparable across syncs. Results and transcripts under
  `.orchestrator/fork-sync/` are gitignored machine-local noise.
- **`ponytail`'s evidence is structurally weaker than `mattpocock`'s.** It loads
  via a SessionStart hook rather than skill invocation, and path injection cannot
  exercise a hook — so its assertions test whether the skill body still *says*
  what the completion contract assumes, not its runtime behaviour. Recorded here
  rather than papered over.
- The budget rule is enforced in
  [`skill-fork-sync/references/sync.md`](../../../skill-fork-sync/references/sync.md).
