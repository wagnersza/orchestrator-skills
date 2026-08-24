# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

**The reads the orchestrator flows make live in
[`orchestrator/references/tracker-reads.md`](../../orchestrator/references/tracker-reads.md)**,
with the command for `gh` and the command for `glab`. That file also holds the rule that
an exit code is checked before a parse. The conventions in this file stay the generic
surface every skill uses, and a flow read gets no second copy here.

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
| to merge | `to-merge` | A human reviewed the item and approved the merge. |
| done | *(closed)* | PR merged and the issue closed. |

Triage roles (`needs-triage`, `needs-info`, `ready-for-human`, `wontfix`) are a
separate vocabulary — see `triage-labels.md`. Phase labels are a third — see
[Phase labels](#phase-labels). The project board's `Status` field is derived from the
work-state labels above — see [Project board](#project-board).

Labels beyond GitHub's defaults don't exist in this repo yet. Create on first use:

```bash
gh label create in-progress --color FBCA04 --description "An agent worker owns this"
gh label create to-review   --color 0E8A16 --description "Work done, PR open, awaiting human review"
gh label create ready-for-agent --color 1D76DB --description "Fully specified, ready for an AFK agent"
gh label create user-story  --color 5319E7 --description "A spec whose children are the implementable work"
gh label create to-merge    --color 6F42C1 --description "A human reviewed this item and approved the merge"
```

## Phase labels

Which part of an owned run a work item is in. A **second family, worn beside the
work-state label** rather than instead of it. **Mutually exclusive inside the family —
swap, never stack** (`gh issue edit <n> --add-label <new> --remove-label <old>`), the
same rule the work-state family takes.

| Phase | Label | Meaning |
|-------|-------|---------|
| implementation | `phase:impl` | A worker is implementing. Set at spawn, beside `in-progress`. |
| review | `phase:review` | A reviewer is reading the diff. Fix rounds are inside this phase. |
| proof | `phase:e2e` | A worker is proving the feature works through the browser surface. |
| human review | *(no phase label)* | `to-review` alone. Removing the label is the transition. |

**The two families stack.** An owned item wears `in-progress` and exactly one `phase:*`
label together, because they answer different questions: who owns the item, and what
that owner is doing. **Human review carries no phase label**, because `to-review`
already records it.

**The `Status` derivation table below is unchanged.** `Status` derives from the
work-state labels alone, so a phase change writes no card. Rationale, and why this is a
second family rather than more values in the first one:
[`orchestrator/docs/adr/0021-phase-is-a-second-label-family.md`](../../orchestrator/docs/adr/0021-phase-is-a-second-label-family.md).

Create on first use:

```bash
gh label create phase:impl   --color C5DEF5 --description "A worker is implementing this"
gh label create phase:review --color C5DEF5 --description "A reviewer is reading the diff"
gh label create phase:e2e    --color C5DEF5 --description "A worker is proving the feature works"
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
| `To merge` | `beff64f9` |
| `Done` | `98236657` |

### Deriving `Status`

| Condition on the issue | `Status` |
|---|---|
| open, no work-state label (incl. `needs-triage` / `needs-info` / newly created) | `Backlog` |
| open, `ready-for-agent`, **≥1 open blocker** | `Backlog` |
| open, `ready-for-agent`, **0 open blockers** | `Ready` |
| open, `in-progress` | `In progress` |
| open, `to-review` | `In review` |
| open, `to-merge` | `To merge` |
| closed | `Done` |

**Open-blocker count is the same predicate the ready queue already uses** — don't
invent a second one. GitHub native issue dependencies:
`gh api repos/<owner>/<repo>/issues/<n> --jq .issue_dependencies_summary.blocked_by`
(open blockers only), falling back to the `Blocked by: #<n>` body line where
dependencies aren't enabled. See the **Blocking** bullet under
[Wayfinding operations](#wayfinding-operations) for the full contract.

**The `To merge` column is the one exception, and it runs the other way.** For every
other column, `Status` derives from the label. For this one column, the label derives
from the column:

- **One column.** The exception covers `To merge` and no other column.
- **One direction: board to label.** A session reads the column and writes the label.
  No write ever targets the column for this state.
- **The promotion happens once.** A session promotes a card the first time it reads the
  merge queue. It also promotes a card the first time it answers a `merge-requested` wake
  and finds the card in `To merge` with no `to-merge` label yet. It then writes the label.
- **The label is authoritative afterwards.** Once a card carries `to-merge`, every later
  read uses the label, the same as every other work-state.

Rationale:
[`orchestrator/docs/adr/0038-the-to-merge-column-is-intent.md`](../../orchestrator/docs/adr/0038-the-to-merge-column-is-intent.md).

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

# 3. find every card in the To merge column, for the promotion pass
gh project item-list 6 --owner wagnersza --format json --limit 100 \
  --jq '.items[] | select(.status=="To merge")'
```

Step 2 is **idempotent** — writing the value a card already holds exits clean and
changes nothing, so a reconcile pass over a consistent board is safe to run any
time. The token needs the `project` scope (`gh auth refresh -s project`). An issue
with no card yields an empty `$ITEM`: skip the write, don't fail.

**A repo with no board leaves this section out entirely**, and every board write
becomes a no-op — the orchestrator looks for this section, finds nothing, and runs
on labels alone. The promotion is a board write too. Its absence is never an error either.
With no `To merge` column, the label stays the only entry for that state.

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
