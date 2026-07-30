# Requirements

What the orchestrator needs, when it's needed, how to check it, and how to
install it. Requirements are **conditional on config** — only the chosen tool,
the chosen harness(es), and the tracker apply. `/orchestrator-setup` reads the
config and checks exactly this set, then offers to install what's missing.

> Install commands marked **(verify)** are not pinned — confirm against the
> tool's own docs before running. The linked doc is the source of truth.

## Check commands

```bash
# binaries
for b in orca cmux herdr claude codex pi copilot cursor-agent gh glab playwright sqlite3 node npm uv; do
  printf "%-14s " "$b"; command -v "$b" || echo "(missing)"
done
# claude plugins
python3 -c "import json;p=json.load(open('$HOME/.claude/plugins/installed_plugins.json'))['plugins'];[print(k, 'OK' if k in p else 'MISSING') for k in ['mattpocock-skills@mattpocock','ponytail@ponytail']]"
# MCP servers configured for claude
python3 -c "import json;d=json.load(open('$HOME/.claude.json'));print('mcp:', list(d.get('mcpServers',{}).keys()))"
# playwright-cli skill (this repo)
ls playwright-cli/SKILL.md 2>/dev/null && echo "playwright-cli skill present"
```

## Always required

| Dep | Why | Check | Install |
|-----|-----|-------|---------|
| **git** | worktrees, branches | `command -v git` | preinstalled on macOS / `brew install git` |
| **mattpocock-skills** (plugin) | tracker config (`/setup-matt-pocock-skills`) + `to-tickets`/`to-spec` conventions the resolver reads | plugin check above | `claude plugin marketplace add mattpocock/skills && claude plugin install mattpocock-skills@mattpocock` — repo <https://github.com/mattpocock/skills> |
| **ponytail** (plugin) | keeps workers lazy/minimal; the completion contract references it | plugin check above | `claude plugin marketplace add DietrichGebert/ponytail && claude plugin install ponytail@ponytail` |
| **playwright-cli** (skill) | UI evidence screenshots the completion contract requires | `ls playwright-cli/SKILL.md` | shipped in this plugin; install browsers with `playwright install` (<https://playwright.dev>) |
| **codebase-memory-mcp** | code discovery for workers (search_graph, trace_path) | MCP check above | **manual** — no public package resolved; if a binary exists (e.g. `~/.local/bin/codebase-memory-mcp`), register it: `claude mcp add codebase-memory-mcp <path-to-binary>`. Otherwise install per its own docs, then `claude mcp add`. |
| **tracker CLI** | read the ready queue, claim items, post review notes | `command -v gh` **or** `command -v glab` | see tracker row below |

**Tracker CLI** depends on what `docs/agents/issue-tracker.md` names:

- **GitHub** → `gh` — <https://cli.github.com/> — `brew install gh`
- **GitLab** → `glab` — <https://gitlab.com/gitlab-org/cli> — `brew install glab`
- **Local markdown** → no CLI needed.

## Tool (pick one — config `tool`)

| Tool | Check | Install | Docs |
|------|-------|---------|------|
| **orca** | `command -v orca` | **(verify)** — Orca ships its own CLI installer, not brew | Orca docs / `orca --help` |
| **cmux** | `command -v cmux` | **(verify)** — on this machine it's in `/opt/homebrew/bin` | cmux docs |
| **herdr** | `command -v herdr` | **(verify)** | herdr docs |

Requires a running Orca runtime for orca (`orca open` first). The tool's reference
file (`references/tools/<tool>.md`) must be filled in for cmux/herdr before use.

## Harness (config `harness`, plus the harness for `models.review` if review is on)

| Harness | Check | Install | Docs |
|---------|-------|---------|------|
| **claude** | `command -v claude` | `npm install -g @anthropic-ai/claude-code` | <https://docs.claude.com/en/docs/claude-code> |
| **codex** | `command -v codex` | `npm install -g @openai/codex` **(verify)** or brew | <https://github.com/openai/codex> |
| **pi** | `command -v pi` | **(verify)** | pi docs |
| **copilot** | `command -v copilot` | **(verify)** — GitHub Copilot CLI | <https://docs.github.com/copilot> |
| **cursor** | `command -v cursor-agent` | **(verify)** — the agent CLI, not the editor | <https://cursor.com/> |

## Optional — enabled by project recipe

| Dep | Why | Check | Install |
|-----|-----|-------|---------|
| **DB CLI** (e.g. `sqlite3`) | the recipe's `db_gate` verify step | `command -v sqlite3` | preinstalled on macOS / `brew install sqlite` |
| **node/npm or uv** | the recipe's `setup_cmd` (`pnpm install`, `uv run …`) | `command -v npm` / `command -v uv` | <https://nodejs.org> / <https://docs.astral.sh/uv/> |

## Vendor keys

A worker needs the API access its harness/model uses (Anthropic for opus-5/
sonnet-5, OpenAI for gpt-5.6). Adversarial review spans **both** vendors, so a
cross-vendor setup needs both credentials configured for the respective
harnesses. The orchestrator doesn't manage keys — it assumes the harness CLIs are
already authenticated (`claude` logged in, `codex` authed, etc.).
