# Setup makes the worker skills model-invocable

Every worker runs the mattpocock `implement` skill, and it can reach for `tdd`,
`code-review`, `diagnosing-bugs` and `pr`. Upstream ships some of them as user-only: the
`SKILL.md` sets `disable-model-invocation: true`. The worker prompt arrives as a message,
not as a typed slash command, so the worker has to invoke each skill itself, and the flag
blocks that. Every worker the orchestrator started hit it on `implement`.

The install writes more than one copy. `~/.agents/skills/<name>/` and
`~/.claude/skills/<name>/` can be separate directories, and an earlier install can leave
the flag set in either one.

## The decision

**Setup removes the user-only flag from every installed copy of the five worker skills,
on every run.** It deletes the `disable-model-invocation: true` line from each `SKILL.md`
under a dot directory of the home directory. A copy without the flag is left as it is, so
a re-run changes nothing, and a re-run repairs a skill that a `skills` update made
user-only again.

**It touches no other skill.** `setup-matt-pocock-skills` stays user-only, because a human
runs it.

**The five-skill check also fails on the flag.** It names each skill that is still
user-only and where, so setup cannot report a harness as ready while its workers would
stall on their first step.

## Rejected

- **Ask upstream to drop the flag.** The skills are user-only on purpose for a human at
  the keyboard, and the orchestrator cannot wait on another repo's release.
- **Inline the skill instructions into the worker prompt.** The prompt would fork from the
  skill, and every upstream change would need a matching change here.
- **Leave it to the user.** Removing the flag by hand does not last: the next install puts
  it back.
- **Only `implement`.** It is the one every worker runs first, but a worker reaches for the
  other four too, and each one blocks the same way.

## Consequences

Setup edits files it does not own, so a `skills update` restores the flag until setup runs
again. Codex reads its own `agents/openai.yaml`, whose `allow_implicit_invocation: false`
this does not change yet.
