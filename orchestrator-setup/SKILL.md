---
name: orchestrator-setup
description: Zero-touch install, update, and config for the orchestrator skill — always updates the plugin and every dependency skill to the latest version first, then either reconciles an existing config (the default when one exists) or installs every missing dependency and writes a fresh per-project config after asking you to pick the workspace tool (orca/cmux/herdr), harness (claude/codex/pi/copilot/cursor) + models per role, adversarial-review policy, project recipe, and gate profile. Use when the user says "set up the orchestrator", "configure orchestration for this repo", "orchestrator setup", "update the orchestrator", "update the orchestrator skills/plugin", "get the latest orchestrator", "re-run orchestrator setup", points Claude at a repo to get it orchestration-ready, or the orchestrator reports its config is missing or stale.
disable-model-invocation: true
---

# Orchestrator Setup

Take a repo from nothing to ready-to-orchestrate with **zero human touch beyond
answering the option prompts**. Point Claude at the repo, run this skill, and it
**installs every missing dependency itself** and writes the full config — the
human only picks options (tool / harness / model / review / recipe / gate profile). No manual
install commands, no hand-edited files.

Two modes, decided in step 0:

- **First setup** (no `docs/agents/orchestrator.md`) — the full flow, steps 1–6.
- **Update** (config already there) — refresh the plugin and every dependency
  skill, put the routed skills back in reach, reconcile the existing config against
  the new version, and change nothing the user didn't ask for. This is the
  **default** on any re-run.

Either way, step 0 runs first and updates everything.

Same posture as `/setup-matt-pocock-skills`: **explore, ask one thing at a time
(each with a recommended answer), then act.** The difference from a
check-only setup: this one **runs the install commands**, it doesn't just print
them.

The vocabulary (Tool, Harness, Model, Vendor, Yolo mode, Adversarial review,
Project recipe, Gate, Layer) is defined in the orchestrator skill's `CONTEXT.md` —
use those terms.

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
claude plugin update mattpocock-skills@mattpocock   # or @claude-plugins-official — read the id from the list
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

### 0b. Unblock the routed skills

**Always run this step, immediately after 0a, on every invocation.**

One line in the frontmatter of a skill puts that skill out of reach:
`disable-model-invocation: true` removes it from the skill list of a session. No model
enters that skill. So a worker prompt that holds `Run /implement.` is plain prose, and the
worker starts cold while the run looks correct. **Nothing at spawn time catches this**, so
this step is the only guard
([ADR 0031](../orchestrator/docs/adr/0031-setup-unblocks-the-routed-skills.md)).

The flag belongs to the upstream skill, and **step 0a puts it back** each time the version
moves. So the strip is not a one-time repair. It runs after every update, which is why it
lives here.

Strip the line from the skills the routing table
([`../orchestrator/references/skill-routing.md`](../orchestrator/references/skill-routing.md))
names, and from those alone. The names come from the `Skill` column of a table row, so no
list of names sits here to go stale. A skill that file names in its prose alone keeps its
flag, and this setup skill is one of those.

Set `ROUTING` to the absolute path of that table. Resolve it from the **Base directory for
this skill** line at the top of this skill:

```bash
ROUTING="<base directory>/../orchestrator/references/skill-routing.md"
for S in $(grep -oE '\| `/[a-z-]+` \|' "$ROUTING" | tr -d '`|/ ' | sort -u); do
  find ~/.claude/plugins/cache ~/.claude/plugins/marketplaces ~/.claude/skills .claude/skills \
       -path "*/$S/SKILL.md" -exec grep -l 'disable-model-invocation: *true' {} + 2>/dev/null \
    | while read -r F; do
        perl -i -ne 'print unless /^disable-model-invocation: *true/' "$F"
        echo "unblocked $S: $F"
      done
