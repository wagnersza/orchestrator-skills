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
One cycle of adversarial review: the review worker posts a verdict (approve / request-changes + findings). On **request-changes**, the orchestrator re-prompts the **original impl worker** with the findings to fix, then re-reviews. Bounded at **3 rounds**. After approve — or after the 3rd round regardless — the orchestrator gathers evidence and moves the item to **human review**. The human reviews after the fixes, and the decision to merge stays theirs. Where the human then asks this session to merge and close, the orchestrator carries out that decision as a **Close transaction**. No worker merges, and no session merges unasked (`docs/adr/0016-the-orchestrator-merges-when-asked.md`).

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
The external skill that owns **all** writing rules for a **Prose deliverable**. It applies ASD-STE100 Simplified Technical English: the sentence limits, the vocabulary discipline, and the mode definitions. A dependency, not vendored: <https://github.com/AminBlg/SimpleEnglish> (MIT, no dependencies of its own). This repo states only *when* to invoke the skill and *what counts as a prose deliverable*, and copies no rule of the standard. Same posture as **prompt-improver**, for the same reason: a copied rule set drifts from the upstream that maintains it. The default mode here is **pragmatic**, which keeps domain vocabulary. Every glossary term in this file therefore survives a writing pass unchanged, and a worker must never "simplify" Tool, Harness, Worker or Effort. **Strict** mode needs the official ASD-STE100 dictionary, which this repo does not have, so nothing here asks for strict. The skill installs through the `skills` CLI (`npx skills add AminBlg/SimpleEnglish`), which registers no Claude plugin marketplace. Install shapes and commands: `references/requirements.md`.
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

**Delegation cap**:
The limit on how many sub-agents one **Worker** runs at the same time inside its
worktree. The number is **5**. The cap counts **concurrent** sub-agents, and it applies
**per worktree**, so it is not a total. A worker can run 5, collect their reports, and
then run 5 more. Five batch-spawned siblings are five worktrees, so each sibling gets
its own 5.

A worker delegates when the work splits, and it does not ask first. A read-only search
over six reference files is the case this exists for. The sub-agent spends its own
context on the reads, and it returns the file and the line. So the worker keeps its
context for the spec and the edit.

**A sub-agent reads, searches and reports. It never writes the item's source.** The
worker owns every edit, every **Commit slice** and every **Gate**, because those three
are the worker's contract and a sub-agent has no branch.

**The condition is a harness with a sub-agent surface.** `claude` has one. A harness
with none reads the same instruction, delegates nothing, and satisfies it.

**The adversarial reviewer is the one exception, and it keeps its own rule.** The
review prompt tells the reviewer to spawn no sub-agents. The reviewer is already the
second opinion, and an unattributed finding costs a **Review round**. Enforcement is
documentary, the same as the **Browser surface** rule. Nothing counts the sub-agents a
worker runs. Rationale, the sentence this reverses, why the number is not a config
field, and the accepted risk:
[`docs/adr/0035-workers-delegate-to-sub-agents-under-a-cap.md`](docs/adr/0035-workers-delegate-to-sub-agents-under-a-cap.md).
_Avoid_: fan-out budget, parallelism, worker pool (the last one names workers, which a
sub-agent is not), sub-worker.

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
A persistent, file-based task list that survives context loss and works across every harness (unlike claude-only `TodoWrite`). Both the orchestrator and each worker keep one, so neither forgets a step (the documented "stalls before opening the MR" failure mode). Written as markdown checkboxes (`- [ ]` / `- [x]`) to `.orchestrator/checklist-<item>.md` at the worktree root (gitignored, torn down with the worktree). The worker ticks each step as it completes; the orchestrator reads the file to see exact progress and detect a stall (unchecked items + idle terminal → re-prompt with the remaining steps). **The last box ends at the review note.** A worker posts that note and stops. The **Orchestrator** writes the review state, in one call with the removal of the `phase:review` label, because that pair names one moment (`docs/adr/0025-the-session-writes-the-review-state.md`).

**Phase**:
Which part of an owned run a **Work item** is in. A second label family, worn beside the **Work-state labels** rather than instead of them. Three values, **mutually exclusive inside the family — swap, never stack**: `phase:impl` (a worker is implementing), `phase:review` (a reviewer is reading the diff, fix rounds included), `phase:e2e` (a worker is proving the feature works through the **Browser surface**). So an owned item wears `in-progress` and exactly one `phase:*` label together. **Human review is `to-review` with no phase label**, because human review is already a work state. So removing the label *is* that transition, and no fact is written twice. **The Orchestrator writes that removal and `to-review` in one call**, and a **Worker** writes neither (`docs/adr/0025-the-session-writes-the-review-state.md`).

