# orchestrator-skills

Skills for driving multi-agent, multi-tool development work. An **orchestrator**
session coordinates **worker** sessions: each worker is a
`(tool, harness, model)` triple implementing one work item in its own worktree.

- **`orchestrator/`** — pick the next ready work item, spawn a worker, prompt and
  monitor it, run optional cross-vendor adversarial review, and close finished
  work. Tool-agnostic (orca / cmux / herdr), harness-agnostic (claude / codex /
  pi / copilot / cursor), and works over any tracker the mattpocock skills
  support (GitHub / GitLab / local markdown).
- **`orchestrator-setup/`** — one-time per-repo setup: pick tool/harness/model,
  the review policy, and the project recipe; check + install dependencies; write
  the config.
- **`skill-fork-sync/`** — hold each declared skill dependency at a version you
  control. Fork the upstream repo, pin your fork's default branch to a known-good
  SHA, and when upstream moves, evaluate only the changed skills this repo
  actually consumes — in a throwaway worktree, against the pinned version — before
  you approve a promote. Three modes: `bootstrap`, `sync [<fork>]`, `promote`.
- **`playwright-cli/`** — browser automation (used for UI evidence).

## Concepts

| Term | Meaning |
|------|---------|
| **Tool** | Workspace manager that cuts a worktree, opens a terminal, sends keystrokes — orca / cmux / herdr. |
| **Harness** | Agent CLI in the worker terminal — claude / codex / pi / copilot / cursor. Owns the yolo flag, the `--model` flag, and how effort is expressed. |
| **Model** | Frontier model + **vendor** (anthropic / openai) + **effort**. Never hardcoded — resolved per role. |
| **Effort** | How much the model *thinks*: `low`…`max`, default `high`. Some harnesses clamp the top (codex → `high`). |
| **Role** | The class of job that picks the `(model, effort)` pair — **heavy** (multi-file/migration → strongest @ `xhigh`), **light** (scoped edit → cheaper @ `medium`), **review** (cross-vendor @ `high`). |
| **Cost profile** | A preset of all three role pairs — **conservative** / **balanced** (default) / **max-capability**. Setup asks this instead of interrogating role-by-role. Table + per-MTok prices in [`models.md`](orchestrator/references/models.md). |
| **Worker** | A `(tool, harness, model)` triple on one work item. |
| **Adversarial review** | Optional review by a second worker on a **different-vendor** model (e.g. implement opus-5, review gpt-5.6). Prompted for **coverage**, not self-filtering. |
| **Fork / Pinned SHA** | `/skill-fork-sync`'s version dial: a fork of an upstream skill repo whose default branch sits at a known-good commit, because `claude plugin marketplace add` takes no ref/branch/tag flag. Nothing reaches your sessions until you promote. |

Full glossary: [`orchestrator/CONTEXT.md`](orchestrator/CONTEXT.md). Design
rationale: [`orchestrator/docs/adr/`](orchestrator/docs/adr/).

## Install

