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
| 11| **automation-create** (opt) | item number, precheck command, worktree → automation id | One schedule per live work item, so the tick outlives the session that created it. |
| 12| **automation-remove** (opt) | automation id → removed | Step 8 of a close transaction removes the schedule with the worktree. |
| 13| **automation-repoint** (opt) | automation id, precheck command, worktree → repointed | A transition moves the work to another worker, so the precheck follows the live one. One schedule per item stands. |

Notes:
- If a tool lacks a native op (e.g. no `tab-open`), the tool file says so and the skill skips that optional step.
- If **send** and **submit** are two steps on a tool, the tool file documents both; the skill body treats them as one logical "send".
- **A tool can also split the logical send deliberately, where a harness needs a first-run dialog answered.** Then the two halves are type-the-prompt and submit-it, with an inspection of the composer between them, and the split is a property of the *harness*, not of the tool. Op 4 stays one step by default, and a tool file documents the split only where the tool supports both halves. `orca` does, and documents it as 4a. This note is the whole contract change: it adds a permitted second shape, and it retires nothing. Rationale: [`../../docs/adr/0017-gate-worker-readiness-on-a-process-check.md`](../../docs/adr/0017-gate-worker-readiness-on-a-process-check.md).
- The **worker-create** handle must be the one to prompt. If a tool returns a handle that churns during boot, the tool file says which handle is stable.
- **Op 3 is not complete when the handle exists.** The skill body requires a **readiness gate** between `worker-create` and the first `send`. Its signal is a live harness process whose working directory is the worktree. A handle, a `running` status and an idle screen are each satisfied by a worker that has already died. So none of them ends op 3. See the ADR above, and the note below for where the check lives.
- **Readiness and the Worker watch get no row, and no tool file implements them.** Both live in one seam, `scripts/worker_state.py`. Neither is a **Tool** fact: a tool cuts the worktree and opens the terminal, and it does not own the process inside it. Only the harness's process name varies, and it arrives as an argument the skill body reads from `../harnesses/<harness>.md`. **This note is a prohibition.** Two rows here put one identical command in three tool files. Three copies of one command drift, and the drift is invisible until a spawn is gated by the older one. `orca`'s **3a** predates this note. It stays, as a pointer to the seam plus the measurements that ruled out the screen signals. Do not add a 3a to a second tool file, and do not add a watch row. Rationale: [`../../docs/adr/0019-readiness-is-a-tool-agnostic-process-check.md`](../../docs/adr/0019-readiness-is-a-tool-agnostic-process-check.md).
- **What the prohibition above forbids is one copy of one identical seam command in three tool files.** It does not reach a command that genuinely differs per tool. Operations 11, 12 and 13 are that case: `orca` has an automation surface, and `cmux` and `herdr` have none. That difference is the shape a tool row exists for. So the three rows are permitted, and each tool file writes its own command around a `<precheck-command>` placeholder. The caller fills the placeholder with the seam command. So the seam stays in one place. Rationale: [`../../docs/adr/0022-item-automation-replaces-the-blocking-watch.md`](../../docs/adr/0022-item-automation-replaces-the-blocking-watch.md), and for operation 13 [`../../docs/adr/0026-the-automation-follows-the-live-worker.md`](../../docs/adr/0026-the-automation-follows-the-live-worker.md).
- **Operation 13 edits one schedule, and it creates none.** ADR 0026 rejected a second schedule per worker, so a transition repoints the one the item already owns. The caller passes the live worker's worktree and the precheck that names it. A tool with no automation surface has no schedule, so it has nothing to repoint and it loses nothing. Rationale: [`../../docs/adr/0026-the-automation-follows-the-live-worker.md`](../../docs/adr/0026-the-automation-follows-the-live-worker.md).
