# Skill routing

Every verb the orchestrator recognises, mapped to the **skill** that owns that job
and the **lane** the skill runs in.

Prompt *content* is not defined here. The wording of a worker-lane invocation
belongs to the **`prompt-improver` skill** (a dependency — see
[`requirements.md`](requirements.md)), per
[`../docs/adr/0006-delegate-prompting-to-prompt-improver.md`](../docs/adr/0006-delegate-prompting-to-prompt-improver.md).
This table only says which skill a verb resolves to, and where that skill runs.

The two lanes:

- **`inline`** — the orchestrator invokes the skill in this session, in the main
  checkout. Only skills whose output is issues, docs or conversation.
- **`worker`** — the orchestrator does not invoke the skill. The invocation goes
  into the spawn prompt, so the worker enters the skill inside its own worktree.

[`../docs/adr/0014-route-verbs-to-skills-in-two-lanes.md`](../docs/adr/0014-route-verbs-to-skills-in-two-lanes.md)
holds the lane split and its rationale. It also records why `/wayfinder` and
`/research` are `inline` although they write to the tracker and to the repo.

| Verb / aliases | Skill | Lane | Notes |
|----------------|-------|------|-------|
| `to-spec`, `spec`, `prd` | `/to-spec` | `inline` | Needs the conversation so far, plus the tracker config at `docs/agents/issue-tracker.md`. The skill publishes the spec and applies `ready-for-agent` itself — do not also write a label. |
| `to-tickets`, `tickets`, `split` | `/to-tickets` | `inline` | Needs the spec or the conversation, and the tracker config. It writes each ticket's `## Blocked by` edges, which is the shape the **Ready queue** reads. |
| `brainstorm`, `grill`, `let's plan`, `stress-test` | `/grill-with-docs` | `inline` | Needs the subject to attack. It runs `/grilling` over `/domain-modeling`, so it writes ADRs and glossary entries. Point it at this repo's layout — `orchestrator/CONTEXT.md` and `orchestrator/docs/adr/` — not at a repo-root `CONTEXT.md`. |
| `triage` | `/triage` | `inline` | Needs the work-item number, and the triage roles from `docs/agents/triage-labels.md`. Every comment the skill posts opens with the AI disclaimer the skill defines. |
| `plan a big chunk`, `map this out`, `wayfind` | `/wayfinder` | `inline` | Needs the destination, named in one sentence. It creates a map issue plus its decision tickets, and it holds the map across turns. `inline` although it writes to the tracker — see the ADR above. |
| `research`, `look into`, `find out how X works` | `/research` | `inline` | Needs the question, and where this repo keeps notes. The skill runs its own background agent and lands a Markdown file in the main checkout. `inline` although it writes to the repo — see the ADR above. |
| `domain model`, `glossary`, `ubiquitous language` | `/domain-modeling` | `inline` | Needs the term or the decision under change. This repo is single-context: `orchestrator/CONTEXT.md`, with ADRs under `orchestrator/docs/adr/` (`docs/agents/domain.md`). Reading the glossary for vocabulary is not this skill. Changing the model is. |
| `hand this off`, `handoff` | `/handoff` | `inline` | Needs what the next session will focus on. The skill writes to the temporary directory of the OS, not to the workspace, so nothing lands in a diff. |
| `architecture review`, `what's shallow`, `deepen this`, `layer 5` | `/improve-codebase-architecture` | `inline` | Needs the direction to look in: one module, one subsystem or one pain point. With no direction it reads the commit history for hot spots. Point it at this repo's layout, `orchestrator/CONTEXT.md` and `orchestrator/docs/adr/`, not at a repo-root `CONTEXT.md`. It is **Layer** 5 and it is advisory, so it stops nothing. When to run it, and what to do with each candidate it lists: [The layer 5 story gate](../SKILL.md#the-layer-5-story-gate). |
| `implement`, `develop`, `build`, `start work on`, `work on` | `/implement` | `worker` | Needs the work item, its acceptance criteria and the scope edges the rendered prompt already carries. Without slash commands: tell the worker to implement the item test-first, at agreed seams. It runs the type check and the full suite, reviews its own diff against the criteria, then commits. |
| `test-first`, `red-green`, `TDD` | `/tdd` | `worker` | Needs the seams to test, confirmed before the first test. Without slash commands: tell the worker to write the failing test first, at the named seam. Then it writes the smallest code that makes the test pass. It tests behaviour through public interfaces only. |
| `debug`, `diagnose`, `it's broken`, `it's slow` | `/diagnosing-bugs` | `worker` | Needs the symptom and the steps that reproduce it. Without slash commands: tell the worker to build a tight pass/fail signal for this bug, before it reads code. Then it bisects against that signal. It fixes the cause and not the symptom. |
| `review`, `review the diff`, `review since X` | `/code-review` | `worker` | Needs the fixed point to diff against (`main`, a SHA, a merge base) and the originating work item, because the skill reviews two axes. Without slash commands: tell the worker to review the diff twice. One pass against this repo's documented standards, one against the item's acceptance criteria. It reports the two axes separately. |
| `prototype`, `spike` | `/prototype` | `worker` | Needs the design question, and which branch answers it — logic or UI. Without slash commands: tell the worker to build throwaway code that answers one question. One command runs it. It has no persistence and no polish, and its name says it is a prototype. |

## The type label of an item names the same skills

A verb comes from a person who typed it. A queue tick has no verb. So the tick reads the
**type label** the work item already carries, and it resolves to the same skills.

| Type label on the work item | Skill | Lane |
|-----------------------------|-------|------|
| `bug` | `/diagnosing-bugs` | `worker` |
| every other type label, and no type label at all | `/implement` | `worker` |

- **This adds no label family.** `bug` is a label the tracker ships. A type label names the
  kind of work, and a maintainer already uses that family. It is a separate family from the
  **Work-state labels** in `docs/agents/issue-tracker.md`.
- **These two rows name no skill the verb table does not.** So both reads answer with the
  same skill, and a worker meets one contract whichever read started it.
- **`user-story` never reaches this read.** A story is not spawned for the work itself,
  and the queue tick descends to its children.
- **This is the one mapping.** A skill body that resolves a type label reads this section,
  and it writes no table of its own. The rendered worker prompt takes the answer as one
  of its inputs.

Notes:

- **Every lane is `inline` or `worker`.** No third value, and no blank. A verb whose
  lane is not decided gets no row.
- **This table adds no dependency.** Every skill above ships in
  `mattpocock-skills`, which [`requirements.md`](requirements.md) already declares
  **Always required**. A row that needs a new dependency row points at something
  uninstalled. Drop the row instead.
- **The table is hand-maintained.** A newly declared dependency becomes one row, in
  the same commit that declares it. Nothing here scans the installed plugin set.
- **The `inline` lane needs a session that can reach the skill.** Every skill above
  is a Claude plugin skill, and a session with no slash commands reaches none of
  them. There the orchestrator answers the verb freehand, and its report says the
  skill was unreachable.
- **Routing is independent of Role.** Verb → skill and work item →
  `(model, effort)` are two resolutions over the same work item, and neither
  constrains the other. The role table is in [`models.md`](models.md).
