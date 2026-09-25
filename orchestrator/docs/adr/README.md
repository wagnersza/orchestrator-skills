# The ADR ledger

Every decision this repo has recorded, by number. A row gives the subject, and the later
decision that reversed or narrowed that subject where one exists. The older file carries
the same pointer in its own preamble, so a reader who opens that file is told there too.
`scripts/test_links.py` holds the two halves together: a row with no pointer behind it
fails the suite, and so does a pointer with no row.

An unused number gets a row as well. So a gap in the sequence reads as void, and never as
a file somebody deleted.

Read a row as a signpost and never as a verdict. A narrowed ADR is still the record of the
decision it made, and every file keeps the text it was written with.

| ADR | Subject | Changed by |
| --- | --- | --- |
| [0001](0001-tool-harness-model-layering.md) | Tool / Harness / Model layering, abstracted by reference-per-variant | — |
| [0002](0002-delegate-tracker-to-mattpocock-skills.md) | Delegate tracker config to the mattpocock engineering skills | narrowed by [0009](0009-labels-drive-board-status.md), narrowed by [0039](0039-a-tracker-read-has-a-verified-command-in-the-skill.md), narrowed by [0040](0040-the-tracker-is-one-adapter-behind-both-seams.md), narrowed by [0065](0065-the-parent-edge-is-two-representations.md) |
| [0003](0003-cross-vendor-adversarial-review.md) | Cross-vendor adversarial review, bounded at 3 rounds | narrowed by [0016](0016-the-orchestrator-merges-when-asked.md), narrowed by [0066](0066-review-and-the-train-are-verbs.md) |
| [0004](0004-file-based-checklist.md) | File-based checklist instead of claude-only TodoWrite | — |
| [0005](0005-role-based-model-and-effort.md) | Role-based model + effort, not a hardcoded model | reversed by [0059](0059-medium-is-the-default-role.md) |
| [0006](0006-delegate-prompting-to-prompt-improver.md) | Delegate prompt composition to the prompt-improver skill | — |
| [0007](0007-fork-and-pin-skill-dependencies.md) | Fork each declared skill dependency and pin the fork's default branch | superseded by [0028](0028-drop-the-fork-and-pin-dial.md), narrowed by [0011](0011-delegate-technical-writing-to-simple-english.md) |
| [0008](0008-diff-targeted-run-budget.md) | A sync spends at most 5 worker runs, targeted by the diff | superseded by [0028](0028-drop-the-fork-and-pin-dial.md) |
| [0009](0009-labels-drive-board-status.md) | Labels drive the board; Projects v2 Status is a derived projection | superseded by [0054](0054-the-board-is-an-input-not-a-mirror.md), narrowed by [0045](0045-a-story-start-is-automatic-under-two-roofs.md) |
| 0010 | Void. Never used, and no file ever carried this number. | |
| [0011](0011-delegate-technical-writing-to-simple-english.md) | Delegate technical writing to the simple-english skill, and narrow the fork set | — |
| [0012](0012-playwright-cli-is-the-only-browser-surface.md) | playwright-cli is the only sanctioned browser surface for a worker | — |
| [0013](0013-workers-commit-in-contextualised-slices.md) | A worker commits in contextualised slices, and this repo owns the rule | narrowed by [0025](0025-the-session-writes-the-review-state.md) |
| [0014](0014-route-verbs-to-skills-in-two-lanes.md) | A verb resolves to a skill, in one of two lanes | narrowed by [0016](0016-the-orchestrator-merges-when-asked.md) |
| [0015](0015-close-is-a-deterministic-transaction.md) | Closing an item is a deterministic transaction, and code owns its order | narrowed by [0040](0040-the-tracker-is-one-adapter-behind-both-seams.md), narrowed by [0057](0057-the-merge-is-the-second-act.md) |
| [0016](0016-the-orchestrator-merges-when-asked.md) | The orchestrator merges and closes when the maintainer asks it to | superseded by [0057](0057-the-merge-is-the-second-act.md), narrowed by [0037](0037-the-merge-queue-is-an-ordered-train.md) |
| [0017](0017-gate-worker-readiness-on-a-process-check.md) | A readiness gate holds the first prompt, and a process check is its signal | narrowed by [0019](0019-readiness-is-a-tool-agnostic-process-check.md) |
| [0018](0018-the-worker-watch-is-a-stateless-seam.md) | The Worker watch is a stateless seam, and every action stays in the session | narrowed by [0022](0022-item-automation-replaces-the-blocking-watch.md), narrowed by [0023](0023-the-stall-count-is-a-tracker-comment.md), narrowed by [0058](0058-one-re-prompt-then-a-human.md), narrowed by [0063](0063-the-stall-window-starts-at-the-spawn.md) |
| [0019](0019-readiness-is-a-tool-agnostic-process-check.md) | Readiness is one tool-agnostic process check, not a command per tool | — |
| 0020 | Void. Never used, and no file ever carried this number. | |
| [0021](0021-phase-is-a-second-label-family.md) | Phase is a second label family, not a second state machine | superseded by [0053](0053-one-work-state-label-and-a-computed-position.md), narrowed by [0025](0025-the-session-writes-the-review-state.md), narrowed by [0047](0047-the-story-proof-runs-before-the-story-gate.md) |
| [0022](0022-item-automation-replaces-the-blocking-watch.md) | An Item automation replaces the blocking watch, and the seam becomes a predicate | narrowed by [0024](0024-the-wake-target-is-a-resolved-handle.md), narrowed by [0027](0027-the-tick-delivers-its-own-wake.md), narrowed by [0063](0063-the-stall-window-starts-at-the-spawn.md) |
| [0023](0023-the-stall-count-is-a-tracker-comment.md) | The stall count is a tracker comment, and no session remembers it | superseded by [0058](0058-one-re-prompt-then-a-human.md) |
| [0024](0024-the-wake-target-is-a-resolved-handle.md) | The wake target is a terminal handle, resolved at spawn | superseded by [0056](0056-the-tick-applies-the-transition-it-computed.md), narrowed by [0027](0027-the-tick-delivers-its-own-wake.md) |
| [0025](0025-the-session-writes-the-review-state.md) | The orchestrator session writes the review state, and the worker stops at its note | superseded by [0056](0056-the-tick-applies-the-transition-it-computed.md), narrowed by [0051](0051-a-hook-refuses-and-a-seam-performs.md) |
| [0026](0026-the-automation-follows-the-live-worker.md) | The Item automation follows the live worker, and one per item stands | superseded by [0056](0056-the-tick-applies-the-transition-it-computed.md), narrowed by [0063](0063-the-stall-window-starts-at-the-spawn.md) |
| [0027](0027-the-tick-delivers-its-own-wake.md) | The tick delivers its own wake, so no agent runs on a tick | superseded by [0056](0056-the-tick-applies-the-transition-it-computed.md) |
| [0028](0028-drop-the-fork-and-pin-dial.md) | Drop the fork-and-pin dial, and take upstream drift as it comes | — |
| [0029](0029-a-work-item-number-is-a-complete-instruction.md) | A verb plus a work-item number is a complete instruction | — |
| 0030 | Void. `0030-preflight-skill-reachability-before-routing.md` held a preflight before every route. [ADR 0031](0031-setup-unblocks-the-routed-skills.md) reverted the file and every change it made, and the number stays unused. | |
| [0031](0031-setup-unblocks-the-routed-skills.md) | Setup unblocks the routed skills | — |
| [0032](0032-quality-gates-are-a-layered-contract.md) | Quality gates are a layered contract | — |
| [0033](0033-the-story-gate-is-advisory.md) | The story gate is advisory | narrowed by [0047](0047-the-story-proof-runs-before-the-story-gate.md), narrowed by [0048](0048-the-story-gate-report-is-a-repo-artifact.md) |
| [0034](0034-the-seam-invocation-carries-a-resolved-plugin-root.md) | The seam invocation carries a resolved plugin root | superseded by [0051](0051-a-hook-refuses-and-a-seam-performs.md) |
| [0035](0035-workers-delegate-to-sub-agents-under-a-cap.md) | Workers delegate to sub-agents, under a cap of 5 at once | — |
| [0036](0036-a-gate-run-is-work-product.md) | A gate run is work product | superseded by [0052](0052-a-gate-blocks-and-a-hook-writes-its-record.md) |
| [0037](0037-the-merge-queue-is-an-ordered-train.md) | The merge queue is an ordered train a session runs | narrowed by [0053](0053-one-work-state-label-and-a-computed-position.md), narrowed by [0057](0057-the-merge-is-the-second-act.md), narrowed by [0066](0066-review-and-the-train-are-verbs.md) |
| [0038](0038-the-to-merge-column-is-intent.md) | The To merge column is intent, for one column and in one direction | superseded by [0054](0054-the-board-is-an-input-not-a-mirror.md) |
| [0039](0039-a-tracker-read-has-a-verified-command-in-the-skill.md) | A tracker read has one verified command, and it lives in the skill | — |
| [0040](0040-the-tracker-is-one-adapter-behind-both-seams.md) | The tracker is one adapter behind both seams | narrowed by [0057](0057-the-merge-is-the-second-act.md), narrowed by [0065](0065-the-parent-edge-is-two-representations.md), narrowed by [0069](0069-the-adapter-orders-a-multi-write-close.md), narrowed by [0071](0071-the-watch-and-the-queue-are-two-seams.md) |
| 0041 | Void. Never used, and no file ever carried this number. | |
| 0042 | Void. Never used, and no file ever carried this number. | |
| 0043 | Void. Never used, and no file ever carried this number. | |
| 0044 | Void. Never used, and no file ever carried this number. | |
| [0045](0045-a-story-start-is-automatic-under-two-roofs.md) | A story start is automatic, under two roofs | narrowed by [0061](0061-the-board-is-read-before-the-label.md), narrowed by [0053](0053-one-work-state-label-and-a-computed-position.md), reversed by [0062](0062-a-story-card-authorises-its-run.md), narrowed by [0068](0068-an-item-writing-flow-writes-the-start-label.md) |
| [0046](0046-parallel-spawn-is-gated-on-a-declared-touch-set.md) | Parallel spawn is gated on a declared touch set | — |
| [0047](0047-the-story-proof-runs-before-the-story-gate.md) | The story proof runs before the story gate | narrowed by [0053](0053-one-work-state-label-and-a-computed-position.md), narrowed by [0056](0056-the-tick-applies-the-transition-it-computed.md) |
| [0048](0048-the-story-gate-report-is-a-repo-artifact.md) | The story gate report is a repo artifact | — |
| [0049](0049-infra-gates-are-policy-on-the-plan.md) | Infra gates are policy on the plan | — |
| [0050](0050-a-standalone-item-bumps-a-patch.md) | A standalone item bumps a patch, and the story sets the level | — |
| [0051](0051-a-hook-refuses-and-a-seam-performs.md) | A hook refuses, and a seam performs | narrowed by [0055](0055-the-label-denial-reads-its-caller.md), reversed by [0060](0060-the-manifest-names-no-standard-hook-file.md) |
| [0052](0052-a-gate-blocks-and-a-hook-writes-its-record.md) | A gate blocks, and a hook writes its record | — |
| [0053](0053-one-work-state-label-and-a-computed-position.md) | One work-state label, and the position is computed | narrowed by [0068](0068-an-item-writing-flow-writes-the-start-label.md) |
| [0054](0054-the-board-is-an-input-not-a-mirror.md) | The board is an input, not a mirror | reversed by [0067](0067-the-board-is-a-mirror-at-three-moments.md) |
| [0055](0055-the-label-denial-reads-its-caller.md) | The label denial reads its caller | — |
| [0056](0056-the-tick-applies-the-transition-it-computed.md) | The tick applies the transition it computed | — |
| [0057](0057-the-merge-is-the-second-act.md) | The merge is the second act, and nothing is typed | — |
| [0058](0058-one-re-prompt-then-a-human.md) | One re-prompt, then a human | — |
| [0059](0059-medium-is-the-default-role.md) | Medium is the default Role, and every other Role needs a named signal | — |
| [0060](0060-the-manifest-names-no-standard-hook-file.md) | The manifest names no standard hook file | — |
| [0061](0061-the-board-is-read-before-the-label.md) | The board is read before the label, so only a card in the start column reports a gap | narrowed by [0064](0064-the-start-gate-reads-two-labelled-sets.md), narrowed by [0062](0062-a-story-card-authorises-its-run.md) |
| [0062](0062-a-story-card-authorises-its-run.md) | A story card authorises its run, and a child label starts the work | — |
| [0063](0063-the-stall-window-starts-at-the-spawn.md) | The stall window starts at the spawn, so a fresh worker is never stalled | — |
| [0064](0064-the-start-gate-reads-two-labelled-sets.md) | The start gate reads two labelled sets, and the whole board is a report | narrowed by [0071](0071-the-watch-and-the-queue-are-two-seams.md) |
| [0065](0065-the-parent-edge-is-two-representations.md) | The parent edge is two representations, and the child read unions both | — |
| [0066](0066-review-and-the-train-are-verbs.md) | Adversarial review and the merge train are verbs | — |
| [0067](0067-the-board-is-a-mirror-at-three-moments.md) | The board is a mirror, and a seam writes the card at three moments | narrowed by [0070](0070-a-board-column-is-a-card-or-a-scoped-label.md) |
| [0068](0068-an-item-writing-flow-writes-the-start-label.md) | An item-writing flow writes `ready-for-agent`, and the drag stays the authorisation | — |
| [0069](0069-the-adapter-orders-a-multi-write-close.md) | The adapter orders a multi-write close | — |
| [0070](0070-a-board-column-is-a-card-or-a-scoped-label.md) | A board column is a card on one tracker and a scoped label on the other | — |
| [0071](0071-the-watch-and-the-queue-are-two-seams.md) | The watch and the queue are two seams | — |
