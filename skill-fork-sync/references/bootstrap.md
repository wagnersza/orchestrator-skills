# Mode: bootstrap

`/skill-fork-sync bootstrap` — create the forks and pin each one to the SHA that
is installed right now, so the day after bootstrap behaves exactly like the day
before.

> **Status: stub.** Filled by issue #4 (*Bootstrap mode: fork-and-pin procedure,
> dry-run verified*). This ticket fixed the mode name and this file's path;
> nothing else here is implemented, and no fork is created or marketplace
> registration changed by the scaffold.

## What will fill this file

The per-fork, idempotent procedure — safe to re-run against an
already-bootstrapped fork without reasoning about whether it has been done:

1. `gh repo fork` the upstream (no clone), which gives GitHub's native fork
   banner and the `parent` API field for free.
2. Clone the fork to `~/.orchestrator/forks/<marketplace-name>/` — never inside
   `~/.claude/plugins/marketplaces/`.
3. Add the `upstream` remote pointing at the original repo.
4. Reset the fork's default branch to the **currently-installed** SHA (from
   `~/.claude/plugins/installed_plugins.json`'s `gitCommitSha`) and force-push.
   Starting at upstream HEAD instead would silently advance the install by
   unevaluated commits — the exact failure the fork exists to prevent.
5. Write and commit `FORK.md`: upstream URL, fork date, last-synced SHA, and why
   the fork exists. A record for humans — the **Pinned SHA** that drives any
   decision is always read live from git.
6. Swap the marketplace registration: remove the upstream one, add the fork's. A
   marketplace name can only be registered once, so fork and upstream are
   mutually exclusive per name.

Also to be pinned down there: how the fork set is derived (cross-referencing
`~/.claude/plugins/known_marketplaces.json` against `gh repo view --json parent`,
so there is no hand-maintained registry to drift), the idempotence check for each
step, and what bootstrap reports when a fork already exists.

## Fixed here, inherited there

- Mode word: `bootstrap`, no arguments.
- Clone root: `~/.orchestrator/forks/<marketplace-name>/`.
- Fork set: the dependencies
  [`requirements.md`](../../orchestrator/references/requirements.md) declares.
  Skills that are merely installed are out of scope until declared.
- Rationale for fork-and-pin, and why tag-based pinning lost:
  [ADR 0007](../../orchestrator/docs/adr/0007-fork-and-pin-skill-dependencies.md).
