# Mode: promote

`/skill-fork-sync promote` — turn the dial. Advance the fork's default branch to
the approved **Sync candidate** and bring the install with it, in one step, so
there is never a half-promoted state where the fork and the install disagree.

> **Status: stub.** Filled by issue #6 (*Promote: advance the pin and refresh the
> install*). Nothing here is implemented, and no install is modified by the
> scaffold.

## What will fill this file

The ordered sequence, plus what to do when a step fails partway:

1. Fast-forward the fork's default branch to the candidate SHA and push. A
   fast-forward only — a promote that needs a force-push means the pin moved
   under the evaluation, so stop and re-sync.
2. Rewrite `FORK.md`'s last-synced SHA and commit it.
3. `claude plugin marketplace update <name>`.
4. Update the plugin **with the command that matches its install shape** — a
   `@skills-dir` clone takes `git pull --ff-only`, not `claude plugin update`,
   which fails on it. The shape table lives in
   [`requirements.md`](../../orchestrator/references/requirements.md); this mode
   reads it rather than restating it.
5. State plainly that the new skill body loads **next session**. The restart
   requirement is documented in `requirements.md` — promote enforces the rule
   instead of re-deriving it.

Deliberately absent: verifying the installed SHA after the update. `plugin
update` may not refresh the cache until restart, so the check would report false
mismatches.

## Fixed here, inherited there

- Mode word: `promote`, no arguments; it acts on the candidate the preceding
  `sync` reported.
- Promote requires explicit approval every time — no auto-promote on a clean
  eval, per
  [ADR 0008](../../orchestrator/docs/adr/0008-diff-targeted-run-budget.md).
- The fork's default branch is the only version dial available, which is why
  promote is a branch move rather than a version or tag bump —
  [ADR 0007](../../orchestrator/docs/adr/0007-fork-and-pin-skill-dependencies.md).
