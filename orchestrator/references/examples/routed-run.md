<!--
Worked example: one end-to-end run over both lanes — an `inline` verb that writes a
spec, then a `worker` verb that spawns against it. Shows where the routed skill
appears in the prompt and in the report. Not loaded unless referenced.
The config it runs against is the peer example, fullstack-app.md.
-->

# A routed run, end to end (example)

Two turns on `acme-app`, against the config in
[`fullstack-app.md`](fullstack-app.md) — `tool: orca`, `harness: claude`,
`models.heavy: opus-5 @ xhigh`, `models.light: sonnet-5 @ medium`, `review.enabled:
false`, GitLab tracker. This repo has no runtime, so a trace of the flow is how the
routing contract gets tested. The rules are in [`../../SKILL.md`](../../SKILL.md).
The rows are in [`../skill-routing.md`](../skill-routing.md).

## Turn 1 — `/orchestrator to-spec` (lane `inline`)

The user has just finished describing a contacts-import feature in this session.

- **Resolve the verb.** `to-spec` matches a row: skill `/to-spec`, lane `inline`.
- **Invoke it here.** In the main checkout (`~/git/acme-app`), on the default branch.
  No worktree, no branch, no spawn. The row's Notes say what to hand it: the
  conversation so far, plus the tracker config at `docs/agents/issue-tracker.md`. The
  same Notes say the skill applies `ready-for-agent` itself, so the orchestrator
  writes no label of its own.
- **The output is non-source** — one issue on the tracker — which is why this row is
  `inline` and no rule is breached.
- **Report.** `/to-spec ran here. Spec is #61, labelled ready-for-agent.`

The user reads the spec, and the acceptance criteria are enumerated on it.

## Turn 2 — `/orchestrator implement #61` (lane `worker`)

- **Resolve the verb.** `implement` matches a row: skill `/implement`, lane `worker`.
  The orchestrator invokes nothing. The invocation goes to the worker.
- **Classify the role, separately.** #61 adds a page, an API route and a migration,
  so it is `heavy`, and `db_gate` is configured, which makes it heavy by definition.
  `models.heavy` resolves to `opus-5 @ xhigh`. The skill and the model are two
  resolutions over one item, and neither decided the other.
- **Preflight the routed skill.** The harness is `claude`, so `/implement` is a plugin
  skill. The `mattpocock-skills` plugin check runs, and the plugin is installed. If it
  were missing, the spawn aborts here, before the worktree exists. The report then says
  which skill, which harness, and that `/orchestrator-setup` installs it.
- **Worktree + worker.** Branch `61-contacts-import` off the default branch,
  `pnpm install` through the setup hook, then `claude --model opus --effort xhigh
  --dangerously-skip-permissions`.
- **Claim #61** — `ready-for-agent` → `in-progress`, and the card to `In progress` in
  the same step.
- **Draft the prompt.** The routed skill is one item in the draft, beside the rest:

  ```
  Run /implement.

  Work item: #61 (contacts import). Acceptance criteria: <from the item>.
  Checklist: .orchestrator/checklist-61.md — work it top to bottom, tick each box,
  do not end the turn while any box is unchecked.
  Recipe: scripts/run.sh start -d -a 8061 -w 3061 -g 3161. DB gate: <the config's>.
  Evidence: real-data proof plus the full suite.
  Do not touch: <the scope edges, the Browser surface edge included>.
  ```

  `Run /implement.` is an imperative in the prompt's own voice, not *you may use*.
  The checklist is untouched. `/implement` runs **inside** the completion contract,
  and `.orchestrator/checklist-61.md` is still the file this session reads for
  progress.
- **Run it through `prompt-improver`**, name `opus-5`, and say it is an
  **agentic-pipeline prompt**. That framing keeps the tight task framing and the
  checklist, and applies only the model tuning. This is what leaves `Run /implement.`
  a literal command in the sent prompt, instead of a paraphrase of one.
- **Report.** `#61 61-contacts-import spawned · /implement · heavy · opus-5 · xhigh.
  1 worker live.` Four fields: the skill first, then the role, the model and the
  effort.

The worker's first act inside the worktree is `/implement`. It then works the
checklist to the review note and stops there, exactly as before this routing
existed.

## The same two turns on a `codex` harness

Everything above holds except the shape of one line. `codex` parses no slash command,
so the prompt carries the row's *Without slash commands* prose in place of
`Run /implement.` — implement the item test-first, at agreed seams, run the type check
and the full suite, review the diff against the criteria, then commit. The preflight
changes with it. There is no plugin to check, so what the orchestrator confirms is that
the row has that prose. A `/implement` sent to `codex` is the failure this avoids. The
worker reads it as text and starts cold, and the transcript looks like it worked.

Turn 1 cannot happen on a session with no slash commands at all. There the
orchestrator answers `to-spec` freehand and its report says the skill was
unreachable.

## Two variants worth tracing once

- **A mixed batch.** `work on #58, max 5` finds two unblocked children: #59, a bug
  with reproduction steps, and #60, a new endpoint. The verb resolves **per child**,
  so #59's prompt carries `/diagnosing-bugs` and #60's carries `/implement`. The
  report gives four fields per child: `#59 → /diagnosing-bugs · light · sonnet-5 ·
  medium`, `#60 → /implement · heavy · opus-5 · xhigh`. One blanket skill for the
  batch is the same defect as one blanket model.
- **A fix round.** Review is off on this config, so this is the on-demand path:
  `review #61 adversarially` spawns a `gpt-5.6-terra` reviewer, which requests
  changes. The fix prompt goes back to the original #61 worker and re-enters
  `/implement` — the skill the original spawn used. Not `/code-review`, although a
  review produced the findings, and not a fresh resolution of the verb. The effort
  steps up a rung, and the skill does not change.
