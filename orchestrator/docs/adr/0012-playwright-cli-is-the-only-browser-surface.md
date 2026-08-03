# playwright-cli is the only sanctioned browser surface for a worker

`playwright-cli` is the one browser-automation surface an orchestrator worker
drives. A browser MCP that a worker's session happens to expose is not a
sanctioned surface, whichever one it is.

Two surfaces were reachable, and only one is chosen. `playwright-cli` ships with
this plugin, `README.md` already names it as the UI-evidence tool, and it carries
ten reference files. Chrome DevTools MCP is registered as a **global** MCP server
in `~/.claude.json` on the maintainer's machine, so it loads in every session here.
That includes an unattended worker with the yolo flag. Nothing in the repo said
which surface to use, so the worker picked. The cheapest pick is whatever is
already in the tool list.

The decisive difference is the artifact. Every `playwright-cli` action emits the
equivalent Playwright TypeScript, which is the raw material for a durable test
(`../../../playwright-cli/references/test-generation.md`). An MCP call emits a
transcript entry that dies with the session. The `evidence` bar asks for proof that
a change works, and only one of the two survives the run.

The rule is about the **class**, not about `chrome-devtools`. This ADR names Chrome
DevTools MCP as the recognisable instance. A new ambient browser MCP that appears
tomorrow is out of bounds on the same terms, with no edit to the rule. **Tool
availability is not tool endorsement.** An unattended worker's tool list comes from
global config it did not choose, so anything this repo has not declared is not
sanctioned by default.

The DevTools MCP is not bad, it is undeclared. It stays usable for the
maintainer's interactive debugging and for other projects. The rule is scoped to
orchestrator workers on this repo's contract.

## Considered Options

- **Declare `playwright-cli`, put ambient browser MCPs out of bounds** (chosen) —
  the surface already ships with the plugin, and its output is code that can
  become a test.
- **Adopt Chrome DevTools MCP as the declared surface** (rejected) — a per-machine
  global registration with no home in this repo, and it produces no reusable
  artifact. A declaration also adds an MCP dependency for a job the plugin already
  carries.
- **Allow both and let the worker choose** (rejected) — the state this ADR
  replaces, and the defect: evidence differs run to run, and neither surface was
  verified.
- **Enforce with a permissions deny rule** in a `settings.json` (rejected) — a
  second enforcement mechanism that drifts from the documented one, and it breaks
  on an MCP rename. Considered and deliberately declined.
- **Unregister the global MCP** (rejected) — mutates user-global state outside the
  repo and breaks unrelated projects that legitimately use it.

## Enforcement is documentary

Three places carry the rule, and nowhere else does:

- `orchestrator/references/requirements.md` — which surface is declared, how to
  check it, how to install it.
- `orchestrator/CONTEXT.md` — the **Browser surface** entry: what the concept
  means.
- The worker prompt's scope edges — the one place a worker is sure to read.

This repo writes no permissions deny rule for `mcp__chrome-devtools__*` or for
anything else, and it leaves the machine's global MCP registration unchanged.

**The accepted risk:** a worker that ignores the scope edge is blocked by nothing.
The mitigation is proportion, not a mechanism. Evidence lands in a review note that
the maintainer reads, and a DevTools-derived screenshot is visibly not Playwright
output. The cost of the failure is one item with a screenshot for evidence instead
of code. Review catches it, and it breaks no build and loses no data.

## No Python seam changes

No file under `scripts/` changes, so the Python seam count is whatever it already
was. A dependency-checking script was considered and
rejected: the check commands belong in the catalog, where `/orchestrator-setup`
and the orchestrator's preflight already read them. A Python wrapper creates a
second place for a check command to live, which is the duplication this repo
repeatedly rejects. This change adds no installer under `scripts/` either. The
installation guide is a procedure a human can follow
(`../../../playwright-cli/references/installation.md`).

## Consequences

- **The dependency row now checks the binary.** It checked
  `ls playwright-cli/SKILL.md`, which tests that the plugin shipped its own file.
  That is always true, so the check tested nothing and moved a command-not-found
  into an unattended worker.
- **The CLI and the browser binaries are two requirements**, reported separately.
  A CLI update can want a newer browser build than the cache holds. One green check
  for both is how a machine reaches a passing preflight with a worker that cannot
  open a page.
- **The check must carry the suffix.** On the maintainer's machine, a bare
  `playwright` resolves to the Python Playwright framework, which is unrelated to
  `@playwright/cli`. So the old binary loop reported green even when the required
  CLI was absent.
- **The provenance is recorded** as the npm global package. That makes
  `npm update -g @playwright/cli` derivable from the catalog, rather than a guess
  at brew.
- **Two follow-ups cite this decision** instead of repeating it: the rule reaches
  the worker contract's scope edges, and `/orchestrator-setup` installs the CLI in
  its normal install loop.
