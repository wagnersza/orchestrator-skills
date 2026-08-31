# Requirements

What the orchestrator needs, when it's needed, how to check it, and how to
install it. Requirements are **conditional on config** — only the chosen tool,
the chosen harness(es), and the tracker apply. `/orchestrator-setup` reads the
config and checks exactly this set, then offers to install what's missing.

> Install commands marked **(verify)** are not pinned — confirm against the
> tool's own docs before running. The linked doc is the source of truth.

## Keeping them current

`/orchestrator-setup` step 0a runs this before anything else, on every invocation.
A stale plugin cache routes to reference files that no longer exist, so this is not
optional maintenance:

```bash
claude plugin list                        # read the exact plugin@marketplace ids
claude plugin marketplace update          # all marketplaces
claude plugin update orchestrator-skills@wsza        # then each installed plugin
claude plugin update mattpocock-skills@claude-plugins-official
claude plugin update ponytail@ponytail
claude plugin update prompt-improver@prompt-improver
# only if prompt-improver was installed the legacy way (git clone, no plugin entry)
[ -d ~/.claude/skills/prompt-improver/.git ] && \
  git -C ~/.claude/skills/prompt-improver pull --ff-only
# simple-english is a skills-CLI install, so `claude plugin update` does not apply
npx skills update simple-english -g -y      # add -p instead of -g for a project install
# playwright-cli is an npm global package, not a plugin — and the browsers are separate
npm update -g @playwright/cli && npx playwright install
```

**Use the full `plugin@marketplace` id** — a bare name fails (`Plugin "<name>" not
found`, exit 1). `claude plugin list` is the source of truth for the ids: update
what it actually lists, and use the clone-pull line only for a `prompt-improver`
that isn't listed there.

**A plugin update needs a session restart** to take effect — until then the loaded
skill body is still the old one. Harness and tracker CLIs update through their own
package manager (`brew upgrade gh glab`, `npm update -g @anthropic-ai/claude-code`),
which needs no restart.

## Check commands

```bash
# binaries
for b in orca cmux herdr claude codex pi copilot cursor-agent gh glab playwright-cli sqlite3 node npm uv; do
  printf "%-14s " "$b"; command -v "$b" || echo "(missing)"
done
# claude plugins
python3 -c "import json;p=json.load(open('$HOME/.claude/plugins/installed_plugins.json'))['plugins'];[print(k, 'OK' if k in p else 'MISSING') for k in ['mattpocock-skills@claude-plugins-official','ponytail@ponytail','prompt-improver@prompt-improver']]"
# MCP servers configured for claude
python3 -c "import json;d=json.load(open('$HOME/.claude.json'));print('mcp:', list(d.get('mcpServers',{}).keys()))"
# playwright browser binaries — a separate requirement from the CLI above
ls -d "${PLAYWRIGHT_BROWSERS_PATH:-$HOME/Library/Caches/ms-playwright}"/chromium-* 2>/dev/null \
  | head -1 || echo "playwright browsers: MISSING"
# prompt-improver — any of three install shapes satisfies it. Print which:
claude plugin list 2>/dev/null | grep -o 'prompt-improver@[a-z-]*' || \
  ls ~/.claude/skills/prompt-improver/SKILL.md .claude/skills/prompt-improver/SKILL.md 2>/dev/null || \
  echo "prompt-improver: MISSING"
# simple-english — global or project install, each with two paths. Print every hit:
ls ~/.agents/skills/simple-english/SKILL.md ~/.claude/skills/simple-english/SKILL.md \
   .agents/skills/simple-english/SKILL.md .claude/skills/simple-english/SKILL.md 2>/dev/null \
  | grep . || echo "simple-english: MISSING"
# the plugin root — where this plugin's own two seams live. Both install shapes, newest
# cache install first, then a clone. Prints the root, then proves the seam runs from here:
PLUGIN_ROOT=$(python3 -c "import pathlib;h=pathlib.Path.home()/'.claude/plugins';c=list(h.glob('cache/*/orchestrator-skills/*/scripts/worker_state.py'))or list(h.glob('marketplaces/*/scripts/worker_state.py'));print(max(c,key=lambda p:p.stat().st_mtime).parents[1] if c else '')")
python3 "$PLUGIN_ROOT/scripts/worker_state.py" ready --help >/dev/null \
  && echo "plugin root: $PLUGIN_ROOT" || echo "plugin root: MISSING"
# resolving-merge-conflicts — ships inside mattpocock-skills, plus two standalone
# shapes. Print every hit:
ls ~/.claude/plugins/cache/*/mattpocock-skills/*/skills/engineering/resolving-merge-conflicts/SKILL.md \
   ~/.claude/plugins/marketplaces/*/skills/engineering/resolving-merge-conflicts/SKILL.md \
   ~/.claude/skills/resolving-merge-conflicts/SKILL.md \
   .claude/skills/resolving-merge-conflicts/SKILL.md 2>/dev/null \
  | grep . || echo "resolving-merge-conflicts: MISSING"
```

