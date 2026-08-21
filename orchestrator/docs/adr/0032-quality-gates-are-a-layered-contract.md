# Quality gates are a layered contract

A worker finishes a work item, and nothing can say whether the work is good.

The completion contract holds one box that reads `implement + self-test`, and the
`evidence` field asks for `real-data proof + full test suite passing`. Neither one names
a command, an exit code or a threshold. So a worker cannot fail the bar, and the
orchestrator session cannot read it. The bar is prose.

The cost lands after the push. Remote CI finds the lint fault, then the coverage fault.
One item takes three round trips, and it leaves `fix lint` commits in the history. A
fault a machine can find must not reach a human reviewer, and it must not reach a second
push.

## The decision

Four **Gate** layers run inside the worker worktree, before the push. Each layer is one
command and one exit code. A non-zero exit is a stop, and no layer has a warning state.

A fifth layer runs once per user story, on the last child, and it is advisory. It emits
candidate work items instead of an exit code, so it can never fail a push or a merge.

The five layers, the budget for each, and the threshold and tool per Gate live in one
reference file:
[`orchestrator/references/quality-gates.md`](../../references/quality-gates.md). Every
claim about a Gate traces there. The vocabulary lands with that file, in
[`orchestrator/CONTEXT.md`](../../CONTEXT.md): **Gate**, **Layer** and **Halt
condition**.

The output of `make deep` becomes the Evidence block of the review note. So the gate
output is the evidence, and the worker makes no claim a reviewer has to trust.

## Config is the source of truth for a threshold

A maintainer raises coverage in one place. The number lives in config, and setup writes
it into the tool config that reads it. So the number reaches the tool that reads it with
no hand step.

**Setup never rewrites a tool config it did not create.** Where that file already
exists, setup reports both values, asks which threshold is correct, and then writes only
that key. This narrows the existing rule in step 5 of `orchestrator-setup`, and it
narrows it to this extent alone.

The `gates:` block that carries the numbers lands with its own child of story #99. This
ADR is the rule that block obeys, so the rule exists before the block does.

## Considered Options

- **Four local layers plus an advisory fifth** (chosen) — the fast layer earns a run
  after every edit, and the slow layer runs once. One ladder, four exit codes, and the
  deep output is the evidence.
- **Leave the bar with remote CI** (rejected) — the state this ADR replaces. It costs
  three round trips per item and it writes `fix lint` commits into the history.
- **One command for every check** (rejected) — a command that takes five minutes is run
  once, at the end. The 1s layer is what makes the habit, and one command cannot hold two
  budgets.
- **A warning state per Gate** (rejected) — a warning is a report, and a report that
  does not stop is not a Gate. A warning nobody reads is the bar going back to prose.
- **Call the bands "tiers"** (rejected) — `_Avoid_: tier` already stands on **Role** and
  on **Cost profile** in [`orchestrator/CONTEXT.md`](../../CONTEXT.md). One word must not
  name three axes. Those two entries stay byte-identical.
- **Call layer 3 "the gauntlet"** (rejected) — it is a metaphor, and the three command
  names have to read as one ladder.
- **Keep each threshold in the tool config alone** (rejected) — a maintainer then edits
  five files to raise coverage, and no file holds the bar.
- **Let setup rewrite every tool config to match the threshold** (rejected) — it erases
  hand-tuned rules the maintainer wrote, and a repo cannot opt out of a rewrite it did
  not ask for.
- **Mirror remote CI with Docker or `act`** (rejected) — one script that CI also runs
  buys the same thing, with no container to build and no second install shape.

## Consequences

- **Enforcement is documentary, the same as the rest of this repo.** The checklist box
  and the review note are the whole guard. No hook and no script blocks a push. That is
  the posture of the **Browser surface** rule as well
  ([ADR 0012](0012-playwright-cli-is-the-only-browser-surface.md)).
- **A repo without a tool drops that Gate.** A layer whose config command is blank
  drops its checklist box before the checklist is sent. This repo has no mutation runner
  for Markdown, so it ships no layer 4 box, and that is a supported configuration.
- **Accepted risk: the Python thresholds are defaults nobody measured on a real repo.**
  85% of lines and a mutation score of 70% are starting numbers. A repo that cannot meet
  one lowers it in config, which is a supported answer and not a breach.
- **Accepted risk: the matrix can name a tool no machine can install.** One test closes
  half of that risk: every tool in the matrix has a row in
  [`orchestrator/references/requirements.md`](../../references/requirements.md). The
  test is `scripts/test_quality_gates.py`, and this ADR names it before it exists, in the
  same shape as the **Worker watch** seam. No test runs an install command, so a stale
  install command stays possible.
- **Accepted risk: two numbers can disagree.** A hand edit to a tool config can leave it
  out of step with config. Config wins by policy, and nothing checks it.
