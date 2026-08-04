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

**Close transaction**:
The eight steps that finish a **Work item**, in one fixed order, after the human asks for them:

1. Resolve conflicts against the default branch.
2. Push the mergeable branch.
3. Merge the PR.
4. Verify the merge landed.
5. Pull the merge into the local default branch.
6. Verify the worktree is clean.
7. Flip the **Work-state labels**, close the item, and write its **Board status** — as one step.
8. Remove the worktree.

The eight split in two, by whether the step needs judgement. **Steps 1 to 3 need judgement, so they belong to prose.** No script reads two versions of a change and decides what the merged file means. Step 1 invokes the **resolving-merge-conflicts** skill. **Steps 4 to 8 need no judgement, so they belong to the seam.** They are predicates, a pull, two tracker writes and a passed-in teardown command, which makes them an ordering and nothing else. One seam owns that ordering, because ordering is what code holds perfectly and prose holds poorly. That seam is `scripts/close_item.py`. This entry names it before it exists: the term is declared here, and the file lands with the flow change that consumes it.

**The actor for all eight steps is the orchestrator session**, and never a **Worker**. A worker can be idle or out of context when the human asks, and its worktree is what step 8 removes. The seam refuses rather than warns. An unmerged PR and a dirty worktree each stop the transaction with a distinct exit code. A refused transaction leaves the item at the review state, with its card at `In review`. Nothing destructive happens by default. Rationale, the rejected alternatives, and the risk accepted for the actor: `docs/adr/0015-close-is-a-deterministic-transaction.md` and `docs/adr/0016-the-orchestrator-merges-when-asked.md`.
_Avoid_: teardown (that names step 8 alone), close flow, closing sequence, wrap-up.

**prompt-improver**:
The external skill that owns **all** prompt composition — the diagnosis checklist, the shared rules (front-load the spec, positive examples over prohibitions, no stale verification/status scaffolding, coverage-not-filtering for code review), and the per-model tuning. A dependency, not vendored: <https://github.com/wagnersza/prompt-improver>. Installs three ways — as a **plugin** (`prompt-improver@prompt-improver`), as a clone under `~/.claude/skills/` (auto-registered as `prompt-improver@skills-dir`), or as a project-level clone. The skill body is identical and the orchestrator invokes the skill rather than a path, so all three satisfy the dependency; only the update command differs (see `references/requirements.md`). The orchestrator drafts a prompt and runs it through this skill; it holds no prompting rules of its own, so the rules never drift out of sync with the upstream guides.
_Avoid_: prompting guide, composing rules (both were vendored files, now removed).

**simple-english**:
The external skill that owns **all** writing rules for a **Prose deliverable**. It applies ASD-STE100 Simplified Technical English: the sentence limits, the vocabulary discipline, and the mode definitions. A dependency, not vendored: <https://github.com/AminBlg/SimpleEnglish> (MIT, no dependencies of its own). This repo states only *when* to invoke the skill and *what counts as a prose deliverable*, and copies no rule of the standard. Same posture as **prompt-improver**, for the same reason: a copied rule set drifts from the upstream that maintains it. The default mode here is **pragmatic**, which keeps domain vocabulary. Every glossary term in this file therefore survives a writing pass unchanged, and a worker must never "simplify" Tool, Harness, Worker or Pinned SHA. **Strict** mode needs the official ASD-STE100 dictionary, which this repo does not have, so nothing here asks for strict. The skill installs through the `skills` CLI (`npx skills add AminBlg/SimpleEnglish`), which registers no Claude plugin marketplace. So `/skill-fork-sync` cannot pin the skill, and it never appears in a **Sync plan** — the accepted risk in `docs/adr/0011-delegate-technical-writing-to-simple-english.md`. Install shapes and commands: `references/requirements.md`.
_Avoid_: STE, ASD-STE100 (both name the standard, not the dependency), style guide, house style (both name the thing this repo refuses to own).

**Prose deliverable**:
Text a human or a later agent reads as prose. A worker routes this text through **simple-english** before it commits. Four classes, all in scope:

