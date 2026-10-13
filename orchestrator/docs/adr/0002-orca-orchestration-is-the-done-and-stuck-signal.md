# orca orchestration is the done and stuck signal

The loop has to know when a worker is done and when it is stuck. v1 rebuilt that signal
itself: a checklist file, the terminal's idle state, whether a PR existed, and one
automatic re-prompt before it called a human. orca now gives the same facts directly.

## The decision

**Each worker starts as a supervised Dispatch in one orca orchestration Run.** orca adds a
preamble that tells the worker how to report. The tick reads three things from the Run:

- **`worker_done --outcome succeeded`** with an open PR moves the issue to
  `ready-for-human` and releases the worker.
- **`worker_done --outcome failed`, a question or an escalation** moves the issue to
  `needs-human`. The tick stops the worker, keeps the worktree, and posts the worker's own
  text as an issue comment.
- **A worker whose liveness reads exited, with no `worker_done`**, also moves the issue to
  `needs-human`.

**There is no re-prompt.** A stuck worker goes straight to a human, so no tokens are spent
on a worker that has already lost its way.

**The tick maps a message to its issue by the Task title and the worktree name,
`issue-N`.** It never parses the free-text summary.

**Every transition is safe to replay.** orca replays a message until the tick acks it, so a
tick that crashed after the label swap sees the message again. A swap to the state the issue
already holds writes nothing.

## Rejected

Checklist files, scraping the terminal's idle state, polling for a PR, and one automatic
re-prompt. Each one rebuilt a fact orca already holds, and each one cost tokens or code.

## Consequences

The worker contract is short: do the work, open the PR, then report with the command in
orca's preamble. A worker that asks a question ends its own run. The human answers on the
issue, and a fresh worker resumes in the same worktree.
