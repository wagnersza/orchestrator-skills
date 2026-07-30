# Role-based model + effort, not a hardcoded model

Config named one `model:` for every worker, and effort was never expressed at all
— so a copy tweak and a schema-changing multi-file feature ran the same model at
whatever effort the harness happened to default to. Both directions cost: the
strong model overspends on trivial items, the cheap one under-thinks hard ones and
burns a whole round trip, which costs more than the model did.

Config now names a `(model, effort)` pair per **Role** — `heavy`, `light`,
`review` — and the orchestrator classifies each work item into a role at spawn
time. Effort is a first-class dial (`low`…`max`), passed through the harness's own
mechanism.

## Considered Options

- **Role-based pairs in config, classified at spawn** (chosen) — the cost/quality
  tradeoff is a per-item decision, made where the item's shape is known, against a
  policy the project set once. Adding a role is a config + table edit.
- **Keep one global model, add a global effort** — simpler, but the effort of a
  one-file copy change and a migration are genuinely different numbers. Retained
  only as the flat-config fallback.
- **Let the worker pick its own effort** — a worker can't; effort is a launch-time
  flag, decided before the worker exists.
- **Infer the role from tracker labels** — rejected for now: it needs per-project
  label conventions the tracker config doesn't own. The signals in the routing
  rule (files touched, `db_gate`, enumerated criteria) are already readable from
  the work item.

## Consequences

- **Default heavy, downgrade only on clear signals.** Ambiguity resolves upward,
  because an under-thinking worker is the expensive failure.
- **Harnesses clamp.** `codex` accepts only `minimal|low|medium|high`; `pi` tops
  out at `xhigh`; `cursor-agent` encodes effort in the model id. Each harness
  reference carries its map, and the orchestrator **reports** any clamp rather than
  silently downgrading.
- **Thinking stays on** at every effort. Thinking-off leaks tool calls as plain
  text that never execute and then poison later turns — fatal in an unattended
  loop.
- **A fix round steps up a rung.** A finding the model missed at `high` is what
  `xhigh` is for.
- The spawn report names the role, model, and effort, so a wrong classification is
  visible and correctable in one sentence.
