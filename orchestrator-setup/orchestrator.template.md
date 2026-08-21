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
tracker:  # read from docs/agents/issue-tracker.md; do NOT redefine labels or
          # board coordinates here

# --- project recipe (the completion contract's project-specific parts) ---
setup_cmd:  ""            # e.g. "pnpm install" — run by the tool's setup hook
run_recipe: ""            # e.g. "scripts/run.sh start -d -a $BE -w $FE -g $GA"
ports:      ""            # e.g. "FE=3000+N BE=8000+N GA=3100+N"  (N = work-item number)
db_gate:    ""            # e.g. "alembic upgrade head; verify new column/table exists"
evidence:   "make deep green + real-data proof"  # the evidence bar

# --- quality gates (the layered completion bar) ---
# The layer model and the Python gate matrix are in references/quality-gates.md.
# Config is the source of truth for a threshold.
gates:
  profile: strict         # strict | lite — `lite` drops layer 4
  langs:   python         # the language families that setup found, comma-separated
  quick:   "make quick"   # layers 1 + 2 — format, lint, types, tests, complexity
  full:    "make full"    # layer 3 — coverage, import boundaries, secrets
  deep:    "make deep"    # layer 4 — mutation score, SAST, dependency CVEs
  story:   "/improve-codebase-architecture"  # layer 5 — advisory, once per story
  thresholds:             # blank = no cap, so the tool's own default stands
    complexity: 10        # cyclomatic branches per function
    cognitive:  ""        # the Python matrix declares no default
    funlen:     ""        # the Python matrix declares no default
    coverage:   85        # percent of lines
    branch:     ""        # the Python matrix declares no default
    mutation:   70        # percent of mutants the suite kills
  infra:                  # every field blank until the Terraform column lands
    plan_role:    ""      # blank = no plan gate
    policy_dir:   ""      # where the policy files live
    fixtures:     ""      # the saved plans those policies read
    halt_on:      ""      # the halt conditions that stop an apply
    zero_changes: ""      # the target a second plan must report with no change
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
  `docs/agents/issue-tracker.md`, not this file — single source of truth. So do the
  **project board** coordinates, in its `## Project board` section: the project
  owner/number, the `Status` field id, and the option ids. The board's `Status` is a
  derived projection of those labels, written at every transition and reconciled when
  the ready queue is read — not a second state machine. A repo with no board omits
  that section and every board write becomes a no-op. Rationale:
  `orchestrator/docs/adr/0009-labels-drive-board-status.md`.
- **Project recipe** fields are the only place project specifics live. Leave a
  field blank if it doesn't apply (e.g. `db_gate` for a repo with no database).
- `N` in `ports` is the work-item number, so parallel workers never collide.
- **evidence** stays a **superset** of the gates. `make deep green` is the machine
  half. `real-data proof` is the half that no gate command produces, because no gate
  drives a browser through the **Browser surface**. So the field asks for both.
- **gates** is the completion bar. Layers 1 to 4 each run one command inside the
  worker's own worktree, before the push. A non-zero exit stops the work. Layer 5
  runs once per user story, and it is advisory. The layer model, the Python gate
  matrix and the default for each number are in `references/quality-gates.md`. The
  rationale is `orchestrator/docs/adr/0032-quality-gates-are-a-layered-contract.md`.
  - **profile** is `strict` or `lite`. `strict` runs all four layers. `lite` drops
    layer 4, so a small repo needs no mutation runner and no SAST. `lite` drops the
    layer 4 box even when `deep` holds a command.
  - **langs** lists the language families that setup found, comma-separated. Only
    `python` has a gate matrix today, and each other family is a work item of its
    own.
  - **quick / full / deep** are layers 1+2, 3 and 4. A worker runs `quick` after
    each edit and before each commit, `full` before the push, and `deep` once per
    item. `story` is layer 5, and the orchestrator session runs it.
  - **A blank command field drops that layer's box** from the checklist, before the
    orchestrator sends it. A blank recipe field does the same. A repo with no
    mutation runner leaves `deep` blank. The worker then cannot fail a box that no
    command can satisfy. **A blank command is a supported configuration and not a
    gap.**
  - **thresholds** hold the numbers that the gates read, and **config is the source
    of truth for a threshold**. A maintainer raises coverage here, in one place, and
    not in five tool configs. `references/quality-gates.md` holds the default for
    each one, so no number stands twice with two values. `complexity` counts
    cyclomatic branches per function, and `coverage`, `branch` and `mutation` are
    percentages. A blank threshold is no cap, so the tool's own default stands.
    `cognitive`, `funlen` and `branch` ship blank, because the Python matrix declares
    no default for them.
  - **Setup writes each threshold into the tool config that reads it**, so the number
    reaches that tool with no hand step. **Setup never rewrites a tool config that it
    did not create.** If that file already exists, setup reports both values, asks
    which threshold is correct, and then writes only that key.
  - **infra** configures the plan gate of an infrastructure repo. `plan_role` names
    the role that the plan runs as, and **a blank `plan_role` means no plan gate**.
    `policy_dir` holds the policy files, and `fixtures` holds the saved plans that
    those policies read. `halt_on` holds the **Halt condition** list that stops an
    apply, and `zero_changes` names the target that a second plan must report with no
    change. Every field ships blank, because the Terraform and Kubernetes columns are
    each a work item of their own.