**The Board status derivation does not read it.** `Status` keeps deriving from the work-state labels alone. So a phase change moves no card, and `docs/adr/0009-labels-drive-board-status.md` needs no edit. The label strings, the swap rule and their `gh label create` lines live with every other label vocabulary, in `docs/agents/issue-tracker.md`. The tracker is the only store: a label survives a restart, a reboot and a teardown, so a session with no memory of the spawn recovers the phase with one read. `phase:e2e` is reachable only where the **Project recipe** boots something, so an item in this repo never wears it. Why a second family and not a second state machine, and the rejected options: `docs/adr/0021-phase-is-a-second-label-family.md`.
_Avoid_: stage, step, state, status (the last two name the work-state axis this deliberately is not), workflow phase.

**Item automation**:
One schedule per live **Work item**, owned by the **Tool** rather than by a session's shell, named `orchestrator-item-<N>`. It ticks once a minute. **Its precheck is the whole tick**: the **Worker watch** seam asked as a predicate, plus the delivery of the line that predicate printed. Where a **Phase** transition is due the seam wakes the **Orchestrator** with that line itself. **The target is that session's terminal handle, resolved at spawn.** The terminal title is the second target, and a comment on the work item is the third. The spawn report names which of the three is live (`docs/adr/0024-the-wake-target-is-a-resolved-handle.md`).

**No agent runs on a tick.** The precheck exits non-zero on every path, so every run records as skipped at no token cost. The schedule's own prompt and provider stay inert. So the only tokens the loop spends are the ones the **Orchestrator** spends when it answers a wake (`docs/adr/0027-the-tick-delivers-its-own-wake.md`).

**It never acts.** It writes no label, composes no prompt, spawns nothing and merges nothing. **Delivery is not action**: the line it sends is the line it printed, and every decision stays with the session that reads it. **The automation decides when, and the session decides what** — the same split as a **Close transaction** and a **Worker watch**, applied a third time. So every destructive act stays in a session a human can interrupt. One per item, so a leaked schedule names the item it leaked from, and five siblings are five observed items. **One per item also means the schedule follows the live worker.** The session repoints its precheck at each **Phase** transition. So a review round watches the reviewer's worktree, and a fix round watches the implementation worktree again (`docs/adr/0026-the-automation-follows-the-live-worker.md`). Removal folds into step 8 of a **Close transaction**, through the teardown command the session passes in, which means a refused transaction leaves the item observed. A tool with no automation surface skips the tick and the spawn works unchanged. Rationale, the schedule that replaces the blocking watch, the `dead` and `stalled` split, and the rejected alternatives: `docs/adr/0022-item-automation-replaces-the-blocking-watch.md`.
_Avoid_: cron job, watcher, daemon, poller (each names a mechanism rather than the unit), run automation (`Run` is not a term this repo defines).

**Worker watch**:
The seam that observes a live **Worker**'s own work product and answers whether something needs a decision now. It is not a worker — it has no **Harness** and no **Model** — and it is not the orchestrator, because it decides nothing. **It reports and never acts.** Asked once per tick, it reads two facts on the file system plus the work item's labels and comments. It answers one bit: a **Phase** transition is due, or nothing is. The printed line names which of the eight outcomes fired. It composes no prompt, kills no process, writes no label, and spawns nothing, so every destructive act stays in a session a human can interrupt. It holds no state that changes an answer, which is what makes a restart after each re-prompt free.

**It also delivers the line it printed, and that is not a decision.** The seam sends the wake to the first target that succeeds. That is the terminal handle, then the terminal title, then a comment on the **Work item**. Every prohibition above holds for that delivery, and the send carries nothing the seam chose. It exits non-zero on every path, which is what keeps an agent off a tick (`docs/adr/0027-the-tick-delivers-its-own-wake.md`).

**The watch decides when, and the session decides what** — the same split as a **Close transaction**, and the same reason: ordering is what code holds perfectly and prose holds poorly. So the watch is a seam, `scripts/worker_state.py`, and the session answers the wake with the flows `SKILL.md` already holds. The seam counts nothing. The session reads the stall count from the **Tracker** and restates it in its report (`docs/adr/0023-the-stall-count-is-a-tracker-comment.md`). One **Item automation** per spawn, impl and review alike, because an opt-in observer is off exactly when the maintainer forgets. Rationale, the rejected alternatives, the reviewer accepted risk, and the context reset that goes with a re-prompt: `docs/adr/0018-the-worker-watch-is-a-stateless-seam.md`. The same seam answers readiness for every **Tool** with one check: `docs/adr/0019-readiness-is-a-tool-agnostic-process-check.md`.

**The blocking poll loop has retired, and the seam has not.** A loop in a background process of the orchestrator's own shell dies with that shell. It reports nothing when it does. So the trigger is an **Item automation**, and the seam is asked once per tick as a predicate. The exit-code contract survives, the statelessness survives, and the split above survives. What retired is the `watch` subcommand, with its bounded maximum wait and its per-role completion flag. The stall window survives as an argument to the predicate. `docs/adr/0022-item-automation-replaces-the-blocking-watch.md` narrows ADR 0018 to that extent and no further.
_Avoid_: watchdog, monitor, supervisor, liveness probe (each implies restart authority this thing does not have).

