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

## 4. send (one step — types **and** submits)

```bash
orca terminal send --terminal "$H" --text "your prompt here" --enter
```

Multi-line: send the whole string as one `--text` (embedded `\n` are literal in the box); the single `--enter` submits.

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
