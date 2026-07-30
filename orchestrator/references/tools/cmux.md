# Tool: cmux

Implements the [operation contract](_operations.md).

> **Status: needs verification.** The exact `cmux` command syntax below is not
> pinned. Before first use, confirm each against the installed `cmux --help` and
> replace the placeholders. What IS known (from prior use) is the *shape* of the
> differences vs. orca — captured per operation.

## Known differences from orca

- **worktree-create is not one call.** Where orca does branch + checkout + setup
  hook + terminal in a single `worktree create`, cmux splits this across ~four
  steps (create branch, check it out, run setup/install, open terminal). Run them
  in order and only proceed to `worker-create` once the worktree exists and deps
  are installed.
- **send is two steps.** cmux `send` types the text but does **not** submit;
  follow it with a separate `send-key Enter`. The skill body's single logical
  "send" = `send` + `send-key Enter` on cmux.
- **teardown is not one call.** cmux needs close-workspace + `git worktree remove`
  + `git branch -d` where orca's `worktree rm --force` does all three.

## Operation map (confirm syntax)

| # | Operation | Command (verify) |
|---|-----------|------------------|
| 1 | worktree-exists? | `cmux workspace list` → match slug |
| 2 | worktree-create  | create branch → checkout → run setup → (capture path) — **multi-step** |
| 3 | worker-create    | open terminal running `$CMD`; capture the handle to prompt |
| 4 | send             | `cmux send <text>` **then** `cmux send-key Enter` — **two steps** |
| 5 | read             | `cmux read <handle>` |
| 6 | wait-idle        | poll `read` for the idle prompt, or a native wait if one exists |
| 7 | tab-open         | if unsupported, skip the follow-along panel |
| 8 | worktree-list    | `cmux workspace list` → slug/path |
| 9 | worker-list      | list terminals in the workspace; match the slug title |
| 10| teardown         | close-workspace + `git worktree remove` + `git branch -d` — **multi-step** |

Fill this file in fully the first time cmux is configured, then the ambiguity is gone for every later run.
