# Preflight skill reachability before routing

The preflight asked one question: is the plugin that ships the routed skill installed?
A plugin can be installed and the skill can still be unreachable. A skill whose
frontmatter holds `disable-model-invocation: true` is absent from the skill list of a
session. No model can enter it. Only a human who types the slash command can.

The defect is proved. Work item #90 spawned with `Run /implement.` on the first line of
its prompt. The plugin was installed, so the preflight passed. The transcript of that
worker holds 235 lines and one skill call, and that call is `simple-english`. The
`implement` skill in `mattpocock-skills` 1.2.3 holds the flag, so `Run /implement.` was
plain prose. The worker started cold and the run looked correct.

The problem is not one skill. On 2026-08-20, in `claude-plugins-official/mattpocock-skills`
1.2.3, 7 of the 13 routed skills hold the flag. One is a `worker` row and six are `inline`
rows. **That count is evidence for this decision, and it is not a table to maintain.** The
flag belongs to the upstream skill, and upstream moves it without telling this repo. So no
reference file here records which skills carry it.

## The decision

The preflight holds two checks, in one order, for every routed skill and in both lanes.

1. **Is the name of the skill in the skill list of this session?** That list is the live
   fact, because it is the set the model can act on. A session on this machine
   reads the same install a worker on this machine gets. So this session's own list
   answers for the worker it is about to spawn.
2. **Where that list is not visible, does the frontmatter of the skill's `SKILL.md` hold
   `disable-model-invocation: true`?** A hit is the failure. The command is in
   [`orchestrator/references/skill-routing.md`](../../references/skill-routing.md), with
   the rest of the preflight.

The failure response follows the **Lane**.

- **`worker`** — the draft prompt carries no slash command. It carries the row's
  *Without slash commands* prose, in the place the slash command holds on `claude`. The
  spawn continues.
- **`inline`** — the session claims nothing. It asks the maintainer to type the slash
  command, or it answers the verb freehand and reports the skill as unreachable.

The vocabulary is the **Skill reachability** entry in
[`orchestrator/CONTEXT.md`](../../CONTEXT.md).

## Considered Options

- **Two checks, the live skill list first and the frontmatter second** (chosen) — the
  list is what the model acts on. It also needs no command. The frontmatter answers where
  the list is not visible. Neither one names a skill, so neither one rots.
- **Send the prompt so that the CLI expands the slash command** (rejected) — the CLI
  expands a command at the start of a message only. The rest of the prompt then reads as
  arguments to that command. So the acceptance criteria, the checklist and the scope
  edges all arrive as one argument string, and the completion contract is lost. This
  option trades a cold start for a worker that runs the skill against the wrong input.
- **A hand-written list of blocked skill names** (rejected) — the flag is upstream's to
  set, and a plugin update moves it. A list of names then reports a stale answer with no
  error, which is the same silent failure this ADR closes.
- **A column in the routing table, or a per-skill flag on a row** (rejected) — the same
  rot. It also puts a property of the install into a table about the verb. The table is
  hand-maintained on purpose (ADR 0014), and this is the one fact a hand cannot keep
  current.
- **Abort the spawn, as a missing plugin does** (rejected) — the plugin is installed and
  the skill body is on disk. So the contract is reachable, and only the slash command is
  not. The prose fallback already exists for a harness that parses no slash command, so
  an abort throws away a path that works.
- **Read the frontmatter only, and skip the session list** (rejected) — the flag is a
  proxy for the outcome. A skill has several install shapes, so the file a grep finds is
  not always the file the session loaded. The list is the outcome itself.
- **Word the prompt harder** (rejected) — the state before this ADR. A literal slash
  command a model cannot invoke is text, and no wording repairs text.

## What this narrows

[ADR 0014](0014-route-verbs-to-skills-in-two-lanes.md) decided that a verb resolves to a
skill in one of two lanes. It also decided that a `worker` row splices a literal
invocation into the spawn prompt. Every part of that stands. This ADR narrows one claim
only: an installed plugin is not the same as a reachable skill. The lane split, the
hand-maintained table and the delegate-do-not-vendor posture are all unchanged.

## Consequences

- **Both prose fallbacks are one branch.** Two cases take the same *Without slash
  commands* prose, in the same place in the prompt. One is a harness that parses no slash
  command. The other is a skill the model cannot invoke. The failure they avoid is also the
  same: the prompt reads as literal text, the worker starts cold, and the run looks
  correct. So a `worker` row with no prose contract is not reachable on either branch.
- **The spawn report names the branch it took.** A prose fallback is then a fact the
  maintainer reads at spawn, rather than a cold start they find in a transcript later.
- **Enforcement is documentary.** No script reads a frontmatter flag, and no code gates a
  spawn. The rule reaches the flow through `orchestrator/SKILL.md`, and it reaches the
  worker through the prompt. That is the same posture as the **Browser surface** rule
  ([ADR 0012](0012-playwright-cli-is-the-only-browser-surface.md)).
- **Accepted risk: a grep can miss an install shape.** Where the skill list is not
  visible, the fallback searches the install shapes this repo knows. A shape it has not met
  reports no hit, which reads as reachable. The report says which half of the preflight
  answered, so a wrong answer is traceable to the half that gave it.
- **The `inline` lane loses no capability.** The session already answers a verb freehand
  where it cannot reach the skill, and it already reports that. This decision only adds the
  second reason it can happen.
