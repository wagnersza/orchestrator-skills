<!--
Worked example: a fully filled-in docs/agents/orchestrator.md for a typical
full-stack monorepo, then a trace of one routed run against it — an `inline`
verb that writes a spec, followed by a `worker` verb that spawns against it.
Shows every recipe field populated, and where the routed skill appears in the
prompt and in the report. Not loaded unless referenced. The setup phase can
offer the config half as a starting point.
-->

# A worked run, end to end (example)

## The config — acme-app

```yaml
tool:     orca
harness:  claude
yolo:     on

models:
  heavy:
    model:  opus-5
    effort: xhigh
  medium:
    model:  sonnet-5
    effort: medium
  light:
    model:  sonnet-5
    effort: low
  review:
    model:  gpt-5.6-terra
    effort: high

repo:     ~/git/acme-app
tracker:  # docs/agents/issue-tracker.md -> GitLab (glab), labels: ready-for-agent / in-progress / to-review / done

setup_cmd:  "pnpm install"
run_recipe: "scripts/run.sh start -d -a $BE -w $FE -g $GA"   # boots api+web+gallery, auto-wires web API base
ports:      "FE=3000+N BE=8000+N GA=3100+N"
db_gate:    "cp apps/api/app.db apps/api/app.db.backup-$(date +%Y%m%d-%H%M%S); cd apps/api && uv run alembic upgrade head; sqlite3 app.db '.schema <table>' to verify the new column/table exists"
evidence:   "real-data proof (playwright screenshot / curl JSON / DB row dump / real-input run) PLUS full suite passing — unit tests alone are not enough"
```

### Role routing on this project

- A ticket that adds a page + API route + migration is **heavy** — it touches
  `apps/web`, `apps/api`, and `alembic/versions` at once.
- A ticket that adds one field to an existing form is **medium**. Criteria are
  already enumerated, but the ticket touches both `apps/web` and `apps/api`. It
  fires no `heavy` signal, because it changes no schema and touches only two
  files. It also fails one `light` condition, because it touches more than one
  file, so it does not round down either.
- A copy change, a single-component styling fix, or a test-only ticket with fully
  enumerated criteria is **light**.
- Anything with a `db_gate` is heavy by definition (the rule in
  [`../models.md`](../models.md)) — the schema/migration pairing is exactly where
  an under-thinking worker 500s the API.

### Project-specific notes

These are the per-project specifics an orchestrator would otherwise hardcode; they
live here as recipe context, not in the skill body.

- **Reuse checks before booting:** `scripts/run.sh status -a $BE -w $FE -g $GA`
  (and/or `lsof -i :$FE` / `lsof -i :$BE`) — reuse a live instance instead of
  double-starting. Tear down after evidence: `scripts/run.sh stop -a $BE -w $FE -g $GA`.
- **DB gate detail:** the ticket touched the DB if it changed an ORM model/schema
  or added a migration under `apps/api/alembic/versions/`. A model field with no
  applied migration is exactly what 500s the API at runtime (`no such column: …`).
  If a model change has no migration, autogenerate one
  (`uv run alembic revision --autogenerate -m "..."`), review, then upgrade.
- **Evidence upload:** screenshots to project uploads —
  `glab api projects/:id/uploads --form "file=@docs/review/<N>/<file>.png"`,
  desktop/web viewport only.
- **Review note** goes on the **ticket** (`glab issue note <N>`), not the MR,
  with sections: What to review / Main changes / How to test / Evidence. The MR
  description just links back to the ticket.
- **Codebase-memory:** workers query the existing index for the **main** checkout;
  never `index_repository` a worktree (it orphans on teardown). Orchestrator
  refreshes the main index once after merges land.
- **user-story parent lifecycle:** specs carry the `user-story` label; their
  children carry `## Parent #N` and link via `/relate`. First child to start
  promotes the parent to `in-progress`; last child to close flips the parent to
  `done`. (This lives in the tracker/to-tickets conventions, surfaced here as
  project context.)

## The trace — two turns, against that config

`tool: orca`, `harness: claude`, `models.heavy: opus-5 @ xhigh`, `models.medium:
sonnet-5 @ medium`, `models.light: sonnet-5 @ low`, `models.review: gpt-5.6-terra @
high`, GitLab tracker. This repo has no runtime, so a trace of the flow is how the
routing contract gets tested. The rules are in [`../../SKILL.md`](../../SKILL.md).
The rows are in [`../skill-routing.md`](../skill-routing.md).

### Turn 1 — `/orchestrator to-spec` (lane `inline`)

The user has just finished describing a contacts-import feature in this session.

