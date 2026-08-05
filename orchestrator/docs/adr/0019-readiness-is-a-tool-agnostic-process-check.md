# Readiness is one tool-agnostic process check, not a command per tool

[ADR 0017](0017-gate-worker-readiness-on-a-process-check.md) put a readiness gate
between `worker-create` and the first prompt, and it chose the right signal: a live
agent process whose working directory is the worktree. It then put the concrete command
in the tool reference, as step **3a** of op 3, and
[`references/tools/orca.md`](../../references/tools/orca.md) holds the `orca` copy of
it.

That placement was correct for the rule it followed. A command that changes per tool
belongs in a tool file. A concrete `orca` command in the skill body is the hardcoding
this repo's own body forbids. **This ADR narrows the placement, and keeps the signal.**

This is a new ADR and not an edit to
[`0017-gate-worker-readiness-on-a-process-check.md`](0017-gate-worker-readiness-on-a-process-check.md),
because it narrows an earlier decision. That is [`CLAUDE.md`](../../../CLAUDE.md)'s
rule, and it is the same move [ADR 0016](0016-the-orchestrator-merges-when-asked.md)
made on the human-merge rule. ADR 0017's text stays as written, and a reader who finds
it also finds this one beside it.

## The signal is not tool-shaped, so its home was wrong

The premise the placement rested on is that the command changes per tool. Read ADR
0017's own signal and the premise fails: **a live agent process whose working directory
is the worktree** names a process and a path. Neither is a **Tool** fact.

- **A tool cuts the worktree and opens the terminal.** It does not own the process
  inside it. After the harness starts, one answer holds for "is a real agent doing real
  work here?", whether `orca`, `cmux` or `herdr` opened the pane.
- **A harness contributes one fact only: its own process name.** `claude`, `codex`,
  `pi`, `copilot`, `cursor` — each is one pattern, and everything around the pattern is
  identical.

So the check is neither tool-shaped nor harness-shaped. Step 3a as written puts one
identical shell pipeline in a tool file, and a second tool needs a copy of it. Three
copies of one command in three files is this repo's named failure mode: the copies
drift, and the drift is invisible until a spawn is gated by the older one.

## One seam answers it, for every tool and every harness

Readiness moves into `scripts/worker_state.py`, which is the same seam the **Worker
watch** uses ([ADR 0018](0018-the-worker-watch-is-a-stateless-seam.md)). Two reasons
put both there rather than in two places.

**It is the same question, asked at two moments.** *Is a real agent doing real work in
this worktree?* Readiness asks it before the first prompt. The stall side of the watch
asks it while the work runs. Two files that ask one question drift apart, and this one
has already produced a lost run.

**The harness supplies a pattern, not a procedure.** The process pattern arrives as an
argument, which the orchestrator reads from `references/harnesses/<harness>.md`. So each
harness file gains one line and no logic. The seam never learns what `claude` is, and a
sixth harness stays a Markdown change.

The tool operation contract therefore gains **no row**. It gains a prohibition instead:
readiness and the watch are tool-agnostic, so no tool file implements them. A note is
better than silence here. Silence invites the next contributor to add a per-tool
readiness check, which is the outcome this ADR exists to prevent.

## Considered Options

- **One seam, with the process pattern passed in** (chosen) — one implementation of one
  question. The two facts that do vary, the worktree path and the harness pattern,
  arrive as arguments. It is also testable: a real short-lived child process in a temp
  worktree makes the check credible rather than asserted.
- **Keep step 3a per tool, as ADR 0017 wrote it** (rejected) — the state this ADR
  narrows. It is correct today because one tool file exists. The second tool file copies
  the pipeline, and from then on a fix to one leaves the other wrong.
- **Put the command in the skill body instead** (rejected) — that is the hardcoding the
  body forbids, for a reason ADR 0017 gave and that still holds. A seam is not the skill
  body. The body states that a gate exists and what its signal is, and the seam holds
  the command.
- **A readiness check per harness reference** (rejected) — closer, because the harness
  owns the pattern. It still copies one pipeline five times to vary one string, and the
  pipeline is the part with the bug in it.
- **Ask the tool for readiness, and let each tool answer as it can** (rejected) — the
  tools already answer this, and both answers are wrong. That measurement is ADR 0017's
  whole finding. `read` reports on a screen buffer and `wait` reports on screen motion.
  A dead agent leaves both of them pointed at the shell that outlived it.

## Consequences

- **ADR 0017's signal is unchanged, and only its home moves.** A live agent process in
  the worktree stays the authoritative fact. The gate still fails closed, and it still
  applies to every harness rather than to TUI harnesses alone.
- **`orca`'s step 3a becomes a pointer to the seam.** Keep its measured facts, because
  they are why the screen signals were rejected. They stay as evidence in the tool file,
  and the command they justify no longer lives there.
- **A new tool costs nothing here.** Readiness is answered before a tool file is
  written. A new harness costs one line: its process pattern.
- **Enforcement is documentary**, as everywhere else in this skill. Nothing blocks a
  tool file that adds its own readiness command. The note in the operation contract is
  what a reader meets first, and this ADR is where the reason lives.
- **This ADR narrows a placement and wires nothing.** The seam, the harness lines and
  the note in the operation contract are separate work.
