---
name: orchestrator
description: Orchestrate agent worker sessions across any workspace tool (orca/cmux/herdr), harness (claude/codex/pi/copilot/cursor), and frontier model. Pick the next ready work item, spawn a worker in its own worktree on the right model and effort for the job, prompt/monitor it via a file-based checklist, run optional cross-vendor adversarial review, and close finished work. Trigger on "what next", "what should I run/work on", "what's ready", "work on #N / implement #N / implement X", "spawn a worker", "start a session for X", "prompt worker Y", "what are the workers doing", "review #N adversarially", "close task #N / it's done / wrap up X", "list workers", "orchestrate".
---

# Orchestrator

This session is the **orchestrator**. It coordinates **worker** sessions. A
worker is a `(Tool, Harness, Model)` triple running against one work item in its
own worktree/terminal. Never do implementation work here — spawn a worker and
prompt it.

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
memory. Never copy a row into this body. One file holds the rows, so a newly declared
dependency is one new row. The vocabulary is the **Skill routing** and **Lane**
entries in [`CONTEXT.md`](CONTEXT.md). Rationale:
[`docs/adr/0014-route-verbs-to-skills-in-two-lanes.md`](docs/adr/0014-route-verbs-to-skills-in-two-lanes.md).

**Lane `inline` — invoke the skill here.** Invoke it in this session, against the
main checkout (config's `repo`), on the default branch. No worktree, no branch, no
spawn. Hand it what the row's Notes column says it needs. Then name the skill you
routed to in the report ([Reporting to the user](#reporting-to-the-user)). An
`inline` skill writes issues, docs or conversation, and never source, so "never do
implementation work here" holds. A verb that writes source is a `worker` row, and
that law is what puts it there.

**Lane `worker` — nothing changes yet.** A `worker` verb keeps the spawn flow below
exactly as it is today. The splice of the invocation into the spawn prompt is
separate work, and it has not landed.

**A queue question is not a verb.** A bare `/orchestrator`, and *what next* / *what
should I run* / *what's ready*, resolve to no skill and route nowhere. Answer them
with ["What next?"](#what-next--pick-the-next-work), unchanged.

**An unmapped verb costs one line, then proceeds.** A verb that matches no row is
not a near miss to act on. Ask once, in one line: name the closest row and the verb
it holds, and ask whether to route there. `Nothing routes "audit the labels". Closest
is triage -> /triage. Route there?` Then wait for the answer. On yes, take that lane.
On no, or on a decline of the whole question, answer the verb freehand, the way this
session does today, and say in the report that no skill was routed to. Two failures
this closes: a fuzzy match into a skill nobody chose, and a silent freehand answer to
a verb that clearly wanted one.

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
4. **Report the choice** when reporting the spawn: `#N → heavy · opus-5 · xhigh`.
   A wrong call is then visible and correctable in one sentence.

Neither flag fails loudly when wrong: `claude` warns-and-defaults on a bad effort,
and `codex` silently ignores a `--model` placed before its subcommand. Where the
harness prints a startup banner (codex prints `model:` and `reasoning effort:`),
read it once after the spawn to confirm both landed.

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
avoids. Report which were spawned (with role · model · effort each), which are busy
(a worker owns them), and what each blocked child waits on.

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
   names (e.g. claude `/implement` plugins); abort rather than send a dead prompt.
3. **worktree-create** (op 2) — branch + checkout + run `setup_cmd` via the tool's
   setup hook, off the default branch (or stacked, if the item stacks). Capture
   the worktree id/path.
4. **worker-create** (op 3) — start `$CMD`; capture the **stable** handle to
   prompt.
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
   the project recipe, the evidence bar, the scope edges.
2. **Run it through `prompt-improver`**, naming the role's model so it applies the
   right profile (look the model up in [`references/models.md`](references/models.md)
   → its `prompt-improver` profile). Send the improved prompt, not the draft.
3. **Tell it this is an agentic-pipeline prompt.** `prompt-improver` handles this
   case explicitly: it keeps the tight task framing and the checklist, and applies
   only the model-specific tuning. A worker prompt must be deterministic and
   finishable unattended, so the open senior-partner rewrite must **not** be
   applied — say so when invoking, or it may reshape the contract.

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

**Harness shape:** a **claude** worker may use its slash skills (`/implement`,
`/ponytail:ponytail`) — see `references/harnesses/claude.md`. **Any other harness**
gets the **same contract in plain English** — no slash commands, no "TodoWrite"
wording; spell out the numbered checklist steps as prose.

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
   (`references/models.md`) — refuse if same vendor.
2. **Prompt it to review** the diff/MR against the work item's acceptance
   criteria — drafted, then run through `prompt-improver` for the review model's
   profile, same as a spawn prompt. Say it's a **code-review prompt**:
   `prompt-improver` has a specific rule for these — **ask for coverage, filter
   downstream** — and it's the one that matters most here. Never "only
   high-severity", "be conservative", or "don't nitpick": every model here obeys
   that literally and silently drops real bugs. The orchestrator ranks when it
   reads the verdict. The reviewer posts a verdict on the work item: **approve**
   or **request-changes + findings**.
3. **On request-changes:** re-prompt the **original impl worker** with the
   findings to fix, then re-review. Loop, bounded at `review.rounds` (default 3).
   Each fix round steps the impl worker's effort up one rung — a finding the model
   missed at `high` is what `xhigh` is for. In a fix round, one finding is one slice,
   so the reviewer can map each fix to the finding it answers.
4. **On approve, or after the last round regardless:** gather evidence and flip
   the item to **human review**. The item stays `in-progress` through the loop (a
   worker owns it); it flips only when the loop concludes. Merge is always a human
   step.

On demand: **"review #N adversarially"** runs this flow directly even if review is
off in config.

## Close a task

When the user says **close task #N / it's done / wrap up <slug>**: run teardown in
order.

1. **Find the worktree** (op 8) — display name = branch = slug. Set the worktree
   id/path. If none matches, say so (maybe already closed) and do only the label
   steps that still apply.
2. **Advance the tracker state** (labels from `issue-tracker.md`, states mutually
   exclusive — swap, never stack), from the main checkout (config's `repo`), and
   move the card with it ([Board status](#board-status)):
   - work done, PR/MR open → review state, card → `In review`.
   - **merged** → pull the merge into local default branch **first**, then flip to
     done and close the item, card → `Done`. Merging is a human step; only advance
     to done once the PR/MR is actually merged. If unmerged, stop at the review
     state — the card **stays** at `In review`; never write `Done` for an unmerged
     PR — and say what's pending.
   - Apply parent-close if the tracker conventions define it (last child closed →
     close the parent), including the parent's card → `Done`.
3. **Confirm nothing is lost** — check the worktree is clean before removing. A
   **dirty** tree with intentional work is the data-loss case; call it out before
   proceeding.
4. **teardown** (op 10) — removes the worktree, kills the worker terminal, deletes
   the branch. The checklist file dies with the worktree (gitignored) — no
   cleanup.

## Reporting to the user

An orchestrator session runs long and the user reads it between other work. They
cannot hold "we're on round 2 of 3 for #38" across turns, so every report restates
it. Shape output for acting on, not for completeness:

- **Lead with state, not narration.** First line is the board: what changed and
  what's running. `#38 b5-contacts spawned · heavy · opus-5 · xhigh. 2 workers live.`
  Never open with what you're about to do.
- **Name the skill you routed to.** A verb resolved through
  [`references/skill-routing.md`](references/skill-routing.md) puts the skill in the
  same turn it ran, in the lead line, so a wrong route costs the user one sentence to
  correct. `/to-spec ran here. Spec is #47, labelled ready-for-agent.` Where no skill
  was routed to — an unmapped verb the user declined, or a session that cannot reach
  the skill — say that instead. The lane the skill ran in needs no line: `ran here`
  and a spawn already read as the two lanes.
- **Restate position every turn.** A worker's progress is `checklist 4/7`, a review
  loop is `round 2 of 3`. Read it off the checklist file and the round counter —
  don't ask the user to remember.
- **One table or list, capped at 5 rows.** More than 5 ready items or 5 findings →
  rank and split (`start now` vs `blocked`, `must-fix` vs `noted`). Five ranked
  beats twelve flat, and the ready queue already promises "at least 5".
- **End with one action the user can take now.** `Spawn #41 next?` / `#38's MR is
  green — merge it and say "close 38".` Merge and teardown are the only human steps;
  name whichever is pending.
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
(answer in full), or before a **destructive** step — teardown confirmation and a
dirty-tree warning are spelled out, never compressed.

## Safety

- Confirm with the user before teardown — it kills the live worker terminal and
  can drop uncommitted work. The data-loss case is a dirty tree (step 3).
- Keep the main checkout (config's `repo`) on the default branch — all
  tracker/git-state ops run there. This orchestrator's own worktree branch is
  separate and irrelevant.
- Never advance an item to done before its PR/MR is actually merged.
