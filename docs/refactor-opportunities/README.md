# Refactor opportunities

The reports the **layer 5 story gate** produces. One file per user story.

Layer 5 runs when a user story finishes. The orchestrator session invokes
`/improve-codebase-architecture` in the main checkout, and that skill writes an HTML report.
The session then saves a copy here, as a docs-only commit
([ADR 0048](../../orchestrator/docs/adr/0048-the-story-gate-report-is-a-repo-artifact.md)). The
five layers are in
[`../../orchestrator/references/quality-gates.md`](../../orchestrator/references/quality-gates.md),
and the flow is
[The layer 5 story gate](../../orchestrator/SKILL.md#the-layer-5-story-gate).

## What each file is

**A reading of the code at one commit, and not a live document.** Each report names the
commit it read. The code moves after that, so a card in an old report can be stale. Read the
work item instead, because a candidate that became work carries the current facts.

**The full evidence for a work item the gate filed.** Each report holds the before and after
diagrams, the measurements and the rating for every candidate. The work item is a summary of
one card. So the report answers "why is this a problem", and the work item answers "what do I
build".

## How a file is named

`<story number>-<slug>.html`. The story number comes first, so a file identifies its user
story with no lookup. That is the same shape a worktree name takes.

## Which candidates reach the tracker

The gate rates every candidate, and the rating decides where it goes:

| Rating | Where it goes | Rating label |
|---|---|---|
| `Strong` | a work item, labelled `ready-for-agent` | `rating:strong` |
| `Worth exploring` | the backlog, with its card attached | `rating:worth-exploring` |
| `Speculative` | dropped, with a one-line reason in the report to the maintainer | none, because it files nothing |

Every item the gate files carries four things: a reference to its user story, a link to its
report here, the `refactor` label, and one `rating:*` label.

`refactor` is provenance. It says a story gate filed the item, so it stacks with a work-state
label. A `rating:*` label carries the rating the report gave, and the family is mutually
exclusive. Neither one moves a board card. See
[`../agents/issue-tracker.md`](../agents/issue-tracker.md).

## What layer 5 does not do

**It stops nothing.** The gate holds no exit code, so it fails no push and no merge. Depth is
a judgement, and a hard gate here stalls every story on an opinion. The rationale is
[ADR 0033](../../orchestrator/docs/adr/0033-the-story-gate-is-advisory.md).

## The reports

| Story | Report | Commit read | Candidates |
|---|---|---|---|
| [#143](https://github.com/wagnersza/orchestrator-skills/issues/143) — the tracker is one verified adapter behind both seams | [`143-tracker-adapter.html`](143-tracker-adapter.html) | `a94f459` | 5, of which 1 `Strong` |

Each report loads Tailwind and Mermaid from a CDN. So a reader with no network sees the text
and the tables, and the diagrams do not draw.
