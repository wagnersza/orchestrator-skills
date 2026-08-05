# Harness: copilot (GitHub Copilot CLI)

## Launch command

```
copilot --allow-all <model-flag> <effort-flag>
```

- **Yolo flag:** `--allow-all` — all tools/paths/urls, no confirmation. Required.
- **Model flag:** `--model <model>` (`auto` lets Copilot pick). Verify the accepted ids against the installed version and map the frontier model ids here; if it can't pin the chosen model, have setup warn.
- **Effort flag:** `--effort <level>` (alias `--reasoning-effort`) — accepts `none | minimal | low | medium | high | xhigh | max`. Verified on GitHub Copilot CLI 1.0.75.

## Effort map

The orchestrator's whole ladder passes through unchanged (`low` … `max`), no clamping. Never pass `none` or `minimal` for a worker — a worker needs thinking on (see `../models.md`).

## Process pattern and context reset

Two facts the skill body reads from here, one per flow.

- **Process pattern** — the readiness gate's `--process` value: `(^|/)copilot$`. Measured
  on GitHub Copilot CLI 1.0.75: `ps -o comm=` returns `copilot` for a live worker, from
  the first moment the process exists.
- **Context reset** — the command sent before every re-prompt: `/new`. Measured on the
  same version, where the composer describes it as `Start a new conversation`. `/clear`
  and `/reset` are both there and both read `Abandon this session and start fresh`, so
  they discard the session rather than reset its context. `/compact` summarises rather
  than resets. `/new` is the one that keeps the worker and drops what it holds.

**A first-run dialog sits in front of both.** A fresh `copilot` asks `Do you trust the
files in this folder?` and `--allow-all` does not answer it. Measured on 1.0.78 in a new
directory: the choices are `1. Yes`, `2. Yes, and remember this folder for future
sessions`, and `3. No (Esc)`. A worker runs in a new worktree each time, so option 2 does
not carry over. So this harness takes the same conditional two-step send `codex` takes
([`../tools/orca.md`](../tools/orca.md#4a-send-in-two-steps-where-a-harness-needs-a-dialog-answered)).
The readiness gate does not cover this on its own. Behind the dialog the process is alive
in the worktree, so the gate reports ready while the composer is closed.

The gate is in the skill body and the check is one seam
([`../../docs/adr/0019-readiness-is-a-tool-agnostic-process-check.md`](../../docs/adr/0019-readiness-is-a-tool-agnostic-process-check.md)).
Why a re-prompt resets first:
[`../../docs/adr/0018-the-worker-watch-is-a-stateless-seam.md`](../../docs/adr/0018-the-worker-watch-is-a-stateless-seam.md).

## Notes

- Plain-English completion contract — no routed skill to invoke, no `TodoWrite`.
- The worker maintains the checklist file; the orchestrator reads it.