1. **Markdown in the diff** — skill bodies, reference files, ADRs, `README.md`, `CLAUDE.md`, config docs. Scoped to the prose the worker already changes, so a one-line doc item does not permit a repo-wide rewrite.
2. **Completion-contract artifacts** — the review note on the **Work item** and the PR/MR body. These apply on every item, even a pure-code one.
3. **Shipped strings** — `argparse` help, warnings and error text in `scripts/*.py`.
4. **Orchestrator reports** — this session's status lines and tables to the maintainer.

A writing pass can change the sentences and paragraphs of running prose, and nothing else. These stay byte-identical: code blocks, identifiers, file paths, commands, quoted error strings, YAML and JSON keys, link targets, and proper nouns. An edit to any of them can break a cross-reference, which is this repo's main failure mode.

Three dependencies now shape a worker's output, and each owns a different artifact:

- **prompt-improver** shapes the prompt the orchestrator sends.
- **simple-english** shapes the prose the worker produces.
- `ponytail` shapes how much code and prose exist at all.

One collision is real: the `ponytail` shortest-explanation rule conflicts with the standard's rules for articles and against telegraph style. The resolution is a split of authority. `ponytail` decides whether a paragraph exists, and **simple-english** decides how a kept paragraph reads. So `ponytail` can delete a paragraph, and a worker that compresses a kept paragraph into telegraph style commits a violation.
_Avoid_: documentation, docs, copy, text (all four are broader than the four classes).

