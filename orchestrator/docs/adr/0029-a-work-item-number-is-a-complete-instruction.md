# A verb plus a work-item number is a complete instruction

The maintainer typed `/orchestrator` before nearly every action. The skill then did
the right thing. So the slash command carried no information, and it was the only
thing between a correct flow and no flow at all.

Two defects made that command necessary.

**The triggers named a syntax nobody types.** The description listed `work on #N` and
`close task #N`. The maintainer writes `work on N` and `merge and close N`, with no `#`
and no word *task*. A bare number after a work verb read as a file, a line or a count,
so the skill did not load. Throughout, `N` is the work-item number the tracker issued.

**The phrasing chose the flow, and not the item.** `work on #N` reached the
batch-spawn section, and `implement #N` reached the single spawn. Both phrases mean
the same thing. So the number of workers a spawn produced depended on the words the
maintainer picked, and never on whether the item was a user story or a leaf task.

## The decision

Three parts, and each one removes a question the maintainer had to answer.

1. **A bare work-item number is a work-item reference.** The description carries the
   forms the maintainer types, with and without a `#`. So a work verb plus a number
   loads the skill with no slash command.
2. **The item shape picks the flow.** The session reads the item's labels first. A
   `user-story` parent batch-spawns its unblocked children. A leaf task spawns one
   worker. The maintainer's wording decides nothing.
3. **`merge and close <N>` is a teardown row.** It joins `close <N>` and
   `wrap up <N>` in the close gate table. The explicit ask is the confirmation, so
   nothing asks again.

## Considered Options

- **Trigger on the bare number, then classify the item** (chosen) — the shape is a
  fact on the tracker, and one read resolves it. The two flows already exist, so this
  adds a resolution step and no flow.
- **Keep the slash command as the entry point** (rejected) — the state before this
  ADR. It made the maintainer the router for a decision the tracker already holds.
- **Ask which flow to run** (rejected) — the answer is on the item. A question about
  a readable fact is friction, and it costs a turn on every spawn.
- **Keep one flow and spawn one worker for a `user-story` parent** (rejected) — a
  parent has no diff to write. A worker on a parent then invents children, or it
  implements every child in one worktree.
- **Read the shape from the maintainer's verb** (rejected) — this is the defect. Two
  phrases for one intent produced two different spawns.

## Consequences

- **A wrong classification is visible in one line.** The spawn report already names
  the routed skill, the role, the model and the effort per child
  ([Reporting to the user](../../SKILL.md#reporting-to-the-user)). A batch that needed
  one worker shows as five spawn lines.
- **The tracker read is the one hard stop.** A failed read cannot say whether an item
  is a parent. The session reports the failed read and spawns nothing, because a guess
  spawns the wrong number of workers.
- **A queue question is still not a verb.** `what next` and a bare `/orchestrator`
  resolve to no skill and to no item, so they reach the ready queue unchanged
  (ADR 0014).
- **This narrows no earlier decision.** Verb → skill stays ADR 0014's resolution, and
  work item → `(model, effort)` stays ADR 0005's. Item → flow is a third resolution
  over the same item, and it constrains neither of them.
