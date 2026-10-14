# Orca manages every worktree

The script finds each worker's worktree through orca. Start checks `orca worktree show` to
decide between a resume and a new worktree, the tick maps a message to its issue by the
worktree name, and teardown runs `orca worktree rm`. A session that made or removed a
worktree with `git worktree` left orca's catalog out of step with git: orca never saw the
new one, and kept a record of the removed one.

## The decision

**The orchestrator session manages every worktree through the orca CLI.** It lists,
inspects, creates and removes one with `orca worktree list`, `show`, `create` and `rm`,
and never with `git worktree`. That holds for any worktree the session touches, not only
the `issue-N` ones the script makes.

## Rejected

- **Raw `git worktree` for the session's own one-off work.** It is quicker, but orca does not
  see it, so the Orca app, `orca worktree ps` and any later `orca worktree rm` go wrong.

## Consequences

Orca's catalog holds every worktree in the repo, so what orca reports matches git. A
session on a machine without orca cannot manage worktrees at all, and setup already
requires orca.
