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

## Process pattern and context reset

Two facts the skill body reads from here, one per flow.

- **Process pattern** — the readiness gate's `--process` value: `(^|/)pi$`. Measured on
  `pi` 0.74.0: `ps -o comm=` returns `pi` for a live worker, because the CLI sets its own
  process title. Anchor it. An unanchored `pi` matches about eight unrelated macOS
  processes, `MTLCompilerService` and `spindump` among them.
- **Context reset** — the command sent before every re-prompt: `/new`. Measured on the
  same version: it starts a new session, and the CLI prints `✓ New session started`.
  `/compact` summarises rather than resets, so it is not the reset command.

The gate is in the skill body and the check is one seam
([`../../docs/adr/0019-readiness-is-a-tool-agnostic-process-check.md`](../../docs/adr/0019-readiness-is-a-tool-agnostic-process-check.md)).
Why a re-prompt resets first:
[`../../docs/adr/0018-the-worker-watch-is-a-stateless-seam.md`](../../docs/adr/0018-the-worker-watch-is-a-stateless-seam.md).

## Notes

- Plain-English completion contract, same as codex — no routed skill to invoke, no `TodoWrite`.
- The worker maintains the checklist file; the orchestrator reads it.
