# The orchestrator session writes the review state, and the worker stops at its note

Three files described the end of implementation, and two of them agreed. The last box of
[`orchestrator/references/checklist.template.md`](../../references/checklist.template.md)
tells the **Worker** to flip the work item to the review state and move its board card.
[`docs/agents/issue-tracker.md`](../../../docs/agents/issue-tracker.md) says `in-progress`
is "Held through the whole adversarial-review loop". Step 4 of *Adversarial review* in
[`orchestrator/SKILL.md`](../../SKILL.md) agrees with the tracker config. **So the
checklist is the file that is wrong.**

The first live run showed the cost. The work item wore `to-review` from the end of
implementation, through the reviewer, through the fix round, to the end of the loop. The
label said a human owned the item while a worker still did.

**The maintainer holds one rule: `to-review` means the phase axis is complete and a human
owns the item.** The label answers *"does a human own this now?"*, and it answers nothing
else.

So the worker's last box becomes one act: post the review note, and stop. The
**Orchestrator** session writes `to-review` **in one call with the removal of
`phase:review`**. The **Board status** write moves with that call. Where **Adversarial
review** is off, the same rule holds: the wake that removes the phase label writes the
review state.

## One moment, one write, one owner

[ADR 0021](0021-phase-is-a-second-label-family.md) made **Phase** and the **Work-state
labels** two independent axes, and they stay independent. They coincide at exactly one
moment, the end of the phase axis. ADR 0021 says so itself: "removing the phase label *is*
that transition", and the item then "wears `to-review` alone".

Two labels that name one moment must move together. Split them, and a reader finds one of
two states that resolve to nothing: `in-progress` with no phase label, or `to-review`
beside `phase:review`. ADR 0021 refused a `phase:human` value on that exact ground — "the
two must then be written together and read together. A run that sets one and not the other
is a state no reader can resolve." **This ADR applies that sentence to the write rather
than to the vocabulary.**

One owner follows from one write. The session already owns the phase axis at both ends:
the spawn writes `phase:impl`, and *On the wake* writes the `phase:*` label as the first
act of every transition after it. A worker cannot own half of a paired write.

## Why the worker's box was wrong, and not merely early

A worker that flips `to-review` at its note is not early by a minute. It is wrong for the
whole review loop, which is up to three **Review round**s plus a fix round for each. A
worker owns the item through all of it.

The worker also has no inputs for the decision. Whether **Adversarial review** is on,
whether a proof phase applies, and which round the item is on are **Config** and
**Tracker** facts the session resolves. So the box asked a worker to announce the end of an
axis it cannot see the end of.

## This narrows ADR 0013 and ADR 0021

[ADR 0013](0013-workers-commit-in-contextualised-slices.md) owns what a worker's checklist
holds as a contract. Its Consequences name "the checklist template a worker ticks, and the
skill body that explains the box" as where its rule lands, and the last rewrite of that
file applied this ADR. **So removing half of a box narrows ADR 0013's contract**, even
though that box is older than the ADR. ADR 0013's own rule is untouched: a slice is still
one logical change, and the branch is still self-consistent at each commit.

This ADR narrows ADR 0021 on one point. Its accepted risk names ordering as the
mitigation — "the session writes the phase label as the first act of every transition".
That mitigation now covers a second label. At the final transition there is no first act
and no second act to get wrong, because one call carries both.

This is a new ADR and not an edit to either older one, per
[`CLAUDE.md`](../../../CLAUDE.md). Both keep their own text.

## Considered Options

- **The session writes both labels in one call, and the worker stops at its note**
  (chosen) — one moment, one write, one actor. `to-review` then answers the question the
  maintainer asks of it, and the two axes meet in one place that a session already owns.
  The worker's contract gets shorter rather than longer.
- **Keep the worker's box, and change the tracker config to match it** (rejected) — that
  reverses the maintainer's rule instead of recording it. The live run showed what the
  reversal costs. `to-review` then means "implementation is done", which no session and no
  human needs, and the question *"does a human own this?"* loses its label.
- **The worker writes `to-review`, and the session removes the phase label** (rejected) —
  the state before this ADR, and the defect. Two actors, two network writes, and an order
  neither of them controls. Every interleaving that fails leaves a state no reader can
  resolve.
- **The worker writes both labels, so one actor still owns the pair** (rejected) — the
  worker cannot resolve whether review is on. So it cannot know that the phase axis is
  complete at its note. It writes the end of an axis whose next step is a reviewer it never
  hears about. It also holds no board field ids that it was not handed.
- **A fourth `phase:human` value, so one axis carries the whole answer** (rejected, again)
  — ADR 0021's rejection stands and its reason is unchanged: the value restates
  `to-review`, and two records of one fact drift.
- **Read "no phase label" as human review** (rejected) —
  [ADR 0009](0009-labels-drive-board-status.md) makes the work-state labels the source of
  truth for `Status`. An item with no `to-review` label forces a second condition on every
  consumer of that label. The board derivation grows one too, over a second family.

## Consequences

- **The worker's contract loses one act and gains none.** Its last box becomes: post the
  review note, and stop. The board commands leave the spawn prompt with the label, so
  `SKILL.md`'s "The worker flips its own card" paragraph goes with them.
- **`docs/agents/issue-tracker.md` needs no edit.** It already holds `in-progress` through
  the whole review loop. This ADR makes the other two files agree with the tracker config,
  which is [ADR 0002](0002-delegate-tracker-to-mattpocock-skills.md)'s rule: the tracker
  config owns the labels.
- **Where review is off, there is no second rule.** The `implementation-complete` wake
  removes the phase label, and that same call writes `to-review` and the card. So a repo
  with review disabled reads one sentence, not an exception.
- **A finished worker waits for the tick, and that is the accepted risk.** Between the
  worker's note and the session's write, the item wears `in-progress` and `phase:impl`
  with nobody working on it. The tick closes that window in about a minute. Where a
  **Tool** has no automation surface, the window lasts until the maintainer looks. The
  wait costs one late hand-off to a human and destroys nothing. ADR 0021 accepted that same
  cost for a wrong reading of its own axis.
- **This ADR declares the owner and wires nothing.** The checklist template's last box,
  the board commands in the spawn prompt, and the wake rows in `SKILL.md` are separate
  work. Until they land, a worker flips its own review state exactly as it does today.