## Always required

| Dep | Why | Check | Install |
|-----|-----|-------|---------|
| **git** | worktrees, branches | `command -v git` | preinstalled on macOS / `brew install git` |
| **mattpocock-skills** (plugin) | tracker config (`/setup-matt-pocock-skills`) + `to-tickets`/`to-spec` conventions the resolver reads | plugin check above | `claude plugin install mattpocock-skills@claude-plugins-official` — the `claude-plugins-official` marketplace ships with Claude Code, so no `marketplace add` step comes first. Repo <https://github.com/mattpocock/skills> |
| **prompt-improver** (plugin) | **owns all worker/review prompt composition** — the per-model tuning rules and the code-review coverage rule. The orchestrator drafts a prompt and runs it through this skill; it holds no prompting rules of its own | plugin check above, **or** the clone fallback in the check block | `claude plugin marketplace add wagnersza/prompt-improver && claude plugin install prompt-improver@prompt-improver` — repo <https://github.com/wagnersza/prompt-improver>. Auto-loads next session (`/reload-plugins` picks it up now). No dependencies of its own. |
| **ponytail** (plugin) | keeps workers lazy/minimal; the completion contract references it | plugin check above | `claude plugin marketplace add DietrichGebert/ponytail && claude plugin install ponytail@ponytail` |
| **simple-english** (skill) | **owns all writing rules for prose deliverables** — a worker runs the prose it changed through this skill before it commits, and the orchestrator applies the skill to its own reports. This repo restates no rule of the standard, only when to invoke it (see `../CONTEXT.md`) | `simple-english` check above | `npx skills add AminBlg/SimpleEnglish --global --all` — the [`skills` CLI](https://skills.sh), so it needs `node`/`npx` and network access. Repo <https://github.com/AminBlg/SimpleEnglish>, MIT, no dependencies of its own. Not a Claude plugin marketplace install, so it carries no pin (ADR 0011) |
| **resolving-merge-conflicts** (skill) | **owns the merge-conflict procedure**, for the maintainer who asks for it. No flow reaches it, because the merge is the maintainer's own act on the tracker. This repo states only *when* to invoke it (see `../CONTEXT.md`) | `resolving-merge-conflicts` check above | ships inside **mattpocock-skills**, so the plugin install above already provides it: `claude plugin install mattpocock-skills@claude-plugins-official`. Nothing separate to install. Rationale: [`../docs/adr/0057-the-merge-is-the-second-act.md`](../docs/adr/0057-the-merge-is-the-second-act.md) |
| **playwright-cli** (CLI) | the **only sanctioned browser surface** for a worker — the UI proof the `evidence` bar asks for runs through it (see `../CONTEXT.md`) | `command -v playwright-cli` | `npm install -g @playwright/cli` — the npm global package, so the update command is `npm update -g @playwright/cli`, never brew. Steps, verification and failure modes: [`../../playwright-cli/references/installation.md`](../../playwright-cli/references/installation.md) |
| **playwright browsers** | the browser builds the CLI drives — a second requirement, because a machine can have the CLI and no browsers | browser check above | `npx playwright install` (<https://playwright.dev>). Run it again after a CLI update. A new CLI can want a newer build than the cache holds |
| **codebase-memory-mcp** | code discovery for workers (search_graph, trace_path) | MCP check above | **manual** — no public package resolved; if a binary exists (e.g. `~/.local/bin/codebase-memory-mcp`), register it: `claude mcp add codebase-memory-mcp <path-to-binary>`. Otherwise install per its own docs, then `claude mcp add`. |
| **tracker CLI** | read the ready queue, claim items, post review notes | `command -v gh` **or** `command -v glab` | see tracker row below |

**`prompt-improver` has three install shapes, and all three work.** The skill body
is identical in each, and the orchestrator invokes the skill rather than a path, so
**an existing install is never broken and never needs migrating.** What differs is
only how you update it:

| Shape | `claude plugin list` shows | Update with |
|-------|----------------------------|-------------|
| **Plugin** (preferred on a fresh install) | `prompt-improver@prompt-improver` | `claude plugin update prompt-improver@prompt-improver` |
| **Clone auto-registered from the skills dir** | `prompt-improver@skills-dir` | `git -C ~/.claude/skills/prompt-improver pull --ff-only` |
| **Project-level clone** (`<repo>/.claude/skills/`) | nothing | `git -C <repo>/.claude/skills/prompt-improver pull` |

**`@skills-dir` is a clone, not the plugin.** A clone under `~/.claude/skills/` is
auto-registered under that marketplace name, so it *appears* in `claude plugin
list` — but `claude plugin update prompt-improver@prompt-improver` fails on it
(`Plugin not found`, exit 1) and it is absent from
`~/.claude/plugins/installed_plugins.json`. Read the suffix before choosing an
update command, and don't install the plugin on top of a clone — that leaves two
copies shadowing each other.

**`simple-english` has four install shapes, and all four satisfy the check.** The
`skills` CLI writes the skill body to `<scope>/.agents/skills/simple-english/`. Then
it makes a symlink or a copy at `<scope>/.claude/skills/simple-english/` for Claude
Code. The check block prints every hit, so **an existing install is never reported
missing and never needs migrating.** One update command covers all four:

| Shape | Where `SKILL.md` sits | Install with |
|-------|-----------------------|--------------|
| **Global, every agent** (what setup runs) | `~/.agents/skills/…`, symlinked to `~/.claude/skills/…` | `npx skills add AminBlg/SimpleEnglish --global --all` |
| **Global, Claude Code only** | `~/.claude/skills/…` (a copy) | `npx skills add AminBlg/SimpleEnglish --global --skill simple-english --agent claude-code --yes` |
| **Project, every agent** | `<repo>/.agents/skills/…`, symlinked to `<repo>/.claude/skills/…` | the global command without `--global` |
| **Manual fallback** (no `npx`, or the CLI has no network access) | wherever you copy it | `git clone https://github.com/AminBlg/SimpleEnglish`, then copy its `skills/simple-english` directory to `~/.claude/skills/simple-english` |

**The skill is not a plugin, so it is absent from `claude plugin list` and from
`installed_plugins.json`.** Do not run `claude plugin update` against it. The update
command is `npx skills update simple-english -g -y` (`-p` for a project install), and
it prints `All global skills are up to date` when nothing moved. Both global shapes
above ran unattended on 2026-08-03. A new skill directory needs a session restart
before the harness finds it, the same as a plugin.

**`resolving-merge-conflicts` has four install shapes, and all four satisfy the
check.** The skill body is identical in each, and the orchestrator invokes the skill
rather than a path. The check block prints every hit, so **an existing install is
never reported missing and never needs migrating.** The first two shapes need no
separate install at all, because the skill ships inside the `mattpocock-skills` repo:

| Shape | Where `SKILL.md` sits | Install with |
|-------|-----------------------|--------------|
| **Plugin cache** (what the plugin install writes) | `~/.claude/plugins/cache/<marketplace>/mattpocock-skills/<version>/skills/engineering/…` | `claude plugin install mattpocock-skills@claude-plugins-official` |
| **Marketplace clone** (the source the cache is built from) | `~/.claude/plugins/marketplaces/<marketplace>/skills/engineering/…` | `claude plugin marketplace add <owner>/skills` |
| **Standalone clone, global** | `~/.claude/skills/resolving-merge-conflicts/` | copy the skill directory there, as with a `prompt-improver` clone |
| **Standalone clone, project** | `<repo>/.claude/skills/resolving-merge-conflicts/` | the same copy, inside the repo |

On this machine on 2026-08-04 the first two shapes are both present and the check
block exits 0 on them. The two standalone shapes are absent, which is the expected
state where the plugin provides the skill — the check needs one hit, not four. The
update command is the plugin's (`claude plugin update mattpocock-skills@claude-plugins-official`),
so this dependency carries no update command of its own.

**`playwright-cli` is two requirements, and the check must carry the suffix.** Both
commands ran on this machine on 2026-08-03:

| Command | Observed |
|---------|----------|
| `command -v playwright-cli` (CLI present) | prints `/opt/homebrew/bin/playwright-cli`, exits 0 |
| `env PATH=/usr/bin:/bin sh -c 'command -v playwright-cli'` (CLI off the PATH) | prints nothing, exits 1 |
| `playwright-cli --version` | `0.1.17` |
| `command -v playwright` | prints `/Library/Frameworks/Python.framework/Versions/3.11/bin/playwright` |

The last line is why the binary loop probes `playwright-cli` and not `playwright`.
That path is the entry point of the Python Playwright framework, it reports
`Version 1.40.0`, and it is unrelated to `@playwright/cli`. On this machine, a loop
that probes `playwright` reports green even when the required CLI is absent.

The installed path is a symlink to
`../lib/node_modules/@playwright/cli/playwright-cli.js`. So the **provenance is the
npm global package**, and the update command is `npm update -g @playwright/cli`.
The skill body under `playwright-cli/` ships with this plugin. The binary does not.

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

## Python gate tools

One row per tool the Python column of [`quality-gates.md`](quality-gates.md) names.
These are conditional the same way as the rest of this file: a repo with no Python
needs none of them.

| Dep | Why | Check | Install |
|-----|-----|-------|---------|
| **ruff** | the layer 1 format and lint gates, plus the layer 2 complexity cap (`C901`) | `command -v ruff` | `uv tool install ruff` |
| **mypy** | the layer 1 types gate, with strict on | `command -v mypy` | `uv add --dev mypy` — it reads the project's own dependencies, so a project install beats a tool install |
| **pytest** | the layer 2 tests gate | `python3 -m pytest --version` | `uv add --dev pytest` |
| **coverage** | the layer 3 coverage gate. It runs the suite itself (`coverage run -m pytest`), so no pytest plugin is needed | `command -v coverage` | `uv add --dev coverage` |
| **import-linter** | the layer 3 import-boundaries gate. The binary is `lint-imports`, and the contracts live in `.importlinter` | `command -v lint-imports` | `uv add --dev import-linter` |
| **gitleaks** | the layer 3 secrets gate | `command -v gitleaks` | `brew install gitleaks` |
| **mutmut** | the layer 4 mutation-score gate | `command -v mutmut` | `uv add --dev mutmut` |
| **bandit** | the layer 4 SAST gate | `command -v bandit` | `uv tool install bandit` |
| **pip-audit** | the layer 4 dependency-CVE gate | `command -v pip-audit` | `uv tool install pip-audit` |

Read every install command in this table as **(verify)**. None of them ran on this
machine, because this repo has no gate config yet. Five of the nine install into the
project rather than onto the machine, so their check command needs the project
environment active.

## Go gate tools

One row per tool the Go column of [`quality-gates.md`](quality-gates.md) names. These are
conditional the same way as the rest of this file: a repo with no `go.mod` needs none of
them.

| Dep | Why | Check | Install |
|-----|-----|-------|---------|
| **go** (the toolchain) | the layer 1 strict-type-check gate (`go build`, `go vet`), the layer 2 unit-tests gate (`go test -race`) and the layer 3 coverage gate (`go test -cover`) | `command -v go` | `brew install go` — <https://go.dev/dl/> |
| **gofmt** | the layer 1 formatting gate | `command -v gofmt` | nothing of its own. It ships with **go**, so the **go** row installs it |
| **goimports** | the layer 1 formatting gate, for import order | `command -v goimports` | `go install golang.org/x/tools/cmd/goimports@latest` |
| **golangci-lint** | the layer 1 static-lint gate, and the binary that runs the four capped linters in this table | `command -v golangci-lint` | `brew install golangci-lint` — <https://golangci-lint.run> |
| **gocyclo** | the layer 2 cyclomatic-complexity cap. Config writes the number into the `gocyclo` setting of `.golangci.yml` | `golangci-lint linters` | nothing of its own. It ships inside **golangci-lint** |
| **gocognit** | the layer 2 cognitive-complexity cap. Config writes the number into the `gocognit` setting of `.golangci.yml` | `golangci-lint linters` | nothing of its own. It ships inside **golangci-lint** |
| **funlen** | the layer 2 function-length cap. Config writes the number into the `funlen` setting of `.golangci.yml` | `golangci-lint linters` | nothing of its own. It ships inside **golangci-lint** |
| **depguard** | the layer 3 import-boundaries gate, for an illegal import | `golangci-lint linters` | nothing of its own. It ships inside **golangci-lint** |
| **godog** | the layer 2 BDD-acceptance gate. It is the runner, and how a repo writes its features is that repo's choice | `command -v godog` | `go install github.com/cucumber/godog/cmd/godog@latest` |
| **go-arch-lint** | the layer 3 import-boundaries gate, for a cycle between packages | `command -v go-arch-lint` | `go install github.com/fe3dback/go-arch-lint@latest` |
| **go-mutesting** | the layer 4 mutation-score gate | `command -v go-mutesting` | `go install github.com/zimmski/go-mutesting/cmd/go-mutesting@latest` |
| **gosec** | the layer 4 SAST gate | `command -v gosec` | `brew install gosec` — <https://github.com/securego/gosec> |
| **semgrep** | the layer 4 SAST gate, beside `gosec` | `command -v semgrep` | `brew install semgrep` — <https://semgrep.dev> |
| **govulncheck** | the layer 4 dependency-CVE gate | `command -v govulncheck` | `go install golang.org/x/vuln/cmd/govulncheck@latest` |

**`gitleaks` answers the secrets Gate of this column too.** It reads a git history and not
a language. So its one row stays in the **Python gate tools** table, and this table does
not repeat it.

Read every install command in this table as **(verify)**. None of them ran on this
machine, because this repo carries no Go file. Five of the fourteen install nothing of
their own: `gofmt` ships with the Go toolchain, and `gocyclo`, `gocognit`, `funlen` and
`depguard` ship inside `golangci-lint`. So the check of those four reads the linter list
of that one binary.

## TypeScript gate tools

One row per tool the TypeScript column of [`quality-gates.md`](quality-gates.md) names.
These are conditional the same way as the rest of this file: a repo with no
`tsconfig.json` needs none of them.

| Dep | Why | Check | Install |
|-----|-----|-------|---------|
| **pnpm** | the documented package manager. The layer 4 dependency-CVE gate runs `pnpm audit`, and every project install in this table runs through it | `command -v pnpm` | `npm install -g pnpm` |
| **biome** | the layer 1 format gate, plus the lint rules it implements. It is the fast linter, so it answers layer 1 | `pnpm exec biome --version` | `pnpm add -D @biomejs/biome` — the package name carries the scope, the binary does not |
| **tsc** | the layer 1 strict type check, with strict on. The binary ships inside the `typescript` package | `pnpm exec tsc --version` | `pnpm add -D typescript` |
| **eslint** | the layer 1 lint rules `biome` does not have, plus the three layer 2 caps. `quality-gates.md` maps each cap to its rule | `pnpm exec eslint --version` | `pnpm add -D eslint` |
| **eslint-plugin-sonarjs** | the layer 2 cognitive-complexity cap. It supplies the `sonarjs/cognitive-complexity` rule, which `eslint` has no built-in for | `pnpm ls eslint-plugin-sonarjs` | `pnpm add -D eslint-plugin-sonarjs` |
| **vitest** | the layer 2 unit tests (`--related`) and the layer 3 coverage gate (`--coverage`) | `pnpm exec vitest --version` | `pnpm add -D vitest @vitest/coverage-v8` — coverage needs the provider package beside the runner |
| **@cucumber/cucumber** | the layer 2 BDD acceptance gate | `pnpm exec cucumber-js --version` | `pnpm add -D @cucumber/cucumber` |
| **dependency-cruiser** | the layer 3 import-boundaries gate. The binary is `depcruise`, and the contracts live in `.dependency-cruiser.js` | `pnpm exec depcruise --version` | `pnpm add -D dependency-cruiser` |
| **stryker** | the layer 4 mutation-score gate. The binary is `stryker`, and the package name is scoped | `pnpm exec stryker --version` | `pnpm add -D @stryker-mutator/core` |
| **semgrep** | the layer 4 SAST gate | `command -v semgrep` | `brew install semgrep` |
| **trivy** | the layer 4 dependency-CVE gate, beside `pnpm audit`. It reads the lockfile, so it catches a transitive dependency the audit command reports differently | `command -v trivy` | `brew install trivy` |

**`gitleaks` gets no second row.** The layer 3 secrets gate is the same tool in every
column, and the Python table already declares it. One tool, one row.

Read every install command in this table as **(verify)**. None of them ran on this
machine, because this repo carries no TypeScript file and no gate config. Eight of the
eleven install into the project rather than onto the machine, so their check command
needs the project dependencies installed first. When a run proves them, record the
target repo and the date here.

## Infra gate tools

One row per tool the Terraform column of
[`quality-gates-infra.md`](quality-gates-infra.md) names. These are conditional the same
way as the rest of this file: a repo that provisions nothing needs none of them. This
repo is that case, so every field of `gates.infra` stays blank here.

| Dep | Why | Check | Install |
|-----|-----|-------|---------|
| **tofu** | the layer 1 format and validate gates, and the layer 3 plan. The binary is the OpenTofu CLI, and a repo that runs `terraform` uses that binary for the same rows | `tofu version` | `brew install opentofu` |
| **tflint** | the layer 1 lint gate, and the version-pin check in the same layer | `command -v tflint` | `brew install tflint` |
| **trivy** | the layer 1 misconfiguration gate (`trivy config`), which reads the `.tf` files and not the plan | `command -v trivy` | `brew install trivy` |
| **conftest** | the layer 2 fixture gate (`conftest verify`) and the layer 3 **Halt condition** gate (`conftest test`). It runs the rules and the tests for those rules, so one tool covers both | `command -v conftest` | `brew install conftest` |
| **infracost** | the layer 3 cost-delta gate. It reads the plan JSON, so it needs no second plan run | `command -v infracost` | `brew install infracost` |

Read every install command in this table as **(verify)**. None of them ran on this
machine, because this repo carries no `.tf` file. All five install onto the machine
rather than into the project, so their check command needs no project environment.

Layer 3 also needs a credential, and it is the one requirement here that no install
command can give. `gates.infra.plan_role` names a read-only plan role, and a blank
`plan_role` means no plan gate. Then layers 1 and 2 still run
([`quality-gates-infra.md`](quality-gates-infra.md)).

## Vendor keys

A worker needs the API access its harness/model uses (Anthropic for opus-5/
sonnet-5, OpenAI for gpt-5.6). Adversarial review spans **both** vendors, so a
cross-vendor setup needs both credentials configured for the respective
harnesses. The orchestrator doesn't manage keys — it assumes the harness CLIs are
already authenticated (`claude` logged in, `codex` authed, etc.).
