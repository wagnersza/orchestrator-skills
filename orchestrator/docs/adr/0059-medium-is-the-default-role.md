# Medium is the default Role, and every other Role needs a named signal

`0005-role-based-model-and-effort.md` gave config a `(Model, Effort)` pair per
**Role** and named three: `heavy`, `light` and `review`. It set the default with
them. Take `heavy`, and drop to `light` only on clear signals.

Two implementation rungs do not match the work. A `light` item is one file with
every acceptance criterion written out. A `heavy` item changes a contract, a schema
or a code seam. The ordinary work item sits between the two, and it had no rung of
its own. So a session rounded it up to `heavy` and paid the strongest model for a
job that did not need one.

The default made that the safe answer. "Downgrade only on clear signals" reads as
an instruction to treat a doubt as a signal for `heavy`, and almost every item
carries a doubt. One project already fought the result:
`docs/agents/orchestrator.md` carried a `role_default: light` key to invert the
rule for that repo alone. Two opposite defaults then lived in one skill, and a
session had to read a project file to learn which one applied.

There are now four Roles, and `medium` is the third implementation rung. A spawn
takes `medium`. It takes `heavy` only where one listed signal fires, and it takes
`light` only where all three listed conditions hold. A doubt is not a signal. The
spawn report names the signal that moved the item off `medium`, so a wrong call is
visible in one sentence.

`role_default` is deleted. The key existed to invert a default that is now
inverted in the skill itself, so it has nothing left to say. A project that wants a
different pair edits the `models:` block, which it could always do.

This ADR reverses one decision of ADR 0005 and leaves the rest of it standing:
pairs per Role in config, classification at spawn time, harness clamps that get
reported, and thinking on at every effort. `references/models.md` holds the two
signal lists, the step-up rule and the three **Cost profile** blocks.

## Considered Options

- **A third Role, `medium`, and `medium` as the default** (chosen) — the middle is
  where most work items sit, so the default belongs there. A Role is the unit
  config already keys on, so the rung costs one column in the `models:` block and
  one row in each Cost profile. Both moves off the default now cost a named signal,
  which is a fact about the item rather than a feeling about it.
- **Keep two Roles and tune effort only** — no new Role, and the middle item runs
  `heavy` at a lower effort. Rejected because it keeps the wrong model. The middle
  item wants `sonnet-5`, and effort cannot change which model a Role names. It also
  leaves the default at `heavy`, which is the half of ADR 0005 that hurt most.
- **Add the rung as an effort value with no Role of its own** — express the middle
  as a sixth point on the effort ladder. Rejected because effort and Role are two
  axes, and this collapses them. The ladder already holds five values that every
  harness maps, and two of them clamp at the top. A new value there changes every
  harness reference to say something about model choice, which is not what effort
  means.
- **Let each project invert the default with a config key** — keep
  `role_default`, and let each project set it. Rejected because it is the state
  this ADR ends. One skill with two defaults makes every rule about routing
  conditional on a file the rule does not name, and the one project that set the
  key set it to the value this ADR makes global.

## Consequences

- **Ambiguity resolves to `medium`, not upward.** The expensive failure that ADR
  0005 named is still real, and a `medium` worker that under-thinks still burns a
  round trip. The trade is deliberate: `heavy` on every doubt pays the top rate on
  every item, and that is the larger bill.
- **`heavy` costs a sentence.** A spawn that wants the strongest model names which
  listed signal fired. A spawn report with no named signal is a routing error.
- **`role_default` goes away, and one default is global.** Every project reads the
  same routing rule. Editing the `models:` block stays the way to change a pair.
- **Each Cost profile gains a row.** `conservative` gives `medium` and `light` the
  same pair, because `low` is the bottom of the effort ladder and `sonnet-5` is the
  cheapest model in the registry. That collision is a property of the ladder, not
  an error in the profile.
- **The step-up ladder gains a rung.** `light` steps to `medium`, `medium` steps to
  `heavy`, and a failed `heavy` round steps its effort up instead of its Role.
- **The Role name `medium` and the effort value `medium` are now the same word on
  two axes.** A pair is always written as model plus effort, so `sonnet-5` @
  `medium` reads unambiguously. Text that names a Role alone says "Role" or writes
  the word in the Role list.
