# The seam invocation carries a resolved plugin root

This plugin holds two seams, `scripts/close_item.py` and `scripts/worker_state.py`. Both
sat behind a bare `python3 -m scripts.<module>`. The `scripts/` package sits at the
**plugin root**, and that directory is never the working directory of either caller. A
session runs in a target repo checkout, and a tick runs in a worker worktree. So both
seams were unreachable as documented. Measured on 2026-08-21 against the installed
plugin `wsza/orchestrator-skills` 0.30.0:

| Working directory | Result |
|---|---|
| the plugin root | works |
| a target repo checkout | `ModuleNotFoundError: No module named 'scripts'` |
| a worker worktree | the same error |
| `orchestrator/`, the skill body's own directory | the same error |

The two failures are not alike. `close_item.py` fails loudly, and a session then runs
steps 4 to 8 of a **Close transaction** by hand. `worker_state.py` fails silently: the
tick precheck exits non-zero on the import, the **Tool** records the run as skipped, and
the schedule reads as healthy. So this is a fourth member of the family
[ADR 0017](0017-gate-worker-readiness-on-a-process-check.md) names, **a failure mode that
reports success**.

## The decision

**Every invocation of either seam names the file, under a plugin root that the session
resolved.** The form is `python3 <plugin root>/scripts/<module>.py`. The `<plugin root>`
part is a placeholder that carries a resolved value, the same way `<the path from op 2>`
does. No path is hardcoded, because the version segment of a cache install changes on
every update.

**The module form is banned, and a working prefix does not excuse it.** Three forms run
today, and the repo used all three. Only the file path is kept:

| Form | Runs | Why it is not the one |
|---|---|---|
| `python3 <plugin root>/scripts/<module>.py` | yes | **chosen.** `sys.path[0]` is the script's own directory, so the file that runs is the file that was named. |
| `PYTHONPATH=<plugin root> python3 -m scripts.<module>` | yes | `-m` puts the working directory **ahead** of `PYTHONPATH`. Inside a checkout of this plugin it imports the checkout's copy. |
| `cd <plugin root> && python3 -m scripts.<module>` | yes | It moves the working directory out from under every other argument. `close_item.py` reads a git worktree, so the move is not free. |

The middle row matters most. It reports success and it reads the wrong file. That is the
same shape as the defect this ADR closes. Measured from a worktree of this plugin:

```
$ PYTHONPATH=<plugin root> python3 -c "import scripts.worker_state as m; print(m.__file__)"
<the worktree>/scripts/worker_state.py
```

**The session resolves the root once, in one command, and that command covers both
install shapes.** A plugin-cache install puts the root at
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`. A clone puts it at the
checkout, which is what `~/.claude/plugins/marketplaces/<marketplace>/` holds. The
resolver reads the cache first. The cache holds the skill body that the session reads,
and a seam from one version beside a skill body from another is drift. The command is in
[`orchestrator/SKILL.md`](../../SKILL.md#config-first--always), once.

**The spawn preflight runs the resolved command before the first Item automation
exists.** It runs `--help`, which mutates nothing, and a non-zero exit **aborts the
spawn**. So an unreachable seam is a spawn that fails, and never a schedule that ticks
for a day and reports nothing.

**A checkout of this plugin is where the module form looks healthy.** This repo has its
own `scripts/`, so a tick against one of its worktrees resolved `scripts.worker_state`
from that worktree. The command worked and it ran the wrong copy. Two live schedules were
in that state on the day of this decision.

## The ban has a test, and no exemption list

`scripts/test_seam_invocations.py` walks every Markdown file in the repo. It reports each
line that prints the module form, with the file and the line number. It reads fenced code
blocks, and it does not skip them, because a command lives inside one. That is the
opposite of `scripts/test_links.py`, where a link inside a fence is example output.

The test has a positive half as well: the repo prints the path form at least once. A ban
on its own permits a repo that prints no invocation at all, and a session then has no
command to run.

The two seams also print the path form in their own `argparse` usage block. Each one
builds `prog` from its `__file__`, so `--help` prints the command that ran, from any
working directory. Neither seam gains a predicate, an outcome or an exit code from this
decision.

## Considered Options

- **The file path under a resolved root** (chosen) — one form everywhere, correct from
  any working directory, and it cannot read a second copy.
- **`PYTHONPATH=<plugin root>` with `-m`** (rejected) — it reports success and it reads
  the copy in the working directory first. The measurement in this ADR shows that. It
  leaves the false green in place inside this repo, where the defect was found.
- **`cd <plugin root> &&` with `-m`** (rejected) — every other argument then reads
  against a different working directory. One of the two seams operates on a git
  worktree.
- **Hardcode the version segment** (rejected) — `claude plugin update` writes a new
  directory, and the old one stays on disk. The hardcoded path then keeps working, and it
  runs a stale seam.
- **Read `$CLAUDE_PLUGIN_ROOT`** (rejected) — measured unset in a `Bash` tool call on
  2026-08-21. The harness sets it for hooks and commands, and not for a shell that a
  skill body opens. It is also a `claude` fact, and the resolver must work wherever the
  orchestrator session runs.
- **Ship the seams as executables in a `bin/` directory** (deferred) — Claude Code puts
  `<plugin root>/bin` on `PATH` for every installed plugin. Measured on 2026-08-21, in
  this session's own environment. That removes the root resolution completely. It is a
  larger change than this defect needs, and it is a `claude` fact where the resolver is
  not. It wants a work item of its own.
- **Leave the module form and document the working directory** (rejected) — the caller
  does not choose its working directory. A tick gets one from the **Tool**, and a session
  gets the target repo.

## Consequences

- **A resolved value is substituted, and not a shell variable.** Each tool call opens its
  own shell, so an assignment does not survive to the next one. The precheck of an **Item
  automation** is worse: the **Tool** stores that string and runs it later, in a shell
  that never saw the assignment. So the spawn writes the literal path into the precheck.
- **The three existing schedules that carry a working form keep working.** A repoint
  ([ADR 0026](0026-the-automation-follows-the-live-worker.md)) rewrites the precheck, so
  they converge on the path form as each item moves phase. The two that carry the bare
  form need the corrected precheck now, because neither one woke anything.
- **The resolver is a glob over two directories, so a machine with neither shape prints
  nothing.** That is deliberate. The preflight is what turns an empty root into a failed
  spawn with a named cause.
- **Accepted risk: the ban is a test over Markdown, and not over a running command.** A
  skill body that prints the path form with a wrong root still passes. The preflight is
  the guard for that case, and it runs once per session rather than once per invocation.
