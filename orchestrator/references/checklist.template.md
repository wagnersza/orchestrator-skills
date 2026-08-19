<!--
Seed for a worker's .orchestrator/checklist-<item>.md (worktree root, gitignored).
The worker rewrites the boxes as it completes each step; the orchestrator reads
this file to see exact progress and detect a stall (unchecked + idle terminal).
Steps whose recipe field is blank in config are dropped before sending. The
writing-pass box is not one of them: it reads no recipe field, so it stays on every
item.

The last box ends at the review note. The worker writes no work-state label, and it
moves no board card. The orchestrator session writes both, in one call with the removal
of the phase label. See ../docs/adr/0025-the-session-writes-the-review-state.md.
-->

# Checklist — <item>

- [ ] implement + self-test
- [ ] run the prose you changed through the `simple-english` skill in pragmatic mode
      — the markdown in your diff, the strings a Python file prints, your review note,
      and your PR/MR body. Identifiers, paths, commands, code blocks, link targets,
      YAML/JSON keys and proper nouns stay byte-identical. This box binds **per
      commit**. Run the pass before the commit that carries that prose, not before the
      last commit of the item.
- [ ] commit in slices — this box covers a **series** of commits, not one. Commit each
      slice as soon as that slice is complete. Do not wait for the end of the item. One
      slice holds one logical change. The branch is also self-consistent at that commit:
      every cross-reference the commit adds resolves inside the same commit. A trivial
      item is one commit, and that is not a violation.
- [ ] push the branch
- [ ] open the PR/MR (description links back to the work item for the review note + evidence)
- [ ] if a DB gate is configured, satisfy it (back up, migrate, verify schema)
- [ ] capture evidence per the evidence bar (real-data proof + full suite passing)
- [ ] post the review note on the **work item** (What to review / Main changes / How to
      test / Evidence) — cover the substance, no filler sections or redundant summaries.
      **This is the last box. Stop here.** Write no work-state label. Move no board card.
      The orchestrator session writes the review state, in one call with the removal of
      the phase label. That pair names one moment.

Do not end the turn while any box is unchecked. If you catch yourself about to
stop at "next step is …", that's the stall — keep going and actually do it.

The writing-pass box applies to every item, including a pure-code one. Your review
note and your PR/MR body are prose whatever the diff contains, so no item is exempt.

(This file is the **completion contract**, not a verification instruction — it
lists work to *do*, so it isn't the stale scaffolding `prompt-improver` tells you
to strip. Don't add a "re-check your work" or "verify again" box: these models
self-verify, and the instruction only costs tokens.)
