# The merge is the second act, and nothing is typed

A worker finishes, and the tick writes the review state
([ADR 0056](0056-the-tick-applies-the-transition-it-computed.md)). The maintainer then
reads the pull request and merges it. From that moment the loop stopped by itself. The
item stayed open, the worktree stayed on disk, and the schedule ticked every minute.
Nothing moved until the maintainer returned to a session and typed *close 215*.

**So the second act of every item needed a human twice.** Once to merge, which is a
judgement, and once to type a verb, which is not. The verb carried no fact the tracker did
not already hold.

## The decision

**A merged pull request closes the item.** `MERGED` on the pull request whose head is the
item's branch is a deterministic fact. The tick reads that fact, closes the item, removes
the worktree and removes the schedule. **No label authorises a close, and no verb reads the
maintainer's words.**

**The tick holds the branch, and not the pull request number.** It watches one worktree, so
git answers the branch. The **Tracker adapter** answers the pull request opened from that
branch, with its number and its state, and both trackers answer it
([ADR 0040](0040-the-tracker-is-one-adapter-behind-both-seams.md)).

**The close runs in the same process as the tick.** `scripts/worker_state.py` imports
`scripts/close_item.py` and calls its plan and its execute. One process means one
**Tracker adapter** and one read of the item. The plan the close emits becomes the tick's
printed line, so the exit code and the reason stay together.

**Steps 1 to 3 of the Close transaction leave the flow.** Resolving conflicts, pushing and
merging were prose an orchestrator session ran. The maintainer merges on the tracker now, so
the session runs none of the three. A conflict is visible in the pull request, where the
tracker already shows it. **`resolving-merge-conflicts` stays available as a verb the
maintainer asks for**, and the **Skill routing** row for it is unchanged.

**`scripts/close_item.py` keeps its five steps and their order.** Its dirty-tree refusal
survives unchanged: a dirty tree refuses, and it never warns. That refusal is what protects
uncommitted work, which has no reflog. On a refusal the tick writes `needs-human` and posts
one comment that names the files.

**A tick with no teardown command closes nothing, and it says so.** A close that removes no
schedule leaves a schedule that ticks against a closed item. So the flag is the condition
for the close, rather than an option on it.

**`/orchestrator-setup` writes no terminal title.** The title existed only as a fallback
target for a wake, and the wake retired with
[ADR 0056](0056-the-tick-applies-the-transition-it-computed.md). A setup that still wrote
one configures a repo for a loop that moved.

## What this supersedes

**It supersedes [ADR 0016](0016-the-orchestrator-merges-when-asked.md) in full.** That
decision made the orchestrator session the actor for all eight steps of a **Close
transaction**, on the maintainer's typed instruction. There is no typed instruction left, and
the session runs no step of the transaction at all.

**So the three sentences ADR 0016 narrowed are true again, and each one reverts.** ADR 0016
asked a future reader who found them with no ADR to revert the change. This is that ADR, and
the revert is the point:

1. **"Never do implementation work here — spawn a worker and prompt it."** The bounded
   exception was a conflict resolution inside the item's worktree. The session resolves no
   conflict now, so the exception has no case left and the rule stands whole.
2. **"Merging is a human step."** The maintainer merges on the tracker. The sentence is a
   plain fact again, and no narrowing carries it.
3. **"merge stays a human step"** — the **Review round** entry of
   [`CONTEXT.md`](../../CONTEXT.md). Same fact, same revert.

**It narrows [ADR 0040](0040-the-tracker-is-one-adapter-behind-both-seams.md) on one point:
the two seams are no longer independent, and the dependency runs one way.** That decision
gave the layer 3 import gate a contract that said neither seam imports the other. The
contract is now a forbidden one instead: **the close seam does not import the watch**. The
tick imports the close, because the close is what a merged pull request fires. An import
back would be a cycle, and the close needs nothing the watch holds. Nothing else in ADR
0040 changes: one adapter still stands behind both seams, and it still imports neither of
its callers.

