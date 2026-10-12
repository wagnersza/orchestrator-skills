# Quality gates. Written from orchestrator-setup/templates/Makefile.template.
#
# One target per gate layer. Each target runs one layer of scripts/checks.sh, and CI
# runs that same script. So a step cannot be green here and red in CI for a reason that
# is not the code. To change a step, edit the script. This file names the layers and
# nothing else.
#
# Run the layers in this order: quick, then full. A later layer does not repeat an
# earlier one.
#
# The layers, their budgets and their thresholds live in
# orchestrator/references/quality-gates.md. Both targets here miss the budget of that
# file, because the suite builds a real git repository per fixture and takes about 35s.
#
# Neither target writes the gate record. The PostToolUse hook hooks/record.py reads the
# exit code of the gate command a worker ran. It appends the line, so the record reads
# `make quick` as the `gates:` block of config names it. Same reference file, gate record
# section.

.PHONY: quick full

# layers 1 and 2 — format, lint, types, tests, complexity. The v1 Python suite runs
# first, then the v2 TypeScript typecheck and tests, so v1 keeps working until the
# cutover.
quick: node_modules
	scripts/checks.sh quick
	npm run --silent typecheck
	npm test --silent

# The dev-only TypeScript tools. npm ci runs again only when the manifest or the lock
# file is newer than node_modules.
node_modules: package.json package-lock.json
	npm ci
	touch node_modules

# layer 3 — the suite, import boundaries, secrets.
full:
	scripts/checks.sh full

# There is no `deep` target. This repo runs the `lite` gate profile, so layer 4 is off.
# `gates.deep` in docs/agents/orchestrator.md is blank. A move to `strict` needs the
# layer 4 block of the template back here, and nothing else. The script keeps its `deep`
# case either way.
