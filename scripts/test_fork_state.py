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


class EvalPlanTestCase(unittest.TestCase):
    """Two bootstrapped forks, one of them hook-loaded, and a consuming repo.

    Same style again: real git repos and real config files in a temp directory,
    `--gh-fixture` standing in for the `gh` reads so fork discovery works without
    a network. The eval plan is derived from the sync plan and spends nothing, so
    every assertion here is about what the plan *says* the judgment half may
    spend — no worker is launched and no worktree is cut.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        self.forks_dir = self.root / "forks"
        self.repo = self.root / "consumer"

        # --- mattpocock's shape: skills invoked by name, no hooks manifest.
        self.matt_upstream = self.make_upstream(
            "matt-upstream",
            ["code-review", "tdd", "wayfinder"],
            manifest={"name": "mattpocock-skills", "version": "1.2.0"},
        )
        self.matt = self.make_clone("mattpocock", self.matt_upstream)

        # --- ponytail's shape: the manifest declares a hooks file, so the skill
        #     reaches a session through SessionStart rather than invocation.
        self.pony_upstream = self.make_upstream(
            "pony-upstream",
            ["ponytail"],
            manifest={"name": "ponytail", "hooks": "./hooks/claude-codex-hooks.json"},
        )
        self.pony = self.make_clone("ponytail", self.pony_upstream)

        # --- The consuming repo references code-review, tdd and ponytail.
        write(
            self.repo / "docs" / "agents" / "orchestrator.md",
            "Workers use `code-review` and `tdd`; `ponytail` keeps them lazy.\n",
        )
        # An eval set already committed from an earlier sync, so "extend rather
        # than rewrite" has something to extend.
        write(
            self.repo / "evals" / "mattpocock" / "code-review.json",
            json.dumps(
                {
                    "skill_name": "code-review",
                    "fork": "mattpocock",
                    "assertions": [
                        {
                            "name": "names-both-axes",
                            "assert": "the review output has a Standards section "
                            "and a Spec section",
                            "check": "both headings present in the transcript",
                            "first_seen_candidate": "aaaaaaa",
                        }
                    ],
                }
            ),
        )

        self.write_config()

    # --- fixture helpers ----------------------------------------------------

    def make_upstream(self, name, skills, manifest):
        upstream = self.root / name
        upstream.mkdir()
        git(upstream, "init", "-q", "-b", "main")
        write(upstream / "README.md", f"# {name}\n")
        write(upstream / ".claude-plugin" / "plugin.json", json.dumps(manifest))
        for skill in skills:
            write(upstream / "skills" / skill / "SKILL.md", f"{skill}: base body\n")
        git(upstream, "add", "-A")
        git(upstream, "commit", "-qm", "base")
        return upstream

    def make_clone(self, name, upstream):
        clone = self.forks_dir / name
        clone.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "-q", str(upstream), str(clone)],
            check=True,
            capture_output=True,
            env=GIT_ENV,
        )
        git(clone, "remote", "add", "upstream", str(upstream))
        git(clone, "fetch", "-q", "upstream")
        return clone

    def write_config(self):
        """Marketplaces plus the `gh` fixture, both naming forks with a parent."""
        self.marketplaces = self.root / "known_marketplaces.json"
        self.marketplaces.write_text(
            json.dumps(
                {
                    "mattpocock": {"source": {"source": "github", "repo": "me/skills"}},
                    "ponytail": {"source": {"source": "github", "repo": "me/ponytail"}},
                }
            )
        )
        self.gh_fixture = self.root / "gh.json"
        self.gh_fixture.write_text(
            json.dumps(
                {
                    "user": "me",
                    "repos": {
                        "me/skills": {"exists": True, "parent": "mattpocock/skills"},
                        "me/ponytail": {
                            "exists": True,
                            "parent": "DietrichGebert/ponytail",
                        },
                    },
                }
            )
        )

    def change(self, upstream, clone, *skills):
        """Advance one upstream past its pin by editing the named skills."""
        for skill in skills:
            write(upstream / "skills" / skill / "SKILL.md", f"{skill}: changed\n")
        git(upstream, "add", "-A")
        git(upstream, "commit", "-qm", f"change {' '.join(skills)}")
        git(clone, "fetch", "-q", "upstream")

    def evals(self, *extra, expect=0):
        """Run the seam with --evals and return the parsed eval plan."""
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.fork_state",
                "--evals",
                "--repo",
                str(self.repo),
                "--marketplaces",
                str(self.marketplaces),
                "--forks-dir",
                str(self.forks_dir),
                "--gh-fixture",
                str(self.gh_fixture),
                *extra,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=GIT_ENV,
        )
        self.assertEqual(proc.returncode, expect, f"stderr: {proc.stderr}")
        return (json.loads(proc.stdout) if proc.stdout else {}), proc.stderr

    def fork(self, plan, name):
        for entry in plan["forks"]:
            if entry["fork"] == name:
                return entry
        self.fail(f"{name} missing: {[f['fork'] for f in plan['forks']]}")

    def one_eval(self, fork_entry, skill):
        for entry in fork_entry["evals"]:
            if entry["skill"] == skill:
                return entry
        self.fail(f"{skill} not planned: {[e['skill'] for e in fork_entry['evals']]}")

    # --- the cases ----------------------------------------------------------

    def test_consumed_delta_plans_a_worktree_pair_at_candidate_and_pin(self):
        """AC 1 + AC 4: the delta is reported, a candidate worktree is planned,
        and every eval is candidate-versus-pinned rather than versus no skill."""
        self.change(self.matt_upstream, self.matt, "code-review")
        plan, _ = self.evals()
        fork = self.fork(plan, "mattpocock")

        self.assertFalse(fork["up_to_date"])
        self.assertNotEqual(fork["pinned_sha"], fork["candidate_sha"])
        self.assertEqual(fork["verdict"], "needs evaluation")

        item = self.one_eval(fork, "code-review")
        self.assertEqual(item["changed_paths"], ["skills/code-review/SKILL.md"])
        # The committed eval set names the skill too, so a skill that has ever
        # been evaluated stays consumed even if every doc reference goes away.
        # That is grep over-testing in the direction ADR 0008 chose.
        self.assertEqual(
            item["referenced_by"],
            ["docs/agents/orchestrator.md", "evals/mattpocock/code-review.json"],
        )
        self.assertEqual(item["runs"], 2)

        candidate = item["worktrees"]["candidate"]
        pinned = item["worktrees"]["pinned"]
        self.assertEqual(candidate["ref"], fork["candidate_sha"])
        self.assertEqual(pinned["ref"], fork["pinned_sha"])
        self.assertNotEqual(candidate["path"], pinned["path"])
        # The worker is handed a skill directory inside the worktree — path
        # injection, not an install.
        self.assertTrue(
            candidate["skill_dir"].endswith("skills/code-review"),
            candidate["skill_dir"],
        )
        self.assertIn("not no-skill", pinned["why"])
        self.assertIn("upstream regressed", pinned["why"])
        self.assertEqual(plan["candidate_loaded_by"].split(" into ")[0], "path injection")

    def test_unconsumed_delta_is_promotable_with_zero_runs(self):
        """AC 2: a delta touching nothing consumed spends nothing."""
        self.change(self.matt_upstream, self.matt, "wayfinder")
        plan, _ = self.evals("--fork", "mattpocock")
        fork = self.fork(plan, "mattpocock")

        self.assertFalse(fork["up_to_date"])
        self.assertEqual(fork["evals"], [])
        self.assertEqual(fork["runs_planned"], 0)
        self.assertEqual(fork["verdict"], "promotable")
        self.assertIn("zero eval runs", fork["verdict_reason"])
        self.assertEqual(plan["budget"]["runs_planned"], 0)
        self.assertEqual(plan["budget"]["spent_on"], [])
        self.assertEqual(
            [u["skill"] for u in plan["budget"]["uncovered"]], ["wayfinder"]
        )
        self.assertEqual(plan["budget"]["uncovered"][0]["cost"], 0)

    def test_no_planned_path_falls_inside_the_plugin_directory(self):
        """AC 3 + AC 10: the plan cannot name a path the plugin system owns, and
        a plan that would is refused rather than emitted."""
        self.change(self.matt_upstream, self.matt, "code-review")
        plan, _ = self.evals()
        item = self.one_eval(self.fork(plan, "mattpocock"), "code-review")

        plugin_root = Path(plan["plugin_root_untouched"])
        self.assertEqual(plugin_root, Path.home() / ".claude/plugins")
        for path in (
            item["worktrees"]["candidate"]["path"],
            item["worktrees"]["pinned"]["path"],
            item["results_dir"],
            *item["transcripts"].values(),
        ):
            self.assertNotIn(str(plugin_root), path)

        # The guard is what makes that a guarantee: aim the plugin root at the
        # tree the worktrees would live in and no plan is emitted at all.
        out, stderr = self.evals("--plugin-root", str(self.forks_dir), expect=2)
        self.assertEqual(out, {})
        self.assertIn("inside the plugin system's directory", stderr)

        # The same guard covers a path the configured tool chose rather than one
        # this script planned, which is the case `--check-path` exists for.
        self.assertEqual(
            self.check_path(str(self.forks_dir / "candidate"))["outside_plugin_root"],
            True,
        )
        self.assertIn(
            "inside the plugin system's directory",
            self.check_path(
                str(plugin_root / "marketplaces/mattpocock"), expect=2
            )["stderr"],
        )

    def check_path(self, path, expect=0):
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.fork_state",
                "--check-path",
                path,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=GIT_ENV,
        )
        self.assertEqual(proc.returncode, expect, f"stderr: {proc.stderr}")
        if expect:
            return {"stderr": proc.stderr}
        return json.loads(proc.stdout)

    def test_assertions_are_named_and_the_eval_set_is_per_fork_per_skill(self):
        """AC 5 + AC 8: each assertion carries a name, and the committed set the
        sync extends is keyed by fork and by skill."""
        self.change(self.matt_upstream, self.matt, "code-review")
        plan, _ = self.evals("--fork", "mattpocock")
        item = self.one_eval(self.fork(plan, "mattpocock"), "code-review")

        self.assertEqual(item["eval_set"]["path"], "evals/mattpocock/code-review.json")
        self.assertTrue(item["eval_set"]["exists"])
        self.assertEqual(item["eval_set"]["action"], "extend")
        self.assertTrue(item["eval_set"]["committed"])
        self.assertEqual(item["eval_set"]["assertion_names"], ["names-both-axes"])
        self.assertNotIn(None, item["eval_set"]["assertion_names"])
        # Transcripts sit under .orchestrator/, which .gitignore already covers.
        for path in item["transcripts"].values():
            self.assertIn(".orchestrator/fork-sync/", path)

    def test_eval_set_is_extended_not_rewritten(self):
        """AC 8: a later sync appends assertions and keeps the old ones verbatim,
        including one whose name is redrafted against."""
        incoming = self.root / "new.json"
        incoming.write_text(
            json.dumps(
                [
                    {"name": "names-both-axes", "assert": "a redraft under an old name"},
                    {"name": "reports-no-findings-explicitly", "assert": "says none"},
                ]
            )
        )
        before = (self.repo / "evals" / "mattpocock" / "code-review.json").read_text()

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.fork_state",
                "--merge-eval-set",
                "--repo",
                str(self.repo),
                "--fork",
                "mattpocock",
                "--skill",
                "code-review",
                "--new-assertions",
                str(incoming),
                "--first-seen",
                "bbbbbbb",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=GIT_ENV,
        )
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        merged = json.loads(proc.stdout)

        self.assertEqual(merged["kept"], ["names-both-axes"])
        self.assertEqual(merged["added"], ["reports-no-findings-explicitly"])
        self.assertEqual(merged["unchanged_kept_as_is"], ["names-both-axes"])
        self.assertEqual(merged["total_assertions"], 2)
        assertions = merged["eval_set"]["assertions"]
        # The old assertion keeps its text and its provenance — a redraft under
        # the same name would break comparability with every earlier sync.
        self.assertEqual(assertions[0]["assert"].split(" has ")[0], "the review output")
        self.assertEqual(assertions[0]["first_seen_candidate"], "aaaaaaa")
        self.assertEqual(assertions[1]["first_seen_candidate"], "bbbbbbb")
        # And nothing was written: the caller writes, the seam only computes.
        self.assertEqual(
            before, (self.repo / "evals" / "mattpocock" / "code-review.json").read_text()
        )

    def test_budget_accounting_names_the_spend_and_what_is_uncovered(self):
        """AC 6: the plan never plans past 5 runs and says where they went."""
        write(self.repo / "docs" / "agents" / "extra.md", "Also: `wayfinder`.\n")
        self.change(self.matt_upstream, self.matt, "code-review", "tdd", "wayfinder")
        self.change(self.pony_upstream, self.pony, "ponytail")
        plan, _ = self.evals()

        budget = plan["budget"]
        self.assertEqual(budget["ceiling"], 5)
        self.assertLessEqual(budget["runs_planned"], 5)
        self.assertEqual(budget["runs_planned"], 4)
        self.assertEqual(budget["remaining"], 1)
        self.assertEqual(
            [(s["fork"], s["skill"], s["runs"]) for s in budget["spent_on"]],
            [("mattpocock", "code-review", 2), ("mattpocock", "tdd", 2)],
        )
        for spend in budget["spent_on"]:
            self.assertEqual(spend["split"], "1 candidate + 1 pinned baseline")
        self.assertEqual(
            budget["runs_planned"],
            sum(f["runs_planned"] for f in plan["forks"]),
        )

        # Everything the ceiling pushed out is named, with its reason.
        uncovered = {(u["fork"], u["skill"]): u["reason"] for u in budget["uncovered"]}
        self.assertIn(("mattpocock", "wayfinder"), uncovered)
        self.assertIn(("ponytail", "ponytail"), uncovered)
        self.assertIn("run budget exhausted", uncovered[("ponytail", "ponytail")])
        self.assertEqual(self.fork(plan, "ponytail")["runs_planned"], 0)

    def test_a_hook_loaded_plugin_asserts_on_body_content(self):
        """AC 11: path injection cannot exercise a SessionStart hook, so the
        plan says the assertions target the skill body's content instead."""
        self.change(self.pony_upstream, self.pony, "ponytail")
        pony = self.fork(self.evals("--fork", "ponytail")[0], "ponytail")
        matt_plan, _ = self.evals("--fork", "mattpocock")

        self.assertTrue(pony["loads_via_hook"])
        item = self.one_eval(pony, "ponytail")
        self.assertIn("skill body content", item["assertion_target"])
        self.assertIn("session hook", item["assertion_target"])
        # The distinction is real, not blanket: mattpocock has no hooks manifest.
        self.change(self.matt_upstream, self.matt, "code-review")
        matt_plan, _ = self.evals("--fork", "mattpocock")
        matt = self.fork(matt_plan, "mattpocock")
        self.assertFalse(matt["loads_via_hook"])
        self.assertEqual(
            self.one_eval(matt, "code-review")["assertion_target"],
            "runtime behaviour under path injection",
        )

    def test_the_plan_promotes_nothing_and_rejecting_is_a_worktree_removal(self):
        """AC 7 + AC 12: the plan is advisory, and it says what a reject costs."""
        self.change(self.matt_upstream, self.matt, "code-review")
        before = sorted(str(p) for p in self.root.rglob("*"))
        plan, _ = self.evals()

        self.assertEqual(plan["mutates"], "nothing")
        self.assertIn("the maintainer decides", plan["promotes"])
        self.assertIn("remove the candidate worktree", plan["rejecting_a_candidate"])
        self.assertIn("no rollback", plan["rejecting_a_candidate"])
        # Planning cut no worktree and touched nothing on disk.
        self.assertEqual(before, sorted(str(p) for p in self.root.rglob("*")))

    def test_a_fork_with_no_clone_reports_cleanly_and_spends_nothing(self):
        """Bootstrap has never been run for real, so this is today's live case."""
        import shutil

        shutil.rmtree(self.pony)
        plan, _ = self.evals(expect=1)
        pony = self.fork(plan, "ponytail")

        self.assertFalse(pony["bootstrapped"])
        self.assertIn("run /skill-fork-sync bootstrap", pony["error"])
        self.assertEqual(pony["verdict"], "cannot evaluate")
        self.assertEqual(pony["runs_planned"], 0)
        self.assertEqual(plan["budget"]["runs_planned"], 0)
        # The other fork is still planned — one missing clone is not a blocker.
        self.assertTrue(self.fork(plan, "mattpocock")["bootstrapped"])

    def test_it_runs_for_one_named_fork_or_for_all_of_them(self):
        """AC 13."""
        self.change(self.matt_upstream, self.matt, "code-review")
        self.change(self.pony_upstream, self.pony, "ponytail")

        every, _ = self.evals()
        self.assertEqual([f["fork"] for f in every["forks"]], ["mattpocock", "ponytail"])
        self.assertEqual(every["budget"]["runs_planned"], 4)

        one, _ = self.evals("--fork", "ponytail")
        self.assertEqual([f["fork"] for f in one["forks"]], ["ponytail"])
        self.assertEqual(one["budget"]["runs_planned"], 2)
        # A named fork gets the whole ceiling, not a per-fork share of it.
        self.assertEqual(one["budget"]["remaining"], 3)


if __name__ == "__main__":
    unittest.main()
