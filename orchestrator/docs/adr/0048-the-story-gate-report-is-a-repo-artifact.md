# The story gate report is a repo artifact

The layer 5 story gate ran for the first time on user story #143, on 2026-08-25. It found
five candidates and filed four of them as work items, #184 to #187.

`/improve-codebase-architecture` writes its report to the temporary directory of the OS. That
file holds the before and after diagrams, the measurements and the rating behind each
candidate. Every filed item is a summary of one card in it. The next reboot deletes it.

So four open work items pointed at evidence that no longer existed. None of them named the
story that produced them. Nothing on them said that a story gate filed them. This repo's own
rule is that a claim with no home rots ([`CLAUDE.md`](../../../CLAUDE.md)), and a gate finding
is a claim.

## The decision

**The report is a repo artifact, and the orchestrator session commits it.**

- **It lands in `docs/refactor-opportunities/`**, one file per story, named
  `<story>-<slug>.html`. The story number comes first, so a file names its story with no
  lookup and two stories never collide. That is the same shape a worktree name takes.
  `docs/automated-workflow.html` already holds committed HTML under `docs/`, so the file type
  needs no new convention.
- **The session commits it, as a docs-only commit on the default branch.** The gate runs
  `inline`, in the main checkout, and that session already writes issues, labels and board
  cards from there. A copy plus a docs-only commit is the same class of act.
- **Every candidate the gate files carries two back-references**: the user story it came from,
  and a link to the saved report. A reader who finds the item six months later reaches both.
- **The item also carries two label families, and both stack.** `refactor` says a layer 5
  story gate filed the item. `rating:strong` and `rating:worth-exploring` say what the gate
  rated the candidate. The vocabulary lives in `docs/agents/issue-tracker.md`, and neither
  family moves a board card.
- **The gate files nothing for a candidate it drops**, so that candidate carries no reference
  and no label.
- **The session copies the report, and it rewrites nothing.** This decision says where the
  report goes. It restates no heading and no section of the report itself, which
  [ADR 0033](0033-the-story-gate-is-advisory.md) already leaves with the skill.

## Two axes, and not more values on one label

`refactor` answers where an item came from. The rating answers how the gate judged it. Those
are two questions, and one label cannot hold both. `refactor` is true for every item the gate
files, and the rating differs per item. A label that folds the rating in gives
`refactor:strong` and `refactor:worth-exploring`. Then "which items came from a layer 5
review" needs one query per rating instead of one.

The two families also behave differently. Provenance never changes, so a session writes
`refactor` once and never swaps it. A rating is one value out of a set, so the rating family
swaps and never stacks. That is the rule the work-state family and the phase family already
take ([ADR 0021](0021-phase-is-a-second-label-family.md)).

## It narrows nothing in ADR 0033

Layer 5 stays advisory. It holds no exit code, it fails no push and no merge, and the
threshold stays 0 untriaged `Strong` candidates rather than 0 findings. The triage stays prose
in the orchestrator session, and `scripts/close_item.py` gains nothing from this decision.

One consequence of ADR 0033 does not hold any more. It read "**The work items are the
record.** The skill writes its report outside the repo, so nothing of the run survives the
session." The report survives, so the work items are no longer the only record. The reason the
threshold sits on the triage does not change. An unfiled candidate still reaches nobody.

## Considered Options

- **The session commits the report** (chosen) — the report is in the repo the moment the gate
  finishes. The commit is one docs-only commit, by the session that already writes to the
  tracker from that checkout.
- **The report lands untracked, and the next worker to touch the directory commits it**
  (rejected) — it leaves open the window this decision exists to close. A reboot inside that
  window deletes the file, and the filed items point at nothing again. It also asks a worker
  to commit a file it did not write and cannot check.
- **Leave the report in the temporary directory, and link it from each item** (rejected) —
  this is the state that produced four items that point at a deleted file.
- **Copy the report body into each candidate** (rejected) — it puts the skill's own report
  shape inside this repo, which ADR 0033 forbids, and four copies of one reading drift.
- **One label, with the rating folded into it** (rejected) — see Two axes, and not more values
  on one label.
- **A `## Parent` edge from each candidate back to the story** (rejected) — the candidates are
  not children of that story, and a closed parent with open children reads wrong to every
  child read the flows make.

## Consequences

- **The repo grows one HTML file per user story.** The story #143 report is 35 KB. No build
  reads the file, and no test parses it.
- **A report needs a network to show its diagrams.** It loads Tailwind and Mermaid from a CDN.
  With no network, the prose and the tables still read, and each diagram shows its own source
  text instead of a picture. That is a named limit rather than a fault to repair here, because
  the skill owns the file it writes.
- **A report is a point-in-time reading, and never a live document.** Nothing updates it after
  the copy. So a maintainer can file, fix or drop a candidate it names while the file still
  says what the gate saw.
  [`docs/refactor-opportunities/README.md`](../../../docs/refactor-opportunities/README.md)
  says so where a reader arrives.
- **The tracker answers two more questions.** A `refactor` filter names every item a story gate
  filed, and a `rating:*` filter names how the gate judged each one. Neither query existed
  before.
- **The session writes to the default branch in one more way.** It already writes issues,
  labels and board cards from the main checkout. This adds a docs-only commit, and it adds no
  code change and no branch.
