import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import killhouse_conduct as conduct  # noqa: E402
import killhouse_delegation_log as dl  # noqa: E402

PINNED_TEST = (
    "import unittest\n"
    "from slug import slugify\n\n\n"
    "class T(unittest.TestCase):\n"
    "    def test_basic(self):\n"
    "        self.assertEqual(slugify('Hello World'), 'hello-world')\n\n\n"
    "if __name__ == '__main__':\n"
    "    unittest.main()\n"
)

GOOD_IMPL = "import re\n\n\ndef slugify(s):\n    return re.sub(r'\\s+', '-', s.strip().lower())\n"
BAD_IMPL = "def slugify(s):\n    return s\n"


def _pinned_head(record):
    return next(
        a["pinned"]["head"] for a in record["upstream_artifacts"] if a.get("kind") == "repository_state"
    )


@contextmanager
def temp_git_repo():
    """A small standalone git repo with a branch, for exercising run_delegation end-to-end."""
    d = Path(tempfile.mkdtemp(prefix="kh-conduct-source-"))
    try:
        subprocess.run(["git", "init", "-q", "-b", "main", str(d)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(d), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(d), "config", "user.name", "Test"], check=True)
        (d / "README.md").write_text("hello\n")
        subprocess.run(["git", "-C", str(d), "add", "README.md"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(d), "commit", "-q", "-m", "initial"], check=True, capture_output=True
        )
        yield d
    finally:
        git_dir = d / ".git"
        if git_dir.is_dir():
            os.chmod(git_dir, 0o755)
        shutil.rmtree(d, ignore_errors=True)


def make_delegation():
    return {
        "delegation_id": "run-test.slugify.implementer",
        "plan_position": "phase-1/milestone-1/slice-1",
        "depends_on": [],
        "resolved_prompt": "Implement slug.py::slugify to satisfy the pinned test.",
        "planned_tier": "fast",
        "gate": {
            "command": f"{sys.executable} -m unittest test_slug -v",
            "cwd": "REPO_ROOT",
            "pass_criteria": "exit 0",
            "baseline_polarity": "fail",
        },
        "upstream_artifacts": [
            {"kind": "repository_state", "pinned": {"head": "advisory-placeholder", "dirty_files": []}},
            {"kind": "pinned_acceptance_test", "path": "test_slug.py", "pinned_content": PINNED_TEST},
        ],
    }