done
```

Report every line the loop printed. Where it printed none, say in one line that each
routed skill is already reachable.

Two limits, and both need a word in the report:

- **The loop writes no `description`.** A skill that carries the flag and no
  `description` is still out of reach after the strip. Name that skill and add nothing,
  because a description invented here routes the model wrong.
- **The strip does not reach this session.** The edited body loads on the next start, the
  same restart rule 0a states. So where a file changed, this session still cannot route
  that skill. Say so, and say which one.

### 0c. Ask what the user wants — update, or full setup

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
>    recipe / gate profile); everything else stays.
> 3. **Full re-setup** — re-interview from scratch and overwrite the config.

**Default to 1.** Only run the full interview (step 3) if the user explicitly asks
for option 3 or clearly says they want to change the setup. If they asked for
something ambiguous ("run setup again", "update the orchestrator"), that means
option 1 — say that's what you're doing rather than asking a second time.

**No config → full setup.** Announce that and run steps 1–6 normally; there's
nothing to preserve.

### 0d. Update-only path

For option 1, skip the interview entirely. Do this instead:

1. **Re-run the dependency checks** (step 4's check commands only) and install
   anything now missing or newly required by this version. This includes
   `simple-english`, and `playwright-cli` plus its browsers where step 4's recipe
   gate applies. A repo configured before these dependencies existed has no
   install of them, so this path must install them for an existing user, not
   merely report them missing. **It includes the gate tools of each language
   family too, at the `strict` default.** Run step 1a first: this path asks no
   interview question, so nothing else names a family.
2. **Reconcile the existing config against the current template**
   ([orchestrator.template.md](orchestrator.template.md)) and
   `references/models.md` — report, don't silently rewrite:
   - **Fields the new version added** that the config lacks (e.g. a config still
     carrying a flat `model:` when roles now exist). Offer to add them with
     defaults.
   - **A missing `gates:` block**, on a config written before the gates existed.
     Offer to add it with the defaults of the template, plus the families step 1a
     found and `profile: strict`. **Ask no interview question here.** So a
     maintainer who answered the questions last month keeps every answer, and
     still gains the block. Where the user takes the block, run step 5a too, so the
     repo gains the gate files with it. Where the user declines it, the gate tools
     from point 1 stay installed and no layer command reaches a checklist.
   - **Values now invalid** — a model no longer in the registry, an effort the
     chosen harness can't reach, a same-vendor review pair.
   - **Dead references** — a `references/` path the config or `CLAUDE.md` points at
     that this version deleted or renamed.
   - **A missing `## Project board` section** in `docs/agents/issue-tracker.md` on a
     GitHub repo that now has a board — run step 2a and offer to add it. If the
     section is there, read the two coordinates back and report any mismatch. **Also
     read the built-in workflow again**, because a maintainer can turn it off.
3. **Run step 5b and report whether the hook plane is live.** A plugin update is
   exactly when a fresh `hooks/hooks.json` arrives, and this path is the only place an
   existing user reads that. The step installs nothing.
   **Then run step 5c**, the gate smoke run. A plane that just went live denies a push
   against a gate command that does not exist. So an existing user learns that here,
   before the next push.
   **Then run step 5d**, the repo-wide queue schedule. A repo configured before that
   schedule existed has none, so nothing starts work by itself there. Read the schedule
   list back first: where `orchestrator-queue` already exists, report it and create no
   second one.
4. **Apply only what the user approves**, one edit at a time. An update must never
   drop a hand-edited recipe field or flip a review policy on its own.
5. **Report** as a short table: what updated, what the config needs, what's fine.
   Then stop — don't continue into steps 1–3.

## 1. Explore

Don't assume — read the repo first:

- `docs/agents/orchestrator.md` — config already present? (step 0c already asked; a
  present config means update-only unless the user chose otherwise — never
  overwrite)
