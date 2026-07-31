# Mode: bootstrap

`/skill-fork-sync bootstrap` — create the **Fork** of each declared dependency and
pin each one to the SHA that is installed right now, so the day after bootstrap
behaves exactly like the day before.

> **Running this for real is a human step.** The skill prints the dry run; the
> maintainer executes the steps. Creating public repositories and force-pushing a
> default branch are not things an unattended session does, and the dry run exists
> so the whole plan can be read before any of it happens.

## The dry run is the command

The skill's own contribution is `scripts/fork_state.py --bootstrap`, which reads
the machine's config, works out the fork targets and their pins, and prints every
action bootstrap would take — taking none of them:

```
python3 -m scripts.fork_state --bootstrap                    # every fork target
python3 -m scripts.fork_state --bootstrap --fork ponytail    # one target
python3 -m scripts.fork_state --bootstrap --json             # the same plan as JSON
```

Run from this repo's root, matching the `python3 -m scripts.<name>` convention
[`sync.md`](sync.md) already uses. It **mutates nothing**: the only writes it makes
are to stdout. Its reads are `gh api user`, `gh repo view --json parent`,
`known_marketplaces.json`, `installed_plugins.json`, `requirements.md`, and
read-only git in any fork clone that already exists (`remote get-url`,
`merge-base --is-ancestor`, `cat-file -e`, `diff --name-only`). It creates no
repository, pushes nothing, and changes no marketplace registration — so it is
safe to run as often as you like, before deciding anything.

`--gh-fixture <file>` stands in for the two `gh` reads so the tests can plan a
bootstrap with no network and no login, the same way `--clone` bypasses fork
discovery on the sync side. `--today YYYY-MM-DD` fixes the date `FORK.md` records.

## Where the fork set and the pins come from

Neither is written down. Both are derived, so there is no hand-maintained list to
drift out of step with the machine (ADR 0007):

- **Which dependencies to fork.** Every `<plugin>@<marketplace>` id in
  [`requirements.md`](../../orchestrator/references/requirements.md) contributes
  its marketplace half — that file is where the dependency set is *declared*, so
  adding a dependency there is enough to bring it into the fork set. Those names
  are then intersected with the marketplaces actually registered in
  `~/.claude/plugins/known_marketplaces.json`. A marketplace that is installed but
  never declared (`caveman`, `claude-code-plugins`) is not a target; a declared
  repo the maintainer already owns outright and that is nobody's fork
  (`wagnersza/prompt-improver`) is not a target either, because there is nothing
  to fork.
- **What to pin each one to.** The `gitCommitSha` recorded for that marketplace's
  plugin in `~/.claude/plugins/installed_plugins.json` — the exact commit sessions
  load today. Where several entries exist for one plugin id, the most recently
  updated one wins. An entry with no `gitCommitSha` (a `@skills-dir` clone, or a
  local-path install) has nothing to pin to; the plan says so and blocks the pin
  step rather than guessing.

