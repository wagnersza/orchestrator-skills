#!/usr/bin/env python3
"""Turn one ready work item into a live worker, in seven ordered steps.

The order is the contract, the same way it is for `scripts/close_item.py`. This seam
runs the worktree, the terminal, the rendered prompt, the readiness gate, the
`in-progress` label, the follow-along panel, and the item schedule, always in that
order:

| Step | Behaviour |
|---|---|
| 1. worktree | create it, unless it already exists |
| 2. terminal | start the worker process, unless one already matches inside the worktree |
| 3. prompt | render `orchestrator/references/prompt.template.md`, and write it to disk |
| 4. readiness gate | the process check `scripts/worker_state.py` already owns. A failure here refuses the whole spawn, so no prompt is ever sent to a process that is not alive |
| 5. `in-progress` label | one label swap, through `scripts/worker_state.py`'s own writer. The prompt is delivered inside this same step, right after the label lands, so the label is always on the item before the prompt reaches the worker |
| 6. follow-along panel | opens the work item inside the worker's worktree. Skipped, and not refused, where the caller passes no `--panel-command` |
| 7. item schedule | named `orchestrator-item-<N>`, so one name still removes it at close. Skipped where the caller passes no `--schedule-command` |

**Plan mode is the default and mutates nothing.** It resolves every precondition from
the current state on disk and on the tracker. It emits JSON: the seven steps, each
marked `todo`, `done`, `refused`, `skipped` or `blocked`, the refusal reason, and the
exit code an `--execute` run uses:

    python3 <plugin root>/scripts/spawn_item.py --item 62 \\
        --worktree /path/to/worktree --process '<the pattern the harness ref gives>' \\
        --worktree-command '<the tool ref's create command>' \\
        --terminal-command '<the tool ref's start command, with {model} {effort} {harness} {tool} {yolo} {item}>' \\
        --send-command '<the tool ref's send command, with {prompt_file}>' \\
        --repo OWNER/NAME --config docs/agents/orchestrator.md --role light \\
        --item-title '<title>' --item-body '<body>' --checklist '<checklist text>' \\
        --gate-quick 'make quick' --gate-full 'make full' --gate-deep '' \\
        --skill /implement

**Execute mode runs that same plan in order** and stops at the first refusal:

    python3 <plugin root>/scripts/spawn_item.py ... --execute

**The seam reads `docs/agents/orchestrator.md` itself.** The `tool:`, `harness:`,
`yolo:` and `models.<role>` keys of its one `yaml` block answer the tool, the harness,
the yolo flag and the model pair. `--role` is the only judgement call a caller makes.
Every other value comes from the file. So no caller composes a launch command of its
own, and this seam parses no other part of that file.

**The seam holds no tool command.** `--worktree-command`, `--terminal-command`,
`--send-command`, `--panel-command` and `--schedule-command` all arrive as argument
strings, the way `scripts/close_item.py` already takes its teardown command. Five
tokens inside `--terminal-command` are filled from the config and the CLI before it
runs: `{tool}`, `{harness}`, `{yolo}`, `{model}`, `{effort}`, plus `{item}` on every
templated string. `--send-command` also takes `{prompt_file}`, and `--panel-command`
also takes `{worktree}`. A token a template does not use is simply never replaced.

**The readiness check is the process check `scripts/worker_state.py` already owns.**
This seam calls `worker_state.ready`, and invents no second signal. A worktree that
does not exist yet reads as *not yet due*, so a spawn plans cleanly before its first
step has run. A worktree that exists with no matching process reads as a refusal.

**The `in-progress` label is one call to `scripts/worker_state.py`'s own claim.** No
second writer exists for that label, so a caller here and the orchestrator's own claim
step can never disagree about how it is written.

The exit code carries the outcome, so the caller reports the cause and parses no
prose: 0 a resolved plan or a completed spawn, 1 a step's own command failed, 2 a
refusal (the reason is named), 64 a flag typo.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Both invocation forms reach the adapter: `python3 <plugin root>/scripts/spawn_item.py`
# puts `scripts/` on the path, and `python3 -m scripts.spawn_item` puts the repo root
# there (ADR 0034).
try:
    from . import worker_state
    from .tracker import GH, GLAB, Tracker, TrackerError
except ImportError:  # the type checker reads the package form above
    import worker_state  # type: ignore[no-redef, import-not-found]
    from tracker import (  # type: ignore[no-redef, import-not-found]
        GH,
        GLAB,
        Tracker,
        TrackerError,
    )

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPT_TEMPLATE = REPO_ROOT / "orchestrator" / "references" / "prompt.template.md"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2
EXIT_USAGE = 64

STATUS_DONE = "done"
STATUS_TODO = "todo"
STATUS_REFUSED = "refused"
STATUS_SKIPPED = "skipped"
STATUS_BLOCKED = "blocked"
STATUS_FAILED = "failed"

# Every Role the vocabulary names, in the order `orchestrator/CONTEXT.md` lists them.
# One list, read by the `--role` choices and by the config parse, so the two cannot
# disagree. `scripts/test_spawn_item.py` reads the same names out of `CONTEXT.md` and
# fails where this list drifts from it.
ROLES = ("heavy", "medium", "light", "review")


class ConfigError(RuntimeError):
    """The orchestrator config does not answer the tool, the harness, the yolo
    flag, or the model pair."""


class MissingInput(Exception):
    """A placeholder the prompt template holds that this run passed no value for."""


class CommandError(RuntimeError):
    """A caller-supplied command exited non-zero."""


# --- the orchestrator config (tool, harness, yolo, models) -------------------

FENCE = re.compile(r"```yaml\n(.*?)```", re.DOTALL)
ROLE_BLOCK = re.compile(r"^  (\w+):[^\n]*\n((?:    .+\n?)+)", re.MULTILINE)
MODELS_KEY = re.compile(r"^models:[^\n]*$", re.MULTILINE)


def models_block(body):
    """The lines under the config's `models:` key, and nothing else.

    The role scan is scoped to this block on purpose. `ROLE_BLOCK` matches any key at
    two spaces of indent whose own keys sit at four, and `gates:` holds two of those
    (`thresholds:` and `infra:`). So an unscoped scan cannot tell an unknown Role from
    a key that was never a Role, and it can only stay silent about both.
    """
    key = MODELS_KEY.search(body)
    if not key:
        return ""
    lines = []
    for line in body[key.end() :].splitlines(keepends=True):
        if line.strip() and not line.startswith("  "):
            break
        lines.append(line)
    return "".join(lines)


def parse_orchestrator_config(text):
    """The tool, the harness, the yolo flag and the model pair per role.

    Reads only the one `yaml` fenced block `docs/agents/orchestrator.md` holds, and
    only the keys this seam needs. Not a general YAML parser: the block's shape is
    fixed, so a hand-rolled scan over it needs no third-party dependency
    (the stdlib-only rule this repo's test suite already runs under).
    """
    fence = FENCE.search(text)
    if not fence:
        raise ConfigError("no ```yaml block in the config file, so nothing to read")
    body = fence.group(1)

    def scalar(name):
        match = re.search(rf"^{name}:\s*(\S+)", body, re.MULTILINE)
        return match.group(1) if match else ""

    roles = {}
    unknown = []
    for name, block in ROLE_BLOCK.findall(models_block(body)):
        if name not in ROLES:
            unknown.append(name)
            continue
        model = re.search(r"model:\s*(\S+)", block)
        effort = re.search(r"effort:\s*(\S+)", block)
        roles[name] = {
            "model": model.group(1) if model else "",
            "effort": effort.group(1) if effort else "",
        }
    if unknown:
        raise ConfigError(
            f"the config's models block names {', '.join(sorted(unknown))}, which "
            f"is no Role. The Roles are {', '.join(ROLES)}"
        )
    return {
        "tool": scalar("tool"),
        "harness": scalar("harness"),
        "yolo": scalar("yolo"),
        "roles": roles,
    }


def resolve_role(config, role):
    """The `(model, effort)` pair one role names, or a `ConfigError`."""
    pair = config["roles"].get(role)
    if not pair or not pair.get("model") or not pair.get("effort"):
        raise ConfigError(
            f"the config names no complete model/effort pair for role {role!r}"
        )
    return pair


def fill(template, **values):
    """`template` with every known `{token}` replaced by its value.

    A plain string replace, and never `str.format`: a caller's command can hold
    braces of its own (JSON, a shell brace expansion), and a token this seam does
    not name is left exactly as it was.
    """
    result = template
    for key, value in values.items():
        result = result.replace("{" + key + "}", str(value))
    return result


# --- the rendered prompt (four inputs, and no more) --------------------------

PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def render_prompt(text, item_number, item_title, item_body, checklist, gates, skill):
    """The one worker prompt, rendered from its four inputs.

    Two render rules, the ones `scripts/test_prompt_template.py` proves against the
    template on disk: a missing placeholder raises `MissingInput`, and a blank value
    drops the whole line that holds it.
    """
    values = {
        "item_number": item_number,
        "item_title": item_title,
        "item_body": item_body,
        "checklist": checklist,
        "gate_quick": gates.get("quick", ""),
        "gate_full": gates.get("full", ""),
        "gate_deep": gates.get("deep", ""),
        "skill": skill,
    }
    lines = []
    for line in COMMENT.sub("", text).splitlines():
        names = PLACEHOLDER.findall(line)
        missing = sorted(name for name in names if name not in values)
        if missing:
            raise MissingInput(", ".join(missing))
        if any(not values[name].strip() for name in names):
            continue
        lines.append(PLACEHOLDER.sub(lambda hit: values[hit.group(1)], line))
    return "\n".join(lines)


# --- the plan -----------------------------------------------------------------


def step(number, name, command, status, note, **extra):
    """One ordered step: what it runs, whether it is needed, and why."""
    return {
        "step": number,
        "name": name,
        "command": command,
        "status": status,
        "note": note,
        **extra,
    }


def not_reached(refusal):
    return f"not reached, because step {refusal['step']} refused"


def build_plan(args, tracker, config, pair):
    """Resolve every precondition and return the seven ordered steps.

    Reads only. A refusal at one step blocks every step after it, and the ones
    before it keep the status this read already gave them — the same cascade
    `scripts/close_item.py` runs.
    """
    steps = []
    refusal = None
    worktree = Path(args.worktree)

    # --- 1. the worktree.
    worktree_command = fill(args.worktree_command, item=args.item)
    if worktree.is_dir():
        steps.append(
            step(1, "worktree", worktree_command, STATUS_DONE, "already exists")
        )
    else:
        steps.append(
            step(
                1,
                "worktree",
                worktree_command,
                STATUS_TODO,
                "creates the worktree",
            )
        )

    # --- 2. the terminal.
    terminal_command = fill(
        args.terminal_command,
        item=args.item,
        tool=config["tool"],
        harness=config["harness"],
        yolo=config["yolo"],
        model=pair["model"],
        effort=pair["effort"],
    )
    live = worktree.is_dir() and worker_state.live_process(worktree, args.process)
    if live:
        pid, name, _ = live
        steps.append(
            step(
                2,
                "terminal",
                terminal_command,
                STATUS_DONE,
                f"pid {pid} ({name}) already matches {args.process!r} inside the worktree",
            )
        )
    else:
        steps.append(
            step(
                2,
                "terminal",
                terminal_command,
                STATUS_TODO,
                f"starts a process matching {args.process!r}",
            )
        )

    # --- 3. the rendered prompt. A missing input refuses the whole spawn: a
    #        prompt with a field missing must never reach a worker.
    prompt_path = Path(args.prompt_file)
    prompt_command = f"render {PROMPT_TEMPLATE.name} to {prompt_path}"
    try:
        rendered = render_prompt(
            PROMPT_TEMPLATE.read_text(encoding="utf-8"),
            str(args.item),
            args.item_title,
            args.item_body,
            args.checklist,
            {"quick": args.gate_quick, "full": args.gate_full, "deep": args.gate_deep},
            args.skill,
        )
    except MissingInput as exc:
        reason = f"the prompt template is missing a value for: {exc}"
        refusal = {"step": 3, "reason": reason, "exit_code": EXIT_REFUSED}
        steps.append(step(3, "prompt", prompt_command, STATUS_REFUSED, reason))
    else:
        already = prompt_path.is_file() and prompt_path.read_text() == rendered
        steps.append(
            step(
                3,
                "prompt",
                prompt_command,
                STATUS_DONE if already else STATUS_TODO,
                "already rendered at this path" if already else "renders the prompt",
                rendered=rendered,
            )
        )

    # --- 4. the readiness gate. `worker_state.ready` is the one signal, asked
    #        before the prompt is sent, so a dead process is a refusal and not a
    #        prompt landing in the shell underneath it.
    gate_command = (
        f"worker_state.py ready --worktree {worktree} --process {args.process!r}"
    )
    if refusal:
        steps.append(
            step(
                4, "readiness gate", gate_command, STATUS_BLOCKED, not_reached(refusal)
            )
        )
    else:
        code, line = worker_state.ready(worktree, args.process)
        if code == worker_state.EXIT_COMPLETE:
            steps.append(step(4, "readiness gate", gate_command, STATUS_DONE, line))
        elif code == worker_state.EXIT_GONE:
            steps.append(
                step(
                    4,
                    "readiness gate",
                    gate_command,
                    STATUS_TODO,
                    f"not yet checked: {line}",
                )
            )
        else:
            refusal = {"step": 4, "reason": line, "exit_code": EXIT_REFUSED}
            steps.append(step(4, "readiness gate", gate_command, STATUS_REFUSED, line))

    # --- 5. the in-progress label. The prompt is delivered here too, right after
    #        the label lands, so a second tick can never hand the item out twice
    #        and the label is always on before the prompt reaches the worker.
    send_command = fill(args.send_command, item=args.item, prompt_file=prompt_path)
    label_command = f"worker_state.py tick --claim --item {args.item}"
    label_and_send = f"{label_command} && {send_command}"
    if refusal:
        steps.append(
            step(
                5,
                "in-progress label",
                label_and_send,
                STATUS_BLOCKED,
                not_reached(refusal),
            )
        )
    else:
        labels, _ = tracker.item_facts(args.item)
        if worker_state.NEEDS_HUMAN in labels:
            reason = (
                f"work item #{args.item} carries the {worker_state.NEEDS_HUMAN} "
                f"label, so no claim runs and no prompt is sent until the "
                f"maintainer clears it"
            )
            refusal = {"step": 5, "reason": reason, "exit_code": EXIT_REFUSED}
            steps.append(
                step(5, "in-progress label", label_and_send, STATUS_REFUSED, reason)
            )
        elif worker_state.IN_PROGRESS in labels:
            steps.append(
                step(
                    5,
                    "in-progress label",
                    label_and_send,
                    STATUS_DONE,
                    f"work item #{args.item} already carries "
                    f"{worker_state.IN_PROGRESS}",
                )
            )
        else:
            steps.append(
                step(
                    5,
                    "in-progress label",
                    label_and_send,
                    STATUS_TODO,
                    "writes the label, then sends the rendered prompt",
                )
            )

    # --- 6. the follow-along panel. Skipped where the caller names no command,
    #        and that absence is never a refusal.
    if refusal:
        status, note = STATUS_BLOCKED, not_reached(refusal)
    elif not args.panel_command:
        status, note = (
            STATUS_SKIPPED,
            "there is no --panel-command, so this tool records the operation as "
            "unsupported",
        )
    else:
        status, note = STATUS_TODO, "opens the work item inside the worker's worktree"
    panel_command = fill(args.panel_command or "", item=args.item, worktree=worktree)
    steps.append(
        step(6, "follow-along panel", panel_command or "(unsupported)", status, note)
    )

    # --- 7. the item schedule, named `orchestrator-item-<N>` so a close removes
    #        it under one name.
    if refusal:
        status, note = STATUS_BLOCKED, not_reached(refusal)
    elif not args.schedule_command:
        status, note = (
            STATUS_SKIPPED,
            "there is no --schedule-command, so this tool records the operation as "
            "unsupported",
        )
    else:
        status, note = STATUS_TODO, f"creates orchestrator-item-{args.item}"
    schedule_command = fill(args.schedule_command or "", item=args.item)
    steps.append(
        step(7, "item schedule", schedule_command or "(unsupported)", status, note)
    )

    return steps, refusal


def build(args, tracker, config, pair):
    """The whole plan, ready to read or to run."""
    steps, refusal = build_plan(args, tracker, config, pair)
    return {
        "generated_by": "scripts.spawn_item",
        "mode": "execute" if args.execute else "plan",
        "mutates": "the steps marked todo below" if args.execute else "nothing",
        "item": args.item,
        "role": args.role,
        "worktree": str(Path(args.worktree)),
        "refused": refusal,
        "exit_code": refusal["exit_code"] if refusal else EXIT_OK,
        "ran": [],
        "steps": steps,
    }


# --- execute --------------------------------------------------------------


def execute(plan, tracker, prompt_path, item, worktree, process):
    """Run the plan in order and stop at the first refusal.

    The same split `scripts/close_item.py` runs: nothing here is re-derived, and
    every step after a refusal keeps the `blocked` status the plan already gave it.

    **Step 4 is the one step this loop re-checks rather than runs.** A worktree
    that did not exist at plan time left the gate `todo`, because there was
    nothing yet to check. By the time this loop reaches it, steps 1 and 2 have
    run, so the gate asks `worker_state.ready` again, for real, before step 5
    ever sends a prompt.
    """
    for entry in plan["steps"]:
        if entry["status"] == STATUS_REFUSED:
            return plan["exit_code"]
        if entry["status"] != STATUS_TODO:
            continue
        if entry["step"] == 4:
            code, line = worker_state.ready(worktree, process)
            if code != worker_state.EXIT_COMPLETE:
                entry["status"] = STATUS_REFUSED
                entry["note"] = line
                plan["refused"] = {"step": 4, "reason": line, "exit_code": EXIT_REFUSED}
                plan["exit_code"] = EXIT_REFUSED
                return EXIT_REFUSED
            entry["status"] = STATUS_DONE
            continue
        try:
            run_step(entry, tracker, prompt_path, item)
        except (CommandError, TrackerError) as exc:
            entry["status"] = STATUS_FAILED
            plan["error"] = str(exc)
            plan["exit_code"] = EXIT_ERROR
            return EXIT_ERROR
        entry["status"] = STATUS_DONE
        plan["ran"].append(entry["command"])
    return plan["exit_code"]


def run_command(command):
    """Run one caller-supplied command through a shell, or raise `CommandError`."""
    proc = subprocess.run(command, shell=True, capture_output=True, text=True)
    if proc.returncode != 0:
        raise CommandError(
            f"{command} failed: {proc.stderr.strip() or proc.stdout.strip()}"
        )


def run_step(entry, tracker, prompt_path, item):
    """Run one step's own action."""
    if entry["step"] in (1, 2, 6, 7):
        run_command(entry["command"])
        return
    if entry["step"] == 3:
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(entry["rendered"])
        return
    if entry["step"] == 5:
        code, line = worker_state.claim(item, tracker)
        if code != worker_state.EXIT_APPLIED:
            raise CommandError(f"the claim did not apply: {line}")
        _, _, send_command = entry["command"].partition(" && ")
        run_command(send_command)
        return
    raise CommandError(f"step {entry['step']} has no runner")


# --- CLI --------------------------------------------------------------------


class UsageExitParser(argparse.ArgumentParser):
    """A parser whose usage errors exit 64, outside the outcome codes above."""

    def exit(self, status=0, message=None):
        if message:
            self._print_message(message, sys.stderr)
        sys.exit(EXIT_USAGE if status else status)


def main(argv=None):
    parser = UsageExitParser(
        prog=f"python3 {Path(__file__).resolve()}",
        description=(
            "Turn one ready work item into a live worker, in seven ordered steps: "
            "the worktree, the terminal, the rendered prompt, the readiness gate, "
            "the in-progress label, the follow-along panel, and the item schedule. "
            "The default prints the plan as JSON and mutates nothing. --execute runs "
            "the plan and stops at the first refusal."
        ),
    )
    parser.add_argument("--item", required=True, type=int, help="the work item number")
    parser.add_argument(
        "--role",
        required=True,
        choices=ROLES,
        help="which model/effort pair to read from the config's models block",
    )
    parser.add_argument(
        "--config",
        default="docs/agents/orchestrator.md",
        help="the orchestrator config this seam reads its tool, harness, yolo flag "
        "and model pair from (default: docs/agents/orchestrator.md)",
    )
    parser.add_argument("--worktree", required=True, help="the worker's worktree")
    parser.add_argument(
        "--process",
        required=True,
        metavar="PATTERN",
        help="a regular expression for the agent's process name. The caller reads "
        "it from references/harnesses/<harness>.md, so this seam names no harness",
    )
    parser.add_argument(
        "--worktree-command",
        required=True,
        help="the command that creates the worktree, with the ids already in it. "
        "The caller reads it from its tool reference, so this seam holds no "
        "command of its own",
    )
    parser.add_argument(
        "--terminal-command",
        required=True,
        help="the command that starts the worker process. Takes {tool}, {harness}, "
        "{yolo}, {model}, {effort} and {item}; this seam fills the first five from "
        "the config and --role, so no caller composes a launch command",
    )
    parser.add_argument(
        "--send-command",
        required=True,
        help="the command that delivers the rendered prompt to the worker. Takes "
        "{prompt_file} and {item}",
    )
    parser.add_argument(
        "--panel-command",
        default="",
        help="the command that opens the work item inside the worker's worktree. "
        "Takes {item} and {worktree}. With no value this step is skipped, and that "
        "is never a refusal",
    )
    parser.add_argument(
        "--schedule-command",
        default="",
        help="the command that creates the item's schedule, named "
        "orchestrator-item-<N> by the caller. Takes {item}. With no value this "
        "step is skipped, and that is never a refusal",
    )
    parser.add_argument(
        "--prompt-file",
        default="",
        help="where the rendered prompt is written (default: "
        "<worktree>/.orchestrator/prompt-<item>.md)",
    )
    parser.add_argument("--item-title", required=True, help="the work item's title")
    parser.add_argument("--item-body", required=True, help="the work item's body")
    parser.add_argument(
        "--checklist", required=True, help="the seeded Checklist file's text"
    )
    parser.add_argument("--gate-quick", default="", help="config's gates.quick command")
    parser.add_argument("--gate-full", default="", help="config's gates.full command")
    parser.add_argument("--gate-deep", default="", help="config's gates.deep command")
    parser.add_argument(
        "--skill", required=True, help="the routed skill, as a literal invocation"
    )
    parser.add_argument(
        "--repo",
        default="",
        help="the tracker repository the labels and the claim write sit on, as "
        "OWNER/NAME",
    )
    parser.add_argument(
        "--tracker-cli",
        default=GH,
        choices=(GH, GLAB),
        help="which CLI reads the labels and writes the claim. The caller resolves "
        "it from docs/agents/issue-tracker.md",
    )
    parser.add_argument(
        "--tracker-host",
        default="",
        metavar="HOST",
        help="the tracker host, for a server the CLI does not reach by default",
    )
    parser.add_argument(
        "--gh-fixture",
        help="JSON that stands in for the tracker reads and writes, so a plan needs "
        "no network and no login (used by the tests)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="run the plan instead of printing it. The run stops at the first refusal",
    )
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args(argv)

    if not args.prompt_file:
        args.prompt_file = str(
            Path(args.worktree) / ".orchestrator" / f"prompt-{args.item}.md"
        )

    tracker = Tracker(args.tracker_cli, args.tracker_host, args.repo, args.gh_fixture)

    try:
        config = parse_orchestrator_config(
            Path(args.config).read_text(encoding="utf-8")
        )
        pair = resolve_role(config, args.role)
        plan = build(args, tracker, config, pair)
    except (ConfigError, OSError, TrackerError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    code = (
        execute(
            plan,
            tracker,
            Path(args.prompt_file),
            args.item,
            Path(args.worktree),
            args.process,
        )
        if args.execute
        else plan["exit_code"]
    )
    print(json.dumps(plan, indent=args.indent))
    return code


if __name__ == "__main__":
    sys.exit(main())
