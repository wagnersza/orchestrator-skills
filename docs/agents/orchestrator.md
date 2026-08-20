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
setup_cmd:  "python3 --version"   # stdlib-only test suite; nothing to install. The tests
                                  # for scripts/close_item.py and scripts/worker_state.py
                                  # run under `python3 -m pytest scripts/ -q` if pytest is
                                  # present, else `python3 -m unittest discover -s scripts -q`.
                                  # No third-party runtime dependency: fixtures are local
                                  # git repos in a temp dir, no network, no agent runs.
run_recipe: ""            # no app to boot
ports:      ""            # no ports (nothing listens)
db_gate:    ""            # no database
evidence:   "run the test suite and quote the result (`python3 -m pytest scripts/ -q`, or unittest discover if pytest is absent) — a green run is part of the bar whenever a Python or a Markdown file is touched. When the run is skipped, the review note must state 'no Python and no Markdown file changed'. Plus: the changed skill/reference read end to end for internal consistency, every cross-reference resolved (`scripts/test_links.py` in that suite proves this half, not a reading), and any manifest edit validated as JSON. For a change to a skill body, quote the before/after of each edited block in the review note."
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

## Why the recipe is nearly empty

This repo is mostly a **documentation artifact**: markdown skills plus a few JSON
manifests. There is nothing to boot, no schema, and no port — so `run_recipe`,
`ports`, and `db_gate` stay blank and the orchestrator drops their checklist steps
before sending a prompt.

**It is no longer markdown-only.** Two seams hold the deterministic halves of two
flows: `scripts/close_item.py` owns steps 4 to 8 of a **Close transaction** (ADR
0015), and `scripts/worker_state.py` owns the **Worker watch** predicate (ADR
0018). Each has a test suite. So:

- `setup_cmd` is a Python availability check, not blank. The suite is
  **stdlib-only** — fixtures are local git repos built in a temp directory, with
  no network, no GitHub calls and no agent runs — so there is still nothing to
  install. `pytest` is used if present purely for nicer output; `python3 -m
  unittest discover -s scripts -q` is the fallback and the guaranteed path.
- **Running the tests is part of the `evidence` bar** whenever a Python or a
  Markdown file is touched. A review note that skips the run must say so and why.

The rest of the `evidence` bar replaces "boot the app and screenshot it" with what
actually proves a skill edit is correct: cross-references resolve, the contract
stays internally consistent, and manifests still parse. The failure mode here is a
dangling link to a renamed reference file or a rule that contradicts another
section — not a 500.

A worker on this repo should also:

- Keep every claim in a skill body traceable to a reference file or an ADR. A rule
  with no home is the thing that rots.
- Record a decision that reverses or narrows an earlier one as a new ADR under
  `orchestrator/docs/adr/`, rather than silently editing the old one.
- Bump `version` in `.claude-plugin/plugin.json` only when a user story finishes. The
  bump lands with the last child of the story, and never once per work item. Minor for a
  story that changed a contract or a dependency, patch for a docs-only story. A worker on
  one child leaves the version untouched. Two children that each bump pick the same
  number, and the merge then keeps one bump and loses the other.
