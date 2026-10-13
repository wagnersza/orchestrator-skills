# orca orchestration is the done and stuck signal

The loop has to know when a worker is done and when it is stuck. v1 rebuilt that signal
itself: a checklist file, the terminal's idle state, whether a PR existed, and one
automatic re-prompt before it called a human. orca now gives the same facts directly.

## The decision

**Each worker starts as a supervised Dispatch in one orca orchestration Run.** Setup
creates the Run from an Orca terminal, which becomes its coordinator, and the tick reaches
every worker through it. orca adds a preamble that tells the worker how to report. The
tick reads these from the Run:

- **`worker_done --outcome succeeded` with work to review** moves the issue to
  `ready-for-human` and releases the worker. On GitHub and GitLab the work to review is an
  open PR. On the local tracker it is the committed branch.
- **`worker_done --outcome succeeded` with nothing to review** moves the issue to
  `needs-human` and releases the worker.
- **`worker_done --outcome failed`** moves the issue to `needs-human` and releases the
  worker.
- **A question or an escalation** moves the issue to `needs-human` and stops the worker.
- **A worker whose liveness reads exited, with no `worker_done`**, moves the issue to
  `needs-human`.

Each move to `needs-human` keeps the worktree and posts a comment that says why, with the
worker's own text where it sent one.

**There is no re-prompt.** A stuck worker goes straight to a human, so no tokens are spent
on a worker that has already lost its way.

**The tick maps a message to its issue by the Task title and the worktree name,
`issue-N`.** It never parses the free-text summary.

**A replay never moves a label twice.** orca replays a message until the tick acks it, so
a tick that crashed before the ack sees the message again. The tick writes the label last,
and it acts only on an issue that is still `in-progress`. So a replay after the swap writes
nothing, and a replay before it may post its comment a second time.

## Rejected

Checklist files, scraping the terminal's idle state, polling for a PR, and one automatic
re-prompt. Each one rebuilt a fact orca already holds, and each one cost tokens or code.

## Consequences

The worker contract is short: do the work, offer it for review, then report with the
command in orca's preamble. Every worker runs the same mattpocock skills on every harness,
`implement` for the work and `pr` for the PR body, so setup installs them into each harness
the roles name. A worker that asks a question ends its own run. The human answers on the
issue, and a fresh worker resumes in the same worktree.
