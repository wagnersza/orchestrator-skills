# orchestrator-skills

Two skills, `orchestrator` and `orchestrator-setup`, and the TypeScript script they call.
The orchestrator session runs agent workers on this repo's tracker issues, one worker per
issue in its own worktree. See [`README.md`](README.md) for the loop and
[`orchestrator/CONTEXT.md`](orchestrator/CONTEXT.md) for the terms.

The script is `scripts/orchestrator.ts`, with `scripts/harnesses.ts` and
`scripts/trackers/`. Node 22.18 or later runs it directly, with no build step and no
runtime dependency. **Run `make quick` when you touch a TypeScript or Markdown file.** It
runs the typecheck and the `node --test` suite, and `scripts/links.test.ts` in that suite
checks that every relative Markdown link resolves.

## Working here

- **Commit in slices, not one blob per item.** One commit holds one logical change. It also
  leaves the branch self-consistent, so every cross-reference it adds resolves inside the
  same commit. Commit each slice as soon as it is complete. Use a Conventional Commits
  prefix, an imperative subject, and a body that says why when the subject cannot carry it.
  A trivial item is one commit, and that is not a violation.
- **Every rule in a skill body traces to an ADR or the glossary.** ADRs live under
  `orchestrator/docs/adr/`. A decision that reverses an earlier one gets a new ADR.
- **Bump `version` in `.claude-plugin/plugin.json` when a user story finishes.** The bump
  lands with the last child of the story, and never once per work item. Minor for a story
  that changed a contract or a dependency, patch for a docs-only story. The story sets that
  level, and the file types of its last child never change it. A worker on one child leaves
  the version untouched.
- **A work item with no `user-story` parent bumps a patch, in its own branch**, when it
  changes what an installed skill or the script does. An item that changes only this repo's
  own files bumps nothing: `AGENTS.md`, a page under `docs/`, an ADR, or a test.

## Agent skills

### Issue tracker

GitHub Issues on `wagnersza/orchestrator-skills`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, unmapped (label string = role name). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — `orchestrator/CONTEXT.md` plus ADRs under `orchestrator/docs/adr/`. See `docs/agents/domain.md`.

### Orchestrator

Runs claude workers via orca, one at a time for the first dogfood run. `sonnet` @ `medium`
by default, `opus` @ `high` on the `heavy` label or three Touches paths, `sonnet` @ `low` on the
`light` label. See `docs/agents/orchestrator.md`.
