# Harness: claude (Claude Code)

The `claude` CLI. Runs a full-screen TUI (alt-screen), so `terminal read` tail is sparse — prefer the checklist file and the tool's idle-detection to tell busy from idle.

## Launch command

```
claude <model-flag> <effort-flag> <yolo-flag>
```

- **Yolo flag:** `--dangerously-skip-permissions` — required; without it the worker stalls at its first edit/bash gate forever.
- **Model flag:** `--model <id>` where `<id>` is the mapped value below.
- **Effort flag:** `--effort <level>` — `low | medium | high | xhigh | max`. Full range, no clamping needed. Omit to take the model default (`high`).

Verified against `claude --version` 2.1.220 (`claude --help`: `--effort <level>  Effort level for the current session (low, medium, high, xhigh, max)`), and both example commands below run clean.

**A bad effort value does not fail** — it warns and silently uses the default:

```
$ claude --model sonnet --effort superhigh -p hi
Warning: Unknown --effort value 'superhigh' — ignoring it and using the default effort. Valid values: low, medium, high, xhigh, max.
```

In a TUI worker that warning scrolls away and the item quietly runs at `high`. So validate the effort string against the ladder **before** composing `$CMD`; don't rely on the CLI to reject a typo.

## Model-id map

| Config model | `--model` value |
|--------------|-----------------|
| `opus-5`     | `opus`          |
| `sonnet-5`   | `sonnet`        |

(`gpt-5.6-*` are openai models — never launched under the claude harness. If config pairs them, that is a config error.)

## Example

`model: opus-5`, `effort: xhigh`, yolo on →

```
claude --model opus --effort xhigh --dangerously-skip-permissions
```

A `light`-role worker, `model: sonnet-5`, `effort: medium` →

```
claude --model sonnet --effort medium --dangerously-skip-permissions
```

## Process pattern and context reset

Two facts the skill body reads from here, one per flow.

- **Process pattern** — the readiness gate's `--process` value: `(^|/)claude$`. Measured
  on `claude` 2.1.220: `ps -o comm=` returns `claude` for a live worker, and returns the
  install's absolute path for the launcher process. So anchor the pattern at a path
  separator. A bare `claude` also matches this machine's `claude bg-pty-host` helper,
  which is a different process in a different directory.
- **Context reset** — the command sent before every re-prompt: `/clear`. This harness
  parses a slash command, so it gets the command itself and not a prose equivalent.

The gate is in the skill body and the check is one seam
([`../../docs/adr/0019-readiness-is-a-tool-agnostic-process-check.md`](../../docs/adr/0019-readiness-is-a-tool-agnostic-process-check.md)).
Why a re-prompt resets first:
[`../../docs/adr/0018-the-worker-watch-is-a-stateless-seam.md`](../../docs/adr/0018-the-worker-watch-is-a-stateless-seam.md).

## Notes

- Never disable thinking (`/effort` and the flag keep it on). Thinking-on at `low` beats thinking-off at similar cost, and thinking-off leaks tool calls as plain text — fatal in an unattended loop.
- Claude Code has `/implement`, `/ponytail:ponytail`, and `TodoWrite`. Those are commands a **human** can type. Which of them a **model** can invoke is what the preflight below asks. The orchestrator does **not** rely on `TodoWrite` for the completion contract — it uses the file-based checklist (see the skill body), which every harness supports. Claude workers may still use `TodoWrite` in addition, but the checklist file is the source of truth the orchestrator reads.
- **A claude worker does enter the routed skill, where the model can invoke that skill.** Where the verb resolved to a `worker` row of [`../skill-routing.md`](../skill-routing.md), the spawn prompt carries the invocation as a literal slash command. The worker's first act inside the worktree is to run it. This harness is the one that parses a slash command, so it gets the command and not the prose contract. Not *may* — the skill body words it as an imperative, and the reason is in [`../../docs/adr/0014-route-verbs-to-skills-in-two-lanes.md`](../../docs/adr/0014-route-verbs-to-skills-in-two-lanes.md). The skill runs inside the completion contract. It does not replace the checklist. **Where the model cannot invoke the skill, this harness takes the prose contract too** — the row's *Without slash commands* prose, in the place the slash command holds. A harness that parses a slash command is one fact. A model that can invoke the skill is a second one ([`../../docs/adr/0030-preflight-skill-reachability-before-routing.md`](../../docs/adr/0030-preflight-skill-reachability-before-routing.md)).
- Preflight the routed skill before the spawn. **Two halves, and both must hold.** The **plugin that ships it is installed** — that check is in [`../requirements.md`](../requirements.md), and a miss aborts the spawn rather than sending a dead prompt. And **the model can invoke the skill** — that check is [Preflight: can the model invoke this skill?](../skill-routing.md#preflight-can-the-model-invoke-this-skill), and a miss takes the prose fallback instead of aborting. Both rules are in the skill body's spawn step 2, and the spawn report names the branch it took.
