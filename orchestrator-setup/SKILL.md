---
name: orchestrator-setup
description: Set up the orchestrator in this repo, or change its setup. It interviews for the tracker, the three roles, max_workers and the base branch, installs every dependency, installs the worker skills into every harness the roles name, writes docs/agents/orchestrator.md, then runs the script's install. Use when the user says "set up the orchestrator", "configure orchestration for this repo", "orchestrator setup", "re-run orchestrator setup", or when the orchestrator skill finds no orchestrator-tick automation for this repo.
---

# Orchestrator setup

This skill asks the questions and installs the tools. `scripts/orchestrator.ts install`
makes the changes in the tracker and in orca: the labels, the orca Run, the
`orchestrator-tick` automation and one proof tick. A re-run is always safe, because every
step finds what is already there and keeps it.

The script is `scripts/orchestrator.ts` in this plugin, one directory above this skill's
own. Written below as `<plugin root>/scripts/orchestrator.ts`.

**Run this skill in the repo's main checkout, from a terminal inside Orca.** `install`
creates the orca Run, and orca refuses with `no_active_sender_terminal` in any other
terminal. Check that `$ORCA_TERMINAL_HANDLE` is set. If it is not, stop and ask the user to
open the repo in Orca and run setup from an Orca terminal.

Ask one question at a time, each with a recommended answer. Where
`docs/agents/orchestrator.md` already holds a JSON block, this is a re-run: offer each of
its values as the recommended answer.

## 1. Tracker

Read `docs/agents/issue-tracker.md`. If it is missing, mattpocock's
`setup-matt-pocock-skills` skill writes it. Where that skill is not installed, install it:

```sh
npx -y skills@latest add mattpocock/skills -s setup-matt-pocock-skills -a claude-code -g -y
```

That skill runs only when the user types it, so ask the user to run
`/setup-matt-pocock-skills`, and continue here once the file exists.

The file's heading names the tracker. Map it to the `tracker` field: GitHub is `github`,
GitLab is `gitlab`, and local markdown is `local`. Any other tracker is not supported, so
stop and say so. Do not ask the user for the tracker again.

## 2. Roles

Ask for a cost profile. It fills all three roles at once:

| Profile | heavy | medium | light |
|---|---|---|---|
| **balanced** (recommended) | `claude` `opus` `high` | `claude` `sonnet` `medium` | `claude` `sonnet` `low` |
| **economy** | `claude` `sonnet` `high` | `claude` `sonnet` `low` | `claude` `haiku` `low` |
| **quality** | `claude` `opus` `xhigh` | `claude` `opus` `high` | `claude` `sonnet` `medium` |

On `claude`, give the CLI's own aliases (`opus`, `sonnet`, `haiku`), because it refuses a
versioned id such as `sonnet-5`. Then ask whether to change any one role. An override
sets that role's `harness`, `model` or `effort`:

- `harness`: `claude`, `codex`, `cursor`, `pi` or `copilot`.
- `model`: an id the harness launches. `claude` launches only anthropic models, and
  `codex` launches only openai models.
- `effort`: `low`, `medium`, `high`, `xhigh` or `max`. `codex` runs `xhigh` and `max` as
  `high`, and `pi` runs `max` as `xhigh`.

## 3. Limits

Ask for `max_workers`, with `3` as the recommended answer. Then ask for the base branch.
The recommended answer is the remote's default branch,
`git symbolic-ref --short refs/remotes/origin/HEAD` without its `origin/` prefix. A new
clone may lack that ref, so run `git remote set-head origin -a` first, and fall back to
`main` where both fail.

## 4. Dependencies

Check each one, and install the missing ones. A check that still fails after its install
is a stop. Name the tool, and give the user the command to run.

| Needed for | Check | Install |
|---|---|---|
| orca | `orca --version` | the Orca app, which ships the CLI |
| this repo in orca | `orca repo list --json` lists the main checkout's path | `orca repo add --path <main checkout>` |
| Node ≥ 22.18 | `node --version` | `nvm install 24`, or the user's own Node manager |
| `tracker` `github` | `gh auth status` | `brew install gh`, then `! gh auth login` |
| `tracker` `gitlab` | `glab auth status` | `brew install glab`, then `! glab auth login` |
| harness `claude` | `command -v claude` | `npm install -g @anthropic-ai/claude-code` |
| harness `codex` | `command -v codex` | `npm install -g @openai/codex` |
| harness `cursor` | `command -v cursor-agent` | `curl https://cursor.com/install -fsS \| bash` |
| harness `pi` | `command -v pi` | `npm install -g @mariozechner/pi-coding-agent` |
| harness `copilot` | `command -v copilot` | `npm install -g @github/copilot` |

Check the CLI of each distinct harness across the three roles, and only those. The
`local` tracker needs no CLI. Each harness must also be logged in. A harness that is not
logged in fails its first worker, so ask the user to log it in (`! codex login`, for
example).

## 5. Skills into every harness

Every worker runs the mattpocock `implement` skill, which uses `tdd`, `code-review` and
`diagnosing-bugs`, and it writes its PR body with `pr`. Install all five into each
distinct harness across the roles, in one call. Give the `-a` value of each harness:

| Harness | `-a` value | Name in `skills list` |
|---|---|---|
| `claude` | `claude-code` | `Claude Code` |
| `codex` | `codex` | `Codex` |
| `cursor` | `cursor` | `Cursor` |
| `pi` | `pi` | `Pi` |
| `copilot` | `github-copilot` | `GitHub Copilot` |

```sh
npx -y skills@latest add mattpocock/skills -s implement tdd code-review diagnosing-bugs pr -a claude-code codex -g -y
```

Separate the values of `-s` and `-a` with spaces. The `skills` CLI reads `-s a,b` as one
skill named `a,b`, and it then installs nothing.

Then check that each harness lists all five. Give the `skills list` name of each harness:

```sh
npx -y skills@latest list -g --json | node -e '
const all = JSON.parse(require("fs").readFileSync(0, "utf8"));
const missing = process.argv.slice(1).flatMap((agent) =>
  ["implement", "tdd", "code-review", "diagnosing-bugs", "pr"]
    .filter((name) => !all.some((s) => s.name === name && s.agents.includes(agent)))
    .map((name) => `${name} is not listed for ${agent}`));
console.log(missing.length ? missing.join("\n") : "every harness lists the five skills");
process.exit(missing.length ? 1 : 0);' "Claude Code" "Codex"
```

A non-zero exit is a stop. Report the lines it printed.

## 6. Config, then install

Write `docs/agents/orchestrator.md` from [`orchestrator.template.md`](orchestrator.template.md),
with each `{{...}}` replaced by an answer. Keep the JSON valid. Add `.orchestrator/` to
`.gitignore` where it is missing, because the Run id and the tick lock live there.

Then run the install from the main checkout:

```sh
node <plugin root>/scripts/orchestrator.ts install
```

It prints one line per label, the Run and the automation, then the proof tick's lines.
Exit `0` and `the precheck works` mean the loop is live. Any other exit is a stop:
report its lines.

## 7. Report

Report the config block, the five-skill check for each harness, and the install's
output. Then tell the user how to start: label an issue `ready-for-agent`, and say
"work on N", or assign it to themself and wait for the next tick. The tick takes only an
issue assigned to them
([ADR 0006](../orchestrator/docs/adr/0006-the-tick-takes-only-what-is-assigned-to-me.md)).