- `docs/agents/issue-tracker.md` — tracker config present? (mattpocock's `/setup-matt-pocock-skills` writes it) Does it already carry a `## Project board` section?
- `git remote -v` — which host/tracker does this repo point at?
- `CLAUDE.md` / `AGENTS.md` — which exists, and is there an `## Agent skills` block?
- Setup/run signals — `package.json` scripts, a `scripts/run.sh`, `pnpm-workspace.yaml`, a migrations dir (`alembic/`, `migrations/`, `prisma/`) → hints for `setup_cmd`, `run_recipe`, `db_gate`.
- Which harness CLIs are installed (`which claude codex pi copilot cursor-agent`) and which tools (`which orca cmux herdr`).

### 1a. Detect the language family

A language family is one column of the gate matrix in
[`references/quality-gates.md`](../orchestrator/references/quality-gates.md). Each column
names the tools that family needs. The Python and TypeScript columns have landed.

Read the repo root for a marker file of each landed family:

```bash
for M in pyproject.toml setup.py setup.cfg requirements.txt; do
  [ -f "$M" ] && echo "python: $M"
done
find . -maxdepth 4 -name tsconfig.json -not -path '*/node_modules/*' -print | \
  while read -r F; do echo "typescript: $F"; done
```

**A marker turns the family on.** Report every marker the loop printed, and name the
family beside it. More than one marker of the same family is still one family. So several
`tsconfig.json` files in a monorepo turn `typescript` on once, and never several times.
Each family you turn on goes to `gates.langs` in the config
([orchestrator.template.md](orchestrator.template.md)), beside any family an earlier marker
already turned on. A repo that hits both markers gets `[python, typescript]`. The value is
the family name, so a repo with only a Python marker gets `python`.

**No marker turns no family on.** Leave `gates.langs` blank, say so in one line, and
continue with setup. A repo with no marker file is a supported configuration, the same as
a blank recipe field. **Never stop setup here.**

**The Go, Terraform and Kubernetes families each wait for a work item of their own.** No
column names their tools yet. So this step turns none of them on, even where a marker file
for one of them sits in the repo. Name the marker you saw, and say that the column has not
landed.

**This condition is also the install condition.** Step 4 requires a family's gate tools
where that family is on, and nowhere else. One condition, read in two steps, so the two
cannot disagree about when a tool is required. The **Browser surface** gate in step 4 has
the same shape. Requirements in that catalog are conditional on config already
([`references/requirements.md`](../orchestrator/references/requirements.md)), and this gate
obeys that rule.

## 2. Ensure the tracker config exists

The orchestrator reads work-state labels and the tracker CLI from
`docs/agents/issue-tracker.md`. If it's **missing**, call
`/setup-matt-pocock-skills` to create it before continuing — do not define labels
in the orchestrator config. If present, note the tracker + labels and move on.

**Then point that file at the verified reads.** Append one line to
`docs/agents/issue-tracker.md` that names
[`references/tracker-reads.md`](../orchestrator/references/tracker-reads.md) as the home
of every read the flows make, with the command for `gh` and the command for `glab`.
**Write no read command into the per-project file.** That file holds per-repo data: the
CLI name, the host, the label vocabulary and the board coordinates. A read command is
the same for every repo, so a copy in each one drifts from the maintained version
([ADR 0039](../orchestrator/docs/adr/0039-a-tracker-read-has-a-verified-command-in-the-skill.md)).
On a re-run (step 0d), leave an existing pointer alone.

### 2a. Detect a project board and read its two coordinates

**The board is an input, and nothing writes it** (`orchestrator/docs/adr/0054-the-board-is-an-input-not-a-mirror.md`).
One question is asked of it: is this item's card in the start column. So this step resolves
two coordinates and no id. Both are **per-repo data**, so write them into
`issue-tracker.md` and never into the orchestrator config, the same split as the labels.

Only for a GitHub tracker. Look for a board owned by the repo's owner:

```bash
gh project list --owner <owner> --format json --jq '.projects[] | {number, title, id}'
```

Ask which project this repo's issues live on (a personal account often has several
untitled ones — show `number` + `title` and let the user pick, or say **none**). Then read
the column names off the live board, and ask which one means "an agent can start this
now":

```bash
gh project field-list <number> --owner <owner> --format json \
  --jq '.fields[] | select(.name=="Status")'
```

Write a `## Project board` section into `docs/agents/issue-tracker.md` carrying: the
`owner` + project `number`, the name of the start column, and the one `gh project
item-list` read. **Write no `Status` field id, no option id and no derivation table.**
Each one existed to write a card, and nothing writes a card. Then verify the token has
the scope — `gh auth status` should list `read:project`; if not, run
`gh auth refresh -s read:project`.

**Then read the board's built-in workflows, and report the one that matters.** Nothing
writes the board, so the built-in **item closed to Done** workflow is the only thing left
that moves a card to `Done`:

```bash
gh api graphql -f owner=<owner> -F number=<number> -f query='
  query($owner: String!, $number: Int!) {
    user(login: $owner) { projectV2(number: $number) {
      workflows(first: 20) { nodes { name enabled } } } } }'
```

