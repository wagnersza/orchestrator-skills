# Harness: pi

The `pi` CLI. No approval gate — instead of a yolo flag, enable the tools the worker needs.

## Launch command

```
pi -t read,bash,edit,write,grep,find,ls --model <provider/id> --thinking <level>
```

- **Yolo flag:** none. `pi` has no approval prompt; `-t <tools>` enables the tool set that lets a worker act unattended. Enabling the tools **is** the yolo equivalent — required.
- **Model flag:** `--model <pattern>` — accepts a bare id, a `provider/id` pair, or `id:<thinking>` shorthand. `--provider <name>` sets the provider separately (default `google`). Run `pi --list-models` on the machine: the catalog is **account/provider-scoped**, so the frontier ids in `../models.md` may not be reachable at all.
- **Effort flag:** `--thinking <level>` — `off | minimal | low | medium | high | xhigh`. Equivalently `--model sonnet:high`.

## Effort map

| Config effort | pi `--thinking` | |
|---------------|-----------------|---|
| `max`         | `xhigh`         | **clamped** (no `max` level) — report it |
| `xhigh`       | `xhigh`         | |
| `high`        | `high`          | |
| `medium`      | `medium`        | |
| `low`         | `low`           | |

Never pass `off` or `minimal` for a worker — thinking off leaks tool calls as plain text (see `../models.md`).

## Model-id map

Not pinnable in general. `pi --list-models` on this machine showed only older Anthropic snapshots behind a Bedrock-style provider plus assorted OpenAI ids — **no** `opus-5` / `sonnet-5` / `gpt-5.6-*`. So:

- Setup must run `pi --list-models` and **warn** if the config's model isn't in the output; don't spawn a `pi` worker against a model it can't reach.
- Add concrete rows here once a machine has the frontier ids available, in the form `config model → provider/id`.

## Notes

- Plain-English completion contract, same as codex — no slash commands, no `TodoWrite`.
- The worker maintains the checklist file; the orchestrator reads it.
