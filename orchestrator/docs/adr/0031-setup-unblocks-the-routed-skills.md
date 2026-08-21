# Setup unblocks the routed skills

A routed skill whose frontmatter holds `disable-model-invocation: true` is absent from the
skill list of a session. No model enters it, and only a human who types the slash command
can. So a worker prompt that holds `Run /implement.` is plain prose. The worker starts cold
and the run looks correct.

The defect is proved. Work item #90 spawned with `Run /implement.` on the first line of its
prompt. The plugin was installed, so the spawn check passed. The transcript of that worker
holds 235 lines and one skill call, and that call is `simple-english`.

On 2026-08-20, in `claude-plugins-official/mattpocock-skills` 1.2.3, 7 of the 13 routed
skills held the flag. That count is evidence for this decision. It is not a table to
maintain.

The cause is one line in a file this repo already writes to. `orchestrator-setup` runs
`claude plugin update` on every invocation. So it touches the installed skill bodies at the
one moment the flag can move.

## The decision

`orchestrator-setup` strips `disable-model-invocation: true` from the frontmatter of every
skill the routing table names. It runs the strip in step 0b, immediately after the update in
step 0a, on **every** invocation and in both modes.

Three limits hold it in place.

1. **The names come from the `Skill` column of a row in
   [`orchestrator/references/skill-routing.md`](../../references/skill-routing.md).** No
   list of names lives in the setup skill, so nothing goes stale when a row moves. A skill
   that file names in its prose alone keeps its flag, and `orchestrator-setup` itself is
   one of those.
2. **A skill outside that table is not touched.** The flag is a real choice upstream makes
   for a skill only a human triggers. This repo reverses it where it owns a route, and
   nowhere else.
3. **The strip removes the flag and writes nothing else.** A skill with the flag and no
   `description` stays out of reach. Setup names that skill and adds no description,
   because an invented one routes the model wrong.

The strip runs after every update because the update restores the flag. It is a repeated
repair, and not a migration.

## What this reverses

The number 0030 held the previous answer: a two-half preflight before every route, plus a
prose fallback per lane where the model could not invoke the skill. That ADR and every
change it made are reverted, and the number stays unused.

The preflight detected the failure and repaired nothing, so the fallback became the steady
state. A worker on prose instead of `/implement` loses the skill's test-first contract and
its own review pass. This ADR removes the cause instead, so the spawn keeps sending the
literal slash command.

Two things the reverted ADR added are gone, and both were only for this failure:

- The second half of the spawn check in step 2 of
  [`orchestrator/SKILL.md`](../../SKILL.md). A missing plugin still aborts a spawn, which
  is the check ADR 0014 already asked for.
- The **Skill reachability** entry in [`orchestrator/CONTEXT.md`](../../CONTEXT.md).

**The *Without slash commands* column stays.** It is older than the reverted ADR and it
serves a different reader: a harness that parses no slash command. That contract is
unchanged.

[ADR 0014](0014-route-verbs-to-skills-in-two-lanes.md) is back to whole. A verb resolves to
a skill in one of two lanes, and a `worker` row splices a literal invocation into the spawn
prompt.

## Considered Options

- **Strip the flag in setup, after the update, from the routed rows only** (chosen) —
  setup is already the one step that runs on every version move, and it already edits the
  machine. The repair lands where the damage lands, and it needs no new seam.
- **Detect the flag before each route and fall back to prose** (rejected, and reverted) —
  the state this ADR replaces. It repairs nothing, it costs a check on every route, and it
  trades the skill's contract for prose that only approximates it.
- **Both: strip in setup, and keep the preflight as a backstop** (rejected) — the check
  then fires on a condition setup has already removed, so it earns its cost on the rare
  machine alone. The two also disagree in one direction that misleads: the preflight reads
  a file on disk, and the session reads the skill list it loaded before the strip ran.
- **Ask the maintainer to type the slash command** (rejected) — this repo exists to spawn
  unattended workers. A human in the loop per item defeats the purpose, and a worker
  session has no human to ask.
- **Fork the upstream skills and pin them** (rejected) —
  [ADR 0028](0028-drop-the-fork-and-pin-dial.md) dropped that dial. A fork carries every
  upstream change by hand, and this problem is one line.
- **Strip the flag from every skill on the machine** (rejected) — the flag is upstream's
  choice, and a strip outside a routed row changes behaviour this repo does not own.
- **Send the prompt so the CLI expands the slash command** (rejected) — the CLI expands a
  command at the start of a message only. The rest of the prompt then reads as arguments to
  that command, so the acceptance criteria, the checklist and the scope edges arrive as one
  argument string. The completion contract is lost.
- **A hook that patches the flag on every session start** (rejected) — a hook edits the
  machine with no report and no version context. Setup already reports what it changed, and
  the maintainer already runs setup after a version moves.

## Consequences

- **A strip needs a session restart.** The edited body loads on the next start. So the
  session that ran the strip still cannot route that skill, and the report says which one.
- **The guard is setup, and setup alone.** Nothing checks the flag at spawn any more. So a
  machine that took a plugin update and no setup run sends a dead slash command, and the
  worker starts cold while the run looks correct. That is the accepted risk of this
  decision, and step 6 of the setup skill states the rule that closes it: re-running setup
  is how you update.
- **The repair is documentary, the same as the rest.** No hook and no script gates a spawn.
  The command sits in the setup skill body, and setup runs it. That is the posture of the
  **Browser surface** rule as well
  ([ADR 0012](0012-playwright-cli-is-the-only-browser-surface.md)).
- **Accepted risk: the loop can miss an install shape.** It searches the shapes
  [`orchestrator/references/requirements.md`](../../references/requirements.md) declares. An
  unknown shape keeps its flag, and the setup report does not name it, because the loop
  never found the file.
- **Accepted risk: the grep for names is a text match.** It reads the `Skill` column of a
  table row. A row written in another shape yields no name, so that skill is not unblocked.
