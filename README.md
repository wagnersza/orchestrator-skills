# orchestrator-skills

Run agent workers on a tracker's `ready-for-agent` issues. One orca automation per repo
ticks every minute at zero tokens. Each worker runs in its own worktree, on the harness and
model its role names. The tracker's state labels are the only state.

- **Harnesses:** claude, codex, cursor, pi and copilot.
- **Trackers:** GitHub, GitLab and local markdown.
- **Roles:** heavy, medium and light, each a harness, a model and an effort.

The terms are in [`orchestrator/CONTEXT.md`](orchestrator/CONTEXT.md), and the decisions
are in [`orchestrator/docs/adr/`](orchestrator/docs/adr/).

## Install

It ships as a [Claude Code plugin](https://code.claude.com/docs/en/plugins):

```bash
claude plugin marketplace add wagnersza/orchestrator-skills
claude plugin install orchestrator-skills@wsza
```

Then open the repo in Orca, and in a Claude session in an Orca terminal say:

```
set up the orchestrator
```

The `orchestrator-setup` skill reads the tracker from `docs/agents/issue-tracker.md`, asks
for a cost profile, `max_workers` and the base branch, and installs what is missing: the
tracker CLI, each harness CLI, and the worker's mattpocock skills in every harness. It
writes `docs/agents/orchestrator.md`, then runs the script's `install`. That creates the
state labels, the orca Run, the `orchestrator-tick` automation and one proof tick. A re-run
is safe. This repo's own config is [`docs/agents/orchestrator.md`](docs/agents/orchestrator.md).

You need orca, Node 22.18 or later, and `gh` or `glab` for a GitHub or GitLab tracker.

## The loop

1. **You label an issue `ready-for-agent`.** On a parent, label each child that is ready
   too.
2. **The tick claims it.** Every minute it assigns you each eligible issue, moves it to
   `in-progress` and starts a worker in worktree `issue-N`, up to `max_workers`. "work on
   N" does the same at once.
3. **The worker does the work.** It runs the `implement` skill, commits in slices, opens a
   PR with `Closes #N`, and reports to orca.
4. **The tick reads the report.** Done with an open PR moves the issue to
   `ready-for-human`. A failure, a question or a dead worker moves it to `needs-human`, with
   the worker's own words as a comment.
5. **You review.** Say "merge N" and the session merges and tears down, or merge on the
   tracker and the next tick tears down. To resume a `needs-human` issue, answer on the
   issue and relabel it `ready-for-agent`. A fresh worker picks up in the same worktree.

Say "status" to see the claimed issues, the ready queue and why each other issue waits.

## Layout

```
orchestrator/            the orchestrator skill, its glossary and ADRs
orchestrator-setup/      the setup skill and the config template
scripts/orchestrator.ts  install · tick · start · status · merge
scripts/harnesses.ts     how each harness starts
scripts/trackers/        github · gitlab · local
```

`make quick` runs the typecheck and the test suite.

## v1

v1 had cmux and herdr, a per-item automation, quality-gate layers, adversarial review and
65 ADRs. It is the [`v1.0.0`](https://github.com/wagnersza/orchestrator-skills/tree/v1.0.0)
tag.
