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
setup_cmd:  "python3 --version"   # stdlib-only test suite; nothing to install in the
                                  # worktree. The tests for scripts/close_item.py and
                                  # scripts/worker_state.py run under
                                  # `python3 -m pytest scripts/ -q`, which is what layer 2
                                  # and layer 3 both call. `python3 -m unittest discover
                                  # -s scripts -q` runs the same tests by hand.
                                  # No third-party runtime dependency: fixtures are local
                                  # git repos in a temp dir, no network, no agent runs.
run_recipe: ""            # no app to boot
ports:      ""            # no ports (nothing listens)
db_gate:    ""            # no database
evidence:   "`make quick` and `make full` green at the pushed HEAD, with the gate record line for each one. The two commands own the test suite now, so no separate run is quoted. `make deep` is blank on the `lite` profile, so it asks for nothing. Plus: the changed skill/reference read end to end for internal consistency, every cross-reference resolved (`scripts/test_links.py` runs inside both gate commands and proves this half, not a reading), and any manifest edit validated as JSON. For a change to a skill body, quote the before/after of each edited block in the review note."

# --- quality gates (the layered completion bar) ---
# The layer model and the Python gate matrix are in references/quality-gates.md.
# Config is the source of truth for a threshold.
gates:
  profile: lite           # layers 1 to 3 run; `lite` drops layer 4
  langs:   [python]       # plus Markdown, which has no gate matrix and no gate tool
  quick:   "make quick"   # layers 1 + 2 — format, lint, types, tests, complexity
  full:    "make full"    # layer 3 — the suite, import boundaries, secrets
  deep:    ""             # blank on `lite`, so the checklist drops the layer 4 box
  story:   "/improve-codebase-architecture"  # layer 5 — advisory, once per story
  thresholds:             # blank = no cap, so the tool's own default stands
    complexity: 16        # cyclomatic branches per function — pyproject.toml max-complexity
    cognitive:  ""        # the Python matrix declares no default
    funlen:     ""        # the Python matrix declares no default
    coverage:   ""        # both seams run as subprocesses, so line coverage reads 0%
    branch:     ""        # the Python matrix declares no default
    mutation:   ""        # layer 4 is off, so no runner reads a score
  infra:                  # every field blank; this repo provisions nothing
    plan_role:    ""      # blank = no plan gate
    policy_dir:   ""
    fixtures:     ""
    halt_on:      ""
    zero_changes: ""
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
- **gates** is the completion bar, and `references/quality-gates.md` holds the layer
  model and every default. The profile is `lite`, so layers 1 to 3 run and layer 4 is
  off. This repo is a documentation artifact plus two Python seams. A mutation score
  over that buys less than it costs. `deep` is blank, so the checklist drops its
  layer 4 box. Two thresholds are blank for a reason of their own, and this file
  names each reason. `coverage` is blank because the suite drives both seams through
  `subprocess`, and in-process line coverage reads 0%. `mutation` is blank because
  layer 4 is off. Layer 5 runs in the orchestrator session, in the main checkout, at
  the close of the last child of a story.

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
  install. `pytest` is a gate tool now. Layer 2 and layer 3 both run `python3 -m
  pytest scripts/ -q`, and the gate stops on a machine without it. `python3 -m
  unittest discover -s scripts -q` still runs the same tests by hand.
- **The two gate commands own the test suite.** `make quick` runs it as layer 2 and
  `make full` runs it as layer 3, so it runs on every item. No review note skips it.
  The gate tools install onto the machine and not into the worktree, so `setup_cmd`
  still installs nothing.

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
- Bump `version` in `.claude-plugin/plugin.json` when a user story finishes. The bump lands
  with the last child of the story, and never once per work item. Minor for a story that
  changed a contract or a dependency, patch for a docs-only story. The story sets that
  level, and the file types of its last child never change it. So a documentation-only last
  child of a contract-changing story still takes the minor. A worker on one child leaves the
  version untouched. Two children that each bump pick the same number, and the merge then
  keeps one bump and loses the other.
- A work item with no `user-story` parent bumps a patch, in its own branch. The condition is
  that the item changes what an installed session or a seam does. An item that changes only
  this repo's own files bumps nothing: `CLAUDE.md`, a page under `docs/`, an ADR, or a test.
  The rationale, the rejected release step and the collision between two standalone items
  are in [ADR 0050](../../orchestrator/docs/adr/0050-a-standalone-item-bumps-a-patch.md).