class RunDelegationPassFailTests(unittest.TestCase):
    def test_pass_path(self):
        with temp_git_repo() as repo:
            with tempfile.TemporaryDirectory() as tmp:
                log_path = Path(tmp) / "delegations.jsonl"

                calls = []

                def executor(prompt, model, workdir):
                    calls.append(model)
                    (workdir / "slug.py").write_text(GOOD_IMPL)

                record, diff_text = conduct.run_delegation(
                    make_delegation(),
                    repo_root=repo,
                    target_branch="main",
                    tier="fast",
                    model="fake-fast",
                    executor=executor,
                    log_path=log_path,
                )

                self.assertEqual(record["outcome"]["status"], "pass")
                self.assertEqual(calls, ["fake-fast"])
                self.assertEqual(dl.validate_record(record), [])

                lines = log_path.read_text().splitlines()
                self.assertEqual(len(lines), 1)
                self.assertEqual(json.loads(lines[0]), record)

                self.assertIn("slug.py", diff_text)

    def test_fail_path_real_gate(self):
        with temp_git_repo() as repo:
            with tempfile.TemporaryDirectory() as tmp:
                log_path = Path(tmp) / "delegations.jsonl"

                def executor(prompt, model, workdir):
                    (workdir / "slug.py").write_text(BAD_IMPL)

                record, diff_text = conduct.run_delegation(
                    make_delegation(),
                    repo_root=repo,
                    target_branch="main",
                    tier="fast",
                    model="fake-fast",
                    executor=executor,
                    log_path=log_path,
                )

                self.assertEqual(record["outcome"]["status"], "fail")
                self.assertEqual(dl.validate_record(record), [])
                lines = log_path.read_text().splitlines()
                self.assertEqual(len(lines), 1)
                self.assertEqual(json.loads(lines[0]), record)

    def test_executor_crash_path(self):
        with temp_git_repo() as repo:
            with tempfile.TemporaryDirectory() as tmp:
                log_path = Path(tmp) / "delegations.jsonl"

                def executor(prompt, model, workdir):
                    raise subprocess.CalledProcessError(1, "boom")

                record, diff_text = conduct.run_delegation(
                    make_delegation(),
                    repo_root=repo,
                    target_branch="main",
                    tier="fast",
                    model="fake-fast",
                    executor=executor,
                    log_path=log_path,
                )

                self.assertEqual(record["outcome"]["status"], "fail")
                self.assertIn("notes", record["outcome"])
                self.assertIn("executor failed", record["outcome"]["notes"])
                lines = log_path.read_text().splitlines()
                self.assertEqual(len(lines), 1)
                self.assertEqual(json.loads(lines[0]), record)

    def test_freeze_before_execute(self):
        """The pinned head in the logged record equals the branch tip BEFORE execution."""
        with temp_git_repo() as repo:
            branch_tip_before = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "main"], capture_output=True, text=True
            ).stdout.strip()

            with tempfile.TemporaryDirectory() as tmp:
                log_path = Path(tmp) / "delegations.jsonl"

                def executor(prompt, model, workdir):
                    # Commit to main from within the sandbox's underlying repo state simulation:
                    # nothing to commit here; we just prove the frozen head matches the pre-run tip.
                    (workdir / "slug.py").write_text(GOOD_IMPL)

                record, _ = conduct.run_delegation(
                    make_delegation(),
                    repo_root=repo,
                    target_branch="main",
                    tier="fast",
                    model="fake-fast",
                    executor=executor,
                    log_path=log_path,
                )

                repo_states = [
                    a for a in record["upstream_artifacts"] if a.get("kind") == "repository_state"
                ]
                self.assertEqual(len(repo_states), 1, "plan's advisory repository_state must be replaced")
                self.assertEqual(repo_states[0]["pinned"]["head"], branch_tip_before)


class BranchSandboxTests(unittest.TestCase):
    def test_nonexistent_branch_raises_value_error(self):
        with temp_git_repo() as repo:
            with self.assertRaises(ValueError) as cm:
                with conduct.branch_sandbox(repo, "no-such-branch"):
                    pass
            self.assertIn("no-such-branch", str(cm.exception))

    def test_resolves_real_branch(self):
        with temp_git_repo() as repo:
            with conduct.branch_sandbox(repo, "main") as sandbox:
                self.assertTrue((sandbox / "README.md").is_file())


ROUTING_ALL_TIERS = {
    "model_tiers": {"fast": "fake-fast", "standard": "fake-standard", "reasoning": "fake-reasoning"}
}


def make_delegation_with_deps(delegation_id, depends_on, planned_tier="fast", gate_cwd="REPO_ROOT",
                               gate_cmd=None, pinned_content=PINNED_TEST, artifact_path="test_slug.py"):
    return {
        "delegation_id": delegation_id,
        "plan_position": f"phase-1/milestone-1/{delegation_id}",
        "depends_on": depends_on,
        "resolved_prompt": f"Implement for {delegation_id}.",
        "planned_tier": planned_tier,
        "gate": {
            "command": gate_cmd or f"{sys.executable} -m unittest test_slug -v",
            "cwd": gate_cwd,
            "pass_criteria": "exit 0",
            "baseline_polarity": "fail",
        },
        "upstream_artifacts": [
            {"kind": "repository_state", "pinned": {"head": "advisory-placeholder", "dirty_files": []}},
            {"kind": "pinned_acceptance_test", "path": artifact_path, "pinned_content": pinned_content},
        ],
    }