**Plugin root**:
The directory this plugin is installed in. It holds `scripts/`, so it is the only working directory a bare `python3 -m scripts.<module>` resolves from. It is also never the working directory of either caller: a session runs in a target repo checkout, and a tick runs in a worker worktree. Two install shapes carry it. A **plugin-cache install** puts it at `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`, where the version segment changes on every update. A **clone** puts it at the checkout. So no path is hardcoded.

**Every invocation of either seam names the file under this root**, as `python3 <plugin root>/scripts/<module>.py`. The **Orchestrator** resolves the root once per session, with one command that covers both shapes. It then substitutes the resolved value into each later invocation. A literal path is the only value that reaches an **Item automation**, because the **Tool** stores that precheck and runs it later, in a shell that saw no assignment. The spawn preflight proves the resolved command runs before the first automation exists, and a failure aborts the spawn.

**A checkout of this plugin is where the module form looks healthy.** This repo has its own `scripts/`, so the module form resolves from that checkout and runs a copy the session never reads. It reports success and it reads the wrong file, which makes it a fourth **failure mode that reports success**. Rationale, the two rejected working forms, the measurements and the ban's test: `docs/adr/0034-the-seam-invocation-carries-a-resolved-plugin-root.md`.
_Avoid_: skill root, install path, plugin directory, `$CLAUDE_PLUGIN_ROOT` (that names a harness variable which is unset in the shell a skill body opens).

**Completion signal**:
How a **Worker**'s finish is detected. Two shapes, and a tick reads exactly one — the item's **Phase** names which, so no flag carries the worker's **Role**:

1. **A fully ticked checklist** — every box in `.orchestrator/checklist-<item>.md` is `- [x]`. This is the implementation worker's shape, read in `phase:impl` and in `phase:e2e`. It docks onto the completion contract the **Checklist** already is, so it adds no second place to record progress.
2. **A `Verdict:` comment** on the **Work item** — the review worker's shape, read in `phase:review`, because a reviewer ticks no checklist. `Verdict:` is a fixed literal shared by the review prompt and the watch, and its value is `approve` or `request-changes`. It is quoted here, so a writing pass leaves it byte-identical.

Both are **work product**: a worker writes them by doing the work. So neither one reports a finish for a dead worker. `orca terminal read` and `orca terminal wait --for tui-idle` both did report one, which is the failure mode recorded in `docs/adr/0017-gate-worker-readiness-on-a-process-check.md`. Why these two shapes, and why a reviewer's stall detection is weaker as accepted risk: `docs/adr/0018-the-worker-watch-is-a-stateless-seam.md`. Why the same seam also answers readiness for every **Tool**: `docs/adr/0019-readiness-is-a-tool-agnostic-process-check.md`.

**Both shapes are read once per tick, rather than polled in a loop.** An **Item automation** asks the seam for a **Phase** transition every minute. So a signal is read at that moment, from disk or from the tracker, and nothing is held between reads. Shape 2 carries one fact more under the tick: **the count of `Verdict:` comments is the Review round number**. So *round 2 of 3* is read from the tracker rather than remembered by a session. Why the tick replaces the loop: `docs/adr/0022-item-automation-replaces-the-blocking-watch.md`.
_Avoid_: done signal, exit signal, finish event, heartbeat (the last one names liveness, which is the signal this deliberately is not).

**Gate**:
One check with one command and one exit code. A non-zero exit stops the work, and no Gate has a warning state. **A check that reports and does not stop is not a Gate.** Each Gate belongs to one **Layer** and carries one hard threshold. The layer model, the threshold per Gate and the tool that holds it live in `references/quality-gates.md`. **Config is the source of truth for a threshold**, so the number in that file is the default this repo ships. Rationale, the rejected names and the accepted risk: `docs/adr/0032-quality-gates-are-a-layered-contract.md`.

**A DB gate is not a Gate.** The `db_gate` field of a **Project recipe** names the data an item's evidence needs, so it holds no command and no exit code, and it keeps its own name and its own checklist box.
_Avoid_: check, hook, step, quality check (each one is broader than a command with an exit code).

**Layer**:
One of the five bands a **Gate** runs in, numbered 1 to 5. Layers 1 to 4 each hold one command, and each one stops a push. Layer 5 is advisory: it runs once per user story, and it emits candidate work items instead of an exit code. The word is **Layer** everywhere, and never "tier", because `_Avoid_: tier` already stands on **Role** and on **Cost profile**. One word must not name three axes. The five, with a command and a budget for each: `references/quality-gates.md`.
_Avoid_: tier, band, gate level, stage (the last one names a step of a run, and **Phase** owns that axis).

**Halt condition**:
A policy that stops an infra plan before it applies. It is not a **Gate**: a Gate reads code that exists, and a Halt condition reads a plan for a change that has not happened. The term is declared here so that no later item defines it twice. The Terraform column is where it gets its rows, and that column is a work item of its own.
_Avoid_: guardrail, policy check, blast radius (none of the three says what stops).
