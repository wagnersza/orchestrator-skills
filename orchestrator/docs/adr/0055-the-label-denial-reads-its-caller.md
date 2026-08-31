# The label denial reads its caller

[ADR 0051](0051-a-hook-refuses-and-a-seam-performs.md) named the caller test as the way to
tell a seam from a hand-typed command. `teardown_denial` reads it, but `label_denial` did
not. So the hook denied the write it exists to let through: the close seam's own
`--remove-label` and `--add-label` flags. The four stale labels on #209, #213, #231 and
#234 are the cost of that gap.

## The decision

**`label_denial` reads its caller before it reads the words.** A command that names
`close_item.py` anywhere returns no denial, the same test `teardown_denial` already runs.
A hand-typed write with no seam in the line stays denied.

**The two denials share one rule now, not two.** Both ask "does this command name the
close seam" before they ask what the command carries. A caller test with two spellings is
the failure mode ADR 0051 already named.

## What this supersedes

**It narrows [ADR 0051](0051-a-hook-refuses-and-a-seam-performs.md) on one point: the
label denial gains the caller test the teardown denial already held.** ADR 0051 stated the
plane law — a hook answers, and a seam performs — and it did not say each denial must read
its caller the same way. This decision states that the two denials must. Nothing else in
ADR 0051 changes: the hook still fails open, still copies no vocabulary, and still exits
fast where the repo carries no marker.

## Considered Options

- **The caller test on both denials** (chosen). One rule, one test, and the sibling
  functions read alike.
- **A second, separate exemption list for the label denial** (rejected). A second list is
  a second place for the same fact, and it drifts from the teardown list the first time
  someone edits one list and not the other.
- **Match the caller on the plugin root path, not the file name** (rejected). `CLOSE_SEAM`
  is already a substring match on `close_item.py`. A path match adds a case the fixture
  must guess at, and the test suite already fixes the seam at
  `/plugin/root/scripts/close_item.py` for the teardown test. The label test reuses that
  same fixture.

## Consequences

- **A hand-typed command that names `close_item.py` as a bare word, with no real call, now
  goes through too.** The teardown denial already accepts this same risk. This decision
  extends it rather than starting a new one.
- **A compound command permits on the side of the seam.** `permit-seam-call &&
  hand-typed-write` goes through in full, because the caller test reads the whole
  command's words and not each command in the chain on its own.
  `hooks/test_refuse.py` states this plainly, so the behavior is a named fact and not a
  silent gap.
- **The rollback is a revert of one function.** `label_denial` returns to reading only the
  words, and the four items this repairs go stale again the next time a close runs.
