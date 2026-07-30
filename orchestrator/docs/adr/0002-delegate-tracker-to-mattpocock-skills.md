# Delegate tracker config to the mattpocock engineering skills

The orchestrator needs a work-item tracker (find ready work, claim it, post review notes, flip states) but the mattpocock engineering skills this project already depends on (`to-tickets`, `to-spec`, `triage`, `/setup-matt-pocock-skills`) already own a tracker abstraction over GitHub / GitLab / local markdown, configured per-repo in `docs/agents/issue-tracker.md`. Rather than build a second tracker abstraction, the orchestrator **reuses that config**: it reads `docs/agents/issue-tracker.md` for the CLI and label vocabulary, and if the file is missing, calls `/setup-matt-pocock-skills` to create it.

## Considered Options

- **Reuse mattpocock config** (chosen) — one tracker abstraction in the ecosystem, single source of truth for tracker CLI + label vocabulary, no duplication.
- **Own tracker abstraction in the orchestrator** — rejected: duplicates work the dependency already does and would drift from the skills that create the tickets.
- **Vendor + adapt a mattpocock skill** — allowed only as a last resort: copy the skill into this repo and adjust its description so the orchestrator picks up the copy. Avoid unless a change is genuinely required.

## Consequences

The orchestrator does not define work-state labels — it reads them from `issue-tracker.md`. The ready-queue resolver (find unblocked `ready-for-agent` items, walk `## Blocked by` / `## Parent` edges from the `to-tickets` template) stays orchestrator logic but is driven by the configured tracker CLI, so a new tracker is a new `issue-tracker.md`, not a skill change.
