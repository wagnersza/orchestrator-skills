# A board column is a card on one tracker and a scoped label on the other

[ADR 0067](0067-the-board-is-a-mirror-at-three-moments.md) made the board a mirror of the
work state. It named one read and three writes. Every one of them addresses a GitHub
Projects v2 card, and three values address that card: the `Status` field, the option id
behind a column name, and the project number with its owner.

A maintainer who runs this plugin against GitLab gets none of that. GitLab has boards. It
has no Projects object, so a GitLab board column is backed by a **label** on the issue
rather than by a card field. The board read builds a `gh project item-list` argv, a GitLab
repo passes no board argument, and the read never runs there. So the maintainer drags an
issue into the start column and the orchestrator reads nothing.

The gap is not a missing feature on GitLab. It is one concept that this repo had recorded
in one tracker's own terms.

## The decision

**A board column is one concept with two representations, and
[`scripts/tracker.py`](../../../scripts/tracker.py) is where the difference lives.** No seam
and no skill body learns which representation it holds.

| Tracker | A column is | What addresses it |
|---|---|---|
| GitHub | the `Status` field on the item's card | the project number, the owner and the column name |
| GitLab | a **scoped label** on the item, `status::to do` and its siblings | the scope prefix and the column name |

**On GitLab the column read costs no call of its own.** The adapter already reads every
label on an item, for the **Work-state label** family. A column is one of those labels, so
the read is a filter over facts the adapter is holding. It makes no second call, it has no
page to fill, and it therefore has no page-limit refusal, which is the whole of the GitHub
board read.

**The answer is the column name with the scope prefix stripped.** So a caller compares a
column name whichever tracker it reads, and the comparison a gate makes does not branch. A
label outside the configured scope is not a column and answers empty, the same as an item
with no card.

**A board built on plain column labels reads as unreadable, and never as an item with no
column.** GitLab swaps one label for another inside a scope by itself. A plain label carries
no scope, so nothing swaps and two column labels can sit on one item at once. No one of them
is then the column. The adapter refuses, the message names the prefix it expected, and the
item stays where it is.

**The scope prefix and the four column names live in `docs/agents/issue-tracker.md`**,
beside the two GitHub coordinates and the four GitHub column names. GitLab needs no project
number and no owner, so the tracker file names neither there. A column name is the whole
coordinate on GitLab, because the label is the column.

## What this narrows

**It narrows [ADR 0067](0067-the-board-is-a-mirror-at-three-moments.md) on one point: a card
is one tracker's representation of a column, and not the concept.** ADR 0067 is written in
cards, option ids and project coordinates throughout. This decision says those words name
the GitHub half, and that the other half is a label.

Nothing else in ADR 0067 changes. The board is still a mirror. There are still three write
moments and one read column, and the two sets still do not overlap. The drag into the start
column is still the authorisation, by the three rows of
[ADR 0062](0062-a-story-card-authorises-its-run.md). A repo that names no board still runs
on the label alone.

It also holds the rule of
[ADR 0040](0040-the-tracker-is-one-adapter-behind-both-seams.md): where two trackers
disagree, the branch sits inside the one method that differs.

## Considered Options

- **The scoped label, read from the labels the adapter already holds** (chosen). It is the
  representation GitLab itself uses for a board column, and it costs nothing to read.
- **The GitLab boards API** (rejected). `GET projects/<id>/boards` answers each list and the
  label behind it. That is one call for the board and one more per list, and the answer is
  the same label the item already carries. It buys the list order, which no gate reads.
- **Pick the first plain column label where the board is not scoped** (rejected). It makes
  the unreadable case silent. Two plain column labels on one item are equally true, so a
  first-wins rule reports a column the maintainer never chose.
- **Leave GitLab with no board at all** (rejected). This is the state before this decision.
  A GitLab maintainer watches the card writes of ADR 0067 do nothing and has no way to
  authorise a start from the board.

## Consequences

- **The GitLab half is smaller than the GitHub half.** One read, no second call, no
  pagination and no truncation to refuse on. The three page-limit constants of the GitHub
  board read have no GitLab counterpart.
- **One value configures the scope, and the column names are the maintainer's own.** A board
  built on `workflow::` instead of `status::` is one edit in the tracker file, and a column
  named `doing` instead of `in progress` is another.
- **A plain-label board is a stop and not a silence.** It reads the way an unreadable board
  already reads, so the tick stays quiet and the item stays where it is. The maintainer
  scopes the labels, or names no board.
- **The GitHub path is untouched.** Its filtered board list, its page refusal and its
  option-id resolution all keep their behaviour, and its cases in the adapter suite need no
  edit.
- **The three column writes on GitLab are a decision of their own.** This ADR covers the
  read. The write is a label write, and the adapter's label writer already speaks both CLIs.
