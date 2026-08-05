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

## First-run dialogs — the yolo flag does not skip them

A fresh `codex` can sit behind **two** dialogs before it accepts any input, and on the
run that produced this section it showed both and then exited:

1. **Directory trust** — `Do you trust the contents of this directory?`
2. **Hooks review** — `Hooks need review`, where a hook is configured whose hash is
   not yet trusted.

`--dangerously-bypass-approvals-and-sandbox` governs command approvals **inside** a
session. It does not answer either dialog, so it does not get a worker to a composer.

**Trust is answered once per project root, then persisted** in `~/.codex/config.toml`:

```toml
[projects."<project-root>"]
trust_level = "trusted"
```

**Do not assume a subdirectory worktree inherits the main checkout's trust.** Measured
on `codex-cli` 0.146.0, `codex` resolves the project root from git, and for a **linked
worktree** that root is *the worktree itself*, not the repository the worktree belongs
to:

| Working directory | Project root codex resolved |
|-------------------|-----------------------------|
| the repository root | the repository root |
| a plain subdirectory of it | the repository root |
| a **linked git worktree** of it | **the linked worktree** |

A plain subdirectory does inherit. A linked worktree does not, and a linked worktree is
exactly what every worker runs in. So each new worktree is a new project root, with its
own unanswered trust dialog. Treat a first spawn in a fresh worktree as a dialog to
answer, never as trusted-by-inheritance.

The **hooks** dialog is keyed separately, by the hash of each hook entry
(`[hooks.state."<file>:<event>:<i>:<j>"]` with a `trusted_hash`), so it reappears
whenever a hook file changes rather than per project. `--dangerously-bypass-hook-trust`
runs enabled hooks without persisted trust for one invocation. It is a separate flag
from the yolo one, and it carries its own risk.

**This is why the readiness gate is a process check.** Behind either dialog, the
process is alive and the composer is closed, so `terminal read` reports
`status: running` and `terminal wait --for tui-idle` reports `satisfied: true`.
Measured: text sent to a dialog-blocked `codex` appeared **nowhere** in the read
buffer. So this harness is the one that needs the conditional split of op 4 — type the
prompt, confirm it is in the composer, then submit
([`../tools/orca.md`](../tools/orca.md#4a-send-in-two-steps-where-a-harness-needs-a-dialog-answered)).
Why the gate is a process check:
[`../../docs/adr/0017-gate-worker-readiness-on-a-process-check.md`](../../docs/adr/0017-gate-worker-readiness-on-a-process-check.md).

## Process pattern and context reset

Two facts the skill body reads from here, one per flow.

- **Process pattern** — the readiness gate's `--process` value: `(^|/)codex$`. Measured
  on `codex-cli` 0.146.0: `ps -o comm=` returns `codex` for a live worker. The gate catches
  the dialogs above at the point they cost a run. A dialog-blocked `codex` that then exits
  leaves the shell behind, and the gate reports not ready where a screen read reports
  running. While it sits at an open dialog the process is alive, so the gate reports ready.
  The two-step send is what protects the prompt there.
- **Context reset** — the command sent before every re-prompt: `/new`. Measured on the
  same version, where the composer describes it as `start a new chat during a
  conversation`. `/clear` exists too and it also clears the terminal, so `/new` is the
  narrower of the two. `/compact` summarises rather than resets, so it is not the reset
  command.

The gate is in the skill body and the check is one seam
([`../../docs/adr/0019-readiness-is-a-tool-agnostic-process-check.md`](../../docs/adr/0019-readiness-is-a-tool-agnostic-process-check.md)).
Why a re-prompt resets first:
[`../../docs/adr/0018-the-worker-watch-is-a-stateless-seam.md`](../../docs/adr/0018-the-worker-watch-is-a-stateless-seam.md).

## Startup noise that is not a failure

A `codex` worker can print these while booting normally. **None of them blocks the
model path**, so do not read one as a dead spawn or tear the worker down over it:

- `Failed to refresh token: refresh_token_reused` — repeated lines. Authentication is
  already valid for the session.
- MCP `HTTP 401` lines. One configured MCP server failed to authenticate. The harness
  runs without that server's tools.

The signal that a spawn worked is the startup header's `model:` and
`reasoning effort:` lines, plus the readiness gate. Judge the spawn on those two and
ignore the noise above.

## Notes

- Send the completion contract as **plain English** — spell out every checklist step in prose; no slash commands, no "TodoWrite" wording.
- The worker maintains the checklist file itself (told to in the prompt); the orchestrator reads it to monitor.
- **Preflight a fresh worktree for the dialogs above** before the first prompt. That is this harness's entry in the "preflight any harness-specific requirement the reference names" rule in the skill body's spawn step 2.
