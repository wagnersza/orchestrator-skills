# The board is an input, not a mirror

[ADR 0009](0009-labels-drive-board-status.md) made a card's `Status` field a projection of
the **Work-state labels**. That projection had seven writers. One was code, in
`scripts/close_item.py`. The other six were instructions in `orchestrator/SKILL.md`: the
spawn claim, each wake transition, the **Ready queue** reconcile, the advance-not-close
row, the **Merge train** park, and the end of the **Story proof**.

A session can skip any one of the six. Nothing reads the card afterwards, so a skipped
write shows as a wrong column and never as an error. #186 reported the same cost one layer
down, in the **Tracker adapter**: one board recipe with two implementations, because the
write needs a card id and the read needs a status name.

## The decision

**The board is an input, and one question is asked of it: is this card in the start
column.** That is the second fact of a **Ready queue** entry, beside the
`ready-for-agent` label ([ADR 0045](0045-a-story-start-is-automatic-under-two-roofs.md)).
`Tracker.board_status` answers it, and the tracker fixture keeps its `board` key for the
same reason. On this repo's board the start column is `To do`.

**Nothing writes the board.** All seven writers go. `card_argv` and `board_card` leave the
**Tracker adapter**, because each one exists only to write a card. `scripts/close_item.py`
loses `--project-number`, `--project-owner`, `--project-id`, `--status-field-id` and
`--done-option-id`, and the card write they fed. **The eight steps of a Close transaction
keep their order, and the dirty-tree refusal does not change.**

**The derivation table goes with them.** A projection that nobody writes is not a
projection. So `docs/agents/issue-tracker.md` loses `### Deriving Status`, the `Status`
field id, the option id map and the two `gh` calls.

**Two coordinates replace five ids.** They are the owner, the project number, and the name
of the start column. One read needs no field id and no option id, so the token needs
`read:project` and no write scope. A leaked token then cannot change the project.

**The board's own built-in workflow moves a card to `Done`.** GitHub Projects ships an
**item closed to Done** workflow. `/orchestrator-setup` reads whether it is on, and it says
so plainly. **It cannot switch it on, because that switch is not in the API.** This is the
one part of setup that a human must do.

**A drag is intent in every column now.** ADR 0009 made a drag drift, and the reconcile
pass overwrote it. No pass writes a card, so a card stays where the maintainer put it.

**No board is still a supported configuration.** A tracker file with no `## Project board`
section leaves the board read with nothing to ask, and the label alone is the whole gate.
That absence is never an error, and `scripts/test_tracker.py` covers it.

## What this supersedes

**It supersedes [ADR 0009](0009-labels-drive-board-status.md) in full.** Four claims of it
are retired: the projection itself, the derivation table, the reconcile pass that repaired
drift, and the write beside every label write. Its sentence that reads a human drag as
drift is retired with them. Its chosen option was "labels authoritative, board derived",
and the board is derived from nothing now.

**Two of its consequences survive as facts rather than as decisions.** Board coordinates
are still per-repo data in `docs/agents/issue-tracker.md`
([ADR 0002](0002-delegate-tracker-to-mattpocock-skills.md)). A repo with no board still
runs on labels alone.

**It supersedes [ADR 0038](0038-the-to-merge-column-is-intent.md) in full.** That ADR made
one column an exception to ADR 0009. `To merge` was intent, and every other column stayed
a projection. Both halves are gone.
[ADR 0053](0053-one-work-state-label-and-a-computed-position.md) deleted the `to-merge`
label the promotion wrote, and this decision deletes the projection. So no rule is left for
one column to be an exception to.

**No old ADR file is edited here.** The ledger pass that marks every retired ADR is a later
item, which is the posture ADR 0053 took. This one writes its own record, and the live
surfaces are what stop naming a deleted rule.

## Considered Options

- **The board is an input, and nothing writes it** (chosen). One question, one reader, and
  no writer. A write that does not exist cannot be forgotten, which is the class of fault
  that #186 and the seven-writer count both report.
- **Keep the projection and repair the drift** (rejected). The reconcile pass was already
  that repair, and it ran only where the maintainer asked "what next?". A pass that repairs
  a cache is a third place the same fact lives.
- **Keep one write, at close, and drop the other six** (rejected). The built-in workflow
  writes `Done` for free, and nobody can skip it. One write in code keeps all five board
  ids, the write scope on the token, and `card_argv` with it. It buys a column the board
  already sets.
- **Delete the board read as well** (rejected). The start column is how the maintainer
  starts a **Story run** by hand, and no label carries that fact
  ([ADR 0045](0045-a-story-start-is-automatic-under-two-roofs.md)). One cheap read keeps
  it, and that read needs no write scope.
- **A second field for the start column** (rejected). That is one more field to create and
  one more id to resolve, for a fact the `Status` field already holds by name.

## Consequences

- **The maintainer enables the item closed to Done workflow, before this lands.** After
  this change nothing writes `Done`. A repo with that workflow off then shows a closed item
  whose card still sits in `In review`. Setup reports the switch, and the review note of
  the item that lands this says it too.
- **The maintainer deletes the columns the repo stops writing.** That is a board edit, and
  a session makes none. An unused column costs nothing until they remove it, which is the
  posture ADR 0053 took for `To merge`.
- **The token loses its write scope, and that narrowing is one-way.** A repo that runs
  `gh auth refresh -s read:project` can still read the board. A later decision that wants
  a write back needs the scope back too.
- **The close plan holds one write fewer, and step 7 keeps its shape.** The label, the
  optional closing note and the close still share one step.
  `scripts/test_close_item.py` asserts the parts of that step by name, so a card part that
  comes back fails a test.
- **Accepted risk: a card nobody moves reads as stale.** A card in `To do` stays there
  while its worker runs, because the start column is read and never written. The item's own
  label is the live state, and the board is not. A maintainer who reads the board as
  progress reads the wrong surface.
- **The rollback is a revert.** The board is data, so a revert restores the writers and
  leaves no data to repair. The five ids stay in the git history of
  `docs/agents/issue-tracker.md`, and setup resolves them live in any case.
