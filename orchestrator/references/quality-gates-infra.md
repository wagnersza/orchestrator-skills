# Infra quality gates

Four layers of checks answer one question: is this infrastructure change safe to apply. A
**Gate** is one check with one command and one exit code. A **Layer** is the band a Gate
runs in. A **Halt condition** is a policy that stops an infra plan before it applies. All
three terms are defined in [`../CONTEXT.md`](../CONTEXT.md).

These are different gates, and that is why they have a file of their own. An application
Gate reads code that exists. An infra Gate reads a plan for a change that has not happened
yet. There is no branch coverage on a resource graph, and there is no mutation score on a
manifest. What takes their place is **policy as code on the plan output**, plus a fixture
suite that proves each policy. The rationale is
[ADR 0049](../docs/adr/0049-infra-gates-are-policy-on-the-plan.md).

**Layer 5 is unchanged, and [`quality-gates.md`](quality-gates.md) owns it.** The story gate
reads module depth once per user story, and it stays advisory. An infra change reaches it in
the same way as any other change. So this file holds no row for layer 5 and changes nothing
about it.

## The infra layer model

| Layer | What runs | What it answers |
|---|---|---|
| 1 · static | `tofu fmt -check`, `tofu validate`, `tflint`, `trivy config`, the pin check | Is the code well formed, lint-clean and pinned? |
| 2 · policy | `conftest verify` over the policy directory and its fixtures | Do the rules themselves work? |
| 3 · plan | `tofu plan -detailed-exitcode`, then `tofu show -json` into `conftest test` | Does the plan match what already exists, and does it fire a **Halt condition**? |
| 4 · applied | apply to a dev stack, then plan again, then read the live inventory | Does it apply clean and stay clean? |

The order is cheapest first. Layer 1 reads the code alone. Layer 2 reads the policy files
and their fixtures. Layer 3 reads the account, and layer 4 writes to a dev stack. A worker
runs the layers in that order, so the cheapest answer arrives first.

