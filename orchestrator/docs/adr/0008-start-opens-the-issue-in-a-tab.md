# Start opens the issue in a browser tab of its worktree

A worker runs in an orca worktree, but the issue it works on lives on the tracker. To read
the comments a worker left, or to see which state label the issue holds, the human had to
leave orca and find the issue in a browser.

## The decision

**Each start opens the issue's web page in an orca browser tab of worktree `issue-N`**,
with `orca tab create --worktree name:issue-N --url <page>`. The tab sits beside the
worker's terminal, so the comments and the state are one click away. A resume that finds
the page already open in the worktree opens no second tab.

**The tab is a convenience, not a step of the start.** It opens after the worker starts.
A tab that fails to open is reported, and the start still succeeds, so the issue keeps its
claim. The local tracker has no web page, so a local start opens no tab.

## Rejected

- **Open the tab before the worker starts.** A tab that failed would then have to undo the
  claim, for something the worker does not need.
- **Open it with the system browser.** That leaves orca, and a tick that starts three
  workers would raise three windows over whatever the human is doing.

## Consequences

Every start makes two more orca calls, a `tab list` and a `tab create`. A human who closes
the tab gets it back on the next resume of the issue.