**Say in one line whether it is on.** Where it is off, say plainly that the maintainer
turns it on in the project settings, and that **this step cannot do it, because the switch
is not in the API.** Do not try. An `organization` board answers the same query under
`organization(login:)` instead of `user(login:)`, and a read that fails is one line to the
user rather than a stop: the workflow is the maintainer's to set either way.

**Handle these three cases explicitly, and say which one applies:**

- **No board, or the user says none** — leave the section out. The board read then asks
  nothing and the orchestrator runs on labels alone. Say so in one line; this is a
  supported configuration, not a gap.
- **A board with no `Status` field, or with no column that means start** — write the
  section with the owner and the number, and say that no start column exists. The label
  alone is then the whole gate, which is the same answer a repo with no board gives.
- **The section already exists** (a re-run) — this is the update path (step 0d): read the
  two coordinates back and **report** a mismatch, don't silently rewrite. A renamed column
  is the one that changes, and a stale name reads every card as outside the start column.

### 2b. Migrate the label vocabulary

**One work-state family, four values, and it never stacks.** A repo set up under an
earlier version carries two more families that this version deleted. This step is the
only one that runs once and touches the whole tracker, so it is the only place the
migration can run
([ADR 0053](../orchestrator/docs/adr/0053-one-work-state-label-and-a-computed-position.md)).

**Land this with no worker in flight.** Read the queue first. An item at `to-review` is
safe. An item at `in-progress` is not, because its schedule ticks while the family goes.

**Name every item that wears a deleted label before you delete anything.** The maintainer
has to see what changed, and a deleted label takes its items with it:

```bash
for label in phase:impl phase:review phase:e2e to-merge; do
  gh issue list --state all --label "$label" --json number,title,labels \
    --jq --arg l "$label" '.[] | "\($l)\t#\(.number)\t\(.title)"'
done
```

Report that list as a table, then take these three steps in order:

1. **Create `needs-human`**, with the `gh label create` line from the `## Work-state
   labels` section of `docs/agents/issue-tracker.md`. It is the one label that stops every
   tick, so it exists before anything reads for it.
2. **Write `needs-human` plus one comment on every open item that wore a deleted label**,
   where that item is not at `to-review`. The comment says which label it lost and what
   the maintainer has to decide. A paused item is safer than an item whose state nothing
   can read.
3. **Delete the two families**, one call per value:

   ```bash
   for label in phase:impl phase:review phase:e2e to-merge; do
     gh label delete "$label" --yes
   done
   ```

**A label that does not exist is not an error here.** A fresh repo has none of the four,
so `gh label delete` reports one miss per absent label and the step is still complete. Say
which of the four existed.

**Every column this repo stopped writing stays on the board, and the maintainer deletes
it.** That is a board edit and not a label. Nothing writes a card at all now, so an unused
column costs nothing until they remove it
(`orchestrator/docs/adr/0054-the-board-is-an-input-not-a-mirror.md`).

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

   | Profile | heavy | medium | light | review | Relative cost |
   |---------|-------|--------|-------|--------|---------------|
   | **conservative** | `opus-5` @ `medium` | `sonnet-5` @ `low` | `sonnet-5` @ `low` | `gpt-5.6-terra` @ `medium` | ~1× |
   | **balanced** (recommended) | `opus-5` @ `high` | `sonnet-5` @ `medium` | `sonnet-5` @ `low` | `gpt-5.6-terra` @ `high` | ~2–3× |
   | **max-capability** | `opus-5` @ `xhigh` | `opus-5` @ `high` | `sonnet-5` @ `high` | `gpt-5.6-sol` @ `high` | ~5–8× |

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
7. **Gate profile** — `strict` or `lite`. Recommend **strict**: it runs all four gate
   layers, so a machine finds each fault before a human reads the diff. **`lite` drops
   layer 4**, which is the mutation score, the SAST scan and the dependency CVE scan. So a
   `lite` repo needs no mutation runner and no SAST tool, and step 4 skips those rows. It
   also drops the layer 4 box from the checklist, even where `deep` holds a command. Take
   `lite` for a small repo, or where layer 4 costs more minutes than the repo is worth.
   The answer goes to `gates.profile` in the config
   ([orchestrator.template.md](orchestrator.template.md)). The layers themselves are in
   [`references/quality-gates.md`](../orchestrator/references/quality-gates.md), and the
   rationale is
   [ADR 0032](../orchestrator/docs/adr/0032-quality-gates-are-a-layered-contract.md).
   **The families are not a question here.** Step 1a detected them, and they go to
   `gates.langs`.
