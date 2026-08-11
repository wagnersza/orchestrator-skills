---
name: orchestrator-setup
description: Zero-touch install, update, and config for the orchestrator skill — always updates the plugin and every dependency skill to the latest version first, then either reconciles an existing config (the default when one exists) or installs every missing dependency and writes a fresh per-project config after asking you to pick the workspace tool (orca/cmux/herdr), harness (claude/codex/pi/copilot/cursor) + models per role, adversarial-review policy, and project recipe. Use when the user says "set up the orchestrator", "configure orchestration for this repo", "orchestrator setup", "update the orchestrator", "update the orchestrator skills/plugin", "get the latest orchestrator", "re-run orchestrator setup", points Claude at a repo to get it orchestration-ready, or the orchestrator reports its config is missing or stale.
disable-model-invocation: true
---

# Orchestrator Setup

Take a repo from nothing to ready-to-orchestrate with **zero human touch beyond
answering the option prompts**. Point Claude at the repo, run this skill, and it
**installs every missing dependency itself** and writes the full config — the
human only picks options (tool / harness / model / review / recipe). No manual
install commands, no hand-edited files.

Two modes, decided in step 0:

- **First setup** (no `docs/agents/orchestrator.md`) — the full flow, steps 1–6.
- **Update** (config already there) — refresh the plugin and every dependency
  skill, reconcile the existing config against the new version, and change
  nothing the user didn't ask for. This is the **default** on any re-run.

Either way, step 0 runs first and updates everything.

Same posture as `/setup-matt-pocock-skills`: **explore, ask one thing at a time
(each with a recommended answer), then act.** The difference from a
check-only setup: this one **runs the install commands**, it doesn't just print
them.

The vocabulary (Tool, Harness, Model, Vendor, Yolo mode, Adversarial review,
Project recipe) is defined in the orchestrator skill's `CONTEXT.md` — use those
terms.

## 0. Update everything, then pick a mode

**Always run this step first, on every invocation — first setup or re-run.**

### 0a. Update the plugin and every dependency skill

The skill body you are reading, and the reference files it sends you to, are the
**cached** copy of whatever plugin version is installed. A stale cache silently
routes to deleted files and misses whole steps, so refresh before doing anything
else:

```bash
claude plugin list                        # FIRST — read the exact ids + versions
claude plugin marketplace update          # refresh every marketplace source
# then each plugin, by its FULL plugin@marketplace id from the list above
claude plugin update orchestrator-skills@wsza
claude plugin update mattpocock-skills@mattpocock
claude plugin update ponytail@ponytail
# prompt-improver: read the SUFFIX from `claude plugin list` and pick ONE.
#   @prompt-improver -> claude plugin update prompt-improver@prompt-improver
#   @skills-dir      -> git -C ~/.claude/skills/prompt-improver pull --ff-only
npx skills update simple-english -g -y   # -p instead of -g for a project install
```

**`simple-english` never takes `claude plugin update`.** It installs through the
`skills` CLI, not a Claude plugin marketplace. So it never appears in `claude
plugin list` — the same trap `@skills-dir` documents above for `prompt-improver`.
Use `npx skills update simple-english -g -y` instead. It prints `All global
skills are up to date` when nothing moved. See `requirements.md`.

**The `plugin@marketplace` form is required.** A bare name fails with
`Plugin "<name>" not found` and **exits 1** — so read the ids from
`claude plugin list` rather than assuming the marketplace name (this plugin is
`orchestrator-skills@wsza`, not `@orchestrator-skills`). Skip any dependency that
isn't installed yet; step 4 installs those.

**`prompt-improver`: read the marketplace suffix, then pick the update command.**
It shipped as a git clone and is now also a plugin, and a clone under
`~/.claude/skills/` is auto-registered as **`prompt-improver@skills-dir`** — so it
shows up in `claude plugin list` while still being a clone. `claude plugin update
prompt-improver@prompt-improver` **fails on it** (`Plugin not found`, exit 1); pull
the clone instead. `@prompt-improver` is the real plugin and takes `plugin update`.
See the shape table in `requirements.md`. **Don't migrate a working clone** — the
skill body is identical and the orchestrator invokes the skill, not a path.