The layer numbers hold across both files. The rule in
[A non-zero exit is a stop](quality-gates.md#a-non-zero-exit-is-a-stop) holds here too. No
infra Layer has a warning state, and a Gate exits 0 or it stops the work.

## The policy directory and the fixture directory

Two directories carry the model, and the `gates.infra` block of
[the config template](../../orchestrator-setup/orchestrator.template.md) names both.
`policy_dir` holds the rules and their tests. `fixtures` holds the saved plans that those
tests read.

```
policy/                      # gates.infra.policy_dir
  stateful.rego              # one rule file per Halt condition
  ownership.rego
  secrets.rego
  pins.rego
  cost.rego
  stateful_test.rego         # the deny case and the allow case for stateful.rego
  ownership_test.rego
  secrets_test.rego
  pins_test.rego
  cost_test.rego
fixtures/                    # gates.infra.fixtures
  stateful/deny.json         # a saved plan that the rule must deny
  stateful/allow.json        # a saved plan that the rule must pass
  ownership/deny.json
  ownership/allow.json
  secrets/deny.json
  secrets/allow.json
  pins/deny.json
  pins/allow.json
  cost/deny.json
  cost/allow.json
```

One rule file per Halt condition, and one test file beside it. A fixture is the JSON that
`tofu show -json` writes, saved to disk. So layer 2 reads a real plan with no account and no
network. The layer 2 command is `conftest verify --policy policy --data fixtures`.

## Every policy needs a deny fixture and an allow fixture

The pair is not optional. **A policy with no allow fixture can deny everything and still
look green.** A rule that denies every plan passes its deny fixture, so the deny half alone
proves nothing about the rule. The allow half is what proves that the rule reads the plan.

`conftest verify` is what proves the pair. It runs the test files in the policy directory,
so a missing half is a missing test and the layer 2 Gate reports it.

This is mutation testing in the shape that infra takes. It asks the same question, which is
whether the assertion asserts.

**The deny fixture lands before the policy.** A worker watches the rule fire on that fixture
first, and only then is the rule trusted. That is the same rule as a failing test
([ADR 0049](../docs/adr/0049-infra-gates-are-policy-on-the-plan.md)).

**This repo carries no `.tf` file, so it carries no policy and no fixture.** The pair rule is
proved by `conftest verify` in the target repo, and not by a test here. A fixture suite here
would test nothing real.

## The Halt conditions

`gates.infra.halt_on` names the list that a target repo enables. Each name has one rule file
behind it, and each rule file has its fixture pair.

| Halt condition | What fires it | Why it stops the plan |
|---|---|---|
| stateful delete or replace | a plan that deletes or replaces a resource that holds data | a refactor must not drop a database |
| foreign ownership | a plan that touches a resource that another repo owns | two stacks must not fight over one resource |
| inline secret | a plan that carries a secret value in a resource argument | a secret must not reach state |
| unpinned version | a provider, a module or a runtime with no exact version | a provider bump is a decision and not a surprise |
| cost delta | a plan whose monthly cost delta is more than the agreed figure | a change that triples the bill gets read before it merges |

A fired Halt condition is also one finding in an adversarial review, and that finding is
grounds for `request-changes` ([`../SKILL.md`](../SKILL.md)).

## The zero-changes rule

`tofu plan -detailed-exitcode` exits 2 when a diff exists. **The gate treats 2 as a stop, and
only 0 passes.** So a worker classifies every diff, and does not push it.

Exit 1 is an error in the plan itself, and it is a stop for the same reason. So layer 3
passes on exit 0 alone.

`gates.infra.zero_changes` names the target that a second plan must report with no change.
Layer 4 runs that second plan after the apply. A dev stack that reports a diff right after
its own apply holds a resource that the code does not describe.

## Layer 3 needs a cloud account, and layers 1 and 2 do not

Layers 1 and 2 read files. A worker gets both on a machine with no credential at all, so
most of the value costs no account.

Layer 3 answers "does this plan match what already exists". That question has no offline
answer, because the state of the account is the answer. So the plan reads the account. The
credential is a read-only plan role, and `gates.infra.plan_role` names it. **A blank
`plan_role` means no plan gate, and layers 1 and 2 still run.**

Layer 4 writes, so a read-only role is not enough for it. It runs against a dev stack, and
never against production.

## Why an emulator is rejected as the foundation

An emulator answers a different question. It says what the provider API accepts, and layer 3
asks what the account already holds.

The state of an emulator is empty until a test fills it. So every plan against an emulator
is a create plan, and the faults that matter are invisible. A delete of a resource that
holds data needs that resource to exist first. A resource that another repo owns needs that
other repo. A drift that somebody made by hand needs the account where they made it.

An emulator also carries drift of its own. It lags the provider, so a rule that passes
against the emulator can fail against the account. The gate then reports the emulator's
version of the truth.

So the read-only plan role is the foundation. The accepted risk is that layer 3 needs a
credential ([ADR 0049](../docs/adr/0049-infra-gates-are-policy-on-the-plan.md)). An emulator
stays available for a unit test of one module, and a unit test is not a Gate.

## The infra gate matrix — Terraform

| Gate | Hard threshold | Layer | Tool |
|---|---|---|---|
| format | 0 files to reformat | 1 | `tofu fmt -check` |
| validate | 0 errors | 1 | `tofu validate` |
| lint | 0 findings | 1 | `tflint` |
| misconfiguration | 0 findings at high severity or above | 1 | `trivy config` |
| version pins | 0 unpinned providers, modules or runtimes | 1 | `tflint` |
| policy fixtures | 0 failures over the deny and allow pairs | 2 | `conftest verify` |
| plan diff | exit code 0, so 0 changes | 3 | `tofu plan -detailed-exitcode` |
| halt conditions | 0 denials over the plan JSON | 3 | `conftest test` |
| cost delta | the agreed monthly figure | 3 | `infracost diff` |
| post-apply plan | exit code 0, so 0 changes after the apply | 4 | `tofu plan -detailed-exitcode` |
| live inventory | 0 resources that the refresh changes | 4 | `tofu plan -refresh-only` |

Every threshold in this matrix is a default. **Config is the source of truth for a
threshold**, so a maintainer raises one in one place
([ADR 0032](../docs/adr/0032-quality-gates-are-a-layered-contract.md)).

**The cost figure is the one threshold that config does not hold.** `gates.infra` has no key
for it, and `halt_on` names the condition alone. So the rule file `cost.rego` carries the
number, and a target repo agrees it there. A key for the figure lands with the column that
needs one ([ADR 0049](../docs/adr/0049-infra-gates-are-policy-on-the-plan.md)).

Every tool in the `Tool` column has a row in [`requirements.md`](requirements.md), with the
reason it is needed, a check command and an install command. A row that names a tool with no
such row fails
[`../../scripts/test_quality_gates.py`](../../scripts/test_quality_gates.py). So this matrix
cannot promise a tool that the repo has no install path for.

`tofu` is the OpenTofu CLI. A repo that runs `terraform` reads every row of this matrix with
that binary instead, because the two share the command surface these rows use.

Only the Terraform column lands here. The Kubernetes column shares this shape, and it is a
work item of its own.