8. **Live story cap** — `max_stories`. Recommend **2**: it bounds how many Story runs are
   live at once, and a run holds its Story slot until the parent closes, story proof
   included.
   Take **1** for a repo where one story at a time is enough. **The second roof is not a
   question here.** `max_workers` bounds live Workers across every run, and its default is
   4. The tick reads both roofs and the lower one wins, so it starts nothing where either
   one is full. **The two roofs must not multiply**, so 2 stories and a cap of 4 give 4 live
   workers and never 8. The answer goes to `max_stories` in the config
   ([orchestrator.template.md](orchestrator.template.md)). The rule itself is
   [ADR 0045](../orchestrator/docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md).
9. **Parallel check** — `touches` or `off`. Recommend **touches**: the queue tick
   compares two candidates' `## Touches` blocks with `fnmatch`, and spawns them
   together only where the blocks are disjoint. **An item with no block runs alone**
   under `touches`, because silence reads as risk and not as safety. Take `off` for a
   repo that will not fill the blocks, where the tick then compares nothing and
   spawns every unblocked child. The answer goes to `parallel_check` in the config
   ([orchestrator.template.md](orchestrator.template.md)). The rule itself is
   [ADR 0046](../orchestrator/docs/adr/0046-parallel-spawn-is-gated-on-a-declared-touch-set.md).
   **A wrong block is never a question here.** The block is a declaration and not a
   constraint. So no gate reads a diff against it, and this step asks only which
   value the dial takes.
