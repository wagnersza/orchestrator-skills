#!/usr/bin/env python3
"""Behaviour tests for the seam: fixture state in, JSON plan out.

Every case runs `python3 -m scripts.fork_state` as a subprocess against local git
repos and config files built in a temp directory, and asserts on the emitted
**Sync plan** or **bootstrap plan** — never on a helper's return value. No
network, no GitHub, no agent runs: sync bypasses fork discovery with `--clone`,
and bootstrap stands the two `gh` reads up with `--gh-fixture`, so `gh` is never
called either way.

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


class BootstrapPlanTestCase(unittest.TestCase):
    """A declared dependency still pointing at upstream, and its installed SHA.

    Same fixture style as above: a real upstream git repo, plus the two Claude
    Code config files and a `requirements.md` written into a temp directory. The
    `gh` reads come from `--gh-fixture`, so nothing here touches the network.
    """

    INSTALLED_SHA_KEY = "gitCommitSha"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        # --- Upstream: two commits, so the installed SHA is not upstream's head.
        self.upstream = self.root / "upstream"
        self.upstream.mkdir()
        git(self.upstream, "init", "-q", "-b", "main")
        write(self.upstream / "skills" / "tdd" / "SKILL.md", "base body\n")
        git(self.upstream, "add", "-A")
        git(self.upstream, "commit", "-qm", "the installed version")
        self.installed_sha = rev(self.upstream, "main")
        write(self.upstream / "skills" / "tdd" / "SKILL.md", "upstream moved on\n")
        git(self.upstream, "add", "-A")
        git(self.upstream, "commit", "-qm", "four commits nobody evaluated")
        self.upstream_head = rev(self.upstream, "main")

        self.forks_dir = self.root / "forks"
        self.repo = self.root / "consumer"
        self.clone = self.forks_dir / "mattpocock"

        # --- The consuming repo declares mattpocock-skills and ponytail, and
        #     prompt-improver, which is already the maintainer's own repo.
        write(
            self.repo / "orchestrator" / "references" / "requirements.md",
            "| **mattpocock-skills** | `mattpocock-skills@mattpocock` |\n"
            "| **ponytail** | `ponytail@ponytail` |\n"
            "| **prompt-improver** | `prompt-improver@prompt-improver` |\n",
        )

        self.write_config()
        self.write_gh_fixture()

    # --- fixture helpers ----------------------------------------------------

    def write_config(self, mattpocock_repo="mattpocock/skills", installed=True):
        """`known_marketplaces.json` + `installed_plugins.json` in the real shape."""
        self.marketplaces = self.root / "known_marketplaces.json"
        self.marketplaces.write_text(
            json.dumps(
                {
                    # Declared, still upstream's: a fork target.
                    "mattpocock": {"source": {"source": "github", "repo": mattpocock_repo}},
                    # Declared, already the maintainer's own repo: not a target.
                    "prompt-improver": {
                        "source": {"source": "github", "repo": "me/prompt-improver"}
                    },
                    # Installed but never declared in requirements.md: not a target.
                    "caveman": {
                        "source": {"source": "github", "repo": "JuliusBrussee/caveman"}
                    },
                }
            )
        )

        entry = {
            "scope": "user",
            "version": "1.2.0",
            "lastUpdated": "2026-07-21T13:27:28.622Z",
        }
        if installed:
            entry[self.INSTALLED_SHA_KEY] = self.installed_sha
        self.installed = self.root / "installed_plugins.json"
        self.installed.write_text(
            json.dumps({"version": 2, "plugins": {"mattpocock-skills@mattpocock": [entry]}})
        )

    def write_gh_fixture(self, fork_exists=False):
        """Stand in for `gh api user` and `gh repo view --json parent`."""
        self.gh_fixture = self.root / "gh.json"
        repos = {
            "mattpocock/skills": {"exists": True, "parent": None},
            "me/prompt-improver": {"exists": True, "parent": None},
            "JuliusBrussee/caveman": {"exists": True, "parent": None},
        }
        if fork_exists:
            repos["me/skills"] = {"exists": True, "parent": "mattpocock/skills"}
        self.gh_fixture.write_text(json.dumps({"user": "me", "repos": repos}))

    def bootstrap(self, *extra, expect=0):
        """Run the dry run and return (parsed JSON plan, rendered text)."""
        base = [
            sys.executable,
            "-m",
            "scripts.fork_state",
            "--bootstrap",
            "--repo",
            str(self.repo),
            "--marketplaces",
            str(self.marketplaces),
            "--installed",
            str(self.installed),
            "--forks-dir",
            str(self.forks_dir),
            "--gh-fixture",
            str(self.gh_fixture),
            "--today",
            "2026-07-31",
        ]

        def run(*args):
            proc = subprocess.run(
                [*base, *args],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                env=GIT_ENV,
            )
            self.assertEqual(proc.returncode, expect, f"stderr: {proc.stderr}")
            return proc.stdout

        return json.loads(run("--json", *extra)), run(*extra)

    def target(self, plan, name="mattpocock"):
        for entry in plan["targets"]:
            if entry["fork"] == name:
                return entry
        self.fail(f"{name} missing: {[t['fork'] for t in plan['targets']]}")

    def step(self, target, name):
        for entry in target["steps"]:
            if entry["name"] == name:
                return entry
        self.fail(f"step {name} missing: {[s['name'] for s in target['steps']]}")

    def bootstrap_the_fork(self, fork_md=True):
        """Do to a fixture clone what a real bootstrap would do, so a re-run is
        planned against an already-bootstrapped fork."""
        self.write_gh_fixture(fork_exists=True)
        self.clone.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "-q", str(self.upstream), str(self.clone)],
            check=True,
            capture_output=True,
            env=GIT_ENV,
        )
        git(
            self.clone,
            "remote",
            "add",
            "upstream",
            "https://github.com/mattpocock/skills.git",
        )
        git(self.clone, "reset", "-q", "--hard", self.installed_sha)
        if fork_md:
            write(self.clone / "FORK.md", "# Fork of mattpocock/skills\n")
            git(self.clone, "add", "FORK.md")
            git(self.clone, "commit", "-qm", "Record the fork and its pin")
        self.write_config(mattpocock_repo="me/skills")

    # --- the cases ----------------------------------------------------------

    def test_fork_targets_are_declared_deps_still_pointing_at_upstream(self):
        plan, text = self.bootstrap()

        # `mattpocock` is declared and still upstream's, so it is the only target:
        # `prompt-improver` is already the user's own repo and `caveman` is
        # installed but never declared in requirements.md.
        self.assertEqual([t["fork"] for t in plan["targets"]], ["mattpocock"])
        target = self.target(plan)
        self.assertEqual(target["upstream"], "mattpocock/skills")
        self.assertEqual(target["fork_repo"], "me/skills")
        self.assertEqual(target["marketplace_source_now"], "mattpocock/skills")
        self.assertEqual(target["clone"], str(self.clone))
        self.assertFalse(target["already_bootstrapped"])
        self.assertIn("prompt-improver", self.marketplaces.read_text())
        self.assertNotIn("prompt-improver", text)
        self.assertNotIn("caveman", text)

    def test_pin_is_the_installed_sha_not_upstream_head(self):
        plan, text = self.bootstrap()
        target = self.target(plan)

        self.assertEqual(target["installed_sha"], self.installed_sha)
        self.assertEqual(target["plugin_id"], "mattpocock-skills@mattpocock")
        self.assertEqual(target["installed_version"], "1.2.0")
        self.assertNotEqual(target["installed_sha"], self.upstream_head)
        self.assertIn("gitCommitSha", plan["pin_source"])
        self.assertIn(self.installed_sha, self.step(target, "pin")["command"])
        self.assertNotIn(self.upstream_head, text)

    def test_dry_run_prints_all_six_actions_and_takes_none(self):
        before = sorted(str(p) for p in self.root.rglob("*"))
        plan, text = self.bootstrap()
        target = self.target(plan)

        self.assertEqual(
            [s["name"] for s in target["steps"]],
            ["fork", "clone", "remote", "pin", "FORK.md", "marketplace swap"],
        )
        self.assertEqual([s["step"] for s in target["steps"]], [1, 2, 3, 4, 5, 6])
        self.assertIn("gh repo fork mattpocock/skills", text)
        self.assertIn(f"git clone https://github.com/me/skills.git {self.clone}", text)
        self.assertIn("remote add upstream", text)
        self.assertIn(f"reset --hard {self.installed_sha}", text)
        self.assertIn("FORK.md", text)
        self.assertIn(
            "claude plugin marketplace remove mattpocock && "
            "claude plugin marketplace add me/skills",
            text,
        )
        self.assertIn("DRY RUN", text)

        # Took none of them: no fork clone appeared, no config file was rewritten,
        # and the marketplace registration still names upstream.
        self.assertEqual(plan["mutates"], "nothing")
        self.assertFalse(self.forks_dir.exists())
        self.assertEqual(before, sorted(str(p) for p in self.root.rglob("*")))
        self.assertIn("mattpocock/skills", self.marketplaces.read_text())

    def test_fork_md_records_the_five_fields(self):
        plan, text = self.bootstrap()
        body = self.target(plan)["fork_md"]

        self.assertIn("https://github.com/mattpocock/skills", body)  # upstream repo
        self.assertIn("**Fork date:** 2026-07-31", body)  # fork date
        self.assertIn(f"`{self.installed_sha}`", body)  # last-synced SHA
        self.assertIn("**Why this fork exists:**", body)  # why
        self.assertIn("**Local changes:** none", body)  # local changes
        self.assertIn("read live from git", body)
        self.assertIn(body.splitlines()[0], text)

    def test_rerun_against_a_bootstrapped_fork_is_a_no_op_per_step(self):
        self.bootstrap_the_fork()
        plan, text = self.bootstrap()
        target = self.target(plan)

        self.assertEqual([s["status"] for s in target["steps"]], ["done"] * 6)
        self.assertTrue(target["already_bootstrapped"])
        self.assertIn("already bootstrapped", text)
        # FORK.md sits one commit ahead of the pin, and that must still read as
        # pinned — otherwise a re-run would reset the record away.
        self.assertNotEqual(rev(self.clone, "main"), self.installed_sha)
        self.assertIn("already pinned", self.step(target, "pin")["note"])

    def test_a_moved_default_branch_is_not_reported_as_pinned(self):
        self.bootstrap_the_fork()
        write(self.clone / "skills" / "tdd" / "SKILL.md", "someone promoted this\n")
        git(self.clone, "add", "-A")
        git(self.clone, "commit", "-qm", "a change that is not FORK.md")

        plan, _ = self.bootstrap()
        self.assertEqual(self.step(self.target(plan), "pin")["status"], "todo")
        self.assertFalse(self.target(plan)["already_bootstrapped"])

    def test_a_plugin_with_no_installed_sha_blocks_the_pin(self):
        self.write_config(installed=False)
        plan, _ = self.bootstrap()
        target = self.target(plan)

        self.assertIsNone(target["installed_sha"])
        self.assertIn("nothing to pin to", target["pin_error"])
        self.assertEqual(self.step(target, "pin")["status"], "blocked")
        self.assertEqual(self.step(target, "marketplace swap")["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
