# Delegate technical writing to the simple-english skill, and narrow the fork set

A work item in this repo is mostly prose. The diff is skill bodies, reference
files, ADRs and README sections. Every worker also writes a review note and a PR
body, and the orchestrator writes status reports the maintainer reads. None of
that prose had a standard. The repo already controls how a worker is prompted
(ADR 0006), how lazy its code is (`ponytail`), and which version of each
dependency it loads (ADR 0007). It controlled nothing about the text a worker
produces.

The cost is the failure mode this repo names elsewhere: a rule with no home rots.
A skill body of 40-word hedged sentences is harder to follow than the same rule
written flat and short. The reader of a skill body is a tired agent that reads
each sentence one time.

The writing rules now live only in the
[`simple-english`](https://github.com/AminBlg/SimpleEnglish) skill, a declared
dependency beside `mattpocock-skills`, `prompt-improver` and `ponytail`. The skill
applies ASD-STE100 Simplified Technical English: a controlled language with
numbered rules, maintained since 1983. It is MIT licensed and has no dependencies
of its own. This repo states only *when* to invoke it and *what counts as a*
**Prose deliverable**. The four classes and the untouchables are in `CONTEXT.md`.
No sentence limit, no substitution table, no modal ladder and no rule number is
copied here.

This is ADR 0006 applied a second time, for the same reason: a copied rule set
drifts from the upstream that maintains it. Three delegations now form one
pattern. `prompt-improver` owns the prompt, `simple-english` owns the prose, and
`ponytail` owns the volume. Judge a fourth candidate against that shape.

## Considered Options

- **Declare `simple-english` as an always-required dependency** (chosen) — the
  rules are numbered, testable, and maintained by someone else. Pragmatic mode
  keeps this repo's domain vocabulary, so the glossary terms survive a writing
  pass unchanged. The skill needs nothing installed beyond itself.
- **Write a house style guide in this repo** — total control over the wording, and
  the same vendoring ADR 0006 undid. A distilled summary of a standard is the copy
  that diverges from it in silence. This option also makes the maintainer own a
  rule set someone else maintains better.
- **Put the writing rules in `prompt-improver`** — one dependency instead of two,
  and the wrong home. That skill shapes the prompt the orchestrator sends, not the
  deliverable a worker produces, and these rules belong to a maintained standard
  rather than to a prompting guide. It also makes one artifact reachable by two
  rule sets with no ordering between them.
- **Leave prose ungoverned** — the state before this ADR, and the problem. Skill
  bodies drift in register, so a worker cannot tell a hard rule from a suggestion
  and picks.

## Consequences

- **A new always-required dependency**, checked in preflight before the first
  spawn and installed by `/orchestrator-setup`. It installs through the `skills`
  CLI (`npx skills add AminBlg/SimpleEnglish`), so it needs `node` and network
  access, and `claude plugin update` does not apply to it. Four install shapes
  satisfy the check, and `references/requirements.md` lists each one with its
  verified path.
- **The default mode is pragmatic**, which keeps domain vocabulary. A worker must
  never simplify a glossary term. Strict mode also needs the official ASD-STE100
  dictionary, which this repo does not have, so nothing here asks for strict.
- **One collision needed a resolution.** `ponytail` decides whether a paragraph
  exists, and `simple-english` decides how a kept paragraph reads. So `ponytail`
  can delete a paragraph, and a worker that compresses a kept paragraph into
  telegraph style commits a violation. Stated one time, in `CONTEXT.md`.
- **The existing prose is not retrofitted.** This ADR declares the standard and
  wires it in. A pass over the skill bodies and ADRs written before it is separate
  work.

## The fork set narrows to marketplace-installed dependencies

ADR 0007 concludes that "the fork set is exactly what `requirements.md`
declares". That sentence is now false, and this ADR narrows it: **the fork set is
the declared dependencies installed through a Claude plugin marketplace.**

`simple-english` is declared and cannot be pinned. `claude plugin marketplace add`
needs a `.claude-plugin/marketplace.json` in the source repo, and the upstream has
none, so there is no marketplace to point at a fork. The `skills` CLI offers no
equivalent version dial. `npx skills add` takes no ref, branch or tag flag, and
`npx skills update` moves the skill to whatever upstream now holds. A fork
therefore buys nothing, because no install shape can read it.

**The accepted risk:** an upstream rule change reaches every session on the next
install or update, through no evaluation gate. Every other dependency reaches a
session only through a **Promote** the maintainer approves. This one does not. The
gap is recorded, not closed. If the writing bar becomes important enough, the
follow-up is a skills-CLI pin path in `/skill-fork-sync` — considered here and
deferred as too large.

ADR 0007 keeps its own text. Per `CLAUDE.md`, a decision that narrows an earlier
one gets a new ADR instead of a silent edit. Its stale sentence is also a
consequence of the mechanism it documents, and not an instruction a reader can act
on wrongly. That ADR names the marketplace CLI as the only version dial
available, which is the exact reason `simple-english` falls outside the set.

**`scripts/fork_state.py` is unchanged, on purpose.** It derives the fork set from
the marketplace config plus GitHub's `parent` field. A dependency with no
marketplace registration is therefore invisible to it, which is correct output and
not a fault. To teach the script the declared set means the hand-maintained
registry ADR 0008 rejected, and it also gives the script a dependency it can do
nothing about. `simple-english` never appears in a **Sync plan**, which is the
expected behaviour, and this ADR is where a reader learns why.