**It narrows [ADR 0037](0037-the-merge-queue-is-an-ordered-train.md) on one point: no tick
calls a Merge train.** The train was the loop's answer to an ask that named ten items. That
ask has no close behind it any more, because each merge closes its own item as it lands. The
train itself is unchanged: the three ordering steps, the park rule and one full **Close
transaction** per item all stand. `scripts/merge_train.py` keeps its contract. The train
stays as a verb the maintainer asks for. It answers the case where a maintainer wants ten
branches ordered and test-merged before they merge any of them.

## Considered Options

- **Read the merge, and close from the tick** (chosen) — the fact is on the tracker, and
  reading a fact costs one command. The maintainer's own merge is the authorisation, so
  nothing weaker replaces it.
- **Keep the typed verb** (rejected) — it asks a human to restate a decision the tracker
  already records. That is the failure mode
  [ADR 0053](0053-one-work-state-label-and-a-computed-position.md) named for the `to-merge`
  label, in a different place.
- **A `merged` label the maintainer writes** (rejected) — a second record of one fact, and
  the two can disagree. The board taught this repo that lesson once already
  ([ADR 0054](0054-the-board-is-an-input-not-a-mirror.md)).
- **Let the tick merge as well** (rejected) — the merge is the judgement in the second act.
  A tick that merged decides whether a change belongs on the default branch, with nobody
  watching.
- **Run the close as a second process** (rejected) — it costs a second **Tracker adapter**
  and a second read of the item. It also puts the plan behind a parse of another process's
  standard output, and this repo already refuses to parse prose for a fact
  ([ADR 0039](0039-a-tracker-read-has-a-verified-command-in-the-skill.md)).

## The risk accepted, and the mitigation that carries it

**An unattended tick now removes a worktree and closes a work item.** That is the one
destructive act that left a session a human can interrupt. Four things carry the risk:

1. **Two gates in front of it, and each one refuses rather than warns.** The pull request
   must read `MERGED`, and the worktree must be clean. The clean-tree gate is the one that
   protects work with no reflog.
2. **`needs-human` stops every tick on the item.** A refused close writes it with one
   comment, so the item stops after the first failure rather than on every minute.
3. **At most one transition per run.** One tick reads one item and applies one thing, so a
   wrong read cannot cascade inside one minute.
4. **A merge is a revert away.** A wrong close is a reopen away, and a removed worktree is
   a branch that is already merged. Neither one loses work.

**A pull request the maintainer merges but does not want closed has no path left.** The
take-back is `needs-human` plus a comment, written before the merge. That is the same
take-back the **Board status** entry of [`CONTEXT.md`](../../CONTEXT.md) already names, so
this decision adds no mechanism for it.

## Consequences

- `orchestrator/SKILL.md` holds no close verb table and no steps 1 to 3. The prose for every
  other flow stays, because that prose is the rollback for this wave.
- The **Close transaction** entry of [`CONTEXT.md`](../../CONTEXT.md) drops from eight steps
  to five, and the actor becomes the tick. The entry and the seam cannot disagree about what
  closes an item.
- `orchestrator/references/tracker-reads.md` gains one read: the pull request opened from one
  branch. `scripts/tracker.py` holds the same command as code
  ([ADR 0039](0039-a-tracker-read-has-a-verified-command-in-the-skill.md)).
- The fixture record for a pull request gains a `head` key, and no second fixture format
  lands ([ADR 0040](0040-the-tracker-is-one-adapter-behind-both-seams.md)).
- The tick's precheck grows three flags: the checkout, the default branch and the teardown
  command. A session resolves all three where it already resolves the rest.
- `.importlinter` trades one independence contract for one forbidden contract, so the layer
  3 gate proves the direction rather than the absence.
- **The five board coordinate flags are not this decision's work.** #199 strips them, in the
  same change that deletes the board write sites.
