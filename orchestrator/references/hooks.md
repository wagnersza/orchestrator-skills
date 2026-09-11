# The hook plane

A hook is the one part of this stack that can refuse a command before it runs.
Everything else is advice: a skill body states a rule, a **Checklist** repeats it, and
a review note claims it was kept. So a rule holds where a model remembers it, and it is
skipped where the model does not.

Three hooks ship with the plugin. The harness reads `hooks/hooks.json` by convention, so
the enforcement installs with the skill and needs no step from the maintainer and no key in
the manifest. **`.claude-plugin/plugin.json` must hold no `hooks` key.** A key that names
the standard path makes the harness read one file twice, and it then refuses the whole
plugin
([ADR 0060](../docs/adr/0060-the-manifest-names-no-standard-hook-file.md)). Each hook is
stdlib-only Python with a suite of its own, which is the bar the two seams already hold.

**The plane law is one sentence: a hook answers, and a seam performs.** A hook never
writes a label, never merges and never spawns. Rationale, the rejected options, the
supersession of ADR 0034 and every accepted risk:
[ADR 0051](../docs/adr/0051-a-hook-refuses-and-a-seam-performs.md).

## One row per hook

| Hook | Event | What it does | Which failure it kills |
|---|---|---|---|
| `hooks/context.py` | `SessionStart`, matching `startup\|resume\|clear\|compact` | Exports the **Plugin root** from `CLAUDE_PLUGIN_ROOT`. Reads whether this session is an **Orchestrator** or a **Worker**. Injects the item facts: the work-state label, the **Checklist** position, and whether the **Gate record** is green at `HEAD`. | A session that works from memory, and a session that lost the facts to a compaction. It also removes one caller of the plugin-root glob, because the hook is handed the path. |
| `hooks/refuse.py` | `PreToolUse` for `Bash` | Denies three commands. A **Work-state label** write from any session, because only a seam writes one. The teardown command outside `scripts/close_item.py`. A `git push` while a configured **Gate** has no green line at `HEAD`. | A label written by hand. A teardown out of order. A push that skipped a gate. |
| `hooks/record.py` | `PostToolUse` for `Bash` | Where the command that just ran is a configured **Gate** command, appends one line to `.orchestrator/gates-<item>.jsonl` with the command, the exit code, a UTC timestamp and `head_sha`. | A forgotten record, which used to read as a failed gate. |

Every term in bold is defined in [`../CONTEXT.md`](../CONTEXT.md).

## `record.py` is the one named exception

Every other hook only answers, and this one writes a file. The reason is stated and not
hidden: **a record a model writes is a record a model can fake.** The write is not a
mutation of the tracker and it is not a decision. It is an append-only note of what a
command already did.

The line format has one home, and that is the gate record section of
[`quality-gates.md`](quality-gates.md). This hook writes that exact shape, and it holds
no second copy of it.

**This hook is the one writer.** `scripts/checks.sh` appended a line of its own until
[ADR 0052](../docs/adr/0052-a-gate-blocks-and-a-hook-writes-its-record.md) removed it.
A gate command now runs and exits, and no script and no `Makefile` writes the record. So
a green line proves that a command exited zero, rather than that a model said so.

**A gate run outside a session writes no record.** CI and a human at a shell fire no
hook. The record is a fact about a worker's session, which is the only place the
**Completion signal** reads it.

## The push block

**`git push` is denied while any configured Gate lacks a green line at `HEAD`.** This is
the denial that makes "all gates are deterministic" true. A command exit code is the
verdict, `record.py` writes the record that proves it, and now nothing pushes past it.

The check asks one question per gate command that the `gates:` block of **Config** names
with a non-blank command: is there a line with exit `0` at the current `HEAD`? Four
answers read as not green, and they are the four the `gates-unproven` outcome already
uses: a missing line, a malformed line, a non-zero exit and a stale `head_sha`
([`quality-gates.md`](quality-gates.md)). **The newest line of a command is the
verdict**, because a worker runs a command again after it corrects a fault.

**A blank command is not a Gate.** A layer the profile dropped names no command, so it
drops out of this check too. Otherwise a repo on the `lite` profile can never push,
because `gates.deep` is blank there.

**The message names each failing gate and the command to run.** A worker that reads
"denied" and no command guesses. A message that names the `full` gate and `make full`
sends the next turn straight at the repair. The gate name and the command both come from
Config, and the message holds no generic sentence.

**A push is a program and a verb.** The hook reads `git` as the program and `push` as
the verb it was given, after a global flag such as `-C`, and in each command of a chain.
So the tail of `make full && git push` is a push, and a review note that quotes the rule
is not.

