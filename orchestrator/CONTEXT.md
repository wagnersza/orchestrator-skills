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
The class of job a work item represents, which selects its `(Model, Effort)` pair from config's `models:` block. Four: **heavy** (a contract, a schema, a code seam, three or more files, or an open decision. Strongest model, `high`), **medium** (the ordinary work item. Cheaper model, `medium`), **light** (one file, criteria fully enumerated, no open decision. Cheaper model, `low`), **review** (the adversarial reviewer. A different vendor, `high`). A spawn takes **medium**. It takes **heavy** only where one listed signal fires, and **light** only where all three listed conditions hold. A doubt is not a signal, so an item that fires no `heavy` signal and misses one `light` condition stays **medium**. `references/models.md` holds both lists and names the signal a spawn report must carry. A fix round steps the Role up one rung, and a failed **heavy** round steps its **Effort** up instead. This default reverses the default-heavy rule of `docs/adr/0005-role-based-model-and-effort.md`, and the rationale is `docs/adr/0059-medium-is-the-default-role.md`.
_Avoid_: tier, profile, model class.

**Cost profile**:
A preset `models:` block, one `(model, effort)` pair per **Role**, chosen as a set instead of role-by-role. Three: **conservative** (heavy opus-5 @ medium, medium sonnet-5 @ low, light sonnet-5 @ low), **balanced** (heavy opus-5 @ high, medium sonnet-5 @ medium, light sonnet-5 @ low. The default), **max-capability** (heavy opus-5 @ xhigh, medium opus-5 @ high, light sonnet-5 @ high). Every profile names a pair for all three implementation Roles, and `references/models.md` defines them with per-MTok prices and the review pair. `/orchestrator-setup` offers them as the first model question. A starting point, not a constraint, because any pair is editable in config afterwards. Note cheaper is not always cheaper: a mis-routed worker burns a round trip that costs more than the effort saved.
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
One cycle of adversarial review: the review worker posts a verdict (approve / request-changes + findings). On **request-changes**, the orchestrator re-prompts the **original impl worker** with the findings to fix, then re-reviews. Bounded at **3 rounds**. After approve — or after the 3rd round regardless — the orchestrator gathers evidence and moves the item to **human review**. The human reviews after the fixes, and merge stays a human step. The maintainer merges on the tracker, and that merge is what fires the **Close transaction** on the next tick. No worker merges, no session merges, and nothing is typed ([`docs/adr/0057-the-merge-is-the-second-act.md`](docs/adr/0057-the-merge-is-the-second-act.md)).

**Close transaction**:
The five steps that finish a **Work item**, in one fixed order, once its pull request is merged. They keep the numbers 4 to 8 they held when the transaction had eight, because `scripts/close_item.py` prints those numbers in every plan:

4. Verify the merge landed.
5. Pull the merge into the local default branch.
6. Verify the worktree is clean.
7. Flip the **Work-state labels** and close the item, as one step.
8. Remove the worktree.

**Steps 1 to 3 left the transaction, and the maintainer holds them.** They were resolve the conflicts against the default branch, push the mergeable branch, and merge the pull request. All three need judgement, and no script reads two versions of a change and decides what the merged file means. The maintainer does all three on the tracker instead. A conflict is visible in the pull request, where the tracker already shows it. **resolving-merge-conflicts** stays a verb the maintainer asks for ([`docs/adr/0057-the-merge-is-the-second-act.md`](docs/adr/0057-the-merge-is-the-second-act.md)).

**The five that stay need no judgement, so they belong to the seam.** They are two predicates, a pull, two tracker writes and a passed-in teardown command, which makes them an ordering and nothing else. One seam owns that ordering, because ordering is what code holds perfectly and prose holds poorly. That seam is `scripts/close_item.py`.

**The actor for all five steps is the tick of an Item automation**, and never a session and never a **Worker**. **The trigger is a merged pull request, and no verb and no label authorises it.** The **Worker watch** reads the branch off the worktree it watches, then asks the **Tracker adapter** for the pull request opened from that branch. Where the answer reads `MERGED`, it runs the five steps in its own process. The seam refuses rather than warns. An unmerged pull request and a dirty worktree each stop the transaction with a distinct exit code. **A refused transaction writes `needs-human` plus one comment that names what stopped it**, so the item stops rather than retrying every minute. Nothing is removed without a teardown command. Rationale, the rejected alternatives, and the risk accepted for an unattended actor: `docs/adr/0015-close-is-a-deterministic-transaction.md` and [`docs/adr/0057-the-merge-is-the-second-act.md`](docs/adr/0057-the-merge-is-the-second-act.md).

