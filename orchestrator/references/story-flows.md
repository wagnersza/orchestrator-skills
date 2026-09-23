# Story flows

What runs between the close of a `user-story` parent's last child and the close of the
parent itself. Two steps, in this order: **the story proof**, then **the layer 5 story
gate**. A failed proof stops there, and the gate never runs. The terms are the **Story
proof**, **Story run** and **Layer** entries in [`../CONTEXT.md`](../CONTEXT.md).

## Parent-close is what is left for you

**The tick closes one item, and it closes no parent.** A **Close transaction** runs
once, on the child that happened to finish last. Apply the parent close after that,
where the tracker conventions define one. **The parent's card needs no move**, because
the board's own built-in workflow answers a closed item, per the **Board status** entry
in [`../CONTEXT.md`](../CONTEXT.md).

The read is *Every child of a parent work item, closed children included*
([`tracker-reads.md`](tracker-reads.md#every-child-of-a-parent-work-item-closed-children-included)).
An open-item list cannot answer this step, because the child that closed last is not in
it.

## The story proof

**The trigger is two facts: the last child's Close transaction completed, and the
parent carries `user-story`.**

**The reachability gate is the one the proof box already uses**: a non-blank
`run_recipe`, or an `evidence` bar that asks for UI proof
([`checklist.template.md`](checklist.template.md)). This step defines no second gate,
so the two can never disagree. Where neither half holds, no story proof runs, and the
parent goes straight to the layer 5 story gate.

Where the gate does hold:

1. **Claim the parent** — the same `tick --claim` command a leaf spawn runs. One label
   swap through the one writer, and no card moves with it.
2. **Spawn the proof worker**, and start or repoint the **Item automation**. The worker
   is fresh, in its own worktree cut from the default branch — the first place every
   child's merged code sits together. **The role is `heavy`.** Resolve its
   `(model, effort)` pair from [`models.md`](models.md), the same as any other spawn.
   The **Item automation** is `orchestrator-item-<parent N>`, and one item never holds
   two schedules: repoint an existing one at the proof worktree, or create one at this
   spawn. Step 8 of the parent's own Close transaction removes it.
3. **The tick reads `implementation-complete` on the parent, and writes `to-review`.**
4. **Read the evidence note and the spec PR** the worker left.
5. **Run the layer 5 story gate below**, and triage every candidate it reports.
6. **The parent already wears `to-review`**, written at step 3, so there is nothing to
   swap here.
7. **The maintainer reads the spec PR, then asks for the close.** No session merges it
   unasked.

**The worker leaves two artifacts.** An evidence note on the parent, one line per user
story of the parent spec, naming which criteria that story exercised. And the generated
Playwright spec, wired into the project's own test command, committed on its own branch
with its own PR. The prompt carries the **Browser surface** scope edge, same as every
other spawn prompt: `playwright-cli` drives the proof, and a browser MCP the worker's
session happens to expose is out of bounds.

**A failed proof stops the parent close.** The worker posts the finding on the parent as
its evidence note, and ticks no last box — a real defect is not a stalled worker. File
each failure through `/to-tickets`, linked to the story that failed. Leave the parent
open at `in-progress`. Run no layer 5 story gate, and report the pending human decision.

## The layer 5 story gate

Run `/improve-codebase-architecture` the moment a user story finishes: after the story
proof, and not where that proof failed. The lane is `inline`
([`skill-routing.md`](skill-routing.md)), so this session invokes it here, in the main
checkout, on the default branch. Hand it the direction to look in, where the maintainer
named one. The skill owns its own report — never restate one of its headings here.

**Save the report before you triage.** The skill writes its HTML to the OS temp
directory, and a reboot deletes it. Copy it to
`docs/refactor-opportunities/<story>-<slug>.html` (`<story>` first, so two stories never
collide), and commit the copy as a docs-only commit on the default branch. The word is
the **Story gate report** entry in [`../CONTEXT.md`](../CONTEXT.md).

**Triage every candidate, in prose:**

- **`Strong`** becomes a work item through `/to-tickets`, wearing `rating:strong` plus
  `refactor`, linked back to the story the gate read and to the saved report.
- **`Worth exploring`** goes to the backlog under no story, wearing `rating:worth-exploring`
  plus `refactor` and the report link, but no parent link.
- **`Speculative`** is dropped, with a one-line reason in the report to the user.

Neither family moves a board card. The threshold this session checks is **0 untriaged
`Strong` candidates**, and not 0 findings — `scripts/close_item.py` never checks it,
because triage is judgement and that seam owns only the judgement-free steps.

**Layer 5 stops nothing.** It holds no exit code, so it fails no push and no merge. A
candidate still untriaged is work to report, never a close this session refuses.
Rationale: [`../docs/adr/0033-the-story-gate-is-advisory.md`](../docs/adr/0033-the-story-gate-is-advisory.md).
