# Fork each declared skill dependency and pin the fork's default branch

Every skill this repo declares as a dependency — `mattpocock-skills`, `ponytail`,
`prompt-improver` — was installed straight from someone else's default branch,
and this repo does not merely coexist with them: `references/requirements.md`
declares `mattpocock-skills` the owner of the tracker config, `ponytail` the thing
that keeps workers lazy, and `prompt-improver` the sole owner of prompt
composition (ADR 0002, ADR 0006). An upstream rename of
`docs/agents/issue-tracker.md`, or a rewrite of ponytail's ladder, breaks this
repo's completion contract with no failing test anywhere. The way that gets
discovered today is a worker behaving differently.

**`claude plugin marketplace add` accepts no `--ref`, `--branch` or `--tag`** —
verified against `claude plugin marketplace add --help`. A marketplace tracks the
source's default-branch HEAD, full stop. So the only version control available is
*what sits on the default branch of the repo the marketplace points at*, and the
only way to own that dial is to own the repo. Each upstream is therefore forked
into the maintainer's account, and **`fork/main` becomes the pin**: upstream
commits accumulate on the `upstream` remote and reach no session until a sync
promotes them.

Each fork is pinned at bootstrap to the **currently-installed** SHA, read from
`installed_plugins.json`'s `gitCommitSha` — not to upstream HEAD. Pinning to HEAD
would silently advance the install by unevaluated commits, which is the exact
failure the fork exists to prevent, so bootstrap is behaviour-neutral by
construction.

Marketplace names stay exactly as upstream defines them. The id comes from the
`name` field in `.claude-plugin/marketplace.json`, not from the repo path, so
leaving that file untouched keeps `mattpocock-skills@mattpocock` and
`ponytail@ponytail` working and needs zero edits to `requirements.md` or
`docs/agents/*.md` — and the file never conflicts on a sync.

## Considered Options

- **Fork and pin the fork's default branch** (chosen) — the only mechanism the
  marketplace CLI leaves available, and it costs nothing on day one because the
  pin starts at the installed SHA. Forks are public by default and carry GitHub's
  native fork banner plus the `parent` API field, so provenance is never
  ambiguous.
- **Pin by tag or release** — the intuitive answer, and unavailable in practice on
  both counts. `ponytail` has no tags at all, so there is nothing to pin to; and
  `mattpocock-skills` is installed at `ed37663`, already **ahead** of its newest
  tag `v1.1.0`, so tag-pinning would move the install *backwards* onto a body
  workers have never run. Even where tags existed, the marketplace CLI has no
  `--tag` flag to consume them.
- **Track upstream directly and read the diff before each `marketplace
  update`** — no forks to maintain, but no dial either: `marketplace update` is
  all-or-nothing, and the delta can only be reviewed *after* it has already
  changed what sessions load. Discipline is not a version pin.
- **Vendor the skill bodies into this repo** — total control, and a permanent
  merge burden on files this repo does not own. It also breaks the delegation the
  dependencies exist for: a vendored copy of the tracker config is the same
  drift ADR 0006 deleted the vendored prompting files to escape.
- **Rename the forks into a `wsza-*` marketplace namespace** — makes fork
  provenance visible in `claude plugin marketplace list`, at the cost of changing
  every plugin id and therefore every existing doc reference and update command.
  Rejected for that blast radius.

## Consequences

- **A marketplace name can be registered only once**, so fork and upstream are
  mutually exclusive per name — registering the fork means removing the upstream
  registration. Bootstrap does both as one step.
- **Fork provenance is invisible in `claude plugin marketplace list`.** It shows
  `mattpocock` pointing at the fork with no marker; provenance is only visible in
  `known_marketplaces.json` and on GitHub. Accepted as the price of stable plugin
  ids.
- **The pin must be read live from git** (`git rev-parse` in the fork clone),
  never from `FORK.md`. `FORK.md` is a human record, and a stale one must not be
  able to drive a wrong decision.
- **Upstream improvements now require a deliberate act.** Nothing arrives by
  drift, which is the point, but it also means a fix that is sitting upstream
  stays out of reach until someone runs a sync.
- **Fork clones live under `~/.orchestrator/forks/`, never inside
  `~/.claude/plugins/marketplaces/`** — that directory is a git clone Claude Code
  owns and may reset or re-clone on `marketplace update`, which would take an
  in-progress candidate worktree with it.
- The fork set is exactly what `requirements.md` declares. Skills that are merely
  installed (`caveman`, `skill-creator`) stay out until they are declared;
  skills that ship with a desktop app and have no public upstream are a vendoring
  problem, not a forking one.
- Turning the dial is what `/skill-fork-sync` exists for —
  [`skill-fork-sync/SKILL.md`](../../../skill-fork-sync/SKILL.md).
