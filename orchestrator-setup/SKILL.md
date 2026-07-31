---
name: orchestrator-setup
description: Zero-touch install + config for the orchestrator skill — installs every missing dependency itself (plugins, CLIs, MCP) and writes the per-project config after asking you to pick the workspace tool (orca/cmux/herdr), harness (claude/codex/pi/copilot/cursor) + model, adversarial-review policy, and project recipe. Run once before orchestrating. Use when the user says "set up the orchestrator", "configure orchestration for this repo", "install and set up the orchestrator", "orchestrator setup", points Claude at a repo to get it orchestration-ready, or the orchestrator reports its config is missing.
disable-model-invocation: true
---

# Orchestrator Setup

Take a repo from nothing to ready-to-orchestrate with **zero human touch beyond
answering the option prompts**. Point Claude at the repo, run this skill, and it
**installs every missing dependency itself** and writes the full config — the
human only picks options (tool / harness / model / review / recipe). No manual
install commands, no hand-edited files.

Same posture as `/setup-matt-pocock-skills`: **explore, ask one thing at a time
(each with a recommended answer), then act.** The difference from a
check-only setup: this one **runs the install commands**, it doesn't just print
them.

The vocabulary (Tool, Harness, Model, Vendor, Yolo mode, Adversarial review,
Project recipe) is defined in the orchestrator skill's `CONTEXT.md` — use those
terms.

## 1. Explore

Don't assume — read the repo first:

