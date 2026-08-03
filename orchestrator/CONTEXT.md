# Orchestrator

The orchestrator skill coordinates worker sessions that implement work items. This context defines the vocabulary the skill uses to stay independent of any one workspace tool, agent CLI, or model vendor.

## Language

**Tool**:
The workspace/session manager that cuts a worktree, opens a terminal, and sends keystrokes to it. One of: orca, cmux, herdr.
_Avoid_: workspace manager, session manager, backend.

**Harness**:
The agent CLI run inside a worker terminal (claude, codex, pi, copilot, cursor). Owns the yolo-mode flag and the model-selection flag.
_Avoid_: agent, runner, CLI (when the layer is meant).

**Model**:
The frontier model a harness runs (e.g. opus-5, sonnet-5, gpt-5.6). Has a **Vendor** and an **Effort**. Never hardcoded — resolved per **Role**.
_Avoid_: LLM.

**Effort**:
The dial for how much a model **thinks** — `low | medium | high | xhigh | max`, defaulting to `high` on both frontier models. Trades capability against tokens and latency. It does *not* shorten the visible response (prompt for length separately). Each harness expresses it differently and some clamp the top of the ladder; `references/harnesses/<h>.md` holds the map, `references/models.md` the ladder.
_Avoid_: reasoning effort, thinking budget, temperature.

**Role**:
The class of job a work item represents, which selects its `(Model, Effort)` pair from config's `models:` block. Three: **heavy** (multi-file feature, refactor, migration, open decisions — strongest model, `xhigh`), **light** (single-file scoped edit with fully enumerated criteria — cheaper model, `medium`), **review** (the adversarial reviewer — different vendor, `high`). Default heavy; downgrade to light only on clear signals. A fix round after review steps up a rung.
_Avoid_: tier, profile, model class.

**Cost profile**:
A preset `models:` block — one `(model, effort)` pair per role, chosen as a set instead of role-by-role. Three: **conservative** (opus-5 @ medium / sonnet-5 @ low), **balanced** (opus-5 @ high / sonnet-5 @ medium — the default), **max-capability** (opus-5 @ xhigh / opus-5 @ high). Defined with per-MTok prices in `references/models.md`; `/orchestrator-setup` offers them as the first model question. A starting point, not a constraint — any pair is editable in config afterwards. Note cheaper is not always cheaper: a mis-routed `light` worker burns a round trip that costs more than the effort saved.
_Avoid_: tier, plan, budget mode.

**Vendor**:
The provider of a model — anthropic or openai. Adversarial review crosses vendors.
_Avoid_: provider, brand.

**Worker**:
One implementation session = a `(Tool, Harness, Model)` triple running against one work item in its own worktree/terminal.
_Avoid_: agent, session (when the worker is meant).

**Orchestrator**:
This session. Coordinates workers; never does implementation work itself.

**Yolo mode**:
The harness's unattended flag (analog of claude's `--dangerously-skip-permissions`) that lets a worker run with no human to approve tool prompts. Required, not optional, for every worker.
_Avoid_: unattended mode, skip-permissions.

**Adversarial review**:
An optional review of a worker's output by a second worker running a **different-vendor** model (e.g. implement with opus-5, review with gpt-5.6). Config names the review model + effort explicitly (`models.review`) and the orchestrator asserts its vendor differs from the impl model's. The review worker runs on the impl branch (own worktree) and reads the diff/MR against the acceptance criteria. Its prompt asks for **coverage, not filtering** — a "only high-severity" bar makes every current model silently drop real bugs.

**Review round**:
One cycle of adversarial review: the review worker posts a verdict (approve / request-changes + findings). On **request-changes**, the orchestrator re-prompts the **original impl worker** with the findings to fix, then re-reviews. Bounded at **3 rounds**. After approve — or after the 3rd round regardless — the orchestrator gathers evidence and moves the item to **human review**. The human reviews after the fixes; merge stays a human step.

**prompt-improver**:
The external skill that owns **all** prompt composition — the diagnosis checklist, the shared rules (front-load the spec, positive examples over prohibitions, no stale verification/status scaffolding, coverage-not-filtering for code review), and the per-model tuning. A dependency, not vendored: <https://github.com/wagnersza/prompt-improver>. Installs three ways — as a **plugin** (`prompt-improver@prompt-improver`), as a clone under `~/.claude/skills/` (auto-registered as `prompt-improver@skills-dir`), or as a project-level clone. The skill body is identical and the orchestrator invokes the skill rather than a path, so all three satisfy the dependency; only the update command differs (see `references/requirements.md`). The orchestrator drafts a prompt and runs it through this skill; it holds no prompting rules of its own, so the rules never drift out of sync with the upstream guides.
_Avoid_: prompting guide, composing rules (both were vendored files, now removed).

