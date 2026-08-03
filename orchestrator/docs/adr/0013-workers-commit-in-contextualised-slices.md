# A worker commits in contextualised slices, and this repo owns the rule

A worker finished a work item and landed the whole thing as one commit. The PR then
carried a single blob, in one step with one message: an ADR, a vocabulary entry,
three reference edits and a manifest bump. `git log` on the branch told the
maintainer nothing that the diff did not already show. A bisect over the branch had
one step, so it located nothing. A worker that stalled halfway left its finished work
uncommitted, and that work died with the worktree.

A worker now commits in **slices**. One slice is one logical change, with a message
that says what the change does and why. The worker commits a slice as soon as that
slice is complete, and it does not wait for the end of the item. A four-part item
arrives as four commits, in the order the worker built them, and each commit is
readable on its own. The maintainer can approve one decision and question its
application as two things, and can revert one wrong slice and keep the rest.

Two conditions define a slice, and both are necessary. The commit holds one logical
change. The branch is self-consistent at that commit, which means every
cross-reference in the commit resolves within the commit. The second condition exists
because a dangling cross-reference is this repo's main failure mode.

So a reference file and the link target it adds are one slice, never two. An ADR is a
separate slice from the reference edits that apply it. The vocabulary is the
**Commit slice** entry in `orchestrator/CONTEXT.md`.

**A trivial item is one commit, and that is not a violation.** The rule sets a shape,
not a count. It says "one commit per logical change" and never "at least N commits".
A minimum count makes a worker split a change whose parts fail on their own.

## The rule is owned here because nothing upstream owns it

This repo delegates a rule instead of owning it, whenever an upstream skill
maintains that rule better. `prompt-improver` owns prompt composition (ADR 0006).
`simple-english` owns the prose (ADR 0011). `ponytail` owns how much code and prose
exist at all. Three delegations, one pattern.

Commit granularity has no such upstream. `mattpocock-skills` ships
`setup-pre-commit`, which installs Husky, lint-staged and Prettier and then wires a
hook that formats, type-checks and tests the staged files. It configures hooks and
says nothing about what one commit holds. `ponytail` decides how much code exists,
not how that code is grouped into commits, so a smaller diff has fewer slices. That
is agreement, not a collision.

The delegate-do-not-vendor pattern is therefore unbroken: there is nothing to
delegate to. **The trigger to revisit this decision is a declared dependency that
acquires the rule.** Then apply the ADR 0006 move: depend on the specialist, and
delete the local copy.

## Considered Options

- **One logical change per commit, committed as soon as the slice is complete**
  (chosen) — the branch history becomes a record of the worker's reasoning, written
  while the work happens. It also makes the finished slices durable. A stalled worker
  loses only the slice it was in the middle of.
- **One commit per work item, at the end** (rejected) — the state before this ADR,
  and the defect. The reviewer gets a wall instead of a first step, a bisect has one
  step, and an unattended worker that stalls leaves nothing behind.
- **Commit once, then split it with an interactive rebase before the PR** (rejected)
  — the history becomes a reconstruction rather than a record. It is also written by
  the worker least able to remember the order. It needs interactive git in a session
  with nobody to answer a prompt, and it keeps the stalled-worker failure as it is.
- **Set a minimum commit count, or one commit per changed file** (rejected) — a
  count rewards the wrong behaviour. A worker that must reach N commits splits a
  change whose parts fail on their own. A per-file rule breaks the self-consistency
  condition every time a file and its link target differ.
- **Delegate the rule to a dependency** (rejected) — there is no dependency to
  delegate it to, per the section above. A rule invented in an upstream skill for
  this repo's benefit is vendoring with extra steps.
- **Enforce the rule with a hook, a linter or a CI commit-count gate** (rejected) —
  a second enforcement mechanism that drifts from the documented one. It also puts a
  machine in judgment of a rule no machine can judge. A gate can count commits, and
  it cannot tell one logical change from two.

## The merge strategy is unchanged

Slices serve the reviewer who reads the open PR. They are not a request to change
the merge button.

This repo allows squash merge and every merged PR so far landed squashed. So `main`
carries one commit per item, and the existing `feat: ... (#N) (#M)` log stays intact.
That history is the maintainer's index of shipped items, and one commit per item is
what makes it readable. The slices live on the worker branch, where the review
happens, and the squash discards them at merge time on purpose. A spec that wants
slices preserved on `main` is separate work with a wider blast radius.

Nothing in this ADR touches a repo setting. No branch protection rule, no allowed
merge method and no default merge commit message changes.

## Enforcement is documentary

The rule reaches a worker as prose it reads, the same as every other rule in this
repo. There is no hook, no linter, no `commitlint`, no `.gitmessage` template and no
PR check on commit count. The commits already on `main` are not rewritten.

**The accepted risk:** a worker that lands one blob is blocked by nothing. The
mitigation is proportion, not a mechanism. The failure is visible in the PR the
maintainer opens, it costs one hard-to-read review, and it breaks no build and loses
no data. A mechanical gate costs more than that, because it can only count. Such a
gate passes a worker that split one change into four commits. It fails a worker that
correctly landed a one-line fix as one commit.

## Consequences

- **The PR is the test.** An item about commit discipline that arrives as one commit
  fails its own acceptance criteria. A review note names each slice and what it
  holds, which is how the maintainer checks the rule without a tool.
- **A stalled worker leaves a second progress signal.** The orchestrator reads the
  checklist file to track a worker. The branch history is now an independent record
  of how far the worker got. The two disagree when a worker ticks a box it did not
  finish, and the commits are the harder evidence.
- **A fix round after an adversarial review commits one slice per finding**, so the
  reviewer can map each fix to the finding it answers.
- **This ADR declares the rule and wires nothing.** The worker contract is a separate
  change: the checklist template a worker ticks, and the skill body that explains the
  box. Until that change lands, no worker behaviour changes, and a worker already in
  flight is unaffected.
