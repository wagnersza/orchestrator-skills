# Tool: orca

Implements the [operation contract](_operations.md). Always pass `--json` and parse the field you need; the shapes are stable. Orca chooses the worktree path (`~/orca/workspaces/<repo>/<name>/`) — never hardcode it; read `worktree.id` / `worktree.path` from the create JSON. Address a worktree by `id:<repoId>::<path>` (copy the whole `id` field) or `name:<slug>`.

## 1. worktree-exists?

```bash
orca worktree list --json | python3 -c "import json,sys;print('EXISTS' if any(w['displayName']=='$SLUG' for w in json.load(sys.stdin)['result']['worktrees']) else '')"
```

## 2. worktree-create

One call cuts the branch, checks it out, runs the repo setup hook, and opens a terminal. Let the setup hook run — do **not** pass `--setup skip`; the worker needs deps installed.

```bash
CJSON=$(orca worktree create --repo name:<repo> --name "$SLUG" --base-branch <base> --no-parent --json)
WT=$(echo "$CJSON" | python3 -c "import json,sys;print(json.load(sys.stdin)['result']['worktree']['id'])")
```

Stacking on another worktree's branch: pass `--base-branch <that-branch>` and `--parent-worktree` instead of `--no-parent`.

## 3. worker-create

Capture the handle from **this** create call — it is stable through TUI boot (the handle `--agent` returns churns while the agent starts). `$CMD` is the harness launch command (see `harnesses/<h>.md`).

```bash
H=$(orca terminal create --worktree "id:$WT" --title "$SLUG" --command "$CMD" --json \
     | python3 -c "import json,sys;print(json.load(sys.stdin)['result']['terminal']['handle'])")
```

**Why not `orca worktree create --agent <name>`:** that clean one-call path launches the agent with Orca's own argv (default model, no way to pass `--model` or the effort flag), and the handle it returns churns during boot. The two-step `terminal create --command "$CMD"` fixes both — `$CMD` is where the role's model **and** effort land.

`worktree create` also opened a startup shell in its own tab. After `$H` exists
and the setup hook is complete, close every other tab. Then the worktree shows
one tab, the agent. Read the handles fresh from `terminal list` — a startup
handle captured before `terminal create` is stale and fails with
`tab_not_found`.

```bash
orca terminal list --worktree "id:$WT" --json \
  | python3 -c "import json,sys;print('\n'.join(t['handle'] for t in json.load(sys.stdin)['result']['terminals'] if t['handle']!='$H'))" \
  | xargs -I{} orca terminal close --terminal {} --tab --json
```

`--tab` removes the pane and the tab that holds it. Without `--tab`, the empty
tab stays. The close does not stop the harness in `$H`, and `$H` still accepts
`send` after it. `$H` is the only handle you prompt. Teardown kills what is
left.

### 3a. readiness gate — before the first `send`

The skill body requires a **readiness gate** between `worker-create` and the first
prompt, and names a live agent process in the worktree as its authoritative signal.
This is that check. Run it after `terminal create` and before op 4. `$WT_PATH` is
`worktree.path` from the create JSON, and `$HARNESS` is the config's harness name.

```bash
lsof -a -d cwd -Fpn 2>/dev/null \
  | awk -v w="$WT_PATH" '/^p/{p=substr($0,2)} /^n/{if(substr($0,2)==w) print p}' \
  | while read -r p; do ps -o comm= -p "$p" 2>/dev/null; done \
  | grep -qx "$HARNESS" && echo READY || echo "NOT READY"
```

It prints `NOT READY` until a process named `$HARNESS` holds the worktree as its
working directory. Poll it, and do not send while it says `NOT READY`. That one answer
covers every way a worker fails to arrive: still booting, waiting on a first-run
dialog, exited, or never authenticated. All four look the same from outside, because
none of them leaves a live agent in the worktree.

**Use `ps -o comm=` and not `pgrep -x <harness>`.** Verified: a `claude` worker
launched as `claude --model opus --effort xhigh --dangerously-skip-permissions` is
**absent** from `pgrep -x claude` output while `ps -o comm=` on the same pid returns
`claude`. So the `pgrep` form reports `NOT READY` for a perfectly healthy worker,
which is a false negative that stalls a spawn the gate must let through.

