# The hook plane

A hook is the one part of this stack that can refuse a command before it runs.
Everything else is advice: a skill body states a rule, a **Checklist** repeats it, and
a review note claims it was kept. So a rule holds where a model remembers it, and it is
skipped where the model does not.

Three hooks ship with the plugin. `.claude-plugin/plugin.json` holds one key,
`"hooks": "./hooks/hooks.json"`, so the enforcement installs with the skill and needs
no step from the maintainer. Each hook is stdlib-only Python with a suite of its own,
which is the bar the two seams already hold.

**The plane law is one sentence: a hook answers, and a seam performs.** A hook never
writes a label, never merges and never spawns. Rationale, the rejected options, the
supersession of ADR 0034 and every accepted risk:
[ADR 0050](../docs/adr/0050-a-hook-refuses-and-a-seam-performs.md).

## One row per hook

| Hook | Event | What it does | Which failure it kills |
|---|---|---|---|
| `hooks/context.py` | `SessionStart`, matching `startup\|resume\|clear\|compact` | Exports the **Plugin root** from `CLAUDE_PLUGIN_ROOT`. Reads whether this session is an **Orchestrator** or a **Worker**. Injects the item facts: the work-state label, the **Checklist** position, and whether the **Gate record** is green at `HEAD`. | A session that works from memory, and a session that lost the facts to a compaction. It also removes one caller of the plugin-root glob, because the hook is handed the path. |
| `hooks/refuse.py` | `PreToolUse` for `Bash` | Denies two commands. A **Work-state label** write from any session, because only a seam writes one. The teardown command outside `scripts/close_item.py`. | A label written by hand. A teardown out of order. |
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

**Two writers reach the record today, on purpose.** `scripts/checks.sh` appends its
line and this hook appends another. Both lines carry the same four keys and the same
`head_sha`. So a reader that takes the last line per command reads the same verdict
either way. The work item that removes the first writer carries the ADR that supersedes
[ADR 0036](../docs/adr/0036-a-gate-run-is-work-product.md).

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

- **No hook denies a `git push`.** That denial needs a gate record no model wrote, and
  the worker still writes its own. A push denied against a record a worker wrote proves
  nothing, so the denial lands with the item that makes the record deterministic.
- **No hook denies the review state.** The same reason holds.
- **No `Stop` hook.** Nothing writes the board on a stop, so a reconcile there would
  move a field no session touched.
- **No merge guard.** The maintainer merges
  ([ADR 0016](../docs/adr/0016-the-orchestrator-merges-when-asked.md)).
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

**The rollback is one line.** Delete the `hooks` key from
`.claude-plugin/plugin.json`. Nothing in the loop was changed, so every flow keeps
working with the plane off.
