<!--
Seed for docs/agents/orchestrator.md in a target repo.
Written by /orchestrator-setup. Human-editable afterwards.
The orchestrator skill reads the values in the fenced block; the prose explains each.
-->

# Orchestrator config

How the orchestrator runs workers in **this** repo. Edit freely; re-run
`/orchestrator-setup` only to start over.

```yaml
# --- workspace + agent CLI ---
tool:     orca            # orca | cmux | herdr  -> references/tools/<tool>.md
harness:  claude          # claude | codex | pi | copilot | cursor -> references/harnesses/<h>.md
yolo:     on              # required; the harness ref supplies the actual flag

# --- right model for the job: one (model, effort) pair per role ---
# Roles, the routing rule, and the cost profiles are in references/models.md.
# This block is the `balanced` profile; swap any pair freely.
models:
  heavy:                  # multi-file feature, refactor, migration, open decisions
    model:  opus-5
    effort: high          # `xhigh` = max-capability profile; `medium` = conservative
  light:                  # single-file/scoped edit, fully enumerated criteria
    model:  sonnet-5
    effort: medium
  review:                 # the adversarial reviewer (see `review` below)
    model:  gpt-5.6-terra
    effort: high

# --- adversarial review (optional) ---
review:
  enabled: false          # on -> spawn a cross-vendor reviewer at the review state
  rounds:  3              # max fix<->review cycles before handing to human review
                          # model+effort come from models.review; its vendor MUST
                          # differ from the impl role's

# --- repo + tracker ---
repo:     /abs/path/to/this/repo   # the main checkout; stays on the default branch
tracker:  # read from docs/agents/issue-tracker.md; do NOT redefine labels here

# --- project recipe (the completion contract's project-specific parts) ---
setup_cmd:  ""            # e.g. "pnpm install" — run by the tool's setup hook
run_recipe: ""            # e.g. "scripts/run.sh start -d -a $BE -w $FE -g $GA"
ports:      ""            # e.g. "FE=3000+N BE=8000+N GA=3100+N"  (N = work-item number)
db_gate:    ""            # e.g. "alembic upgrade head; verify new column/table exists"
evidence:   "real-data proof + full test suite passing"  # the evidence bar
```

## Notes

- **tool / harness** pick the workspace and the agent CLI. The skill reads the
  matching reference files for concrete commands; nothing tool-specific is
  hardcoded in the skill body.
- **models** picks the right model for the job — one `(model, effort)` pair per
  **role**, not one global model. The orchestrator classifies each work item into
  a role at spawn time (`heavy` / `light`), defaulting to `heavy` and downgrading
  only on clear signals. The routing rule and the effort ladder live in
  `references/models.md`.
  - **Effort** tunes how much the model *thinks*: `low | medium | high | xhigh | max`.
    Both frontier models default to `high`.
  - The **harness clamps** what it can express — `codex` tops out at `high`,
    `pi` at `xhigh`, `cursor` bakes effort into the model id. The harness
    reference holds the map, and the orchestrator reports any clamp.
  - **Cost profile.** The block above is `balanced`. `conservative` drops heavy to
    `medium` and light to `low`; `max-capability` runs heavy at `xhigh` and light on
    `opus-5` @ `high`. Full table + per-MTok prices in `references/models.md`.
    Cheaper isn't always cheaper — a `light` worker that under-thinks costs a whole
    round trip, more than the effort saved.
  - **Single-model setup?** Replace the `models:` block with a flat
    `model:`/`effort:` pair — every role then uses it (with `models.review`, or the
    legacy `review.model`, still honoured for review).
- **yolo** is always required for a worker (nobody approves its prompts). The
  harness reference names the actual flag.
- **review** — when `enabled`, the orchestrator asserts `models.review.model`'s
  vendor differs from the impl role's (see `references/models.md`). It runs up to
  `rounds` fix↔review cycles, then hands to human review regardless.
- **Work-state labels** (`ready-for-agent`, `in-progress`, review, done) come from
  `docs/agents/issue-tracker.md`, not this file — single source of truth.
- **Project recipe** fields are the only place project specifics live. Leave a
  field blank if it doesn't apply (e.g. `db_gate` for a repo with no database).
- `N` in `ports` is the work-item number, so parallel workers never collide.
