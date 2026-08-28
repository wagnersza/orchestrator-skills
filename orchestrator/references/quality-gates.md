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

**The Story proof is not a Layer.** It runs once per user story, before layer 5, and the
layer table keeps its five rows. There is no layer 6 row because the layer numbers read as
a run order, and this step runs before layer 5. The **Commit slice** that adds the
generated Playwright spec also wires that spec into the project's own test command. So the
existing gate commands run that spec, and no new gate command exists. The term is the
**Story proof** entry of [`../CONTEXT.md`](../CONTEXT.md), and the rationale is
[ADR 0047](../docs/adr/0047-the-story-proof-runs-before-the-story-gate.md).

## A non-zero exit is a stop

No layer has a warning state. A Gate exits 0, or it stops the work, and the worker
corrects the fault before it pushes. A check that reports and does not stop is not a
Gate. Layer 5 is that case: it emits candidate work items, so it is a step and never a
Gate.

The output of `make deep` becomes the Evidence block of the review note. So the gate
output is the evidence, and the worker makes no claim a reviewer has to trust.

## The gate record

A gate run leaves a machine record behind. `hooks/record.py` appends one line per gate
run to `.orchestrator/gates-<item>.jsonl` in the worker's own worktree, beside the
**Checklist** it ticks. This file is the format's one home, and the **Gate record** entry
of [`../CONTEXT.md`](../CONTEXT.md) holds the term:

```json
{"command": "make quick", "exit": 0, "utc": "2026-08-21T09:14:02Z", "head_sha": "1b9f0c2"}
```

| Key | What it holds |
|---|---|
| `command` | the gate command that ran, as the `gates:` block of config names it |
| `exit` | the code that command returned |
| `utc` | when the run ended, as `YYYY-MM-DDTHH:MM:SSZ` |
| `head_sha` | the commit the run saw, from `git rev-parse HEAD`. A short sha reads as a prefix, so either form matches |

**`hooks/record.py` is the one writer.** A gate command runs and it exits. The hook reads
the exit code the harness reports and appends the line, so a green line proves that a
command exited zero rather than that a model said so. No gate script and no `Makefile`
writes the record, in this repo or in a repo `/orchestrator-setup` writes. The hook, its
event and the exception it holds in the plane law are in [`hooks.md`](hooks.md).

**The line is appended whatever the exit code is.** A red run that writes no line reads as
a run that never happened. So the record costs the worker no step of its own, and a worker
runs the gate and records nothing.

**The record is the third fact the Completion signal reads.** A ticked checklist, plus a
green line for every required layer at the current `HEAD`, is a finish. A missing line, a
malformed line, a non-zero exit or a stale `head_sha` fires the `gates-unproven` outcome
instead, and the item stops before review. Which layers are required is the spawn's
answer, and it passes them to the watch as a repeatable flag.

**A red record denies the push.** `hooks/refuse.py` reads this file before a `git push`
runs, and it asks one question per gate command Config names with a non-blank command: is
there a line with exit `0` at the current `HEAD`? The four answers that read as not green
are the four this section names, and the denial gives each failing gate the command that
repairs it. A blank command is not a Gate, so a dropped layer holds no push. The rule and the
message are in [`hooks.md`](hooks.md).

**A gate run outside a session writes no record.** CI and a human at a shell each run the
gate command with no harness that reads its exit code, so no hook fires. The record is a
fact about a worker's session, which is the only place the **Completion signal** reads it.
A push from a shell outside a session fires no hook either, so the block holds a worker
and never a maintainer.

Rationale, the rejected writers and the accepted gap where the hook can read no exit code:
[ADR 0052](../docs/adr/0052-a-gate-blocks-and-a-hook-writes-its-record.md). It supersedes
[ADR 0036](../docs/adr/0036-a-gate-run-is-work-product.md) on two claims: a gate run is no
longer work product, and the record no longer promises that nothing blocks a push.

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

## The application gate matrix — Go

`go.mod` in the repo root is the detection marker for the Go family. One hit turns this
column on.

| Gate | Hard threshold | Layer | Tool |
|---|---|---|---|
| formatting | 0 unformatted files | 1 | `gofmt`, `goimports` |
| strict type check | 0 errors, 0 warnings | 1 | `go build`, `go vet` |
| static lint | 0 warnings | 1 | `golangci-lint` |
| cyclomatic complexity | max 10 per function | 2 | `gocyclo` |
| cognitive complexity | max 8 per function | 2 | `gocognit` |
| function length | max 30 lines | 2 | `funlen` |
| unit tests | 100% pass, 0 retries | 2 | `go test -race` |
| BDD acceptance | 100% pass, 0 skipped | 2 | `godog` |
| line and branch coverage | over 85% and over 80% | 3 | `go test -cover` |
| import boundaries | 0 illegal, 0 cycles | 3 | `depguard`, `go-arch-lint` |
| secrets | 0 leaked | 3 | `gitleaks` |
| mutation score | over 70% mutants killed | 4 | `go-mutesting` |
| SAST | 0 high or critical | 4 | `gosec`, `semgrep` |
| dependency CVEs | 0 high or critical | 4 | `govulncheck` |

