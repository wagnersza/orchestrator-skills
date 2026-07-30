# Tool / Harness / Model layering, abstracted by reference-per-variant

The orchestrator was hardwired to one workspace tool (Orca), one agent CLI (Claude), and one project. To make it tool-agnostic we split the worker into three orthogonal layers — **Tool** (workspace/session manager: orca, cmux, herdr), **Harness** (agent CLI: claude, codex, pi, copilot, cursor), and **Model** (frontier model + vendor) — and abstract each layer with one reference file per variant (`references/tools/<t>.md`, `references/harnesses/<h>.md`), the way mattpocock's `cloud-deploy` splits aws/gcp/azure. `SKILL.md` speaks in abstract steps and points at the reference for the concrete commands.

## Considered Options

- **Reference-file-per-variant** (chosen) — the skill body stays legible, each variant's real commands live in one place, adding a tool/harness is a new file with no body edit.
- **Command-table in config** — config declares CLI command strings per abstract operation. Rejected: verbose per-project config, flag knowledge duplicated across every project, unverified by the skill.

## Consequences

A worker is a `(Tool, Harness, Model)` triple. Yolo-mode and model-selection flags are properties of the Harness (see ADR-0003 for how they compose). A CLI change is a one-file edit that every project inherits.
