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
# This is `balanced` with heavy raised to xhigh: a wrong edit to a skill body
# ships bad instructions to every future worker, so heavy items justify the rung.
models:
  heavy:                  # multi-skill change, new skill, contract/vocabulary change
    model:  opus-5
    effort: xhigh
  light:                  # single-file reference or doc edit, fully enumerated criteria
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
repo:     /Users/wagner.souza/git/wsza/orchestrator-skills   # main checkout; stays on main
tracker:  # read from docs/agents/issue-tracker.md (GitHub / gh); do NOT redefine labels here

# --- project recipe (the completion contract's project-specific parts) ---
setup_cmd:  ""            # nothing to install — this repo is markdown skills + JSON manifests
run_recipe: ""            # no app to boot
ports:      ""            # no ports (nothing listens)
db_gate:    ""            # no database
evidence:   "the changed skill/reference read end to end for internal consistency, every cross-reference resolved (no link to a deleted or renamed file), and any manifest edit validated as JSON. For a change to a skill body, quote the before/after of each edited block in the review note."
```

## Notes

- **tool / harness** pick the workspace and the agent CLI. The skill reads the
  matching reference files for concrete commands; nothing tool-specific is
  hardcoded in the skill body. `orca` needs `orca open` running before the first
  spawn.
- **models** picks the right model for the job — one `(model, effort)` pair per
  **role**, not one global model. The orchestrator classifies each work item into
  a role at spawn time (`heavy` / `light`), defaulting to `heavy` and downgrading
  only on clear signals. The routing rule and the effort ladder live in
  `references/models.md`.
  - **Effort** tunes how much the model *thinks*: `low | medium | high | xhigh | max`.
    Both frontier models default to `high`.
  - The **harness clamps** what it can express — `codex` tops out at `high`,
    `pi` at `xhigh`, `cursor` bakes effort into the model id. `claude` (this
    config) reaches the whole ladder, so no clamp applies.
- **yolo** is always required for a worker (nobody approves its prompts). For
  `claude` that's `--dangerously-skip-permissions`.
- **review** is off. Run it on demand with "review #N adversarially" — that spawns
  a `gpt-5.6-terra` reviewer (openai) against an `opus-5`/`sonnet-5` impl
  (anthropic), so the cross-vendor assertion holds. Turning it on requires `codex`
  to be OpenAI-authed.
- **Work-state labels** (`ready-for-agent`, `in-progress`, `to-review`, closed)
  come from `docs/agents/issue-tracker.md`, not this file — single source of truth.
  They don't exist in the GitHub repo yet; that file carries the `gh label create`
  commands.

## Why the recipe is empty

This repo is a **documentation artifact**: markdown skills plus a few JSON
manifests. There is nothing to install, nothing to boot, no schema, and no port.
So `setup_cmd`, `run_recipe`, `ports`, and `db_gate` are all blank, and the
orchestrator drops their checklist steps before sending a prompt.

The `evidence` bar replaces "boot the app and screenshot it" with what actually
proves a skill edit is correct: cross-references resolve, the contract stays
internally consistent, and manifests still parse. The failure mode here is a
dangling link to a renamed reference file or a rule that contradicts another
section — not a 500.

A worker on this repo should also:

- Keep every claim in a skill body traceable to a reference file or an ADR. A rule
  with no home is the thing that rots.
- Record a decision that reverses or narrows an earlier one as a new ADR under
  `orchestrator/docs/adr/`, rather than silently editing the old one.
- Bump `version` in `.claude-plugin/plugin.json` — minor for a contract or
  dependency change, patch for docs-only.
