# Orchestrator

The orchestrator runs agent workers on a tracker's issues. This file names the terms the
two skills use. The decisions behind them are the ADRs in [`docs/adr/`](docs/adr/).

## Language

**Orchestrator**:
The main session. It answers four verbs, work on N, status, merge N and set up, and each
verb is one call to the script. It relays what the call prints, and it never implements an
issue itself.
_Avoid_: coordinator, main agent.

**Worker**:
One agent session that orca starts on one issue, in its own worktree, on the harness and
model its role names. It does the work, opens the PR and reports done or stuck. It runs the
same skills on every harness, and it never changes a state label and never merges.
_Avoid_: agent, sub-agent.

**Harness**:
The agent CLI a worker runs in: claude, codex, cursor, pi or copilot.
_Avoid_: agent, runner, tool.

**Tracker**:
Where issues live: GitHub, GitLab or local markdown. It holds every state label, the
blockers, the parent links and the PR.
_Avoid_: backend, board.

**Role**:
The class of an issue that picks its harness, model and effort: heavy, medium or light.
It is picked without an agent, from the issue's labels and its Touches count, unless a
human names one ([ADR 0005](docs/adr/0005-the-role-is-picked-deterministically.md)).
_Avoid_: tier, profile.

**Tick**:
One run of the automation's precheck, once a minute. It reads what the workers reported,
moves state labels, tears down merged issues, closes finished parents and fills free
slots. Then it exits non-zero, so no agent runs
([ADR 0001](docs/adr/0001-the-precheck-is-the-whole-tick.md)).
_Avoid_: poll, watch.

**State label**:
The one value that holds an issue's work state: ready-for-agent, in-progress,
ready-for-human or needs-human. A label on GitHub and GitLab, a `Status:` line on the local
tracker. Only the script moves one, except that a human writes ready-for-agent
([ADR 0003](docs/adr/0003-state-labels-are-the-only-state.md)).
_Avoid_: status, phase, column.

**Claim**:
Assigning an eligible issue to the person who runs the orchestrator and moving it to
in-progress, in one tracker write.
_Avoid_: pick up, lock.

**Eligible**:
Open, ready-for-agent, unassigned or assigned to me, and nothing open blocks it.
_Avoid_: ready, startable.

**Parent**:
An issue with children, or with the `user-story` label. It is claimed and later closed,
but it never gets a worker of its own. The tick closes it once every child is closed.
_Avoid_: epic, story run.

**Child**:
An issue under a parent. It runs exactly like any other issue, and it starts only when it
carries its own ready-for-agent and nothing blocks it.
_Avoid_: sub-task.

**Slot**:
One of `max_workers` places for a live worker. A parent takes none.
_Avoid_: seat, roof.

**Resume**:
A fresh worker on an existing `issue-N` worktree, after a needs-human round trip. The human
answers on the issue and relabels it ready-for-agent, and the new worker reads the latest
comments first.
_Avoid_: retry, re-prompt.

**Teardown**:
Releasing the worker, removing the worktree, dropping the state label and closing the
issue, after the tracker confirms the merge
([ADR 0004](docs/adr/0004-the-session-merges-on-request.md)).
_Avoid_: close transaction, cleanup.

## Relationships

- A **Tracker** holds many issues. Each issue holds at most one **State label**.
- A **Tick** or a work on N **Claims** an **Eligible** issue and starts one **Worker** on
  it, in one **Slot**, on the **Harness** its **Role** names.
- A **Parent** holds **Children**. Claiming a parent starts its eligible children and takes
  no slot.
- A done worker moves its issue to ready-for-human. A stuck worker moves it to needs-human
  ([ADR 0002](docs/adr/0002-orca-orchestration-is-the-done-and-stuck-signal.md)).
- A needs-human issue that a human relabels gets a **Resume**. A merged ready-for-human
  issue gets a **Teardown**.
