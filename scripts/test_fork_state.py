#!/usr/bin/env python3
"""Behaviour tests for the sync-plan seam: fixture repo state in, JSON plan out.

Every case runs `python3 -m scripts.fork_state` as a subprocess against local
git repos built in a temp directory and asserts on the emitted **Sync plan** —
never on a helper's return value. No network, no GitHub, no agent runs: fork
discovery is bypassed with `--clone`, so `gh` is never called.

    python3 -m pytest scripts/ -q
    python3 -m unittest discover -s scripts -t . -q     # fallback, no pytest
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.com",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}

CONSUMED = ["code-review", "tdd"]
UNCONSUMED = ["wayfinder", "to-questionnaire"]


def git(cwd, *args):
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        env=GIT_ENV,
    )


def rev(cwd, ref):
    return subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", ref],
        check=True,
        capture_output=True,
        text=True,
        env=GIT_ENV,
    ).stdout.strip()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class SyncPlanTestCase(unittest.TestCase):
    """One upstream repo, one fork clone pinned to its base, one consuming repo."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        # --- Upstream: a skills repo in the mattpocock shape.
        self.upstream = root / "upstream"
        self.upstream.mkdir()
        git(self.upstream, "init", "-q", "-b", "main")
        write(self.upstream / "README.md", "# upstream\n")
        for skill in CONSUMED + UNCONSUMED:
            write(
                self.upstream / "skills" / skill / "SKILL.md",
                f"---\nname: {skill}\ndescription: fixture\n---\n\nbase body\n",
            )
        git(self.upstream, "add", "-A")
        git(self.upstream, "commit", "-qm", "base")

        # --- Fork clone: `main` is the pin, `upstream` is the delta source.
        self.clone = root / "mattpocock"
        subprocess.run(
            ["git", "clone", "-q", str(self.upstream), str(self.clone)],
            check=True,
            capture_output=True,
            env=GIT_ENV,
        )
        git(self.clone, "remote", "add", "upstream", str(self.upstream))
        git(self.clone, "fetch", "-q", "upstream")

        # --- The consuming repo: references CONSUMED, never UNCONSUMED.
        self.repo = root / "consumer"
        write(
            self.repo / "docs" / "agents" / "orchestrator.md",
            "Workers use `code-review` for review and `tdd` for new logic.\n",
        )

    # --- fixture helpers ----------------------------------------------------

    def push_upstream_change(self, *skills, files=("SKILL.md",)):
        """Advance upstream past the pin by editing the named skills."""
        for skill in skills:
            for name in files:
                write(
                    self.upstream / "skills" / skill / name,
                    f"changed {skill}/{name}\n",
                )
        git(self.upstream, "add", "-A")
        git(self.upstream, "commit", "-qm", f"change {' '.join(skills)}")
        git(self.clone, "fetch", "-q", "upstream")

    def plan(self, *extra):
        """Run the seam and return the parsed Sync plan."""
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.fork_state",
                "--clone",
                str(self.clone),
                "--upstream-repo",
                "fixture/upstream",
                "--repo",
                str(self.repo),
                *extra,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=GIT_ENV,
        )
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        plan = json.loads(proc.stdout)
        return plan, plan["forks"][0]

    def skill(self, fork, name):
        for entry in fork["skills"]:
            if entry["skill"] == name:
                return entry
        self.fail(f"{name} missing from plan: {[s['skill'] for s in fork['skills']]}")

    # --- the six cases ------------------------------------------------------

    def test_no_delta_reports_up_to_date_and_zero_runs(self):
        plan, fork = self.plan()

        self.assertTrue(fork["up_to_date"])
        self.assertEqual(fork["pinned_sha"], fork["candidate_sha"])
        self.assertEqual(fork["changed_paths"], [])
        self.assertEqual(fork["skills"], [])
        self.assertEqual(fork["allocated_runs"], 0)
        self.assertEqual(plan["run_budget"]["allocated"], 0)
        self.assertEqual(plan["run_budget"]["dropped_for_budget"], [])

    def test_unconsumed_delta_allocates_zero_runs(self):
        self.push_upstream_change(*UNCONSUMED)
        plan, fork = self.plan()

        self.assertFalse(fork["up_to_date"])
        self.assertEqual(fork["consumed"], [])
        self.assertEqual(
            [s["skill"] for s in fork["skipped"]], sorted(UNCONSUMED)
        )
        for entry in fork["skipped"]:
            self.assertEqual(entry["reason"], "not referenced by this repo")
        self.assertEqual(fork["allocated_runs"], 0)
        self.assertEqual(plan["run_budget"]["allocated"], 0)

    def test_consumed_delta_is_listed_for_eval(self):
        self.push_upstream_change("code-review")
        plan, fork = self.plan()

        self.assertEqual(fork["consumed"], ["code-review"])
        self.assertEqual(fork["skipped"], [])
        entry = self.skill(fork, "code-review")
        self.assertTrue(entry["consumed"])
        self.assertEqual(entry["path"], "skills/code-review")
        self.assertEqual(entry["changed_paths"], ["skills/code-review/SKILL.md"])
        self.assertEqual(entry["runs"], 2)
        self.assertEqual(
            entry["referenced_by"], ["docs/agents/orchestrator.md"]
        )
        self.assertEqual(fork["allocated_runs"], 2)
        self.assertEqual(plan["run_budget"]["allocated"], 2)
        self.assertEqual(plan["run_budget"]["tiebreak_reserve"], 3)

    def test_mixed_delta_splits_consumed_and_skipped(self):
        self.push_upstream_change("code-review", "wayfinder")
        plan, fork = self.plan()

        self.assertEqual(fork["consumed"], ["code-review"])
        self.assertEqual([s["skill"] for s in fork["skipped"]], ["wayfinder"])
        self.assertEqual(self.skill(fork, "code-review")["runs"], 2)
        self.assertEqual(self.skill(fork, "wayfinder")["runs"], 0)
        self.assertEqual(fork["allocated_runs"], 2)
        self.assertEqual(plan["run_budget"]["dropped_for_budget"], [])

    def test_budget_ceiling_never_exceeds_five_and_names_drops(self):
        # Three consumed skills at two runs each wants 6 — one run over.
        write(
            self.repo / "docs" / "agents" / "extra.md",
            "Also consumed: `wayfinder`.\n",
        )
        self.push_upstream_change("code-review", "tdd", "wayfinder")
        plan, fork = self.plan()

        budget = plan["run_budget"]
        self.assertEqual(budget["ceiling"], 5)
        self.assertLessEqual(budget["allocated"], 5)
        self.assertEqual(budget["allocated"], 4)
        self.assertEqual(len(fork["consumed"]), 3)

        dropped = [d["skill"] for d in budget["dropped_for_budget"]]
        self.assertEqual(dropped, ["wayfinder"])
        self.assertEqual(dropped, [d["skill"] for d in fork["dropped_for_budget"]])
        self.assertEqual(
            budget["dropped_for_budget"][0]["reason"],
            "run budget exhausted (5 runs per sync)",
        )
        self.assertTrue(self.skill(fork, "wayfinder")["dropped_for_budget"])
        self.assertEqual(self.skill(fork, "wayfinder")["runs"], 0)
        self.assertEqual(
            sum(s["runs"] for s in fork["skills"]), budget["allocated"]
        )

    def test_pinned_sha_comes_from_git_not_fork_md(self):
        self.push_upstream_change("code-review")
        bogus = "0" * 40
        write(
            self.clone / "FORK.md",
            f"# Fork\n\nupstream: fixture/upstream\nlast-synced SHA: {bogus}\n",
        )
        git(self.clone, "add", "FORK.md")
        git(self.clone, "commit", "-qm", "record a deliberately wrong SHA")

        expected_pinned = rev(self.clone, "main")
        expected_candidate = rev(self.clone, "upstream/main")
        plan, fork = self.plan()

        self.assertEqual(fork["pinned_sha"], expected_pinned)
        self.assertNotEqual(fork["pinned_sha"], bogus)
        self.assertEqual(fork["candidate_sha"], expected_candidate)
        # FORK.md is in the pin but not in the candidate, so the diff shows it
        # as a deletion — it maps to no skill and spends nothing.
        self.assertIn("FORK.md", fork["unmapped_paths"])
        self.assertEqual(fork["consumed"], ["code-review"])
        del plan

    # --- AC 11: the seam mutates nothing -----------------------------------

    def test_script_mutates_nothing(self):
        self.push_upstream_change("code-review", "wayfinder")
        before = (
            rev(self.clone, "main"),
            rev(self.clone, "upstream/main"),
            sorted(p.name for p in self.clone.iterdir()),
            sorted(p.name for p in self.repo.rglob("*")),
        )

        self.plan()

        self.assertEqual(
            before,
            (
                rev(self.clone, "main"),
                rev(self.clone, "upstream/main"),
                sorted(p.name for p in self.clone.iterdir()),
                sorted(p.name for p in self.repo.rglob("*")),
            ),
        )
        status = subprocess.run(
            ["git", "-C", str(self.clone), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
            env=GIT_ENV,
        ).stdout
        self.assertEqual(status, "")


if __name__ == "__main__":
    unittest.main()
