# Infra gates are policy on the plan

An infra change has no gate that can catch what breaks production.

[ADR 0032](0032-quality-gates-are-a-layered-contract.md) gives five **Gate** layers, and
each one measures code. There is no branch coverage on a resource graph, and there is no
mutation score on a manifest. So the layers stop at format and lint on a `.tf` file.

The faults that matter are elsewhere. A plan can delete a stateful resource. A plan can
touch a resource that another repo owns. A plan can carry an inline secret value, or an
unpinned version. Each one of these faults is a sentence in a document today, and a
sentence cannot fail a run.

## The decision

**Policy as code on the plan output is what replaces coverage and mutation.** A rule reads
the JSON that `tofu show -json` writes, and it denies the plan or it passes it. A denial is
an exit code, so a rule in a document becomes a rule that a run obeys.

Four Layers carry that model, and they live in one reference file:
[`orchestrator/references/quality-gates-infra.md`](../../references/quality-gates-infra.md).
Every claim about an infra Gate traces there. The four Layers hold the same numbers as the
application Layers, so `make quick` and layer 1 mean the same band in both files.

**The application matrix file gains one cross-reference line, and no infra section.** These
are different gates, and one file that holds both stops being readable. The application file
is [`orchestrator/references/quality-gates.md`](../../references/quality-gates.md).

**A fired Halt condition is the stop, and the diff is not.** A **Halt condition** is a
policy that stops a plan before it applies, and
[`orchestrator/CONTEXT.md`](../../CONTEXT.md) holds the term. The infra reference file holds
the five conditions and one rule file per condition.

**The zero-changes rule stands beside the conditions.** `tofu plan -detailed-exitcode` exits
2 when a diff exists. The gate treats 2 as a stop, and only 0 passes. So a worker classifies
every diff, and does not push it.

**Layer 5 is unchanged.** The story gate reads module depth once per user story, and it stays
advisory ([ADR 0033](0033-the-story-gate-is-advisory.md)). An infra change reaches it in the
same way as any other change.

## Test-first applies to policy

**The deny fixture lands first, and the policy comes after it.** A worker watches the policy
fire on that fixture. Only then is the policy trusted. This is the same rule as a failing
test, in the shape that infra takes.

**Then the allow fixture proves that the rule denies something and not everything.** A
policy with no allow fixture can deny every plan and still look green. So the pair is not
optional, and `conftest verify` is what proves the pair.

A policy that nobody watched fail is a rule with no evidence behind it. Nothing then says
that the rule reads the plan.

## Considered Options

- **Policy as code on the plan output** (chosen) — the plan holds the effect of the change.
  So a rule that reads the plan reads the effect. The output is JSON, and one tool
  (`conftest`) covers both the rules and the tests for those rules.
- **An emulator as the foundation** (rejected) — an emulator answers a different question. It
  says what the provider API accepts, and layer 3 asks what the account already holds. The
  state of an emulator is empty until a test fills it, so every plan against it is a create
  plan. A delete of a stateful resource, a resource that another repo owns and a hand-made
  drift are all invisible there. An emulator also lags the provider, so a rule that passes
  against the emulator can fail against the account.
- **Lint and format alone, with no plan gate** (rejected) — this is the state that this ADR
  replaces. It catches a badly formatted file and it misses a deleted database.
- **A cost report with no threshold** (rejected) — a check that reports and does not stop is
  not a Gate ([ADR 0032](0032-quality-gates-are-a-layered-contract.md)). A cost delta needs
  an agreed figure, or nobody reads the report.
- **An infra section inside the application matrix file** (rejected) — the application matrix
  answers "is this code good", and the infra matrix answers "is this change safe to apply".
  One file with both sections makes a reader of either one read the other.
- **A deny fixture per policy, and no allow fixture** (rejected) — a rule that denies every
  plan passes its deny fixture. So the deny half alone proves nothing about the rule.
- **The policy first, and the fixtures after it** (rejected) — the worker then trusts a rule
  that nobody watched fire. That is the state that a failing test exists to prevent.
- **A hook or a script that rejects the push** (rejected) — enforcement in this repo is
  documentary. The checklist box and the review note are the whole guard
  ([ADR 0032](0032-quality-gates-are-a-layered-contract.md)).

## Consequences

- **Accepted risk: layer 3 needs a cloud credential.** The question "does this plan match
  what already exists" has no offline answer. So the highest-value Layer is the one that
  needs an account. The credential is a read-only plan role, and `gates.infra.plan_role`
  names it. A blank `plan_role` means no plan gate, and layers 1 and 2 still run. So a repo
  with no account keeps most of the value.
- **Accepted risk: the fixture-pair rule has no test in this repo.** This repo carries no
  `.tf` file, so a fixture suite here would test nothing real. `conftest verify` in the
  target repo is what proves the pair.
- **Named limit: config holds no key for the cost figure.** The `gates.infra` block names
  the condition in `halt_on`, and it holds no number. So the rule file that reads the cost
  delta carries the figure, and that one threshold sits outside config. A key for it lands
  with the column that needs one, and not before.
- **Accepted risk: a saved plan fixture ages.** A fixture is a plan from one day against one
  account. The provider schema moves, and nothing here re-records the fixture. A stale
  fixture can pass a rule that a live plan breaks.
- **Accepted risk: the matrix can name a tool that no machine can install.** One test closes
  half of that risk. Every tool in the infra matrix has a row in
  [`orchestrator/references/requirements.md`](../../references/requirements.md), and
  `scripts/test_quality_gates.py` reports each tool with no such row. No test runs an
  install command, so a stale install command stays possible.
- **This repo never enables the plan gate.** It provisions nothing, so every field of
  `gates.infra` stays blank here. The reference file is a contract for a target repo, and
  `github.com/harumi-io/harumi-infra` is where that contract runs.
- **The Kubernetes column shares this shape.** It reads a manifest instead of a plan, and it
  uses the same tool. That column is a work item of its own, and this ADR is the rule that it
  obeys.
