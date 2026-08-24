# A tracker read has one verified command, and it lives in the skill

[ADR 0002](0002-delegate-tracker-to-mattpocock-skills.md) made the per-project
`docs/agents/issue-tracker.md` the one home for the tracker CLI, and it closed with
"a new tracker is a new `issue-tracker.md`, not a skill change". That held while one
repo used one tracker.

**A second tracker arrived, and the flows need reads that no per-project file gives a
command for.** The **Ready queue** needs every open item with its blockers. A parent
close needs every child of a parent, closed children included. A **Review round**
number is a count of comments that carry `Verdict:`, and a stall count is the same
shape over `Stall:`. Each flow names its read in prose and stops there. So each
session improvises a command, and a per-project file that answers one tracker
answers nothing about the other.

**Measured on 2026-08-21, at the close of em-os #239 on a self-hosted GitLab.** The session
needed the children of the parent, closed children included. It improvised
`glab issue list -O json --state all`. That command has no `--state` flag, so `glab`
printed a decorated error block on standard error and exited 1. Standard output was
empty. A `json.load` on empty output then raised
`JSONDecodeError: Expecting value: line 1 column 1 (char 0)`, which names the parser
and never names the flag.

## The decision

**One reference file holds the reads, with a command for `gh` and a command for
`glab`.** It is [`references/tracker-reads.md`](../../references/tracker-reads.md).
One read per section, and the section heading is the query in the flow's own words.
Every command in it ran against a real GitHub repo and a real GitLab project before
it landed.

**A tracker read is checked before it is parsed.** The exit code is the check, and
the reference file holds the one shape for it. A session that reads a failure reports
the command and the tracker's own first line. It parses nothing.

**The per-project file keeps every fact that is per-repo data.** That is the CLI name,
the host, the label vocabulary and the board coordinates. It no longer restates the
read commands. It points at the reference instead.

## This narrows ADR 0002 and keeps its split

**The orchestrator still owns no tracker abstraction.** It reads the CLI name and the
labels from `docs/agents/issue-tracker.md`, exactly as before. What narrows is where
the *command* for a read lives. A third CLI now needs a skill change as well as a new
`issue-tracker.md`, and this repo supports two.

That price is small and the gain is measured. Two CLIs are what the repo declares
today ([`references/requirements.md`](../../references/requirements.md)), and
`scripts/worker_state.py` already holds a builder for each one. So the reference file
records what the code already knows, in the place a session reads.

This is a new ADR and not an edit to
[`0002-delegate-tracker-to-mattpocock-skills.md`](0002-delegate-tracker-to-mattpocock-skills.md),
per [`CLAUDE.md`](../../../CLAUDE.md).

## Considered Options

- **One reference file in the skill, with both commands per read** (chosen). A read has
  one home, and a session matches a need to a command without a guess. The two commands
  sit side by side, so a GitLab session never reads a GitHub command as its own. It also
  gives the tracker adapter the right commands before that adapter exists.
- **A command per read in each per-project `issue-tracker.md`** (rejected). An external
  skill writes that file, and it holds per-repo data. Every new repo then restates the
  same two commands. The em-os copy proves what happens next. It carried a warning about
  one flag, and a session found the second flag trap on the same command only when it hit
  that flag.
- **A command per read in the flow steps of `orchestrator/SKILL.md`** (rejected). The
  skill body traces each claim to a reference file. A command in a flow step is also a
  second source of truth beside the seam that already runs it.
- **A wrapper script per read** (rejected). Every read here is one line of an installed
  CLI. A script needs its own tests, its own install path and its own argument surface.
  A reference file states the same fact once.

## Consequences

- **A read that fails names its cause.** The check is one line of shell, and the
  reference file holds it. The `unreadable` outcome of a tick already worked this way
  ([ADR 0018](0018-the-worker-watch-is-a-stateless-seam.md)), so a session and a tick
  now report the same failure the same way.
- **The `glab issue list` flag trap has a home.** `-O json` is the JSON flag on that one
  command, `-F` is `--output-format`, and there is no `--state`. A session reads the row.
  It does not find the trap by accident.
- **Two facts about `glab` reach the reference and no skill body.** Its error block goes
  to standard error, and `glab issue list -F json` prints a text table and exits 0. Both
  are why an exit code is the check and a clean exit is not proof of JSON.
- **No flow gains a step.** Each flow keeps its prose and gains a pointer.
- **`scripts/close_item.py` still hardcodes `gh`.** This ADR gives the reads their
  commands and changes no seam. The adapter behind both seams is its own work item.