Report the before/after version for each. `claude plugin list` gives the installed
version directly; for a git clone use
`git -C ~/.claude/skills/<name> log --oneline -1`.

**A plugin update needs a session restart to take effect** — the CLI says so, and
it means the *currently loaded* skill body is still the old one. So:

- **If `orchestrator-skills` actually changed version:** stop here. Tell the user
  the new version, that this session is still running the old skill body, and ask
  them to restart and re-run `/orchestrator-setup`. Don't carry on with stale
  instructions and don't try to work around it by reading the new files directly —
  the loaded body is what drives the flow.
- **If nothing changed:** say so in one line and continue.

**Detect a stale body.** The cache keeps every version side by side, and the "Base
directory for this skill" line at the top of this skill names the one actually
loaded. Compare it against the newest:

```bash
ls -1v ~/.claude/plugins/cache/wsza/orchestrator-skills/ | tail -1   # newest cached
```

If that doesn't match the version in your base directory path, you are running a
stale body — stop and restart, as above. This is the common case right after an
update lands, and it's silent: the old body reads fine, it just points at
reference files that moved.

### 0b. Ask what the user wants — update, or full setup

Once versions are current, **check whether `docs/agents/orchestrator.md` already
exists** and branch:

**Config exists → default to update-only.** Re-running this skill on a configured
repo is an **update**, not a re-setup: the point is to refresh the plugin and
skills and reconcile the existing config, **not** to re-interview or overwrite
choices the user already made. Confirm before doing anything more:

> Config found at `docs/agents/orchestrator.md` (orca / claude / opus-5+sonnet-5).
> Plugin and skills are now up to date. Update only, or change the setup?
>
> 1. **Update only** (recommended) — keep the config as-is; just reconcile it
>    against the new version and report anything that needs attention.
> 2. **Change some choices** — say which (tool / harness / models / review /
>    recipe); everything else stays.
> 3. **Full re-setup** — re-interview from scratch and overwrite the config.

**Default to 1.** Only run the full interview (step 3) if the user explicitly asks
for option 3 or clearly says they want to change the setup. If they asked for
something ambiguous ("run setup again", "update the orchestrator"), that means
option 1 — say that's what you're doing rather than asking a second time.

**No config → full setup.** Announce that and run steps 1–6 normally; there's
nothing to preserve.

### 0c. Update-only path

For option 1, skip the interview entirely. Do this instead:

