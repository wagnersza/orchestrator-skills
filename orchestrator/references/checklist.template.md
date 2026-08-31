<!--
Seed for a worker's .orchestrator/checklist-<item>.md (worktree root, gitignored).
The worker rewrites the boxes as it completes each step; the orchestrator reads
this file to see exact progress and detect a stall (unchecked + idle terminal).
Steps whose recipe field is blank in config are dropped before sending. A gate box
drops on the same rule: a layer whose command is blank in the `gates:` block of config
loses its box. The writing-pass box is not one of them: it reads no recipe field, so it
stays on every item. The layer model, with a command and a budget for each layer, is in
quality-gates.md.

The proof box drops on that same rule, and `run_recipe` is the field it reads. So
"every box ticked" already covers the browser proof, and the tick needs no separate
proof signal. `orchestrator-skills` has a blank `run_recipe`, so no item in that repo
grows a proof box.

This file carries no Markdown link. The orchestrator copies it into a worker's own
worktree, where a relative path out of this directory resolves to nothing.

The last box ends at the review note. The worker writes no work-state label, and it
moves no board card. The orchestrator session writes the label, and nothing writes a card.
See ../docs/adr/0025-the-session-writes-the-review-state.md
and ../docs/adr/0054-the-board-is-an-input-not-a-mirror.md.
-->

# Checklist — <item>

- [ ] implement + self-test
- [ ] gate layer 1, static — run `make quick` (`gates.quick` in config) after each edit.
      A non-zero exit is a stop, and there is no warning state.
- [ ] gate layer 2, tests and caps — run `make quick` (`gates.quick` in config) before
      each commit. A non-zero exit is a stop, and there is no warning state.
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
- [ ] gate layer 3, whole repo — run `make full` (`gates.full` in config) before the
      push. A non-zero exit is a stop, and there is no warning state.
- [ ] push the branch
- [ ] open the PR/MR (description links back to the work item for the review note + evidence)
- [ ] if a DB gate is configured, satisfy it (back up, migrate, verify schema)
- [ ] gate layer 4, deep — when the PR/MR is open, run `make deep` (`gates.deep` in
      config). A non-zero exit is a stop, and there is no warning state.
- [ ] prove the feature works through the browser surface — boot the app per `run_recipe`
      on this item's `ports`. Then drive `playwright-cli` through every user story on the
      work item. Save the Playwright code it emits. Then stop the app. `playwright-cli`
      is the one sanctioned surface, because its output is code a later test can keep. A
      browser MCP your session happens to expose is not that surface, whichever one it
      is.
- [ ] capture evidence per the evidence bar (`make deep` green + real-data proof). Paste
      the `make deep` summary under Evidence in the review note.
- [ ] post the review note on the **work item** (What to review / Main changes / How to
      test / Evidence) — cover the substance, no filler sections or redundant summaries.
      **This is the last box. Stop here.** Write no work-state label. Move no board card.
      The orchestrator session writes the review state, because one session owns that
      swap.

Do not end the turn while any box is unchecked. If you catch yourself about to
stop at "next step is …", that's the stall — keep going and actually do it.

The writing-pass box applies to every item, including a pure-code one. Your review
note and your PR/MR body are prose whatever the diff contains, so no item is exempt.

(This file is the **completion contract**, not a verification instruction — it
lists work to *do*, so it isn't the stale scaffolding `prompt-improver` tells you
to strip. Don't add a "re-check your work" or "verify again" box: these models
self-verify, and the instruction only costs tokens.)
