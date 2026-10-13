# The precheck is the whole tick

Something has to watch the workers and start the next issue. An agent session can do it,
but it must stay open, and every wake costs tokens. v1 used orca automations, one per work
item plus a queue automation. That leaked automations, and each one needed a repoint step.

## The decision

**One orca automation per repo, `orchestrator-tick`, runs every minute.** Its precheck runs
the script's `tick`. The tick is the whole loop: it reads the mailbox, catches dead
workers, tears down merged issues, closes finished parents and fills free slots, in that
order. Reading first frees slots before filling them, so a worker that finished this minute
makes room in the same tick.

**The precheck exits non-zero on every path.** orca records each run as skipped and never
starts the automation's agent. So a tick costs no tokens.

**A lock file keeps two ticks apart.** A lock older than five minutes is left over from a
crash, and the next tick takes it.

**Setup creates the automation, and a re-run keeps it.** The install step finds the labels,
the Run and the automation that already exist and creates only what is missing.

## Rejected

- **A blocking wait in the main session.** The session must stay alive, and every wake
  costs tokens.
- **One automation per item**, as v1 did. Automations leaked, and each new item needed a
  repoint.

## Consequences

The main session never polls and never waits. It answers a verb and goes idle. A repo with
no automation has no loop, so the skill sends a first "work on N" to setup.
