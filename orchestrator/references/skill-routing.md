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
| `implement`, `develop`, `build`, `start work on`, `work on` | `/implement` | `worker` | Needs the work item, its acceptance criteria and the scope edges the draft prompt already carries. Without slash commands: tell the worker to implement the item test-first, at agreed seams. It runs the type check and the full suite, reviews its own diff against the criteria, then commits. |
| `test-first`, `red-green`, `TDD` | `/tdd` | `worker` | Needs the seams to test, confirmed before the first test. Without slash commands: tell the worker to write the failing test first, at the named seam. Then it writes the smallest code that makes the test pass. It tests behaviour through public interfaces only. |
| `debug`, `diagnose`, `it's broken`, `it's slow` | `/diagnosing-bugs` | `worker` | Needs the symptom and the steps that reproduce it. Without slash commands: tell the worker to build a tight pass/fail signal for this bug, before it reads code. Then it bisects against that signal. It fixes the cause and not the symptom. |
| `review`, `review the diff`, `review since X` | `/code-review` | `worker` | Needs the fixed point to diff against (`main`, a SHA, a merge base) and the originating work item, because the skill reviews two axes. Without slash commands: tell the worker to review the diff twice. One pass against this repo's documented standards, one against the item's acceptance criteria. It reports the two axes separately. |
| `prototype`, `spike` | `/prototype` | `worker` | Needs the design question, and which branch answers it — logic or UI. Without slash commands: tell the worker to build throwaway code that answers one question. One command runs it. It has no persistence and no polish, and its name says it is a prototype. |

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
  skill was unreachable. **A session with slash commands can still fail to reach a
  row**, and that is the second case: the model cannot invoke the skill. Then the
  session claims nothing. It asks the maintainer to type the slash command, or it
  answers the verb freehand and reports the skill as unreachable, exactly as above. The
  check is [Preflight: can the model invoke this skill?](#preflight-can-the-model-invoke-this-skill).
- **Routing is independent of Role.** Verb → skill and work item →
  `(model, effort)` are two resolutions over the same work item, and neither
  constrains the other. The role table is in [`models.md`](models.md).

## Preflight: can the model invoke this skill?

**An installed plugin is not a reachable skill.** A skill whose frontmatter holds
`disable-model-invocation: true` is absent from the skill list of a session. No model
enters it, and only a human who types the slash command can. So a prompt that holds
`Run /implement.` is plain prose, and the worker starts cold while the run looks correct.

So the preflight holds **two** checks. Ask them in this order, for every row above and in
both lanes:

1. **Is the plugin installed?** Every row ships in `mattpocock-skills`, so this is the
   `mattpocock-skills` line of the plugin check block in
   [`requirements.md`](requirements.md).
2. **Can the model invoke the skill?** This is the check below.

Check 2 has two halves, in this order. The first half answers on its own where it can, and
the second half is the fallback:

1. **Is the name of the skill in the skill list of this session?** Read the list this
   session already holds. That list is the live fact, because it is the set a model can act
   on. Ask it about the bare name, with no leading slash. A session on this machine reads
   the same install a worker on this machine gets. So this session's list answers for the
   worker it is about to spawn.
2. **Where that list is not visible, does the frontmatter carry the flag?** One command,
   over the install shapes [`requirements.md`](requirements.md) declares. A hit is the
   failure:

   ```bash
   S=<the skill name from the table above, with no leading slash>
   find ~/.claude/plugins/cache ~/.claude/plugins/marketplaces ~/.claude/skills .claude/skills \
        -path "*/$S/SKILL.md" -exec grep -l 'disable-model-invocation: *true' {} + 2>/dev/null \
     | grep -q . && echo "$S: the model cannot invoke it" || echo "$S: the model can invoke it"
   ```

**The check names no skill, and this file lists none.** The flag belongs to the upstream
skill, and a plugin update moves it. A hand-written list of blocked names then reports a
stale answer with no error. So the table above gains no column and no per-skill flag.

**A failure is not an abort.** The plugin is installed and the skill body is on disk, so
the contract is reachable and only the slash command is not. The two lanes answer
differently:

- **`worker`** — the draft prompt carries no slash command. It carries this row's *Without
  slash commands* prose, in the place the slash command holds on `claude`. The spawn
  continues, and the report names the branch. The rule sits beside the harness rule it
  matches, in [`../SKILL.md`](../SKILL.md#the-prompt-checklist--completion-contract).
- **`inline`** — the session claims nothing. The `inline` note above holds both ways a
  session fails to reach a row.

Rationale, the rejected alternatives and the accepted risk:
[`../docs/adr/0030-preflight-skill-reachability-before-routing.md`](../docs/adr/0030-preflight-skill-reachability-before-routing.md).
The vocabulary is the **Skill reachability** entry in [`../CONTEXT.md`](../CONTEXT.md).
