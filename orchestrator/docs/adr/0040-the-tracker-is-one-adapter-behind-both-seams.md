# The tracker is one adapter behind both seams

This repo holds two seams that speak to a tracker. `scripts/worker_state.py` asks what
state a work item is in, and `scripts/close_item.py` closes one. Each seam held its own
tracker code:

- The watch grew `--tracker-cli` and `--tracker-host`, and it carried a `gh` builder and
  a `glab` builder behind them.
- The close hardcoded `gh` in one constant, and four more uses of that constant sat in
  its plan builder.
- Each seam also carried its own fixture format. One keyed the facts by tracker object,
  and the other keyed them by fact name. So a test author learned two shapes for one
  concept. The one fact both shapes held, the labels on an item, sat at two depths.

So "read and write a work item" had two interfaces in one repo. One command existed
twice, and the second copy was free to drift.

## The decision

**One module owns every tracker command both seams run or print.** It is
`scripts/tracker.py`, beside the two seams. It holds one class, and a tracker is four
values on it: the CLI name, the host, the repository and the fixture. Where two
trackers disagree about a command, the branch is inside the one method that differs.

**The commands in it are the verified ones.**
[`references/tracker-reads.md`](../../references/tracker-reads.md) holds each read as
prose with a command per tracker ([ADR 0039](0039-a-tracker-read-has-a-verified-command-in-the-skill.md)),
and this module is where the same commands live as code. A read is checked before it is
parsed there too, so no caller parses an error block.

**Neither seam names a tracker any more.** Each one keeps its own argv interface, and it
asks the adapter for a fact or for an argv. The watch keeps `--tracker-cli` and
`--tracker-host` unchanged, and the close keeps the flags it already had.

**One fixture format serves every test under `scripts/`.** One record per work item, and
one per pull request. A test author learns one shape, and a fixture that stands in for
one tracker stands in for the other.

## This reverses the deferral #86 wrote for itself

Work item #86 deferred this module with one sentence: "One tracker does not pay for the
module. Do this when a second tracker arrives." A `ponytail:` comment above the
hardcoded constant carried the same ceiling.

**A second tracker arrived, and it is in daily use.** A repo of ours runs on `glab`
against a self-hosted GitLab server. A session closed item #239 there on 2026-08-21. It
ran five steps of the **Close transaction** by hand, because the seam could reach GitHub
and nothing else. So the trigger the deferral named is met, and the module is paid for.

Two earlier records said the opposite while one tracker held. This one narrows both, and
it edits neither, per [`CLAUDE.md`](../../../CLAUDE.md):

- [ADR 0015](0015-close-is-a-deterministic-transaction.md) closed with "`gh` is
  hardcoded with its ceiling named in a comment". This item reaches that ceiling, so the
  comment goes with the constant it annotated.
- [ADR 0002](0002-delegate-tracker-to-mattpocock-skills.md) put the tracker
  configuration in the per-project `docs/agents/issue-tracker.md`, and that still holds.
  The CLI name, the host, the label vocabulary and the board coordinates are per-repo
  data, and this module reads none of them. It receives them.

## Considered Options

- **One module beside the two seams, one class, one fixture format** (chosen). A command
  has one home, and a tracker is added in one file. The seams keep their own argv, so
  every caller that works today keeps working.
- **Leave each seam with its own tracker code** (rejected). This is the state the
  deferral bought, and the price came due. The close could not run at all on the second
  tracker, and the two fixture formats cost a test author twice.
- **A plugin mechanism, a registry or a class per tracker** (rejected). Two CLIs are what
  [`references/requirements.md`](../../references/requirements.md) declares, and a branch
  inside one method is shorter than a class that holds one command. A third CLI is a
  third branch, and a registry is worth its cost no earlier than that.
- **A wrapper script per tracker, outside these seams** (rejected). A script needs its
  own tests, its own install path and its own argument surface. It also puts the exit
  code of a seam behind a process the seam cannot see.

## Consequences

- **Each tracker command exists once.** The close printed its merged-state read as a
  string, and it ran the same read as an argv. A maintainer kept the two copies in step
  by hand. Both now come from one builder, so a printed plan and a run cannot disagree.
- **The close seam gains no behaviour here.** A plan it emits for a GitHub repo is
  byte-identical to the plan it emitted before, which is the bar for a refactor of a
  working seam. The GitLab behaviour is its own work item.
- **The adapter names the trackers, and the seams do not.** A test on each seam asserts
  that. The watch already asserts the same shape of fact about a harness and a tool
  ([ADR 0018](0018-the-worker-watch-is-a-stateless-seam.md)).
- **A board read still names one tracker.** A project board is GitHub's own surface, and
  the other tracker has no equivalent. So the board commands name that CLI inside the
  adapter. A repo on the other tracker passes no board argument and reaches no board
  read. This is the behaviour both seams already had.
- **The import boundary grows one contract.** `.importlinter` already held that the two
  seams do not import each other. It now also holds that the adapter imports neither
  seam. So the shared module cannot grow a dependency on one of its callers.
