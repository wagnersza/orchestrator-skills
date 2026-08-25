---
name: orchestrator
description: Orchestrate agent worker sessions across any workspace tool (orca/cmux/herdr), harness (claude/codex/pi/copilot/cursor), and frontier model. Pick the next ready work item, read whether it is a user story or a leaf task, spawn a worker in its own worktree on the right model and effort for the job, prompt/monitor it via a file-based checklist, run optional cross-vendor adversarial review, then merge and close finished work. Use this skill for every work-item action, and never wait for the user to type /orchestrator. A work verb plus a work-item number N is enough, with or without a "#". Trigger on "work on N", "work on #N", "implement N", "build N", "start N", "do N", "implement X", "spawn a worker", "start a session for X", "prompt worker Y", "what next", "what should I run/work on", "what's ready", "what are the workers doing", "list workers", "review N adversarially", "merge and close N", "merge N and close it", "close N", "close task #N", "it's done", "wrap up N", "orchestrate". A bare number after a work verb always means a tracked work item, so route it here rather than reading it as a file or a line number.
---

# Orchestrator

This session is the **orchestrator**. It coordinates **worker** sessions. A
worker is a `(Tool, Harness, Model)` triple running against one work item in its
own worktree/terminal. Never do implementation work here — spawn a worker and
prompt it. One bounded exception: step 1 of a [close](#close-a-task) resolves
conflicts in the item's own worktree, on the maintainer's explicit instruction
([`docs/adr/0016-the-orchestrator-merges-when-asked.md`](docs/adr/0016-the-orchestrator-merges-when-asked.md)).

The vocabulary (Tool, Harness, Model, Effort, Role, Vendor, Worker, Yolo mode,
Adversarial review, Ready queue, Checklist, Project recipe, Phase, Item automation) is
defined in [`CONTEXT.md`](CONTEXT.md).

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

**The reads every flow makes come from
[`references/tracker-reads.md`](references/tracker-reads.md).** That file holds one read
per section, with the command for `gh` and the command for `glab`. So no flow step and
no session invents a flag. Read the row you need at the moment you need it, never from
memory.

**Check a tracker read before you parse it.** The exit code is the check, and that file
holds the one shape for it. A tracker CLI that fails writes prose rather than JSON, so
an unchecked parse reports the parser and never the cause. Where a read fails, **report
it in one line: the command that ran, and the tracker's own first line.** Then stop.
Spawn nothing, write no label and move no card. That is the same answer a tick gives
with its `unreadable` outcome
([On the wake](#on-the-wake--one-response-per-outcome)). Rationale:
[`docs/adr/0039-a-tracker-read-has-a-verified-command-in-the-skill.md`](docs/adr/0039-a-tracker-read-has-a-verified-command-in-the-skill.md).

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

Throughout, address a worker by its **slug**. The form is `<N>-<slug>`: the work-item
number, then the ticket prefix. So `#38 B5 · Contacts` becomes `38-b5-contacts`. The
number comes first, so a worktree name identifies its work item with no lookup. Where
the tool can hold a link to the work item, op 2 records it as well. The link then lives
outside the name ([`references/tools/<tool>.md`](references/tools/_operations.md)).

### Resolve the plugin root, and prove the seam runs

**Three seams live in this plugin, and none of them is on the `PATH`.** They are
`scripts/worker_state.py` (readiness and the tick), `scripts/close_item.py` (steps 4
to 8 of a **Close transaction**) and `scripts/merge_train.py` (the order of a **Merge
train**). All three sit in `scripts/` at the **plugin root**, and
**that directory is never the working directory of a caller**. This session runs in the
target repo, and a tick runs in a worker worktree. So the module form
(`-m scripts.<module>`) finds no module there, and the seam is unreachable. The term is
the **Plugin root** entry in [`CONTEXT.md`](CONTEXT.md).

**Resolve the root once, here, with this command.** It covers both install shapes: a
plugin-cache install, whose version segment changes on every update, and a clone. It
prints nothing where the machine holds neither shape.

```bash
PLUGIN_ROOT=$(python3 -c "import pathlib;h=pathlib.Path.home()/'.claude/plugins';c=list(h.glob('cache/*/orchestrator-skills/*/scripts/worker_state.py'))or list(h.glob('marketplaces/*/scripts/worker_state.py'));print(max(c,key=lambda p:p.stat().st_mtime).parents[1] if c else '')")
python3 "$PLUGIN_ROOT/scripts/worker_state.py" ready --help >/dev/null && echo "$PLUGIN_ROOT"
```

**The second line is the preflight, and a non-zero exit aborts the spawn.** It runs
`--help`, so it mutates nothing. Run it before the first spawn of a session, which puts
it before the first **Item automation** exists. Say which root it printed. Where it
fails, say that the plugin is installed and its seams are not reachable. Then point the
user at `/orchestrator-setup`, the same as any other missing dependency. The three sit
in one directory, so one check answers for all of them.

**Every later invocation carries the resolved value, and never the variable.** Each
command you run opens its own shell, so that assignment does not survive to the next
one. The precheck of an **Item automation** is worse: the **Tool** stores that string and
runs it a minute later, in a shell that saw no assignment. So write the literal path in.
Everywhere in this body, `<plugin root>` is that value. It is the same kind of
placeholder as `<the path from op 2>`.

**This is a fourth member of a named family: a failure mode that reports success.** This
repo has its own `scripts/`, so the module form resolves inside a worktree of it and runs
a copy this session never reads. It works, and it reads the wrong file. The other three
are the `claude` effort typo, the `codex` model flag placed before its subcommand, and
the terminal that reports its shell (see
[Gate readiness before the first prompt](#gate-readiness-before-the-first-prompt)).
Rationale, the three forms that run, and the two this repo rejected:
[`docs/adr/0034-the-seam-invocation-carries-a-resolved-plugin-root.md`](docs/adr/0034-the-seam-invocation-carries-a-resolved-plugin-root.md).

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

**A flow this skill owns is not a verb either.** *merge and close N*, *close N*,
*wrap up N*, *list workers* and *what are the workers doing* each name a section
below, so they resolve to no skill and route nowhere. Run the section
([Close a task](#close-a-task), [Monitor workers](#monitor-workers)) and never ask the
user to confirm a route. The one skill a close invokes is
`resolving-merge-conflicts`, at step 1, and the close flow names it there.

**An unmapped verb costs one line, then proceeds.** A verb that matches no row is
not a near miss to act on. Ask once, in one line: name the closest row and the verb
it holds, and ask whether to route there. `Nothing routes "<the user's phrase>".
Closest row is <verb> → <skill>. Route there?` Then wait for the answer. On yes, take
that lane. On no, answer the verb freehand, the way this session does today. Then say
in the report that no skill was routed to. A decline of the whole question reads as a
no. This closes two failures: a fuzzy match into a skill nobody chose, and a silent
freehand answer to a verb that wanted one.

## Resolve the item shape before you pick a flow

**A work verb plus a work-item number is a complete instruction.** `work on N` needs
no slash command, no `#`, and no follow-up question. `N` is the work-item number the
tracker issued, and the `#` in front of it is optional. **The item picks the flow, and the
user's wording does not.** So read the item before you pick one:

1. **Read the item.** Use the tracker CLI from `docs/agents/issue-tracker.md`. You need
   its labels, its `## Blocked by` edges and its children.
2. **It carries `user-story`** → ["Work a #N"](#work-a-n--batch-spawn-its-unblocked-children).
   Batch-spawn every unblocked child at once. A child that carries `user-story` itself
   is a nested spec, so descend to the implementable leaves. Never spawn the parent.
3. **It carries no `user-story`** → [Spawn a worker](#spawn-a-worker-implement-x). One
   item, one worktree, one worker.
4. **The tracker read failed** → report it in one line and spawn nothing. A guess at
   the shape spawns the wrong number of workers.

**Ask nothing on the way.** Which child, which skill and which model are three
resolutions this session already owns, and each one has its own section. A work verb
asks in one case only: an unmapped verb, which costs one line
([Resolve the verb before you act](#resolve-the-verb-before-you-act)).

This resolution is independent of the other two. Verb → skill stays
[`references/skill-routing.md`](references/skill-routing.md), and work item →
`(model, effort)` stays [`references/models.md`](references/models.md). Rationale:
[`docs/adr/0029-a-work-item-number-is-a-complete-instruction.md`](docs/adr/0029-a-work-item-number-is-a-complete-instruction.md).

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
  this skill: the claim at spawn (step 5), the wake that ends the phase axis
  ([On the wake](#on-the-wake--one-response-per-outcome)), and close (step 2). Plus the
  reconcile below. **This session writes all three.** A worker writes no card.
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

**Report the Merge queue beside the ready queue.** This pass already holds every open
item's labels, so the queue costs no second read: it is every open item that carries
`to-merge`. **Promote a dragged card in this same pass.** This session writes the label for
a card that sits in the board's `To merge` column with no label yet, and that promotion
belongs to the pass which already reconciles the board
([`docs/adr/0038-the-to-merge-column-is-intent.md`](docs/adr/0038-the-to-merge-column-is-intent.md)).
Report the queue as its own capped list, under the ready queue. Then offer the train
([Merge the queue](#merge-the-queue)).

**This read is the whole fallback where the tool supports no automation surface.** `cmux`
and `herdr` create no schedule, so no tick fires and no `merge-requested` wake ever arrives
([Start the tick](#start-the-tick--one-item-automation-per-worker)). A maintainer who asks
what next still sees the queue, and can still ask for the train.

## "Work a #N" — batch-spawn its unblocked children

This flow runs when the item carries `user-story`
([Resolve the item shape before you pick a flow](#resolve-the-item-shape-before-you-pick-a-flow)).
The phrases that reach it are **work on N / work on #N / implement the unblocked tasks
of #N / do #N, max K**: don't ask which child — spawn a worker for **every unblocked
child at once**, capped at K (default 5). Resolve the children fresh exactly as in "What
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

This flow runs when the item carries no `user-story` label
([Resolve the item shape before you pick a flow](#resolve-the-item-shape-before-you-pick-a-flow)),
and when the user names work with no number at all. The phrases that reach it are
**work on N / implement #N / implement X / start work on X**:

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

   **The plugin root is a requirement of this spawn too.** Where this session has not
   resolved it yet, run the preflight now
   ([Resolve the plugin root, and prove the seam runs](#resolve-the-plugin-root-and-prove-the-seam-runs)).
   A failed check aborts the spawn as well, because step 4 gates readiness on that seam
   and step 8 writes it into a schedule. Both would then fail, and the schedule would
   fail silently.
3. **worktree-create** (op 2) — branch + checkout + run `setup_cmd` via the tool's
   setup hook, off the default branch (or stacked, if the item stacks). Capture
   the worktree id/path.
4. **worker-create** (op 3) — start `$CMD`; capture the **stable** handle to
   prompt. Then **gate on readiness** before any prompt — see
   [Gate readiness before the first prompt](#gate-readiness-before-the-first-prompt).
5. **Claim the item first** — swap `ready-for-agent` → `in-progress` on the
   tracker (labels from `issue-tracker.md`) **and add `phase:impl` in the same
   call**, before prompting, so the board reflects the worker and "what next?" won't
   hand it out twice. One write for both families means the work state and the
   **Phase** cannot disagree. Then **move its card to `In progress`**
   ([Board status](#board-status)) — same step, so the label and the card never
   disagree. The card derives from the work-state label alone, so the phase label
   moves no card
   ([`docs/adr/0021-phase-is-a-second-label-family.md`](docs/adr/0021-phase-is-a-second-label-family.md)).
   Apply any parent-promotion the tracker conventions
   define (idempotent) — including the parent's own card, which sits in
   `In progress` while any child does.
6. **Write the checklist + deliver the prompt** — see below.
7. **Follow-along panel** (op 7, if the tool supports it) — open the work item as
   a tab inside the worker's worktree.
8. **Create the Item automation** (op 11) — mandatory, and the last step of every
   spawn. See
   [Start the tick](#start-the-tick--one-item-automation-per-worker).

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

**One seam answers the gate, for every tool and every harness.** It is
`scripts/worker_state.py`, the same seam the tick's precheck asks. Readiness and a stall
are one question asked at two moments. No tool file implements this, and the
operation contract carries that as a prohibition
([`references/tools/_operations.md`](references/tools/_operations.md)). Rationale:
[`docs/adr/0019-readiness-is-a-tool-agnostic-process-check.md`](docs/adr/0019-readiness-is-a-tool-agnostic-process-check.md).

```bash
python3 <plugin root>/scripts/worker_state.py ready \
  --worktree <the path from op 2> \
  --process '<the pattern from references/harnesses/<harness>.md>'
```

`<plugin root>` is the value the preflight resolved
([Resolve the plugin root, and prove the seam runs](#resolve-the-plugin-root-and-prove-the-seam-runs)).

**The gate is harness-shaped, and the seam names no harness.** Only the `--process` pattern
varies, and each harness reference holds its own. Read it from there and never from memory.
Exit `0` is ready. Poll while it is not, and **abort the spawn** rather
than send a prompt into a dead terminal. Say which harness, which worktree, and what the
seam printed. Which dialogs a harness can sit behind belongs to that same reference
([`references/harnesses/<harness>.md`](references/harnesses/codex.md)). The argument
surface is `python3 <plugin root>/scripts/worker_state.py ready --help`, and the module
docstring is the signal it reads. Never restate either here or in a report.

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
[`docs/adr/0017-gate-worker-readiness-on-a-process-check.md`](docs/adr/0017-gate-worker-readiness-on-a-process-check.md),
whose signal ADR 0019 keeps and whose placement it narrows.

### The prompt: checklist + completion contract

The worker must **finish**, not stall before the PR/MR. Enforce it with the
file-based **checklist** (works across every harness, unlike claude-only
`TodoWrite`):

- Seed `.orchestrator/checklist-<item>.md` at the worktree root from
  [`references/checklist.template.md`](references/checklist.template.md). Drop any
  step whose recipe field is blank in config (e.g. no `db_gate` → drop the DB
  step). **A gate box drops on the same rule.** A **Layer** whose command is blank in
  the `gates:` block loses its box before this session sends the checklist. That is a
  supported configuration: a repo with no mutation runner ships no layer 4 box
  ([`references/quality-gates.md`](references/quality-gates.md),
  [`docs/adr/0032-quality-gates-are-a-layered-contract.md`](docs/adr/0032-quality-gates-are-a-layered-contract.md)).
  **The writing-pass box is unconditional** — it depends on no recipe field,
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
- **Ask for delegation, under the cap.** When the work splits, the worker delegates.
  It does not ask first. **At most 5 sub-agents run at once, per worktree.** The cap
  counts concurrent sub-agents, so a worker can run 5, read the reports, and then run
  5 more. **A sub-agent reads, searches and reports. It never writes the item's
  source**, because the worker owns every edit, every **Commit slice** and every
  **Gate**. **The worker delegates where its harness has a sub-agent surface.** A
  harness with none reads the same sentence, delegates nothing, and satisfies the
  instruction. Take the answer from the harness reference file under
  `references/harnesses/`, not from a guess. Name the reads the item needs, because a
  bare permission gets a worker that delegates nothing. Definition: the **Delegation
  cap** entry in [`CONTEXT.md`](CONTEXT.md). Rationale, the sentence this reverses and
  the accepted risk:
  [`docs/adr/0035-workers-delegate-to-sub-agents-under-a-cap.md`](docs/adr/0035-workers-delegate-to-sub-agents-under-a-cap.md).
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
  glossary term — Tool, Harness, Worker, Effort — survives the pass unchanged.
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
**work item** (What to review / Main changes / How to test / Evidence). **That note is
the worker's last act.**

**The worker writes no work-state label and moves no board card.** So the prompt hands
it no `gh` command for either one. This session writes the review state itself, in one
call with the removal of the `phase:review` label. It moves the card in the same step
([On the wake](#on-the-wake--one-response-per-outcome)). The two labels name one moment,
the end of the phase axis. One call is what keeps them consistent. A worker also cannot
see that moment. Whether review is on, and which round the item is on, are facts this
session resolves. Rationale:
[`docs/adr/0025-the-session-writes-the-review-state.md`](docs/adr/0025-the-session-writes-the-review-state.md).

**The `phase:*` label is not the worker's either.** This session owns the **Phase** axis
at both ends: the spawn writes `phase:impl` (step 5), and the wake writes every transition
after it. A worker that removes its own phase label leaves the tick with an item that reads as
human review. That worker's finish then wakes nothing
([On the wake](#on-the-wake--one-response-per-outcome)).

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

### Start the tick — one Item automation per worker

**A spawn with no tick is incomplete.** The last step of every spawn creates an **Item
automation** (op 11). One per worker, implementation and review alike. The **Tool** owns
the schedule, so it outlives this session, a restart of the harness and a reboot. It
ticks once a minute. A batch of five siblings gets five automations, one each.
Definitions: the **Item automation** and **Phase** entries in
[`CONTEXT.md`](CONTEXT.md). Rationale:
[`docs/adr/0022-item-automation-replaces-the-blocking-watch.md`](docs/adr/0022-item-automation-replaces-the-blocking-watch.md).

**The precheck is the whole tick.** `wake` asks the same predicate as `phase`. The
outcomes, their order and the back-off window are unchanged. On a due transition it
delivers the printed line itself. **No path through it exits 0**, so every run records as
skipped, no model loads and no agent runs on a tick. That command goes into op 11's
`<precheck-command>` placeholder:

```bash
python3 <plugin root>/scripts/worker_state.py wake --item <N> \
  --worktree <the path from op 2> \
  --process '<the pattern from references/harnesses/<harness>.md>' \
  --rounds <config's review.rounds> --stall-after <duration> \
  --back-off <duration> --repo <owner>/<name> \
  --marker-dir <the implementation worktree from op 2>/.orchestrator \
  --tracker-cli <gh or glab> --tracker-host <host> \
  --board-project <number> --board-owner <owner> --board-option <name> \
  --require-gate '<one per required layer, from config's gates: block>' \
  --handle <this session's terminal handle, from op 9> --title orchestrator \
  --send-command '<op 4, with {target} where the terminal goes and {text} where the line goes>'
```

**Where the tracker config has no `## Project board` section, the spawn passes none of the
three board flags.** That is a supported configuration, and the label path still fires
`merge-requested` there.

**`<plugin root>` is a literal path in this string, and never a shell variable.** The
**Tool** stores the precheck and runs it a minute later, in a shell that saw no
assignment, and with a working directory this session did not choose. So substitute the
value the preflight resolved
([Resolve the plugin root, and prove the seam runs](#resolve-the-plugin-root-and-prove-the-seam-runs)).
A precheck that carries the module form still runs inside a worktree of *this* repo. It
then runs that worktree's copy of the seam, and not the installed one.

**Op 11's `--prompt` and `--provider` are inert.** The CLI requires both. Neither one runs.
Exit 0 is what starts that agent, and no path through `wake` exits 0. Write a prompt that
says the tick delivered its own line, so a maintainer who reads the schedule is not misled.
Rationale:
[`docs/adr/0027-the-tick-delivers-its-own-wake.md`](docs/adr/0027-the-tick-delivers-its-own-wake.md).

**Resolve the config values once, here.** The seam parses no configuration file, and it
names no harness, no tracker and no tool. So the spawn is the one place they are read:

| Value | Where you read it | What it decides |
|---|---|---|
| the plugin root | the preflight in [Resolve the plugin root](#resolve-the-plugin-root-and-prove-the-seam-runs) | which copy of the seam a tick runs, and whether it runs at all |
| the round bound | config's `review.rounds` (default 3) | when `rounds-exhausted` fires instead of `verdict-request-changes` |
| the proof-phase gate | a non-blank `run_recipe`, or an `evidence` bar that asks for UI proof | whether this item can ever reach `phase:e2e` — see [The proof phase](#the-proof-phase) |
| the harness process pattern | `references/harnesses/<harness>.md` | what the `dead` outcome looks for |
| the stall window | longer than the item's slowest single step, so a worker thinking hard is never read as stalled | when `stalled` fires |
| the required gate layers | config's `gates:` block — one `--require-gate` per non-blank command, minus `deep` under the `lite` profile, and never `story` | when `gates-unproven` fires in place of a finish. With none the record is never read ([`references/quality-gates.md`](references/quality-gates.md)) |
| the marker directory | the item's implementation worktree (op 2), plus `/.orchestrator` | where a back-off marker lives, and what it outlives |
| the tracker CLI | `docs/agents/issue-tracker.md` | which command reads the labels and the comments, and which posts the wake comment |
| the tracker host | `docs/agents/issue-tracker.md`, where the tracker is self-hosted | which server those reads go to |
| the board project, owner and Status option | the [`## Project board`](../docs/agents/issue-tracker.md#project-board) section of `docs/agents/issue-tracker.md` | whether `merge-requested` can fire from a dragged card, not only from the `to-merge` label |
| this session's handle and title | op 9, against this session's own worktree | where the wake is delivered, `--handle` first and `--title` second |
| the send command | the tool file's operation 4 | how the tick delivers one line to a terminal |

Every value above is a flag on the command, except one. **The proof-phase gate is not a
flag.** The item's own `phase:*` label is what gates that outcome. So the gate decides which
label this session writes when the implementation finishes, and the seam reads that label.
It is the same gate the Browser-surface preflight uses, so the two cannot disagree about
when a proof phase applies.

`--back-off` suppresses a repeat of one outcome for one item, so an unanswered wake does
not queue sixty prompts in an hour. Pick a window at least as long as a fix round takes.
`--repo` is the tracker repository as `OWNER/NAME`, read from
`docs/agents/issue-tracker.md`.

**`--marker-dir` is where those back-off markers live, and it is an argument because the
watched worktree can change.** A reviewer reads the diff in its own worktree. A schedule
that follows the live worker takes the default directory with it, and an answered wake then
fires again from a fresh directory. Pass the item's implementation worktree instead. It
lives until step 8 of the **Close transaction** removes it, so the markers still die with
the work item.

**`--tracker-cli` and `--tracker-host` are the tracker read, and the wake comment that is
target three below.** `gh` on github.com is the default and needs no host, so this repo
passes neither flag. A self-hosted GitLab needs both, and it then needs no wrapper script
outside this repo.

**Resolve this session's own terminal handle here, and pass it as `--handle`.** Op 9 returns
`{handle, title}` for a worktree, so a session that can list a worker can list itself. The
wake has three targets, and the first one that succeeds ends the delivery:

1. **the handle** (`--handle`) — the identifier the tool issued, so no display string can
   move it.
2. **the title** (`--title`), which is `orchestrator`. `/orchestrator-setup` sets it (step
   5a of [`../orchestrator-setup/SKILL.md`](../orchestrator-setup/SKILL.md)). **A title is
   not a stable target.** The `claude` harness renames its own tab while the session runs,
   and that is the harness this session runs under. So the title is a second chance and
   never the mechanism.
3. **a comment on the work item**, through `--tracker-cli`. So a transition is recorded late
   rather than lost, which is the accepted risk in ADR 0022.

**Say which of the three is live on the spawn line**
([Reporting to the user](#reporting-to-the-user)). A comment-only wake is then a fact the
maintainer reads at spawn, rather than a silence they find many runs later. Rationale:
[`docs/adr/0024-the-wake-target-is-a-resolved-handle.md`](docs/adr/0024-the-wake-target-is-a-resolved-handle.md).

**The tick delivers the line it printed, and it decides nothing else.** It writes no label,
composes no prompt, spawns nothing and merges nothing. The **Item automation** entry in
[`CONTEXT.md`](CONTEXT.md) holds that prohibition. It is why every destructive act stays in
this session, where a human can interrupt it. The wake it delivers can land in a busy
terminal, and the tick does not wait for idle. That is the accepted risk in ADR 0027, and
`--back-off` is its mitigation.

**A tool with no automation surface spawns exactly as it does today.** Operations 11 and
12 are optional (`references/tools/_operations.md`), and `cmux` and `herdr` record them
as unsupported. Skip the step and change nothing else about the spawn. **Then say in the
report that the tick is unavailable on this tool.** The maintainer then knows to monitor by
hand ([Monitor workers](#monitor-workers)).

The argument surface is `python3 <plugin root>/scripts/worker_state.py wake --help`, and
the module docstring is the outcome table. **Never restate either here or in a report.**
What this session does when a tick wakes it is
[On the wake](#on-the-wake--one-response-per-outcome).

**A tick against a worktree that is gone is silent.** The seam exits 3, which is
non-zero, so the run records as skipped and nothing wakes. A live automation on a removed
worktree is a leak from a teardown that skipped op 12. Remove it by name
(`orchestrator-item-<N>`, op 12), because no wake can come for it.

## Monitor workers

- **Topology / handles:** `worktree-list` (op 8), `worker-list` (op 9) — map slug
  → worktree → handle.
- **Exact progress:** read `.orchestrator/checklist-<item>.md` — which boxes are
  ticked.
- **Busy vs idle:** `wait-idle` (op 6). A TUI harness (claude) has sparse
  read-tail, so trust the checklist + idle state over scraping.
- **Stall detection:** unchecked boxes **and** an idle terminal → the worker
  stopped early. Reset its context
  ([Reset the worker's context before every re-prompt](#reset-the-workers-context-before-every-re-prompt)),
  then re-prompt with the remaining (unchecked) steps (op 4). Prefix a
  code-changing follow-up appropriately for the harness. A worker that stalls or
  flails **twice** was mis-routed — tear it down and re-spawn a rung up
  (`light` → `heavy`, or `heavy` at `max`), and say that's what happened.

The tick is what fires this rule without your asking
([Start the tick](#start-the-tick--one-item-automation-per-worker)). The four
bullets above stay the way to answer *what are the workers doing* between wakes, and they
are the whole of monitoring on a tool with no automation surface.

## On the wake — one response per outcome

A tick wakes this session with the one line its precheck printed, and that line names one
of its outcomes. **The response is a lookup, not an interpretation.** Read the outcome,
run its row, and report per [Reporting to the user](#reporting-to-the-user).

**Write the `phase:*` label as the first act of every transition.** That write is what
acknowledges the wake. It also stops a repeat fire on the same fact a minute later. It is
also the mitigation ADR 0021 names for its own accepted risk, that an owned
item with no phase label reads as human review. So it goes first and never last. A phase
label moves no card ([Board status](#board-status)).

**The transition that ends the phase axis writes two labels in one call.** The removal of
the `phase:*` label and the write of the review state name one moment. So one row does
both: it adds `to-review` in the same `gh issue edit`, and it moves the card to
`In review`. There is then no first act and no second act to get wrong. The card derives
from the work-state label alone, so that half of the pair is what moves it
([Board status](#board-status)). **This session writes all three, and the worker writes
none of them** — its last act is the review note. Rationale:
[`docs/adr/0025-the-session-writes-the-review-state.md`](docs/adr/0025-the-session-writes-the-review-state.md).

**One row writes a work-state label and no phase label.** `merge-requested` fires in
human review, where the item wears no `phase:*` label to change. So its first act is that
work-state swap itself: it adds `to-merge`, removes the review state in the same call, and
moves the card. That write still acknowledges the wake, and it still stops a repeat fire on
the same fact a minute later.

| Outcome | Write first | Then |
|---|---|---|
| `implementation-complete` | `phase:impl` → `phase:e2e` where the proof-phase gate holds; else → `phase:review` where review is on; else remove it **and add `to-review` in the same call, and move the card to `In review`** | Proof: [The proof phase](#the-proof-phase). Review on: [Adversarial review](#adversarial-review-when-configs-reviewenabled) steps 1 and 2. Step 1 also **repoints the precheck** at the reviewer's worktree, with the review harness's process pattern — below. Review off: this wake is the hand-off to a human. Report the finish, the label pair you wrote, and the review you can still offer, in one line |
| `proof-complete` | `phase:e2e` → `phase:review` where review is on; else remove it **and add `to-review` in the same call, and move the card to `In review`** | The same two branches, with the proof already done |
| `gates-unproven` | nothing, because the item stays in the phase it is in | Reset the context and re-prompt — below. The line names one of four causes, so quote that cause and name the command to run again. Never move the item to review on this line |
| `verdict-approve` | remove `phase:review` **and add `to-review` in the same call, and move the card to `In review`** | [Adversarial review](#adversarial-review-when-configs-reviewenabled) step 4 — gather evidence and hand the item to human review |
| `verdict-request-changes` | nothing, because a fix round is inside `phase:review` | [Adversarial review](#adversarial-review-when-configs-reviewenabled) step 3, at the round the line names. That step also **repoints the precheck** back at the implementation worktree, with the implementation harness's pattern — below |
| `rounds-exhausted` | remove `phase:review` **and add `to-review` in the same call, and move the card to `In review`** | Step 4 again — "after the last round regardless". The bound is spent, so offer no further round |
| `merge-requested` | add `to-merge` **and remove the review state in the same call, and move the card to `To merge`** | [Merge the queue](#merge-the-queue). The item that woke this session is one entry to the queue, and the train resolves the whole set fresh |
| `dead` | nothing, because the item stays in the phase it is in | Report, and **never re-prompt** — below |
| `stalled` | nothing, for the same reason | Reset the context and re-prompt — below |
| `unreadable` | nothing, because a read that failed cannot say which phase the item is in | Report in one line: the tracker read is broken, and the item is unobserved until that read works again |

**The item's phase is what makes the response a lookup.** The seam reads that label to
decide which of the gated outcomes a tick can reach. So `implementation-complete` and
`verdict-approve` can never arrive for one item on the same minute. `unreadable` is the one
outcome no label gates: the read that failed is the read that carries the label.
The on-demand door (`review #N adversarially`) is unchanged, and it writes `phase:review`
itself.

**Five rows write no label, because they are not phase transitions.** ADR 0021 rejected a
`phase:fix` value, so a fix round stays inside `phase:review`. And `dead` and `stalled` say
something about the worker rather than about the phase. `unreadable` says something about
the tracker read, and a fact the tick never read cannot decide a label. `gates-unproven`
says the work is not finished after all, so the item stays where it is
([`docs/adr/0036-a-gate-run-is-work-product.md`](docs/adr/0036-a-gate-run-is-work-product.md)).
Nothing acknowledges those five wakes, so `--back-off` is what stops a repeat every minute.
**A repeat that carries the same round
number, or the same checklist position, is a wake you already answered.** Say so in
one line and do nothing. That stays a lookup, because the line carries both facts.

**Two rows carry a second act: they repoint the precheck at the live worker.** One **Item
automation** per item stands, and a transition moves the work to a different worker. So the
precheck follows it (op 13,
[`references/tools/_operations.md`](references/tools/_operations.md)). The repoint sits in
the same row as the phase-label write, so one transition is one step. It is not a repair the
maintainer has to remember:

- `implementation-complete` points the precheck at the reviewer's worktree, with the review
  harness's process pattern from
  [`references/harnesses/<harness>.md`](references/harnesses/claude.md). Step 1 of
  [Adversarial review](#adversarial-review-when-configs-reviewenabled) creates that
  worktree, so the same row already holds both values.
- `verdict-request-changes` points it back at the implementation worktree, with the
  implementation harness's pattern. The fix round runs there.

**The automation is repointed, and never restarted.** The schedule, its name and its run
history all stay, so step 8 of a **Close transaction** still removes one schedule under one
name. The edit fails closed: a rejected repoint leaves the old precheck running, and the
item keeps an observer. **A row that names no next worker repoints nothing.**
`verdict-approve` and `rounds-exhausted` end the phase axis. `dead`, `stalled`,
`gates-unproven` and `unreadable` say nothing about which worker is live.
`merge-requested` fires where no worker owns the item at all. Rationale:
[`docs/adr/0026-the-automation-follows-the-live-worker.md`](docs/adr/0026-the-automation-follows-the-live-worker.md).

**The repointed precheck is the same `wake` command, with two flags changed.** `--worktree`
and `--process` name the live worker. Every other flag keeps the value the spawn resolved
([Start the tick](#start-the-tick--one-item-automation-per-worker)), and `--handle` is one
of them. So a repoint never drops the wake target. **`--marker-dir` stays pointed at the
item's implementation worktree.** So an answered wake cannot fire again from a fresh
directory. The markers still die with the item, at step 8 of a **Close transaction**.

**A tool that records operation 13 as unsupported changes nothing else about the flow.**
`cmux` and `herdr` declare no automation surface, so no schedule exists and nothing needs a
repoint. Run the rest of the row unchanged. Then say in the report that the repoint is
unavailable on this tool ([Reporting to the user](#reporting-to-the-user)).

**`gates-unproven` — the record does not agree with the box, so a re-prompt is the
response.** The line names one of four causes: a missing file, a missing line, a non-zero exit or
a stale `head_sha`. Reset the worker's context
([Reset the worker's context before every re-prompt](#reset-the-workers-context-before-every-re-prompt)).
Then re-prompt with that cause and the command the line names, and ask for the gate run
rather than for a tick of the box. A stale `head_sha` usually means the worker committed
after the run, so the layer runs again at this commit. **The re-prompt is unconfirmed**,
exactly as it is for a stall. **This is not a stall**, so it writes no `Stall:` comment and it counts
toward no rung. **The record is not an enforcement mechanism**: nothing blocked the
worker's push, and the item stops before review instead
([`docs/adr/0036-a-gate-run-is-work-product.md`](docs/adr/0036-a-gate-run-is-work-product.md)).

**`dead` — a re-prompt cannot work, so nothing re-prompts.** No live agent process has its
working directory inside the worktree, so nothing listens. Report which phase the item is
in and where the worker got to. Then name the one human decision: tear the worker down and
re-spawn a rung up. **Teardown keeps its confirmation** ([Safety](#safety)), because a
tick cannot read intent in an uncommitted diff. This outcome needs no stall window, so it
arrives about a minute after the worker exits.

**`stalled` — a live process with stale work product, so a re-prompt is the response that
works.** Reset the worker's context
([Reset the worker's context before every re-prompt](#reset-the-workers-context-before-every-re-prompt)).
Then re-prompt with the unchecked boxes (op 4). **The re-prompt is unconfirmed** — it is
additive, and it costs the maintainer nothing to get wrong. **Post the stall as a comment on
the work item, in the same step.** That comment carries the literal `Stall:`, plus the
worker's model and effort. The stall count is the number of those comments that name the
current `(model, effort)` pair. That is the shape the **Review round** number already takes,
as the count of `Verdict:` comments. So neither count is held in a session's context
([`docs/adr/0023-the-stall-count-is-a-tracker-comment.md`](docs/adr/0023-the-stall-count-is-a-tracker-comment.md)).
At the **second** such comment the item was mis-routed. Tear the worker down and re-spawn a
rung up (`light` → `heavy`, or `heavy` at `max`), and say that is what happened. The pair
changes with the rung, so the new worker's count starts again with nothing to reset.
That teardown keeps its confirmation too. Do not diagnose *why* the worker stalled: that is
judgement on a live terminal and nothing here asks for it.

**No response above touches the automation.** It outlives the re-prompt, the fix round and
this session, so there is nothing to restart. The seam still holds no state that changes an
answer, which is what keeps a re-prompt free. Rationale:
[`docs/adr/0018-the-worker-watch-is-a-stateless-seam.md`](docs/adr/0018-the-worker-watch-is-a-stateless-seam.md)
and
[`docs/adr/0022-item-automation-replaces-the-blocking-watch.md`](docs/adr/0022-item-automation-replaces-the-blocking-watch.md).

### The proof phase

**An item enters `phase:e2e` only where the project recipe asks for a proof.** The gate is
the one resolved at spawn: a non-blank `run_recipe`, or an `evidence` bar that asks for UI
proof. Where neither holds, the phase is unreachable, and `implementation-complete` goes
straight to review or to human review. **This repo is that case.** Its `run_recipe` is
blank, and its `evidence` bar asks for a test run and resolved cross-references. So an item
here goes `phase:impl`, then `phase:review` or human review, and it **never wears
`phase:e2e`**
([`docs/adr/0021-phase-is-a-second-label-family.md`](docs/adr/0021-phase-is-a-second-label-family.md)).

Where the gate does hold:

1. **Write `phase:e2e`**, as the first act, like every other transition.
2. **Re-prompt the implementation worker in its own worktree.** Not a fresh worker: that
   worktree already holds the branch, the checklist and the per-item `ports`. So the reset
   and the self-contained re-prompt rules apply to it unchanged
   ([Reset the worker's context before every re-prompt](#reset-the-workers-context-before-every-re-prompt)).
3. **The proof drives the declared Browser surface**, `playwright-cli`. It boots the app
   per `run_recipe`, on those ports. A browser MCP the worker's session happens to expose is
   out of bounds, whichever one it is. That is the same scope edge every spawn prompt
   already carries.
   Reason, and why an MCP transcript is not durable evidence:
   [`docs/adr/0012-playwright-cli-is-the-only-browser-surface.md`](docs/adr/0012-playwright-cli-is-the-only-browser-surface.md).
4. **The finish is the same Completion signal**, a fully ticked checklist. The tick then
   reports `proof-complete`, and the row above carries the item on.

### Reset the worker's context before every re-prompt

**Every re-prompt resets the worker's context first** — a stall recovery and an
adversarial-review fix round alike. A worker that burned a long attempt carries that whole
attempt into its retry, and the retry is the turn that most needs the headroom.

**The command is harness-shaped.** On `claude` it is `/clear`. Every other harness takes
whatever its own [`references/harnesses/<harness>.md`](references/harnesses/claude.md)
names. Where a harness offers no reset command, **the step is skipped and the report says
so**. Read the command from the reference and never from memory. This is the same
plain-English split every other part of the contract takes: never send a slash command to
a harness that cannot parse one.

**The re-prompt is then self-contained.** A cleared worker has forgotten its spawn prompt.
So the re-prompt re-carries four things. The routed skill, as a literal invocation. The
worker's own harness, model, effort and role. Then the acceptance criteria and the scope
edges. **That is the same list a fix prompt already carries** (step 3 of
[Adversarial review](#adversarial-review-when-configs-reviewenabled)) — one contract
reached from two directions, not two rules. A re-prompt is a worker prompt, so it goes
through `prompt-improver` as an agentic-pipeline prompt like any other.

**The checklist file is what makes the reset safe.** Progress lives on disk, so a reset
loses the worker's reasoning and never its position. Rationale:
[`docs/adr/0018-the-worker-watch-is-a-stateless-seam.md`](docs/adr/0018-the-worker-watch-is-a-stateless-seam.md).

## Adversarial review (when config's `review.enabled`)

When a work item reaches `phase:review` and review is enabled. **The tick is the actor that
starts it** — its `implementation-complete` outcome, or `proof-complete` where a proof phase
ran ([On the wake](#on-the-wake--one-response-per-outcome)). The label this session writes
in answer to that wake is what puts the item in this flow.

**The round bound is the resolved `review.rounds`, and one value serves both halves.** It
bounds the loop below, and it is the same number written into the tick's `--rounds` at spawn
([Start the tick](#start-the-tick--one-item-automation-per-worker)). So the seam and the
loop cannot disagree about which round is the last one. And `rounds-exhausted` is the
outcome that reports the bound spent.

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
   findings never arrive, and nothing reports an error. **Then repoint the item's Item
   automation at this worktree** (op 13), and create no second one. One schedule per
   item stands, and its precheck follows the live worker
   ([On the wake](#on-the-wake--one-response-per-outcome)). The precheck is the same `wake`
   command. `--worktree` and `--process` then name this worktree and the review harness.
   **The automation is repointed, and never restarted**, so the schedule and its run history
   both stay. The item's `phase:review` label is what makes the tick read a verdict
   rather than a checklist. A reviewer needs no flag of its own.
2. **Prompt it to review** the diff/MR and the `make deep` report against the work
   item's acceptance criteria — drafted, then run through `prompt-improver` for the
   review model's profile, same as a spawn prompt. Say it's a **code-review prompt**:
   `prompt-improver` has a specific rule for these — **ask for coverage, filter
   downstream** — and it's the one that matters most here. Never "only
   high-severity", "be conservative", or "don't nitpick": every model here obeys
   that literally and silently drops real bugs. The orchestrator ranks when it
   reads the verdict. The reviewer posts a verdict on the work item: **approve**
   or **request-changes + findings**.

   **The verdict carries a `Verdict:` line, and the prompt asks for it verbatim.** Its
   value is `approve` or `request-changes`. That literal is what the tick reads in
   `phase:review`, so a review whose comment omits it never wakes this session. Its count is
   also the round number, so an omitted line loses the count with the wake. It is quoted
   in the **Completion signal** entry of [`CONTEXT.md`](CONTEXT.md), so a writing pass
   leaves it byte-identical.

   **Four substitutions this prompt needs, learned by running the flow.** Each closes a
   way a reviewer produces a plausible verdict that is not a review:

   - **Run the suites and the gate commands yourself, rather than trusting the commit
     messages.** A worker's own claim that a suite or a **Gate** is green is the claim
     under review, not evidence for it.
   - **Give every acceptance-criteria checkbox its own verdict.** One verdict per box,
     named. A summary over a group of boxes hides the one box that failed.
   - **Do not spawn sub-agents.** The reviewer is already the second opinion. A
     sub-agent's findings arrive unattributed and cost a round. This rule is the one
     exception to the **Delegation cap**:
     [`docs/adr/0035-workers-delegate-to-sub-agents-under-a-cap.md`](docs/adr/0035-workers-delegate-to-sub-agents-under-a-cap.md).
   - **Report per axis, with a confidence and a severity on each finding.** The axes
     stay `/code-review`'s two. This adds only the two per-finding fields, which is
     what lets this session rank without re-reading the diff.

   These four are prompt *content*, so they go into the draft and through
   `prompt-improver` with the rest — they restate no rule of the two-axis contract.

   **The layer 4 report is input next to the diff.** The output of `make deep` is the
   Evidence block of the review note, so the reviewer reads gate output instead of a
   worker's claim ([`references/quality-gates.md`](references/quality-gates.md),
   [`docs/adr/0032-quality-gates-are-a-layered-contract.md`](docs/adr/0032-quality-gates-are-a-layered-contract.md)).
   Three findings are each grounds for `request-changes`. They are a mutant that the
   suite left alive, a SAST finding at high or critical severity, and a fired **Halt
   condition**. The first two break a hard threshold in the layer 4 rows of the gate
   matrix. The third stops an infra plan and not code, so it is not a **Gate**. Its rows
   land with the Terraform column ([`CONTEXT.md`](CONTEXT.md)). Each one is one finding
   in the verdict. The fix loop in step 3 then answers it as it answers every other
   finding.

   **A repo with a blank `deep` command has no report to read.** That Layer drops its
   checklist box before this session sends the checklist
   ([The prompt: checklist + completion contract](#the-prompt-checklist--completion-contract)).
   The reviewer then reads the diff, and reviews it as it does today.
3. **On request-changes:** reset the original impl worker's context
   ([Reset the worker's context before every re-prompt](#reset-the-workers-context-before-every-re-prompt)).
   Then re-prompt **that same worker** with the findings to fix, and re-review. **Repoint the
   precheck back at the implementation worktree** (op 13), with the implementation harness's
   process pattern. The fix round then watches the worker that is fixing
   ([On the wake](#on-the-wake--one-response-per-outcome)). The automation already runs and
   outlives the round, so it is repointed and never restarted. Loop,
   bounded at the resolved `review.rounds` (default 3), and the round the tick's line names
   is the round you are on.
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
     goes to a worker whose context this session has cleared**, so it re-states the
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
   the item to **human review**. **That transition is one call: it removes the
   `phase:review` label and it writes `to-review`.** The card moves to `In review` with it
   ([Board status](#board-status)). **This session writes all three. The worker wrote
   none of them**, because its last act was the review note. The item holds
   `in-progress` and `phase:review` for the whole loop, because a worker owns it and a
   fix round is inside the phase. So both labels change only here, at the one moment the
   phase axis concludes
   ([`docs/adr/0025-the-session-writes-the-review-state.md`](docs/adr/0025-the-session-writes-the-review-state.md)).
   Merge is always a human step.

On demand: **"review #N adversarially"** runs this flow directly even if review is
off in config.

## Close a task

When the user says **merge and close N / close N / close task #N / it's done / wrap up
<slug>**: run one **Close transaction**. It is eight steps in one fixed order, defined in
[`CONTEXT.md`](CONTEXT.md). The split is by judgement. Steps 1 to 3 need it, so they
are the prose below. Steps 4 to 8 need none, so `scripts/close_item.py` owns them.
Rationale:
[`docs/adr/0015-close-is-a-deterministic-transaction.md`](docs/adr/0015-close-is-a-deterministic-transaction.md).

**The maintainer's words are the gate.** Read the instruction against this table
before you touch anything:

| Instruction | Teardown |
|---|---|
| "task done, merge and close" | yes |
| "merge and close 20", "merge 20 and close it" | yes |
| "close 20" | yes |
| "wrap up 20" | yes |
| the `to-merge` label, or a card in the `To merge` column | yes |
| "flip 20 to review", "advance 20" | no |
| ambiguous, or not said | ask first |

The explicit ask **is** the confirmation. So never ask again for a merge the
maintainer requested in the same turn. A **no** row is an advance and not a close:
swap the label to the review state, move the card to `In review`
([Board status](#board-status)), and stop there. On the **ask first** row, ask in one
line and wait.

**The `to-merge` row is an ask too, recorded on the item instead of typed.** A maintainer
who writes that label, or drags that card, decided for that one item after they read it.
So a close inside a **Merge train** carries the same authority as a typed one
([Merge the queue](#merge-the-queue),
[`docs/adr/0037-the-merge-queue-is-an-ordered-train.md`](docs/adr/0037-the-merge-queue-is-an-ordered-train.md)).

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
`python3 <plugin root>/scripts/close_item.py --help` is the argument surface, and the
module docstring is the step table. `<plugin root>` is the value the preflight resolved
([Resolve the plugin root, and prove the seam runs](#resolve-the-plugin-root-and-prove-the-seam-runs)).
The path names the seam and it leaves the working directory alone, which matters here:
`--repo` defaults to the working directory, so a form that moves there first would point
the merge at the plugin.

```bash
python3 <plugin root>/scripts/close_item.py --issue <N> --pr <PR> \
  --repo <config's repo> --worktree <the path from op 8> \
  --remove-label <the review label> \
  --tracker-cli <gh or glab> --tracker-host <host> --tracker-repo <owner>/<name> \
  --project-number <n> --project-owner <owner> --project-id <id> \
  --status-field-id <id> --done-option-id <the `Done` option id> \
  --teardown-command '<op 10, with the ids filled in>'
```

Four things the seam never learns, so you pass them in:

- **The teardown command, as a string — and it removes the automation as well as the
  worktree.** Read both halves from
  [`references/tools/<tool>.md`](references/tools/_operations.md), op 12 then op 10, and
  substitute the ids. Join them with `&&`, in that order, and pass the whole line to
  `--teardown-command`. So the seam holds no `orca` command, and a new tool stays a
  markdown change. **The automation goes first**, so nothing ticks against a worktree that
  is half removed. Use `&&` and not `;`, so a failed op 12 leaves both in place. The plan
  then reports the failure rather than a leaked schedule. A session that no longer holds the
  automation id reads it back from the name, `orchestrator-item-<N>` — that is what op 12
  is written to do. The checklist file dies with the worktree, so nothing cleans it up.
  Where the tool records operations 11 and 12 as unsupported, no automation was created and
  the string is op 10 alone. Rationale:
  [`docs/adr/0022-item-automation-replaces-the-blocking-watch.md`](docs/adr/0022-item-automation-replaces-the-blocking-watch.md).
  **The eight steps and their order are unchanged**, and `scripts/close_item.py` gains no
  code. The whole change is the value of one argument it already takes.
- **The board coordinates, as arguments.** Read the five values from
  `docs/agents/issue-tracker.md`'s
  [`## Project board`](../docs/agents/issue-tracker.md#project-board) section. Where
  that section is absent, omit them. The card write is then a no-op
  ([Board status](#board-status)). **GitLab has no board of this kind**, so a project
  there passes none of the five and step 7 writes no card.
- **Which tracker, as three arguments.** Read `--tracker-cli`, `--tracker-host` and
  `--tracker-repo` from [`../docs/agents/issue-tracker.md`](../docs/agents/issue-tracker.md),
  the same way the tick reads its own two
  ([On the wake](#on-the-wake--one-response-per-outcome)). `gh` on github.com is the
  default, so this repo passes none of the three. A self-hosted GitLab needs all three,
  and the seam then runs there with no wrapper script. `--tracker-repo` is the tracker
  project and `--repo` is the checkout on disk, so the two never share an argument. Every
  command comes from the **Tracker adapter**
  ([`CONTEXT.md`](CONTEXT.md), **Tracker adapter**), so never write a tracker command
  here or in a prompt.
- **Whether to mutate. The default invocation is a dry run.** It resolves every
  precondition, prints the plan as JSON, and changes nothing. Read that plan. Then
  re-run it with `--execute`. Teardown needs `--execute --teardown` together, and
  only where the table above says yes.

**A refused transaction leaves the automation in place.** Teardown is step 8, so a refusal
at any earlier step never reaches the string above. The item is then still observed, and the
next tick still wakes this session. That is deliberate: an item that did not close is
exactly the one that must keep its observer.

**Parent-close stays yours.** The seam closes one item. Where the tracker conventions
define a parent close, apply it after the seam exits clean. That is the last child
closed → close the parent, and the parent's card → `Done`. **The read is *Every child of
a parent work item, closed children included***
([`references/tracker-reads.md`](references/tracker-reads.md#every-child-of-a-parent-work-item-closed-children-included)).
An open-item list cannot answer this step, because the child that closed last is not in
it. Then report per [Reporting to the user](#reporting-to-the-user).

### The layer 5 story gate

**Run `/improve-codebase-architecture` when a user story finishes.** The moment is the
close of its last child, in the same turn that bumps the version in
`.claude-plugin/plugin.json`. The bump rule itself is a project rule, in config at
`docs/agents/orchestrator.md`, and this step performs no bump. The lane is `inline`, so
this session invokes the skill here, in the main checkout, on the default branch
([Resolve the verb before you act](#resolve-the-verb-before-you-act)).

Layers 1 to 4 each read one work item, inside one worker worktree. This layer is the one
that reads what ten green items left behind. The five layers are in
[`references/quality-gates.md`](references/quality-gates.md), and the word is the
**Layer** entry in [`CONTEXT.md`](CONTEXT.md).

Hand the skill the direction to look in, where the maintainer named one. The Notes column
of its row in [`references/skill-routing.md`](references/skill-routing.md) holds the rest.
**The skill owns its own report.** Never restate one of its headings here, in a prompt or
in a report.

**Triage every candidate the report holds. This session does it, in prose:**

- **`Strong`** becomes a work item, through `/to-tickets`.
- **`Worth exploring`** goes to the backlog, with its card attached
  ([Board status](#board-status)).
- **`Speculative`** is dropped, with a one-line reason in the report to the user.

The skill ends by asking which candidate to explore. This triage is the answer, so no
grilling loop runs here.

**The threshold is 0 untriaged `Strong` candidates, and not 0 findings.** This session
checks it, and `scripts/close_item.py` does not. That seam owns the judgement-free steps
of a **Close transaction** alone, and triage is judgement
([Steps 4 to 8](#steps-4-to-8--close_item-owns-the-order)).

**Layer 5 stops nothing.** It holds no exit code, so it fails no push and no merge. Depth
is a judgement, and a hard gate here stalls every story on an opinion. A candidate still
untriaged is work to report, and never a close this session refuses. Rationale, the
threshold and the accepted risk:
[`docs/adr/0033-the-story-gate-is-advisory.md`](docs/adr/0033-the-story-gate-is-advisory.md).

## Merge the queue

This flow runs at two moments. A tick that reports `merge-requested`
([On the wake](#on-the-wake--one-response-per-outcome)) is the first. A maintainer who asks
for the queue after a ["What next?"](#what-next--pick-the-next-work) read is the second. It
runs one **Merge train**: one ordered run over the **Merge queue**, both defined in
[`CONTEXT.md`](CONTEXT.md).

**The ordering rule and the park rule live in
[`references/merge-train.md`](references/merge-train.md).** Read them there at the moment
you need them, and never from memory. This section restates neither one. Rationale:
[`docs/adr/0037-the-merge-queue-is-an-ordered-train.md`](docs/adr/0037-the-merge-queue-is-an-ordered-train.md).

1. **Resolve the Merge queue fresh.** Every open item that carries `to-merge` is in it. So
   is every open item whose card sits in the board's `To merge` column. **Promote each
   dragged card to the label**, then read labels alone from there. That direction is board
   to label, once, for that one column
   ([`docs/adr/0038-the-to-merge-column-is-intent.md`](docs/adr/0038-the-to-merge-column-is-intent.md)).
   The column read is a board read, so a repo with no board keeps the label as its only
   entry ([Board status](#board-status)).
2. **Ask the seam for the order.** Rank nothing yourself. `scripts/merge_train.py` plans a
   train, and it merges nothing.

   ```bash
   python3 <plugin root>/scripts/merge_train.py --repo <config's repo> \
     --default-branch <the default branch> \
     --item <N>:<the item's branch> --item <N>:<the item's branch>
   ```

   One `--item` per queued item, and the item's branch is its slug. `<plugin root>` is the
   value the preflight resolved
   ([Resolve the plugin root, and prove the seam runs](#resolve-the-plugin-root-and-prove-the-seam-runs)).
   The plan is one JSON object on stdout, with an `order` and a `parked` list. Read it.
   `python3 <plugin root>/scripts/merge_train.py --help` is the argument surface, and the
   module docstring holds the JSON keys and one row per exit code. **Never restate one of
   them here or in a report.**
3. **Report the plan before the first merge.** The order and the parked list, capped at 5
   rows like every other report ([Reporting to the user](#reporting-to-the-user)). That
   report is what lets the maintainer stop a train they did not expect.
4. **Park what the plan parked.**
   [`references/merge-train.md`](references/merge-train.md) holds the park rule, and this
   session performs it. **Move the card with the label**, to `In review`
   ([Board status](#board-status)). The seam writes no label and comments nowhere, so this
   session makes every tracker write a park needs.
5. **Run one full Close transaction per item, in the printed order.** Steps 1 to 3 in
   prose, and `resolving-merge-conflicts` where step 1 conflicts. Then steps 4 to 8 through
   `scripts/close_item.py`, with `--execute --teardown`
   ([Close a task](#close-a-task)). **No step of the transaction changes, and their order
   does not change.** The `to-merge` label is the standing authorisation, so no close
   inside a train asks a second time ([Safety](#safety)).
6. **A late conflict parks the item, and the train continues.** Step 1 of the transaction
   is where it appears, because an earlier merge of this same train moved the default
   branch. Park it per step 4, then continue with the next item.
7. **Apply the layer 5 story gate per item, and never once per train.** Where a merge
   closed the last child of a user story, run
   [The layer 5 story gate](#the-layer-5-story-gate) for that story. One train can close
   two stories, so the check belongs to each item.

## Reporting to the user

An orchestrator session runs long and the user reads it between other work. They
cannot hold "we're on round 2 of 3 for #38" across turns, so every report restates
it. Shape output for acting on, not for completeness:

- **Lead with state, not narration.** First line is the board: what changed and
  what's running.
  `#38 38-b5-contacts spawned · /implement · heavy · opus-5 · xhigh. 2 workers live.`
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
- **Restate position every turn, and carry the phase with it.** A worker's progress is
  `phase:impl · checklist 4/7`, a review loop is `phase:review · round 2 of 3`. Every
  report of an owned item says which phase it is in, because that is the fact a fresh
  session cannot infer. Read the phase off the item's labels, the position off the
  checklist file, and the round number off the count of `Verdict:` comments. Do not ask the
  user to remember any of the three.
- **A wake report names the outcome and the transition that ran.** The outcome is the
  tick's own word: `implementation-complete`, `proof-complete`, `gates-unproven`,
  `verdict-approve`, `verdict-request-changes`, `rounds-exhausted`, `merge-requested`,
  `dead`, `stalled` or `unreadable`. Then
  the phase label you wrote, then what you did. `#38 implementation-complete · phase:impl →
  phase:review. Reviewer spawned, gpt-5.6-terra @ high.` **Where the wake ended the phase
  axis, name the label pair you wrote.** That one call is the hand-off to a human:
  `#38 verdict-approve · phase:review removed · to-review · card In review.`
- **Both counts come from the tracker, so restate both.**
  [On the wake](#on-the-wake--one-response-per-outcome) says how to read each one.
  `#38 stalled at phase:impl ·
  checklist 4/7 · stall 1 of 2. Context reset, re-prompted with the unchecked boxes.` At
  `stall 2 of 2`, and on `dead`, the next step is a teardown — name it as the pending
  human decision.
- **Name the live wake mode on the spawn line.** The tick delivers to the handle, the title
  or a comment on the work item, and the first that succeeds ends the delivery
  ([Start the tick](#start-the-tick--one-item-automation-per-worker)). Say which one this
  spawn resolved: `#38 tick: wake by handle` / `wake by title` / `wake by comment`. A
  comment-only wake is then a fact the user reads at spawn, rather than a silence they find
  many runs later.
- **Say when the tick is unavailable.** A tool that records operations 11 and 12 as
  unsupported gets no automation, so nothing wakes this session for that item. Say so on
  the spawn line, once, and point at the four monitor bullets
  ([Monitor workers](#monitor-workers)).
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
- **A train report names the order it ran**, what merged, what parked and why, and it ends
  with the one action left. That is the close-report shape, once per train instead of once
  per item ([Merge the queue](#merge-the-queue)). **A parked item is that action**, and it
  carries the conflicting paths. `#152 #153 merged, in that order. #151 parked:
  orchestrator/SKILL.md conflicts. Resolve it in 151-merge-train, then say "close 151".`
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
- **The `to-merge` label is the standing authorisation, so a Merge train asks no second
  time.** The maintainer writes it per item, on an item they read, so it authorises one
  transaction and never a whole session. Each close inside a train then runs all eight
  steps, teardown included ([Merge the queue](#merge-the-queue),
  [`docs/adr/0037-the-merge-queue-is-an-ordered-train.md`](docs/adr/0037-the-merge-queue-is-an-ordered-train.md)).
- **A second stall is one of the ambiguous cases, so it asks. So is a `dead` worker.** The
  maintainer said nothing about a teardown in either case, and a tick cannot read intent in
  an uncommitted diff. The re-prompt on the first stall stays unconfirmed, because it
  destroys nothing.
- Keep the main checkout (config's `repo`) on the default branch — all
  tracker/git-state ops run there. This orchestrator's own worktree branch is
  separate and irrelevant.
- Never advance an item to done before its PR/MR is actually merged.