**A Merge train loops this transaction, and changes no step of it.** The five steps and
their order are the same whether one merge fires one close or a train runs ten, teardown
included. So a train adds one caller and no second merge path. **No tick calls a train**,
and it stays a verb the maintainer asks for
([`docs/adr/0037-the-merge-queue-is-an-ordered-train.md`](docs/adr/0037-the-merge-queue-is-an-ordered-train.md),
narrowed by [`docs/adr/0057-the-merge-is-the-second-act.md`](docs/adr/0057-the-merge-is-the-second-act.md)).
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
The external skill that owns **all** procedure for an in-progress merge or rebase conflict. It holds how to read the current state, how to find the intent behind each side, how to resolve a hunk, and which project checks to run afterwards. A dependency, not vendored — it ships inside `mattpocock-skills` (<https://github.com/mattpocock/skills>), so the plugin this repo already declares provides it. There is nothing separate to install. This repo states only *when* to invoke it: **where the maintainer asks for it**, in the orchestrator session, inside the item's worktree. No flow reaches it by itself, because the merge that used to need it is the maintainer's own act now ([`docs/adr/0057-the-merge-is-the-second-act.md`](docs/adr/0057-the-merge-is-the-second-act.md)). It copies no step of the procedure. Same posture as **prompt-improver** and **simple-english**, for the same reason: a copied rule set drifts from the upstream that maintains it. Install shapes and the check: `references/requirements.md`.
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
Where work items live (GitHub / GitLab / local markdown). The orchestrator does not own a tracker abstraction — it reuses the mattpocock engineering skills' config, written to `docs/agents/issue-tracker.md` by `/setup-matt-pocock-skills`. The two Python seams do own a **Tracker adapter**, which is a different thing: it holds the commands, and it reads none of that configuration.
_Avoid_: issue tracker, board (when the layer is meant).

**Tracker adapter**:
`scripts/tracker.py` — the one module that holds every tracker command the two Python seams run or print. One class, and a tracker is four values on it: the CLI name, the host, the repository and the fixture. Where two trackers disagree about a command, the branch is inside the one method that differs. So a new tracker lands here and in no seam. The commands are the verified ones `references/tracker-reads.md` holds as prose, and a read is checked before it is parsed in both places. It receives every per-repo value as an argument and reads no configuration file, which is what keeps it separate from the **Tracker** entry above. One fixture format serves every test under `scripts/`: one record per **Work item**, and one per pull request. A pull request record carries a `head` key. One read asks for the pull request opened from a branch, because a tick holds the branch and never a number. **A difference between two trackers can also be a count of commands.** One tracker closes a **Work item** and records the reason in the same command, and the other has no reason flag at all. **So the adapter answers the writes that close an item and the order they run in.** A caller iterates that answer, and it assembles no order of its own. The order matters, because an item that closes first closes with no reason on it. A caller reads no CLI name either (`docs/adr/0056-the-adapter-orders-a-multi-write-close.md`). Rationale, and the deferral it reverses: `docs/adr/0040-the-tracker-is-one-adapter-behind-both-seams.md`.
_Avoid_: tracker client, tracker wrapper, tracker layer (each one suggests a stack this deliberately is not), CLI abstraction.

**Work item**:
One tracked unit of work (a ticket / issue) a worker implements. Carries `## Blocked by` and `## Parent` edges per the `to-tickets` template.
_Avoid_: ticket, issue, task (pick one — prefer work item).

**Ready queue**:
The set of work items a worker can start now — labelled `ready-for-agent` with every `## Blocked by` edge closed. The orchestrator resolves this over whatever tracker `docs/agents/issue-tracker.md` names.

**The automation needs one fact more, and it is the card.** An item starts by itself only
where it carries the label *and* its card sits in the board's `To do` column. Both facts are
necessary. So a card in `To do` with no label never starts, and a labelled item whose card
sits in `Ready` never starts either. That second case is the point: `Ready` is the
maintainer's own lane, and no agent enters it. **Where `docs/agents/issue-tracker.md` names
no board, the label alone is the whole gate**, which is the fallback a **Merge queue**
already takes. A queue read reports every item that holds one fact and not the other, because
a forgotten drag otherwise reads as an empty queue
([`docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md`](docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md)).

**Story run**:
One user story the automation owns end to end: the `user-story` parent, plus every **Worker**
it spawns for that story's children, plus the story proof that runs before the parent closes.
It begins when the parent holds both facts of a **Ready queue** entry. It ends when the parent
closes.

**A child of a live Story run needs neither fact.** The queue tick descends from the parent to
its unblocked children and spawns them, and it writes no `ready-for-agent` label on any of
them. So the rule that only a human writes that label is unchanged, and one human act starts
ten children. A child that itself carries `user-story` is a nested spec, so the descent
continues to the implementable leaves, which is the rule the `work on N` flow already holds.

`work on N` stays as the manual override. It writes the label and spawns at once, and it is a
convenience rather than the mechanism
([`docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md`](docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md)).
_Avoid_: epic, batch, story batch (that names one spawn, not the whole run), campaign.

**Story slot**:
One unit of the bound on live **Story run**s. The count is `max_stories` in
**Config**, and its default is **2**. A run holds its slot until the parent closes, story
proof included, so a story with one child left still occupies one.

**A second roof stands beside it, and the lower one wins.** The worker cap bounds live
**Worker**s across every run, and it is **4**. The queue tick spawns nothing where either roof
is full. Two roofs exist because one of them alone fails: `max_stories` on its own multiplies
into 2 runs times the worker cap, and the worker cap on its own lets one wide story starve
every other
([`docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md`](docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md)).
_Avoid_: story limit, concurrency, quota, seat.

**Story proof**:
The proof that one whole user story works, run before its parent **Work item** closes. One
fresh **Worker** does it, in its own worktree cut from the default branch, so it reads every
child's merged code together. It drives the declared **Browser surface** through every user
story of the parent spec, and it boots the app per the **Project recipe**.

**The trigger is the close of the last child of a `user-story` parent**, and the proof runs
before the layer 5 story gate. An architecture opinion about a story that does not work is
premature.

**A failed proof stops the parent close.** A pass or a fail is a fact, and depth is a
judgement, so this step can block where **Layer** 5 cannot. The parent stays open at
`in-progress`, and each failure becomes a work item.

**It leaves two durable artifacts.** The first is an evidence note on the parent work item,
with one line per user story. The second is the generated Playwright spec, committed on its
own branch in a PR. The same **Commit slice** wires that spec into the project's own test
command, so the proof becomes a regression test.

**It adds no machinery.** The parent sits in the implementation **Position**, so the
**Worker watch** reads its **Checklist** and its **Gate record** with no edit. It reports the
`implementation-complete` outcome it already reports, and there is no new outcome, label
string, exit code or config field. It is reachable only where the **Project recipe** boots
something, so no story in this repo reaches one. Rationale, what it narrows and the accepted
risks:
[`docs/adr/0047-the-story-proof-runs-before-the-story-gate.md`](docs/adr/0047-the-story-proof-runs-before-the-story-gate.md).
_Avoid_: wrap-up (the **Close transaction** entry already avoids it), e2e test, story gate
(that names layer 5), smoke test.

**Touch set**:
The paths a **Work item** declares it will change, as a `## Touches` block of paths or globs
in the item body. It sits beside the `## Blocked by` and `## Parent` edges. The session that
creates the item writes the block, because `/to-spec`, `/to-tickets` and `/triage` all run in
the **inline** **Lane**. Nothing forks the external template to hold it.

**Two items start in parallel only where their touch sets are disjoint.** An overlap delays
the higher-numbered item and cancels nothing, so the next tick with a free slot spawns it.
The comparison is on where `parallel_check` in **Config** is `touches`, and an item with no
block is spawned alone. With `off` the tick compares nothing.

**It is a declaration, and not a constraint.** No gate reads a diff against it, and a worker
that edits an undeclared file breaks no rule. The test-merge inside `scripts/merge_train.py`
stays the real check, so a wrong block costs one park and never a wrong merge. That is the
same posture a **Merge train** takes on file overlap
([`docs/adr/0046-parallel-spawn-is-gated-on-a-declared-touch-set.md`](docs/adr/0046-parallel-spawn-is-gated-on-a-declared-touch-set.md)).
_Avoid_: file list, scope, footprint, blast radius (the last one already stands on **Halt
condition**), affected files.

**Merge queue**:
The set of open work items the maintainer asked to order and test-merge as one run. **The
ask is typed, and it names the items.** No label records it, because a label restates an
approval the maintainer already gave. The set is read fresh at the moment a **Merge train**
starts, which is the rule the **Ready queue** already takes, so nothing holds it between
reads. **It is a set and not a run**, because the order over it belongs to the train. An
empty queue is the resting state, and it is now the usual one. One merge closes one item on
the next tick, so no queue forms unless the maintainer asks for a train
([`docs/adr/0057-the-merge-is-the-second-act.md`](docs/adr/0057-the-merge-is-the-second-act.md)).
_Avoid_: merge backlog, ready-to-merge list, merge candidates, close queue.

**Merge train**:
One ordered run over a **Merge queue**. It resolves the order from a seam,
`scripts/merge_train.py`, and it hands the maintainer that order. **The maintainer merges
in it, and each merge closes its own item on the next tick.** So a merged item leaves no
worktree and no schedule behind, because step 8 of each **Close transaction** is that
teardown. **A branch that conflicts is parked, and the train keeps moving**: the session
reports the conflicting paths on the work item and carries on with the next branch. Nothing
unattended decides what a merged file means. **No tick calls a train.** The whole run exists
for one case: a maintainer who wants ten branches ordered and test-merged before they merge
any of them. The three ordering steps, the park rule and the seam's contract:
[`references/merge-train.md`](references/merge-train.md). Rationale, the rejected
alternatives and the accepted risk:
[`docs/adr/0037-the-merge-queue-is-an-ordered-train.md`](docs/adr/0037-the-merge-queue-is-an-ordered-train.md),
narrowed by [`docs/adr/0057-the-merge-is-the-second-act.md`](docs/adr/0057-the-merge-is-the-second-act.md).
_Avoid_: merge queue (that names the set, not the run), batch merge, auto-merge, merge
sequence.

**Config**:
The per-project orchestrator settings — tool, harness, model, adversarial-review policy, tracker-setup pointer, and the two dials the automation reads: `max_stories` (the **Story slot** count, default 2) and `parallel_check` (`touches` or `off`, which decides whether a **Touch set** gates a parallel spawn). Lives at `docs/agents/orchestrator.md` in the target repo (same pattern as `/setup-matt-pocock-skills`): human-editable markdown, seeded from a template in the skill folder, with a one-line summary block in `CLAUDE.md`. Per-project because different projects use different setups.

**Setup phase**:
The one-time interview that writes the Config — the user describes environment, tool, harness/CLI, models, adversarial-review policy, and the project recipes (setup command, run-for-evidence recipe + port scheme, optional DB gate, evidence expectations). Same posture as `/setup-matt-pocock-skills`: explore, present findings, confirm, write. Also ensures the tracker config exists (calls `/setup-matt-pocock-skills` if `docs/agents/issue-tracker.md` is missing).

**Work-state labels**:
The tracker labels that gate the queue and mark progress. **One family, four values, and it never stacks**: `ready-for-agent`, `in-progress`, `to-review` and `needs-human`. Owned by `docs/agents/issue-tracker.md` (`/setup-matt-pocock-skills`), not the orchestrator config — single source of truth. During an adversarial-review loop the item stays `in-progress` (a worker still owns it); it flips to the review label only when the loop concludes.

**One seam writes every value of this family, and no session writes one by hand.** The
**Worker watch** applies the transition it computed, in the process that read the labels. So
the removals and the addition are one tracker write, and nothing can stack
([`docs/adr/0056-the-tick-applies-the-transition-it-computed.md`](docs/adr/0056-the-tick-applies-the-transition-it-computed.md)).
The spawn claim goes through that same writer, under one named transition. The one other
writer is `scripts/close_item.py`, which flips the family and closes the item as one step of
a **Close transaction**.

**`needs-human` is the one label that stops the machine.** It means a seam refused. Every
tick reads it first and stays quiet, whatever the other facts say. It carries one comment
that says what the seam saw, and only the maintainer removes it. Where an item sits inside
an owned run is a **Position**, and **no label records that**
([`docs/adr/0053-one-work-state-label-and-a-computed-position.md`](docs/adr/0053-one-work-state-label-and-a-computed-position.md)).

**Board status**:
The `Status` field on a work item's card, where the tracker has a project board (GitHub Projects v2). **The board is an input, and nothing writes it.** One question is asked of it: is this item's card in the start column. So `Status` is no projection of the **Work-state labels**, and there is no derivation table, no reconcile pass and no sync command. `Tracker.board_status` is the one reader. The two coordinates and the name of the start column live in `docs/agents/issue-tracker.md`, alongside the labels; a repo with no board omits that section, and the label alone is the whole gate. Rationale: [`docs/adr/0054-the-board-is-an-input-not-a-mirror.md`](docs/adr/0054-the-board-is-an-input-not-a-mirror.md).

**One column is the start column, and its direction is board to label.** `To do` is that
column. A card the maintainer drags there means "an agent can start this now". It is the
second fact of a **Ready queue** entry, beside the `ready-for-agent` label
([`docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md`](docs/adr/0045-a-story-start-is-automatic-under-two-roofs.md)).

**A drag is intent in every column, because nothing overwrites a card.** No drag removes a
label, so a card dragged back out of `To do` changes nothing. A take-back is the maintainer
removing `ready-for-agent`, or writing `needs-human` plus a comment that says why.

**A closed item reaches `Done` through the board's own built-in item closed to Done
workflow.** The maintainer enables it in the project settings, and **no session can**,
because that switch is not in the API. `/orchestrator-setup` reads whether it is on and
says so.
_Avoid_: board state, column, board label, project status (the field is `Status`; the layer is Board status).

**Project recipe**:
Per-project commands the completion contract needs but that aren't tool/harness/model: setup command, run-for-evidence recipe + port scheme, optional DB gate, evidence expectations. Stored in Config so the skill body stays abstract ("boot per the run recipe", "if a DB gate is configured, satisfy it").

**Checklist**:
A persistent, file-based task list that survives context loss and works across every harness (unlike claude-only `TodoWrite`). Both the orchestrator and each worker keep one, so neither forgets a step (the documented "stalls before opening the MR" failure mode). Written as markdown checkboxes (`- [ ]` / `- [x]`) to `.orchestrator/checklist-<item>.md` at the worktree root (gitignored, torn down with the worktree). The worker ticks each step as it completes; the orchestrator reads the file to see exact progress and detect a stall (unchecked items + idle terminal → re-prompt with the remaining steps). **Where the Project recipe asks for browser proof, the proof is one more box.** It drops on the same blank-field rule every other box takes, and `run_recipe` is the field it reads. So "every box ticked" is the whole finish signal, and a worker works one list top to bottom. **The last box ends at the review note.** A worker posts that note and stops. The tick of an **Item automation** writes the review state, and a **Worker** writes no work-state label at all (`docs/adr/0056-the-tick-applies-the-transition-it-computed.md`).

**Position**:
Where a **Work item** sits inside its own run, computed from facts rather than read from a
label. Three values: **human review**, **review round** and **implementation**. The
**Worker watch** computes it in one function, and the outcome a tick can reach follows
from it.

The rule, in this order:

1. The `to-review` label on the item means human review.
2. Otherwise, a `Verdict:` comment newer than the last write to the **Checklist** means a
   review round.
3. Otherwise the item is in implementation.

**Human review is a work state, and never a position a worker owns.** So `to-review`
answers first, and nothing restates it. **One transition is due there, and a merged pull
request is the fact behind it.** The tick reads the branch off the worktree and asks for the
pull request opened from it. An open pull request is a quiet tick, and a branch with no pull
request is a quiet tick. A merged one is a whole **Close transaction**
([`docs/adr/0057-the-merge-is-the-second-act.md`](docs/adr/0057-the-merge-is-the-second-act.md)).

**Every fact it reads is a fact the tick already read.** Those facts are the **Work-state
labels**, the `Verdict:` comment list, and when the **Checklist** file was last written.
So a position costs no second tracker read and no second file.

**A cached answer can be stale, and a computed one cannot.** A second label family stored
this answer beside the facts that make it. So the two can disagree, and nothing repairs a
disagreement. A computed answer holds no second copy to repair.

**One label answers before every fact, and it is `needs-human`.** The tick reads that
label first and stays quiet, whatever the other facts say. So a paused item costs one
cheap read a minute and moves nowhere.

**Human review is also where an applied transition stops repeating.** A tick that writes
the review state leaves the item in a position whose one transition waits on the
maintainer's own merge. So the next tick reads that label, reads no merge, stays quiet, and
no suppression window is needed
([`docs/adr/0056-the-tick-applies-the-transition-it-computed.md`](docs/adr/0056-the-tick-applies-the-transition-it-computed.md)).

**A review round always has a verdict behind it.** That verdict is what computes the
position, so the verdict fires its own outcome and only implementation reads the
checklist, the process and the stall window. The cost is one accepted risk: a reviewer
that has posted no verdict yet reads as an implementation worker. The label family that
retired, what this supersedes and that risk:
[`docs/adr/0053-one-work-state-label-and-a-computed-position.md`](docs/adr/0053-one-work-state-label-and-a-computed-position.md).
_Avoid_: phase (that named the label family this replaces), stage, state, status (the last
two name the work-state axis), progress.

**Item automation**:
One schedule per live **Work item**, owned by the **Tool** rather than by a session's shell, named `orchestrator-item-<N>`. It ticks once a minute. **Its precheck is the whole tick**: the **Worker watch** seam asked for a transition, plus the write that transition carries. **The tick applies the transition it computed**, in the process that read the facts. It delivers nothing and it wakes nobody, so no transition can be lost to a delivery (`docs/adr/0056-the-tick-applies-the-transition-it-computed.md`).

**No agent runs on a tick.** The precheck exits non-zero on every path, so every run records as skipped at no token cost. The schedule's own prompt and provider stay inert. So the loop spends no tokens at all between the spawn of a worker and the maintainer's own reading of the pull request.

**It acts on two things: the work-state label of the item it watches, and the close of that item once its pull request merges.** It composes no prompt, kills no process, moves no card, merges nothing and spawns nothing. **At most one transition lands per run**, which is what stops a wrong computation cascading inside one minute. **The automation decides when, and the seam decides what** — the same split as a **Close transaction**, applied again. One per item, so a leaked schedule names the item it leaked from, and five siblings are five observed items. **One per item also means the schedule follows the live worker.** A session repoints the precheck when it spawns the next worker. So a review round watches the reviewer's worktree, and a fix round watches the implementation worktree again (`docs/adr/0026-the-automation-follows-the-live-worker.md`). Removal is step 8 of the **Close transaction** the tick itself runs, through the teardown command the spawn passes into the precheck. So a refused transaction leaves the item observed. A tool with no automation surface skips the tick and the spawn works unchanged. Rationale, the schedule that replaces the blocking watch, the `dead` and `stalled` split, and the rejected alternatives: `docs/adr/0022-item-automation-replaces-the-blocking-watch.md`.

**A tick in human review reads the pull request for the item's branch.** A merged one closes
the item, removes the worktree and removes the schedule. So the maintainer merges and types
nothing, and no label records the ask. **The tick still merges nothing, moves no card and
spawns nothing**
([`docs/adr/0057-the-merge-is-the-second-act.md`](docs/adr/0057-the-merge-is-the-second-act.md)).
_Avoid_: cron job, watcher, daemon, poller (each names a mechanism rather than the unit), run automation (`Run` is not a term this repo defines).

**Worker watch**:
The seam that observes a live **Worker**'s own work product and answers whether something needs a decision now. It is not a worker — it has no **Harness** and no **Model** — and it is not the orchestrator, because it composes nothing. Asked once per tick, it reads three facts on the file system plus the work item's labels and comments. In human review it reads one fact more, and that is the pull request opened from the item's branch. It answers one outcome. The printed line names which one fired. It composes no prompt, kills no process, moves no card and spawns nothing, so every destructive act but the close stays in a session a human can interrupt. It holds no state that changes an answer and it writes no file, which is what makes a restart after each re-prompt free.

**The one thing it writes is the transition it computed.** One function inside the seam owns every **Work-state label** swap, and it runs in the process that read those labels. The removals and the addition are one tracker write, so the two can never land apart. **At most one transition lands per run.** Three outcomes carry a label swap, and four refuse and leave the item where it is (`docs/adr/0056-the-tick-applies-the-transition-it-computed.md`).

**A stalled worker is the one transition a count decides: one re-prompt, and then a human.** Under the bound the tick posts one `Re-prompt:` comment, and the worker keeps its item. At the bound it writes `needs-human` with one comment and re-prompts nothing. **Nothing computes a rung**, because a bigger model is a judgement about a terminal this seam cannot see (`docs/adr/0058-one-re-prompt-then-a-human.md`).

**One outcome carries a whole Close transaction instead of a label swap, and it is `merged`.** The seam imports `scripts/close_item.py` and runs steps 4 to 8 in its own process. So one **Tracker adapter** serves both seams, and one read of the item serves both. That close is the one destructive act that left a session a human can interrupt, and two refusals in that seam stand in front of it ([`docs/adr/0057-the-merge-is-the-second-act.md`](docs/adr/0057-the-merge-is-the-second-act.md)).

**Two subcommands read one plan.** `phase` computes and writes nothing at all, so a maintainer dry-runs one item against a live tracker. `tick` computes through the same code path and then applies. That is the plan-and-execute split a **Close transaction** already holds, applied a second time.

**The watch decides when and what, and the session decides everything else** — spawns, prompts and reports. The merge is the maintainer's own act, and no session and no tick makes one. Ordering is what code holds perfectly and prose holds poorly, so the watch is a seam, `scripts/worker_state.py`. The seam stores no count. It reads both counts from the comment bodies it already holds: the **Review round** number, and the number of retries a stalled worker already got (`docs/adr/0058-one-re-prompt-then-a-human.md`). One **Item automation** per spawn, impl and review alike, because an opt-in observer is off exactly when the maintainer forgets. Rationale, the rejected alternatives, the reviewer accepted risk, and the context reset that goes with a re-prompt: `docs/adr/0018-the-worker-watch-is-a-stateless-seam.md`. The same seam answers readiness for every **Tool** with one check: `docs/adr/0019-readiness-is-a-tool-agnostic-process-check.md`.

**The blocking poll loop has retired, and the seam has not.** A loop in a background process of the orchestrator's own shell dies with that shell. It reports nothing when it does. So the trigger is an **Item automation**, and the seam is asked once per tick as a predicate. The exit-code contract survives, the statelessness survives, and the split above survives. What retired is the `watch` subcommand, with its bounded maximum wait and its per-role completion flag. The stall window survives as an argument to the predicate. `docs/adr/0022-item-automation-replaces-the-blocking-watch.md` narrows ADR 0018 to that extent and no further.
_Avoid_: watchdog, monitor, supervisor, liveness probe (each implies restart authority this thing does not have).

**Plugin root**:
The directory this plugin is installed in. It holds `scripts/`, so it is the only working directory a bare `python3 -m scripts.<module>` resolves from. It is also never the working directory of either caller: a session runs in a target repo checkout, and a tick runs in a worker worktree. Two install shapes carry it. A **plugin-cache install** puts it at `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`, where the version segment changes on every update. A **clone** puts it at the checkout. So no path is hardcoded.

**Every invocation of either seam names the file under this root**, as `python3 <plugin root>/scripts/<module>.py`. The **Orchestrator** resolves the root once per session, with one command that covers both shapes. It then substitutes the resolved value into each later invocation. A literal path is the only value that reaches an **Item automation**, because the **Tool** stores that precheck and runs it later, in a shell that saw no assignment. The spawn preflight proves the resolved command runs before the first automation exists, and a failure aborts the spawn.

**A checkout of this plugin is where the module form looks healthy.** This repo has its own `scripts/`, so the module form resolves from that checkout and runs a copy the session never reads. It reports success and it reads the wrong file, which makes it a fourth **failure mode that reports success**. Rationale, the two rejected working forms, the measurements and the ban's test: `docs/adr/0034-the-seam-invocation-carries-a-resolved-plugin-root.md`.
_Avoid_: skill root, install path, plugin directory, `$CLAUDE_PLUGIN_ROOT` (that names a harness variable which is unset in the shell a skill body opens).

**Completion signal**:
How a **Worker**'s finish is detected. Two shapes, and a tick reads exactly one — the item's **Position** names which, so no flag carries the worker's **Role**:

1. **A fully ticked checklist** — every box in `.orchestrator/checklist-<item>.md` is `- [x]`. This is the implementation worker's shape, read in the implementation position. It docks onto the completion contract the **Checklist** already is, so it adds no second place to record progress.
2. **A `Verdict:` comment** on the **Work item** — the review worker's shape, read in a review round, because a reviewer ticks no checklist. `Verdict:` is a fixed literal shared by the review prompt and the watch, and its value is `approve` or `request-changes`. It is quoted here, so a writing pass leaves it byte-identical.

**Shape 1 reads a third fact, and that is the Gate record.** A ticked checklist on its own says a worker believes it is done. A ticked checklist plus a green line for every required layer at the current `HEAD` says a machine agreed. A missing line, a malformed line, a non-zero exit or a stale `head_sha` fires the `gates-unproven` outcome instead. The **Orchestrator** then re-prompts the worker, and the item does not move to review. Which layers are required arrives as a repeatable flag the spawn resolves, so the seam still parses no config (`docs/adr/0036-a-gate-run-is-work-product.md`).

Both are **work product**: a worker writes them by doing the work. So neither one reports a finish for a dead worker. `orca terminal read` and `orca terminal wait --for tui-idle` both did report one, which is the failure mode recorded in `docs/adr/0017-gate-worker-readiness-on-a-process-check.md`. Why these two shapes, and why a reviewer's stall detection is weaker as accepted risk: `docs/adr/0018-the-worker-watch-is-a-stateless-seam.md`. Why the same seam also answers readiness for every **Tool**: `docs/adr/0019-readiness-is-a-tool-agnostic-process-check.md`.

**Both shapes are read once per tick, rather than polled in a loop.** An **Item automation** asks the seam for a transition every minute. So a signal is read at that moment, from disk or from the tracker, and nothing is held between reads. Shape 2 carries one fact more under the tick: **the count of `Verdict:` comments is the Review round number**. So *round 2 of 3* is read from the tracker rather than remembered by a session. Why the tick replaces the loop: `docs/adr/0022-item-automation-replaces-the-blocking-watch.md`.

**A third literal takes that same shape, and it is `Re-prompt:`.** It is not a completion signal, because a stall is the fact that fires it. **The count of `Re-prompt:` comments is the number of retries a stalled worker already got**, and the bound is one. So a restart reads the number a maintainer reads. **The literal has to open a line to count**, which is where the tick writes it. So prose that quotes it, in a review note or in this repo, spends no retry. `Re-prompt:` is quoted here for the same reason `Verdict:` is. One prompt writes it and the watch reads it, so a writing pass leaves it byte-identical (`docs/adr/0058-one-re-prompt-then-a-human.md`).
_Avoid_: done signal, exit signal, finish event, heartbeat (the last one names liveness, which is the signal this deliberately is not).

**Gate**:
One check with one command and one exit code. A non-zero exit stops the work, and no Gate has a warning state. **A check that reports and does not stop is not a Gate.** Each Gate belongs to one **Layer** and carries one hard threshold. The layer model, the threshold per Gate and the tool that holds it live in `references/quality-gates.md`. **Config is the source of truth for a threshold**, so the number in that file is the default this repo ships. Rationale, the rejected names and the accepted risk: `docs/adr/0032-quality-gates-are-a-layered-contract.md`.

**A DB gate is not a Gate.** The `db_gate` field of a **Project recipe** names the data an item's evidence needs, so it holds no command and no exit code, and it keeps its own name and its own checklist box.
_Avoid_: check, hook, step, quality check (each one is broader than a command with an exit code).

**Gate record**:
What a **Gate** run leaves on disk. `hooks/record.py` appends one line per gate run to
`.orchestrator/gates-<item>.jsonl` in the **Worker**'s own worktree, beside the
**Checklist**. The line is one JSON object with four keys: `command` is the gate command
that ran, `exit` is the code it returned, `utc` is when the run ended, and `head_sha` is
the commit it saw. `head_sha` is what ties a green run to a commit, because a green line
against a stale commit proves nothing. The format and its one home are
[`references/quality-gates.md`](references/quality-gates.md).

**The hook is the one writer, and the line is appended whatever the exit code is.** A gate
command runs and it exits, so a worker records nothing. A red run that writes no line
reads as a run that never happened.

**A green line proves that a command exited zero.** That is why the write sits in the hook
and not in the gate script: a record a model writes is a record a model can fake. The
**Worker watch** reads the record as the third fact of the **Completion signal**, so an
item whose record proves nothing stops before review instead. Rationale, the rejected
writers and the accepted gap where the hook can read no exit code:
[`docs/adr/0052-a-gate-blocks-and-a-hook-writes-its-record.md`](docs/adr/0052-a-gate-blocks-and-a-hook-writes-its-record.md).
It supersedes [`docs/adr/0036-a-gate-run-is-work-product.md`](docs/adr/0036-a-gate-run-is-work-product.md)
on two claims: a gate run is no longer work product, and the record no longer promises
that nothing blocks a push.
_Avoid_: gate log, gate report, audit trail, receipt (each one names a document a human reads, and this is a fact a tick reads).

**Layer**:
One of the five bands a **Gate** runs in, numbered 1 to 5. Layers 1 to 4 each hold one command, and each one stops a push. Layer 5 is advisory: it runs once per user story, and it emits candidate work items instead of an exit code. What that run leaves in the repo is the **Story gate report**. The word is **Layer** everywhere, and never "tier", because `_Avoid_: tier` already stands on **Role** and on **Cost profile**. One word must not name three axes. The five, with a command and a budget for each: `references/quality-gates.md`.
_Avoid_: tier, band, gate level, stage (the last one names a step of a run, and **Position** owns that axis).

**Story gate report**:
The HTML file `/improve-codebase-architecture` writes when **Layer** 5 runs. The orchestrator
session copies it into `docs/refactor-opportunities/` in the repo. The name is
`<story>-<slug>.html`, so the story number keeps two stories apart. It
holds the diagrams, the measurements and the rating behind each candidate, and every work item
the gate files links back to it.

**It is a point-in-time reading, and never a live document.** It records one commit on one day,
nothing updates it after the copy, and a later story writes a new file beside it. The session
commits it from the main checkout, where the gate runs. Rationale, the rejected homes and the
accepted limits:
[`docs/adr/0048-the-story-gate-report-is-a-repo-artifact.md`](docs/adr/0048-the-story-gate-report-is-a-repo-artifact.md).
_Avoid_: gate report (**Gate record** reserves it), architecture doc, refactor plan (a plan is a document someone keeps current, and this file is frozen).

**Halt condition**:
A policy that stops an infra plan before it applies. It is not a **Gate**: a Gate reads code that exists, and a Halt condition reads a plan for a change that has not happened. The term is declared here so that no later item defines it twice. The Terraform column is where it gets its rows, and that column is a work item of its own.
_Avoid_: guardrail, policy check, blast radius (none of the three says what stops).