**resolving-merge-conflicts**:
The external skill that owns **all** procedure for an in-progress merge or rebase conflict. It holds how to read the current state, how to find the intent behind each side, how to resolve a hunk, and which project checks to run afterwards. A dependency, not vendored — it ships inside `mattpocock-skills` (<https://github.com/mattpocock/skills>), so the plugin this repo already declares provides it. There is nothing separate to install. This repo states only *when* to invoke it: step 1 of a **Close transaction**, in the orchestrator session, inside the item's worktree, before the merge. It copies no step of the procedure. Same posture as **prompt-improver** and **simple-english**, for the same reason: a copied rule set drifts from the upstream that maintains it. Install shapes and the check: `references/requirements.md`.
_Avoid_: conflict resolution, merge resolution (both name the job, not the dependency), git merge skill.

**Browser surface**:
The one browser-automation surface a **Worker** drives when an item needs UI proof.
It is `playwright-cli`, and it is the only sanctioned one. Every action it performs
emits the equivalent Playwright TypeScript. So its output is code that can become a
durable test (`../playwright-cli/references/test-generation.md`), not a transcript
entry that dies with the session. It is a declared dependency with a checked binary
and an install procedure of its own (`references/requirements.md`,
`../playwright-cli/references/installation.md`).

**A browser MCP that a worker's session happens to expose is not a sanctioned
surface, whichever one it is.** Chrome DevTools MCP is the instance registered
globally on the maintainer's machine today, so it loads in every worker session
here. But the rule is about the class, not about that one server. A new browser MCP
that appears tomorrow is out of bounds on the same terms, with no edit to this
entry. **Tool availability is not tool endorsement.** An unattended worker's tool
list comes from global config the worker did not choose, so anything this repo has
not declared is not sanctioned by default.

Enforcement is **documentary**, in three places and nowhere else. This entry says
what the concept means, `references/requirements.md` says which surface is declared,
and the worker prompt's scope edges say it to the worker. This repo writes no
permissions deny rule, and it leaves the machine's global MCP registration alone.
That registration serves the maintainer's unrelated projects, and this repo does not
own user-global state. Rationale and the accepted risk:
`docs/adr/0012-playwright-cli-is-the-only-browser-surface.md`.
_Avoid_: browser tool, browser automation (both are broader than the declared
surface), Playwright (that names the library, not this repo's surface).

**Commit slice**:
One commit on a **Worker**'s branch. Two conditions define a slice, and both are
necessary:

1. **One logical change.** The commit does one thing a reviewer can judge on its own:
   an ADR, or a vocabulary entry, or the reference edits that apply a decision. One of
   those, not two.
2. **The branch is self-consistent at that commit.** Every cross-reference the commit
   introduces resolves within the same commit. This condition exists because a
   dangling cross-reference is this repo's main failure mode. So a reference file and
   the link target it adds are one slice, never two.

A worker commits a slice as soon as that slice is complete, and it does not wait for
the end of the item. The message is **Conventional Commits** with an imperative
subject, plus a body that says why when the subject cannot carry it. A **Prose
deliverable** in a slice goes through **simple-english** before the commit that
carries it, not before the last commit of the item.

**A trivial item is one commit, and that is not a violation.** The rule is "one commit
per logical change", never "at least N commits". A minimum count makes a worker split
a change whose parts fail on their own. In a **Review round** fix cycle, one finding
is one slice, so the reviewer can map each fix to the finding it answers.

Slices serve the reviewer who reads the open PR. They are not a request to change the
merge button: this repo squash-merges, so `main` keeps one commit per item. Rationale
and the accepted risk of documentary enforcement:
`docs/adr/0013-workers-commit-in-contextualised-slices.md`.
_Avoid_: atomic commit (that names indivisibility, not one logical change),
checkpoint, WIP commit (neither has to be self-consistent), granularity (that names
the dial, not the unit).

**Tuning profile**:
Which of `prompt-improver`'s per-model rule sets a spawn prompt uses. Two: **Claude Opus 5** and **Claude Sonnet 5**. `references/models.md` maps each supported model to one — GPT-5.6's **sol** tier takes the Opus 5 profile, **terra** the Sonnet 5 profile.

**Agentic-pipeline prompt**:
What a worker prompt is: deterministic, complete in one turn, finishable unattended. `prompt-improver` treats this as an explicit case — it keeps the tight task framing and the checklist and applies only the model tuning, rather than doing its open senior-partner rewrite. The orchestrator says so when invoking it.

**Skill routing**:
The resolution of a user's verb to the installed skill that owns that job. One table holds it — `references/skill-routing.md` — with a row per verb and its aliases, the skill, the **Lane**, and what the skill needs handed to it. Hand-maintained, and a property of the installed skill set rather than of a project, so a newly declared dependency is one new row. Every row names a skill that `references/requirements.md` already declares, so a route never points at something uninstalled. Independent of **Role**: verb → skill and work item → `(Model, Effort)` are two resolutions over the same item, and neither constrains the other. It carries no prompting rule. The wording of a routed invocation stays **prompt-improver**'s (`docs/adr/0006-delegate-prompting-to-prompt-improver.md`). Rationale and the rejected options: `docs/adr/0014-route-verbs-to-skills-in-two-lanes.md`.
_Avoid_: skill selection, verb mapping, dispatch, skill registry (the last one names the plugin-set scan this deliberately is not).

**Lane**:
Where a routed skill runs. Two values, and a **Skill routing** row carries exactly one. **inline** — the **Orchestrator** invokes the skill in this session, in the main checkout. **worker** — the orchestrator invokes nothing, and the invocation goes into the spawn prompt, so a **Worker** enters the skill inside its own worktree. The split follows the nature of the skill's output, not its volume. A skill whose output is issues, docs or conversation is inline, and that breaches no rule, because "never do implementation work here" is about writing source. A skill that writes source is worker. `/wayfinder` and `/research` are the boundary: both write outside the conversation, and both stay inline because their output is non-source and a delete or an edit undoes it. There is no third value and no blank — a verb whose lane is not decided gets no row.
_Avoid_: mode, channel, side, track, local/remote (none of them says where the skill runs).

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

Vocabulary for `/skill-fork-sync` (`../skill-fork-sync/SKILL.md`), which holds each declared skill dependency at a version this repo controls. Rationale: `docs/adr/0007-fork-and-pin-skill-dependencies.md` and `docs/adr/0008-diff-targeted-run-budget.md`.

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
