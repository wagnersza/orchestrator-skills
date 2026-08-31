# orchestrator-skills

Skills for driving multi-agent development work: an **orchestrator** session
coordinates **worker** sessions, each a `(tool, harness, model)` triple
implementing one work item in its own worktree. See [`README.md`](README.md) for
the layout and [`orchestrator/CONTEXT.md`](orchestrator/CONTEXT.md) for the
vocabulary.

This repo is mostly markdown skills plus JSON manifests — nothing to build, boot,
or migrate. The exceptions are two seams, `scripts/close_item.py` (the close
transaction) and `scripts/worker_state.py` (the worker watch), plus the
`scripts/tracker.py` adapter they share (the tracker commands), each with a
stdlib-only test suite: **run the tests when you touch a Python file**, per the
`evidence` bar in [`docs/agents/orchestrator.md`](docs/agents/orchestrator.md).
`scripts/test_links.py` puts every Markdown file in the repo under that same suite.
So **run the tests when you touch a Markdown file too**.

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
- **Closing a work item is a transaction, not a checklist.** Its five steps hold one
  order, and they keep the numbers 4 to 8. `scripts/close_item.py` owns them and refuses
  rather than warns. **A merged pull request is what fires it**, and no verb and no label
  authorises a close. The tick reads that merge and runs the seam in its own process. The
  maintainer merges on the tracker, and no session merges. The unit is the **Close
  transaction** entry in [`orchestrator/CONTEXT.md`](orchestrator/CONTEXT.md). The
  rationale is
  [ADR 0015](orchestrator/docs/adr/0015-close-is-a-deterministic-transaction.md) and
  [ADR 0057](orchestrator/docs/adr/0057-the-merge-is-the-second-act.md).
- **Every claim in a skill body traces to a reference file or an ADR.** A rule with
  no home rots.
- **A decision that reverses or narrows an earlier one gets a new ADR** under
  `orchestrator/docs/adr/`, rather than a silent edit to the old one.
- **Renaming or deleting a reference file means updating every link to it.** A
  dangling cross-reference is this repo's main failure mode.
- **Bump `version` in `.claude-plugin/plugin.json` when a user story finishes.** The bump
  lands with the last child of the story, and never once per work item. Minor for a story
  that changed a contract or a dependency, patch for a docs-only story. **The story sets
  that level, and the file types of its last child never change it.** So a
  documentation-only last child of a contract-changing story still takes the minor. A
  worker on one child leaves the version untouched. Two children that each bump pick the
  same number, and the merge then keeps one bump and loses the other.
- **A work item with no `user-story` parent bumps a patch, in its own branch.** The
  condition is that the item changes what an installed session or a seam does. An item
  that changes only this repo's own files bumps nothing: `CLAUDE.md`, a page under
  `docs/`, an ADR, or a test. The rationale, the rejected release step and the collision
  between two standalone items are in
  [ADR 0050](orchestrator/docs/adr/0050-a-standalone-item-bumps-a-patch.md).

## Agent skills

### Issue tracker

GitHub Issues on `wagnersza/orchestrator-skills`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, unmapped (label string = role name). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — `orchestrator/CONTEXT.md` plus ADRs under `orchestrator/docs/adr/`. See `docs/agents/domain.md`.

### Orchestrator

Runs claude workers via orca — `sonnet-5` @ `medium` by default, `opus-5` @ `high` only where one named `heavy` signal fires; adversarial review off (on demand only). See `docs/agents/orchestrator.md`.

### Quality gates

The `lite` profile: `make quick` runs layers 1 and 2, `make full` runs layer 3, and layer 4 is off. A non-zero exit is a stop, and `hooks/record.py` appends one line per run to `.orchestrator/gates-<item>.jsonl`. See `orchestrator/references/quality-gates.md`.
