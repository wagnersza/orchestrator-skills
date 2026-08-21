# Quality gates

Five layers of checks answer one question: is this work item done. A **Gate** is one
check with one command and one exit code. A **Layer** is the band a Gate runs in.
Both terms are defined in [`../CONTEXT.md`](../CONTEXT.md).

Layers 1 to 4 run inside the **Worker**'s own worktree, before the push. Layer 5 runs
once per user story. Rationale, the rejected names and the accepted risk:
[ADR 0032](../docs/adr/0032-quality-gates-are-a-layered-contract.md).

## The layer model

| Layer | Command | Budget | What it answers |
|---|---|---|---|
| 1 · static | `make quick` | under 1s | Is the code formatted, typed and lint-clean? |
| 2 · tests and caps | `make quick` | under 10s | Do the tests pass, and is any function too complex? |
| 3 · whole repo | `make full` | under 30s | Is coverage at the bar, do the import boundaries hold, and is a secret committed? |
| 4 · deep | `make deep` | 1 to 5 min | Does the suite kill mutants, and does the code or a dependency carry a known risk? |
| 5 · architecture | `/improve-codebase-architecture` | advisory, once per story | Which module is too shallow to leave alone? |

Layers 1 and 2 share one command. `make quick` answers both questions, so its budget
is the sum of the two. The split is about habit rather than about the command. Layer 1
is what a worker runs after each edit, and layer 2 is what it runs before each commit.

The three names read as one ladder: `make quick`, `make full`, `make deep`. A project
maps each name to its own script through config, so no skill body names a tool.

## A non-zero exit is a stop

No layer has a warning state. A Gate exits 0, or it stops the work, and the worker
corrects the fault before it pushes. A check that reports and does not stop is not a
Gate. Layer 5 is that case: it emits candidate work items, so it is a step and never a
Gate.

The output of `make deep` becomes the Evidence block of the review note. So the gate
output is the evidence, and the worker makes no claim a reviewer has to trust.

## The gate record

A gate run leaves work product behind. Each gate command appends one line to
`.orchestrator/gates-<item>.jsonl` in the worker's own worktree, beside the **Checklist**
it ticks. This file is the format's one home, and the **Gate record** entry of
[`../CONTEXT.md`](../CONTEXT.md) holds the term:

```json
{"command": "make quick", "exit": 0, "utc": "2026-08-21T09:14:02Z", "head_sha": "1b9f0c2"}
```

| Key | What it holds |
|---|---|
| `command` | the gate command that ran, as the `gates:` block of config names it |
| `exit` | the code that command returned |
| `utc` | when the run ended, as `YYYY-MM-DDTHH:MM:SSZ` |
| `head_sha` | the commit the run saw, from `git rev-parse HEAD`. A short sha reads as a prefix, so either form matches |

**A gate command appends its line whatever the exit code is.** A red run that writes no
line reads as a run that never happened. The `Makefile` and the `scripts/checks.sh` that
`/orchestrator-setup` writes hold that append, so the record costs the worker no step of
its own.

**The record is the third fact the Completion signal reads.** A ticked checklist, plus a
green line for every required layer at the current `HEAD`, is a finish. A missing line, a
malformed line, a non-zero exit or a stale `head_sha` fires the `gates-unproven` outcome
instead, and the item stops before review. Which layers are required is the spawn's
answer, and it passes them to the watch as a repeatable flag.

**The record is not a second enforcement mechanism.** No hook blocks a push, and no
script rejects a commit. Rationale, and the risk that a line can be forged:
[ADR 0036](../docs/adr/0036-a-gate-run-is-work-product.md).

## The application gate matrix — Python

| Gate | Hard threshold | Layer | Tool |
|---|---|---|---|
| format | 0 files to reformat | 1 | `ruff` |
| lint | 0 findings | 1 | `ruff` |
| types | 0 errors, strict on | 1 | `mypy` |
| tests | 0 failures and 0 errors | 2 | `pytest` |
| complexity | 10 cyclomatic per function | 2 | `ruff` |
| coverage | 85% of lines | 3 | `coverage` |
| import boundaries | 0 broken contracts | 3 | `import-linter` |
| secrets | 0 findings | 3 | `gitleaks` |
| mutation score | 70% | 4 | `mutmut` |
| SAST | 0 findings at high severity | 4 | `bandit` |
| dependency CVEs | 0 known at high severity or above | 4 | `pip-audit` |

Every threshold above is a default. **Config is the source of truth for a threshold**,
so a maintainer raises coverage in one place and not in five tool configs
([ADR 0032](../docs/adr/0032-quality-gates-are-a-layered-contract.md)).

Every tool in the `Tool` column has a row in
[`requirements.md`](requirements.md), with the reason it is needed, a check command and
an install command. A row that names a tool with no such row fails
[`../../scripts/test_quality_gates.py`](../../scripts/test_quality_gates.py). So this
matrix cannot promise a tool the repo has no install path for.

Only the Python column lands here. The Go, TypeScript, Terraform and Kubernetes
columns are each a work item of their own.
