# orchestrator-skills

Skills for driving multi-agent development work: an **orchestrator** session
coordinates **worker** sessions, each a `(tool, harness, model)` triple
implementing one work item in its own worktree. See [`README.md`](README.md) for
the layout and [`orchestrator/CONTEXT.md`](orchestrator/CONTEXT.md) for the
vocabulary.

A third skill, **`skill-fork-sync`**, owns dependency versioning: it forks each
declared skill dependency, pins the fork's default branch, applies the **invocation
overlay** so an unattended worker can reach every registered skill, and gates
upstream deltas behind a diff-targeted evaluation before you promote. See
[`skill-fork-sync/SKILL.md`](skill-fork-sync/SKILL.md),
[ADR 0007](orchestrator/docs/adr/0007-fork-and-pin-skill-dependencies.md),
[ADR 0008](orchestrator/docs/adr/0008-diff-targeted-run-budget.md) and
[ADR 0010](orchestrator/docs/adr/0010-invocation-overlay-on-the-forks.md).

This repo is mostly markdown skills plus JSON manifests — nothing to build, boot,
or migrate. The exceptions are `scripts/fork_state.py` (the sync-plan seam) and
`scripts/invocation_overlay.py` (the overlay writer), each with a stdlib-only test
suite: **run the tests when you touch a Python file**, per the `evidence` bar in
[`docs/agents/orchestrator.md`](docs/agents/orchestrator.md).

## Working here

- **Prompting rules live in the `prompt-improver` skill, not here.** The
  orchestrator drafts a prompt and runs it through that dependency. Don't
  re-vendor prompting guidance into this repo — see
  [ADR 0006](orchestrator/docs/adr/0006-delegate-prompting-to-prompt-improver.md).
- **Every claim in a skill body traces to a reference file or an ADR.** A rule with
  no home rots.
- **A decision that reverses or narrows an earlier one gets a new ADR** under
  `orchestrator/docs/adr/`, rather than a silent edit to the old one.
- **Renaming or deleting a reference file means updating every link to it.** A
  dangling cross-reference is this repo's main failure mode.
- **Bump `version` in `.claude-plugin/plugin.json`** — minor for a contract or
  dependency change, patch for docs-only.

## Agent skills

### Issue tracker

GitHub Issues on `wagnersza/orchestrator-skills`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, unmapped (label string = role name). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — `orchestrator/CONTEXT.md` plus ADRs under `orchestrator/docs/adr/`. See `docs/agents/domain.md`.

### Orchestrator

Runs claude workers via orca — `opus-5` @ `xhigh` for heavy items, `sonnet-5` @ `medium` for light ones; adversarial review off (on demand only). See `docs/agents/orchestrator.md`.
