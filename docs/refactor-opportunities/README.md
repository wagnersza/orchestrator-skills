# Refactor opportunities

When a user story finishes, the layer 5 story gate runs
`/improve-codebase-architecture`. That skill writes one HTML report. This directory holds the
saved copy of each report, one file per story.

The name is `<story>-<slug>.html`: the number of the user story, then a short slug from its
title. The story number comes first, so a file names its story with no lookup, and two stories
never collide. That is the same shape a worktree name takes.

**The orchestrator session writes the file.** It runs the gate in the main checkout, on the
default branch, and it commits the copy from there as a docs-only commit
([ADR 0047](../../orchestrator/docs/adr/0047-the-story-gate-report-is-a-repo-artifact.md)).

**A report is a point-in-time reading, and never a live document.** It records one commit on
one day. Nothing updates it after the copy, and a later story writes a new file beside it. So a
maintainer can file, fix or drop a candidate a report names, while the file still says what the
gate saw.

Every work item the gate files links back to the report it came from. Each one also carries the
`refactor` label and one `rating:*` label, and
[`docs/agents/issue-tracker.md`](../agents/issue-tracker.md) defines both families.

Each report loads Tailwind and Mermaid from a CDN. With no network, the prose and the tables
still read, and each diagram shows its own source text instead of a picture.

| Report | Story |
|---|---|
| [`143-tracker-adapter.html`](143-tracker-adapter.html) | #143, "The tracker is one verified adapter behind both seams", read at `a94f459` on 2026-08-25 |
