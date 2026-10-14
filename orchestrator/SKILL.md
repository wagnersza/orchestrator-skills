---
name: orchestrator
description: Run agent workers on this repo's tracker issues through one script. Use it for every work-item action, without waiting for the user to type /orchestrator. Trigger on "work on N", "work on #N", "start N", "implement N", "build N", "do N", "status", "what's running", "what next", "what's ready", "list workers", "merge N", "merge and teardown N", "set up the orchestrator". A bare number after a work verb always means a tracker issue, not a file or a line number.
---

# Orchestrator

This session is the **orchestrator**. It answers four verbs. Each verb is one call to the
script, and the session then goes idle. An orca automation, `orchestrator-tick`, runs the
script's `tick` every minute. The tick watches the workers, moves the state labels and
starts the next eligible issue, so the session never polls and never waits on a worker.

The script is `scripts/orchestrator.ts` in this plugin, one directory above this skill's
own. Node runs it directly. Run it from the repo's main checkout, because it reads
`docs/agents/orchestrator.md` and `.orchestrator/run.json` from the current directory:

```sh
node <plugin root>/scripts/orchestrator.ts <verb> ...
```

## The four verbs

| The user says | The session runs |
|---|---|
| "work on N", "start N", "implement #N" | `start N` |
| "status", "what's running", "what next" | `status` |
| "merge N", "merge and teardown N" | `merge N` |
| "set up the orchestrator" | the `orchestrator-setup` skill |

- **`start N`** claims issue N and starts one worker on it, in worktree `issue-N`. On a
  parent it claims the parent and starts each eligible child. Add `--role heavy|medium|light`
  only when the user names a role. Add `--note "..."` only when the user gives extra
  context for the worker, and pass their words through as they are.
- **`status`** prints the claimed issues, with state, role, harness, liveness and PR, then
  the ready queue the tick takes, then each issue the tick waits on and why. The tick takes
  an issue only once it is assigned to the user, or is a child of a parent assigned to them
  ([ADR 0006](docs/adr/0006-the-tick-takes-only-what-is-assigned-to-me.md)). `start N` needs
  no assignee.
- **`merge N`** merges the PR of a `ready-for-human` issue, then releases the worker,
  removes the worktree and closes the issue. A merge made on the tracker works too: the
  next tick sees it and tears down.

Each verb prints its own outcome, or one line that says why it refused. Relay that output
to the user as it is. A refusal changes nothing, so do not retry it, and do not work
around it.

**"work on N" in a repo without the automation goes to setup first.** Before the first
`start` of a session, run `orca automations list --json`. If it lists no automation named
`orchestrator-tick` whose `runContext.path` is this repo's main checkout, run the
`orchestrator-setup` skill, and then run `start N`.

Answer any other request freehand. Read the tracker or the script's output to do that, and
change nothing.

## Three hard rules

1. **Never implement in this session.** No code, no tests and no commits for an issue.
   A worker does that work in its own worktree. Asked to implement, run `start N`.
2. **Never write a state label by hand.** The script writes every transition between
   `ready-for-agent`, `in-progress`, `ready-for-human` and `needs-human`. Of the four, a human
   writes only `ready-for-agent`: to queue an issue, or to resume one from `needs-human`
   after answering it in a comment.
3. **Manage every worktree through the orca CLI.** List, inspect, create and remove one
   with `orca worktree list`, `show`, `create` and `rm`, and never with `git worktree`.
   Orca tracks each worktree, and the script finds a worker's worktree through it
   ([ADR 0007](docs/adr/0007-orca-manages-every-worktree.md)).
