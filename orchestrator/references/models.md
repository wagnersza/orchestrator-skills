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