- **Resolve the verb.** `to-spec` matches a row: skill `/to-spec`, lane `inline`.
- **Invoke it here.** In the main checkout (`~/git/acme-app`), on the default branch.
  No worktree, no branch, no spawn. The row's Notes say what to hand it: the
  conversation so far, plus the tracker config at `docs/agents/issue-tracker.md`. The
  same Notes say the skill applies `ready-for-agent` itself, so the orchestrator
  writes no label of its own.
- **The output is non-source** — one issue on the tracker — which is why this row is
  `inline` and no rule is breached.
- **Report.** `/to-spec ran here. Spec is #61, labelled ready-for-agent.`

The user reads the spec, and the acceptance criteria are enumerated on it.

### Turn 2 — `/orchestrator implement #61` (lane `worker`)

- **Resolve the verb.** `implement` matches a row: skill `/implement`, lane `worker`.
  The orchestrator invokes nothing. The invocation goes to the worker.
- **Classify the role, separately.** #61 adds a page, an API route and a migration,
  so it is `heavy`, and `db_gate` is configured, which makes it heavy by definition.
  `models.heavy` resolves to `opus-5 @ xhigh`. The skill and the model are two
  resolutions over one item, and neither decided the other.
- **Preflight the routed skill.** The harness is `claude`, so `/implement` is a plugin
  skill. The `mattpocock-skills` plugin check runs, and the plugin is installed. If it
  were missing, the spawn aborts here, before the worktree exists. The report then says
  which skill, which harness, and that `/orchestrator-setup` installs it.
- **Run `scripts/spawn_item.py --execute`.** It reads the config for the tool, the
  harness, the yolo flag and the model pair; this session names only `--role heavy`.
  The seam creates the worktree, branch `61-contacts-import` off the default branch,
  boots `claude --model opus --effort xhigh --dangerously-skip-permissions`, gates on
  readiness, then claims #61 (swaps `ready-for-agent` for `in-progress`) and delivers
  the rendered prompt.
- **The rendered prompt** carries the four inputs
  [`../prompt.template.md`](../prompt.template.md) takes: the work item, the seeded
  checklist, the gate commands, and `/implement` as the routed skill. `Run
  /implement.` is an imperative in the prompt's own voice, and it goes through
  `prompt-improver`, named `opus-5`, as an **agentic-pipeline prompt**.
- **Report.** `#61 61-contacts-import spawned · /implement · heavy · opus-5 · xhigh.
  1 worker live.` Four fields: the skill first, then the role, the model and the
  effort.

The worker's first act inside the worktree is `/implement`. It then works the
checklist to the review note and stops there.

### The same two turns on a `codex` harness

Everything above holds except the shape of one line. `codex` parses no slash command,
so the prompt carries the row's *Without slash commands* prose in place of
`Run /implement.` — implement the item test-first, at agreed seams, run the type check
and the full suite, review the diff against the criteria, then commit. The preflight
changes with it. There is no plugin to check, so what the orchestrator confirms is that
the row has that prose. A `/implement` sent to `codex` is the failure this avoids. The
worker reads it as text and starts cold, and the transcript looks like it worked.

Turn 1 cannot happen on a session with no slash commands at all. There the
orchestrator answers `to-spec` freehand and its report says the skill was
unreachable.

### Two variants worth tracing once

- **A mixed batch.** `work on #58, max 5` finds three unblocked children. #59 is a
  bug with reproduction steps in one file. #62 is a settings toggle on an existing
  page, with criteria already enumerated but touching two files. #60 is a new
  endpoint that adds a page, an API route, and a migration. The verb resolves **per
  child**, so #59's prompt carries `/diagnosing-bugs`, and #62's and #60's carry
  `/implement`. #59 fires all three `light` conditions — one file, criteria
  enumerated, no open decision — so it takes the `light` role. #62 touches two
  files, so it misses the `light` file-count condition. It also fires no `heavy`
  signal, so it takes the `medium` role instead. #60 touches three components at
  once, a `heavy` signal, so it takes the `heavy` role. The report gives four
  fields per child: `#59 → /diagnosing-bugs · light · sonnet-5 · low`, `#62 →
  /implement · medium · sonnet-5 · medium`, `#60 → /implement · heavy · opus-5 ·
  xhigh`. One blanket skill for the batch is the same defect as one blanket model.
- **A review.** `review #61 adversarially` spawns a `gpt-5.6-terra` reviewer on #61's
  branch, and that reviewer posts one comment naming three findings. **The comment goes to
  the maintainer, and no verb resolves off it.** Nothing re-prompts the #61 worker, and its
  effort stays where the spawn put it. Where the maintainer wants those findings fixed,
  they ask for the fix as its own work (ADR 0066).
