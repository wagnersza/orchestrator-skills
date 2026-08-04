# A readiness gate holds the first prompt, and a process check is its signal

An adversarial-review round was lost in silence. The orchestrator cut a worktree,
launched `codex` in it, and sent the review prompt. The harness never received it.
`codex` sat behind two first-run dialogs and then exited, so the prompt text landed
in the terminal's `zsh`, which ran the readable fragments of it and printed
`cd: too many arguments`. Nothing was damaged. Nothing errored either. The round was
gone, and the orchestrator believed it had started.

Two signals were available at the moment of the send, and **both reported ready**:

- `orca terminal read` returned `status: running`. True, and about the wrong
  process — the shell was alive after the agent had exited.
- `orca terminal wait --for tui-idle` returned `satisfied: true`. Also true, and
  also useless. An idle shell is idle.

So the gap is not a missing check. It is that the two checks a tool already offers
both answer a question next to the one that matters.

## The signal is a live agent process in the worktree

What separates a worker that can accept a prompt from one that cannot is **a live
harness process whose working directory is the worktree**. That is a process check.

Neither existing signal is a process check. `read` looks at a screen buffer, and
`wait` looks at screen motion. A dead agent leaves both of them looking at the shell
that outlived it.

A screen check cannot be repaired into this, either. On an alt-screen TUI the buffer
comes back as box-drawing noise. Measured on the run that produced this ADR, a
`--limit 40` read of a booting `codex` returned about 4 KB of line-art and three
readable words. All three came from the shell prompt above the alt screen. A scrape
for a `%` prompt in that buffer misfires in both directions. It finds the pre-launch
prompt under a perfectly healthy TUI, and it misses a dead agent whose prompt has
scrolled past the tail.

The process check has the further property that it is **true of the thing being
asked about**. A prompt goes to an agent, so the check tests for an agent.

## This is the third member of a known family

This repo already records two failure modes with the same shape, and both cost a
worker its run before anyone noticed:

- `claude` accepts a typo'd `--effort`, warns, and runs at the default. In a TUI the
  warning scrolls away (`references/harnesses/claude.md`).
- `codex` silently ignores a `--model` placed before its subcommand and runs its own
  default (`references/harnesses/codex.md`).

The family is **a failure mode that reports success**. Each member returns a value
that means "fine" for a question adjacent to the one asked, and the cost lands one
whole run later. Naming the family is the point of putting it here. Then the next
member is recognisable by its shape before it is diagnosed, and the response is the
same each time. Do not add a louder check of the same kind. Find the signal that is
true of the thing you are asking about, and gate on that one.

## Send and submit split only where a dialog can intercept

Op 4 of the operation contract types a prompt and submits it in one call. That is
still the right default. The two steps separate only where a first-run dialog can sit
between the launch and the composer. Then the orchestrator can look at the composer
before it commits the prompt.

The split is **conditional, and every other tool reference stays unchanged.** Two
reasons hold it there. `cmux` already splits `send` from `send-key Enter` for an
unrelated reason, so a global split collapses two different facts into one rule.
And the contract's own note already says a tool can implement the logical send in two
steps. So the conditional split needs no new mechanism — it names a condition under
which the orchestrator uses the second step deliberately.

The inspection between the steps is worth having only because it can fail closed. On
the run that produced this ADR, text sent to a dialog-blocked `codex` did **not**
appear anywhere in the read buffer. So a composer that does not show the text is
evidence, and the orchestrator holds the prompt rather than submitting it into a
dialog.

## Considered Options

- **A process check for a live harness in the worktree, before the first send**
  (chosen) — it tests the thing the prompt needs. It is one command, it works on
  every harness because every harness is a process, and it fails closed: no match
  means not ready, whatever the screen says.
- **Keep `wait --for tui-idle` and raise the timeout** (rejected) — the signal was
  not slow, it was wrong. A longer wait on a true-but-irrelevant answer returns the
  same answer later.
- **Scrape the read buffer for a harness banner or a shell prompt** (rejected) — the
  measurement above. Alt-screen noise makes this misfire in both directions, and it
  ties the gate to one harness's boot text, which changes on any upgrade.
- **Pre-answer the dialogs by writing the harness's trust config directly**
  (rejected) — it puts this repo in charge of user-global state it does not own. That
  is the posture already rejected for the browser MCP registration (ADR 0012). It also
  fixes one harness's dialogs and leaves the general failure open, because the gate is
  needed for a crashed agent too, not only a blocked one.
- **Split send from submit on every tool** (rejected) — half the tools have no dialog
  to inspect for. The contract also permits a two-step send already, where a tool needs
  one. A global split changes three reference files to describe one harness's
  behaviour.
- **Send the prompt and detect the failure afterwards** (rejected) — this is the
  current behaviour and the defect. The detection is a lost round, read after the
  fact, and on this run the prompt fragments executed in a shell first.

## Consequences

- **One more step before the first prompt, on every spawn and every review spawn.**
  It costs one command. The alternative cost, measured once, was a whole review round
  plus the time to work out why the findings never arrived.
- **The gate is harness-shaped, and the command is not in the skill body.**
  `SKILL.md` states that a readiness gate exists and what its signal is. The concrete
  command lives in the tool reference. A concrete `orca` command in the skill body is
  the hardcoding this repo's own body forbids, and it needs an edit for each new
  tool.
- **The gate is not conditional on the harness being a TUI.** A crashed agent, a
  failed authentication and an unanswered dialog are one state from the outside: no
  live agent in the worktree. So the gate applies to every harness, and only the
  dialog-answering step below it is harness-specific.
- **Enforcement is documentary**, as with every other rule here. Nothing blocks a
  send that skips the gate. The failure is visible in the review round that produces
  no findings, and the mitigation is that the orchestrator reads this before it
  spawns.