class RunWithEscalationTests(unittest.TestCase):
    def _executor_factory(self, impl_by_model):
        def factory(model):
            def executor(prompt, m, workdir):
                (workdir / "slug.py").write_text(impl_by_model[model])
            return executor
        return factory

    def test_escalates_from_fast_to_standard_on_gate_failure(self):
        with temp_git_repo() as repo:
            with tempfile.TemporaryDirectory() as tmp:
                log_path = Path(tmp) / "delegations.jsonl"
                factory = self._executor_factory({"fake-fast": BAD_IMPL, "fake-standard": GOOD_IMPL})

                record, diff_text = conduct.run_with_escalation(
                    make_delegation_with_deps("esc.slugify", []),
                    repo_root=repo,
                    target_branch="main",
                    routing=ROUTING_ALL_TIERS,
                    executor_factory=factory,
                    log_path=log_path,
                )

                self.assertEqual(record["outcome"]["status"], "pass")
                self.assertTrue(record["outcome"]["escalated"])
                self.assertEqual(record["outcome"]["escalation_magnitude"], 1)
                self.assertIn("fast", record["outcome"]["escalation_trigger"])
                self.assertEqual(dl.validate_record(record), [])
                self.assertIsNotNone(diff_text)
                assert diff_text is not None
                self.assertIn("slug.py", diff_text)

                lines = log_path.read_text().splitlines()
                self.assertEqual(len(lines), 1, "exactly one record per delegation, not one per attempt")
                self.assertEqual(json.loads(lines[0]), record)

    def test_exhausted_ladder_fails_with_notes_on_all_tiers(self):
        with temp_git_repo() as repo:
            with tempfile.TemporaryDirectory() as tmp:
                log_path = Path(tmp) / "delegations.jsonl"
                factory = self._executor_factory(
                    {"fake-fast": BAD_IMPL, "fake-standard": BAD_IMPL, "fake-reasoning": BAD_IMPL}
                )

                record, diff_text = conduct.run_with_escalation(
                    make_delegation_with_deps("exhaust.slugify", []),
                    repo_root=repo,
                    target_branch="main",
                    routing=ROUTING_ALL_TIERS,
                    executor_factory=factory,
                    log_path=log_path,
                )

                self.assertEqual(record["outcome"]["status"], "fail")
                self.assertFalse(record["outcome"]["escalated"])
                for tier in ("fast", "standard", "reasoning"):
                    self.assertIn(tier, record["outcome"]["notes"])
                self.assertEqual(dl.validate_record(record), [])

                lines = log_path.read_text().splitlines()
                self.assertEqual(len(lines), 1)
                self.assertEqual(json.loads(lines[0]), record)

    def test_no_model_for_planned_tier_never_executes_or_logs(self):
        with temp_git_repo() as repo:
            with tempfile.TemporaryDirectory() as tmp:
                log_path = Path(tmp) / "delegations.jsonl"
                called = []

                def factory(model):
                    called.append(model)
                    def executor(prompt, m, workdir):
                        called.append("executed")
                    return executor

                record, diff_text = conduct.run_with_escalation(
                    make_delegation_with_deps("noroute.slugify", [], planned_tier="fast"),
                    repo_root=repo,
                    target_branch="main",
                    routing={"model_tiers": {}},
                    executor_factory=factory,
                    log_path=log_path,
                )

                self.assertEqual(record["outcome"]["status"], "fail")
                self.assertIn("no model", record["outcome"]["notes"])
                self.assertIsNone(diff_text)
                self.assertEqual(called, [], "executor_factory must never be invoked")
                self.assertFalse(log_path.exists(), "nothing should be logged")