**Tuning profile**:
Which of `prompt-improver`'s per-model rule sets a spawn prompt uses. Two: **Claude Opus 5** and **Claude Sonnet 5**. `references/models.md` maps each supported model to one — GPT-5.6's **sol** tier takes the Opus 5 profile, **terra** the Sonnet 5 profile.

**Agentic-pipeline prompt**:
What a worker prompt is: deterministic, complete in one turn, finishable unattended. `prompt-improver` treats this as an explicit case — it keeps the tight task framing and the checklist and applies only the model tuning, rather than doing its open senior-partner rewrite. The orchestrator says so when invoking it.

**Tracker**:
Where work items live (GitHub / GitLab / local markdown). The orchestrator does not own a tracker abstraction — it reuses the mattpocock engineering skills' config, written to `docs/agents/issue-tracker.md` by `/setup-matt-pocock-skills`.
_Avoid_: issue tracker, board (when the layer is meant).

**Work item**:
One tracked unit of work (a ticket / issue) a worker implements. Carries `## Blocked by` and `## Parent` edges per the `to-tickets` template.
_Avoid_: ticket, issue, task (pick one — prefer work item).

**Ready queue**:
The set of work items a worker can start now — labelled `ready-for-agent` with every `## Blocked by` edge closed. The orchestrator resolves this over whatever tracker `docs/agents/issue-tracker.md` names.

**Config**:
The per-project orchestrator settings — tool, harness, model, adversarial-review policy, and tracker-setup pointer. Lives at `docs/agents/orchestrator.md` in the target repo (same pattern as `/setup-matt-pocock-skills`): human-editable markdown, seeded from a template in the skill folder, with a one-line summary block in `CLAUDE.md`. Per-project because different projects use different setups.

**Setup phase**:
The one-time interview that writes the Config — the user describes environment, tool, harness/CLI, models, adversarial-review policy, and the project recipes (setup command, run-for-evidence recipe + port scheme, optional DB gate, evidence expectations). Same posture as `/setup-matt-pocock-skills`: explore, present findings, confirm, write. Also ensures the tracker config exists (calls `/setup-matt-pocock-skills` if `docs/agents/issue-tracker.md` is missing).

**Work-state labels**:
The tracker labels that gate the queue and mark progress (`ready-for-agent`, `in-progress`, review, done). Owned by `docs/agents/issue-tracker.md` (`/setup-matt-pocock-skills`), not the orchestrator config — single source of truth. During an adversarial-review loop the item stays `in-progress` (a worker still owns it); it flips to the review label only when the loop concludes.

**Board status**:
The `Status` field on a work item's card, where the tracker has a project board (GitHub Projects v2: `Backlog | Ready | In progress | In review | Done`). A **derived projection of the Work-state labels, not a second state machine** — labels are the source of truth, and `Status` is written wherever a label is written, plus recomputed for every open item when the **Ready queue** is read (which is where drift is repaired; there is no sync command). `Backlog` covers both never-triaged and ready-but-blocked; `Ready` is exactly the ready queue, which is why the split is only knowable at queue time. A human drag is drift, not intent — it is overwritten. The derivation table and the board coordinates live in `docs/agents/issue-tracker.md`, alongside the labels; a repo with no board omits the section and every board write becomes a no-op. Rationale: `docs/adr/0009-labels-drive-board-status.md`.
_Avoid_: board state, column, board label, project status (the field is `Status`; the layer is Board status).

**Project recipe**:
Per-project commands the completion contract needs but that aren't tool/harness/model: setup command, run-for-evidence recipe + port scheme, optional DB gate, evidence expectations. Stored in Config so the skill body stays abstract ("boot per the run recipe", "if a DB gate is configured, satisfy it").

**Checklist**:
A persistent, file-based task list that survives context loss and works across every harness (unlike claude-only `TodoWrite`). Both the orchestrator and each worker keep one, so neither forgets a step (the documented "stalls before opening the MR" failure mode). Written as markdown checkboxes (`- [ ]` / `- [x]`) to `.orchestrator/checklist-<item>.md` at the worktree root (gitignored, torn down with the worktree). The worker ticks each step as it completes; the orchestrator reads the file to see exact progress and detect a stall (unchecked items + idle terminal → re-prompt with the remaining steps).

## Skill dependency versioning

Vocabulary for `/skill-fork-sync` (`../skill-fork-sync/SKILL.md`), which holds each declared skill dependency at a version this repo controls. Rationale: `docs/adr/0007-fork-and-pin-skill-dependencies.md`, `docs/adr/0008-diff-targeted-run-budget.md` and `docs/adr/0010-invocation-overlay-on-the-forks.md`.

