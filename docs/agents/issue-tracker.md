# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` — `gh` does this automatically when run inside a clone.

## Work-state labels

The states a work item moves through while an agent owns it. **Mutually exclusive
— swap, never stack** (`gh issue edit <n> --add-label <new> --remove-label <old>`).
The orchestrator reads these from here; its own config never redefines them.

| State | Label | Meaning |
|-------|-------|---------|
| ready | `ready-for-agent` | Fully specified; a worker can start. Gates the ready queue. |
| in progress | `in-progress` | A worker owns it. Set at spawn, before the prompt. Held through the whole adversarial-review loop. |
| review | `to-review` | Work done, PR open, evidence posted. Waiting on a human. |
| done | *(closed)* | PR merged and the issue closed. |

Triage roles (`needs-triage`, `needs-info`, `ready-for-human`, `wontfix`) are a
separate vocabulary — see `triage-labels.md`. The project board's `Status` field is
derived from these labels — see [Project board](#project-board).

Labels beyond GitHub's defaults don't exist in this repo yet. Create on first use:

```bash
gh label create in-progress --color FBCA04 --description "An agent worker owns this"
gh label create to-review   --color 0E8A16 --description "Work done, PR open, awaiting human review"
gh label create ready-for-agent --color 1D76DB --description "Fully specified, ready for an AFK agent"
gh label create user-story  --color 5319E7 --description "A spec whose children are the implementable work"
```

## Project board

This repo's issues are also cards on a GitHub Projects v2 board. **`Status` is a
derived projection of the work-state labels above — not a second state machine.**
Labels stay the source of truth; the board is written at every label transition and
recomputed whenever the ready queue is read. Rationale:
[`orchestrator/docs/adr/0009-labels-drive-board-status.md`](../../orchestrator/docs/adr/0009-labels-drive-board-status.md).

Coordinates:

| What | Value |
|------|-------|
| Project | <https://github.com/users/wagnersza/projects/6> — `--owner wagnersza`, number `6` |
| Project id | `PVT_kwHOAASnrs4BetWv` |
| `Status` field id | `PVTSSF_lAHOAASnrs4BetWvzhZFi3U` |

`Status` single-select option ids:

| Option | Option id |
|--------|-----------|
| `Backlog` | `f75ad846` |
| `Ready` | `61e4505c` |
| `In progress` | `47fc9ee4` |
| `In review` | `df73e18b` |
| `Done` | `98236657` |

### Deriving `Status`

| Condition on the issue | `Status` |
|---|---|
| open, no work-state label (incl. `needs-triage` / `needs-info` / newly created) | `Backlog` |
| open, `ready-for-agent`, **≥1 open blocker** | `Backlog` |
| open, `ready-for-agent`, **0 open blockers** | `Ready` |
| open, `in-progress` | `In progress` |
| open, `to-review` | `In review` |
| closed | `Done` |

**Open-blocker count is the same predicate the ready queue already uses** — don't
invent a second one. GitHub native issue dependencies:
`gh api repos/<owner>/<repo>/issues/<n> --jq .issue_dependencies_summary.blocked_by`
(open blockers only), falling back to the `Blocked by: #<n>` body line where
dependencies aren't enabled. See the **Blocking** bullet under
[Wayfinding operations](#wayfinding-operations) for the full contract.

Items labelled `user-story` are cards too. A `user-story` parent is never spawned
directly, so its own labels lag its children: it sits in `In progress` while **any**
child is `in-progress` or `to-review` — that **takes precedence over the parent's own
`ready-for-agent`**, which it keeps for the whole run — and reaches `Done` only when
the parent issue is itself closed. With no child in flight it falls back to the table
unchanged.

### The two calls

```bash
# 1. resolve an issue number to its board item id
ITEM=$(gh project item-list 6 --owner wagnersza --format json --limit 100 \
         --jq '.items[] | select(.content.number==<n>) | .id')

# 2. set Status
gh project item-edit --id "$ITEM" \
  --project-id PVT_kwHOAASnrs4BetWv \
  --field-id   PVTSSF_lAHOAASnrs4BetWvzhZFi3U \
  --single-select-option-id <option-id>
```

Step 2 is **idempotent** — writing the value a card already holds exits clean and
changes nothing, so a reconcile pass over a consistent board is safe to run any
time. The token needs the `project` scope (`gh auth refresh -s project`). An issue
with no card yields an empty `$ITEM`: skip the write, don't fail.

**A repo with no board leaves this section out entirely**, and every board write
becomes a no-op — the orchestrator looks for this section, finds nothing, and runs
on labels alone. Its absence is never an error.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments` then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either — resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api` on the sub-issues endpoint). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies** — the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only — the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --state open`, scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me` — the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.
