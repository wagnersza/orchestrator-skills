# A fork may carry one local change: the invocation overlay

Every skill a **Fork** registers is made **model-invocable** on that fork, by
deleting two keys and nothing else — `disable-model-invocation: true` from
`SKILL.md` frontmatter, and the `policy.allow_implicit_invocation: false` block
from `agents/openai.yaml`. That deletion is the **invocation overlay**. It is
applied by `scripts/invocation_overlay.py`, recorded in the fork's `FORK.md`, and
re-applied after every **Promote**.

The orchestrator spawns workers with `--dangerously-skip-permissions` and drives
them through a file-based checklist. There is no human in a worker session. A
skill marked user-invoked-only is reachable *only* by a human typing its name — no
model can fire it, and no other skill can reach it either. Upstream's own
`.agents/invocation.md` says as much, and it is the right split for interactive
use. Under an orchestrator it means a skill that never runs. In
`mattpocock-skills@mattpocock` at the pinned SHA that was 13 of 22 registered
skills, `implement`, `to-tickets`, `to-spec`, `triage` and `wayfinder` among
them — the ones the orchestrator drives most.

This reverses ADR 0007's "**Local changes:** none, and none intended". It narrows
that rule rather than dropping it: **one** overlay, deleting **two known keys**,
touching no skill body, name, description or reference file. Everything else about
the fork is unchanged — it still pins a version rather than developing one.

## Why this can stay a fast-forward

The obvious objection is that a fork carrying local changes can no longer take a
promote as a fast-forward, and `fast_forwardable()` in `scripts/fork_state.py`
refuses rather than force-pushes. Left alone, the overlay would refuse every
promote forever, by construction.

So `overlay_diff()` decides on **diff content, not on filenames**. A path diverges
acceptably when its diff is deletions only, and every deleted line is one of the
two overlay keys or the `policy:` header that held one. A commit that edits a
skill body — even in a file the overlay also touches — adds or deletes something
else, so `pinned_at()` reports the dial as moved and the promote is refused, which
is what ADR 0007 wanted the check to catch. Path-allowlisting the overlaid files
would have been simpler and would have let a body edit through under cover.

The overlay is a deletion of keys upstream re-introduces, so an upstream commit
adding a new user-invoked skill silently un-overlays it. That is why it is a
re-runnable script and step 7 of bootstrap rather than a hand-edit, and why
`FORK.md` carries the re-apply command: after a promote, run it again. It is
idempotent — a clone with nothing to strip reports exactly that.

## Considered Options

- **Overlay the fork, content-checked** (chosen) — the skills become reachable
  without a prompt-side workaround, and the promote path still refuses a real
  local commit. Costs a re-apply step after every promote and a merge conflict
  whenever upstream edits a frontmatter block the overlay also touches — narrow,
  because the overlay touches two lines per skill.
- **Leave the forks pristine; have the orchestrator type the slash command** — a
  slash command in a spawn prompt arrives as user input, so `/implement` fires
  today with no fork change at all. Rejected as insufficient rather than wrong:
  it covers the spawn prompt and nothing else. The model cannot reach the skill
  mid-session when the work turns out to need it, and a user-invoked skill still
  cannot reach another user-invoked skill, so `/wayfinder` calling `/to-tickets`
  stays broken. It remains the correct fallback while a fork is un-overlaid.
- **Fork and rewrite the descriptions too** — model-facing trigger phrasing would
  fire more reliably than upstream's stripped human-facing one-liners. Rejected
  for now: it is an edit to content rather than a deletion of a key, so
  `overlay_diff()` could not distinguish it from a body edit, and every upstream
  description change would conflict. Revisit only if a skill measurably fails to
  trigger.
- **Patch the flags in `~/.claude/plugins/cache/` after each install** — no fork
  divergence, and it evaporates on the next `claude plugin update` with nothing
  recording that it ever existed. That directory is Claude Code's (ADR 0007).
- **Ask upstream to drop the split** — the split is correct for upstream's
  interactive users; this is a disagreement about our deployment, not a bug.
  Contributing back is out of scope (ADR 0007).

## Consequences

- `bootstrap` grows a **step 7**, after the marketplace swap: apply the overlay,
  commit, push. It goes last because it is the only step that changes what a skill
  *does* rather than which version is in force.
- `FORK.md`'s **Local changes** field states the overlay and how to re-apply it.
  It is still never read back for a decision — every version fact comes from git.
- A promote's checklist gains one item: re-run the overlay, because the candidate
  may register a new user-invoked skill.
- `OVERLAY_KEYS` is defined twice — in `scripts/invocation_overlay.py`, which
  writes the overlay, and in `scripts/fork_state.py`, which must recognise it.
  They must stay in step; both name the other in a comment.
- Only **registered** skills are overlaid — those the plugin manifest lists.
  Anything under `skills/in-progress/` or `skills/deprecated/` loads in no session,
  so stripping its flag would be divergence for nothing.