**Why `read` and `wait --for tui-idle` are both insufficient here.** Neither looks at
the agent. Measured against a `codex` worker that had exited behind a first-run
dialog:

| Signal | Reported | Why it is wrong |
|--------|----------|-----------------|
| `terminal read` | `status: running` | The **shell** is running. It outlived the agent, and it is what receives the prompt. |
| `terminal wait --for tui-idle` | `satisfied: true` | An idle shell is idle. The condition is met by the failure state. |
| the gate above | `NOT READY` | No process named `codex` holds the worktree. |

`read` is also near-useless for this on an alt-screen TUI. A `--limit 40` read of a
booting `codex` returned ~4 KB of box-drawing noise and three readable words, all
three from the shell prompt above the alt screen. Scraping it for a `%` prompt
misfires both ways: it finds the pre-launch prompt under a healthy TUI, and it misses
a dead agent whose prompt scrolled past the tail.

Two further measured facts, so nobody re-derives them:

- `wait --for tui-idle` returns `satisfied: true` on a plain non-TUI terminal too, so
  a `true` here never implies a TUI is up.
- Where the launched command exits but the shell survives, `read` reports
  `status: running` and `wait` fails with `{"code":"timeout"}` rather than reporting
  the exit. `status: exited` appears only when the terminal itself is gone.

Rationale, and why the gate is stated in the skill body but commanded here:
[`../../docs/adr/0017-gate-worker-readiness-on-a-process-check.md`](../../docs/adr/0017-gate-worker-readiness-on-a-process-check.md).

## 4. send (one step — types **and** submits)

```bash
orca terminal send --terminal "$H" --text "your prompt here" --enter
```

Multi-line: send the whole string as one `--text` (embedded `\n` are literal in the box); the single `--enter` submits.

### 4a. send in two steps, where a harness needs a dialog answered

Where the harness reference names a first-run dialog, split the one call above into
type-then-submit. Then the composer can be inspected while the prompt is still
uncommitted. `orca` supports both halves:

```bash
orca terminal send --terminal "$H" --text "your prompt here"     # types, no submit
orca terminal read --terminal "$H" --limit 40 --json             # is the text in the composer?
orca terminal send --terminal "$H" --enter                       # submits
```

Verified: `--text` with no `--enter` leaves the text un-submitted, and a later bare
`--enter` submits exactly that text. So the split needs no extra flag.

**The inspection fails closed.** Text sent to a dialog-blocked `codex` did not appear
anywhere in the read buffer. So a composer that does not show the text is evidence
that the harness is not accepting input. Hold the prompt, answer the dialog, and
re-check the gate rather than submitting into a dialog. On an alt-screen TUI, look for
the prompt's own first words in the buffer. Do not expect a clean echo.

This split is **conditional**. Op 4 stays one step everywhere else, and the other tool
references are unchanged — see the note in
[`_operations.md`](_operations.md).

## 5. read

```bash
orca terminal read --terminal "$H" --limit 40 --json
```

## 6. wait-idle

TUI harnesses (claude) run alt-screen, so read-tail is sparse. Use wait:

```bash
orca terminal wait --terminal "$H" --for tui-idle --timeout-ms 60000 --json
```

## 7. tab-open (supported)

```bash
orca tab create --worktree "id:$WT" --url "<url>"   # beside a worker
orca tab create --worktree active   --url "<url>"   # beside this orchestrator
```

Orca's browser isn't logged into private hosts by default — the first tab may land on a sign-in page; the user signs in once and it sticks.

## 8. worktree-list

```bash
orca worktree list --json     # displayName = slug = branch, plus full id + path
orca worktree ps   --json     # topology: every worktree with branch, card status, comment
```

## 9. worker-list

The worker terminal is titled with the slug (`--title "$SLUG"`). Match on that; skip the setup/shell terminals — don't just take the first.

```bash
orca terminal list --worktree name:$SLUG --json | python3 -c "import json,sys;ts=json.load(sys.stdin)['result']['terminals'];c=[t for t in ts if '$SLUG' in (t.get('title')or'')];print(c[0]['handle'] if c else 'NO AGENT TERM')"
```

## 10. teardown

One command kills the running worker terminal, removes the git worktree, and deletes the branch. `--force` is required to kill the **live** terminal; once the tree is confirmed clean it is not a data-loss flag.

```bash
orca worktree rm --worktree "id:$WT" --force --json
```
