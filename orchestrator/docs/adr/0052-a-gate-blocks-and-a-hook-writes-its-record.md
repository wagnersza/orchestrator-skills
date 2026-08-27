# A gate blocks, and a hook writes its record

[ADR 0036](0036-a-gate-run-is-work-product.md) made a gate run leave a line on disk, and
`scripts/checks.sh` appended it. So the record proved that a script the worker ran said
the gate passed. A worker that edits that script, or that runs the gate command by hand,
writes whatever line it likes. So a green line proved that a model said the gate
passed, and not that a command exited zero.

[ADR 0051](0051-a-hook-refuses-and-a-seam-performs.md) added `hooks/record.py`, which
writes the same line from the exit code the harness reports. It accepted two writers for
one item, because the derived exit code leaves a gap the worker's own append covered.

## The decision

**A gate command runs and exits, and the hook writes its record.** `hooks/record.py` is
the one writer of `.orchestrator/gates-<item>.jsonl`. The gate script holds no append,
and neither `Makefile` passes `GATE_COMMAND` to it. The hook reads the command from the
`gates:` block of config, so the record still reads `make quick` and never the path of a
script.

**A green line now proves that a command exited zero.** That is the whole reason the
write moves. A record a model writes is a record a model can fake, and the record is the
third fact the **Completion signal** reads.

**The record contract does not change.** The keys stay `command`, `exit`, `utc` and
`head_sha`, and the format keeps its one home in
[`../../references/quality-gates.md`](../../references/quality-gates.md). A line is
appended whatever the exit code is, because a red run that writes no line reads as a run
that never happened. A stale `head_sha` still reads as not green.

**Nothing in the loop changes.** The `gates-unproven` outcome reads the same file under
the same rule, and no seam changes.

**This repo accepts one hook that writes a file.** ADR 0051 states the plane law: a hook
answers, and a seam performs. `record.py` is the one named exception, and this ADR makes
that exception the only writer rather than one of two. The write is an append-only note
of what a command already did. It is not a mutation of the tracker and it is not a
decision. A second exception needs an ADR of its own.

**The push block is not part of this decision.** The work item that follows denies a
`git push` against a red record. It can only land after this one, because a push denied
against a record a worker wrote proves nothing.

## What this supersedes

**It supersedes [ADR 0036](0036-a-gate-run-is-work-product.md) on two claims.**

- **A gate run is no longer work product.** ADR 0036 put the record beside the
  **Checklist** and a `Verdict:` comment, which a worker writes by doing the work. The
  record is now a machine record: the worker runs the command, and the hook writes the
  line.
- **"No hook blocks a push, and no script rejects a commit" is gone.** A hook writes the
  record here, and the item that follows denies a push against it. So the sentence no
  longer describes the plane, and it is removed from the live surfaces rather than left to
  contradict them.

**The rest of ADR 0036 stands.** The four keys, `head_sha` as the tie between a run and a
commit, `gates-unproven` as the ninth outcome, the one bit the precheck answers with, and
the rule that the seam parses no config are all unchanged.

**Two of its accepted risks are gone.** A worker can no longer hand-write a green line
through the gate script, because the script writes nothing. A second writer no longer
covers the gap where the hook reads no exit code. The first consequence of this ADR
states that cost.

## Considered Options

- **The hook is the one writer** (chosen) — one writer, and it is the plane that sees the
  exit code the harness reported. The record then measures the command rather than
  quoting the worker.
- **Keep both writers** (rejected) — the state ADR 0051 accepted for one item. Two lines
  per run read the same only while the script is honest, and the script is the half a
  worker can edit.
- **Keep the script as the only writer, and drop the hook** (rejected) — this is the
  defect. A record a model can rewrite proves nothing about a command.
- **A seam writes the record** (rejected again) — a seam is not present when a gate runs.
  ADR 0051 rejected this for the same reason.
- **Make the script write the line to a place the worker cannot reach** (rejected) — no
  such place exists inside a worktree the worker owns, and a path outside it needs state
  the seam would then have to find.
- **Let the hook block the gate command instead** (rejected) — the exit code does not
  exist before the command runs, so a `PreToolUse` hook has nothing to judge.

## Consequences

- **A gate run outside a session writes no record.** CI, a `git bisect` script and a
  human at a shell each run the gate command outside a session, so no hook fires.
  The record is a fact about a worker's session, which is the only place the
  **Completion signal** reads it.
- **Accepted risk: a call the harness stopped leaves a gap.** The exit code in the record
  is derived, so `record.py` writes no line where it can read none
  ([ADR 0051](0051-a-hook-refuses-and-a-seam-performs.md)). The worker's append used to
  cover that gap. The gap now reads as a missing line, which fires `gates-unproven` and
  re-prompts the worker to run the layer again. A false stop costs one run, and a false
  green costs the bar.
- **Accepted risk: the plane needs the plugin installed and the session restarted.** A
  manifest is read once, at session start. So a worker in a session that started before
  the plugin carried its `hooks` key runs a gate and gets no line.
  `/orchestrator-setup` reports the plane and names that restart.
- **Accepted risk: a worker can still write the file by hand.** Nothing stops an
  `echo` into the record. The forged line is a lie a human can read afterwards, which is
  what ADR 0036 already accepted. What is gone is the honest-looking path: no script in
  the repo writes the record, so a green line has one origin.
- **The gate script is shorter, and it holds no `git` call and no clock.** The removed
  block read the checklist name, the commit and the time. So the script now needs only
  the tools each layer names, and `scripts/test_quality_gates.py` runs both layers with a
  stub for each one.
