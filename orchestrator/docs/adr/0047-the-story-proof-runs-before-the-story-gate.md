# The story proof runs before the story gate

Layers 1 to 4 each read one **Work item**, inside one worker worktree. A user story
finishes when its last child closes, and every child was green on its own. So ten green
children can leave a feature that does not work as one flow. The login item passes, the
cart item passes, the checkout item passes, and a user still cannot buy anything.

A `phase:e2e` proof already exists, and it reads one work item in one worker worktree. So
it proves one slice. The layer 5 story gate is the only step that reads a whole story
([ADR 0033](0033-the-story-gate-is-advisory.md)). It reads the shape of the code rather
than the behaviour, and it is advisory. So a story can close with an opinion about its
modules and no proof that a user can use it.

Nothing durable holds the proof for a story either. Each child's evidence sits in its own
review note, against its own diff. Nobody can point at one artifact and say that a finished
story works.

## The decision

**The Orchestrator proves a whole user story before it closes the parent.** The term is the
**Story proof** entry of [`orchestrator/CONTEXT.md`](../../CONTEXT.md).

**The trigger is the close of the last child of a `user-story` parent.** The
**Orchestrator** writes `in-progress` and `phase:e2e` on the parent, in one call. Then it
spawns one fresh **Worker**, in its own worktree, cut from the default branch. That
worktree holds every child's merged code together, which no child's worktree ever did. A
fresh session also carries no child worker's context and no leftover state.

**The proof drives the declared Browser surface, `playwright-cli`, and nothing else.** It
boots the app per the **Project recipe**, and it walks every user story of the parent spec
([ADR 0012](0012-playwright-cli-is-the-only-browser-surface.md)).

**The proof runs before `/improve-codebase-architecture`.** An architecture opinion about a
story that does not work is premature. Layer 5 asks which module is too shallow, and it
costs minutes. That question has no value while the feature is broken. So the story proof
is first and layer 5 is second, in the layer model that
[`orchestrator/references/quality-gates.md`](../../references/quality-gates.md) holds.

**A failed proof stops the parent close.** This step can block where layer 5 cannot. The
reason is the kind of answer each one gives. A pass or a fail is a fact, and depth is a
judgement. A **Gate** is one command with one exit code, and a judgement has none. So the
parent stays open, with `phase:e2e` in place. The session files each failure as a work
item, runs no layer 5, and names the pending human decision.

**The proof leaves two durable artifacts.** They are the whole record of the run:

1. **An evidence note on the parent work item.** It holds the run output, the screenshots,
   and one line per user story that says which criteria it exercised.
2. **The generated Playwright spec, committed on its own branch, in a PR.** The same
   **Commit slice** wires that spec into the project's own test command. So the proof
   becomes a regression test instead of a transcript that dies with the worktree. The
   maintainer reviews that PR, and no session merges it unasked
   ([ADR 0016](0016-the-orchestrator-merges-when-asked.md)).

## The parent wears `phase:e2e`, so no new machinery exists

**`scripts/worker_state.py` is not changed.** The parent story item wears the `phase:e2e`
label that a leaf proof already uses. So every branch of the **Worker watch** that reads
that phase applies with no edit:

- The **Completion signal** is shape 1, a fully ticked **Checklist**, plus a green **Gate
  record** line for every required layer at `HEAD`
  ([ADR 0036](0036-a-gate-run-is-work-product.md)).
- The outcome is `proof-complete`, which already reaches `phase:e2e` alone.
- `gates-unproven`, `stalled` and `dead` already reach `phase:e2e` too.

The `--item` flag carries the parent's number, and the `--worktree`, `--process` and
`--marker-dir` flags carry the proof worktree. All four are arguments today, because a
schedule already follows the live worker
([ADR 0026](0026-the-automation-follows-the-live-worker.md)). So the proof reuses the
`orchestrator-item-<parent N>` **Item automation**, with its precheck repointed.

