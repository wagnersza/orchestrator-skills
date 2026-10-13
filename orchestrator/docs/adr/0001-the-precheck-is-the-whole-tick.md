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

**The precheck exits non-zero on every path**, so orca never starts the automation's
agent. A tick costs no tokens.

**The precheck is one line that runs a generated file.** Install writes
`.orchestrator/tick.sh`, a gitignored shell file with one word per line, and the precheck
is `sh '<repo>/.orchestrator/tick.sh'`. A hand run of `sh .orchestrator/tick.sh` is the
same tick, with the same exit code, so debugging a tick needs no copy of orca's precheck.

**A lock file keeps two ticks apart.** A lock older than five minutes is left over from a
crash, and the next tick takes it.

**Setup creates the automation, and a re-run keeps it.** The install step creates the
labels, the Run, the tick file and the automation where they are missing. It repairs a
tick file or an automation that differs from what the loop needs, and it replaces a Run
that orca no longer knows. Then it runs one tick by hand, and that proof tick shows the
loop is live.

## Rejected

- **A blocking wait in the main session.** The session must stay alive, and every wake
  costs tokens.
- **One automation per item**, as v1 did. Automations leaked, and each new item needed a
  repoint.
- **The tick inline in the precheck**, as v2.0.0 did. The line quoted the repo, node and
  the script, a hand run had to copy it out of orca, and a new node path meant an edit to
  the automation.

## Consequences

The main session never polls and never waits. It answers a verb and goes idle. A repo with
no automation has no loop, so the skill sends a first "work on N" to setup.
