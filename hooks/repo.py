#!/usr/bin/env python3
"""What a hook needs to know about the repository it fired in.

Three hooks fire in every session on the machine. Each one starts from the same handful
of facts:

- which directory the session opened,
- whether this plugin has anything to say about that directory,
- which work item the worktree implements,
- which commands the `gates:` block of config names,
- what the work-state label family is,
- which commit `HEAD` is.

**This module is the one home of those reads.** A hook holds no private copy of one,
because a read with two copies drifts.

It refuses nothing and it performs nothing, so the plane law holds
(`orchestrator/docs/adr/0051-a-hook-refuses-and-a-seam-performs.md`). It is a library of
the plane and not a hook. So `hooks/hooks.json` names no event for it, and the manifest
names nothing at all
(`orchestrator/docs/adr/0060-the-manifest-names-no-standard-hook-file.md`).

**It has no suite of its own.** Every function here sits on the path of a hook, and the
three hook suites drive those hooks as processes. `scripts/test_worker_state.py` drives
the fourth caller of `head_sha`. The plane is `orchestrator/references/hooks.md`.
"""

import os
import re
import subprocess
from pathlib import Path

# The two facts that say this repo is orchestrated. Either one is enough: a main
# checkout carries the config, and a worker worktree carries the checklist directory. A
# directory with neither is a repo this plugin has nothing to say about.
CONFIG = Path("docs") / "agents" / "orchestrator.md"
ORCHESTRATOR_DIR = ".orchestrator"

# The file that owns the tracker vocabulary, and the section of it that holds the
# work-state label family. No label string is copied into the plane.
TRACKER_CONFIG = Path("docs") / "agents" / "issue-tracker.md"
LABEL_SECTION = "## Work-state labels"
TABLE_LABEL = re.compile(r"^\|[^|]*\|\s*`([^`]+)`\s*\|")

# The checklist file, whose name carries the item number.
CHECKLIST_GLOB = "checklist-*.md"
CHECKLIST_PREFIX = "checklist-"

# The three layer keys of the `gates:` block. Layer 5 is not a Gate: the `story` key
# holds a verb with no exit code, so it stops nothing and it records nothing
# (`orchestrator/references/quality-gates.md`).
GATE_LAYERS = ("quick", "full", "deep")

# One line of that block: the key, then a quoted or a bare value. A trailing comment is
# not part of the command. The expression is declared here once, and the layer keys
# above are what it matches, so a fourth layer is one edit.
GATE_LINE = re.compile(
    rf"""^\s+({"|".join(GATE_LAYERS)}):\s*(?:"([^"]*)"|'([^']*)'|([^#\n]*))"""
)


def project_dir():
    """The repository this session opened.

    The harness passes it, and the working directory answers where it did not.
    """
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())


def plugin_root():
    """The directory this plugin is installed in.

    The harness passes it to every hook. This file sits one level under that root, so
    the parent answers where the variable is unset.
    """
    return Path(
        os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent
    )


def orchestrated(root):
    """Whether this repo is one the orchestrator skill runs on."""
    return (root / CONFIG).is_file() or (root / ORCHESTRATOR_DIR).is_dir()


def item_number(root):
    """The work item this worktree implements, or an empty string.

    The checklist file names it, so no field of config reaches this read. A directory
    with no checklist is not a worker's worktree.
    """
    found = sorted((root / ORCHESTRATOR_DIR).glob(CHECKLIST_GLOB))
    return found[0].stem[len(CHECKLIST_PREFIX) :] if found else ""


def work_state_labels(root):
    """The work-state label family, from the file that owns the vocabulary.

    A table row holds the label in its second cell. Where the file is absent, or holds
    no such table, this reads as an empty family and each caller says what that means
    for it.
    """
    path = root / TRACKER_CONFIG
    if not path.is_file():
        return []
    labels = []
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line.strip() == LABEL_SECTION
            continue
        if not inside:
            continue
        match = TABLE_LABEL.match(line)
        if match:
            labels.append(match.group(1))
    return labels


def gate_commands(root):
    """Every `(layer, command)` pair the `gates:` block of config names.

    The block is the one source, and the pairs come back in the order the layers run.
    **A blank command is not a Gate**: a layer the profile dropped names no command, so
    it is left out here. Otherwise a repo on the `lite` profile, where `deep` is blank,
    can never push and every call records under an empty name.

    A caller that needs the commands alone reads the second half of each pair.
    """
    path = root / CONFIG
    if not path.is_file():
        return []
    gates = []
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("gates:"):
            inside = True
            continue
        if inside and line.strip() and not line.startswith((" ", "\t")):
            break
        if not inside:
            continue
        match = GATE_LINE.match(line)
        if match:
            value = next(group for group in match.groups()[1:] if group is not None)
            if value.strip():
                gates.append((match.group(1), value.strip()))
    return gates


def head_sha(root):
    """The commit this worktree sits on, or an empty string.

    **The empty string is the one failure value**, and it replaces the `unknown` the
    record hook used to write. Every caller tests this value for truth, so a value that
    means "no commit" has to be falsy. `unknown` is seven characters long, and that is
    the exact floor a recorded sha has to clear. So it read as a sha that names another
    commit, rather than as an absent answer.

    A caller does one of two things with an empty answer. It writes the line anyway,
    because a run with no readable commit still happened. Or it reads the record as not
    green, because nothing ties a run to this commit. Neither one guesses.
    """
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "--quiet", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""
