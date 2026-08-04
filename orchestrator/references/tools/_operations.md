# Tool operation contract

Every tool reference (`orca.md`, `cmux.md`, `herdr.md`) maps these abstract operations to real commands. The skill body calls operations by name; the tool named in config supplies the command. Add a tool = add a file that fills in this contract.

| # | Operation            | Input → Output | Purpose |
|---|----------------------|----------------|---------|
| 1 | **worktree-exists?** | slug → yes/no | Avoid double-spawn. |
| 2 | **worktree-create**  | slug, base-branch → worktree id + path | Branch + checkout + run setup hook. |
| 3 | **worker-create**    | worktree, launch-command, title → **stable** terminal handle | Start the harness in yolo mode. Handle must survive TUI boot. |
| 4 | **send**             | handle, text → (submitted) | Type prompt **and** submit in one call. |
| 5 | **read**             | handle, limit → recent output | Inspect what a worker is doing. |
| 6 | **wait-idle**        | handle, timeout → idle/timeout | Tell busy from idle before sending. |
| 7 | **tab-open** (opt)   | worktree, url → tab | Follow-along browser panel. |
| 8 | **worktree-list**    | → [{slug, id, path}] | Map slug → worktree. |
| 9 | **worker-list**      | worktree → [{handle, title}] | Map worktree → worker handle. |
| 10| **teardown**         | worktree → removed | Kill terminals + remove git worktree + delete branch, in one step if the tool supports it. |

Notes:
- If a tool lacks a native op (e.g. no `tab-open`), the tool file says so and the skill skips that optional step.
- If **send** and **submit** are two steps on a tool, the tool file documents both; the skill body treats them as one logical "send".
- **A tool can also split the logical send deliberately, where a harness needs a first-run dialog answered.** Then the two halves are type-the-prompt and submit-it, with an inspection of the composer between them, and the split is a property of the *harness*, not of the tool. Op 4 stays one step by default, and a tool file documents the split only where the tool supports both halves. `orca` does, and documents it as 4a. This note is the whole contract change: it adds a permitted second shape, and it retires nothing. Rationale: [`../../docs/adr/0017-gate-worker-readiness-on-a-process-check.md`](../../docs/adr/0017-gate-worker-readiness-on-a-process-check.md).
- The **worker-create** handle must be the one to prompt. If a tool returns a handle that churns during boot, the tool file says which handle is stable.
- **Op 3 is not complete when the handle exists.** The skill body requires a **readiness gate** between `worker-create` and the first `send`: a live harness process whose working directory is the worktree. A handle, a `running` status and an idle screen are each satisfied by a worker that has already died, so none of them ends op 3. Each tool file supplies the concrete check as **3a**. `orca` does, and a tool file that omits it is incomplete. See the ADR above.
