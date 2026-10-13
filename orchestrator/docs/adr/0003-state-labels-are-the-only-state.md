# State labels are the only state

v1 kept work state in several places: labels, a Projects board mirror, checklist files and
gate records. They drifted apart, and code had to reconcile them.

## The decision

**An issue's work state is one state label on the tracker, and nothing else.** There are
four: `ready-for-agent`, `in-progress`, `ready-for-human` and `needs-human`. An issue holds
at most one. On GitHub and GitLab it is a label. On the local tracker it is the `Status:`
line. A transition swaps one value for another in one tracker call.

**The script writes every transition.** A worker never changes a label, and a session never
writes one by hand. A human writes only `ready-for-agent`: to queue an issue, or to resume
one from `needs-human` after answering it in a comment.

**The claim is the lock between people.** A claim assigns the issue to the person who runs
the orchestrator, and an issue assigned to someone else is not eligible. So one person's
orchestrator never takes another person's issue.

**The only local state is the Run id**, in a gitignored file. The tick lock is a lock, not
state.

## Rejected

- **A local state file.** It drifts from the tracker.
- **The Projects board mirror.** It is a second copy of the same fact.

## Consequences

Any tick can rebuild the whole picture from one tracker read plus one orca read. A crash
loses nothing. Two orchestrators run by the same person on two machines can both claim an
issue. That case is out of scope: run one setup per repo per person.
