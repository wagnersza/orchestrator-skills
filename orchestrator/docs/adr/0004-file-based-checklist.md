# File-based checklist instead of claude-only TodoWrite

Workers reliably finish the code then stall before opening the MR, leaving the item stuck in-progress with nothing pushed. The old fix leaned on Claude Code's `TodoWrite` — but that is claude-only (codex/pi/copilot/cursor have no equivalent) and lives in context that evaporates. To be harness-agnostic and durable, both the orchestrator and each worker keep a **file-based checklist**: markdown checkboxes at `.orchestrator/checklist-<item>.md` in the worktree root (gitignored, torn down with the worktree). The worker ticks each contract step as it completes it; the orchestrator reads the file to see exact progress and detect a stall (unchecked items + idle terminal → re-prompt with the remaining steps).

## Considered Options

- **File-based checklist, orchestrator reads it** (chosen) — works across every harness, survives context loss, gives the orchestrator reliable cross-harness stall detection.
- **TodoWrite in the prompt** — rejected: claude-only and non-durable.
- **Prompt-only, monitor via terminal/TUI** — rejected: no reliable cross-harness progress signal, which is the exact failure this fixes.

## Consequences

The completion contract is expressed as checklist items. The file is ephemeral run-state, not config or repo content — hence the worktree + gitignore placement.
