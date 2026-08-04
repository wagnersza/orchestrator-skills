# orchestrator-skills

Skills for driving multi-agent development work: an **orchestrator** session
coordinates **worker** sessions, each a `(tool, harness, model)` triple
implementing one work item in its own worktree. See [`README.md`](README.md) for
the layout and [`orchestrator/CONTEXT.md`](orchestrator/CONTEXT.md) for the
vocabulary.

A third skill, **`skill-fork-sync`**, owns dependency versioning: it forks each
declared skill dependency, pins the fork's default branch, and gates upstream
deltas behind a diff-targeted evaluation before you promote. See
[`skill-fork-sync/SKILL.md`](skill-fork-sync/SKILL.md),
[ADR 0007](orchestrator/docs/adr/0007-fork-and-pin-skill-dependencies.md) and
[ADR 0008](orchestrator/docs/adr/0008-diff-targeted-run-budget.md).

This repo is mostly markdown skills plus JSON manifests — nothing to build, boot,
or migrate. The one exception is `scripts/fork_state.py` (the sync-plan seam) and
its stdlib-only test suite: **run the tests when you touch a Python file**, per the
`evidence` bar in [`docs/agents/orchestrator.md`](docs/agents/orchestrator.md).

## Working here

- **Prompting rules live in the `prompt-improver` skill, not here.** The
  orchestrator drafts a prompt and runs it through that dependency. Don't
  re-vendor prompting guidance into this repo — see
  [ADR 0006](orchestrator/docs/adr/0006-delegate-prompting-to-prompt-improver.md).
- **Writing rules live in the `simple-english` skill, not here.** Before you
  commit, run the prose you changed through that dependency in pragmatic mode.
  This covers the markdown in your diff, your review note, your PR body, and each
  string a Python file prints. Code blocks, identifiers, paths, commands, quoted
  error strings, YAML and JSON keys, link targets and proper nouns stay
  byte-identical. This repo defines only what counts as a **prose deliverable**
  ([`orchestrator/CONTEXT.md`](orchestrator/CONTEXT.md)) and restates no rule of
  the standard, per
  [ADR 0011](orchestrator/docs/adr/0011-delegate-technical-writing-to-simple-english.md).
- **Commit in slices, not one blob per item.** One commit holds one logical change. It
  also leaves the branch self-consistent, so every cross-reference it adds resolves
  inside the same commit. Commit each slice as soon as it is complete. Conventional
  Commits prefix, imperative subject, and a body that says why when the subject cannot
  carry it. A trivial item is one commit, and that is not a violation. The unit is the
  **Commit slice** entry in [`orchestrator/CONTEXT.md`](orchestrator/CONTEXT.md). The
  rationale is
  [ADR 0013](orchestrator/docs/adr/0013-workers-commit-in-contextualised-slices.md).
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
