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

## Notes

- Plain-English completion contract — no slash commands, no `TodoWrite`.
- The worker maintains the checklist file; the orchestrator reads it.
