# Model registry

The frontier models the orchestrator supports, each with its **vendor**, the
**tuning profile** its prompt follows, and its **effort** range.

Prompt *content* is not defined here. The orchestrator composes every spawn and
review prompt through the **`prompt-improver` skill** (a dependency — see
[`requirements.md`](requirements.md)), which owns the per-model tuning rules. This
table only says which of that skill's model profiles applies.

Adversarial review requires the reviewer's **vendor** to differ from the
implementer's — this table is where the orchestrator looks up each side's vendor
to assert that.

| Model            | Vendor    | prompt-improver profile | Default effort | Notes |
|------------------|-----------|-------------------------|----------------|-------|
| `opus-5`         | anthropic | Claude Opus 5           | `high`         | Long-horizon agentic coding; give the full spec up front. Quality holds at `low`/`medium`. |
| `sonnet-5`       | anthropic | Claude Sonnet 5         | `high`         | Coding + agentic; literal instruction following. |
| `gpt-5.6-sol`    | openai    | Claude Opus 5           | `high`         | "sol" tier — closest to the Opus 5 profile. |
| `gpt-5.6-terra`  | openai    | Claude Sonnet 5         | `high`         | "terra" tier — closest to the Sonnet 5 profile. |

Notes:

- **Frontier only.** This version supports only the models above. A model not in this table is unsupported — the setup phase should reject it rather than guess a profile.
- **`gpt-5.6` alone is ambiguous** — it has two tiers. Config must name `gpt-5.6-sol` or `gpt-5.6-terra` so the profile is unambiguous.
- The **harness** decides how a model id becomes a `--model` flag value and how effort is expressed (see `harnesses/<h>.md`); this table is only about vendor, profile, and effort semantics — not the flag strings.

## Effort

Effort tunes how much the model **thinks** — capability against tokens and
latency. It does *not* shorten the visible response; prompt for length
separately (a `prompt-improver` shared rule).

| Effort   | Use |
|----------|-----|
| `max`    | Absolute maximum capability, no token constraint. Rare — a repeatedly-failed item. |
| `xhigh`  | The hardest coding/agentic work: multi-file features, migrations, large refactors. |
| `high`   | Default for both models. Balances tokens and intelligence. |
| `medium` | Cost-sensitive, well-specified work. Trades some intelligence. |
| `low`    | Short scoped tasks, latency-sensitive, not intelligence-sensitive. |

- **Keep thinking on.** Both models think by default; thinking-on at `low` effort beats thinking-off at similar cost. With thinking off, tool calls leak into visible text (never executed, and they poison later turns in an agentic loop) and internal XML tags appear. Never disable thinking for a worker.
- **Raise effort, don't prompt around it.** Shallow reasoning on a complex item → step effort up. Only if latency forces `low` add: `This task involves multistep reasoning. Think carefully through the problem before responding.`
- **Harness ceilings are real.** `codex` accepts only `minimal|low|medium|high` — an `xhigh`/`max` role under codex must be clamped to `high` and reported. Check the harness reference before promising an effort level.
- Migration mapping (if carrying over a 4.x/older default): Sonnet 5 `medium` ≈ Sonnet 4.6 `high`; Sonnet 5 `high` ≈ Sonnet 4.6 `max`. Don't inherit a previous model's effort default — pick from the job.

## Roles — the right model for the job

Config names a model **per role**, not one global model (see the `models:` block
in the config template). A role is a *class of job*, resolved per work item at
spawn time:

| Role     | Job | Typical setting |
|----------|-----|-----------------|
| `heavy`  | Multi-file feature, refactor, migration, schema change, or any item whose spec leaves real decisions open. | strongest model, `xhigh` |
| `light`  | Single-file/scoped edit, copy or config change, test-only work — fully enumerated acceptance criteria. | cheaper model, `medium` |
| `review` | The cross-vendor adversarial reviewer. Review accuracy holds at lower effort. | different-vendor model, `high` |

**Routing rule — default `heavy`, downgrade only on clear signals.** Pick `light`
only when *all* hold: one file or one component touched, no schema/migration and
no `db_gate` needed, no new dependency, and acceptance criteria fully enumerated
in the work item. Anything ambiguous stays `heavy` — a mis-sized `light` worker
under-thinks and burns a whole round trip, which costs more than the model
did. State the chosen role and effort when reporting a spawn, so a wrong call is
visible and correctable.

**Flat-config fallback.** A config with a single `model:` / `effort:` and no
`models:` block uses that pair for every role (and `review.model` for review, as
before).

## Cost profiles

Three preset `models:` blocks, cheapest to most capable. `/orchestrator-setup`
offers these instead of asking role-by-role; every one is still per-role routing,
so a `light` item never pays the `heavy` rate.

| Profile | heavy | light | review | Relative cost |
|---------|-------|-------|--------|---------------|
| **conservative** | `opus-5` @ `medium` | `sonnet-5` @ `low` | `gpt-5.6-terra` @ `medium` | ~1× |
| **balanced** (default) | `opus-5` @ `high` | `sonnet-5` @ `medium` | `gpt-5.6-terra` @ `high` | ~2–3× |
| **max-capability** | `opus-5` @ `xhigh` | `opus-5` @ `high` | `gpt-5.6-sol` @ `high` | ~5–8× |

**Read the multiplier as a range, not a number.** Effort changes how many tokens
the model *thinks*, and that varies per item — the same `xhigh` spawn costs far
more on an open-ended refactor than on a tightly-specced one. Treat the column as
ordering, and measure your own workload before budgeting from it.

Per-MTok list prices (input / output), for reasoning about the table above:

| Model | Vendor | Input | Output |
|-------|--------|-------|--------|
| `opus-5` | anthropic | $5 | $25 |
| `sonnet-5` | anthropic | $3 ($2 intro through 2026-08-31) | $15 ($10 intro) |
| `gpt-5.6-sol` / `gpt-5.6-terra` | openai | per OpenAI's published rates | — |

### Choosing a profile

- **conservative** — high-volume or well-specced work, or a personal-budget
  project. `opus-5` at `medium` still holds quality on most items; `sonnet-5` at
  `low` is for genuinely trivial ones. Expect a higher re-spawn rate: a `light`
  worker at `low` that under-thinks costs a whole round trip, which can exceed
  what the cheaper effort saved.
- **balanced** — the default, and the right answer unless you know otherwise.
  Both models at their own default effort.
- **max-capability** — migrations, security-sensitive work, anything where a
  missed bug costs more than the tokens. Note `light` runs `opus-5` here, so the
  cheap tier isn't cheap: pick this when correctness dominates, not as a default.

**Cheaper is not always cheaper.** The dominant cost in this system is a failed
round trip — a worker that under-thinks, gets caught in review, and re-spawns a
rung up pays for two spawns plus a review cycle. That's why the routing rule
defaults to `heavy` and why an ambiguous item should not be dropped to `light`
to save tokens. A fix round already steps effort up one rung, so a
`conservative` config that mis-routes converges on `balanced` pricing anyway —
with the extra latency.

**Effort is the lever, not the model.** Within a profile, moving `heavy` one rung
(`high` → `xhigh`) changes cost more than swapping which model runs `light`.
Tune effort first.

Profiles are a starting point, not a constraint — `docs/agents/orchestrator.md`
is human-editable, so set any `(model, effort)` pair per role directly.
