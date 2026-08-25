# Parallel spawn is gated on a declared touch set

[ADR 0037](0037-the-merge-queue-is-an-ordered-train.md) ranks a **Merge queue** by how many
changed files each branch shares with the others, and the ranking reads real branches. So it
answers at merge time, when the code exists.

The `work on N` flow spawns every unblocked child of a story at once. Two children that
change one file then produce two branches that fight over it, and the train parks one of
them. The park costs a human a conflict resolution that never had to happen. A branch does
not exist before a spawn, so the merge-time ranking cannot answer at spawn time.

## The decision

**A work item can declare a Touch set, and the queue tick spawns two items in parallel only
where their touch sets are disjoint.**

- **A Touch set is a `## Touches` block on the work item.** It holds paths or globs, one per
  line, in the same shape as the `## Blocked by` and `## Parent` edges the item already
  carries.
- **The session that creates the items writes it.** `/to-spec`, `/to-tickets` and `/triage`
  run inline in the **Orchestrator** session, so the block goes in with the body. The
  external template that `to-tickets` ships is not edited and not forked
  ([ADR 0028](0028-drop-the-fork-and-pin-dial.md)). The maintainer can edit the block
  afterwards, on the tracker.
- **One config field turns the comparison on: `parallel_check`.** With `touches`, the tick
  compares the sets, and an item with no `## Touches` block is spawned alone. With `off`,
  the tick compares nothing and spawns every unblocked child, which is the behaviour today.
- **An overlap delays a spawn, and never cancels one.** The tick spawns the lower-numbered
  item and leaves the other ready. The next tick that finds a free slot and no live overlap
  spawns it.
- **A Touch set is a declaration, and not a constraint.** Nothing stops a worker from
  editing a file the block does not name, and no gate checks the diff against it. The
  test-merge inside `scripts/merge_train.py` stays the real check, the same way ADR 0037
  already treats file overlap as a cheap proxy.

## Considered Options

- **A declared touch set, config-gated** (chosen) — the one source that knows the answer
  before the code exists is the person or session that wrote the ticket. Writing it down
  costs one block, and it is readable and editable by both.
- **An agent reads both bodies and judges the overlap** (rejected) — it puts an agent back
  in the middle of the loop, which the label-driven design exists to remove. It also spends
  tokens on every tick that has two candidates.
- **Serialise inside a story, parallelise across stories** (rejected) — it needs no new
  field, and it is wrong for this repo. Two children of one story are often an ADR and a
  reference file, which never collide. This option serialises them and gives up the
  parallelism the story cap was raised for.
- **Derive the paths from the title and body with a heuristic** (rejected) — a guess
  presented as a fact. A wrong guess spawns two colliding branches and reports success,
  which is the failure class this repo names in
  [ADR 0034](0034-the-seam-invocation-carries-a-resolved-plugin-root.md).
- **Fork the `to-tickets` template to add the block** (rejected) — ADR 0028 dropped the
  fork-and-pin dial. An inline session that appends the block reaches the same result and
  forks nothing.
- **No gate: let the train park the loser** (rejected) — this is today, and it is what the
  maintainer asked to change. A park is cheap for the machine and expensive for the human,
  because step 1 of a **Close transaction** stays in prose.

## Consequences

- **A missing block costs parallelism, and never correctness.** Under `touches` an
  undeclared item runs alone. So a repo that fills no blocks runs one worker at a time, and
  `parallel_check: off` is the escape.
- **A wrong block costs one park.** The declaration can be wrong in both directions. Two
  items declared disjoint that in fact collide are parked by the train, exactly as today.
  So this gate removes parks and never introduces a wrong merge.
- **The gate is advisory in the same sense as the story gate**
  ([ADR 0033](0033-the-story-gate-is-advisory.md)). It shapes what starts. It blocks no
  push, rejects no commit and fails no build.
- **The comparison belongs to a seam.** Path and glob matching is a `fnmatch` compare over
  two lists, so it is a tested function and not a judgement.
- **This ADR records the decision and wires nothing.** The `## Touches` block, the compare
  in the queue tick, and the `parallel_check` field are each separate work.