- `docs/agents/orchestrator.md` — config already present? (offer to edit, not overwrite)
- `docs/agents/issue-tracker.md` — tracker config present? (mattpocock's `/setup-matt-pocock-skills` writes it)
- `git remote -v` — which host/tracker does this repo point at?
- `CLAUDE.md` / `AGENTS.md` — which exists, and is there an `## Agent skills` block?
- Setup/run signals — `package.json` scripts, a `scripts/run.sh`, `pnpm-workspace.yaml`, a migrations dir (`alembic/`, `migrations/`, `prisma/`) → hints for `setup_cmd`, `run_recipe`, `db_gate`.
- Which harness CLIs are installed (`which claude codex pi copilot cursor-agent`) and which tools (`which orca cmux herdr`).

## 2. Ensure the tracker config exists

The orchestrator reads work-state labels and the tracker CLI from
`docs/agents/issue-tracker.md`. If it's **missing**, call
`/setup-matt-pocock-skills` to create it before continuing — do not define labels
in the orchestrator config. If present, note the tracker + labels and move on.

## 3. Interview — one choice at a time

Take these in order; each leads with a recommendation.

1. **Tool** — orca / cmux / herdr. Recommend whichever exploration found
   installed (default orca). Confirm the matching `references/tools/<tool>.md` is
   filled in; if it's cmux or herdr and still marked "needs verification", tell
   the user its commands must be confirmed against the installed CLI first.
2. **Harness** — the agent CLI that runs in a worker terminal.
3. **Models per role** — *not* one global model. Ask for the `heavy` and `light`
   pair (see the Role table in `references/models.md`), each as
   `(model, effort)`. Recommend `heavy: opus-5 @ xhigh` / `light: sonnet-5 @ medium`
   for a claude harness; the strongest available model at `xhigh` for heavy in
   general. Then:
   - Reject a model not in the registry (frontier only).
   - Warn if the harness can't pin the chosen model
     (`references/harnesses/<h>.md` model-id map incomplete or, for `pi`, the model
     absent from `pi --list-models` on this machine).
   - **Check the harness's effort ceiling** from its reference and say so plainly if
     a chosen effort gets clamped — e.g. "`codex` tops out at `high`, so `xhigh`
     becomes `high`". Offer the alternative harness rather than writing a config
     that lies.
   - Offer a **flat single-model** config (`model:`/`effort:`) if the user doesn't
     want per-role routing; note it costs more on trivial items or under-thinks on
     hard ones, depending which way it's set.
4. **Yolo** — on (required). State the actual flag from the harness reference so
   the user sees what "unattended" means for their harness.
5. **Adversarial review** — off by default. If on, ask for `models.review`
   (model + effort, default effort `high`) and **assert its vendor differs** from
   the impl roles' (look both up in `references/models.md`); refuse a same-vendor
   pair. Confirm the round cap (default 3).
6. **Project recipe** — `setup_cmd`, `run_recipe` + `ports`, `db_gate` (blank if
   no database), `evidence` bar. Pre-fill from what exploration found and let the
   user correct. Offer to clone `references/examples/fullstack-app.md` as a
   starting point if the repo resembles it.
7. **repo** — the absolute path to the main checkout (stays on the default
   branch).

## 4. Install the dependencies (zero-touch)

Now that the choices are made, the required dependency set is known. Check
**exactly** what this config needs, then **install every missing one yourself** —
run the install command from [`references/requirements.md`](../orchestrator/references/requirements.md)
(the full catalog with check + install commands). Don't just print commands for
the user to run.

Scope — only the chosen pieces apply:

- **Always:** git, the `mattpocock-skills` plugin, the `ponytail` plugin, the
  `prompt-improver` skill (all worker/review prompt composition runs through it),
  the `playwright-cli` skill (ships with this plugin — nothing to install),
  `codebase-memory-mcp`, and the tracker CLI the tracker config names
  (`gh` / `glab` / none for local).
- **tool:** the one in config (`orca` / `cmux` / `herdr`).
- **harness(es):** the impl harness, **and** the review harness if
  `review.enabled` — a cross-vendor review setup (e.g. impl `claude`/opus-5,
  review `codex`/gpt-5.6) needs **both** CLIs installed and authenticated.
- **optional, per recipe:** a DB CLI like `sqlite3` (if `db_gate` set), node/npm
  or uv (if `setup_cmd` needs them).

### Install loop

For each needed dep, run its check command. **If present, skip.** If missing,
install it by running the command from `requirements.md`:

- **Plugins** — `claude plugin marketplace add <slug> && claude plugin install <name>@<marketplace>` (mattpocock, ponytail). Verified shell commands.
- **Skills** — `prompt-improver` is a plain git clone into `~/.claude/skills/` (see `requirements.md`); it's auto-discovered next session, so mention a restart is needed before the first spawn.
- **CLIs** — the documented installer (`brew install gh`/`glab`, `npm install -g @anthropic-ai/claude-code`, etc.).
- **MCP** — `claude mcp add <name> <command/url>` once the server binary/endpoint is known.

**Only pause for a human when you genuinely can't proceed automatically:**

- An install command is marked **(verify)** in `requirements.md` (tool/harness
  installers not pinned) — show the doc link and ask the user to run/confirm it.
- **`codebase-memory-mcp`** has no public package resolved. Detect a local binary
  (e.g. `~/.local/bin/codebase-memory-mcp`); if found, register it with
  `claude mcp add codebase-memory-mcp <path>`. If not found, tell the user it must
  be installed manually (point at its docs), then `claude mcp add`.
- A CLI needs **authentication** (vendor login) — run its login if interactive is
  possible, else tell the user the exact command (`claude` login, `codex` auth,
  `gh auth login`, `glab auth login`).

Anything a plugin install pulls in that needs the session reloaded to take effect
(new skills), note it — the user may need to restart the agent once.

After the loop, re-run the checks and present a short table: each needed dep, now
**present** / **installed** / **needs the user** (with the exact remaining
action). Don't write config that names a tool/harness still absent — flag it. Also
confirm the tool's reference file is filled in (cmux/herdr ship marked "needs
verification"); if not, that's a "needs the user" item.

## 5. Confirm and write

Show a draft of the filled-in `docs/agents/orchestrator.md` (from
[orchestrator.template.md](orchestrator.template.md)) and let the user edit before
writing. Then:

- Write `docs/agents/orchestrator.md`.
- Add/update a one-line pointer under `## Agent skills` in whichever of
  `CLAUDE.md` / `AGENTS.md` exists (edit the existing one; never create the other;
  never duplicate the block):

  ```markdown
  ### Orchestrator

  Runs <harness> workers via <tool> — <heavy.model>@<heavy.effort> for heavy items, <light.model>@<light.effort> for light[, cross-vendor review with <review.model>]. See `docs/agents/orchestrator.md`.
  ```

- Ensure `.orchestrator/` is gitignored (the worker checklist files live there):
  add `.orchestrator/` to the repo's `.gitignore` if absent.

## 6. Done

Tell the user setup is complete and that the orchestrator will now read
`docs/agents/orchestrator.md`. They can edit it directly later; re-run this skill
only to switch tools/harnesses or start over.