class CommitDiffTests(unittest.TestCase):
    def test_commits_diff_to_target_branch(self):
        with temp_git_repo() as repo:
            def executor(prompt, model, workdir):
                (workdir / "slug.py").write_text(GOOD_IMPL)

            record, diff_text = conduct.run_delegation(
                make_delegation(),
                repo_root=repo,
                target_branch="main",
                tier="fast",
                model="fake-fast",
                executor=executor,
                log_path=Path(tempfile.mktemp()),
            )
            self.assertEqual(record["outcome"]["status"], "pass")

            expected_head = _pinned_head(record)
            sha = conduct._commit_diff(repo, "main", diff_text, "commit-test.slugify", expected_head)
            log = subprocess.run(
                ["git", "-C", str(repo), "log", "-1", "--format=%an <%ae> %s"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            self.assertIn("killhouse-conductor", log)
            self.assertIn("conductor@killhouse.local", log)
            self.assertIn("commit-test.slugify", log)

            head = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "main"], capture_output=True, text=True
            ).stdout.strip()
            self.assertEqual(head, sha)

    def test_update_ref_race_guard_raises_when_branch_moved(self):
        with temp_git_repo() as repo:
            def executor(prompt, model, workdir):
                (workdir / "slug.py").write_text(GOOD_IMPL)

            record, diff_text = conduct.run_delegation(
                make_delegation(),
                repo_root=repo,
                target_branch="main",
                tier="fast",
                model="fake-fast",
                executor=executor,
                log_path=Path(tempfile.mktemp()),
            )
            self.assertEqual(record["outcome"]["status"], "pass")
            expected_head = _pinned_head(record)  # the tip the diff was computed against

            # Move the branch out from under _commit_diff between diff capture and commit-back.
            (repo / "intervening.txt").write_text("race\n")
            subprocess.run(["git", "-C", str(repo), "add", "intervening.txt"], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "commit", "-q", "-m", "intervening"], check=True
            )

            with self.assertRaises(subprocess.CalledProcessError) as cm:
                conduct._commit_diff(repo, "main", diff_text, "race-test.slugify", expected_head)
            self.assertIn("update-ref", " ".join(cm.exception.cmd))