1. **Re-run the dependency checks** (step 4's check commands only) and install
   anything now missing or newly required by this version. This includes
   `simple-english`, and `playwright-cli` plus its browsers where step 4's recipe
   gate applies. A repo configured before these dependencies existed has no
   install of them, so this path must install them for an existing user, not
   merely report them missing.
2. **Reconcile the existing config against the current template**
   ([orchestrator.template.md](orchestrator.template.md)) and
   `references/models.md` — report, don't silently rewrite:
   - **Fields the new version added** that the config lacks (e.g. a config still
     carrying a flat `model:` when roles now exist). Offer to add them with
     defaults.
   - **Values now invalid** — a model no longer in the registry, an effort the
     chosen harness can't reach, a same-vendor review pair.
   - **Dead references** — a `references/` path the config or `CLAUDE.md` points at
     that this version deleted or renamed.
   - **A missing `## Project board` section** in `docs/agents/issue-tracker.md` on a
     GitHub repo that now has a board — run step 2a and offer to add it. If the
     section is there, re-resolve its ids and report any mismatch.
3. **If the orchestrator terminal title is not set yet, set it** (step 5a). A repo
   configured before the tick existed has no titled terminal, so this path is the only
   place an existing user gets one.
4. **Apply only what the user approves**, one edit at a time. An update must never
   drop a hand-edited recipe field or flip a review policy on its own.
5. **Report** as a short table: what updated, what the config needs, what's fine.
   Then stop — don't continue into steps 1–3.

## 1. Explore

Don't assume — read the repo first:

- `docs/agents/orchestrator.md` — config already present? (step 0b already asked; a
  present config means update-only unless the user chose otherwise — never
  overwrite)
- `docs/agents/issue-tracker.md` — tracker config present? (mattpocock's `/setup-matt-pocock-skills` writes it) Does it already carry a `## Project board` section?
- `git remote -v` — which host/tracker does this repo point at?
- `CLAUDE.md` / `AGENTS.md` — which exists, and is there an `## Agent skills` block?
- Setup/run signals — `package.json` scripts, a `scripts/run.sh`, `pnpm-workspace.yaml`, a migrations dir (`alembic/`, `migrations/`, `prisma/`) → hints for `setup_cmd`, `run_recipe`, `db_gate`.
- Which harness CLIs are installed (`which claude codex pi copilot cursor-agent`) and which tools (`which orca cmux herdr`).

## 2. Ensure the tracker config exists

The orchestrator reads work-state labels and the tracker CLI from
`docs/agents/issue-tracker.md`. If it's **missing**, call
`/setup-matt-pocock-skills` to create it before continuing — do not define labels
in the orchestrator config. If present, note the tracker + labels and move on.

### 2a. Detect a project board and resolve its ids

The orchestrator writes a card's `Status` at every label transition, deriving it from
the labels (`orchestrator/docs/adr/0009-labels-drive-board-status.md`). It needs the
real field and option ids to do that, and those are **per-repo data**, so resolve
them here and write them into `issue-tracker.md` — never into the orchestrator
config, same split as the labels.

Only for a GitHub tracker. Look for a board owned by the repo's owner:

```bash
gh project list --owner <owner> --format json --jq '.projects[] | {number, title, id}'
```

Ask which project this repo's issues live on (a personal account often has several
untitled ones — show `number` + `title` and let the user pick, or say **none**). Then
resolve the `Status` field and every option id from the live board:

```bash
gh project field-list <number> --owner <owner> --format json \
  --jq '.fields[] | select(.name=="Status")'
```

Write a `## Project board` section into `docs/agents/issue-tracker.md` carrying: the
`owner` + project `number`, the project id, the `Status` field id, the
option-name→id map **as resolved** (never the ids from this skill's examples — they
are one board's), the derivation table, and the two `gh` calls (resolve an issue's
item id, then `item-edit --single-select-option-id`). Then verify the token has the
scope — `gh auth status` should list `project`; if not, run
`gh auth refresh -s project`.

**Handle these three cases explicitly, and say which one applies:**

- **No board, or the user says none** — leave the section out. Every board write
  becomes a no-op and the orchestrator runs on labels alone. Say so in one line;
  this is a supported configuration, not a gap.
- **A board with no `Status` field, or with different option names** — write the
  section with whatever options exist and map the derivation table onto them by
  meaning (a board with only `Todo | In Progress | Done` folds `Backlog`/`Ready` onto
  `Todo` and both work states onto `In Progress`). Say which columns got folded.
- **The section already exists** (a re-run) — this is the update path (step 0c):
  re-resolve the ids and **report** a mismatch, don't silently rewrite. Ids change
  when a field is recreated, and a stale one fails every write.

## 3. Interview — one choice at a time

Take these in order; each leads with a recommendation.

1. **Tool** — orca / cmux / herdr. Recommend whichever exploration found
   installed (default orca). Confirm the matching `references/tools/<tool>.md` is
   filled in; if it's cmux or herdr and still marked "needs verification", tell
   the user its commands must be confirmed against the installed CLI first.
2. **Harness** — the agent CLI that runs in a worker terminal.
3. **Models per role — lead with a cost profile.** Don't open with a
   role-by-role interrogation. Offer the three presets from the **Cost profiles**
   table in [`references/models.md`](../orchestrator/references/models.md) and let
   the user pick one, then show the resolved pairs:

   | Profile | heavy | light | review | Relative cost |
   |---------|-------|-------|--------|---------------|
   | **conservative** | `opus-5` @ `medium` | `sonnet-5` @ `low` | `gpt-5.6-terra` @ `medium` | ~1× |
   | **balanced** (recommended) | `opus-5` @ `high` | `sonnet-5` @ `medium` | `gpt-5.6-terra` @ `high` | ~2–3× |
   | **max-capability** | `opus-5` @ `xhigh` | `opus-5` @ `high` | `gpt-5.6-sol` @ `high` | ~5–8× |

   Recommend **balanced**. Say the multiplier is an ordering, not a budget figure
   — effort changes thinking tokens per item, so the spread is workload-dependent.
   Name the one non-obvious trade: **conservative can cost more** when a
   `light` worker at `low` under-thinks, because a failed round trip plus a
   re-spawn a rung up exceeds what the cheap effort saved.

   The user may override any single pair after picking (e.g. "balanced, but heavy
   at `xhigh`") — that's expected; profiles are a starting point. Then, whichever
   way the pairs were reached:
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
5. **Adversarial review** — off by default. If on, the chosen profile already
   supplies `models.review`; just confirm it rather than re-asking. Either way
   **assert its vendor differs** from the impl roles' (look both up in
   `references/models.md`) and refuse a same-vendor pair. Confirm the round cap
   (default 3). Mention the cost shape: review roughly **doubles** the per-item
   spend when it runs, and each fix round steps the impl worker up a rung — so on
   a `conservative` profile, a review loop converges toward `balanced` pricing.
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
  `prompt-improver` plugin (all worker/review prompt composition runs through it —
  an existing git clone of it also counts as satisfied), the `simple-english`
  skill (owns all writing rules for prose deliverables), `codebase-memory-mcp`, and
  the tracker CLI the tracker config names (`gh` / `glab` / none for local).
- **browser surface — `playwright-cli` and `playwright browsers`, the catalog's two
  always-required rows, gated on the recipe.** The **skill body** under
  `playwright-cli/` ships with this plugin. The **binary does not**. The browsers it
  drives are a second requirement, because a machine can have the CLI and no
  browsers. The gate is the project recipe naming a **browser-evidence need** — a
  non-blank `run_recipe`, or an `evidence` bar that asks for UI proof. If the recipe
  names one, check and install both rows. If it names neither, install nothing and
  say so in the table. A recipe with no browser-evidence need is a supported
  configuration, not a gap. This is the same gate the orchestrator's preflight uses,
  so the two cannot disagree about when the surface is required
  ([`../orchestrator/CONTEXT.md`](../orchestrator/CONTEXT.md), **Browser surface**;
  [ADR 0012](../orchestrator/docs/adr/0012-playwright-cli-is-the-only-browser-surface.md)).
- **tool:** the one in config (`orca` / `cmux` / `herdr`).
- **harness(es):** the impl harness, **and** the review harness if
  `review.enabled` — a cross-vendor review setup (e.g. impl `claude`/opus-5,
  review `codex`/gpt-5.6) needs **both** CLIs installed and authenticated.
- **optional, per recipe:** a DB CLI like `sqlite3` (if `db_gate` set), node/npm
  or uv (if `setup_cmd` needs them).

### Install loop

For each needed dep, run its check command. **If present, it was already brought up
to date in step 0a** — skip it. The browser surface is the one exception, because
step 0a cannot apply the recipe gate: see its bullet below. If missing, install it
by running the command from `requirements.md`:

- **Plugins** — `claude plugin marketplace add <slug> && claude plugin install <name>@<marketplace>` (mattpocock, ponytail, prompt-improver). Verified shell commands. A plugin auto-loads next session, so mention a restart (or `/reload-plugins`) is needed before the first spawn.
- **`prompt-improver` specifically** — install as a plugin (see `requirements.md`). If exploration found an existing clone at `~/.claude/skills/prompt-improver`, **it's already satisfied** — don't install the plugin on top, which would leave two copies shadowing each other. Report it as present.
- **`simple-english` specifically** — run `npx skills add AminBlg/SimpleEnglish
  --global --all` (the command `requirements.md` verified). It needs `node`/`npx`
  and network access. If the check already found any of the four install shapes
  `requirements.md` lists, skip the install and report it present. If `npx` is not
  on the machine, or the CLI cannot reach the network, or the install otherwise
  cannot finish unattended, fall back to the manual path in `requirements.md`
  (`git clone https://github.com/AminBlg/SimpleEnglish`, then copy its
  `skills/simple-english` directory to `~/.claude/skills/simple-english`). If that
  fallback also cannot run unattended, report it as **needs the user**, with that
  clone-and-copy command as the exact remaining action. Never write a config that
  names `simple-english` present while it is still absent.
- **`playwright-cli` specifically — two steps, in order, and only when the gate
  above applies.** Run the CLI check from `requirements.md`. If the CLI is missing,
  install it with that row's command. Then run the **browser** check from the same
  block, as a **separate step**. If the browsers are missing, install them with that
  row's command. A machine can have the CLI and no browsers, so a green CLI check is
  not permission to skip the second step. Take both commands from
  `requirements.md` — the CLI row, the browsers row, and the check block — rather
  than typing them here. The steps, the verification that a browser really opens,
  the update command, and the failure modes are in
  [`../playwright-cli/references/installation.md`](../playwright-cli/references/installation.md).
  **A present CLI was not brought up to date in step 0a**, unlike the plugins —
  step 0a runs before the recipe is known, so it cannot apply this gate. Update a
  present CLI here, with the line the update block in `requirements.md` already
  carries for it.
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
- **`playwright-cli` cannot install because node is absent, or because the install
  cannot reach the network.** Both are genuine, because neither can finish
  unattended and a node install can ask for a password. Stop, report the row as
  **needs the user**, and give the exact remaining command from `requirements.md`.
  Point at the **No node** failure mode in
  [`../playwright-cli/references/installation.md`](../playwright-cli/references/installation.md).
  A **missing CLI on a machine that has node is not this case** — install it and
  move on.

Anything a plugin install pulls in that needs the session reloaded to take effect
(new skills), note it — the user may need to restart the agent once.

After the loop, re-run the checks and present a short table: each needed dep, now
**present** / **installed** / **needs the user** (with the exact remaining
action). Don't write config that names a tool/harness still absent — flag it. Also
confirm the tool's reference file is filled in (cmux/herdr ship marked "needs
verification"); if not, that's a "needs the user" item. Include a `simple-english`
row: **present** if a check hit already covered it, **installed** if the `npx
skills add` command above ran, or **needs the user** with the clone-and-copy
fallback command as the exact remaining action if it could not run unattended.

Give the browser surface **two rows, never one** — `playwright-cli` and the
playwright browsers — on the same present / installed / needs-the-user terms. Then a
machine with the CLI and no browsers is described as what it is. A "needs the user"
row on either one carries the exact remaining command from `requirements.md`. If the
recipe names no browser-evidence need, both rows read **not needed by this recipe**
rather than a gap. Nothing was checked, and nothing is missing.

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

### 5a. Title the orchestrator terminal

Each live work item gets an **Item automation**. Its tick wakes the orchestrator session
with one line to that session's terminal, found **by title**. An auto-generated title
changes, so the wake target must be a fixed literal: **`orchestrator`**. Set it once here
and it survives a restart of the session
([`../orchestrator/SKILL.md`](../orchestrator/SKILL.md), *Start the tick*;
[ADR 0022](../orchestrator/docs/adr/0022-item-automation-replaces-the-blocking-watch.md)).

Only for a tool whose reference file supports operation 11
([`../orchestrator/references/tools/_operations.md`](../orchestrator/references/tools/_operations.md)).
On `orca`:

```bash
orca terminal list --worktree active --json          # find this session's handle
orca terminal rename --terminal <handle> --title "orchestrator"
```

More than one terminal can sit in the active worktree. So **confirm which handle is this
session's** before you rename it. A title on the wrong terminal sends every wake to a shell
nobody reads. Where the tool records operation 11 as unsupported, there is no tick at all.
Skip this step and say so in one line. Where the title cannot be set, say that the wake
falls back to a comment on the work item. That is a supported configuration and not a gap.

## 6. Done

Tell the user setup is complete and that the orchestrator will now read
`docs/agents/orchestrator.md`. They can edit it directly later.

**Re-running is how you update.** A later `/orchestrator-setup` refreshes the
plugin and every dependency skill, then reconciles the config without
re-interviewing — it only starts over if the user explicitly asks for a full
re-setup (step 0b). Mention this, so a version bump doesn't look like it needs a
manual reinstall.