10. **repo** — the absolute path to the main checkout (stays on the default
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
- **gate tools — conditional on the language family step 1a turned on.** Each family has
  one table of tool rows in
  [`references/requirements.md`](../orchestrator/references/requirements.md).
  `## Python gate tools` and `## TypeScript gate tools` are the two that landed. Where a
  family is on, its table is part of the required set — a repo where step 1a turned on
  both `python` and `typescript` installs both tables. Where no family is on, no row of
  either applies and setup checks nothing. **This is the same condition step 1a used**, so
  the detection and the install cannot disagree about when a tool is required. The gate
  profile then narrows that set, and it never widens it — see the install loop below.
- **tool:** the one in config (`orca` / `cmux` / `herdr`).
- **harness(es):** the impl harness, **and** the review harness if
  `review.enabled` — a cross-vendor review setup (e.g. impl `claude`/opus-5,
  review `codex`/gpt-5.6) needs **both** CLIs installed and authenticated.
- **optional, per recipe:** a DB CLI like `sqlite3` (if `db_gate` set), node/npm
  or uv (if `setup_cmd` needs them).

### Install loop

For each needed dep, run its check command. **If present, it was already brought up
to date in step 0a** — skip it. The browser surface and the gate tools are the two
exceptions, because step 0a updates neither: see each bullet below. If missing, install
it by running the command from `requirements.md`:

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
- **Gate tools specifically — one row at a time, and every name comes from the table.**
  Run the check command of each row in `## Python gate tools` and, where `typescript` is
  on, `## TypeScript gate tools` too. Install each missing one with that row's install
  command. **Never name a tool that has no row there.** The matrix
  and the catalog are held together by
  [`../scripts/test_quality_gates.py`](../scripts/test_quality_gates.py), and a name
  invented here escapes that test. Every command in that table carries a **(verify)**
  note, because none of them has run on this machine yet. That note is not the
  **(verify)** of an unpinned installer, and these commands are exact. So run each one,
  then run the row's check command again. Report the row as **installed** only where that
  second check is green.
  - **A row that installs into the project needs the project environment active.** The
    install command says which: `uv add --dev` writes into the project, and
    `uv tool install` or `brew install` writes onto the machine. Activate that environment
    before the check. A check that runs outside it reports a present tool as missing.
  - **The profile drops a layer, and a dropped layer drops its rows.** On `lite`, skip
    every row whose gate sits in layer 4 of the matrix. The `Layer` column names them, so
    no list of tools stands here to go stale. Those rows read **not needed by this
    profile** in the table below, and never missing. On `strict`, every row applies.
  - **A row that needs a credential is never installed.** If a row needs an API key, a
    license or a login, report it as **needs the user**, with the exact remaining action.
    A credential cannot arrive unattended, and a config that names such a tool present is
    a config that lies. No Python row and no TypeScript row needs one today, so this rule
    waits for the family that brings one. `## Vendor keys` in the same catalog holds the
    rule for a harness.
  - **A present gate tool stays as it is.** The update block in `requirements.md` carries
    no line for one, so step 0a did not update it and this loop does not either. A green
    check is the whole answer.
  - **This step installs a tool and writes no file.** The Makefile, the gate script and
    each threshold key land in step 5a. So no threshold reaches a tool config here.
- **CLIs** — the documented installer (`brew install gh`/`glab`, `npm install -g @anthropic-ai/claude-code`, etc.).
- **MCP** — `claude mcp add <name> <command/url>` once the server binary/endpoint is known.

**Only pause for a human when you genuinely can't proceed automatically:**

- An install command is marked **(verify)** in `requirements.md` (tool/harness
  installers not pinned) — show the doc link and ask the user to run/confirm it. **A gate
  tool row is not this case**, and the install loop above says why.
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

Give the gate tools **one row each**, on the same present / installed / needs-the-user
terms. Name the language family and the marker that turned it on above the rows. Name the
gate profile beside it. Then the table says which family setup found, which profile the
user chose, and which tools are now present. Where no family is on, write one line in
place of the rows: no family is on, so no gate tool applies. Nothing was checked, and
nothing is missing.

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

  Runs <harness> workers via <tool> — <heavy.model>@<heavy.effort> for heavy items, <medium.model>@<medium.effort> for medium, <light.model>@<light.effort> for light[, cross-vendor review with <review.model>]. See `docs/agents/orchestrator.md`.
  ```

- Ensure `.orchestrator/` is gitignored (the worker checklist files live there):
  add `.orchestrator/` to the repo's `.gitignore` if absent.

### 5a. Write the gate files

Each layer command in `gates:` needs a file behind it. Write those files here, from the two
templates beside this skill:

- [`templates/Makefile.template`](templates/Makefile.template) → `Makefile`
- [`templates/checks.sh.template`](templates/checks.sh.template) → `scripts/checks.sh`,
  and make that file executable

Each Makefile target runs one layer of the script, and CI runs the same script. So a step
cannot be green here and red in CI for a reason that is not the code. The layers are in
[`references/quality-gates.md`](../orchestrator/references/quality-gates.md), and the
rationale is
[ADR 0032](../orchestrator/docs/adr/0032-quality-gates-are-a-layered-contract.md).

**Only where a language family is on.** Step 1a turns a family on, and `python` is the one
family that landed. Where `gates.langs` is blank, write no gate file and say so in one
line. That repo has no gate tool either, from the same condition step 4 read. It is a
supported configuration and not a gap.

**The `lite` profile drops layer 4.** A comment marks the layer 4 block of the Makefile
template on each side. On `lite`, delete that block. Leave `gates.deep` blank, and the
blank field then drops the layer 4 box from the checklist
([`references/checklist.template.md`](../orchestrator/references/checklist.template.md)).
The script keeps its `deep` case, because no target and no config field reaches it. So a
later move to `strict` needs the Makefile block back, and nothing else. On `strict`, keep
the block. Write `make deep` into `gates.deep`.

**Each threshold goes to the file that reads it.** Config is the source of truth for a
threshold. Write the number the config holds, and never a second number:

| Threshold | File | Key |
|---|---|---|
| `complexity` | `pyproject.toml` | `max-complexity` under `[tool.ruff.lint.mccabe]` |
| `coverage` | `pyproject.toml` | `fail_under` under `[tool.coverage.report]` |
| `mutation` | `scripts/checks.sh` | `MUTATION_MIN` |
| `cognitive`, `funlen`, `branch` | — | the Python column states no default, so these stay blank and nothing is written |

A blank threshold writes no key at all. The tool's own default then stands, which is what
the config template says a blank field means.

**Setup never rewrites a file it did not create.** Where the target file already exists,
read the value it holds. Where that value equals the config value, say so in one line and
write nothing. Where the two differ, report both and ask which one is correct:

> `pyproject.toml` sets `fail_under = 90`, and the config sets `coverage: 85`.
> Which number is correct?
>
> 1. **Keep 90** — the config takes the value of the file.
> 2. **Write 85** — the file takes the value of the config, and only that key changes.

Then write only that one key, and touch no second key. This narrows the rule that opens
step 5, and it narrows it to this extent alone. A hand-tuned rule set belongs to the
maintainer
([ADR 0032](../orchestrator/docs/adr/0032-quality-gates-are-a-layered-contract.md)).

The same rule covers the Makefile and the script. Where a `Makefile` exists, add only the
targets it lacks. Where it already holds a target of one of these names, report both
recipes. Then ask which one is correct. Where `scripts/checks.sh` exists, do the same, one
layer at a time.

**Two more files belong to the maintainer, and both need a word in the report.** Layer 3
reads its contracts from `.importlinter`, and the mutation runner reads which paths to
mutate from `pyproject.toml`. Setup writes neither. So layer 3 stops until the contracts
exist, and layer 4 stops until the runner knows what to mutate. Name each one as an action
for the maintainer. Write no contract yourself, because a contract invented here describes
a dependency graph nobody read.

**Report one row per file**: written / already there / needs the user. Give each threshold
its own row, with the key and the number. Then the report says which command is real, and
which number reached the tool that reads it.

### 5b. Report whether the enforcement is live

The plugin ships a **hook plane**: three hooks that inject the item facts, deny a write
that only a seam makes, and record what a gate command did. They are the one layer that
can refuse a command before it runs
([`../orchestrator/references/hooks.md`](../orchestrator/references/hooks.md);
[ADR 0051](../orchestrator/docs/adr/0051-a-hook-refuses-and-a-seam-performs.md)).

**This step installs nothing.** The hooks ship with the plugin, so there is no file to
write and no dependency to add. It reads three facts and reports them.

Set `ROOT` to the plugin root. Resolve it from the **Base directory for this skill** line
at the top of this skill:

```bash
ROOT="<base directory>/.."
# read 1 — the manifest names the hook file
python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('hooks','NO HOOKS KEY'))" \
  "$ROOT/.claude-plugin/plugin.json"
