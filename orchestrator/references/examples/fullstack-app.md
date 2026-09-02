<!--
Worked example: a fully filled-in docs/agents/orchestrator.md for a typical
full-stack monorepo — web app + API + SQL migrations, GitLab tracker.
Shows every recipe field populated. Not loaded unless referenced.
The setup phase can offer to clone this as a starting point.
-->

# Orchestrator config — acme-app (example)

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

review:
  enabled: false
  rounds:  3

repo:     ~/git/acme-app
tracker:  # docs/agents/issue-tracker.md -> GitLab (glab), labels: ready-for-agent / in-progress / to-review / done

setup_cmd:  "pnpm install"
run_recipe: "scripts/run.sh start -d -a $BE -w $FE -g $GA"   # boots api+web+gallery, auto-wires web API base
ports:      "FE=3000+N BE=8000+N GA=3100+N"
db_gate:    "cp apps/api/app.db apps/api/app.db.backup-$(date +%Y%m%d-%H%M%S); cd apps/api && uv run alembic upgrade head; sqlite3 app.db '.schema <table>' to verify the new column/table exists"
evidence:   "real-data proof (playwright screenshot / curl JSON / DB row dump / real-input run) PLUS full suite passing — unit tests alone are not enough"
```

## Role routing on this project

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
  `references/models.md`) — the schema/migration pairing is exactly where an
  under-thinking worker 500s the API.

## Project-specific notes

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
