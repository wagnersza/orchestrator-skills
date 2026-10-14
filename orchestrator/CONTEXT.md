# Orchestrator

The orchestrator runs agent workers on a tracker's issues. This file names the terms the
two skills use. The decisions behind them are the ADRs in [`docs/adr/`](docs/adr/).

## Language

**Orchestrator**:
The main session. It answers four verbs: work on N, status, merge N and set up. It acts on
a verb without waiting for a slash command, and a bare number after a work verb names an
issue. It passes a role or a note only when the human gives one, and it relays each
outcome as it is. It never retries a refusal, and it never implements an issue itself. It
answers any other request without changing anything.
_Avoid_: coordinator, main agent.

**Worker**:
One agent session that orca starts on one issue, in its own worktree, on the harness and
model its role names. It does the work, offers it for review and reports done or stuck. It
never changes a state label and never merges.
_Avoid_: agent, sub-agent.

**Harness**:
The agent CLI a worker runs in: claude, codex, cursor, pi or copilot.
_Avoid_: agent, runner, tool.

**Tracker**:
Where issues live: GitHub, GitLab or local markdown, and no other. It holds every state
label, the blockers, the parent links and the work under review. A repo names its tracker
once, and setup reads it from there.
_Avoid_: backend, board.

**Run**:
The one orca orchestration that all of a repo's workers belong to. Setup creates it from
an Orca terminal, and the tick reaches every worker through it.
_Avoid_: session, workspace.

**Role**:
The class of an issue that picks its harness, model and effort: heavy, medium or light.
It is picked without an agent, from the issue's labels and its Touches count, unless a
human names one ([ADR 0005](docs/adr/0005-the-role-is-picked-deterministically.md)).
_Avoid_: tier, profile.

**Tick**:
One run of the automation's check, once a minute. It reads what the workers reported,
moves state labels, tears down merged issues, closes finished parents and fills free
slots. It never starts an agent, so it costs no tokens
([ADR 0001](docs/adr/0001-the-precheck-is-the-whole-tick.md)).
_Avoid_: poll, watch.

**State label**:
The one value that holds an issue's work state: ready-for-agent, in-progress,
ready-for-human or needs-human. A label on GitHub and GitLab, a status line on the local
tracker. Only the script moves one, except that a human writes ready-for-agent
([ADR 0003](docs/adr/0003-state-labels-are-the-only-state.md)).
_Avoid_: status, phase, column.

**Claim**:
Assigning an eligible issue to the person who runs the orchestrator and moving it to
in-progress, in one tracker write.
_Avoid_: pick up, lock.

**Eligible**:
Open, ready-for-agent, unassigned or assigned to me, and nothing open blocks it. A work on
N claims any eligible issue. The tick claims one only once it is assigned to me, or is a
child of a parent I hold ([ADR 0006](docs/adr/0006-the-tick-takes-only-what-is-assigned-to-me.md)).
_Avoid_: ready, startable.

**Parent**:
An issue that holds children, such as a user story. It is claimed and later closed, but it
never gets a worker of its own. The tick closes a claimed parent once it has children and
every one is closed.
_Avoid_: epic, story run.

**Child**:
An issue under a parent. It runs exactly like any other issue, and it starts only when it
carries its own ready-for-agent and nothing blocks it. Once its parent is assigned to me,
the tick takes it with no assignee of its own.
_Avoid_: sub-task.

**Slot**:
One of the places the tick fills with a live worker. The config sets how many. A parent
takes none.
_Avoid_: seat, roof.

**Resume**:
A fresh worker in the issue's existing worktree, after a needs-human round trip. The human
answers on the issue and swaps needs-human for ready-for-agent, and the new worker reads
the latest comments first.
_Avoid_: retry, re-prompt.

**Teardown**:
Releasing the worker, removing the worktree, dropping the state label and closing the
issue, after the tracker confirms the merge
([ADR 0004](docs/adr/0004-the-session-merges-on-request.md)).
_Avoid_: close transaction, cleanup.

## Relationships

- A **Tracker** holds many issues. An issue the loop owns holds one **State label**.
- A **Tick** **Claims** each **Eligible** issue assigned to me and starts one **Worker** on
  it, in a free **Slot**, on the **Harness** its **Role** names. A work on N does the same
  at once, assigned or not.
- A **Parent** holds **Children**. Each eligible child starts on its own. A work on N on a
  parent claims it and starts its eligible children, and the parent takes no slot.
- The tick reads each worker's report through the **Run**. It moves the issue of a worker
  that finished with work to review to ready-for-human, and the issue of any other worker
  that stopped to needs-human
  ([ADR 0002](docs/adr/0002-orca-orchestration-is-the-done-and-stuck-signal.md)).
- A needs-human issue that a human relabels gets a **Resume**. A merged ready-for-human
  issue gets a **Teardown**.