# read 2 — that file resolves, and it parses
python3 -c "import json,sys;print(sorted(json.load(open(sys.argv[1])).get('hooks',{})))" \
  "$ROOT/hooks/hooks.json"
# read 3 — the marker that makes a hook do anything at all
{ [ -f docs/agents/orchestrator.md ] || [ -d .orchestrator ]; } \
  && echo "marker: present" || echo "marker: absent"
```

Report one row per read: **live** / **not live**, with what the command printed.

- **Read 1 prints `./hooks/hooks.json`.** Any other value, and the plane is off. The
  repair is that one key in `.claude-plugin/plugin.json`, and it is also the rollback.
- **Read 2 prints the three event names.** A file that does not resolve, or that does not
  parse, is a plane the harness loads nothing from.
- **Read 3 answers for this repo alone.** With no marker every hook exits at once and
  costs nothing. Step 5 wrote the config, so a first setup reaches this step with the
  marker present.

**Name the restart.** A manifest is read once, at session start. So a `hooks/hooks.json`
that arrived with step 0a reaches this session only after a restart, which is the same
rule step 0a states for the skill body. Say in one line that the plane is live from the
next start, and never from this one.

### 5c. Run each gate command once

**Why this step exists: a `git push` is denied while a configured gate has no green line
at `HEAD`** ([`../orchestrator/references/hooks.md`](../orchestrator/references/hooks.md)).
So a `gates:` field can name a command that does not exist. That field then denies every
push in this repo, and the message names a command nobody can run. One run per command
here turns that from a mystery at push time into a message at setup time.

Run each non-blank command of the `gates:` block once, from the repo root. Report the
exit code of each one:

```bash
make quick; echo "quick exit: $?"
make full;  echo "full exit: $?"
```

- **Read the commands from the config this setup wrote**, and never from this page. A
  blank field is not a Gate: run nothing for it, and say so in one line. The `story` field
  is not a Gate either, because it has no exit code
  ([`references/quality-gates.md`](../orchestrator/references/quality-gates.md)).
- **A command that does not exist is the fault this step looks for.** `No rule to make
  target` and `command not found` each mean no push can land. Name the field, the command
  and the repair, which is either step 5a or the field itself.
- **A non-zero exit from a command that ran is not a setup fault.** The repo has work to
  do, and the report says which layer is red. Change no code here.
- **Report one row per gate**: the field, the command, and the exit code. Then say in one
  line that a red row holds every push until it is green.

### 5d. Write the repo-wide queue schedule

**Why this step exists: without it no work starts by itself.** A maintainer labels a story
and drags its card, and then nothing reads that. One repo-wide schedule named
`orchestrator-queue` turns those two facts into a running worker, so no session sits in the
middle of the loop
([ADR 0045](../orchestrator/docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md)).

Create it with operation 11 of the tool reference
([`../orchestrator/references/tools/_operations.md`](../orchestrator/references/tools/_operations.md)),
with three changes from the per-item form. The name is `orchestrator-queue`. The precheck
is the `queue` subcommand. And the schedule binds to the main checkout, because it watches
the tracker rather than a worktree:

```bash
--name "orchestrator-queue" --trigger '* * * * *' --workspace "<the main checkout>" \
  --precheck "python3 <plugin root>/scripts/worker_state.py queue --repo <owner>/<name> --board-project <number> --board-owner <owner> --start-column '<column>' --max-stories <max_stories> --max-workers <max_workers> --parallel-check <parallel_check> --spawn-command '<the spawn_item.py invocation>'"
