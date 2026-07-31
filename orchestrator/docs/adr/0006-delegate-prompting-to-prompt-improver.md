# Delegate prompt composition to the prompt-improver skill

The orchestrator carried its own prompting rules in three vendored files:
`references/prompting/_composing.md` (model-independent rules) plus copies of
Anthropic's Opus 5 and Sonnet 5 guides. `_composing.md` said in its own header that
it was "distilled from the wsza/prompt-improver skill" — so the rules existed in
two places, and the two vendored guides were snapshots stamped "Fetched 2026-07-29.
Refresh manually when the guide changes", i.e. guaranteed to rot.

The prompting rules now live only in the
[`prompt-improver`](https://github.com/wagnersza/prompt-improver) skill, which is a
declared dependency alongside `mattpocock-skills` and `ponytail`. The orchestrator
drafts a worker or review prompt and runs it through that skill, naming the target
model's profile; it holds no prompting rules of its own. The vendored
`references/prompting/` directory is deleted.

This is the same move as ADR 0002 (delegate the tracker to the mattpocock skills):
own the orchestration, depend on the specialist.

## Considered Options

- **Depend on the skill, delete the vendored copies** (chosen) — one source of
  truth. `prompt-improver` already covers every rule `_composing.md` had, plus the
  per-model tuning, and it handles the agentic-pipeline case explicitly rather than
  needing the orchestrator to carve out an exception.
- **Keep `_composing.md`, delete only the two model guides** — halves the
  duplication but keeps the worse half: the distilled summary is exactly the copy
  that silently diverges from upstream.
- **Keep vendoring everything** — works offline and pins the rules, but the pin is
  the problem: the guides change with each model generation, and a stale rule here
  is not inert, it actively degrades every worker prompt (a "double-check your
  work" line costs tokens for nothing on Opus 5; a "be conservative" review bar
  drops real bugs).
- **Fetch the upstream guides at spawn time** — no local staleness, but a network
  fetch on the hot path of every spawn, and no offline path.

## Consequences

- **A new hard dependency**, checked in preflight before the first spawn and
  installed by `/orchestrator-setup`. It's a git clone into `~/.claude/skills/`,
  not a plugin, so it needs a session restart to be discovered.
- **The orchestrator must declare the prompt kind when invoking.** A worker prompt
  is an agentic-pipeline prompt — `prompt-improver` keeps the tight framing and the
  checklist for that case, but its default posture is the open senior-partner
  rewrite, which would dissolve the completion contract. A review prompt must be
  declared as a code-review prompt so the coverage-not-filtering rule applies.
- **Three things stay in the skill body** because `prompt-improver` can't know
  them: a worker has no human to answer a follow-up (so name the assumption, never
  "ask the user"), a worker in a worktree shouldn't fan out, and the scope edges are
  a deliberate exception to positive-framing.
- `references/models.md` maps each model to a `prompt-improver` **profile** (Claude
  Opus 5 / Claude Sonnet 5) instead of a vendored file path. GPT-5.6 sol takes the
  Opus 5 profile, terra the Sonnet 5 profile — unchanged mapping, new target.
- Upstream prompting improvements reach every worker on a `git pull` of the skill,
  with no edit here.
