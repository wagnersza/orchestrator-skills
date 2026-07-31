<!--
Seed for a worker's .orchestrator/checklist-<item>.md (worktree root, gitignored).
The worker rewrites the boxes as it completes each step; the orchestrator reads
this file to see exact progress and detect a stall (unchecked + idle terminal).
Steps whose recipe field is blank in config are dropped before sending.
-->

# Checklist — <item>

- [ ] implement + self-test
- [ ] commit
- [ ] push the branch
- [ ] open the PR/MR (description links back to the work item for the review note + evidence)
- [ ] if a DB gate is configured, satisfy it (back up, migrate, verify schema)
- [ ] capture evidence per the evidence bar (real-data proof + full suite passing)
- [ ] post the review note on the **work item** (What to review / Main changes / How to test / Evidence) — cover the substance, no filler sections or redundant summaries
- [ ] flip the work item to the review state

Do not end the turn while any box is unchecked. If you catch yourself about to
stop at "next step is …", that's the stall — keep going and actually do it.

(This file is the **completion contract**, not a verification instruction — it
lists work to *do*, so it isn't the stale scaffolding `prompt-improver` tells you
to strip. Don't add a "re-check your work" or "verify again" box: these models
self-verify, and the instruction only costs tokens.)
