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
# This is plain `balanced`. This repo is markdown plus two small Python seams, so
# `light` carries most items and `heavy` is the exception. A spawn takes `light`
# unless a signal in the models note demands `heavy`. See `role_default`.
models:
  role_default: light     # this repo inverts the skill's default; see the models note
  heavy:                  # contract/vocabulary change, new skill, a seam plus its tests
    model:  opus-5
    effort: high
  light:                  # single-file reference or doc edit, fully enumerated criteria
    model:  sonnet-5
    effort: medium
  review:                 # the adversarial reviewer (see `review` below)
    model:  gpt-5.6-sol   # the openai tier closest to opus-5; codex launches it
    effort: high          # codex tops out at `high`, so no clamp applies

# --- adversarial review (optional) ---
review:
  enabled: false          # on -> spawn a cross-vendor reviewer at the review state
  rounds:  3              # max fix<->review cycles before handing to human review
                          # model+effort come from models.review; its vendor MUST
                          # differ from the impl role's

# --- the two roofs on live work (ADR 0045) ---
# The queue tick reads both, and the lower one wins. It starts nothing where either roof
# is full.
max_stories: 2            # live Story runs at once. A run holds its slot until the parent
                          # closes, story proof included
max_workers: 4            # live Workers across every run. The worst case is 4 workers, and
                          # never 2 times 4

# --- parallel spawn gate ---
parallel_check: touches   # touches | off -> compare declared Touch sets before a parallel
                          # spawn (ADR 0046). `off` compares nothing, which is today's
                          # behaviour. An item with no `## Touches` block runs alone under
                          # `touches`.

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
  a role at spawn time (`heavy` / `light`). The routing rule and the effort ladder
  live in `references/models.md`.
  - **`role_default: light` inverts that rule for this repo.** The skill defaults to
    `heavy` and drops to `light` on clear signals. It does this because its assumed
    repo is application code. There, a mis-sized worker costs a whole round trip.
    This repo is markdown skills plus two small Python seams. Here, a mis-sized
    `light` worker loses one cheap `sonnet-5` spawn. So the default is `light`, and
    `heavy` needs a signal. Take `heavy` only when one of these conditions is true:
    - The item changes a **contract**. This is a `CONTEXT.md` unit, a config schema,
      a close-transaction step, or a rule that a worker prompt depends on.
    - The item adds a **new skill**, or a new ADR that reverses an earlier one.
    - The item touches a **Python seam** (`scripts/*.py`) plus its test suite.
    - The item spans **three or more files across two or more skills**.
    - The item leaves a real decision open.
    - The item is a **re-spawn** after a failed round.

    Every other item is `light`. One reference edit, one ADR that adds a decision, a
    doc fix, a link repair, a table column, or one test file is `light`. Report the
    role on every spawn. A wrong call is then visible in one line.
  - **`light` is the answer unless a signal above says otherwise.** A run on `opus-5`
    costs several times the same run on `sonnet-5`, so a `heavy` call the item did not
    need is money spent for nothing. The six conditions above are the whole list. Where
    none of them is true, the spawn takes `light`, and a doubt is not a seventh
    condition. Say which condition fired on every `heavy` spawn, and take `light` where
    you can name none.
  - **Effort** tunes how much the model *thinks*: `low | medium | high | xhigh | max`.
    Both frontier models default to `high`, and `heavy` sits at that default. The rung
    above it is not gone. A re-spawn after a failed round steps up, so a genuinely hard
    item still reaches `opus-5` at `xhigh`. It is not the first guess.
  - The **harness clamps** what it can express — `codex` tops out at `high`,
    `pi` at `xhigh`, `cursor` bakes effort into the model id. `claude` (this
    config) reaches the whole ladder, so no clamp applies.
- **yolo** is always required for a worker (nobody approves its prompts). For
  `claude` that's `--dangerously-skip-permissions`.
- **review** is off. Run it on demand with "review #N adversarially" — that spawns
  a `gpt-5.6-sol` reviewer under `codex` (openai) against an `opus-5`/`sonnet-5`
  impl (anthropic), so the cross-vendor assertion holds. `codex` on this machine
  runs against the OLX GenAI proxy with an API key, and not against a ChatGPT
  login. So **the worker terminal needs `LLM_API_KEY` in its environment**, or the
  reviewer gets a `401` and no verdict arrives. Verified on 2026-09-01:
  `codex -c model_reasoning_effort="high" exec --model gpt-5.6-sol` prints
  `provider: olx-genai` and answers.
  **`gpt-5.6-sol` is the tier that matches the `opus-5` profile**, and the earlier
  `gpt-5.6-terra` matched `sonnet-5`. A reviewer below the implementer's profile
  reads a hard diff and reports nothing, so the review round costs money and
  proves nothing.
  **The story proof takes no harness of its own.** Its spawn reads the one
  `harness:` field above and the `heavy` role, so it cannot run under `codex`
  today. And no story here reaches that step, because `run_recipe` is blank.
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
- **`max_stories` and `max_workers` are the two roofs the queue tick reads.** The first
  bounds live **Story run**s, and the second bounds live **Worker**s across every run. The
  tick starts nothing where either one is full, so the lower roof wins. Two roofs exist
  because one of them alone fails. `max_stories` on its own multiplies into 2 runs times
  the worker cap, and the worker cap on its own lets one wide story starve every other. A
  run holds its **Story slot** until the parent closes, story proof included, so a story
  with one child left still occupies one
  ([ADR 0045](../../orchestrator/docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md)).
  The tick counts both from one tracker read. A live worker is an open item that wears
  `in-progress`, and a live story run is a `user-story` parent that wears a work-state
  label itself or has a descendant that does.
- **`parallel_check`** decides whether a **Touch set** gates a parallel spawn. With
  `touches`, the queue tick compares two candidates' `## Touches` blocks with
  `fnmatch`, and spawns them together only where the blocks are disjoint. An item
  with no block runs alone, because silence reads as risk. With `off`, the tick
  compares nothing and spawns every unblocked child, which is today's behaviour. A
  Touch set is a declaration and not a constraint: no gate reads a diff against it,
  so a wrong block costs one park and never a wrong merge
  ([ADR 0046](../../orchestrator/docs/adr/0046-parallel-spawn-is-gated-on-a-declared-touch-set.md)).

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