```

- **The trigger is one tick a minute**, which is the cron form `'* * * * *'`. One item a
  minute is slow enough for a human to notice a wrong start and stop it.
- **The workspace is the main checkout the `repo` field of the config names.** Pass the
  workspace selector of that checkout, and never the flag that names a repository. A repo
  selector cuts a new worktree per run, and this schedule reads the tracker rather than a
  worktree. The two flag names are in operation 11 of the tool reference.
- **`<plugin root>` is a literal path here, and never a shell variable.** The tool stores
  this string and runs it a minute later, in a shell that saw no assignment. So resolve the
  value and write it in, the same way a per-item precheck carries it
  ([`../orchestrator/SKILL.md`](../orchestrator/SKILL.md#resolve-the-plugin-root-and-prove-the-seam-runs)).
- **Read every other value from the config this setup wrote**, and never from this page.
  The two roofs are `max_stories` and `max_workers`, the gate mode is `parallel_check`, and
  the three board coordinates come from the `## Project board` section of
  `docs/agents/issue-tracker.md`. A repo whose tracker names no board passes none of the
  three, and the label alone is then the whole gate.
- **The spawn command is the whole `scripts/spawn_item.py` invocation**, with its own tool
  commands already in it. The tick fills five tokens of one work item into that string:
  `{item}`, `{slug}`, `{title}`, `{body}` and `{skill}`. The argument surface of that seam
  is its own `--help`, so this page restates none of it.
- **Prove the precheck runs before the schedule exists.** Run the same command once by
  hand, from the repo root. Exit 1 is a quiet tick and it is the answer a fresh repo gives.
  Exit 64 is a flag with a typo, and it means the schedule fails every minute.

**This step writes no per-item schedule**, because `scripts/spawn_item.py` writes that one
at its last step.

**A tool with no automation surface records this operation as unsupported.** `cmux` and
`herdr` declare none, so skip the step and change nothing else about the setup. **Then say
in the report that the queue tick is unavailable on this tool.** The maintainer then knows
that a start stays a manual `work on N`
([`../orchestrator/SKILL.md`](../orchestrator/SKILL.md#what-next--pick-the-next-work)).

## 6. Done

Tell the user setup is complete and that the orchestrator will now read
`docs/agents/orchestrator.md`. They can edit it directly later.

**Re-running is how you update.** A later `/orchestrator-setup` refreshes the
plugin and every dependency skill, then reconciles the config without
re-interviewing — it only starts over if the user explicitly asks for a full
re-setup (step 0c). It also strips the no-invoke flag the update restores (step 0b), so a
routed skill the model could not invoke is reachable again. Mention this, so a version bump
doesn't look like it needs a
manual reinstall.
