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

## The parent edge

**A child carries its parent in two representations, and one command writes both.** The
native parent link is a sub-issue on the parent, and it is the one a human sees as a tree.
The `## Parent` line in the child body is the portable one, because it is the only form
that works on every tracker. Rationale:
[`orchestrator/docs/adr/0065-the-parent-edge-is-two-representations.md`](../../orchestrator/docs/adr/0065-the-parent-edge-is-two-representations.md).

```bash
gh issue edit <child> --parent <parent> --body "<body, carrying its ## Parent block>"
```

**One command, so it cannot write only one edge.** `--parent` sets the native link and
`--body` carries the `## Parent` block, so there is no window in which the child is half
linked. `Tracker.parent_link_argv` in `scripts/tracker.py` builds this argv, and it adds the
`## Parent` block to a body that holds none. The body is a required argument there, because
the command replaces the body.

**This flag takes the parent's `#number`, and no database id.** That is what makes it the
command to use. The REST route, `POST repos/<owner>/<name>/issues/<parent>/sub_issues`, needs
the child's numeric database id from `gh api repos/<owner>/<name>/issues/<n> --jq .id`, which
is neither the `#number` nor the `node_id`. It is the same trap the dependencies line below
warns about, and the `--parent` flag has no part in it.

**Run it once per child, at the create.** A second run on a child that already carries the
native link fails, and the whole command fails with it, so the body write does not land
either. The error names the cause:

```
GraphQL: Failed to add sub-issue #<child> to parent #<parent>. Issue may not contain duplicate sub-issues (addSubIssue)
```

**A failed link write is reported and is not a stop.** The session names the child and the
parent, then carries on. The `## Parent` line already carries the meaning, so no
`needs-human` label is written for it.

**The child read unions the two, and it prefers neither.** One list read carries both edges:

```bash
gh issue list --state all --limit 200 --json number,state,title,body,parent \
  --jq '[.[] | select((.parent.number == <N>) or ((.body // "") | test("(?m)^## Parent\\s+#<N>\\b"))) | {number, state, title}]'
```

**The union is by work item number, and a child that carries both counts once.** Where the
two disagree, the child stays in the answer, so a wrong edge shows up as an extra child and
never as a missing one. A preference order hides that disagreement. A child a maintainer
linked by hand in the UI is a real child here, and that is the case a body scan alone missed.
The full recipe, with the GitLab read beside it, is in
[`orchestrator/references/tracker-reads.md`](../../orchestrator/references/tracker-reads.md).

**GitLab has no parent link between two issues, and this claims no parity.** Its issue links
endpoint offers `relates_to`, `blocks` and `is_blocked_by` only, and its real hierarchy is an
epic or a work item, which is a different object. So there the `## Parent` line is the whole
edge, the write sets the description alone, and the native half of the union is always empty.

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

**A seam writes every value in this table, and no session moves an item from one value to
another by hand.** The tick of an **Item automation** applies the transition it computed, in
the process that read the labels. The removals and the addition are one command, so nothing
can stack. The orchestrator's spawn claim runs that same writer under one named transition,
and the close seam writes the last value as one step of its own transaction. Rationale:
[`orchestrator/docs/adr/0056-the-tick-applies-the-transition-it-computed.md`](../../orchestrator/docs/adr/0056-the-tick-applies-the-transition-it-computed.md).