class ConductEndToEndTests(unittest.TestCase):
    def test_chain_and_independent_delegation_all_pass_with_commit_back(self):
        with temp_git_repo() as repo:
            with tempfile.TemporaryDirectory() as tmp:
                log_path = Path(tmp) / "delegations.jsonl"

                a = make_delegation_with_deps(
                    "A", [], gate_cwd="REPO_ROOT",
                    gate_cmd=(
                        f"{sys.executable} -c \"import pathlib; "
                        "assert pathlib.Path('a.txt').is_file()\""
                    ),
                    pinned_content="unused\n", artifact_path="unused_a.txt",
                )
                b = make_delegation_with_deps(
                    "B", ["A"], gate_cwd="REPO_ROOT",
                    # B's gate reads the file A committed: proves the commit landed on the branch.
                    gate_cmd=(
                        f"{sys.executable} -c \"import pathlib; "
                        "assert pathlib.Path('a.txt').read_text() == 'from-A\\n'\""
                    ),
                    pinned_content="unused\n", artifact_path="unused_b.txt",
                )
                c = make_delegation_with_deps(
                    "C", [], gate_cwd="REPO_ROOT",
                    gate_cmd=(
                        f"{sys.executable} -c \"import pathlib; "
                        "assert pathlib.Path('c.txt').is_file()\""
                    ),
                    pinned_content="unused\n", artifact_path="unused_c.txt",
                )
                plan = {"plan_id": "e2e-plan", "delegations": [a, b, c]}

                def factory(model):
                    def executor(prompt, m, workdir):
                        if prompt.endswith("A."):
                            (workdir / "a.txt").write_text("from-A\n")
                        elif prompt.endswith("B."):
                            pass  # B's gate only reads A's file; nothing to write
                        elif prompt.endswith("C."):
                            (workdir / "c.txt").write_text("from-C\n")
                    return executor

                summary = conduct.conduct(
                    plan,
                    repo_root=repo,
                    target_branch="main",
                    routing=ROUTING_ALL_TIERS,
                    executor_factory=factory,
                    log_path=log_path,
                )

                self.assertEqual(summary["verdicts"], {"A": "PASS", "B": "PASS", "C": "PASS"})
                self.assertIn("A", summary["commits"])
                self.assertIn("C", summary["commits"])

                log = subprocess.run(
                    ["git", "-C", str(repo), "log", "--format=%an <%ae> %s"],
                    capture_output=True, text=True, check=True,
                ).stdout
                self.assertIn("conduct: A", log)
                self.assertIn("conduct: C", log)
                self.assertIn("killhouse-conductor <conductor@killhouse.local>", log)

    def test_failing_dependency_blocks_dependent_but_not_independent(self):
        with temp_git_repo() as repo:
            with tempfile.TemporaryDirectory() as tmp:
                log_path = Path(tmp) / "delegations.jsonl"

                a = make_delegation_with_deps(
                    "A", [], gate_cwd="REPO_ROOT",
                    gate_cmd=f"{sys.executable} -c \"import sys; sys.exit(1)\"",
                    pinned_content="unused\n", artifact_path="unused_a.txt",
                )
                b_calls = []
                b = make_delegation_with_deps(
                    "B", ["A"], gate_cwd="REPO_ROOT",
                    gate_cmd=f"{sys.executable} -c \"import sys; sys.exit(0)\"",
                    pinned_content="unused\n", artifact_path="unused_b.txt",
                )
                c = make_delegation_with_deps(
                    "C", [], gate_cwd="REPO_ROOT",
                    gate_cmd=(
                        f"{sys.executable} -c \"import pathlib; "
                        "assert pathlib.Path('c.txt').is_file()\""
                    ),
                    pinned_content="unused\n", artifact_path="unused_c.txt",
                )
                plan = {"plan_id": "block-plan", "delegations": [a, b, c]}

                def factory(model):
                    def executor(prompt, m, workdir):
                        if prompt.endswith("B."):
                            b_calls.append(True)
                        if prompt.endswith("C."):
                            (workdir / "c.txt").write_text("from-C\n")
                    return executor

                summary = conduct.conduct(
                    plan,
                    repo_root=repo,
                    target_branch="main",
                    routing=ROUTING_ALL_TIERS,
                    executor_factory=factory,
                    log_path=log_path,
                )

                self.assertEqual(summary["verdicts"], {"A": "FAIL", "B": "BLOCKED", "C": "PASS"})
                self.assertEqual(b_calls, [], "B must never be executed once blocked")


class RunCliTests(unittest.TestCase):
    def test_run_with_no_model_tiers_exits_2_and_executes_nothing(self):
        with temp_git_repo() as repo:
            plan = {
                "plan_id": "cli-plan",
                "target_branch": "main",
                "delegations": [make_delegation_with_deps("cli.slugify", [])],
            }
            plan_path = repo / "plan.json"
            plan_path.write_text(json.dumps(plan))

            exit_code = conduct.main(["--run", str(plan_path), "--repo-root", str(repo)])
            self.assertEqual(exit_code, 2)

            log_path = conduct.default_log_path(repo)
            self.assertFalse(log_path.exists())


class UnwritableLogPathTests(unittest.TestCase):
    @unittest.skipIf(os.name != "posix", "permission-bit probe requires POSIX")
    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root bypasses permission bits")
    def test_unwritable_log_dir_sets_log_error(self):
        with temp_git_repo() as repo:
            with tempfile.TemporaryDirectory() as tmp:
                blocked_dir = Path(tmp) / "blocked"
                blocked_dir.mkdir()
                os.chmod(blocked_dir, 0o500)
                log_path = blocked_dir / "nested" / "delegations.jsonl"

                def executor(prompt, model, workdir):
                    (workdir / "slug.py").write_text(GOOD_IMPL)

                try:
                    record, _ = conduct.run_delegation(
                        make_delegation(),
                        repo_root=repo,
                        target_branch="main",
                        tier="fast",
                        model="fake-fast",
                        executor=executor,
                        log_path=log_path,
                    )
                    self.assertIn("_log_error", record)
                finally:
                    os.chmod(blocked_dir, 0o755)


if __name__ == "__main__":
    unittest.main()