Three states permit the push, because each one proves nothing rather than proving a
fault:

- A repo with no marker.
- A checkout with no **Checklist** to name the item.
- A Config with no gate command at all.

**A command that does not exist denies every push in that repo.** So
`/orchestrator-setup` runs each configured gate command once and reports its exit code,
and it names this denial as the reason. A typo in Config is then a message at setup time
rather than a mystery at push time.

## Every hook exits fast where it does not apply

A hook fires in every session on the machine once the plugin is installed. So the first
check in each of the three is the repo marker:

| The marker | Where it sits | What it means |
|---|---|---|
| the orchestrator **Config** | `docs/agents/orchestrator.md` | a main checkout of an orchestrated repo |
| the checklist directory | `.orchestrator/` | a **Worker**'s own worktree |

Either fact is enough. With neither, a hook prints nothing, writes nothing and exits 0.
So a repo this plugin has nothing to say about pays nothing for the plane.

## What each hook reads, and where that fact lives

No hook copies a vocabulary or a command into itself. A rule with two homes drifts.

| The fact | Where the hook reads it |
|---|---|
| the work-state label family | `docs/agents/issue-tracker.md`, the `## Work-state labels` table |
| the item number | the `.orchestrator/checklist-<item>.md` file name |
| the gate commands | the `gates:` block of `docs/agents/orchestrator.md`, keys `quick`, `full` and `deep` |
| the labels the item wears | the **Tracker adapter**, `scripts/tracker.py` |
| the teardown verb | `worktree remove` or `worktree rm`, operation 10 of [`tools/_operations.md`](tools/_operations.md) |
| the commit a run saw | `git rev-parse HEAD` in the worktree |

**Layer 5 names no gate command.** The `story` key holds a verb with no exit code, so
it is not a **Gate** and it never reaches the record
([`quality-gates.md`](quality-gates.md)). A blank key is a dropped layer, and it
matches nothing.

## A hook fails open

`refuse.py` permits a command it cannot split into words, and it denies nothing where
`docs/agents/issue-tracker.md` names no label family. A hook that guesses stops correct
work, and that costs more than the rule it was protecting.

`record.py` writes no line where it cannot read an exit code. The payload carries no
field for one: a completed command answers with an object, and a failed one answers
with a string whose first line reads `Error: Exit code <N>`. An interrupted call and a
call the harness stopped each reach no verdict, so neither one earns a line. A line
nothing stands behind is worse than no line.

## What the plane does not do yet

- **The label denial still reads a command and not a caller's role.** The tick applies the
  transition itself now, so no session has a reason to write a work-state label
  ([ADR 0056](../docs/adr/0056-the-tick-applies-the-transition-it-computed.md)). The
  denial's caller test names one seam file, and no hook writes a label
  ([ADR 0051](../docs/adr/0051-a-hook-refuses-and-a-seam-performs.md),
  [ADR 0055](../docs/adr/0055-the-label-denial-reads-its-caller.md)).
- **No `Stop` hook.** Nothing writes the board on a stop, so a reconcile there would
  move a field no session touched.
- **No merge guard.** The maintainer merges, on the tracker
  ([ADR 0057](../docs/adr/0057-the-merge-is-the-second-act.md)).
- **No label vocabulary changes.** The four work-state strings are the ones
  `docs/agents/issue-tracker.md` holds today.

## The tests, and the restart

One suite per hook: `hooks/test_context.py`, `hooks/test_refuse.py` and
`hooks/test_record.py`. A test drives its hook as a process. The input is the JSON that
the event carries. The test asserts the exit code and what the hook emitted. No test
reaches for a helper inside a hook, so the suite holds the contract a live session
holds. Both gate commands run them, beside the two seam suites.

Each suite covers three cases:

- The marker is absent, so the hook is silent and costs nothing.
- The marker is present, and no work item is in context.
- The deciding case for that hook.

`refuse.py` pairs each denial with a command that must go through. A hook that denies
everything passes a deny test and breaks every run.

**The manifest is read once, at session start.** So a fresh `hooks/hooks.json` reaches
a session after a restart. `/orchestrator-setup` reports whether the plane is live, and
it names that restart. It installs nothing, because the hooks ship with the plugin.

**The rollback is one file, and it is no longer a manifest key.** Rename or delete
`hooks/hooks.json`. The harness then finds no hook file at the standard path and loads the
plugin with the plane off. Nothing in the loop was changed, so every flow keeps working
([ADR 0060](../docs/adr/0060-the-manifest-names-no-standard-hook-file.md)).