Ships as a native [Claude Code plugin](https://code.claude.com/docs/en/plugins),
same model as the mattpocock skills. Install the plugin, then run one setup
command — **setup installs every other dependency for you**.

```
/plugin marketplace add wagnersza/orchestrator-skills
/plugin install orchestrator-skills@wsza
```

or from your shell:

```bash
claude plugin marketplace add wagnersza/orchestrator-skills
claude plugin install orchestrator-skills@wsza
```

That's the only manual install. Everything else — the tracker skills, the tool
and harness CLIs, the MCP — is handled by setup below.

### Dependencies (installed for you by setup)

`/orchestrator-setup` **installs** every missing dependency your chosen config
needs — it runs the install commands itself, pausing only where it genuinely
can't automate (an unpinned installer, a login, or the local-only MCP). Full
catalog with check + install commands:
[`orchestrator/references/requirements.md`](orchestrator/references/requirements.md).

**Always:** git · `mattpocock-skills` plugin (tracker config + ticket
conventions) · [`prompt-improver`](https://github.com/wagnersza/prompt-improver)
plugin (owns all worker/review prompt composition) · `ponytail` plugin ·
`playwright-cli` (ships in this plugin) · `codebase-memory-mcp` · a tracker CLI
(`gh`/`glab`, or none for local markdown).

`prompt-improver` also ships as a plugin now — `claude plugin marketplace add
wagnersza/prompt-improver && claude plugin install prompt-improver@prompt-improver`.
If you already have it as a git clone under `~/.claude/skills/`, that still works
and needs no migration; the skill body is identical either way.

**Your chosen tool:** `orca` (its own CLI; needs `orca open` running) / `cmux` /
`herdr` — fill in `orchestrator/references/tools/<tool>.md` for cmux/herdr first.

**Your chosen harness(es):** the impl harness, plus the review harness if review
is on. Cross-vendor review needs **both** CLIs installed **and** authenticated.

**Per recipe (optional):** `sqlite3` / `node` / `uv` if `db_gate` or `setup_cmd`
need them.

### Vendor authentication

Each harness CLI must be logged in for its vendor; a cross-vendor review setup
needs **both** an Anthropic-authed and an OpenAI-authed harness. Setup runs the
login where it can and tells you the exact command otherwise — it doesn't manage
keys itself.

## Setup (run once per repo — zero touch)

Point Claude at the repo and run:

```
/orchestrator-setup
```

It explores the repo, ensures the tracker config exists (calls
`/setup-matt-pocock-skills` if missing), asks you one choice at a time
(tool → harness → models+effort per role → yolo → review → recipe → repo), then
**installs every missing dependency itself** (plugins, CLIs, MCP) and writes
`docs/agents/orchestrator.md` plus a one-line pointer in `CLAUDE.md`/`AGENTS.md`.
The only time it stops for you is a login or an installer it can't run
unattended — it hands you the exact command.

The config is human-editable markdown — edit it directly later; re-run setup only
to switch tools/harnesses. Worked example:
[`orchestrator/references/examples/fullstack-app.md`](orchestrator/references/examples/fullstack-app.md).

## Use

The orchestrator reads `docs/agents/orchestrator.md` on every action. Trigger
phrases:

| Say | Does |
|-----|------|
| **what next** / what's ready | Resolve the ready queue; present startable items. |
| **implement #N** / start work on X | Spawn a worker for the item (worktree + harness + prompt + checklist). |
| **work on #N, max K** | Batch-spawn every unblocked child of #N, capped at K. |
| **what are the workers doing** | Monitor via checklist files + terminal idle state. |
| **review #N adversarially** | Spawn a cross-vendor reviewer even if review is off in config. |
| **close task #N** / it's done | Advance tracker state, tear down the worktree (after merge). |

`/skill-fork-sync` is invoked with its mode word — `bootstrap` to create and pin
the forks, `sync [<fork>]` to check whether upstream moved and evaluate the delta,
`promote` to advance the pin and refresh the install. The promote decision is
always yours; nothing auto-promotes.

Each worker keeps a file-based **checklist** (`.orchestrator/checklist-<item>.md`,
gitignored) it ticks as it completes each contract step; the orchestrator reads it
to track progress and catch a worker that stalls before opening the PR/MR. This
replaces claude-only `TodoWrite` so it works across every harness.

Merge is always a human step — the orchestrator never auto-merges.

## Layout

```
orchestrator/
  SKILL.md · CONTEXT.md
  docs/adr/                     # design decisions
  references/
    requirements.md            # deps: check + install
    models.md                  # model -> vendor -> prompt-improver profile
    checklist.template.md
    tools/{_operations,orca,cmux,herdr}.md
    harnesses/{claude,codex,pi,copilot,cursor}.md
    examples/fullstack-app.md
orchestrator-setup/
  SKILL.md · orchestrator.template.md
skill-fork-sync/
  SKILL.md
  references/{bootstrap,sync,promote}.md   # one per mode
playwright-cli/
```