**`ready-for-agent` has one other writer, and it writes it on create.** An inline
item-writing flow (`/to-tickets`, `/to-spec`, `/triage`) writes that label on each item it
files, beside the `## Touches` block and the parent edge it already writes. The label means
the item is fully specified, and the flow that wrote the specification is the one that knows
it. **The drag into the start column stays the maintainer's, and it stays the
authorisation**, so the label alone still starts nothing. A `user-story` parent takes no
work-state label at all. `hooks/refuse.py` exempts a create for this reason, and it still
denies every `edit`. Rationale:
[`orchestrator/docs/adr/0068-an-item-writing-flow-writes-the-start-label.md`](../../orchestrator/docs/adr/0068-an-item-writing-flow-writes-the-start-label.md).

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
both stack — see [Story gate labels](#story-gate-labels). The project board mirrors the
work, and a seam writes the card at three moments — see [Project board](#project-board).

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

**Neither family reaches the board.** The three card writes happen at the three moments of
the work, and no label of either family moves a card. That is one statement for both
families.

Create on first use:

```bash
gh label create refactor --color A2EEEF --description "A layer 5 story gate filed this. Provenance, not a state, so it stacks"
gh label create rating:strong --color D4C5F9 --description "The layer 5 story gate rated this candidate Strong"
gh label create rating:worth-exploring --color D4C5F9 --description "The layer 5 story gate rated this candidate Worth exploring"
```

## Project board

This repo's issues are also cards on a GitHub Projects v2 board. **The board is read in one
column and written in three, and the two sets do not overlap.** One question is asked of it:
is this item's card in the start column. **What that answer authorises depends on the item's
kind.** Three rows, and an item matches one:

| Item kind | What authorises it |
|---|---|
| `user-story` | its card sits in the start column. **No label, ever.** |
| child of an authorised story | it wears `ready-for-agent`, and every `## Blocked by` edge is closed. **Its own column is not read.** |
| standalone leaf | it wears `ready-for-agent`, **and** its own card sits in the start column. |

A story card authorises that story's whole run, so one drag starts every labelled,
unblocked child. A child with no label stays stopped. On the standalone row both facts are
necessary, and one fact on its own starts nothing. Rationale:
[`orchestrator/docs/adr/0054-the-board-is-an-input-not-a-mirror.md`](../../orchestrator/docs/adr/0054-the-board-is-an-input-not-a-mirror.md)
and
[`orchestrator/docs/adr/0062-a-story-card-authorises-its-run.md`](../../orchestrator/docs/adr/0062-a-story-card-authorises-its-run.md),
which narrows
[`orchestrator/docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md`](../../orchestrator/docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md).

Two coordinates, the name of the start column, and the three columns a seam writes:

| What | Value |
|------|-------|
| Project | <https://github.com/users/wagnersza/projects/6> — `--owner wagnersza`, number `6` |
| Start column | `To do`, between `Ready` and `In progress` |
| The spawn claim writes | `In progress` |
| The finish writes | `In review` |
| The close writes | `Done`, after the teardown |

**This file records every column by name, and never as an option id.** A write needs the
option id, and the seam resolves that id from the name at run time: the project's own id,
the `Status` field id, and the option id of the name. So the name is the whole coordinate
here, a reader compares it to the `Status` name the board answers, and a renamed column is
one edit in this file. Rationale:
[`orchestrator/docs/adr/0067-the-board-is-a-mirror-at-three-moments.md`](../../orchestrator/docs/adr/0067-the-board-is-a-mirror-at-three-moments.md).

**A repo on GitLab has a board too, and a column is a label there rather than a card.** Its
coordinates are their own table, and the rest of this section holds for both trackers. See
[The GitLab board](#the-gitlab-board).

**`Backlog`, `Ready` and the start column are the maintainer's own lanes, and nothing
writes one.** The three writes above and the one read never touch the same column, so a card
the loop wrote and the maintainer drags back stays where they put it.

**A `To do` card is not promoted to the `ready-for-agent` label.** No pass reads one fact
and writes the other, in either direction, and that holds for a story card too. The two
facts stay separate. That is what keeps `Ready` the maintainer's own lane. An item dragged
to `Ready` gains no label, and a labelled standalone leaf left in `Ready` starts nothing. A
labelled child of an authorised story does start there, because a child's own column is
never read.

**A filed item carries the label already.** An inline item-writing flow writes
`ready-for-agent` as it files the item, per the **Work-state labels** section above. So a
standalone leaf waits in `Backlog` for one drag, and a child of a story the maintainer
already dragged is startable as soon as it is filed.

### The one filtered call

```bash
gh project item-list 6 --owner wagnersza --format json --limit 500 --query '-status:Done'
```

The reader walks the answer and matches the card whose `content.number` is the item. The
`Status` name on that card is the answer, and an item with no card answers nothing.

**The filter is what keeps the read whole, and it names no column.** `-status:Done` is every
card that is not finished, which is every card a gate can act on. This board holds 188 cards
and answers 54 rows, so the limit above is ten times the answer. A card in any lane still
answers its own `Status` name, because the filter removes only the finished cards. An
unfiltered read of 100 cards was the fault this closes: a new card sits at the end of the
board, so every new item read as an item with no card.

**A card the read never returned is not a missing card.** Where the answer holds exactly as
many cards as `--limit` asked for, that answer can be one page of a longer board, so the
read fails instead of answering. A read that cannot answer must never answer "no", and the
tick reads that board as unreadable.

**The filter needs github.com, or GitHub Enterprise Server 3.20 and later.** An older host
answers an error, so the read fails and the tick reads the board as unreadable. No older
host answers "no card".

**A card with no status, an item with no card, and a repo with no board all read the same
way**, so none of the three is an error. A card the read never returned is a fourth case,
and that sentence does not cover it: it reads as unreadable, and never as a missing card. A
card in `Done` is outside the filter, so it reads as an item with no card. No gate acts on
either one, because `Done` is not the start column.

The token needs the `project` scope (`gh auth refresh -s project`). That scope covers the
read and the three writes. **A token with `read:project` alone answers every read and fails
every card write**, and a failed card write is reported and stops nothing, so the symptom is
a stale card rather than a stopped loop.

**A closed item also reaches `Done` through the board's own built-in workflow.** GitHub
Projects ships an **item closed to Done** workflow, and the maintainer enables it in the
project settings. Nothing in this repo can switch it on, because that switch is not in the
API. `/orchestrator-setup` reads whether it is on and says so. **Keep it on**: it and the
close's own write are safe beside each other, because the seam reads the card before it
writes and moves nothing that already sits in `Done`.

**A drag is intent, in every column.** No pass reads a card and writes it back, so a card
stays where the maintainer put it. The three writes above happen at the moment the work
moves, and none of them is a repair pass. A take-back is the maintainer removing
`ready-for-agent`, or writing `needs-human` with a comment that says why.

**A repo with no board leaves this section out entirely.** The board read then asks
nothing, no card write is even attempted, the `ready-for-agent` label alone is the whole
gate, and that absence is never an error.

### The GitLab board

**On GitLab a column is a scoped label on the issue, and there is no card.** A scoped label
is a label whose name carries a scope and a value, `status::to do`. GitLab keeps one label
per scope on an item, so a column move is one label write and the old value comes off
without being named. Rationale:
[`orchestrator/docs/adr/0070-a-board-column-is-a-card-or-a-scoped-label.md`](../../orchestrator/docs/adr/0070-a-board-column-is-a-card-or-a-scoped-label.md).

The scope prefix, and the four column names:

| What | Value |
|------|-------|
| Scope prefix | `status::` |
| Start column | `status::to do`, which reads as `to do` |
| In progress | `status::in progress` |
| In review | `status::in review` |
| Done | `status::done` |

**GitLab needs no project number and no owner.** Those two coordinates address a Projects v2
board, and GitLab has no such object. So a column name is the whole coordinate here, because
the label is the column. A renamed column is one edit in this table, the same as it is on the
other tracker.

**The read costs no call of its own.** Every label on an item arrives with the item read the
adapter already makes, and the column is one of those labels. So there is no board list, no
page to fill and no page-limit refusal. `scoped_column` in `scripts/tracker.py` is that
filter, and it answers the label with the prefix stripped.

**A board built on plain column labels reads as unreadable.** A plain label carries no
scope, so GitLab swaps nothing and two column labels can sit on one item at once. Neither
one is then the column. The adapter refuses, the message names the prefix it expected, and
the item stays where it is. Scope the column labels, or name no board at all.

**A GitLab project has no way to declare that it wants no board.** The two GitHub coordinates
are what a missing board looks like there, and GitLab reads neither. So the three writes below
always run on this tracker. A project whose maintainer wants no board gains three scoped labels
that nothing reads, and no read and no gate acts on them.

**The three writes work here too, at the same three moments.** The spawn claim writes
`status::in progress`, the tick that writes `to-review` writes `status::in review`, and the
close writes `status::done` after the teardown. Each one is a single label write. It adds the
label for the target column and names none to remove, because GitLab drops the other value of
the same scope by itself. So a repeat write of the same column changes nothing, and it needs
no read of the board first.

**On GitLab this write is the only thing that fills the done column.** GitHub Projects ships
an **item closed to Done** workflow, so most cards there arrive in that column before the
close writes it. GitLab has no such workflow. Both trackers end in the same column, and on
this one the orchestrator's own write is what puts the item there.

**A failed write is reported and it is never fatal**, at all three moments and on both
trackers. A spawn, a transition and a close each run whole against a board that will not
answer. The symptom is a stale column and nothing else.

**The `ready-for-agent` write works here with no change of its own**, because it goes through
the same label writer. That is the **Work-state labels** section above, and it holds a
separate family from this one. A work-state swap computes its removals from the four work
states. A column write names no label to remove at all. Neither one can reach the other's
family.

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
