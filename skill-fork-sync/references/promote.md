# Mode: promote

`/skill-fork-sync promote` — turn the dial. Advance the **Fork**'s default branch
to the approved **Sync candidate** and bring the live install with it, so there is
never a state where the pin and the install disagree about which version is in
force.

> **Promote runs only on explicit approval, every time.** A **sync** recommends;
> it never promotes, and an all-green assertion table is a *recommend promote*,
> not a promote. At most 5 runs per sync is too thin a sample to move a live
> install unattended, and a silent promote reintroduces the exact problem the fork
> exists to prevent —
> [ADR 0008](../../orchestrator/docs/adr/0008-diff-targeted-run-budget.md). There
> is no flag, no threshold and no "all green so go ahead" path.

## The plan is the command

```bash
python3 -m scripts.fork_state --promote --fork <name>
python3 -m scripts.fork_state --promote --fork <name> --candidate <sha>
python3 -m scripts.fork_state --promote --json          # the same plan as JSON
```

Run from this repo's root, matching the `python3 -m scripts.<name>` convention
[`sync.md`](sync.md) documents. It **mutates nothing** — it prints the four
ordered steps, each with a status, the `FORK.md` body step 2 would write, and the
update command step 4 needs. Nothing is pushed, no marketplace is refreshed and no
plugin is updated by the command; the maintainer runs the steps.

`--candidate <sha>` is the SHA the sync's assertion table was graded against.
Without it the plan targets `upstream/main`. **Exit 2 means at least one fork was
refused** — read the reason before touching anything.

The two decisions promote must not get wrong are derived, not asserted in prose:

- **Can this be taken without rewriting history** (`fast_forward`), and
- **which update command this dependency's install shape calls for**
  (`install_shape`).

Both come out of the same seam as the **Sync plan** and the bootstrap dry run, so
they are testable with plain asserts and cost no runs.

## Fast-forward only, and what refusal means

The **Pinned SHA** is read live from git; `FORK.md` is never read back for a
decision (ADR 0007). A promote is allowed when taking the candidate only *adds*
commits:

| The plan says | Because | Do |
|---------------|---------|-----|
| `fast_forward: true` | the candidate is a descendant of the pin, or the pin diverges from their shared base by nothing but `FORK.md` — the shape bootstrap and every earlier promote leave behind | run the four steps |
| `fast_forward: false` | the fork's default branch carries a change upstream does not have, so merging would not produce the tree the sync evaluated | **stop. Re-sync.** |
| `stale_evaluation` set | the approved candidate is no longer `upstream/main` — upstream moved after the sync, so the assertion table describes a different tree | **stop. Re-sync.** |

**Never force-push.** A promote that would need one is not a promote — it is a
pin that moved under the evaluation, and the evidence no longer describes what
would land. The plan refuses rather than offering a `--force`: step 1 reads
`refused` and steps 2–4 read `blocked`, so no half-promote is even planned. The
fix is a fresh `/skill-fork-sync sync`, not a bigger hammer.

## The four steps, in order

Read the plan for the fork first; every command below is one it prints verbatim.
**The order is load-bearing** and each step names what "already done" looks like,
so a re-run resumes rather than restarting.

### 1. Advance the pin to the candidate

```bash
git -C <clone> merge --no-edit <candidate-sha>
git -C <clone> push origin main
```

A merge, not a reset: the pin legitimately carries `FORK.md` commits upstream does
not have, so the merge is what keeps them while taking everything the candidate
adds. `main` on the fork **is** the version dial — a marketplace tracks its
source's default-branch HEAD and accepts no ref flag, which is why promote is a
branch move rather than a version or tag bump
([ADR 0007](../../orchestrator/docs/adr/0007-fork-and-pin-skill-dependencies.md)).

**Already done when** the candidate is an ancestor of the fork's default branch
(`already_promoted`). **Per step, not per promote** — step 1 landing says nothing
about step 4, so a re-run after a partial failure resumes at the first step whose
effect is missing rather than replaying or skipping the lot.

### 2. Rewrite `FORK.md`'s synced SHA

```bash
# write <clone>/FORK.md, then:
git -C <clone> add FORK.md
git -C <clone> commit -m "Promote to <candidate-sha-7>"
git -C <clone> push origin main
```

Only the `- **Last-synced SHA:**` line changes, to the candidate plus the plugin
version declared at it; the other four fields bootstrap wrote stay as they are
(see [`bootstrap.md`](bootstrap.md) for the five). The plan prints the exact body
in `fork_md`.

This is the one place this skill *writes* `FORK.md`, and the one thing it ever
reads the file *for*: whether the record has caught up. **Never for what the pin
is** — every version fact in the plan comes from `git rev-parse`, so a stale or
hand-edited record cannot drive a wrong decision (ADR 0007).

**Already done when** the `FORK.md` committed on the default branch already names
the candidate (`record_up_to_date`), read from git rather than the working tree, so
an uncommitted edit does not make the step look done.

### 3. Refresh the marketplace

```bash
claude plugin marketplace update <marketplace-name>
```

**Not checked — just run it.** It is a fetch into the clone Claude Code owns;
running it twice costs nothing, and a status derived from that clone's contents
would be a status about a directory this skill does not control.

### 4. Update the plugin — with the command its install shape takes

```bash
claude plugin update <plugin>@<marketplace>     # the plugin shape
```

**Marketplace before plugin, and both.** The plugin is installed *out of* the
marketplace's local clone, so updating the plugin against a stale clone reinstalls
the version already in force — the pin moves and the install does not, which is
precisely the disagreement promote exists to prevent. The reverse order fails
silently, which is why the order is fixed rather than advisory.

