# Reporting to the user

An orchestrator session runs long and the user reads it between other work. They
cannot hold "#38 is at checklist 4 of 7" across turns, so every report restates it.
Shape output for acting on, not for completeness.

- **Lead with state, not narration.** First line is the board: what changed and what's
  running. `#38 38-b5-contacts spawned · /implement · heavy · opus-5 · high. 2 workers
  live.` Never open with what you're about to do.
- **Name the skill you routed to.** A verb resolved through
  [`skill-routing.md`](skill-routing.md) names its skill in the lead line, in the same
  turn the skill ran. A wrong route then costs one sentence to correct.
  `/to-spec ran here. Spec is #47, labelled ready-for-agent.` Where no skill was routed
  to — an unmapped verb the user declined, or a session that cannot reach the skill —
  say that instead.
- **A spawn line carries four fields, in this order:** the routed skill, the role, the
  model, the effort — `#23 → /implement · heavy · opus-5 · high`. A batch-spawn reports
  the four fields **per child**, so a mixed batch shows two different skills.
- **Restate the position every turn, and carry the progress with it.** A worker's
  progress is `implementation · checklist 4/7`. The position is computed, so read it
  the way the seam does: the work-state label, and then the checklist file for the
  progress beside it.
- **A tick report names the outcome and the transition the tick applied.** The outcome
  is the tick's own word — `implementation-complete`, `gates-unproven`, `merged`,
  `dead`, `stalled` or `unreadable` — then the label the tick wrote, then what you did.
  `#38 implementation-complete · in-progress → to-review.` Read the swap off the item,
  and never write one yourself.
- **A story-proof line names the parent and the two artifacts.**
  `#57 story proof · evidence note on #57 · spec PR #64.`
- **The retry count comes from the tracker, so restate it.**
  `#38 stalled in implementation · checklist 4/7 · retry 1 of 1. Context reset,
  re-prompted with the unticked steps.` On the second stall the tick already wrote
  `needs-human`: `#38 stalled again · needs-human written. Read its comment and take
  the item back.` On `dead` the next step is a teardown — name it as the pending human
  decision.
- **Say that the tick writes the label, and that you do not.** `#38 tick: applies the
  transition.`
- **Name the panel on the spawn line**, and say when it or the tick is unavailable — a
  tool that records operation 7, 11 or 12 as unsupported gets no follow-along tab and no
  automation. Point at the four [Monitor workers](../SKILL.md#monitor-workers) bullets,
  and run `tick` by hand there instead of writing a label, with the same flags the
  precheck would have carried.
- **One table or list, capped at 5 rows.** More than 5 ready items or 5 findings → rank
  and split (`start now` vs `blocked`, `must-fix` vs `noted`).
- **End with one action the user can take now.** `Spawn #41 next?` /
  `#38's MR is green — merge it and the tick closes #38.` The merge is the only human
  step left in the second act, so name it where it is pending.
- **A close report names which steps ran and which refused** (below), and ends with the
  one action left. `#20: steps 4 to 7 ran, and step 6 refused. Cause: the worktree holds
  src/api.ts. Commit it or stash it, clear needs-human, and the next tick finishes the
  close.`
- **A train report names the order the seam planned**, what parked and why, and ends
  with the one action left — the close-report shape, once per train instead of once per
  item. `#152 #153 in that order, ready to merge. #151 parked: orchestrator/SKILL.md
  conflicts. Resolve it in 151-merge-train first.`
- **Matter-of-fact failures.** Location, cause, fix — no "uh oh", no apology.
- **Finish the item before raising the next.** A second problem noticed mid-flow goes
  at the end as its own one-line offer, not inline.
- **No preamble, no recap, no closer.** The checklist and the tracker are the record.

**These reports are a Prose deliverable too** — the fourth class in the **Prose
deliverable** entry of [`../CONTEXT.md`](../CONTEXT.md). Apply `simple-english` in
pragmatic mode to what you write here. Keep the untouchables byte-identical: a slug, a
model id, a label name, an effort string and a command stay exactly as they are.

Break this when the user asks you to **explain** a routing or review decision (answer
in full), or before a **destructive** step — a teardown confirmation and a refusal
reason are spelled out, never compressed.

## Answering a close or status question

**There is nothing to run here.** A close is what one tick does when the pull request
for an item's branch reads `MERGED`. The maintainer merges on the tracker, and the next
tick closes the item, removes the worktree and removes the automation. No verb starts a
close, and no label authorises one.

So *merge and close N*, *close N*, *it's done* and *wrap up \<slug\>* are questions.
Read the item and its pull request, then answer in one line:

| What you read | The one-line answer |
|---|---|
| the pull request is merged, and the item is closed | it closed on a tick, and that tick's line carries the plan |
| the pull request is merged, and the item is open | the next tick closes it, inside a minute |
| the pull request is open | merge it on the tracker, and the close follows by itself |
| the item wears `needs-human` | quote the comment on the item, and stop |
| there is no pull request | no worker opened one, so read the outcome instead (`scripts/worker_state.py --help`) |

**Never merge for the maintainer, and never run `scripts/close_item.py` by hand.** That
seam runs inside the tick, in the process that already read the item. A refused close
writes `needs-human` and stops; the comment names the reason, and a repair takes two
ticks (implementation re-proves the finish, then the merge closes it).
