# Labels drive the board; Projects v2 Status is a derived projection

The orchestrator moved work items by **label only** — `ready-for-agent` →
`in-progress` → `to-review` → closed — and never touched a GitHub Projects v2
`Status` field. On a board with `Backlog | Ready | In progress | In review | Done`
that means cards only move when a human drags them, and the two `Ready`-ish states
collapse: `ready-for-agent` with an open blocker and `ready-for-agent` with zero
blockers are indistinguishable on the board even though the ready queue treats them
as opposites.

**Labels stay the source of truth. `Status` is a projection of them**, written at
every place the skill already writes a label, with the ready-queue read doubling as
the reconcile pass that repairs drift. The derivation table and the board
coordinates (project number, `Status` field id, option ids, the two `gh` calls) live
in `docs/agents/issue-tracker.md` — the same file that owns the labels, per
ADR 0002.

This **narrows** ADR 0002's consequence that "the orchestrator does not define
work-state labels": it still doesn't define them, and it now derives a second,
non-authoritative surface from them. The label vocabulary and the board coordinates
both stay in the tracker config; nothing moves into the orchestrator's own config
(`docs/agents/orchestrator.md`), which is why board state is absent from it.

## Considered Options

- **Labels authoritative, board derived** (chosen) — one state machine. Label
  queries are cheap (`gh issue list --label`), work on a repo with **no** board at
  all, and are already the ready-queue gate. The board write is two `gh` calls and
  `gh project item-edit` is idempotent, so the reconcile pass is safe to run on
  every "what next?" and a consistent board costs nothing.
- **Board authoritative, ready queue on GraphQL** — rejected. It reads better in
  isolation (one surface, human drags are respected as intent) but it makes a
  Projects v2 board a hard dependency of the ready queue: every board-less repo
  loses `/orchestrator` entirely, and the resolver becomes a GraphQL query against
  `ProjectV2ItemFieldSingleSelectValue` that must still join back to labels for the
  blocker predicate. It also can't express `Backlog` vs `Ready`, because that split
  is a function of live blocker counts, not of anything stored on the card.
- **Both authoritative, reconciled on conflict** — rejected: two writers, no
  tiebreak. A human drag and a worker claim race, and the loser is silent.
- **A separate `/board-sync` command** — rejected as a redundant surface. Reading
  the ready queue is already the moment blocker counts are resolved, which is
  exactly what the `Backlog`/`Ready` split needs; reconciling there means drift is
  repaired by the flow the user runs most, with no command to remember.
- **A Python script or CLI wrapper for the write** — rejected. It is two `gh`
  invocations; a script would be a tool abstraction over a tool, against ADR 0002's
  posture, and would need its own tests and its own version.

## Consequences

- **A human drag is not intent, it's drift.** Moving a card by hand is overwritten
  on the next reconcile. The way to move an item is to change its label.
- **`Backlog` carries two meanings** — never triaged, and ready-but-blocked. That's
  accepted: both are "a worker cannot start this", which is what the column means
  operationally. `Ready` is precisely the ready queue.
- **The board can lag.** Nothing writes `Status` between transitions, so a blocker
  closing elsewhere doesn't promote `Backlog` → `Ready` until the next ready-queue
  read. Bounded by how often "what next?" runs, and repaired without a command.
- **No board is a supported configuration.** With no `## Project board` section in
  `issue-tracker.md`, every board write is a no-op and the orchestrator behaves
  exactly as before. Its absence is never an error.
- **Board coordinates are per-repo data, not skill logic.** `/orchestrator-setup`
  resolves the field and option ids live (`gh project field-list`) and writes them
  into `issue-tracker.md`; the skill body references them by name only, so a
  different board is a different config, not a skill change.
- **The worker writes its own card once.** The flip to the review state is the
  worker's own final checklist step, so the checklist template and the prompt
  contract carry the board move — as one box, not two, because a label that moves
  without its card is exactly the drift this ADR removes.
