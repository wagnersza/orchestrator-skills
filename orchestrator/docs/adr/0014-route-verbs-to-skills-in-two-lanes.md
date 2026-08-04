# A verb resolves to a skill, in one of two lanes

The orchestrator read the user's verb as plain English and improvised. The skills
that already hold those jobs — `/to-spec`, `/to-tickets`, `/grill-with-docs`,
`/implement` — sat installed and unused. So `/orchestrator to-spec` produced
something spec-shaped that was not a spec: no template, no `ready-for-agent` label,
no seam-confirmation step. A spawn prompt described the work in prose and never
named `/implement`. The worker then started cold on a brief, when a skill existed
that gives it the loop.

Both failures are silent. Nothing errors, and the output is plausible. The cost is a
quality lower than what the declared dependencies already provide.

A verb now resolves through one table:
[`orchestrator/references/skill-routing.md`](../../references/skill-routing.md).
Each row gives a verb and its aliases, the skill that owns the job, the **Lane**,
and what the skill needs handed to it. The vocabulary is the **Skill routing** and
**Lane** entries in [`orchestrator/CONTEXT.md`](../../CONTEXT.md).

## The lane split

Two lanes, and every row is one of them:

- **`inline`** — the orchestrator invokes the skill in this session, in the main
  checkout.
- **`worker`** — the orchestrator invokes nothing. The invocation goes into the
  spawn prompt, so a worker's first act inside its worktree is to enter the skill.

The split holds the skill's own law: **never do implementation work in the
orchestrator session.** The load-bearing claim is that this law is about writing
source, and not about writing at all. A skill whose output is issues, docs or
conversation therefore runs here and breaches nothing. A skill that touches source
belongs in a worktree, on a branch, behind a PR.

The two lanes also differ in what a wrong turn costs. An `inline` skill produces an
issue or a document, and a delete or an edit undoes a wrong one. A `worker` skill
produces a diff, and a wrong one costs a branch, a review round and a re-spawn. So
the lane a skill lands in follows the reversibility of its output.

## Why `/wayfinder` and `/research` are inline

These two are the boundary, and they are the rows a future reader will re-litigate.
Both write outside the conversation.

`/wayfinder` creates a map issue plus its decision tickets, and it holds the map
across many turns. So it writes to the tracker, repeatedly. That is the same surface
`/to-spec` and `/to-tickets` write to, at a larger volume. Volume is not the test.
The test is whether the output is source, and a decision ticket is not.

`/research` is the harder one, because it commits a Markdown file into the main
checkout. That is a write to the repo the orchestrator holds on the default branch.
It stays `inline` for two reasons. The file is **non-source**: it is a note, nothing
compiles, imports or tests it, and no behaviour depends on it. And the write is
**reversible** by the delete of one file, with no branch, no review round and no
migration.

So the boundary is not "the orchestrator never writes". It is: **the orchestrator
never writes source.** Two properties put a skill on the inline side of it, and both
are necessary. The output is non-source, and a delete or an edit undoes a wrong
output. A skill that writes a Python file, a config the runtime reads, or a skill
body other sessions load, fails the first property. It takes the worker lane
whatever its volume.

**The trigger to move this boundary is a new candidate that satisfies neither
property.** Then the boundary moves in this ADR and in one column of one table. It
does not move by an argument in a PR comment about one row.

## Considered Options

- **One table, two lanes, keyed on the nature of the output** (chosen) — the map is
  a property of the installed skill set, so every project with these dependencies
  wants the same rows. A new skill is one row. The lane column carries the reasoning
  at the point of use.
- **Run every skill inline** (rejected) — `/implement` and `/tdd` write source in
  the main checkout, on the default branch, with no worktree and no branch to review.
  That is the law this skill exists to hold.
- **Splice every skill into a worker, the planning ones included** (rejected) — a
  spec, a triage pass and a handoff each need the conversation that just happened. A
  worker starts with none of it. The orchestrator would rebuild the context it
  already holds, and pay a worktree and a spawn for a tracker comment.
- **No table: let the orchestrator pick a skill per turn** (rejected) — the state
  before this ADR, and the defect. A rule with no home rots, and this one had no home
  at all.
- **Per-project verb overrides in config** (rejected) — the map follows the
  installed skill set, not the project. An override set is a second source of truth
  for the same question. Revisit only when a real project needs a different map.
- **Derive the table by a scan of the installed plugin set** (rejected) — a scan
  finds the skills and cannot assign a lane, which is the whole judgment. It also
  routes a verb to a skill nobody chose.
- **A third lane for the ambiguous rows** (rejected) — a third value is where
  `/wayfinder` and `/research` go to avoid the decision. Two lanes force the
  decision, and this ADR is where it is recorded.

## This ADR restates no prompting rule

The wording of a spliced invocation, and of the prose around it, stays
`prompt-improver`'s (ADR 0006). This ADR says only *that* a skill is invoked and
*where*. The Notes column of the routing table names what a skill needs handed to
it, and what to say when the harness has no slash commands. Neither is a prompting
rule.

The delegate-do-not-vendor pattern holds. `prompt-improver` owns the prompt,
`simple-english` owns the prose, `ponytail` owns the volume, and the routed skills
own their own loops. This change vendors none of them. It records which one to reach
for.

## Consequences

- **The table is hand-maintained, and that is the design.** A newly declared
  dependency becomes one row in the same commit that declares it. Nothing scans the
  plugin set.
- **Every row must name a declared dependency.** Each skill in the table ships in
  `mattpocock-skills`, already **Always required** in
  [`orchestrator/references/requirements.md`](../../references/requirements.md). A
  row that needs a new dependency row points at something uninstalled — drop the row.
- **Routing is independent of Role.** Verb → skill and work item →
  `(model, effort)` are two resolutions over the same item. A light-role
  `/implement` and a heavy-role `/implement` differ only in the model, which is what
  ADR 0005 already decides.
- **This ADR declares the split and wires nothing.** The consuming rule in
  `orchestrator/SKILL.md` is separate work. Until it lands, the table changes no
  behaviour, and `/orchestrator` resolves a verb exactly as it does today.
