# A standalone item bumps a patch, and the story sets the level

The bump rule covers one case. [`CLAUDE.md`](../../../CLAUDE.md) and
[`docs/agents/orchestrator.md`](../../../docs/agents/orchestrator.md) bump `version` in
`.claude-plugin/plugin.json` when a user story finishes, with the last child of that story.
The clause exists so that two children of one story do not each pick a number. That is the
fault it prevents.

**It names no case for a work item with no story parent.** #171 was one of those: a bug fix
to the `Start the tick` precheck block, with no `user-story` above it. By the letter of the
rule that fix takes no bump. So it shipped inside `0.33.0`, and `0.33.0` is the version that
already carried the bug. One number then named two different plugin contents. A maintainer
who has `0.33.0` cannot tell whether a card at `To merge` fires a wake. A session that reads
its own installed version cannot tell either.

PR #173 bumped to `0.33.1` by hand. That closed the ambiguity for one fix and changed no
rule.

The level clause has a second hole. It gives a minor for a story that changed a contract or a
dependency, and a patch for a docs-only story. It does not say whether the file types of the
last child can change that level. Story #163 changed a contract, and its last child #168
holds documentation only. One reading of the clause makes that pair a patch, and the other
makes it a minor.

## The decision

**A work item with no `user-story` parent bumps a patch, in its own branch.** The condition
is that the item changes what an installed session or a seam does. The number then keeps
answering "which contents", which is the question a version answers.

**An item that changes only this repo's own files bumps nothing.** `CLAUDE.md`, a page under
`docs/`, an ADR and a test are each outside what an installed session obeys. A bump there
moves the number and ships nothing, which is the same lie in the other direction.

**The story sets the level, and the file types of its last child never change it.** A
documentation-only last child of a contract-changing story still takes the minor. The level
reads the story, because the story is the unit that moved the contract.

**The story clause stands unchanged.** A story bumps once, with its last child, and never
once per work item. A worker on one child leaves the version untouched. Two children that
each bump pick the same number, and the merge then keeps one bump and loses the other.

This decision narrows the "only when a user story finishes" half of the earlier rule. So it
gets an ADR instead of a silent edit, per [`CLAUDE.md`](../../../CLAUDE.md). The rule keeps
its two homes: the project rules in `CLAUDE.md`, and the Notes of
[`docs/agents/orchestrator.md`](../../../docs/agents/orchestrator.md). Both link here.

## Considered Options

- **A patch on a standalone item that changes what the plugin does** (chosen) — one line per
  behavioural fix, and the number stays true. It needs no release step and no new tool.
- **No bump on a standalone item, and a release step that moves the version** (rejected) —
  this repo has no release step today, so the option is a new flow and not a rule. It also
  holds the number back. A fix merges, a user installs the plugin from the default branch,
  and the version still names the contents that carried the bug. The fault this ADR closes
  then survives between releases, which is the state #171 was in.
- **A patch on every standalone item, whatever it touched** (rejected) — a typo fix in an ADR
  then moves the number. A reader who compares two versions finds nothing that changed for
  them, so the number stops meaning anything.
- **A minor on a standalone item that changes behaviour** (rejected) — a minor says a
  contract moved. A standalone fix restores behaviour that the contract already promised, so
  a patch is the honest level. An item that does move a contract has a story above it.
- **The file types of the last child set the level** (rejected) — a contract-changing story
  then ships as a patch, because its last child holds documentation. The order of the
  children is an accident, and the contract is not.
- **Silence, and a judgement call per item** (rejected) — the state this ADR replaces. Two
  sessions read the same silence and pick different answers. #171 shows which answer loses.

## Consequences

- **Two standalone items in flight can pick the same patch number.** This is the collision
  the story clause already names, and the resolution is the same. The merge keeps one bump,
  and the second branch takes the next patch. Nothing checks this, so the second worker reads
  the version again at the merge.
- **The condition is a judgement, and no gate reads it.** "What an installed session or a
  seam does" needs a reader. Enforcement here is documentary, as it is for every other rule
  in this repo ([ADR 0032](0032-quality-gates-are-a-layered-contract.md)).
- **Accepted risk: a mixed item bumps.** An item that edits a skill body and a page under
  `docs/` in one branch takes the patch, because the shipped half decides. So a bump can land
  beside a change that ships nothing.
- **Named limit: `docs/architecture.html` restates the story half alone.** That page holds a
  target design and a version plan, and it is not a home for this rule. It keeps its own
  text, and the two files above are the rule.
