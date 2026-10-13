# The session merges on request

v1 kept the merge with the maintainer, on the tracker, and no session merged
([v1 ADR 0057](https://github.com/wagnersza/orchestrator-skills/blob/v1.0.0/orchestrator/docs/adr/0057-the-merge-is-the-second-act.md)).
The teardown then needed a second act after the merge. That made "merge it and clean up"
two steps for the human.

## The decision

**This reverses v1 ADR 0057. The human's own "merge N" is the authorisation.** The session
runs `merge N`, and the script merges the PR and tears down.

**The merge refuses unless every precondition holds**, and a refusal changes nothing:

- The issue is `ready-for-human`.
- The worktree `issue-N` holds no uncommitted work.
- The tracker allows the merge. On GitHub and GitLab the PR is mergeable and has no
  changes requested. On the local tracker the main checkout is clean and on the base branch.

**A merge made on the tracker is honoured too.** The next tick sees the merged PR and runs
the same teardown.

**Teardown runs only after the tracker confirms the merge.** It releases the worker,
removes the worktree, then drops the state label and closes the issue.

## Rejected

The human-only merge on the tracker. It kept the human in the loop, but it needed a second
act for the teardown.

## Consequences

No session merges unless a human asks for that one issue in person. A tick never merges on
its own: it only tears down a merge the tracker already reports.