**Fork**:
A copy of an upstream skill repo in the maintainer's own GitHub account, created with `gh repo fork` and registered as the marketplace source in place of the upstream. Its **default branch is the version dial**: whatever sits there is what sessions load, because `claude plugin marketplace add` accepts no ref/branch/tag flag. Public, and explicitly a fork (GitHub's fork banner, the `parent` API field, plus a `FORK.md` recording upstream, fork date, last-synced SHA and why it exists). Clone lives under `~/.orchestrator/forks/<marketplace-name>/`, never inside `~/.claude/plugins/marketplaces/`.
_Avoid_: mirror, vendored copy (a fork tracks upstream via a remote; neither of those does).

**Upstream**:
The original third-party repo a **Fork** was made from (`mattpocock/skills`, `DietrichGebert/ponytail`), present in the fork clone as the `upstream` git remote. Commits accumulate there and reach no session until a **Promote** moves them.
_Avoid_: origin (that's the fork), source repo, parent (that's GitHub's API field name, not the layer).

**Pinned SHA**:
The commit the fork's default branch currently sits at — the version every session actually loads. Always resolved **live from git** (`git rev-parse main` in the fork clone), never read from `FORK.md`, so a stale record can't drive a wrong decision. Set at bootstrap to the *currently-installed* SHA (`installed_plugins.json`'s `gitCommitSha`), which makes bootstrap behaviour-neutral.
_Avoid_: version, tag, release (tag-based pinning was rejected — see ADR 0007), current SHA.

**Sync candidate**:
The upstream commit a sync is considering promoting to — `git rev-parse upstream/main`, also read live from git. Evaluated in a throwaway worktree with the live install untouched, so a bad candidate can't break the session evaluating it and rejecting it means deleting a worktree with no rollback path.
_Avoid_: new version, upstream HEAD (that's where the candidate comes from, not the thing under evaluation), release candidate.

**Consumed skill**:
A skill in an upstream delta that **this repo references**, decided by grepping this repo for the skill's name. Only consumed skills spend **Run budget**; changed skills this repo never references are skipped. Self-maintaining — a new reference in any doc is covered by the next sync with no registry to update — and deliberately biased toward false positives, so the failure direction is over-testing rather than skipping risk.
_Avoid_: used skill, dependency (a dependency is declared in `references/requirements.md`; consumption is per-skill and grep-derived), relevant skill.

**Sync plan**:
The JSON a sync's deterministic half emits before anything is spent: the **Pinned SHA** and **Sync candidate**, the changed paths, the changed paths mapped to skills, each one marked **consumed** or skipped, the **Run budget** allocation, and what was dropped. Produced by one seam (`scripts/fork_state.py`) that mutates nothing, so it is testable with plain asserts and zero agent runs.
_Avoid_: diff report, delta, manifest.

**Promote**:
Turning the dial: fast-forward and push the fork's default branch to the approved **Sync candidate**, rewrite `FORK.md`'s synced SHA, update the marketplace, and update the plugin — as one step, so there is never a state where the fork and the install disagree. **Always an explicit human decision**, never automatic on a clean eval. The new skill body loads next session.
_Avoid_: merge, upgrade, release, sync (sync only evaluates and recommends; promote is the act).

**Run budget**:
The cap on what one sync may spend: **5 worker runs total, pinned-baseline runs included**. So either two paired candidate-vs-pinned comparisons plus a tiebreak, or up to five candidate runs. The allocation and any coverage dropped for budget is always reported, so "tested" never silently means "partially tested". Diff-targeted rather than a fixed contract suite, which at this ceiling could consume the whole budget and leave nothing for the change that triggered the sync.
_Avoid_: cost cap, token budget, quota, test budget.

**Invocation overlay**:
The one local change a **Fork** may carry: every skill the fork's plugin manifest registers is made reachable by a model, by deleting two keys and nothing else — `disable-model-invocation: true` from `SKILL.md` frontmatter, and the `policy.allow_implicit_invocation: false` block from `agents/openai.yaml`. A worker session has no human in it, so a skill only a human can type is a skill that never runs. Applied by `scripts/invocation_overlay.py` (idempotent, dry by default), it is bootstrap's **step 7** and must be **re-applied after every Promote**, since an upstream commit adding a user-invoked skill re-introduces the keys. Recognised as acceptable divergence by diff *content*, not by filename, so a skill-body edit in an overlaid file still reads as a moved dial and refuses the promote. See ADR 0010.
_Avoid_: patch, fix, customisation, local changes (ADR 0007 uses that phrase for the `FORK.md` field this overlay is the sole entry in), enabling skills.
