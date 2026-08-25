# Refactor opportunities

When a user story finishes, the layer 5 story gate runs
`/improve-codebase-architecture`. That skill writes one HTML report. This directory holds the
saved copy of each report, one file per story.

The name is `architecture-review-<story>-<YYYYMMDD>.html`: the number of the user story, then
the day of the run. The story number is what keeps two stories apart.

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
| [`architecture-review-143-20260825.html`](architecture-review-143-20260825.html) | #143, "The tracker is one verified adapter behind both seams", read on 2026-08-25 |
