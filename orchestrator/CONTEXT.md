# Orchestrator

The orchestrator skill coordinates worker sessions that implement work items. This context defines the vocabulary the skill uses to stay independent of any one workspace tool, agent CLI, or model vendor.

## Language

**Tool**:
The workspace/session manager that cuts a worktree, opens a terminal, and sends keystrokes to it. One of: orca, cmux, herdr.
_Avoid_: workspace manager, session manager, backend.

**Harness**:
The agent CLI run inside a worker terminal (claude, codex, pi, copilot, cursor). Owns the yolo-mode flag and the model-selection flag.
_Avoid_: agent, runner, CLI (when the layer is meant).

**Model**:
The frontier model a harness runs (e.g. opus-5, sonnet-5, gpt-5.6). Has a **Vendor** and an **Effort**. Never hardcoded — resolved per **Role**.
_Avoid_: LLM.

**Effort**:
The dial for how much a model **thinks** — `low | medium | high | xhigh | max`, defaulting to `high` on both frontier models. Trades capability against tokens and latency. It does *not* shorten the visible response (prompt for length separately). Each harness expresses it differently and some clamp the top of the ladder; `references/harnesses/<h>.md` holds the map, `references/models.md` the ladder.
_Avoid_: reasoning effort, thinking budget, temperature.

**Role**:
The class of job a work item represents, which selects its `(Model, Effort)` pair from config's `models:` block. Three: **heavy** (multi-file feature, refactor, migration, open decisions — strongest model, `xhigh`), **light** (single-file scoped edit with fully enumerated criteria — cheaper model, `medium`), **review** (the adversarial reviewer — different vendor, `high`). Default heavy; downgrade to light only on clear signals. A fix round after review steps up a rung.
_Avoid_: tier, profile, model class.

**Vendor**:
The provider of a model — anthropic or openai. Adversarial review crosses vendors.
_Avoid_: provider, brand.

**Worker**:
One implementation session = a `(Tool, Harness, Model)` triple running against one work item in its own worktree/terminal.
_Avoid_: agent, session (when the worker is meant).

**Orchestrator**:
This session. Coordinates workers; never does implementation work itself.

**Yolo mode**:
The harness's unattended flag (analog of claude's `--dangerously-skip-permissions`) that lets a worker run with no human to approve tool prompts. Required, not optional, for every worker.
_Avoid_: unattended mode, skip-permissions.

**Adversarial review**:
An optional review of a worker's output by a second worker running a **different-vendor** model (e.g. implement with opus-5, review with gpt-5.6). Config names the review model + effort explicitly (`models.review`) and the orchestrator asserts its vendor differs from the impl model's. The review worker runs on the impl branch (own worktree) and reads the diff/MR against the acceptance criteria. Its prompt asks for **coverage, not filtering** — a "only high-severity" bar makes every current model silently drop real bugs.

**Review round**:
One cycle of adversarial review: the review worker posts a verdict (approve / request-changes + findings). On **request-changes**, the orchestrator re-prompts the **original impl worker** with the findings to fix, then re-reviews. Bounded at **3 rounds**. After approve — or after the 3rd round regardless — the orchestrator gathers evidence and moves the item to **human review**. The human reviews after the fixes; merge stays a human step.

**Prompting guide**:
The per-model reference the orchestrator follows when composing a spawn prompt. Two guides, vendored into `references/prompting/`: opus-5 and sonnet-5. Each model maps to one guide. GPT-5.6 has two tiers — **sol** (follows the opus-5 guide) and **terra** (follows the sonnet-5 guide). Read alongside `references/prompting/_composing.md`, the model-independent rules for every worker prompt.

**Composing rules**:
The model-independent half of prompt composition, in `references/prompting/_composing.md`: whole spec in the first turn, center + edges, named artifacts, positive examples over prohibitions, scope stated per item, and the stale scaffolding to delete (verification steps, forced status cadence, thinking-off rules). A worker prompt is an agentic-pipeline prompt — tight and finishable — so open-ended senior-partner framing does not apply, but everything above does.

**Tracker**:
Where work items live (GitHub / GitLab / local markdown). The orchestrator does not own a tracker abstraction — it reuses the mattpocock engineering skills' config, written to `docs/agents/issue-tracker.md` by `/setup-matt-pocock-skills`.
_Avoid_: issue tracker, board (when the layer is meant).

**Work item**:
One tracked unit of work (a ticket / issue) a worker implements. Carries `## Blocked by` and `## Parent` edges per the `to-tickets` template.
_Avoid_: ticket, issue, task (pick one — prefer work item).

**Ready queue**:
The set of work items a worker can start now — labelled `ready-for-agent` with every `## Blocked by` edge closed. The orchestrator resolves this over whatever tracker `docs/agents/issue-tracker.md` names.

**Config**:
The per-project orchestrator settings — tool, harness, model, adversarial-review policy, and tracker-setup pointer. Lives at `docs/agents/orchestrator.md` in the target repo (same pattern as `/setup-matt-pocock-skills`): human-editable markdown, seeded from a template in the skill folder, with a one-line summary block in `CLAUDE.md`. Per-project because different projects use different setups.

**Setup phase**:
The one-time interview that writes the Config — the user describes environment, tool, harness/CLI, models, adversarial-review policy, and the project recipes (setup command, run-for-evidence recipe + port scheme, optional DB gate, evidence expectations). Same posture as `/setup-matt-pocock-skills`: explore, present findings, confirm, write. Also ensures the tracker config exists (calls `/setup-matt-pocock-skills` if `docs/agents/issue-tracker.md` is missing).

**Work-state labels**:
The tracker labels that gate the queue and mark progress (`ready-for-agent`, `in-progress`, review, done). Owned by `docs/agents/issue-tracker.md` (`/setup-matt-pocock-skills`), not the orchestrator config — single source of truth. During an adversarial-review loop the item stays `in-progress` (a worker still owns it); it flips to the review label only when the loop concludes.

**Project recipe**:
Per-project commands the completion contract needs but that aren't tool/harness/model: setup command, run-for-evidence recipe + port scheme, optional DB gate, evidence expectations. Stored in Config so the skill body stays abstract ("boot per the run recipe", "if a DB gate is configured, satisfy it").

**Checklist**:
A persistent, file-based task list that survives context loss and works across every harness (unlike claude-only `TodoWrite`). Both the orchestrator and each worker keep one, so neither forgets a step (the documented "stalls before opening the MR" failure mode). Written as markdown checkboxes (`- [ ]` / `- [x]`) to `.orchestrator/checklist-<item>.md` at the worktree root (gitignored, torn down with the worktree). The worker ticks each step as it completes; the orchestrator reads the file to see exact progress and detect a stall (unchecked items + idle terminal → re-prompt with the remaining steps).
