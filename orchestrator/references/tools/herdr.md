# Tool: herdr

Implements the [operation contract](_operations.md).

> **Status: needs verification.** herdr's command syntax is not pinned here.
> Before first use, confirm each operation against the installed `herdr --help`
> (or its docs) and replace the placeholders. Keep the operation *names* — only
> the commands change.

## Operation map (confirm syntax)

| # | Operation | Command (verify) |
|---|-----------|------------------|
| 1 | worktree-exists? | list worktrees → match slug |
| 2 | worktree-create  | create worktree (branch + checkout + setup hook); capture id/path from output |
| 3 | worker-create    | start `$CMD` in the worktree terminal; capture the **stable** handle to prompt |
| 3a| readiness gate   | a live `$HARNESS` process whose working directory is the worktree — **not** a herdr status field. The check is the tool-independent `lsof`/`ps` one in [`orca.md`](orca.md#3a-readiness-gate--before-the-first-send). Nothing in it is orca-specific, so use it verbatim with herdr's worktree path |
| 4 | send             | send prompt + submit (note whether it's one step or two, like cmux) |
| 5 | read             | read recent terminal output |
| 6 | wait-idle        | native idle-wait if available, else poll `read` |
| 7 | tab-open         | if unsupported, skip the follow-along panel |
| 8 | worktree-list    | list worktrees → slug/id/path |
| 9 | worker-list      | list terminals in the worktree; match the slug title |
| 10| teardown         | remove worktree + kill terminals + delete branch (one call if supported, else the multi-step sequence) |

Record for each op: whether it emits JSON (parse a stable field) or plain text, whether `send` auto-submits, and whether `teardown` is one call. Fill this in the first time herdr is configured.
