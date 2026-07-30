# Harness: codex

The `codex` CLI (OpenAI). Plain task prompts only — no `/implement`, no `TodoWrite`, no slash skills. The file-based checklist replaces all of that.

## Launch command

```
codex <effort-flag> <model-flag> <yolo-flag>
```

- **Yolo flag:** `--dangerously-bypass-approvals-and-sandbox` — required.
- **Model flag:** `--model <id>` (short: `-m`).
- **Effort flag:** no dedicated flag — pass the config override `-c model_reasoning_effort="<level>"`.

## Effort — clamped range

`codex-cli` 0.38.0 accepts **only** `minimal | low | medium | high`. Verified:

```
$ codex -c model_reasoning_effort="bogus" exec "hi"
Error: unknown variant `bogus`, expected one of `minimal`, `low`, `medium`, `high`
in `model_reasoning_effort`
```

Mapping from the orchestrator's effort ladder:

| Config effort | codex value | |
|---------------|-------------|---|
| `max`         | `high`      | **clamped** — report it |
| `xhigh`       | `high`      | **clamped** — report it |
| `high`        | `high`      | |
| `medium`      | `medium`    | |
| `low`         | `low`       | |

A `heavy` role asking `xhigh` under codex silently becomes `high`. Say so when reporting the spawn; if the item genuinely needs the top of the ladder, spawn it under a harness that reaches `xhigh` (claude, copilot, cursor) instead. Re-check the accepted variants after a `codex` upgrade — this list is version-pinned.

## Model-id map

| Config model    | `--model` value |
|-----------------|-----------------|
| `gpt-5.6-sol`   | `gpt-5.6-sol`   |
| `gpt-5.6-terra` | `gpt-5.6-terra` |

(Anthropic models are not launched under codex.)

## Example

Interactive (how a worker is launched) — `model: gpt-5.6-terra`, `effort: high`, yolo on →

```
codex -c model_reasoning_effort="high" --model gpt-5.6-terra --dangerously-bypass-approvals-and-sandbox
```

## Flag placement — `--model` before a subcommand is silently dropped

`-c` is global, but `--model` binds to the subcommand. With `exec` in the line,
`--model` **must come after it** or codex ignores it and runs its own default with
no error:

```
$ codex -c model_reasoning_effort=high --model gpt-5.6-terra exec ... "hi"
model: gpt-5-codex          # <- wrong model, silently
reasoning effort: high

$ codex -c model_reasoning_effort=medium exec --model gpt-5.6-terra ... "hi"
model: gpt-5.6-terra        # <- correct
reasoning effort: medium
```

The startup header prints `model:` and `reasoning effort:` — read it once after a
spawn to confirm both landed, and re-order rather than trusting the flag position.

## Notes

- Send the completion contract as **plain English** — spell out every checklist step in prose; no slash commands, no "TodoWrite" wording.
- The worker maintains the checklist file itself (told to in the prompt); the orchestrator reads it to monitor.
