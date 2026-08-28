#!/bin/sh
# Quality gates for this repo. Written from
# orchestrator-setup/templates/checks.sh.template.
#
# One argument, one gate layer:
#   quick   layers 1 and 2 — format, lint, types, tests, complexity
#   full    layer 3 — the suite, import boundaries, secrets
#   deep    layer 4 — mutation score, SAST, dependency CVEs   (off, see below)
#
# The Makefile calls this script, and CI calls it too. Both get the same steps in the
# same order. Run the layers in this order: quick, then full. A later layer does not
# repeat an earlier one.
#
# A step that exits non-zero stops the script, and no step warns. The layers, the tools
# and the thresholds live in orchestrator/references/quality-gates.md.
#
# Each threshold lives in the tool config that reads it, so this script holds no number.
# MUTATION_MIN below is the one exception, because the mutation runner reads no
# threshold from a config file.
#
# Each tool reads its own paths and excludes from pyproject.toml. Narrow them there, not
# here. Layer 3 reads its contracts from .importlinter and its secret rules from
# .gitleaks.toml.
#
# This script writes no gate record. It runs the gate command and it exits. The
# PostToolUse hook hooks/record.py then reads that exit code and appends the line. So a
# green line proves that a command exited zero, rather than that a model said so. The
# format and its one home are the gate record section of
# orchestrator/references/quality-gates.md.
#
# This repo runs the `lite` profile, so layer 4 is off. The Makefile has no `deep`
# target, and `gates.deep` in docs/agents/orchestrator.md is blank. So nothing reaches
# the `deep` case that follows. That case stays here, so a move to `strict` needs the
# Makefile block back and nothing else.

set -eu

# The name of a tool. A machine without it is a stop, never a skipped step.
need() {
	command -v "$1" >/dev/null 2>&1 && return 0
	echo "missing tool: $1" >&2
	echo "install it from the Python gate tools table of the orchestrator requirements" >&2
	exit 1
}

# A step name, then the command. The name reaches the log before the command runs.
step() {
	name=$1
	shift
	printf '\n==> %s\n' "$name"
	need "$1"
	"$@"
}

quick() {
	step 'format · layer 1' ruff format --check .
	step 'lint · layer 1' ruff check .
	# --strict on the command line, so the gate holds where pyproject.toml sets
	# nothing. The per-module section there relaxes the annotation checks alone.
	step 'types · layer 1' mypy --strict .
	# The template names one test directory, and this repo has two: the seams under
	# scripts/ and the hook plane under hooks/. The template keeps its one directory,
	# because a target repo holds no hook of this plugin's own. Same reference file,
	# and orchestrator/references/hooks.md holds the plane.
	step 'tests · layer 2' python3 -m pytest scripts/ hooks/ -q
	# C901 is the complexity rule, and it reads max-complexity from pyproject.toml.
	# --select on the command line, so the cap holds whatever the repo's own rule set
	# selects.
	step 'complexity · layer 2' ruff check --select C901 .
}

full() {
	# The template runs the suite here under the coverage tool. This repo drops that
	# wrapper and keeps the run. Both seams are CLI processes, and the suite drives them
	# through `subprocess`. So in-process line coverage reads 0% while every test passes.
	# A number that measures nothing is not a threshold. So `gates.thresholds.coverage`
	# stays blank, and `pyproject.toml` carries no `fail_under`.
	step 'tests · layer 3' python3 -m pytest scripts/ hooks/ -q
	# The contracts live in .importlinter.
	step 'import boundaries · layer 3' lint-imports
	# The rules live in .gitleaks.toml, and the scan reads the whole history.
	step 'secrets · layer 3' gitleaks detect --no-banner --redact
}

MUTATION_MIN=70 # percent of mutants the suite kills — gates.thresholds.mutation

# Where the mutation runner writes its counts. The path is the runner's own, and the
# `export-cicd-stats` command that writes it needs version 3 of the runner.
MUTATION_STATS=mutants/mutmut-cicd-stats.json

# The mutation runner reads no threshold from a config file, so the score check lives
# here. It fails closed: counts it cannot read are a stop, never a pass.
mutation_score() {
	mutmut export-cicd-stats
	python3 - "$MUTATION_STATS" "$MUTATION_MIN" <<-'PY'
		import json
		import sys

		path, minimum = sys.argv[1], int(sys.argv[2])
		with open(path, encoding="utf-8") as stats_file:
		    stats = json.load(stats_file)
		killed, total = stats["killed"], stats["total"]
		score = 100 * killed / total if total else 0
		print(f"mutation score: {score:.0f}% ({killed} of {total}, minimum {minimum}%)")
		sys.exit(0 if total and score >= minimum else 1)
	PY
}

deep() {
	printf '\n==> mutation score · layer 4\n'
	need mutmut
	# A surviving mutant is not the stop, and the score against MUTATION_MIN is. So the
	# run itself is tolerated. Last run's counts go first, or a crashed run reads as a
	# pass.
	rm -f "$MUTATION_STATS"
	mutmut run || true
	mutation_score
	step 'SAST · layer 4' bandit --quiet --recursive --severity-level high .
	step 'dependency CVEs · layer 4' pip-audit
}

case ${1:-} in
quick | full | deep)
	"$1"
	;;
*)
	echo "usage: $0 quick|full|deep" >&2
	exit 2
	;;
esac
