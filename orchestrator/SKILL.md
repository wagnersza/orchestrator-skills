---
name: orchestrator
description: Orchestrate agent worker sessions across any workspace tool (orca/cmux/herdr), harness (claude/codex/pi/copilot/cursor), and frontier model. Pick the next ready work item, spawn a worker in its own worktree on the right model and effort for the job, prompt/monitor it via a file-based checklist, run optional cross-vendor adversarial review, and close finished work. Trigger on "what next", "what should I run/work on", "what's ready", "work on #N / implement #N / implement X", "spawn a worker", "start a session for X", "prompt worker Y", "what are the workers doing", "review #N adversarially", "close task #N / it's done / wrap up X", "list workers", "orchestrate".
---

# Orchestrator

This session is the **orchestrator**. It coordinates **worker** sessions. A
worker is a `(Tool, Harness, Model)` triple running against one work item in its
own worktree/terminal. Never do implementation work here — spawn a worker and
prompt it. One bounded exception: step 1 of a [close](#close-a-task) resolves
conflicts in the item's own worktree, on the maintainer's explicit instruction
([`docs/adr/0016-the-orchestrator-merges-when-asked.md`](docs/adr/0016-the-orchestrator-merges-when-asked.md)).

The vocabulary (Tool, Harness, Model, Effort, Role, Vendor, Worker, Yolo mode,
Adversarial review, Ready queue, Checklist, Project recipe) is defined in
[`CONTEXT.md`](CONTEXT.md).

```
one work item  ->  one worktree (branch + checkout + terminal)  ->  one worker (tool, harness, model)
```

## Config first — always

Every flow below reads the per-project config at `docs/agents/orchestrator.md`
in the target repo. **Before anything else, load it.** If it's missing, run
`/orchestrator-setup` (don't guess a tool/harness/model). From the config you get:

- **tool** → the concrete commands in [`references/tools/<tool>.md`](references/tools/_operations.md) (operation contract).
- **harness + yolo** → the launch command from [`references/harnesses/<harness>.md`](references/harnesses/claude.md) (composes the yolo flag, the `--model` value, and the effort flag).
- **models** → one `(model, effort)` pair per **role** (`heavy` / `light` / `review`). Never a hardcoded model — pick the right one for the job, see [Right model for the job](#right-model-for-the-job).
- **review** → whether to spawn a cross-vendor reviewer (model+effort from `models.review`; vendor asserted different — see [`references/models.md`](references/models.md)).
- **repo** → the main checkout; all tracker/git-state ops run there, on the default branch.
- **project recipe** → `setup_cmd`, `run_recipe` + `ports`, `db_gate`, `evidence` — the project-specific parts of the completion contract.

Work-state labels and the tracker CLI come from `docs/agents/issue-tracker.md`
(written by `/setup-matt-pocock-skills`), **not** the orchestrator config. If that
file is missing, run `/setup-matt-pocock-skills` first. That file also owns the
**project board** coordinates — see [Board status](#board-status).

**Preflight the config's dependencies.** Before the first spawn of a session,
confirm the tool binary, the harness binary (and the review harness if
`review.enabled`), and the tracker CLI are present — `command -v <bin>` — plus the
**`prompt-improver` skill**, which every spawn and review prompt goes through —
`claude plugin list | grep -o 'prompt-improver@[a-z-]*'`, falling back to
`ls ~/.claude/skills/prompt-improver/SKILL.md`. Any of its three install shapes
(plugin, `@skills-dir` clone, project-level clone) **satisfies the check** — the
skill body is the same and you invoke the skill, not a path.

Check the **`simple-english` skill** in the same pass, because every worker routes
its **Prose deliverable** text through it. Run the `simple-english` line of the
check block in [`references/requirements.md`](references/requirements.md) — the
four-path `ls` that prints every hit. Don't write a check of your own. Any of its
four install shapes (global or project, `.agents/` or `.claude/`) **satisfies the
check**, for the same reason `prompt-improver` gets three: you invoke the skill,
not a path. The skill is not a plugin, so `claude plugin list` never shows it.

Check the **`resolving-merge-conflicts` skill** in the same pass too, because step 1
of every [close](#close-a-task) invokes it. Run the `resolving-merge-conflicts` line
of that same check block — the four-path `ls`. Any of its four install shapes
**satisfies the check**, for the same reason the other two get theirs: the plugin
cache, the marketplace clone, or a standalone clone global or project. The skill ships
inside `mattpocock-skills`, so there is nothing separate to install. **Never begin a
close against a missing skill.** Stop and point the user at `/orchestrator-setup`, the
same as any other missing dependency.

**Check the Browser surface only when the recipe asks for browser evidence.** The
gate is the project recipe: a non-blank `run_recipe`, or an `evidence` bar that asks
for UI proof. Where the gate holds, check `playwright-cli` and the browser binaries
it drives. Those are two rows in
[`references/requirements.md`](references/requirements.md), because a machine can
have the CLI and no browsers. Run the check commands those rows give you.
**Preflight does not demand the browser CLI from a repo with a blank `run_recipe`
and no UI proof in its `evidence` bar.** There it does not check the surface at all.
This repo is that case: its `run_recipe` is blank, and its `evidence` bar asks for a
test run and resolved cross-references. So a documentation item here is never
blocked on a browser install. Requirements in this catalog are conditional on config
already, and this gate follows that rule. The concept is the **Browser surface**
entry in [`CONTEXT.md`](CONTEXT.md). The decision is
[`docs/adr/0012-playwright-cli-is-the-only-browser-surface.md`](docs/adr/0012-playwright-cli-is-the-only-browser-surface.md).

If any of them is missing, stop and point the user at `/orchestrator-setup` (it
installs deps). The full catalog is
[`references/requirements.md`](references/requirements.md). Don't try to spawn
against a missing binary. Don't compose a prompt without `prompt-improver`. And
never tell a worker to invoke a skill that is not installed.

**A failed browser-surface check reports a next step, not a missing binary.** Point
the user at
[`../playwright-cli/references/installation.md`](../playwright-cli/references/installation.md)
as well as `/orchestrator-setup`. That file holds the steps, the check that a browser
opens, and the failure modes. One of those modes is invisible to a bare `command -v`:
the CLI check is green and a browser session still cannot start. Never restate one of
its commands here or in a report. A copied command drifts from the maintained one.

Throughout, address a worker by its **slug** (the work-item's ticket prefix, e.g.
`#38 B5 · Contacts` → `b5-contacts`).

## Resolve the verb before you act

The user's phrase usually carries a **verb**, and an installed skill owns that job.
Before you act on a verb, read
[`references/skill-routing.md`](references/skill-routing.md) and resolve the verb to
its **Skill** and its **Lane**. Read that file at the moment you need it, never from
memory. Never copy a row into this body. One file holds the rows, so a new dependency
is one new row. The vocabulary is the **Skill routing** and **Lane** entries in
[`CONTEXT.md`](CONTEXT.md). Rationale:
[`docs/adr/0014-route-verbs-to-skills-in-two-lanes.md`](docs/adr/0014-route-verbs-to-skills-in-two-lanes.md).

**Lane `inline` — invoke the skill here.** Invoke it in this session, against the
main checkout (config's `repo`), on the default branch. No worktree, no branch, no
spawn. Hand it what the row's Notes column says it needs. Then name the skill you
routed to in the report ([Reporting to the user](#reporting-to-the-user)). An
`inline` skill writes issues, docs or conversation, and never source, so "never do
implementation work here" holds. A verb that writes source is a `worker` row, and
that law is what puts it there.

**Lane `worker` — hand the skill to the worker.** Invoke nothing here. The
invocation goes into the spawn prompt, so the worker's first act inside its own
worktree is to enter the skill. [Spawn a worker](#spawn-a-worker-implement-x)
preflights the skill and splices it. This section only resolves which skill it is. A
worked trace of both lanes, end to end, is
[`references/examples/routed-run.md`](references/examples/routed-run.md).

**A queue question is not a verb.** A bare `/orchestrator`, and *what next* / *what
should I run* / *what's ready*, resolve to no skill and route nowhere. Answer them
with ["What next?"](#what-next--pick-the-next-work), unchanged.

**An unmapped verb costs one line, then proceeds.** A verb that matches no row is
not a near miss to act on. Ask once, in one line: name the closest row and the verb
it holds, and ask whether to route there. `Nothing routes "<the user's phrase>".
Closest row is <verb> → <skill>. Route there?` Then wait for the answer. On yes, take
that lane. On no, answer the verb freehand, the way this session does today. Then say
in the report that no skill was routed to. A decline of the whole question reads as a
no. This closes two failures: a fuzzy match into a skill nobody chose, and a silent
freehand answer to a verb that wanted one.

## Board status

Where the tracker config has a **`## Project board`** section, every work item is
also a card with a `Status` field. **Labels are the source of truth; `Status` is
derived from them** — never a second state machine you advance separately. The
derivation table, the board coordinates (project number, `Status` field id, option
ids), and the two `gh` calls all live in that section of
`docs/agents/issue-tracker.md`; read them from there, never from memory. Rationale:
[`docs/adr/0009-labels-drive-board-status.md`](docs/adr/0009-labels-drive-board-status.md).

Two rules:

- **Write the card wherever you write a label** — and nowhere else. Three places in
  this skill: the claim at spawn (step 5), the worker's own flip to the review state
  (its final checklist box), and close (step 2). Plus the reconcile below.
- **A missing `## Project board` section means every board write is a no-op.** A
  repo with no board is a supported configuration — skip the write silently and
  carry on with labels. Never fail a spawn or a close over the board.

The write is idempotent, so re-writing a value a card already holds is free. An
issue with no card resolves to an empty item id: skip it, don't fail.

## Right model for the job

Never hardcode a model. Config names a `(model, effort)` pair per **role**;
classify the work item, then resolve the pair. The role table, the effort ladder,
and the routing rule live in [`references/models.md`](references/models.md) —
read it before the first spawn of a session.

1. **Classify the item.** Default **`heavy`**. Choose `light` only when *all* hold:
   one file/component touched, no schema change or `db_gate`, no new dependency,
   and acceptance criteria fully enumerated on the work item. Ambiguous → `heavy`.
   A re-spawn after a failed round, or a fix round from adversarial review, goes up
   a rung (`heavy` at `xhigh`, or `max` if `xhigh` already failed).
2. **Resolve** `models.<role>` → model + effort. A flat `model:`/`effort:` config
   applies to every role.
3. **Legal on this harness?** The harness reference's effort map holds the ceiling
   (`codex` tops out at `high`; `pi` at `xhigh`; `cursor` encodes effort in the
   model id). If the role's effort exceeds it, **clamp and say so** — or route the
   item to a harness that reaches it. Validate the effort string against the ladder
   **yourself**: `claude` accepts a typo'd `--effort` with only a warning and then
   runs at the default, which scrolls away unseen in a TUI worker.
4. **Report the choice** when reporting the spawn, after the routed skill:
   `#23 → /implement · heavy · opus-5 · xhigh`. A wrong call is then visible and
   correctable in one sentence. The skill field is the routed one, and it is a
   separate resolution from this one — see
   [Reporting to the user](#reporting-to-the-user).

Neither flag fails loudly when wrong: `claude` warns-and-defaults on a bad effort,
and `codex` silently ignores a `--model` placed before its subcommand. Where the
harness prints a startup banner (codex prints `model:` and `reasoning effort:`),
read it once after the spawn to confirm both landed.

**Both are members of one family: a failure mode that reports success.** The third is
the readiness gate — see
[Gate readiness before the first prompt](#gate-readiness-before-the-first-prompt),
which names the family and says how to answer the next one.

Thinking stays **on** for every worker at every effort. Thinking-off leaks tool
calls into plain text — they never execute and they poison later turns of an
unattended loop.

## "What next?" — pick the next work

When the user asks **what next / what should I run / what's ready**: resolve the
**ready queue** fresh (states change live, never cache).

A work item is **ready** when it carries the `ready-for-agent` label (from
`issue-tracker.md`) and every item in its `## Blocked by` list is closed (closed
= satisfied; only still-open deps block). Skip items already `in-progress` or in
the review state — a worker owns them.

Read the tracker CLI from `issue-tracker.md`, list open items, and for each read
its `## Blocked by` / `## Parent` edges (the `to-tickets` template). A child that
itself carries the `user-story` label is a **nested spec** — descend into its
children, never spawn it directly. Present **all ready items first** (they can
start in parallel), then fill to at least 5 with the soonest-unblocked blocked
items (fewest open deps first), noting what each waits on. Offer to spawn a worker
for whichever the user picks.

**Reconcile the board here.** This read is the one moment every open item's labels
*and* open-blocker count are already in hand — which is exactly what the
`Backlog`/`Ready` split needs — so it's where board drift gets repaired. There is no
separate sync command. For each open item, derive `Status` from the table in
`issue-tracker.md`'s [`## Project board`](../docs/agents/issue-tracker.md#project-board)
section and write it; the write is idempotent, so a consistent board costs nothing
and no card moves. Report only the cards that **changed** (`#4 In progress → In
review`), one line, after the queue — an unchanged board says nothing. Skip the
whole pass if the section is absent, and never let a board error block the queue
answer: the queue is the deliverable, the reconcile is a side effect.

The reconcile covers **every open item**, not just the ready ones — an item sitting
in `in-progress` or `to-review` still gets its card confirmed, and a closed item
already reached `Done` at close. A `user-story` parent's card follows the same table
against its own labels and state, per that section.

## "Work a #N" — batch-spawn its unblocked children

When the user says **work on #N / implement the unblocked tasks of #N / do #N,
max K**: don't ask which child — spawn a worker for **every unblocked child at
once**, capped at K (default 5). Resolve the children fresh exactly as in "What
next?" (recurse through any `user-story` child to reach implementable leaves).
Ports stay per-item (`N` = work-item number), so batch-spawned siblings never
collide. **Classify each child's role separately** — a batch usually mixes heavy
and light items, and giving them all one model is exactly the hardcoding this
avoids. **Resolve each child's verb separately too**, for the same reason: a batch
that mixes a bug and a feature splices `/diagnosing-bugs` into one prompt and
`/implement` into the other. One blanket skill for the whole batch is the same defect
as one blanket model. The verb is the one the child's own work item carries, and
where the child names none, the batch's own verb applies. Report which were spawned
(with skill · role · model · effort each), which are busy (a worker owns them), and
what each blocked child waits on.

Parent lifecycle and the `relates_to`/`## Parent` conventions are tracker/
`to-tickets` behaviour — see the project's `issue-tracker.md` and the worked
example for how a `user-story` parent moves as a function of its children.

## Spawn a worker (implement X)

When the user says **implement #N / implement X / start work on X**:

1. **Already exists?** (op 1, worktree-exists?) — if a worktree matches the slug,
   reuse it: get its worker handle (op 9) and just send the prompt (step 6). Only
   continue if nothing matches.
2. **Launch command** — classify the item's **role** and resolve its
   `(model, effort)` pair (see [Right model for the job](#right-model-for-the-job)),
   then compose `$CMD` from `references/harnesses/<harness>.md` using harness +
   model + effort + yolo. Preflight any harness-specific requirement the reference
   names; abort rather than send a dead prompt. **The routed skill is one of those
   requirements.** Where the verb resolved to a `worker` row
   ([Resolve the verb before you act](#resolve-the-verb-before-you-act)), confirm the
   skill is reachable by *this* harness, before you compose the prompt:
   - **claude** — the skill is a plugin skill, so confirm the plugin that ships it is
     installed. Every row in the routing table ships in `mattpocock-skills`, so the
     check is the `mattpocock-skills` line of the plugin check block in
     [`references/requirements.md`](references/requirements.md). Don't write a check
     of your own.
   - **any other harness** — there is no slash command to reach, so the reachable
     form is the row's Notes prose. Confirm the row has it. A `worker` row with no
     prose contract is not reachable on this harness.

   A failed check **aborts the spawn**. Say which skill, which harness, and that
   `/orchestrator-setup` installs the missing plugin. This is the one place a routed
   verb fails hard. So it fails before a worktree exists, and not inside a worker that
   cannot run its first instruction.
3. **worktree-create** (op 2) — branch + checkout + run `setup_cmd` via the tool's
   setup hook, off the default branch (or stacked, if the item stacks). Capture
   the worktree id/path.
4. **worker-create** (op 3) — start `$CMD`; capture the **stable** handle to
   prompt. Then **gate on readiness** before any prompt — see
   [Gate readiness before the first prompt](#gate-readiness-before-the-first-prompt).
5. **Claim the item first** — swap `ready-for-agent` → `in-progress` on the
   tracker (labels from `issue-tracker.md`), before prompting, so the board
   reflects the worker and "what next?" won't hand it out twice. Then **move its
   card to `In progress`** ([Board status](#board-status)) — same step, so the label
   and the card never disagree. Apply any parent-promotion the tracker conventions
   define (idempotent) — including the parent's own card, which sits in
   `In progress` while any child does.
6. **Write the checklist + deliver the prompt** — see below.
7. **Follow-along panel** (op 7, if the tool supports it) — open the work item as
   a tab inside the worker's worktree.

### Gate readiness before the first prompt

**A handle is not a worker.** Between `worker-create` (op 3) and the first `send`
(op 4), confirm the agent is actually accepting input. This gate applies to **every
harness** and to **every** first prompt, the review spawn included.

**The authoritative signal is a live agent process whose working directory is the
worktree.** That is a **process check**, not a screen check. Nothing else qualifies.
Three states leave no such process: a harness that has died, one waiting on a
first-run dialog, and one that never authenticated. From outside they are
indistinguishable, which is why one check covers all three.

**Two things that look like the signal and are not.** A terminal that reports itself as
running is reporting on the **shell**, which outlives the agent and is what then
receives the prompt. An idle-screen condition is met by an idle shell. Both report
ready for a worker that is already dead. On an alt-screen TUI the screen is worse than
useless. The buffer comes back as box-drawing noise. Scraping it for a shell prompt
finds one under a healthy TUI, and misses one under a dead agent.

**The concrete command belongs to the tool, not here** — it is op **3a** in
[`references/tools/<tool>.md`](references/tools/_operations.md), which is where a
command that changes per tool has its home. Which dialogs a harness can sit behind
belongs to [`references/harnesses/<harness>.md`](references/harnesses/codex.md).

**Where the harness reference names a first-run dialog, send and submit are two
steps:** type the prompt, confirm it reached the composer, then submit. One call that
does both cannot be inspected between them, and a prompt submitted into a dialog is
lost — worse, it can reach the shell underneath and execute as commands. Where the
harness has no such dialog, op 4 stays one step. The tool reference documents both
halves.

**This is the third member of a named family: a failure mode that reports success.**
The other two are already recorded — `claude` warns-and-defaults on a typo'd
`--effort`, and `codex` silently ignores a `--model` placed before its subcommand (see
[Right model for the job](#right-model-for-the-job)). Each returns a value meaning
"fine" for a question next to the one asked, and each costs a whole run before anyone
notices. **Recognise the shape, and do not answer it with a louder check of the same
kind.** Find the signal that is true of the thing you are asking about, and gate on
that. Rationale:
[`docs/adr/0017-gate-worker-readiness-on-a-process-check.md`](docs/adr/0017-gate-worker-readiness-on-a-process-check.md).

### The prompt: checklist + completion contract

The worker must **finish**, not stall before the PR/MR. Enforce it with the
file-based **checklist** (works across every harness, unlike claude-only
`TodoWrite`):

- Seed `.orchestrator/checklist-<item>.md` at the worktree root from
  [`references/checklist.template.md`](references/checklist.template.md). Drop any
  step whose recipe field is blank in config (e.g. no `db_gate` → drop the DB
  step). **The writing-pass box is unconditional** — it depends on no recipe field,
  so it ships on every item, including a pure-code one.
- The prompt tells the worker to **work the checklist top to bottom, ticking each
  box as it completes it, and not to end the turn while any box is unchecked.**

**Prompt quality is not this skill's job — it's `prompt-improver`'s.** That skill
(a dependency, see [`references/requirements.md`](references/requirements.md)) owns
the diagnosis checklist, the shared rules, and the per-model tuning. Don't restate
its rules here or work from memory of them.

1. **Draft** the worker prompt: the task, the acceptance criteria, the checklist,
   the project recipe, the evidence bar, the scope edges — and the **routed skill**,
   where the verb resolved to a `worker` row. The invocation is one more item in that
   list, at the same level as the criteria and the scope edges, and it goes into the
   **draft**, not into the sent prompt afterwards. The `prompt-improver` pass below
   must see it.
2. **Run it through `prompt-improver`**, naming the role's model so it applies the
   right profile (look the model up in [`references/models.md`](references/models.md)
   → its `prompt-improver` profile). Send the improved prompt, not the draft.
3. **Tell it this is an agentic-pipeline prompt.** `prompt-improver` handles this
   case explicitly: it keeps the tight task framing and the checklist, and applies
   only the model-specific tuning. A worker prompt must be deterministic and
   finishable unattended, so the open senior-partner rewrite must **not** be
   applied — say so when invoking, or it can reshape the contract. **This framing is
   also what protects the spliced invocation.** The rewrite keeps a literal
   instruction literal. The open rewrite is the one that turns a command into a
   suggestion, and a suggestion is the *may* this change exists to remove.

**Word the routed skill as a command the worker runs, not as advice.** The first
thing the prompt asks of the worker is to enter the skill: `Run /implement.` — an
imperative, in the prompt's own voice. Never *you may use*, *consider*, *if it
helps*, or a mention of the skill inside a sentence about something else. A worker
that reads a suggestion does the work freehand, which is the defect the routing
table exists to close. The skill then runs **inside** the completion contract, not in
place of it. The checklist above still holds every box, and
`.orchestrator/checklist-<item>.md` stays the file this session reads for progress.
Which skill it is comes from the routing table
([Resolve the verb before you act](#resolve-the-verb-before-you-act)), and what to
hand it comes from that row's Notes. How to word the rest of the prompt is
`prompt-improver`'s, as above.

Three things `prompt-improver` can't know, so state them in the draft:

- **Whole spec, first turn.** A worker has no human to answer a follow-up, so
  "ask the user" is never an option — where something is genuinely unknown, name
  the assumption to take instead.
- **Cap delegation.** A worker already inside a worktree shouldn't fan out;
  `prompt-improver`'s subagent cap is the wording to use.
- **Scope edges are the exception to positive-framing.** Name the neighbouring
  files, features, and refactors the worker must not touch — negatively, on
  purpose.
- **One scope edge ships on every item: the Browser surface.** Where an item needs
  UI proof, the worker drives the declared surface, `playwright-cli`. **A browser MCP
  that the worker's session happens to expose is out of bounds, whichever one it
  is.** Write the edge about the class, so a new ambient MCP that appears tomorrow is
  already covered. Name Chrome DevTools MCP as the recognisable instance. Carry the
  reason with the rule, because a worker that reads a bare prohibition is the worker
  that reverses it later. The reason has two halves. The declared surface emits
  Playwright code, which is the raw material for a durable test, and an MCP call emits
  a transcript entry that dies with the session. And an undeclared tool has no home in
  this repo, which is this repo's named failure mode in a different form. **Tool
  availability is not tool endorsement.** An unattended worker's tool list comes from
  global config the worker did not choose. So anything this repo has not declared is
  not sanctioned by default. That framing holds for the next ambient dependency too,
  not only for this one. The edge ships even on an item with no UI. There it costs one
  sentence, and it closes the reading that an idle browser tool is an invitation.
  Definition: the **Browser surface** entry in [`CONTEXT.md`](CONTEXT.md). Rationale
  and the accepted risk:
  [`docs/adr/0012-playwright-cli-is-the-only-browser-surface.md`](docs/adr/0012-playwright-cli-is-the-only-browser-surface.md).
  Enforcement is documentary, so this prompt is where the rule reaches the worker.

**Writing quality is not this skill's job either — it's `simple-english`'s.** That
skill (a dependency, see
[`references/requirements.md`](references/requirements.md)) owns every writing rule.
Tell the worker to run the prose it changed through `simple-english` in
**pragmatic** mode, before it commits. State only which text, in which mode, and
what stays untouched — the **simple-english** and **Prose deliverable** entries in
[`CONTEXT.md`](CONTEXT.md) hold the definitions. Don't restate a sentence limit, a
substitution or a rule number here or in the prompt. Rationale:
[`docs/adr/0011-delegate-technical-writing-to-simple-english.md`](docs/adr/0011-delegate-technical-writing-to-simple-english.md).

Four things the prompt must carry:

- **Which text.** The four **Prose deliverable** classes in `CONTEXT.md`. Two classes
  bind a worker only when its diff contains them: the markdown in the diff, and the
  strings a Python file prints. Two classes bind **every** worker on **every** item:
  the review note on the work item, and the PR/MR body. So a worker on a pure-code
  item is never exempt. The fourth class is orchestrator reports, which bind this
  session and no worker — see [Reporting to the user](#reporting-to-the-user).
- **Which mode.** Pragmatic, which keeps domain vocabulary. Every `CONTEXT.md`
  glossary term — Tool, Harness, Worker, Pinned SHA — survives the pass unchanged.
  Never ask for strict mode: it needs a dictionary this repo does not have.
- **What stays byte-identical.** Code blocks, identifiers, file paths, commands,
  quoted error strings, YAML and JSON keys, link targets, and proper nouns. A pass
  that edits one of these can break a cross-reference or a copy-pasteable command.
- **How far it reaches.** Only the prose the worker already changes. A one-line
  documentation item stays a one-line diff. A repo-wide rewrite is separate work.

**Keep the three delegations apart.** A worker that runs one artifact through two of
them acts on contradictory instructions. The orchestrator invokes `prompt-improver`
on the prompt. The worker invokes `simple-english` on its own deliverable prose.
`ponytail` governs how much exists at all. The ordering rule and the one real
collision sit in the **Prose deliverable** entry of [`CONTEXT.md`](CONTEXT.md).
Point the worker at that entry rather than re-deriving the rule in the prompt.

**The `commit` box is a loop, not a step.** It covers a series of commits, and the
worker lands each one as soon as that slice is complete. So the prompt carries the two
conditions for one slice: one logical change, and the branch self-consistent at that
commit. It names the message convention — Conventional Commits, an imperative subject,
and a body that says why when the subject cannot carry it. It says that a trivial item
is one commit, and that this is not a violation. It puts the writing pass before the
commit that carries the prose, which is what the writing-pass box on the checklist also
says. Give the worker the rule in plain English, whatever the harness. Definition: the
**Commit slice** entry in [`CONTEXT.md`](CONTEXT.md), which the prompt points at rather
than restating. Rationale, the rejected options and the accepted risk:
[`docs/adr/0013-workers-commit-in-contextualised-slices.md`](docs/adr/0013-workers-commit-in-contextualised-slices.md).

Bake in the project recipe: boot the app with `run_recipe` on the per-item `ports`
for evidence; satisfy `db_gate` if configured; meet the `evidence` bar (real-data
proof + full suite — unit tests alone are not enough); post the review note on the
**work item** (What to review / Main changes / How to test / Evidence); flip to
the review state.

**The worker flips its own card.** That last step is the worker's, not yours, so the
prompt must carry the board move with it: give the worker the two literal `gh`
commands — the label swap and the `In review` write, with the real ids from
`issue-tracker.md`'s `## Project board` section substituted in. A worker can't look
up a field id it wasn't given. Omit the board command if that section is absent.

**Harness shape:** a **claude** worker **does** enter the routed skill — the
invocation is a literal slash command in the prompt (`/implement`), and its other
slash skills (`/ponytail:ponytail`) stay available on top. See
`references/harnesses/claude.md`. **Any other harness** gets the **same contract in
plain English** — no slash commands, no "TodoWrite" wording; spell out the numbered
checklist steps as prose. **The routed skill takes that same split.** A harness with
no slash commands gets the skill's contract as prose, from the *Without slash
commands* sentences in the row's Notes column of
[`references/skill-routing.md`](references/skill-routing.md). Copy the substance of
those sentences into the draft prompt as the worker's opening instruction, in the
place the slash command takes on claude. **Never send a slash command to a harness
that cannot parse one** — it reads as literal text and the worker starts cold, which
is worse than the prose contract because it looks like it worked. This is the same
plain-English rule as every other part of the contract, not a second mechanism.

**Per-item ports.** Derive from the work-item number `N` per config's `ports`
(e.g. `FE=3000+N`), so parallel workers never collide and the port reads back to
the item. Check reuse before booting; tear down after evidence — per the recipe.

## Monitor workers

- **Topology / handles:** `worktree-list` (op 8), `worker-list` (op 9) — map slug
  → worktree → handle.
- **Exact progress:** read `.orchestrator/checklist-<item>.md` — which boxes are
  ticked.
- **Busy vs idle:** `wait-idle` (op 6). A TUI harness (claude) has sparse
  read-tail, so trust the checklist + idle state over scraping.
- **Stall detection:** unchecked boxes **and** an idle terminal → the worker
  stopped early. Re-prompt with the remaining (unchecked) steps (op 4). Prefix a
  code-changing follow-up appropriately for the harness. A worker that stalls or
  flails **twice** was mis-routed — tear it down and re-spawn a rung up
  (`light` → `heavy`, or `heavy` at `max`), and say that's what happened.

## Adversarial review (when config's `review.enabled`)

When a work item reaches the review state and review is enabled:

1. **Spawn a review worker** on the impl branch (its own worktree, op 2 with
   `--base-branch <impl-branch>`), harness per config, model + effort =
   `models.review` (default effort `high` — review accuracy holds at lower effort).
   Assert the review model's vendor differs from the impl model's
   (`references/models.md`) — refuse if same vendor. **Then gate on readiness before
   the review prompt**, per
   [Gate readiness before the first prompt](#gate-readiness-before-the-first-prompt).
   A review spawn needs this more than an impl spawn, not less. Its worktree is fresh,
   and its harness is usually the *other* vendor's — so it is the one this machine has
   launched least often. A lost review round is also silent: the impl worker waits, the
   findings never arrive, and nothing reports an error.
2. **Prompt it to review** the diff/MR against the work item's acceptance
   criteria — drafted, then run through `prompt-improver` for the review model's
   profile, same as a spawn prompt. Say it's a **code-review prompt**:
   `prompt-improver` has a specific rule for these — **ask for coverage, filter
   downstream** — and it's the one that matters most here. Never "only
   high-severity", "be conservative", or "don't nitpick": every model here obeys
   that literally and silently drops real bugs. The orchestrator ranks when it
   reads the verdict. The reviewer posts a verdict on the work item: **approve**
   or **request-changes + findings**.

   **Four substitutions this prompt needs, learned by running the flow.** Each closes a
   way a reviewer produces a plausible verdict that is not a review:

   - **Run the suites yourself, rather than trusting the commit messages.** A worker's
     own claim that a suite is green is the claim under review, not evidence for it.
   - **Give every acceptance-criteria checkbox its own verdict.** One verdict per box,
     named. A summary over a group of boxes hides the one box that failed.
   - **Do not spawn sub-agents.** The reviewer is already the second opinion. A
     sub-agent's findings arrive unattributed and cost a round.
   - **Report per axis, with a confidence and a severity on each finding.** The axes
     stay `/code-review`'s two. This adds only the two per-finding fields, which is
     what lets this session rank without re-reading the diff.

   These four are prompt *content*, so they go into the draft and through
   `prompt-improver` with the rest — they restate no rule of the two-axis contract.
3. **On request-changes:** re-prompt the **original impl worker** with the
   findings to fix, then re-review. Loop, bounded at `review.rounds` (default 3).
   Each fix round steps the impl worker's effort up one rung — a finding the model
   missed at `high` is what `xhigh` is for. In a fix round, one finding is one slice,
   so the reviewer can map each fix to the finding it answers. **The fix prompt
   re-enters the same routed skill the original spawn used** — not a re-resolution of
   the verb, and not `/code-review` because a review produced the findings. The worker
   resumes in the posture it started in. Effort steps up, and the skill does not change.

   **A fix prompt written from the findings alone is incomplete.** The findings say what
   is wrong. They carry nothing about who is fixing it. Three things go in besides:

   - **The routed skill, as a literal invocation.** `/implement`, not a sentence
     mentioning `/implement`. Same rule as a spawn prompt, for the same reason — a
     mention reads as a suggestion, and the worker then works freehand. **A fix prompt
     is a fresh prompt to a worker whose context can be gone**, so it re-states the
     invocation instead of relying on the worker to remember entering it.
   - **The worker's own harness, model, effort and role.** Effort steps up each round,
     so the worker cannot infer its current setting from the last one it saw.
   - **The reviewer's model, effort and harness, with the cross-vendor fact stated.**
     Not a footnote. A worker that does not know a **different vendor** produced the
     findings reads them as its own second-guessing, and argues with them instead of
     fixing them.

   Word these the way a spawn prompt words the same facts. Then run the fix prompt
   through `prompt-improver` as an agentic-pipeline prompt. A fix prompt is a worker
   prompt, so every rule in
   [The prompt: checklist + completion contract](#the-prompt-checklist--completion-contract)
   applies to it unchanged.
4. **On approve, or after the last round regardless:** gather evidence and flip
   the item to **human review**. The item stays `in-progress` through the loop (a
   worker owns it); it flips only when the loop concludes. Merge is always a human
   step.

On demand: **"review #N adversarially"** runs this flow directly even if review is
off in config.

## Close a task

When the user says **close task #N / it's done / wrap up <slug>**: run one **Close
transaction**. It is eight steps in one fixed order, defined in
[`CONTEXT.md`](CONTEXT.md). The split is by judgement. Steps 1 to 3 need it, so they
are the prose below. Steps 4 to 8 need none, so `scripts/close_item.py` owns them.
Rationale:
[`docs/adr/0015-close-is-a-deterministic-transaction.md`](docs/adr/0015-close-is-a-deterministic-transaction.md).

**The maintainer's words are the gate.** Read the instruction against this table
before you touch anything:

| Instruction | Teardown |
|---|---|
| "task done, merge and close" | yes |
| "close 20" | yes |
| "wrap up 20" | yes |
| "flip 20 to review", "advance 20" | no |
| ambiguous, or not said | ask first |

The explicit ask **is** the confirmation. So never ask again for a merge the
maintainer requested in the same turn. A **no** row is an advance and not a close:
swap the label to the review state, move the card to `In review`
([Board status](#board-status)), and stop there. On the **ask first** row, ask in one
line and wait.

Then **find the worktree** (op 8) — display name = branch = slug. Keep its id and
its path. If nothing matches, the item is probably closed already. Do the label steps
that still apply, and say so.

### Steps 1 to 3 — judgement, in this session

**This orchestrator session does all three, and no worker is prompted for any of
them.** A worker can be idle or out of context by now, and its worktree is what step
8 removes. Step 1 needs a working tree, so it runs **inside the item's worktree**.
That worktree is still there, because teardown has not run yet. The main checkout
(config's `repo`) stays on the default branch. Step 3 is an API call and needs no
checkout, which is why only the first two steps care where they run.

1. **Resolve conflicts against the default branch.** Merge the default branch into
   the item's branch, inside the item's worktree. If it conflicts, invoke
   `resolving-merge-conflicts`. That skill owns the procedure and this repo copies no
   step of it. So never resolve a hunk from memory.
2. **Push the mergeable branch.**
3. **Merge the PR.** The maintainer made this decision already, and you are carrying
   it out
   ([`docs/adr/0016-the-orchestrator-merges-when-asked.md`](docs/adr/0016-the-orchestrator-merges-when-asked.md)).

### Steps 4 to 8 — `close_item` owns the order

`scripts/close_item.py` holds the ordering, the gates, the exit codes and the
refusal reasons. **Never restate one of them here, in a prompt, or in a report.** A
second copy is a second source of truth. Read the plan the seam emits.
`python3 -m scripts.close_item --help` is the argument surface, and the module
docstring is the step table.

```bash
python3 -m scripts.close_item --issue <N> --pr <PR> \
  --repo <config's repo> --worktree <the path from op 8> \
  --remove-label <the review label> \
  --project-number <n> --project-owner <owner> --project-id <id> \
  --status-field-id <id> --done-option-id <the `Done` option id> \
  --teardown-command '<op 10, with the ids filled in>'
```

Three things the seam never learns, so you pass them in:

- **The teardown command, as a string.** Read it from
  [`references/tools/<tool>.md`](references/tools/_operations.md) (op 10) and
  substitute the ids. Pass that whole line to `--teardown-command`. So the seam holds
  no `orca` command, and a new tool stays a markdown change. The checklist file dies
  with the worktree, so nothing cleans it up.
- **The board coordinates, as arguments.** Read the five values from
  `docs/agents/issue-tracker.md`'s
  [`## Project board`](../docs/agents/issue-tracker.md#project-board) section. Where
  that section is absent, omit them. The card write is then a no-op
  ([Board status](#board-status)).
- **Whether to mutate. The default invocation is a dry run.** It resolves every
  precondition, prints the plan as JSON, and changes nothing. Read that plan. Then
  re-run it with `--execute`. Teardown needs `--execute --teardown` together, and
  only where the table above says yes.

**Parent-close stays yours.** The seam closes one item. Where the tracker conventions
define a parent close, apply it after the seam exits clean. That is the last child
closed → close the parent, and the parent's card → `Done`. Then report per
[Reporting to the user](#reporting-to-the-user).

## Reporting to the user

An orchestrator session runs long and the user reads it between other work. They
cannot hold "we're on round 2 of 3 for #38" across turns, so every report restates
it. Shape output for acting on, not for completeness:

- **Lead with state, not narration.** First line is the board: what changed and
  what's running.
  `#38 b5-contacts spawned · /implement · heavy · opus-5 · xhigh. 2 workers live.`
  Never open with what you're about to do.
- **Name the skill you routed to.** A verb resolved through
  [`references/skill-routing.md`](references/skill-routing.md) names its skill in the
  lead line, in the same turn the skill ran. A wrong route then costs one sentence to
  correct. `/to-spec ran here. Spec is #47, labelled ready-for-agent.` Where no skill
  was routed to — an unmapped verb the user declined, or a session that cannot reach
  the skill — say that instead. The lane needs no line of its own: `ran here` and a
  spawn already read as the two lanes.
- **A spawn line carries four fields, in this order:** the routed skill, the role,
  the model, the effort — `#23 → /implement · heavy · opus-5 · xhigh`. The skill sits
  first because it is what the worker does. The other three are how hard it thinks.
  A batch-spawn reports the four fields **per child**, so a mixed batch shows two
  different skills. A spawn with no routed skill drops the field and keeps the other
  three.
- **Restate position every turn.** A worker's progress is `checklist 4/7`, a review
  loop is `round 2 of 3`. Read it off the checklist file and the round counter —
  don't ask the user to remember.
- **One table or list, capped at 5 rows.** More than 5 ready items or 5 findings →
  rank and split (`start now` vs `blocked`, `must-fix` vs `noted`). Five ranked
  beats twelve flat, and the ready queue already promises "at least 5".
- **End with one action the user can take now.** `Spawn #41 next?` / `#38's MR is
  green — merge it and say "close 38".` The merge decision and the teardown
  authorisation are the only human steps; name whichever is pending.
- **A close report names which steps ran and which refused**, read off the plan the
  seam emitted ([Close a task](#close-a-task)), and ends with the one action left.
  `#20 closed: steps 1 to 7 ran, teardown refused. Cause: the worktree holds
  src/api.ts. Commit it or stash it, then say "close 20" again.`
- **Matter-of-fact failures.** Location, cause, fix — no "uh oh", no apology.
  `#38 idle with checklist 4/7 (evidence unchecked). Cause: port 3038 in use.
  Re-prompting with the remaining steps.`
- **Finish the item before raising the next.** A second problem noticed mid-flow
  goes at the end as its own one-line offer, not inline.
- **No preamble, no recap, no closer.** Don't re-list what you just did step by
  step; the checklist and the tracker are the record.

**These reports are a Prose deliverable too.** They are the fourth class in the
**Prose deliverable** entry of [`CONTEXT.md`](CONTEXT.md), so the same writing rules
that bind a worker bind this session. Apply `simple-english` in pragmatic mode to
what you write here. Keep the untouchables byte-identical: a slug, a model id, a
label name, an effort string and a command stay exactly as they are. This session
enforces the standard on every worker, so its own output cannot be the
counter-example.

Break this when the user asks you to **explain** a routing or review decision
(answer in full), or before a **destructive** step — a teardown confirmation and a
refusal reason are spelled out, never compressed.

## Safety

- Confirm with the user before teardown **where the instruction is ambiguous or
  unsaid** — it kills the live worker terminal and can drop uncommitted work. An
  explicit "merge and close" **is** that confirmation, so a second ask is friction
  rather than safety (the table in [Close a task](#close-a-task)). The data-loss case
  is a dirty tree, and step 6 of the transaction refuses it rather than warning.
- Keep the main checkout (config's `repo`) on the default branch — all
  tracker/git-state ops run there. This orchestrator's own worktree branch is
  separate and irrelevant.
- Never advance an item to done before its PR/MR is actually merged.
