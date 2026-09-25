# The watch and the queue are two seams

[ADR 0064](0064-the-start-gate-reads-two-labelled-sets.md) put six subcommands in
`scripts/worker_state.py`. It chose a reading strategy, and it did not choose a file
boundary. The file then reached 2794 lines with a module docstring of 465 of them, so a
reader met the whole process check before the first statement and the queue algorithm
began at line 1663.

The two halves shared almost nothing. One reads a worktree, a process listing and a git
repository, in eighteen file-system and `subprocess` touches. The other is a graph walk
over one tracker read, and it touches the file system once, to fire the spawn command.
The file also had no internal order: the **Touch set** reader sat in the middle of the
watch region and both its callers were 1200 lines away, and `main()` was 365 lines with
23 argument definitions behind six subparsers.

## The decision

**The watch and the queue are two files, and neither imports the other.**

- `scripts/worker_state.py` is the **Worker watch**. It holds the process check, the
  **Completion signal**, the **Gate record**, the stall, the computed **Position** and the
  transition the tick applies. It serves `ready`, `phase` and `tick`. It keeps its name,
  so every spawn wrapper and every **Item automation** already registered still runs.
- `scripts/worker_queue.py` is the start gate and the queue tick. It holds the gate table,
  the whole tracker-graph walk, the candidate selection and the board report, plus the
  **Touch set** reader and the `## Parent` and `## Blocked by` readers beside it. It serves
  `start`, `queue` and `report`.

**What the two share sits in `scripts/tracker.py`, the Tracker adapter.** Three things
moved there, and each one moved because both files need it and no import
runs between them:

| What moved | Why the adapter holds it |
|---|---|
| the **Work-state label** family and `write_transition` | the watch swaps those four labels on a transition, and the queue writes `needs-human` on a failed spawn. One function still owns every label write. |
| `add_tracker_arguments` and `add_board_arguments` | two `main` functions build one adapter from one set of flag names, so the two can never drift apart on the tracker they read. |
| `UsageExitParser` and `EXIT_USAGE` | a usage error stays outside every seam's exit contract, and the rule has one home. |

`.importlinter` proves the boundary. One `independence` contract says the two never import
each other in either direction, and the adapter still imports none of its callers.

## What this narrows

**It narrows nothing.** [ADR 0018](0018-the-worker-watch-is-a-stateless-seam.md) calls the
watch a stateless seam and [ADR 0022](0022-item-automation-replaces-the-blocking-watch.md)
narrows it to a per-tick predicate. Both hold word for word, because the queue half was
never part of the watch. ADR 0064's rule survives too: `start` and a queue tick still call
one gate function, so the two cannot disagree about one item. That function now lives in
the queue file, and both of its callers live there with it.

[ADR 0040](0040-the-tracker-is-one-adapter-behind-both-seams.md) gains a third caller and
loses no rule. The adapter is still a library and not a seam, and it still imports none of
the files above it.

## Considered Options

- **Two files, with the shared surface in the adapter** (chosen). The boundary is the one
  the call graph already drew, and the shared surface has one home that both sides reach
  with no edge between them.
- **Two files, with the queue importing the watch** (rejected). It is one directed edge
  and it looks cheap. It also means a queue change reads a file full of process-check
  vocabulary to find one label writer, which is the cost this decision removes.
- **Two new files, and `worker_state.py` deleted** (rejected). Every **Item automation**
  and every spawn wrapper stores a literal path to that file. Deleting it breaks every
  live schedule at the moment of the merge, and it buys only a tidier name.
- **Duplicate the label writer in each file** (rejected). ADR 0018 requires that one
  function owns every work-state label swap, so that no second read can disagree with the
  first. Two copies is exactly the drift that rule exists to stop.

## Consequences

- **A queue change touches one file with no process-check vocabulary in it**, and a stall
  change touches one file with no story-tree vocabulary in it. Each `--help` carries three
  subcommands instead of six.
- **The queue suite needs no worktree, no git repository and no agent process.** It builds
  one tracker fixture file, so 59 cases run in about 6 seconds. The watch suite keeps the
  slow fixtures, because the process check is what makes it credible. Two source
  invariants in `scripts/test_worker_queue.py` hold that line: the queue file starts one
  subprocess, and it names no `git`, `ps` or `lsof` command.
- **One stored command changes.** The `orchestrator-queue` schedule's `--precheck` names
  `scripts/worker_queue.py queue`. Every **Item automation** names `tick` and every spawn
  wrapper names `ready` and `tick --claim`, so all of those are untouched.
- **`scripts/spawn_item.py` reads two label constants from the adapter** instead of from
  the watch. It still calls `worker_state.ready`, `worker_state.live_process`,
  `worker_state.checklist_path` and `worker_state.claim`, so the spawn's seven steps do not
  move.