**The command depends on how the dependency was installed**, and the three-shape
table lives in
[`requirements.md`](../../orchestrator/references/requirements.md) — promote
*reads* that rule rather than restating it. The short version of why it matters: a
clone registered from the skills directory appears in `claude plugin list` but is
not a plugin, and `claude plugin update` fails on it with `Plugin not found`,
exit 1. The plan resolves the shape from the same evidence a human would — an
entry in `installed_plugins.json`, and any clone whose `origin` is this fork — and
names both the shape and the command in `install_shape`.

Two shapes have no command, and the plan reports the step `blocked` rather than
guessing:

| Shape | Means | Do |
|-------|-------|-----|
| `ambiguous` | a plugin install *and* a clone, or clones in both skills directories — two copies shadowing each other | resolve the duplicate first; `requirements.md` warns against installing the plugin on top of a clone |
| `unknown` | no plugin entry and no clone found | read `claude plugin list` and pick the command from the three-shape table by hand |

**Not checked either**, and for a stronger reason than step 3 — see
[what promote deliberately does not do](#what-promote-deliberately-does-not-do).

### Then: say that it takes effect next session

The promote's last act is a sentence, not a command:

> Promoted `<fork>` from `<pinned-sha-7>` to `<candidate-sha-7>` (`<version>`).
> **The new skill body loads next session** — this session keeps the body it
> started with.

That restart requirement is `requirements.md`'s rule ("a plugin update needs a
session restart to take effect"); promote enforces it rather than re-deriving it.
Saying it plainly is the difference between a maintainer who restarts and one who
spends an hour wondering why the change did nothing.

## What promote deliberately does not do

**It does not verify the installed SHA afterwards.** No read-back of
`installed_plugins.json`, no comparison against the promoted SHA, no "verified"
line in the output. `claude plugin update` may not refresh the loaded cache until
a restart, so a check run immediately after step 4 would report a mismatch that
is not real — and a check that cries wolf is worse than no check, because the next
real mismatch reads as noise. The restart sentence above is what carries that
information instead. The plan records the omission and its reason in
`verifies_installed_sha_afterwards` and `why_not`, so it reads as a decision
rather than a gap.

It also promotes nothing itself, creates no repository, and touches nothing under
`~/.claude/plugins/marketplaces/` beyond the `marketplace update` in step 3 —
that directory is Claude Code's (ADR 0007).

## When a step fails partway

**Say which steps completed and which did not.** A promote that dies between
steps 1 and 4 leaves a real, describable state, and the only unrecoverable version
of it is the one nobody wrote down. The report shape:

```
## promote mattpocock: 91aae53 -> f8adfd8 (1.3.0) — INCOMPLETE

Completed:
  1. advance the pin      pushed — fork/main is now f8adfd8
  2. FORK.md              synced SHA rewritten and pushed
  3. marketplace          claude plugin marketplace update mattpocock — refreshed

Did not complete:
  4. plugin               claude plugin update mattpocock-skills@mattpocock
                          failed: Plugin "mattpocock-skills" not found (exit 1)

State right now: the pin is f8adfd8 and the install is still on 91aae53. They
disagree until step 4 lands.

To finish: re-run `python3 -m scripts.fork_state --promote --fork mattpocock` —
steps 1 and 2 now read `done`, so only 3 and 4 are left and 3 is a free repeat.
If the plugin step keeps failing, check the install shape against
requirements.md's three-shape table: `Plugin not found` on a name that
`claude plugin list` does show is the @skills-dir case, which takes a git pull
rather than a plugin update.
```

Three rules for that report:

- **Name every step by number and outcome**, including the ones that succeeded.
  "Promote failed" is not a state; "1–3 done, 4 failed" is.
- **State which side of the dial each half is on** — the pin's SHA and the
  install's — so the disagreement is a fact rather than a worry.
- **The recovery is a re-run, not a rollback.** Every step's status is derived
  from the effect, so a re-run resumes at the first incomplete one. There is no
  undo to get wrong, and rewinding the pin to "clean up" would be an unapproved
  demote.

A failure at step 1 is the easy case: nothing moved, nothing to explain beyond the
refusal reason. Steps 2–4 are the ones worth writing out.

## Fixed here, inherited there

- Mode word: `promote`, with an optional `--fork <name>` and `--candidate <sha>`;
  it acts on the candidate the preceding `sync` reported.
- Approval is explicit and per promote, on a clean assertion table as much as a
  dirty one —
  [ADR 0008](../../orchestrator/docs/adr/0008-diff-targeted-run-budget.md).
- The fork's default branch is the only version dial available, which is why
  promote is a branch move —
  [ADR 0007](../../orchestrator/docs/adr/0007-fork-and-pin-skill-dependencies.md).
- The install-shape rule and the restart requirement both belong to
  [`requirements.md`](../../orchestrator/references/requirements.md). This file
  applies them; it does not own them.
- The seam that derives the plan, and its test suite: [`sync.md`](sync.md)
  documents the shared script; the promote-specific cases are
  `test_a_promotable_candidate_plans_four_steps_and_takes_none`,
  `test_a_diverged_pin_is_refused_rather_than_force_pushed`,
  `test_a_pin_already_carrying_the_candidate_is_a_no_op_not_a_rewind`,
  `test_fork_md_synced_sha_is_rewritten_to_the_candidate`,
  `test_the_update_command_follows_the_install_shape`,
  `test_an_ambiguous_install_blocks_the_plugin_step`,
  `test_it_promotes_nothing_and_never_verifies_the_installed_sha` and
  `test_a_stale_candidate_and_a_missing_clone_are_both_refused`.
- What produces the candidate and the approval promote acts on:
  [`sync.md`](sync.md).