`bootstrap_targets()` and `discover_forks()` are two views of the same config.
Bootstrap needs the targets whose marketplace still points at a third party — the
ones `gh repo view --json parent` reports no parent for, which is precisely why
`discover_forks()` cannot see them. Sync needs the opposite: only a fork has an
**Upstream** remote and therefore a delta to evaluate. Bootstrap's view also keeps
the already-forked targets, reporting each step as already done, because that is
what makes a re-run readable (see [Re-running](#re-running-is-a-no-op-per-step)).

## The procedure, for one fork

Six steps, and **the order is load-bearing**. Read the dry run for the target
first; every command below is one the dry run prints verbatim.

### 1. Fork the upstream

```bash
gh repo fork <upstream> --clone=false
```

A fork of a public repo is public by default, so "the forks are public" needs no
step of its own. `gh repo fork` also gives GitHub's native fork banner and the
`parent` API field for free, which is what makes provenance unambiguous and what
sync later reads to enumerate the forks. `--clone=false` because step 2 clones it
somewhere specific; note that `--remote` is rejected outright when a repository
argument is given, so don't reach for it.

Skip `--fork-name`: the fork keeps upstream's repo name, which keeps the
`gh repo view --json parent` round-trip and the clone path predictable.

**Already done when** the fork repo exists in the maintainer's account.

### 2. Clone the fork

```bash
git clone https://github.com/<user>/<repo>.git ~/.orchestrator/forks/<marketplace-name>/
```

**Never inside `~/.claude/plugins/marketplaces/`.** That directory is a git clone
Claude Code owns and may reset or re-clone on `marketplace update`, which would
take an in-progress candidate worktree with it. The clone is keyed by *marketplace
name*, not repo name, because the marketplace name is what every other part of
this skill keys on.

**Already done when** `<clone>/.git` exists.

### 3. Add the `upstream` remote

```bash
git -C <clone> remote add upstream https://github.com/<upstream>.git
```

This is where the **Upstream** commits accumulate. They reach no session until a
**Promote** moves the fork's default branch, which is the whole mechanism.

**Already done when** the `upstream` remote resolves to the upstream repo.

### 4. Pin the default branch to the installed SHA

```bash
git -C <clone> reset --hard <installed-sha>
git -C <clone> push --force origin main
```

**The pin is the currently-installed SHA, not upstream's head.** This is the point
of the whole exercise, so it is worth stating plainly: a marketplace tracks its
source's default-branch HEAD, so whatever sits on the fork's `main` is what
sessions load. If bootstrap started the fork at upstream's head, the first
`marketplace update` would advance every session past commits nobody has
evaluated — for `mattpocock` today that is four such commits. That is the exact
failure the fork exists to prevent, and it would be introduced by the act of
building the defence against it. Starting at the installed SHA instead makes
bootstrap **behaviour-neutral by construction**: the day after runs exactly the
code the day before ran, and the first thing that ever changes it is a promote the
maintainer approved.

The force-push is what makes the fork's default branch a dial rather than a mirror
— a fresh fork starts at upstream's head, and moving it back is a rewrite. It is
also the one destructive command in the procedure, which is another reason the dry
run prints it instead of running it.

**Already done when** the installed SHA is an ancestor of `main` *and* every
commit after it touches nothing but `FORK.md` — not `main == <installed-sha>`,
because step 5 commits `FORK.md` on top of the pin, so an already-bootstrapped
fork legitimately sits one commit ahead. Anything else on `main` means the dial has
moved (someone promoted), and re-running the reset would be an unapproved
*demote*, so the plan reports the pin as `todo` and leaves the decision to the
maintainer rather than quietly rewinding.

### 5. Write and commit `FORK.md`

```bash
# write <clone>/FORK.md, then:
git -C <clone> add FORK.md
git -C <clone> commit -m "Record the fork and its pin"
git -C <clone> push origin main
```

`FORK.md` is a **record for humans**, sitting next to GitHub's fork banner. The
**Pinned SHA** that drives any decision is always read live from git; nothing in
this skill ever reads `FORK.md` back, which is why a stale one cannot cause a
wrong decision (and why `sync.md`'s test suite proves it by planning against a
deliberately wrong one).

Five fields, exactly:

| Field | Holds |
|-------|-------|
| Upstream repository | the URL the fork came from |
| Fork date | when the fork was created |
| Last-synced SHA | the commit `main` is pinned to, plus the plugin version |
| Why the fork exists | that a marketplace takes no ref flag, so this branch is the dial |
| Local changes | what diverges from upstream — `none` here, and none intended |

Concretely, as the dry run prints it:

```markdown
# Fork of mattpocock/skills

- **Upstream repository:** https://github.com/mattpocock/skills
- **Fork date:** 2026-07-31
- **Last-synced SHA:** `ed37663cc5fbef691ddfecd080dff42f7e7e350d` (1.2.0)
- **Why this fork exists:** `claude plugin marketplace add` accepts no ref,
  branch or tag, so a marketplace tracks its source's default-branch HEAD. This
  fork's `main` is therefore the version dial for `mattpocock-skills@mattpocock`: upstream
  commits accumulate on the `upstream` remote and reach no session until a sync
  evaluates them and the maintainer promotes. See ADR 0007 in
  wagnersza/orchestrator-skills.
- **Local changes:** none, and none intended. This fork pins a version; it is not
  a development branch. The only commit ahead of the pinned upstream SHA is this
  file.

The pinned SHA that drives any decision is read live from git (`git rev-parse
main` in this clone), never from this file.
```

**Local changes stays `none`.** These forks pin versions; they are not development
branches, and contributing back upstream is out of scope (ADR 0007). Keeping the
only divergence to a single file also keeps every future sync a clean
fast-forward.

**Already done when** `FORK.md` exists in the clone.

### 6. Swap the marketplace registration

```bash
claude plugin marketplace remove <marketplace-name>
claude plugin marketplace add <user>/<repo>
```

**Remove, then add — in that order, and both.** A marketplace name can hold
exactly one source, so the fork and the upstream are mutually exclusive under one
name: `add` cannot point an existing name somewhere new, so without the `remove`
first there is nothing for the fork to be registered as. `remove` drops the
declaration from every settings scope unless `--scope` narrows it, and `add`
declares at `user` scope by default.

**The marketplace name must not be renamed.** It comes from the `name` field in
the source's `.claude-plugin/marketplace.json` — `"mattpocock"`, `"ponytail"` —
not from the repo path, so leaving that file untouched is what carries the name
across the fork. Do not edit it. If it were renamed (say into a `wsza-*`
namespace), then:

- every plugin id changes, so `mattpocock-skills@mattpocock` and
  `ponytail@ponytail` stop resolving, and `claude plugin update <old-id>` fails
  with `Plugin "<name>" not found`;
- every reference to those ids needs editing —
  [`requirements.md`](../../orchestrator/references/requirements.md), the
  `docs/agents/*.md` files, and this skill's own reference files;
- `marketplace.json` becomes a locally-modified file in the fork, so it conflicts
  on every sync forever, for no benefit.

The accepted cost of keeping the name is that `claude plugin marketplace list`
shows `mattpocock` pointing at the fork with no visual marker. Fork provenance
lives in `known_marketplaces.json` and on GitHub instead (ADR 0007).

**This step goes last** because it is the step that changes what sessions load.
Pointing the marketplace at a fork whose pin has not landed yet would hand
sessions upstream's head — the failure step 4 exists to avoid. The dry run
enforces the ordering by reporting the swap as `blocked` until the pin and
`FORK.md` are in place.

**Already done when** the marketplace's registered repo is already the fork.

### Then, once per fork

A marketplace change needs `claude plugin marketplace update <name>` to refresh
the local clone, and **the new skill body loads next session** — the running
session keeps the body it started with. That rule lives in
[`requirements.md`](../../orchestrator/references/requirements.md); bootstrap
inherits it rather than restating it.

## The procedure, for all of them

Bootstrap is per-fork and the forks are independent, so "all of them" is the
one-fork procedure repeated — but the order across forks matters for a different
reason:

1. **Read the whole dry run first**, with no `--fork` filter, so every action for
   every target is on screen before any of it is real:
   `python3 -m scripts.fork_state --bootstrap`.
2. **Check the pins against the versions you expect.** Each target prints its
   plugin id, installed SHA and version. A SHA that isn't the version you think
   you're running is the cheapest possible moment to notice.
3. **Complete one fork's six steps end to end before starting the next.** Not
   step 1 for every fork, then step 2 for every fork. A fork that is half
   bootstrapped — say, forked and cloned but not yet pinned — is a fork whose
   marketplace could be swapped by mistake onto upstream's head, and doing them
   one at a time means there is only ever one incomplete fork to reason about.
4. **Re-run the dry run after each fork.** Every step of the finished one should
   now read `DONE`, which is both the confirmation and the proof that a re-run is
   safe.
5. **Restart the session** once, after the last fork, so the swapped
   registrations are what the next session loads.

Today that is two forks — `mattpocock/skills` and `DietrichGebert/ponytail`.
`prompt-improver` is already `wagnersza/prompt-improver` and is not a target.

## Re-running is a no-op, per step

Bootstrap must be safe to re-run without anyone having to remember whether it was
already done, so **idempotence is per step, not per fork**, and a partially
bootstrapped fork resumes where it stopped rather than starting over. The dry run
labels every step:

| Status | Means |
|--------|-------|
| `DONE` | the step's effect is already in place — a re-run would change nothing, so skip it |
| `TODO` | not done, and its preconditions are met — this is the next thing to run |
| `BLOCKED` | a precondition is missing, so the step can be planned but not yet checked |

The per-step checks are the "Already done when" lines above, and each one asks
about the *effect* rather than trusting a record: the fork exists on GitHub, the
clone has a `.git`, the `upstream` remote resolves to upstream, the installed SHA
is an ancestor of `main` with only `FORK.md` on top, `FORK.md` exists, the
marketplace already names the fork. Nothing consults a "bootstrap has run" flag,
because a flag can be true when the thing it describes is gone.

When every step of every target reads `DONE`, the plan says so
(`already_bootstrapped`) and there is nothing to do.

## What this skill never does here

- **Creates no repository.** `gh repo fork` is printed, never run.
- **Force-pushes nothing.** The `reset --hard` and `push --force` in step 4 are
  the maintainer's to run, on repos they own.
- **Changes no marketplace registration** and modifies no plugin install.
- **Reads `FORK.md` back for a decision.** Ever. It is a record; git is the truth.

## Fixed here, inherited there

- Mode word: `bootstrap`, no arguments beyond an optional `--fork <name>`.
- Clone root: `~/.orchestrator/forks/<marketplace-name>/`.
- Fork set: the dependencies
  [`requirements.md`](../../orchestrator/references/requirements.md) declares,
  read live. Skills that are merely installed are out of scope until declared.
- The seam that derives all of it, and its test suite:
  [`sync.md`](sync.md) documents the shared script; the bootstrap-specific cases
  are `test_fork_targets_are_declared_deps_still_pointing_at_upstream`,
  `test_pin_is_the_installed_sha_not_upstream_head`,
  `test_dry_run_prints_all_six_actions_and_takes_none`,
  `test_fork_md_records_the_five_fields`,
  `test_rerun_against_a_bootstrapped_fork_is_a_no_op_per_step`,
  `test_a_moved_default_branch_is_not_reported_as_pinned` and
  `test_a_plugin_with_no_installed_sha_blocks_the_pin`.
- Rationale for fork-and-pin, why tag-based pinning lost, and why the marketplace
  names stay as upstream defines them:
  [ADR 0007](../../orchestrator/docs/adr/0007-fork-and-pin-skill-dependencies.md).