**No new outcome, no new label string, no new exit code and no new config field exists.**
`run_recipe`, `ports`, `db_gate` and `evidence` hold everything the proof needs, and the
`gates:` block is untouched. **The reachability gate is the one that already exists**: a
non-blank `run_recipe`, or an `evidence` bar that asks for UI proof. The story proof takes
that same gate and defines no second one, so the two can never disagree. This repo is the
blank case, so no story here reaches a story proof.

## What this narrows

- **[ADR 0021](0021-phase-is-a-second-label-family.md).** It said a `phase:*` label marks
  which part of an owned run a work item is in. A `phase:*` label now also marks a parent
  story under proof. Every other property of the family holds: three values, mutually
  exclusive inside the family, worn beside the work-state label.
- **[ADR 0033](0033-the-story-gate-is-advisory.md).** It put layer 5 at the close of the
  last child. Layer 5 now runs second, after the story proof. It keeps every other property
  it has. It is a step and never a **Gate**, its threshold is 0 untriaged `Strong`
  candidates, and it stops nothing.
- **[ADR 0009](0009-labels-drive-board-status.md) needs no edit.** **Board status** still
  derives from the **Work-state labels** alone. So the parent's phase label moves no card,
  and the derivation table stays as written.

## Considered Options

- **A blocking proof of the whole story, in a fresh worktree, before layer 5** (chosen) —
  one run reads every child's merged code, and a story that fails it never reads as done.
  The cost is one more worker per story, on the machinery that already exists.
- **A `story-proof-complete` outcome, with a `phase:story-e2e` label** (rejected) — it
  reads better in a log, and it costs new code, new tests, and a second path that can
  disagree with the first. The item number already says whether a leaf or a parent is under
  proof.
- **A layer 6 row in the layer model** (rejected) — the layer numbers read as a run order,
  and this step runs before layer 5. A row numbered 6 that runs before 5 misleads every
  reader.
- **Renumber the architecture layer to 6** (rejected) — it churns every link and every
  table row for a number, and the numbering is the only thing it corrects.
- **An advisory proof that never blocks** (rejected) — a pass or a fail needs no judgement
  call, so an advisory answer throws away what the run knows. It also leaves a broken story
  on the same path as a working one, which is the fault this decision closes.
- **A proof inside one child's worktree** (rejected) — that branch holds one child's code,
  which is what the leaf `phase:e2e` proof already reads. The whole point is every child's
  merged code in one tree. That worktree also carries its own worker's context and leftover
  state.
- **A `story_proof_cmd` config field** (rejected) — the **Commit slice** that adds the
  generated spec also wires it into the project's own test command. So the existing gate
  commands run it, and its own run needs no second name.

## Consequences

- **Enforcement is documentary, the same as the rest of this repo.** No hook and no script
  runs the proof, and nothing refuses a parent close that skipped it. The trigger prose and
  the report to the maintainer are the whole guard
  ([ADR 0032](0032-quality-gates-are-a-layered-contract.md)).
- **A Story run holds its Story slot through the proof.** The run ends when the parent
  closes, so a story with every child merged still occupies one slot while its proof runs.
- **Accepted risk: a proof worker can write a shallow spec.** A Playwright spec that
  asserts a page title proves little. Two things mitigate it, and neither is a mechanism.
  The evidence note asks for one line per user story, and a human reviews the spec PR.
- **Accepted risk: the two HTML overview docs can drift.** `scripts/test_links.py` walks
  `*.md` only, so nothing checks a link or an anchor in `docs/architecture.html` or
  in `docs/skill-state-and-roadmap.html`. A reader must read both by hand. A
  Markdown-plus-HTML link walk is work of its own.
- **This ADR declares the step and wires nothing.** The flow in
  [`orchestrator/SKILL.md`](../../SKILL.md), the paragraph in the layer model, and the
  label row in the tracker config are separate work. No story runs a proof until they land.
