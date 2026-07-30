# Harness: cursor (cursor-agent)

The `cursor-agent` CLI — **not** the `cursor` editor.

## Launch command

```
cursor-agent --force --model '<model-id>'
```

- **Yolo flag:** `--force` — required.
- **Model + effort:** one flag. `cursor-agent` bakes effort **into the model id** — there is no separate `--effort`. Either use a pre-composed id (`claude-opus-5-thinking-xhigh`) or the parameterized form: `--model 'claude-opus-5[context=1m,effort=xhigh,fast=false]'` (quote it — brackets are shell globs).

## Model + effort map

Ids as listed by `cursor-agent --list-models` (verify after an upgrade — this catalog moves):

| Config model    | effort   | `--model` value |
|-----------------|----------|-----------------|
| `opus-5`        | `low`    | `claude-opus-5-thinking-low` |
| `opus-5`        | `medium` | `claude-opus-5-thinking-medium` |
| `opus-5`        | `high`   | `claude-opus-5-thinking-high` |
| `opus-5`        | `xhigh`  | `claude-opus-5-thinking-xhigh` |
| `opus-5`        | `max`    | `claude-opus-5-thinking-max` |
| `sonnet-5`      | `low`    | `claude-sonnet-5-thinking-low` |
| `sonnet-5`      | `medium` | `claude-sonnet-5-thinking-medium` |
| `sonnet-5`      | `high`   | `claude-sonnet-5-thinking-high` |
| `sonnet-5`      | `xhigh`  | `claude-sonnet-5-thinking-xhigh` |
| `sonnet-5`      | `max`    | `claude-sonnet-5-thinking-max` |
| `gpt-5.6-sol`   | `high`   | `gpt-5.6-sol-high` |
| `gpt-5.6-sol`   | `xhigh`  | `gpt-5.6-sol-xhigh` |
| `gpt-5.6-terra` | `low`…`max` | `gpt-5.6-terra-<effort>` |

- **Pick the `-thinking-` variant** for anthropic models — the non-thinking ids (`claude-opus-5-high`) run with thinking off, which leaks tool calls as plain text and is unsafe for an unattended worker.
- `-fast` suffixes exist for most ids (lower latency, higher price). Not used by default; opt in per project.
- `gpt-5.6-sol` currently lists only `high`/`xhigh` — an `sol` role asking `low`/`medium` has no id. Clamp to `high` and report it, or route that role to another harness.

## Example

`model: opus-5`, `effort: xhigh`, yolo on →

```
cursor-agent --force --model claude-opus-5-thinking-xhigh
```

## Notes

- Plain-English completion contract — no slash commands, no `TodoWrite`.
- The worker maintains the checklist file; the orchestrator reads it.
