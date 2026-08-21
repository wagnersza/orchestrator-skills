# A gate run is work product

A worker ticks its own gate box. Nothing on disk says the command ran, and nothing says
it exited 0.

[ADR 0032](0032-quality-gates-are-a-layered-contract.md) gave each **Layer** a command
and an exit code, and [`../../references/checklist.template.md`](../../references/checklist.template.md)
gave each layer a box. So the bar moved from *trust my evidence* to *trust that my
command was green*. Both are a claim a reviewer has to accept. A **Worker watch** tick
reads the ticked box and reports `implementation-complete`, and the session moves the
item to review on a fact nobody measured.

## The decision

Each gate command appends one line to `.orchestrator/gates-<item>.jsonl` in the worker's
own worktree. The line carries four keys: `command`, `exit`, `utc` and `head_sha`. The
format and its one home are
[`../../references/quality-gates.md`](../../references/quality-gates.md), and the
vocabulary is the **Gate record** entry of [`../../CONTEXT.md`](../../CONTEXT.md).

`head_sha` is what ties a green run to a commit. A green line against a stale commit
proves nothing, and the watch can see the difference.

The **Completion signal** then reads three facts instead of two. A ticked **Checklist**,
plus a green line for every required layer at the current `HEAD`, is a finish. A ticked
checklist with a line missing, a malformed line, a non-zero exit or a stale `head_sha`
is a ninth outcome, `gates-unproven`. The session re-prompts the worker instead of
moving the item to review.

**The record is a record, and not a second enforcement mechanism.** No hook blocks a
push, and no script rejects a commit. ADR 0032 rejects the second mechanism. It does not
reject a record of what happened. The push stays open, and the item stops before review
instead.

**The outcome carries no new exit code.**
[ADR 0022](0022-item-automation-replaces-the-blocking-watch.md) holds the precheck to a
binary contract, so `gates-unproven` rides the printed line like the other eight
outcomes and exits 0 through the same `fire()` path. It shares the `--back-off` window
too, keyed on the same `(item, outcome)` pair.

**The seam still parses no config.** The spawn resolves which layers are required and
passes them as a repeatable `--require-gate` flag, the same way it already passes the
round bound and the stall window
([ADR 0018](0018-the-worker-watch-is-a-stateless-seam.md)). So the seam names no gate
command of its own, and a repo whose spawn names no layer keeps the behaviour it had
before this flag existed.

**`gates-unproven` fires inside the Completion signal**, in `phase:impl` and in
`phase:e2e`, and only after the checklist reads complete. So it fires in place of
`implementation-complete` or `proof-complete`, and it can never compete with `dead` or
`stalled`. Those two need an unticked checklist to be reached at all.

## Considered Options

- **One appended line per gate command, read by the watch** (chosen) — the run becomes
  work product, the same way the checklist and a `Verdict:` comment already are
  ([ADR 0018](0018-the-worker-watch-is-a-stateless-seam.md)). A worker writes it when it
  runs the gate, so there is no second place to record progress.
- **Trust the ticked box** (rejected) — the state this ADR replaces. A box is a claim,
  and a claim about a machine-readable fact is the one kind this repo does not accept.
- **A git hook, or a script that rejects a commit** (rejected) — ADR 0032 chose
  documentary enforcement, and a hook is the second mechanism it rejected. A hook also
  fails closed on a machine that has no tool installed. It then stops work that the bar
  permits.
- **A new exit code for the outcome** (rejected) — ADR 0022 holds the precheck to one
  bit. A ninth code makes every caller read more than that bit.
- **Let the seam read the `gates:` block of config** (rejected) — the seam parses no
  configuration file, names no harness, no tracker and no tool, and this would be the
  first exception. The spawn is the one place config is read.
- **One line per step instead of one per layer command** (rejected) — a step is inside
  the layer script, and the **Layer** command is the unit config names. The watch then
  needs to know which steps a layer holds.
- **Record the run in a tracker comment** (rejected) — a comment is a network write on
  every gate run, and the file dies with the worktree exactly as the checklist does.

## Consequences

- **ADR 0022 and ADR 0027 name eight outcomes, and neither body changes.** This ADR adds
  the ninth. ADR 0022 narrowed
  [ADR 0018](0018-the-worker-watch-is-a-stateless-seam.md) the same way, with no edit to
  that body. The live surfaces — the seam, [`../../CONTEXT.md`](../../CONTEXT.md) and
  [`../../SKILL.md`](../../SKILL.md) — say nine.
- **The `gates-unproven` row writes no label.** The item stays in the phase it is in, so
  the response is a reset and a re-prompt, the same shape as the `stalled` row.
- **A red run must still append its line.** A gate that writes nothing when it fails
  reads as a gate that never ran, which is the state this ADR replaces. So the templates
  append whatever the exit code is.
- **Accepted risk: a worker can hand-write a green line.** The record is work product,
  and work product can be forged. A forged line is a lie a human can read afterwards,
  and a ticked box never was. Nothing here finds one.
- **Accepted risk: the record can name a command no required layer names.** The spawn
  resolves the required list, so a typo in either place reads as a missing line. The
  printed line names the command it wanted, which is what a maintainer needs to correct
  one.
- **Accepted risk: a stale `head_sha` fires on an amended commit.** A worker that amends
  or rebases after a green run runs that layer again. That is the intended cost:
  the record ties a run to a commit, and the commit changed.
