# Adversarial review and the merge train are verbs

Two flows sat inside the automated loop, and neither one belongs there. An
**Adversarial review** ran as a bounded fix loop that a **Worker watch** drove. A **Merge
train** ran as an ordered pass over a **Merge queue**. Both leave the loop here. Both stay
as a verb the maintainer asks for.

The two halves share one shape, which is why they share one file. Each held a seam inside
the loop. Neither seam produced a fact the loop can act on.

## A judgement has no exit code

A **Review round** asked the tick to read an opinion. The reviewer posted a `Verdict:`
line, and the tick parsed that line into a transition. So a model's judgement became the
input of a deterministic gate.

That is the wrong shape, for three reasons.

**A gate needs a fact, and a verdict is not one.** Every other outcome the tick reads is a
fact on disk or on the tracker: a ticked box, a green **Gate record** line, a live process,
a merged pull request. Each one is true or false whatever model reads it. A verdict is one
model's opinion of a diff, and a second run of the same reviewer can reach the other value.
The tick then writes a different label from the same code.

**A missing line is silence, and not a false answer.** A reviewer that forgot the literal
fired no transition at all. The impl worker waited, the findings never arrived, and nothing
reported an error. So the loop's one signal was a string a model had to remember to type.

**A round counter is state a restarted session misreads.** The count was the number of
`Verdict:` comments, which kept it off disk and out of a session's context. It still put a
bound in config that two readers had to agree on: the loop's own prose, and the tick's
`--rounds`. Issue #157 reported that disagreement before it closed as not planned.

**So the review leaves the loop, and it keeps one entry.** `review N` spawns a reviewer on
the item's branch, and the reviewer posts one comment. There is no round, no `Verdict:`
literal, no fix loop and no counter. The maintainer reads that comment beside the diff, the
same way they read the work item's review note.

## An order you pick needs no seam inside the loop

A **Merge train** never merged anything. It resolved an order and handed that order to the
maintainer, who merged on the tracker
([ADR 0057](0057-the-merge-is-the-second-act.md)). So the ordering was already advice, and
the act was already the maintainer's.

Advice that a human reads needs no place in an unattended loop. Nothing wakes to compute
it, and nothing acts on it. **A tick that computes an order and writes nothing is a tick
that spent a minute for no transition.**

**So the train leaves the loop, and it keeps one entry.** The maintainer asks for the
order, this session runs `scripts/merge_train.py`, and it reads the JSON plan. The plan
runs in a throwaway checkout and mutates nothing.

## What this narrows

**[ADR 0003](0003-cross-vendor-adversarial-review.md) keeps its body, and loses its
loop.** The cross-vendor rule survives whole: a reviewer runs a different vendor's model,
config names that model in `models.review`, and the prompt asks for coverage rather than
filtering. What retires is the bound, the `Verdict:` line, the fix round and the effort
step per round.

**[ADR 0037](0037-the-merge-queue-is-an-ordered-train.md) keeps its ordering, and loses
its trigger.** The three ordering steps, the park rule and the seam's contract all stand,
and `scripts/merge_train.py` is unchanged. What retires is any path from a schedule to a
train. ADR 0037 already rejected "the automation merges by itself" and ADR 0057 already
took the merge out of every session. This ADR finishes that line: no tick reaches a train
at all.

**The seam stays, and its caller changes.** `scripts/merge_train.py` and its test suite
are untouched. A verb calls it now, and nothing unattended does.

## Considered Options

- **Both flows become verbs** (chosen) — each keeps the one entry a human already used, and
  the loop keeps only outcomes it can prove. A reviewer's opinion reaches a human who can
  weigh it, and an order reaches the human who performs the merges.
- **Keep the rounds, and make the reviewer's verdict advisory** (rejected) — the tick then
  reads a `Verdict:` comment and writes no label for it. That is a parse with no consumer,
  so the literal stays a rule a model has to remember for nothing.
- **Keep the rounds, and gate on a machine-readable finding count instead** (rejected) —
  a count of findings is still the reviewer's own count. A model that reports zero findings
  is making the same judgement, with the opinion hidden inside a number.
- **Let the tick run the train on a schedule** (rejected) — already rejected by ADR 0037,
  for the reason that still holds: an **Item automation** writes no label, spawns nothing
  and merges nothing.
- **Delete `scripts/merge_train.py` with the loop step** (rejected) — the ordering is the
  part a machine does better than a maintainer's eye, and a verb needs it exactly as much
  as a tick did.
- **Delete adversarial review outright** (rejected) — a different-vendor reader catches
  what the implementing model rationalised, and that value never depended on the loop. It
  costs one verb to keep.

## Consequences

- **The tick loses three outcomes**: `verdict-approve`, `verdict-request-changes` and
  `rounds-exhausted`. It loses `--rounds` and `--review` with them, so no round bound
  reaches the seam from config.
- **A finish always writes the review state.** Nothing holds that swap any more, so
  `implementation-complete` has one behaviour rather than two.
- **A Position has two values, and not three.** The review-round value read a `Verdict:`
  comment, and no seam reads that literal now. So the rule is the `to-review` label, and
  then implementation ([ADR 0053](0053-one-work-state-label-and-a-computed-position.md)).
- **`Re-prompt:` is the one counted literal left.** Its count is the retries a stalled
  worker already got, and that count is a fact the tick itself wrote
  ([ADR 0058](0058-one-re-prompt-then-a-human.md)). So the shape survives on the one signal
  whose author is the seam.
- **Config drops `review.enabled` and `review.rounds`.** Neither one has a reader left.
  `models.review` stays, because the verb resolves the reviewer's model and effort from it.
- **A review's findings reach a human, and never a worker.** Nothing re-prompts the impl
  worker with them, so nothing steps its effort up a rung. The maintainer decides what a
  finding is worth, which is the decision they already make on a pull request.
