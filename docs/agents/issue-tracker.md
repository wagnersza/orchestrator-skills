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

The states a work item moves through while an agent owns it. **One family, four values,
and it never stacks — swap, never stack**
(`gh issue edit <n> --add-label <new> --remove-label <old>`).
The orchestrator reads these from here; its own config never redefines them.

| State | Label | Meaning |
|-------|-------|---------|
| ready | `ready-for-agent` | Fully specified; a worker can start. Gates the ready queue. |
| in progress | `in-progress` | A worker owns it. Set at spawn, before the prompt. Held through the whole adversarial-review loop. |
| review | `to-review` | Work done, PR open, evidence posted. Waiting on a human. |
| stopped | `needs-human` | A seam refused. **The one label that stops every tick.** |
| done | *(closed)* | PR merged and the issue closed. |

**A seam writes every value in this table, and no session writes one by hand.** The tick of
an **Item automation** applies the transition it computed, in the process that read the
labels. The removals and the addition are one command, so nothing can stack. The
orchestrator's spawn claim runs that same writer under one named transition, and the close
seam writes the last value as one step of its own transaction. Rationale:
[`orchestrator/docs/adr/0056-the-tick-applies-the-transition-it-computed.md`](../../orchestrator/docs/adr/0056-the-tick-applies-the-transition-it-computed.md).

**`needs-human` carries one comment that says what the seam saw, and only the maintainer
removes it.** Every tick reads it first and stays quiet, whatever the other facts say. So a
paused item costs one cheap read a minute and moves nowhere.

**Where an item sits inside an owned run is computed, and no label records it.** The
**Position** entry of
[`orchestrator/CONTEXT.md`](../../orchestrator/CONTEXT.md) holds that rule, and
[`orchestrator/docs/adr/0053-one-work-state-label-and-a-computed-position.md`](../../orchestrator/docs/adr/0053-one-work-state-label-and-a-computed-position.md)
records why the family that cached the same answer is gone.

Triage roles (`needs-triage`, `needs-info`, `ready-for-human`, `wontfix`) are a
separate vocabulary — see `triage-labels.md`. The layer 5 story gate writes two more, and
both stack — see [Story gate labels](#story-gate-labels). The project board is an input
and nothing writes it — see [Project board](#project-board).

Labels beyond GitHub's defaults don't exist in this repo yet. Create on first use:

```bash
gh label create in-progress --color FBCA04 --description "An agent worker owns this"
gh label create to-review   --color 0E8A16 --description "Work done, PR open, awaiting human review"
gh label create ready-for-agent --color 1D76DB --description "Fully specified, ready for an AFK agent"
gh label create user-story  --color 5319E7 --description "A spec whose children are the implementable work"
gh label create needs-human --color B60205 --description "A seam refused. Every tick stops until a human clears it"
```

## Story gate labels

Two more families, and the layer 5 story gate writes both on every candidate it files. They
answer different questions from the two families this file already names. So they **stack**
with a work-state label, and neither one replaces a label of another
family. Rationale:
[`orchestrator/docs/adr/0048-the-story-gate-report-is-a-repo-artifact.md`](../../orchestrator/docs/adr/0048-the-story-gate-report-is-a-repo-artifact.md).

**`refactor` is provenance, and not a state.** It answers where an item came from: a layer 5
story gate filed it. Provenance never changes, so a session writes the label once. It never
swaps the label and never removes it. One label is the whole family.

| Provenance | Label | Meaning |
|-------|-------|---------|
| story gate | `refactor` | A layer 5 story gate filed this item. Written once, never swapped and never removed. |

**The `rating:*` family says what the gate rated the candidate.** **Mutually exclusive inside
the family — swap, never stack** (`gh issue edit <n> --add-label <new> --remove-label <old>`),
the same rule the work-state family takes. It stacks with `refactor`,
because the two answer different questions: where the item came from, and how the gate judged
it.

| Rating | Label | Meaning |
|-------|-------|---------|
| strong | `rating:strong` | The gate rated the candidate strong. Filed as a work item, so it wears `ready-for-agent` beside this label. |
| worth exploring | `rating:worth-exploring` | The gate rated the candidate worth exploring. Sent to the backlog, so it wears no work-state label. |

The gate files no item for a candidate it drops, so nothing wears either family.

**Neither family reaches the board.** Nothing writes a card at all, so no label of any
family moves one. That is one statement for both families.

Create on first use:

```bash
gh label create refactor --color A2EEEF --description "A layer 5 story gate filed this. Provenance, not a state, so it stacks"
gh label create rating:strong --color D4C5F9 --description "The layer 5 story gate rated this candidate Strong"
gh label create rating:worth-exploring --color D4C5F9 --description "The layer 5 story gate rated this candidate Worth exploring"
```

## Project board

This repo's issues are also cards on a GitHub Projects v2 board. **The board is an input,
and nothing writes it.** One question is asked of it: is this item's card in the start
column. That is the second fact of a ready-queue entry, beside the `ready-for-agent`
label. **Both facts are necessary, and one fact on its own starts nothing.** Rationale:
[`orchestrator/docs/adr/0054-the-board-is-an-input-not-a-mirror.md`](../../orchestrator/docs/adr/0054-the-board-is-an-input-not-a-mirror.md)
and
[`orchestrator/docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md`](../../orchestrator/docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md).

Two coordinates, and the name of the start column:

| What | Value |
|------|-------|
| Project | <https://github.com/users/wagnersza/projects/6> — `--owner wagnersza`, number `6` |
| Start column | `To do`, between `Ready` and `In progress` |

**This file records the start column by name, and never as an option id.** An option id is
the address a card write needs, and nothing writes a card. So the name is the whole
coordinate, and the reader compares it to the `Status` name the board answers.

**A `To do` card is not promoted to the `ready-for-agent` label.** No pass reads one fact
and writes the other, in either direction. The two facts stay separate. That is what keeps
`Ready` the maintainer's own lane. An item dragged to `Ready` gains no label, and a
labelled item left in `Ready` starts nothing.

### The one call

```bash
gh project item-list 6 --owner wagnersza --format json --limit 100
```

The reader walks the answer and matches the card whose `content.number` is the item. The
`Status` name on that card is the answer, and an item with no card answers nothing. **A
card with no status, an item with no card, and a repo with no board all read the same
way**, so none of the three is an error.

The token needs the `read:project` scope (`gh auth refresh -s read:project`). **There is
no write scope, because there is no write.**

**A closed item reaches `Done` through the board's own built-in workflow.** GitHub Projects
ships an **item closed to Done** workflow, and the maintainer enables it in the project
settings. Nothing in this repo can switch it on, because that switch is not in the API.
`/orchestrator-setup` reads whether it is on and says so.

**A drag is intent, in every column.** No pass writes a card, so a card stays where the
maintainer put it. A take-back is the maintainer removing `ready-for-agent`, or writing
`needs-human` with a comment that says why.

**A repo with no board leaves this section out entirely.** The board read then asks
nothing, the `ready-for-agent` label alone is the whole gate, and that absence is never an
error.

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
