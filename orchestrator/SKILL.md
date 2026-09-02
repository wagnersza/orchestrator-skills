---
name: orchestrator
description: Orchestrate agent worker sessions across any workspace tool (orca/cmux/herdr), harness (claude/codex/pi/copilot/cursor), and frontier model. Pick the next ready work item, read whether it is a user story or a leaf task, spawn a worker in its own worktree on the right model and effort for the job, prompt/monitor it via a file-based checklist, run optional cross-vendor adversarial review, then report finished work for the maintainer to merge. Use this skill for every work-item action, and never wait for the user to type /orchestrator. A work verb plus a work-item number N is enough, with or without a "#". Trigger on "work on N", "work on #N", "implement N", "build N", "start N", "do N", "implement X", "spawn a worker", "start a session for X", "prompt worker Y", "what next", "what should I run/work on", "what's ready", "what are the workers doing", "list workers", "review N adversarially", "merge and close N", "merge N and close it", "close N", "close task #N", "it's done", "wrap up N", "orchestrate". A bare number after a work verb always means a tracked work item, so route it here rather than reading it as a file or a line number.
---

# Orchestrator

This session is the **orchestrator**. It coordinates **worker** sessions. A
worker is a `(Tool, Harness, Model)` triple running against one work item in its
own worktree/terminal. Never do implementation work here — spawn a worker and
prompt it. **There is no exception.** The one that existed was a conflict resolution
inside a [close](#close-a-task), and the maintainer merges on the tracker now
([`docs/adr/0057-the-merge-is-the-second-act.md`](docs/adr/0057-the-merge-is-the-second-act.md)).

The vocabulary (Tool, Harness, Model, Effort, Role, Vendor, Worker, Yolo mode,
Adversarial review, Ready queue, Checklist, Project recipe, Position, Item automation) is
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
**project board** coordinates, and there are two of them — see
[Board status](#board-status).

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
([On the tick](#on-the-tick--what-it-wrote-and-what-is-left-for-you)). Rationale:
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

Check the **`resolving-merge-conflicts` skill** in the same pass too, because the
maintainer can ask for it at any time. Run the `resolving-merge-conflicts` line
of that same check block — the four-path `ls`. Any of its four install shapes
**satisfies the check**, for the same reason the other two get theirs: the plugin
cache, the marketplace clone, or a standalone clone global or project. The skill ships
inside `mattpocock-skills`, so there is nothing separate to install. **No flow reaches
it by itself**, because the merge it used to serve is the maintainer's own act now
([`docs/adr/0057-the-merge-is-the-second-act.md`](docs/adr/0057-the-merge-is-the-second-act.md)).

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

**An inline skill that files a work item appends its `## Touches` block**, beside
the `## Blocked by` and `## Parent` edges the item already carries. `/to-spec`,
`/to-tickets` and `/triage` run in this lane, so each one writes the block with the
body it files. No external template is edited, and none is forked
([ADR 0028](docs/adr/0028-drop-the-fork-and-pin-dial.md),
[ADR 0046](docs/adr/0046-parallel-spawn-is-gated-on-a-declared-touch-set.md)).

**One dispatch row per item-writing phrase family.** Each row is a pointer to the
skill that answers it, and it restates none of that skill's rules. Read
[`references/skill-routing.md`](references/skill-routing.md) for the full alias list.

| Phrase family | Skill |
|---|---|
| "create a ticket", "file a ticket", "open an issue" | `/to-tickets` |
| "create a spec", "write a spec" | `/to-spec` |
| a request to sort or label existing items | `/triage` |

**An item-writing flow writes the work item, its `## Touches` block and its type
label, and starts nothing.** Act one — the `ready-for-agent` label and the board
drag into the start column — stays the maintainer's own
([Board status](#board-status)).

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
user to confirm a route. **A close needs no verb at all now**, so the first three
phrases answer a question rather than start a transaction
([`docs/adr/0057-the-merge-is-the-second-act.md`](docs/adr/0057-the-merge-is-the-second-act.md)).

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

Where the tracker config has a **`## Project board`** section, every work item is also a
card. **The board is an input, and nothing writes it.** One question is asked of it: is
this item's card in the start column. That is the second fact of a
[ready queue](#what-next--pick-the-next-work) entry, beside the `ready-for-agent` label.
The two coordinates, the name of that column and the one read live in that section of
`docs/agents/issue-tracker.md`; read them from there, never from memory. Rationale:
[`docs/adr/0054-the-board-is-an-input-not-a-mirror.md`](docs/adr/0054-the-board-is-an-input-not-a-mirror.md)
and
[`docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md`](docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md).

**A seam answers the two facts for one item**, so no session compares a column name by
hand. It writes nothing and moves no card, and exit 0 means both facts hold:

```bash
python3 <plugin root>/scripts/worker_state.py start --item <N> \
  --repo <owner>/<name> \
  --tracker-cli <gh or glab> --tracker-host <host> \
  --board-project <the project number from the tracker file> \
  --board-owner <the owner from the tracker file> \
  --start-column '<the column name from the tracker file>'
```

Where the tracker names no board, pass no board flag. The label then decides on its own,
and that absence is never an error. The argument surface is
`python3 <plugin root>/scripts/worker_state.py start --help`.

Three rules:

- **Write no card, anywhere.** No flow below moves one, and no seam builds a card write.
  The three coordinates above reach one read and nothing else. A card write was a
  projection of the label, and it had seven writers that
  each could forget it. **A closed item reaches `Done` through the board's own built-in
  item closed to Done workflow**, which the maintainer enables in the project settings.
- **A drag is intent, in every column.** Nothing overwrites a card, so a card stays where
  the maintainer put it. A take-back is the maintainer removing `ready-for-agent`, or
  writing `needs-human` plus a comment that says why.
- **A missing `## Project board` section means the board read asks nothing.** A repo with
  no board is a supported configuration, and the label alone is the whole gate. Never fail
  a spawn or a close over the board.

## Right model for the job

Never hardcode a model. Config names a `(model, effort)` pair per **role**;
classify the work item, then resolve the pair. The role table, the effort ladder,
and the routing rule live in [`references/models.md`](references/models.md) —
read it before the first spawn of a session.

1. **Classify the item.** Default **`heavy`**. Choose `light` only when *all* hold:
   one file/component touched, no schema change or `db_gate`, no new dependency,
   and acceptance criteria fully enumerated on the work item. Ambiguous → `heavy`.
   A fix round from adversarial review raises the effort by one rung (`heavy` at `xhigh`,
   or `max` if `xhigh` already failed). A reviewer's verdict is the fact behind that step.
   **A stalled worker raises nothing** — it gets one re-prompt and then a human
   ([`docs/adr/0058-one-re-prompt-then-a-human.md`](docs/adr/0058-one-re-prompt-then-a-human.md)).
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

A work item is **ready** when it holds **two facts** and every item in its `## Blocked by`
list is closed (closed = satisfied; only still-open deps block):

1. It carries the `ready-for-agent` label (from `issue-tracker.md`).
2. Its board card sits in the start column, whose name that same file gives.

**Both facts are necessary, and one fact on its own is not ready.** A card in the start
column with no label is not ready, and a labelled item whose card sits in `Ready` is not
ready either. So `Ready` is the maintainer's own lane, and no agent enters it. Where the
tracker names no board, the label alone is the whole gate
([Board status](#board-status)). Skip items already `in-progress` or in the review state —
a worker owns them.

Read the tracker CLI from `issue-tracker.md`, list open items, and for each read
its `## Blocked by` / `## Parent` edges (the `to-tickets` template). A child that
itself carries the `user-story` label is a **nested spec** — descend into its
children, never spawn it directly. Present **all ready items first** (they can
start in parallel), then fill to at least 5 with the soonest-unblocked blocked
items (fewest open deps first), noting what each waits on. Offer to spawn a worker
for whichever the user picks.

**One board read answers the second fact for every item.** It is the one call
[Board status](#board-status) names, and it returns every card, so this pass makes it once
and adds no second read. **This read writes nothing to the board.** There is no reconcile
pass and no sync command, because the board is an input.

**Report every item that holds one fact and not the other, capped at 5 rows.** A forgotten
drag otherwise reads as an empty queue, and nothing repairs the disagreement on its own.
Name which fact is missing per item, because that is what the maintainer acts on: the
label, or the drag. An item here is not an error and needs no comment — a parked story
reads exactly the same way
([`docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md`](docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md)).

**Report every item at `to-review` beside the ready queue.** This pass already holds every
open item's labels, so that list costs no second read. **No label records a merge ask.** The
maintainer reads the pull request and types the ask, so this session offers the train and
never infers one
([`docs/adr/0053-one-work-state-label-and-a-computed-position.md`](docs/adr/0053-one-work-state-label-and-a-computed-position.md)).
Report the list as its own capped list, under the ready queue. Then offer the train
([Merge the queue](#merge-the-queue)).

**This read is the whole fallback where the tool supports no automation surface.** `cmux`
and `herdr` create no schedule, so no tick fires and no transition lands
([Start the tick](#start-the-tick--one-item-automation-per-worker)). A maintainer who asks
what next still sees the list, and can still ask for the train.

### The queue tick — how work starts, and it is not you

**A schedule starts the work, and no session starts an item by hand.** One repo-wide
schedule named `orchestrator-queue` ticks once a minute
([`orchestrator-setup`](../orchestrator-setup/SKILL.md) writes it at setup time). Its
precheck is the whole tick, and it is the `queue` subcommand of the **Worker watch** seam:

```bash
python3 <plugin root>/scripts/worker_state.py queue --help
```

**There is nothing for you to run here.** The exit codes, the order of the reads and the
argument surface are one home, that module docstring and its `--help`. **Never restate
them here or in a report.** Read them when you need them.

One tick reads every open work item, and it applies the two facts of the ready queue read
to each one. It descends through any `user-story` parent to that parent's unblocked
children. It counts the live **Story run**s and the live **Worker**s against the two roofs.
Then it compares the declared **Touch set**s against every live worker, and starts **at
most one** item. The spawn goes through `scripts/spawn_item.py`, so the tick composes no
launch command.

- **One item per tick, always.** A queue holding ten startable items starts one. That is a
  hard rule and never a dial, because a tick that starts three fills a disk while nobody
  watches.
- **A `user-story` parent is never spawned for the work itself.** The tick descends to its
  children, and **it writes no `ready-for-agent` label on any of them**. So the rule that
  only a human writes that label survives word for word.
- **The two roofs are `max_stories` and `max_workers` in the Config**, and the lower one
  wins. The tick starts nothing where either one is full.
- **An overlap delays an item and cancels nothing.** The next tick with a free slot and no
  live overlap starts it. `parallel_check: off` compares nothing.

**`work on N` stays the maintainer's own override, and it is a convenience rather than the
mechanism** (["Work a #N"](#work-a-n--batch-spawn-its-unblocked-children),
[Spawn a worker](#spawn-a-worker-implement-x)). It writes the label and spawns at once,
because a person typed the number. **Offer it, and never take it on your own.** A session
that spawns an item nobody asked for is the thing this schedule replaces. Rationale:
[`docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md`](docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md)
and
[`docs/adr/0046-parallel-spawn-is-gated-on-a-declared-touch-set.md`](docs/adr/0046-parallel-spawn-is-gated-on-a-declared-touch-set.md).

**Removing the schedule is the rollback.** With no `orchestrator-queue` schedule the loop
falls back to `work on N`, and nothing else changes. A tool with no automation surface is
already in that state.

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
   reuse it: get its worker handle (op 9) and just send the prompt. Only continue if
   nothing matches.
2. **Run the seam.** `scripts/spawn_item.py` runs the rest of this flow, in seven
   ordered steps: the worktree, the terminal, the rendered prompt, the readiness
   gate, the `in-progress` label, the follow-along panel, and the item schedule. The
   order, the exit codes and the argument surface are one home, the module docstring —
   `python3 <plugin root>/scripts/spawn_item.py --help`. **Never restate that order
   here or in a report.**

   The seam reads `docs/agents/orchestrator.md` itself for the tool, the harness, the
   yolo flag and the model pair. So this session composes no `$CMD` of its own, and it
   resolves no launch command from a table. `--role` is the one judgement call this
   session still makes: classify the item and resolve its role before the run (see
   [Right model for the job](#right-model-for-the-job)).

   **Preflight the routed skill before the run**, the same way this section always
   has. Where the verb resolved to a `worker` row
   ([Resolve the verb before you act](#resolve-the-verb-before-you-act)), confirm the
   skill is reachable by *this* harness:
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

   **The plugin root is a requirement of this run too.** Where this session has not
   resolved it yet, run the preflight now
   ([Resolve the plugin root, and prove the seam runs](#resolve-the-plugin-root-and-prove-the-seam-runs)).
   A failed check aborts the spawn as well, because the seam's readiness gate needs
   it and its last step writes it into a schedule.

   Read [Gate readiness before the first prompt](#gate-readiness-before-the-first-prompt)
   for why the readiness gate is a process check and never a screen check. Read
   [The prompt: checklist + completion contract](#the-prompt-checklist--completion-contract)
   for how this session seeds the seam's checklist and prompt inputs. Read
   [Start the tick](#start-the-tick--one-item-automation-per-worker) for the
   `--schedule-command` this session passes in, and what it does after the seam
   returns.

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
  **The proof box drops on the same rule**, and `run_recipe` is the field it reads.
  So "every box ticked" already covers the browser proof. **This repo is that case**: its
  `run_recipe` is blank, so no item here grows a proof box.
  **The writing-pass box is unconditional** — it depends on no recipe field,
  so it ships on every item, including a pure-code one.
- That seeded file is the **Checklist** input of the template below. The boxes reach the
  worker with the render, so nothing about them is worded twice.

**The prompt is a render, and not a draft.**
[`references/prompt.template.md`](references/prompt.template.md) is the one worker
prompt, and this session fills its four inputs: the **Work item**, the **Checklist**
above, the gate commands of the `gates:` block, and the routed skill. Nothing else
reaches a worker. **Restate no wording of that body here, and compose none of your
own.** A prompt this session writes by hand can drop a field, and the template is what
closes that failure. Its own header holds the two render rules, the value shape of the
routed skill, and the harness split. Read them there.

**The acceptance criteria and the Touch set are already in the item body.** So the
render carries both with the body, and this session assembles neither. That is what
keeps the input count at four.

**`prompt-improver` reviewed that body once, at build time**, as an
**Agentic-pipeline prompt**. So a spawn runs no pass of its own, and this session names
no model to it. An edit to the body needs the review again, and the item that carries
the edit records it. Prompt quality stays that skill's job and never this one's
([`references/requirements.md`](references/requirements.md),
[`docs/adr/0006-delegate-prompting-to-prompt-improver.md`](docs/adr/0006-delegate-prompting-to-prompt-improver.md)).

**Which skill the fourth input names comes from the routing table**
([Resolve the verb before you act](#resolve-the-verb-before-you-act)). A verb resolves
one row, and a type label resolves the same skills through the type-label section of
[`references/skill-routing.md`](references/skill-routing.md). The skill then runs
**inside** the completion contract and never in place of it, so
`.orchestrator/checklist-<item>.md` stays the file this session reads for progress.

Each part of that contract has a home, and the template body is where it reaches the
worker:

| The part | Definition | Rationale |
|---|---|---|
| the **Delegation cap** | [`CONTEXT.md`](CONTEXT.md) | [`docs/adr/0035-workers-delegate-to-sub-agents-under-a-cap.md`](docs/adr/0035-workers-delegate-to-sub-agents-under-a-cap.md) |
| the **Browser surface** edge | [`CONTEXT.md`](CONTEXT.md) | [`docs/adr/0012-playwright-cli-is-the-only-browser-surface.md`](docs/adr/0012-playwright-cli-is-the-only-browser-surface.md) |
| the **Commit slice** rule | [`CONTEXT.md`](CONTEXT.md) | [`docs/adr/0013-workers-commit-in-contextualised-slices.md`](docs/adr/0013-workers-commit-in-contextualised-slices.md) |
| the writing pass, in pragmatic mode | the **simple-english** and **Prose deliverable** entries of [`CONTEXT.md`](CONTEXT.md) | [`docs/adr/0011-delegate-technical-writing-to-simple-english.md`](docs/adr/0011-delegate-technical-writing-to-simple-english.md) |

**A scope edge is the one exception to positive framing**, and the **Browser surface**
row is negative on purpose. Enforcement is documentary for each row, so the rendered
prompt is where the rule reaches the worker. `scripts/test_prompt_template.py` fails
where a part of that table leaves the template body.

**Keep the three delegations apart.** A worker that runs one artifact through two of
them acts on contradictory instructions. This session's artifact is the prompt, and
`prompt-improver` shaped it at build time. The worker's artifact is its own **Prose
deliverable**, and `simple-english` shapes that. `ponytail` governs how much exists at
all. The ordering rule and the one real collision sit in the **Prose deliverable**
entry of [`CONTEXT.md`](CONTEXT.md).

**The project recipe reaches the worker through the Checklist, and not as a fifth
input.** The boot box names `run_recipe` and the item's `ports`, the DB box names
`db_gate`, and the evidence box names the `evidence` bar. Each box drops where its
field is blank, so the recipe of the repo is already inside the boxes this session
sends. The review note on the **work item** is the last box, and **that note is the
worker's last act.**

**The worker writes no work-state label, and neither does anything else about the
board.** So the prompt hands it no `gh` command at all. The tick writes the review state
([On the tick](#on-the-tick--what-it-wrote-and-what-is-left-for-you)), from the ticked
checklist and the green **Gate record** the worker leaves behind. Those two are the
worker's whole part in that transition.

**One family means one swap, so nothing can stack.** One writer inside the seam owns that
swap at both ends: the spawn claim calls it at step 5, and every later transition is a
tick calling it. A worker that writes a work-state label of its own leaves the tick reading
a state nothing computed. Rationale:
[`docs/adr/0056-the-tick-applies-the-transition-it-computed.md`](docs/adr/0056-the-tick-applies-the-transition-it-computed.md).

**Harness shape:** the split lands on one value, and that value is the routed skill. A
**claude** worker takes the literal slash command (`/implement`), and its other slash
skills (`/ponytail:ponytail`) stay available on top
(`references/harnesses/claude.md`). **Any other harness** takes the skill's contract as
prose, from the *Without slash commands* sentence of that row in
[`references/skill-routing.md`](references/skill-routing.md). **Never send a slash
command to a harness that cannot parse one** — it reads as literal text and the worker
starts cold, which is worse than the prose contract because it looks like it worked. The
template header holds the shape each value takes, and the rest of the body is
harness-neutral prose.

**Per-item ports.** Derive from the work-item number `N` per config's `ports`
(e.g. `FE=3000+N`), so parallel workers never collide and the port reads back to
the item. Check reuse before booting; tear down after evidence — per the recipe.

### Start the tick — one Item automation per worker

**A spawn with no tick is incomplete.** The last step of every spawn creates an **Item
automation** (op 11). One per worker, implementation and review alike. The **Tool** owns
the schedule, so it outlives this session, a restart of the harness and a reboot. It
ticks once a minute. A batch of five siblings gets five automations, one each.
Definitions: the **Item automation** and **Position** entries in
[`CONTEXT.md`](CONTEXT.md). Rationale:
[`docs/adr/0022-item-automation-replaces-the-blocking-watch.md`](docs/adr/0022-item-automation-replaces-the-blocking-watch.md).

**The precheck is the whole tick.** `tick` reads the same plan `phase` reads, and then it
applies the one transition that plan carries. The outcomes and their order are unchanged.
**No path through it exits 0**, so every run records as skipped, no model loads and no agent
runs on a tick. That command goes into op 11's `<precheck-command>` placeholder:

```bash
python3 <plugin root>/scripts/worker_state.py tick --item <N> \
  --worktree <the path from op 2> \
  --process '<the pattern from references/harnesses/<harness>.md>' \
  --rounds <config's review.rounds> --stall-after <duration> \
  --repo <owner>/<name> \
  --tracker-cli <gh or glab> --tracker-host <host> \
  --require-gate '<one per required layer, from config's gates: block>' \
  --checkout <config's repo> --default-branch <the default branch> \
  --teardown-command '<op 12 && op 10, with the ids filled in>' \
  --review    # only where config's review.enabled is on
```

**The last three flags are the close, and they are not optional.** A merged pull request
fires a whole **Close transaction** on the tick that reads it
([Close a task](#close-a-task)). A precheck missing `--checkout` or `--teardown-command`
closes nothing and names the flag, so the item then sits at the review state with its pull
request already merged.

**`--checkout` is the main checkout, and never the item's worktree.** That worktree is a
linked one, so `git fetch origin <branch>:<branch>` inside it exits 128 with `refusing to
fetch into branch`: the main checkout already holds that branch. Step 5 of the transaction
is that fetch, so the flag decides whether a close can run at all.

**`<plugin root>` is a literal path in this string, and never a shell variable.** The
**Tool** stores the precheck and runs it a minute later, in a shell that saw no
assignment, and with a working directory this session did not choose. So substitute the
value the preflight resolved
([Resolve the plugin root, and prove the seam runs](#resolve-the-plugin-root-and-prove-the-seam-runs)).
A precheck that carries the module form still runs inside a worktree of *this* repo. It
then runs that worktree's copy of the seam, and not the installed one.

**Op 11's `--prompt` and `--provider` are inert.** The CLI requires both. Neither one runs.
Exit 0 is what starts that agent, and no path through `tick` exits 0. Write a prompt that
says the tick applied its own transition, so a maintainer who reads the schedule is not
misled. Rationale:
[`docs/adr/0056-the-tick-applies-the-transition-it-computed.md`](docs/adr/0056-the-tick-applies-the-transition-it-computed.md).

**Resolve the config values once, here.** The seam parses no configuration file, and it
names no harness, no tracker and no tool. So the spawn is the one place they are read:

| Value | Where you read it | What it decides |
|---|---|---|
| the plugin root | the preflight in [Resolve the plugin root](#resolve-the-plugin-root-and-prove-the-seam-runs) | which copy of the seam a tick runs, and whether it runs at all |
| the round bound | config's `review.rounds` (default 3) | when `rounds-exhausted` fires instead of `verdict-request-changes` |
| the proof-box gate | a non-blank `run_recipe`, or an `evidence` bar that asks for UI proof | whether the worker's **Checklist** ships a proof box — see [The proof box](#the-proof-box) |
| the harness process pattern | `references/harnesses/<harness>.md` | what the `dead` outcome looks for |
| the stall window | longer than the item's slowest single step, so a worker thinking hard is never read as stalled | when `stalled` fires |
| the required gate layers | config's `gates:` block — one `--require-gate` per non-blank command, minus `deep` under the `lite` profile, and never `story` | when `gates-unproven` fires in place of a finish. With none the record is never read ([`references/quality-gates.md`](references/quality-gates.md)) |
| the review policy | config's `review.enabled` | whether a finish holds its swap to the review state, because a **Review round** comes first |
| the tracker CLI | `docs/agents/issue-tracker.md` | which command reads the labels and the comments, and which writes the label a transition swaps |
| the tracker host | `docs/agents/issue-tracker.md`, where the tracker is self-hosted | which server those reads and that write go to |
| the checkout | config's `repo` | where step 5 of a **Close transaction** pulls the merge into |
| the default branch | config's `repo`, or the tracker's own default | which branch step 5 moves |
| the teardown command | [`references/tools/<tool>.md`](references/tools/_operations.md), op 12 then op 10 | what step 8 runs to remove the automation and the worktree |

**The teardown command is one string, and it removes the automation as well as the
worktree.** Read both halves from the tool reference. Substitute the ids. Then join them
with `&&` in that order. **The automation goes first**, so nothing ticks against a
worktree that is half removed. Use `&&` and not `;`. A failed op 12 then leaves both in
place, and the plan reports the failure rather than a leaked schedule. The checklist file
dies with the worktree, so nothing cleans it up. Where the tool records operations 11 and
12 as unsupported, no automation exists and there is no precheck to carry the string.

Every value above is a flag on the command, except one. **The proof-box gate is not a
flag.** It decides whether the **Checklist** this session writes ships a proof box, and
"every box ticked" then covers the proof. So the seam needs no second outcome for it. It is
the same gate the Browser-surface preflight uses, so the two cannot disagree about when a
proof is required.

`--repo` is the tracker repository as `OWNER/NAME`, read from
`docs/agents/issue-tracker.md`.

**`--review` is a switch and not a value.** Pass it only where config's `review.enabled` is
on. A finish then holds its swap, because a **Review round** comes next and a worker still
owns the item. With no `--review` a finish writes the review state, which is the policy this
repo runs.

**`--tracker-cli` and `--tracker-host` cover the tracker read and the label write.** `gh` on
github.com is the default and needs no host, so this repo passes neither flag. A self-hosted
GitLab needs both, and it then needs no wrapper script outside this repo.

**There is no delivery, so this command carries no target.** The tick applies the transition
itself and wakes nobody. It writes no marker file and it needs no suppression window,
because the label it wrote is what stops the same fire on the next minute. So no handle, no
title and no send template enter the precheck
([`docs/adr/0056-the-tick-applies-the-transition-it-computed.md`](docs/adr/0056-the-tick-applies-the-transition-it-computed.md)).

**The tick writes one work-state label, or it runs one close.** It composes no
prompt, kills no process, moves no card, merges nothing and spawns nothing. **At most one
transition lands per run.** The **Item automation** entry in [`CONTEXT.md`](CONTEXT.md)
holds that prohibition. **The close is the one destructive act that left this session**, and
two refusals inside `scripts/close_item.py` stand in front of it. Every other destructive
act stays here, where a human can interrupt it.

**A tool with no automation surface spawns exactly as it does today.** Operations 11 and
12 are optional (`references/tools/_operations.md`), and `cmux` and `herdr` record them
as unsupported. Skip the step and change nothing else about the spawn. **Then say in the
report that the tick is unavailable on this tool.** The maintainer then knows to monitor by
hand ([Monitor workers](#monitor-workers)).

The argument surface is `python3 <plugin root>/scripts/worker_state.py tick --help`, and
the module docstring is the outcome table, the transition table and the exit codes.
**Never restate one of them here or in a report.** What this session does after a tick has
written a label is
[On the tick](#on-the-tick--what-it-wrote-and-what-is-left-for-you).

**A tick against a worktree that is gone writes nothing.** The seam exits 3, which is
non-zero, so the run records as skipped. A live automation on a removed
worktree is a leak from a teardown that skipped op 12. Remove it by name
(`orchestrator-item-<N>`, op 12), because no transition can come for it.

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
  code-changing follow-up appropriately for the harness. **One re-prompt, and then a
  human.** A worker that stalls again gets `needs-human`, which the tick writes
  ([On the tick](#on-the-tick--what-it-wrote-and-what-is-left-for-you)). Never diagnose why
  it stopped. Never re-spawn it on a bigger model
  ([`docs/adr/0058-one-re-prompt-then-a-human.md`](docs/adr/0058-one-re-prompt-then-a-human.md)).

The tick is what fires this rule without your asking
([Start the tick](#start-the-tick--one-item-automation-per-worker)). The four
bullets above stay the way to answer *what are the workers doing*, and they
are the whole of monitoring on a tool with no automation surface.

## On the tick — what it wrote, and what is left for you

**The tick has already written the label by the time you read this section.** It applies
the transition it computed, in the process that read the facts
([`docs/adr/0056-the-tick-applies-the-transition-it-computed.md`](docs/adr/0056-the-tick-applies-the-transition-it-computed.md)).
**So write no work-state label here, and hand no `gh issue edit` to anything.** Read the
item, find the outcome, run its row, and report per
[Reporting to the user](#reporting-to-the-user).

**Nothing wakes this session any more.** The tick delivers no line, so a transition is a
line in the schedule's run history and a label on the item. You find it when the maintainer
asks, or when you next read the queue
(["What next?"](#what-next--pick-the-next-work), which already reports every item at
`to-review` beside the ready queue).
Until the item that removes that gap lands, **read the item's labels and its `Verdict:`
comments before you answer any question about a worker**
([`references/tracker-reads.md`](references/tracker-reads.md)).

**Three outcomes carry a label the tick wrote, and it is one swap in one call.** The
work-state family has four values and it never stacks. So the tick removes every value it
found and adds the new one in the same command. **It moves no card**, because the board is
an input ([Board status](#board-status)). That write is also what stops a repeat fire on the
same fact a minute later. **The worker writes none either** — its last act is the review
note.

**One outcome carries a whole Close transaction, and it is `merged`.** The tick reads the
pull request for the item's branch, and a merged one closes the item, removes the worktree
and removes the automation. So there is no close to run here and no verb to wait for
([`docs/adr/0057-the-merge-is-the-second-act.md`](docs/adr/0057-the-merge-is-the-second-act.md)).

**One outcome carries a comment or a label, and it is `stalled`.** The first stalled tick
posts one `Re-prompt:` comment and moves nothing. The second writes `needs-human`, and only
the maintainer clears that label
([`docs/adr/0058-one-re-prompt-then-a-human.md`](docs/adr/0058-one-re-prompt-then-a-human.md)).

**Four outcomes carry nothing at all**, and the tick exits 2 on each of them. The item stays
where it is, and the row below is the whole of what is left to do.

| Outcome | What the tick already wrote | What is left for you |
|---|---|---|
| `implementation-complete` | `in-progress` → `to-review`, on a leaf item and on a `user-story` parent alike. **Review on**: nothing, because a worker still owns the item and `--review` holds the swap | **Leaf, review on**: [Adversarial review](#adversarial-review-when-configs-reviewenabled) steps 1 and 2. Step 1 also **repoints the precheck** at the reviewer's worktree, with the review harness's process pattern — below. **Leaf, review off**: the item is already with a human. Report the finish, the label the tick wrote, and the review you can still offer, in one line. **Parent**: [The story proof](#the-story-proof), steps 4 to 7. Read the evidence note and the spec PR, then run [The layer 5 story gate](#the-layer-5-story-gate). **The gate runs after that swap, and it needs no label of its own.** No adversarial review round runs on the parent |
| `gates-unproven` | nothing, because the item stays where it is | Reset the context and re-prompt — below. The line names one of four causes, so quote that cause and name the command to run again. Never move the item to review on this line |
| `verdict-approve` | `in-progress` → `to-review` | [Adversarial review](#adversarial-review-when-configs-reviewenabled) step 4 — gather evidence, and report that the item is with a human |
| `verdict-request-changes` | nothing, because a fix round is still the same worker's work | [Adversarial review](#adversarial-review-when-configs-reviewenabled) step 3, at the round the line names. That step also **repoints the precheck** back at the implementation worktree, with the implementation harness's pattern — below |
| `rounds-exhausted` | `in-progress` → `to-review` | Step 4 again — "after the last round regardless". The bound is spent, so offer no further round |
| `merged` | the whole **Close transaction**: the review label came off, the item closed, and the worktree and the automation are gone. The line carries the plan | Nothing on the item. **Parent-close is what is left** ([Close a task](#close-a-task)), and only where this was the last child of a `user-story` parent |
| `dead` | nothing, because the item stays where it is | Report, and **never re-prompt** — below |
| `stalled` | **first stall**: one `Re-prompt:` comment, and no label. **Second**: `needs-human`, with one comment that says what it saw | **First**: read that comment, then reset the context and re-prompt with the steps it carries — below. **Second**: report that the item is with a human, and clear nothing yourself |
| `unreadable` | nothing, because a read that failed cannot say where the item sits | Report in one line: the tracker read is broken, and the item is unobserved until that read works again |

**The computed Position is what makes the response a lookup.** The seam computes where the
item sits and reads no label of its own to do that. It reads the work-state label, the
`Verdict:` comment list and the last write to the checklist. So `implementation-complete`
and `verdict-approve` can never arrive for one item on the same minute. The rule has one
home, the **Position** entry in [`CONTEXT.md`](CONTEXT.md), and this table restates no part
of it. `unreadable` is the one outcome no position gates: the read that failed is the read
that carries the facts. The on-demand door (`review #N adversarially`) is unchanged, and it
needs no label of its own.

**`needs-human` answers before every fact.** The tick reads that label first and stays
quiet, so a paused item moves nowhere and no row above runs.

**Why four outcomes carry no label.** A fix round is still the same worker's work, so
nothing changes state. `dead` says something about the worker rather than about
the item, and a re-prompt cannot reach a process that is gone. `unreadable` says something
about the tracker read, and a fact the tick never read
cannot decide a label. `gates-unproven` says the work is not finished after all, so the
item stays where it is
([`docs/adr/0036-a-gate-run-is-work-product.md`](docs/adr/0036-a-gate-run-is-work-product.md)).

**A row you already ran is a row that carries the same round
number, or the same checklist position.** Say so in
one line and do nothing. That stays a lookup, because the line carries both facts.

**Two rows carry an act on the schedule: they repoint the precheck at the live worker.** One
**Item automation** per item stands, and a transition moves the work to a different worker.
So the precheck follows it (op 13,
[`references/tools/_operations.md`](references/tools/_operations.md)). The repoint sits in
the same row as the spawn of that worker, so one transition is one step. It is not a repair
the maintainer has to remember:

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
`verdict-approve` and `rounds-exhausted` hand the item to a human. `dead`, `stalled`,
`gates-unproven` and `unreadable` say nothing about which worker is live. Rationale:
[`docs/adr/0026-the-automation-follows-the-live-worker.md`](docs/adr/0026-the-automation-follows-the-live-worker.md).

**The repointed precheck is the same `tick` command, with two flags changed.** `--worktree`
and `--process` name the live worker. Every other flag keeps the value the spawn resolved
([Start the tick](#start-the-tick--one-item-automation-per-worker)). So a repoint changes
which worker is watched and nothing else about the transition the tick can apply.

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
exactly as it is for a stall. **This is not a stall**, so the tick writes no `Re-prompt:`
comment and this re-prompt counts toward nothing.
**The record is not an enforcement mechanism**: nothing blocked the
worker's push, and the item stops before review instead
([`docs/adr/0036-a-gate-run-is-work-product.md`](docs/adr/0036-a-gate-run-is-work-product.md)).

**`dead` — a re-prompt cannot work, so nothing re-prompts.** No live agent process has its
working directory inside the worktree, so nothing listens. Report where the item sits and
where the worker got to. Then name the one human decision: tear the worker down and
re-spawn it. **Teardown keeps its confirmation** ([Safety](#safety)), because a
tick cannot read intent in an uncommitted diff. This outcome needs no stall window, so it
arrives about a minute after the worker exits.

**`stalled` — one re-prompt, and then a human.** A live process with stale work product, so a
re-prompt is the response that works once. **The tick owns the count**, which is the number of
`Re-prompt:` comments on the work item. That is the shape the **Review round** number already
takes, as the count of `Verdict:` comments. So no session holds either count in its context
([`docs/adr/0058-one-re-prompt-then-a-human.md`](docs/adr/0058-one-re-prompt-then-a-human.md)).
**Only a comment that opens with the literal counts**, so a report or a note that quotes it
spends no retry.

- **The first stalled tick posts one `Re-prompt:` comment**, which carries what it saw and the
  unticked steps. Read that comment. Reset the worker's context
  ([Reset the worker's context before every re-prompt](#reset-the-workers-context-before-every-re-prompt)),
  then re-prompt with those steps (op 4). **The re-prompt is unconfirmed** — it is additive,
  and it costs the maintainer nothing to get wrong.
- **The second stalled tick writes `needs-human`**, with one comment that says what it saw.
  The item is then with a human, and every later tick leaves it alone. **Write no label, and
  clear none.** Offer the teardown as the pending decision, and do not run it.

**Do not diagnose *why* the worker stalled.** **Never re-spawn it a rung up.** Both are
judgement on a live terminal, and nothing here asks for either.

**No response above touches the automation.** It outlives the re-prompt, the fix round and
this session, so there is nothing to restart. The seam still holds no state that changes an
answer, which is what keeps a re-prompt free. Rationale:
[`docs/adr/0018-the-worker-watch-is-a-stateless-seam.md`](docs/adr/0018-the-worker-watch-is-a-stateless-seam.md)
and
[`docs/adr/0022-item-automation-replaces-the-blocking-watch.md`](docs/adr/0022-item-automation-replaces-the-blocking-watch.md).

### The proof box

**A worker's Checklist ships a proof box only where the project recipe asks for a proof.**
The gate is the one resolved at spawn: a non-blank `run_recipe`, or an `evidence` bar that
asks for UI proof. Where neither holds, the box drops before the send, and the checklist
holds the boxes it always held. **This repo is that case.** Its `run_recipe` is
blank, and its `evidence` bar asks for a test run and resolved cross-references. So no item
here grows a proof box
([`references/checklist.template.md`](references/checklist.template.md)).

**The proof is one more box, and it needs no label and no outcome of its own.** So "every
box ticked" already covers it, and one worker works one list top to bottom
([`docs/adr/0053-one-work-state-label-and-a-computed-position.md`](docs/adr/0053-one-work-state-label-and-a-computed-position.md)).

Where the gate does hold:

1. **Ship the proof box in the checklist**, at the position the template gives it.
2. **The proof runs in the implementation worker's own worktree.** Not a fresh worker: that
   worktree already holds the branch, the checklist and the per-item `ports`. So the reset
   and the self-contained re-prompt rules apply to it unchanged
   ([Reset the worker's context before every re-prompt](#reset-the-workers-context-before-every-re-prompt)).
3. **The proof drives the declared Browser surface**, `playwright-cli`. It boots the app
   per `run_recipe`, on those ports. A browser MCP the worker's session happens to expose is
   out of bounds, whichever one it is. That is the same scope edge every spawn prompt
   already carries.
   Reason, and why an MCP transcript is not durable evidence:
   [`docs/adr/0012-playwright-cli-is-the-only-browser-surface.md`](docs/adr/0012-playwright-cli-is-the-only-browser-surface.md).
4. **The finish is the same Completion signal**, a fully ticked checklist with the proof box
   ticked. The tick then reports `implementation-complete`, and the row above carries the
   item on.

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

When a worker finishes a work item and review is enabled. **The tick is the actor that
starts it** — its `implementation-complete` outcome
([On the tick](#on-the-tick--what-it-wrote-and-what-is-left-for-you)). The item stays at `in-progress`
through the whole loop, because a worker still owns it.

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
   ([On the tick](#on-the-tick--what-it-wrote-and-what-is-left-for-you)). The precheck is the same `tick`
   command. `--worktree` and `--process` then name this worktree and the review harness.
   **The automation is repointed, and never restarted**, so the schedule and its run history
   both stay. The first `Verdict:` comment is what makes the tick read a verdict rather
   than a checklist, so a reviewer needs no flag and no label of its own.
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
   value is `approve` or `request-changes`. That literal is what puts the item in a review
   round, so a review whose comment omits it fires no transition at all. Its count is
   also the round number, so an omitted line loses the count with it. It is quoted
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
   ([On the tick](#on-the-tick--what-it-wrote-and-what-is-left-for-you)). The automation already runs and
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
4. **On approve, or after the last round regardless:** gather evidence and report that the
   item is with a human. **The tick has already swapped `in-progress` for `to-review`**, on
   its `verdict-approve` or `rounds-exhausted` outcome. No card moves with it
   ([Board status](#board-status)). **Write that label nowhere.** The item holds
   `in-progress` for the whole loop, because a worker owns it and a fix round is that same
   worker's work. So the label changes only here, at the one moment the loop concludes
   ([`docs/adr/0056-the-tick-applies-the-transition-it-computed.md`](docs/adr/0056-the-tick-applies-the-transition-it-computed.md)).
   `--review` on the precheck is what holds the finish back until this moment
   ([Start the tick](#start-the-tick--one-item-automation-per-worker)).
   Merge is always a human step.

On demand: **"review #N adversarially"** runs this flow directly even if review is
off in config.

## Close a task

**There is nothing to run here.** A close is what one tick does when the pull request for
an item's branch reads `MERGED`. The maintainer merges on the tracker, and the next tick
closes the item, removes the worktree and removes the automation. **No verb starts a close,
and no label authorises one**
([`docs/adr/0057-the-merge-is-the-second-act.md`](docs/adr/0057-the-merge-is-the-second-act.md)).

So *merge and close N*, *close N*, *it's done* and *wrap up <slug>* are questions now. Read
the item and its pull request. Then answer in one line:

| What you read | The one-line answer |
|---|---|
| the pull request is merged, and the item is closed | it closed on a tick, and that tick's line carries the plan |
| the pull request is merged, and the item is open | the next tick closes it, inside a minute |
| the pull request is open | merge it on the tracker, and the close follows by itself |
| the item wears `needs-human` | quote the comment on the item, and stop |
| there is no pull request | no worker opened one, so read the outcome instead ([On the tick](#on-the-tick--what-it-wrote-and-what-is-left-for-you)) |

**Never merge for the maintainer, and never run `scripts/close_item.py` by hand.** That
seam runs inside the tick, in the process that already read the item
([Start the tick](#start-the-tick--one-item-automation-per-worker)). A second caller is a
second source of truth about what closed an item. The five steps, their order, their gates
and their refusals live in the seam and in the **Close transaction** entry of
[`CONTEXT.md`](CONTEXT.md). **Never restate one of them here, in a prompt, or in a report.**
Rationale:
[`docs/adr/0015-close-is-a-deterministic-transaction.md`](docs/adr/0015-close-is-a-deterministic-transaction.md).

**A refused close writes `needs-human` and stops.** The comment on the item carries the
plan's own reason, so a dirty worktree names its files. Read that comment, then repair the
one thing it names. **A refused item keeps its observer**, because teardown is step 8 and a
refusal never reaches it. That is deliberate: an item that did not close is exactly the one
that must keep watching.

**The recovery goes back through the implementation position, and it takes two ticks.** The
refusal took `to-review` off the item, so clearing `needs-human` leaves it with no
work-state label. The next tick then reads implementation, re-proves the finish, and writes
`to-review` again. The tick after that reads the merge and closes. **Where the repair was a
commit, the Gate record must go green at the new `HEAD` first**, or the tick fires
`gates-unproven` instead
([On the tick](#on-the-tick--what-it-wrote-and-what-is-left-for-you)). A repair that commits
nothing needs no gate run.

**A close needs three flags on the precheck**, and a spawn is where they are resolved
([Start the tick](#start-the-tick--one-item-automation-per-worker)). A precheck missing
`--checkout` or `--teardown-command` closes nothing and names the flag. So an item that sits
at the review state with a merged pull request is a precheck to repair.

### Parent-close is what is left for you

**The tick closes one item, and it closes no parent.** Where the tracker conventions
define a parent close, apply it after the last child of a `user-story` parent closes.
**The parent's card needs no move**, because the board's own built-in workflow answers a
closed item ([Board status](#board-status)). **Two steps run before that close, in this
order**: [The story proof](#the-story-proof), then
[The layer 5 story gate](#the-layer-5-story-gate). A proof that failed stops there, and the
parent stays open.

**The read is *Every child of a parent work item, closed children included***
([`references/tracker-reads.md`](references/tracker-reads.md#every-child-of-a-parent-work-item-closed-children-included)).
An open-item list cannot answer this step, because the child that closed last is not in
it. Then report per [Reporting to the user](#reporting-to-the-user).

### The story proof

**Prove the whole user story before the parent closes.** The trigger is two facts: the last
child's **Close transaction** completed, and the parent carries `user-story`. The term
is the **Story proof** entry in [`CONTEXT.md`](CONTEXT.md). Rationale, what it narrows and
the accepted risks:
[`docs/adr/0047-the-story-proof-runs-before-the-story-gate.md`](docs/adr/0047-the-story-proof-runs-before-the-story-gate.md).

**The reachability gate is the one the proof box already uses**: a non-blank `run_recipe`,
or an `evidence` bar that asks for UI proof ([The proof box](#the-proof-box)). This step
defines no second gate, so the two can never disagree. Where neither half holds, no story
proof runs, and the parent goes to the layer 5 story gate. **This repo is the blank case.**
Its `run_recipe` is blank, so no story here ever reaches a story proof.

Where the gate does hold:

1. **Claim the parent**, with the same `tick --claim` command a leaf spawn runs
   ([Spawn a worker](#spawn-a-worker-implement-x)). One label swap through the one writer, and no card
   moves with it ([Board status](#board-status)).
2. **Spawn the proof worker**, and start or repoint the **Item automation** — below.
3. **The tick reads `implementation-complete` on the parent, and writes `to-review`**
   ([On the tick](#on-the-tick--what-it-wrote-and-what-is-left-for-you)).
4. **Read the evidence note and the spec PR.**
5. **Run [The layer 5 story gate](#the-layer-5-story-gate)**, and triage every candidate it
   reports.
6. **The parent already wears `to-review`**, because the tick wrote it at step 3. So there
   is nothing to swap here, and this session writes no label
   ([On the tick](#on-the-tick--what-it-wrote-and-what-is-left-for-you)).
7. **The maintainer reads the spec PR, then asks for the close.** No session merges that PR
   unasked ([Close a task](#close-a-task)).

**The worker is fresh, in its own worktree cut from the default branch.** That tree is the
first place every child's merged code sits together, and no child's worktree ever held it.
**This is the one difference from [The proof box](#the-proof-box) on a leaf item**, which
re-prompts the worker that is already there. **The role is `heavy`.** Resolve its
`(model, effort)` pair from [`references/models.md`](references/models.md), the same as any
other spawn ([Right model for the job](#right-model-for-the-job)). Everything else is
[Spawn a worker](#spawn-a-worker-implement-x) unchanged.

**The worker leaves two artifacts, and they are the whole record of the run:**

- **An evidence note on the parent work item.** It holds one line per user story of the
  parent spec, and each line says which criteria that story exercised.
- **The generated Playwright spec.** The worker wires it into the project's own test command,
  commits it on its own branch, and opens a PR for it.

**This prompt carries the Browser surface scope edge too.** The proof drives the declared
surface, `playwright-cli`. A browser MCP the worker's session happens to expose is out of
bounds, whichever one it is. It is the same edge every spawn prompt already carries, so never
restate its reason here
([The prompt: checklist + completion contract](#the-prompt-checklist--completion-contract),
[`docs/adr/0012-playwright-cli-is-the-only-browser-surface.md`](docs/adr/0012-playwright-cli-is-the-only-browser-surface.md)).

**The Item automation is `orchestrator-item-<parent N>`, and one item never holds two
schedules.** Where the parent already carries one, repoint its precheck at the proof worktree
(op 13), the same way a review round does
([On the tick](#on-the-tick--what-it-wrote-and-what-is-left-for-you)). Where it carries none, create one at
this spawn ([Start the tick](#start-the-tick--one-item-automation-per-worker)). Step 8 of the
parent's own **Close transaction** removes it.

**A failed proof stops the parent close.** The worker posts the finding on the parent as its
evidence note, and it ticks no last box. So a real defect is not a stalled worker. This
session then files each failure through `/to-tickets`, and it leaves the parent open at
`in-progress`. It runs **no** layer 5 story gate, and it reports the pending human
decision ([Reporting to the user](#reporting-to-the-user)). `gates-unproven`, `stalled` and
`dead` keep the answers they already have
([On the tick](#on-the-tick--what-it-wrote-and-what-is-left-for-you)).

### The layer 5 story gate

**Run `/improve-codebase-architecture` when a user story finishes.** The moment is the
close of its last child, in the same turn that bumps the version in
`.claude-plugin/plugin.json`. The bump rule itself is a project rule, in config at
`docs/agents/orchestrator.md`, and this step performs no bump. The lane is `inline`, so
this session invokes the skill here, in the main checkout, on the default branch
([Resolve the verb before you act](#resolve-the-verb-before-you-act)).

**It runs after the story proof, and it does not run where that proof failed**
([The story proof](#the-story-proof)).

Layers 1 to 4 each read one work item, inside one worker worktree. This layer is the one
that reads what ten green items left behind. The five layers are in
[`references/quality-gates.md`](references/quality-gates.md), and the word is the
**Layer** entry in [`CONTEXT.md`](CONTEXT.md).

Hand the skill the direction to look in, where the maintainer named one. The Notes column
of its row in [`references/skill-routing.md`](references/skill-routing.md) holds the rest.
**The skill owns its own report.** Never restate one of its headings here, in a prompt or
in a report.

**Save the report before you triage.** The skill writes its HTML to the temporary directory of
the OS, and the next reboot deletes it. Copy that file to
`docs/refactor-opportunities/<story>-<slug>.html`. `<story>` is the number of the user story,
and `<slug>` is a short slug from its title. The story number comes first, so two stories never
collide. **This session commits the copy**, as a docs-only commit on the default branch,
because it already writes to the tracker from the same checkout. The word is the **Story gate
report** entry in [`CONTEXT.md`](CONTEXT.md), and what lands in that directory is
[`../docs/refactor-opportunities/README.md`](../docs/refactor-opportunities/README.md).
Rationale:
[`docs/adr/0048-the-story-gate-report-is-a-repo-artifact.md`](docs/adr/0048-the-story-gate-report-is-a-repo-artifact.md).

**Triage every candidate the report holds. This session does it, in prose:**

- **`Strong`** becomes a work item, through `/to-tickets`, and it wears `rating:strong`.
- **`Worth exploring`** goes to the backlog, and it wears `rating:worth-exploring`.
- **`Speculative`** is dropped, with a one-line reason in the report to the user.

**Every candidate this gate files carries two back-references and two labels.** The references
are the user story the gate read, and a link to the saved report. The labels are `refactor` and
the rating label in the list, and `docs/agents/issue-tracker.md` defines both families. The
first two ratings each reach the tracker, so each one carries the pair and both labels. The
third files nothing, so it carries none. **Neither family moves a board card**, because
nothing moves one ([Board status](#board-status)).

The skill ends by asking which candidate to explore. This triage is the answer, so no
grilling loop runs here.

**The threshold is 0 untriaged `Strong` candidates, and not 0 findings.** This session
checks it, and `scripts/close_item.py` does not. That seam owns the judgement-free steps
of a **Close transaction** alone, and triage is judgement
([Close a task](#close-a-task)).

**Layer 5 stops nothing.** It holds no exit code, so it fails no push and no merge. Depth
is a judgement, and a hard gate here stalls every story on an opinion. A candidate still
untriaged is work to report, and never a close this session refuses. Rationale, the
threshold and the accepted risk:
[`docs/adr/0033-the-story-gate-is-advisory.md`](docs/adr/0033-the-story-gate-is-advisory.md).

## Merge the queue

This flow runs when the maintainer asks for the queue, usually after a
["What next?"](#what-next--pick-the-next-work) read. **No tick starts it**, because no label
records a merge ask. It runs one **Merge train**: one ordered run over the **Merge queue**,
both defined in [`CONTEXT.md`](CONTEXT.md).

**The ordering rule and the park rule live in
[`references/merge-train.md`](references/merge-train.md).** Read them there at the moment
you need them, and never from memory. This section restates neither one. Rationale:
[`docs/adr/0037-the-merge-queue-is-an-ordered-train.md`](docs/adr/0037-the-merge-queue-is-an-ordered-train.md).

1. **Resolve the Merge queue fresh.** The maintainer's ask names the items. Where the ask
   names the queue rather than a list, read every open item at `to-review` and confirm the
   set in one line before the train starts. Nothing on the tracker records the ask, so a
   train never infers one
   ([`docs/adr/0053-one-work-state-label-and-a-computed-position.md`](docs/adr/0053-one-work-state-label-and-a-computed-position.md)).
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
   session performs it. **The comment is the whole park.** No label moves, because a queued
   item already wears the review state, and no card moves either
   ([Board status](#board-status)). `scripts/merge_train.py` comments nowhere, so this
   session posts that one comment.
5. **Hand the maintainer the order, and merge nothing.** They merge on the tracker, in
   that order, and each merge closes its own item on the next tick
   ([Close a task](#close-a-task)). **No step of a Close transaction changes, and their
   order does not change.** So a train adds one caller and no second close path.
6. **A late conflict parks the item, and the train continues.** It appears when the
   maintainer merges, because an earlier merge of this same train moved the default branch.
   Park it per step 4, then continue with the next item. `resolving-merge-conflicts` is
   there where they ask for it.
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
- **Restate the position every turn, and carry the progress with it.** A worker's progress
  is `implementation · checklist 4/7`, a review loop is `review round 2 of 3`. Every
  report of an owned item says where it sits, because that is the fact a fresh
  session cannot infer. The position is computed, so read it the way the seam does: the
  work-state label, the `Verdict:` comment count and the checklist file. Do not ask the
  user to remember any of the three.
- **A tick report names the outcome and the transition the tick applied.** The outcome is the
  tick's own word: `implementation-complete`, `gates-unproven`,
  `verdict-approve`, `verdict-request-changes`, `rounds-exhausted`,
  `dead`, `stalled` or `unreadable`. Then
  the label the tick wrote, then what you did. `#38 implementation-complete · in-progress
  held. Reviewer spawned, gpt-5.6-terra @ high.` **Where the tick handed the item to a human,
  name the swap it wrote.** That one write is the whole hand-off:
  `#38 verdict-approve · in-progress → to-review.` Read the swap off the item, and never
  write one yourself.
- **A story-proof line names the parent and the two artifacts.**
  `#57 story proof · evidence note on #57 · spec PR #64.` The parent number is
  the fact a fresh session cannot infer, because the item that reached the finish was the
  last child ([The story proof](#the-story-proof)).
- **Both counts come from the tracker, so restate both.**
  [On the tick](#on-the-tick--what-it-wrote-and-what-is-left-for-you) says how to read each one.
  `#38 stalled in implementation ·
  checklist 4/7 · retry 1 of 1. Context reset, re-prompted with the unticked steps.` On the
  second stall the tick already wrote `needs-human`, so name the label and stop:
  `#38 stalled again · needs-human written. Read its comment and take the item back.` On
  `dead` the next step is a teardown — name it as the pending human decision.
- **Say that the tick writes the label, and that you do not.** One line on the spawn line:
  `#38 tick: applies the transition, review policy off`
  ([Start the tick](#start-the-tick--one-item-automation-per-worker)). The user then knows
  which writes happen with nobody in the turn, and that `needs-human` is the label that
  stops them.
- **Name the panel on the spawn line.** Op 7 opens the work item as a tab beside
  the worker. Say it happened: `#38 panel: opened`.
- **Say when the panel is unavailable.** A tool that records operation 7 as
  unsupported opens no follow-along tab, so say so on the spawn line, once.
- **Say when the tick is unavailable.** A tool that records operations 11 and 12 as
  unsupported gets no automation, so no transition lands on its own. Say so on
  the spawn line, once, and point at the four monitor bullets
  ([Monitor workers](#monitor-workers)). **Run the `tick` command by hand there instead of
  writing a label**, with the same flags the precheck would have carried
  ([Start the tick](#start-the-tick--one-item-automation-per-worker)). One writer holds
  every swap, whether a schedule calls it or you do.
- **One table or list, capped at 5 rows.** More than 5 ready items or 5 findings →
  rank and split (`start now` vs `blocked`, `must-fix` vs `noted`). Five ranked
  beats twelve flat, and the ready queue already promises "at least 5".
- **End with one action the user can take now.** `Spawn #41 next?` / `#38's MR is
  green — merge it and the tick closes #38.` **The merge is the only human step left in the
  second act**, so name it where it is pending.
- **A close report names which steps ran and which refused**, read off the tick's own line
  ([Close a task](#close-a-task)), and ends with the one action left.
  `#20: steps 4 to 7 ran, and step 6 refused. Cause: the worktree holds src/api.ts. Commit
  it or stash it, clear needs-human, and the next tick finishes the close.`
- **A train report names the order the seam planned**, what parked and why, and it ends with
  the one action left. That is the close-report shape, once per train instead of once per
  item ([Merge the queue](#merge-the-queue)). **A parked item is that action**, and it
  carries the conflicting paths. `#152 #153 in that order, ready to merge. #151 parked:
  orchestrator/SKILL.md conflicts. Resolve it in 151-merge-train first.`
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

- **The maintainer's own merge is the authorisation for the teardown that follows it**, and
  no session asks a second time ([Close a task](#close-a-task)). The data-loss case is a
  dirty tree, and step 6 of the transaction refuses it rather than warning. So the one
  unrecoverable case never reaches an unattended teardown
  ([`docs/adr/0057-the-merge-is-the-second-act.md`](docs/adr/0057-the-merge-is-the-second-act.md)).
- **Confirm before any teardown this session runs by hand**, because that one carries no
  merge behind it. It kills the live worker terminal and it can drop uncommitted work.
- **A second stall goes to `needs-human`, and the tick writes that label itself.** So the
  item moves no further, and no teardown runs. A `dead` worker is the ambiguous case that
  still asks. The maintainer said nothing about a teardown, and a tick cannot read intent in
  an uncommitted diff. The re-prompt on the first stall stays unconfirmed, because it
  destroys nothing
  ([`docs/adr/0058-one-re-prompt-then-a-human.md`](docs/adr/0058-one-re-prompt-then-a-human.md)).
- Keep the main checkout (config's `repo`) on the default branch — all
  tracker/git-state ops run there. This orchestrator's own worktree branch is
  separate and irrelevant.
- Never advance an item to done before its PR/MR is actually merged.