**`golangci-lint` is one binary and several Gates.** The `Tool` column names the linter
that answers each Gate, and not the command that runs it. So a reader maps a fault to one
row and guesses nothing. Which linter answers which row, and which Layer runs it:

| Gate | Linter | Layer |
|---|---|---|
| static lint | every linter the config enables, except the four that follow | 1 |
| cyclomatic complexity | `gocyclo` | 2 |
| cognitive complexity | `gocognit` | 2 |
| function length | `funlen` | 2 |
| import boundaries | `depguard` | 3 |

**One run per Layer.** `golangci-lint` runs once in each Layer of that table, with only
that Layer's linters on. So a complexity linter does not fire inside the one-second
budget of Layer 1. Layer 1 also does not wait for `depguard`.

The `gates.thresholds` keys of config reach this column through `.golangci.yml`:

| Config key | Where the number lands | Gate |
|---|---|---|
| `complexity` | the `gocyclo` setting of `.golangci.yml` | cyclomatic complexity |
| `cognitive` | the `gocognit` setting of `.golangci.yml` | cognitive complexity |
| `funlen` | the `funlen` setting of `.golangci.yml` | function length |
| `coverage` and `branch` | the Layer 3 coverage gate | line and branch coverage |

**One `thresholds` block serves every column.** So the mutation-score row of this column
states the same 70% the Python column states, and not a number of its own. A block per
family reverses that decision, and it needs an ADR of its own
([ADR 0032](../docs/adr/0032-quality-gates-are-a-layered-contract.md)).

**No soft fail.** Every linter in this column is on from the first commit, and no Go Gate
has a soft-fail setting. A soft-fail setting exists to carry a backlog, and a hard fail
from the first commit means no backlog forms.

## The application gate matrix — TypeScript

| Gate | Hard threshold | Layer | Tool |
|---|---|---|---|
| formatting | 0 unformatted files | 1 | `biome format` |
| strict type check | 0 errors, 0 warnings | 1 | `tsc --noEmit` |
| static lint | 0 warnings | 1 | `biome check`, `eslint` |
| cyclomatic complexity | max 10 per function | 2 | `eslint complexity` |
| cognitive complexity | max 8 per function | 2 | `eslint-plugin-sonarjs` |
| function length | max 30 lines | 2 | `eslint max-lines-per-function` |
| unit tests | 100% pass, 0 retries | 2 | `vitest --related` |
| BDD acceptance | 100% pass, 0 skipped | 2 | `@cucumber/cucumber` |
| line and branch coverage | over 85% and over 80% | 3 | `vitest --coverage` |
| import boundaries | 0 illegal, 0 cycles | 3 | `dependency-cruiser` |
| secrets | 0 leaked | 3 | `gitleaks` |
| mutation score | 70% of mutants killed | 4 | `stryker` |
| SAST | 0 high or critical | 4 | `semgrep` |
| dependency CVEs | 0 high or critical | 4 | `pnpm audit`, `trivy` |

**Two linters, split by speed.** `biome` owns format and the lint rules it implements,
because it is the fast one. `eslint` runs only the rules `biome` does not have. So layer
1 keeps its budget. The `Tool` cell of each row names the linter that answers it.

Each layer 2 cap maps to one `eslint` rule, so a reader traces a failure back to a row:

| Gate | `eslint` rule |
|---|---|
| cyclomatic complexity | `complexity` |
| cognitive complexity | `sonarjs/cognitive-complexity` |
| function length | `max-lines-per-function` |

**The strict type check row holds two halves.** `0 errors, 0 warnings` counts the
`tsc --noEmit` errors, and it counts the lint rule that bans an explicit `any` cast. A
type check that passes says nothing where the code casts to `any`. So the ban belongs
inside the row rather than beside it, and a green layer 1 means the types carry
information.

**Layer 2 runs the related tests, and layer 3 runs the full suite with coverage.**
`vitest --related` runs only the tests the change touches, so layer 2 keeps its budget
on a large package. The full suite is slower, so it belongs to layer 3 and its 30
seconds. The fast layer stays fast, and the slow one still runs before the push.

**`pnpm` is the documented package manager**, because the dependency CVE row runs
`pnpm audit`. A repo on `npm` or `yarn` substitutes its own audit command in the
`Makefile`, and no other row changes.

## What every column shares

Every threshold in a column here is a default. **Config is the source of truth for a
threshold**, so a maintainer raises coverage in one place and not in five tool configs
([ADR 0032](../docs/adr/0032-quality-gates-are-a-layered-contract.md)).

Every tool in a `Tool` column has a row in [`requirements.md`](requirements.md), with the
reason it is needed, a check command and an install command. A row that names a tool with no such row fails
[`../../scripts/test_quality_gates.py`](../../scripts/test_quality_gates.py). So no
column here can promise a tool the repo has no install path for.

The Kubernetes column is a work item of its own, and **the Terraform column lives in
[`quality-gates-infra.md`](quality-gates-infra.md)**, because an infra Gate reads a plan
and not code.
