import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import killhouse_gate_replay as gr  # noqa: E402

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

ROUTING = {"model_tiers": {"fast": "fake-fast", "standard": "fake-standard", "reasoning": "fake-reasoning"}}


def make_record(chosen_tier="reasoning"):
    return {
        "delegation_id": "replay-test.slugify.implementer",
        "plan_position": "phase-1/milestone-1/slice-1",
        "depends_on": [],
        "resolved_prompt": "Implement slug.py::slugify to satisfy the pinned test.",
        "chosen_tier": chosen_tier,
        "tier_price": {"currency": "USD", "basis": "configured", "input": 15.0, "output": 75.0},
        "decision_signals": {"source": "triage", "task_tier": "light", "confidence": 0.9, "reasoning": "x"},
        "gate": {
            "command": f"{sys.executable} -m unittest test_slug -v",
            "cwd": "REPO_ROOT",
            "pass_criteria": "exit 0",
            "baseline_polarity": "fail",
        },
        "upstream_artifacts": [
            {"kind": "repository_state", "pinned": {"head": "deadbeef", "dirty_files": []}},
            {"kind": "pinned_acceptance_test", "path": "test_slug.py", "pinned_content": PINNED_TEST},
        ],
        "outcome": {"status": "pass", "escalated": False},
    }


@contextmanager
def temp_sandbox(record):
    d = Path(tempfile.mkdtemp(prefix="kh-replay-test-"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


class GateReplayDirectionTests(unittest.TestCase):
    """Both directions are decided by the REAL gate (a real python -m unittest subprocess)."""

    def test_pass_when_cheaper_output_meets_the_gate(self):
        calls = []

        def executor(prompt, model, workdir):
            calls.append(model)
            (workdir / "slug.py").write_text(GOOD_IMPL)

        result = gr.replay(make_record(), "fast", routing=ROUTING,
                           executor=executor, sandbox_factory=temp_sandbox)
        self.assertEqual(result.verdict, "PASS", result.reason)
        self.assertEqual(result.gate_exit, 0)
        self.assertEqual(calls, ["fake-fast"], "executor must actually run on the lower-tier model")

    def test_fail_when_cheaper_output_misses_the_gate(self):
        def executor(prompt, model, workdir):
            (workdir / "slug.py").write_text(BAD_IMPL)

        result = gr.replay(make_record(), "fast", routing=ROUTING,
                           executor=executor, sandbox_factory=temp_sandbox)
        self.assertEqual(result.verdict, "FAIL", result.reason)
        self.assertNotEqual(result.gate_exit, 0)

    def test_gate_is_real_not_llm_judged(self):
        # An executor that writes nothing cannot satisfy the pinned test -> the real gate fails.
        def executor(prompt, model, workdir):
            pass

        result = gr.replay(make_record(), "fast", routing=ROUTING,
                           executor=executor, sandbox_factory=temp_sandbox)
        self.assertEqual(result.verdict, "FAIL")


class GateReplaySkipAndErrorTests(unittest.TestCase):
    def test_skips_without_routing_and_never_calls_executor(self):
        called = []

        def executor(prompt, model, workdir):
            called.append(True)

        result = gr.replay(make_record(), "fast", routing={},
                           executor=executor, sandbox_factory=temp_sandbox)
        self.assertEqual(result.verdict, "SKIPPED_NO_ROUTING")
        self.assertEqual(called, [], "must not run a replay when it cannot route to a real cheaper tier")

    def test_skips_when_routing_present_but_no_executor(self):
        result = gr.replay(make_record(), "fast", routing=ROUTING, sandbox_factory=temp_sandbox)
        self.assertEqual(result.verdict, "SKIPPED_NO_ROUTING")
        self.assertIn("executor", (result.reason or ""))

    def test_error_when_target_tier_is_not_lower(self):
        result = gr.replay(make_record(chosen_tier="fast"), "reasoning", routing=ROUTING,
                           sandbox_factory=temp_sandbox)
        self.assertEqual(result.verdict, "ERROR")
        self.assertIn("not lower", (result.reason or ""))

    def test_error_on_schema_invalid_record(self):
        record = make_record()
        del record["resolved_prompt"]
        result = gr.replay(record, "fast", routing=ROUTING, sandbox_factory=temp_sandbox)
        self.assertEqual(result.verdict, "ERROR")
        self.assertIn("schema", (result.reason or ""))

    def test_error_on_absolute_gate_cwd(self):
        # An absolute cwd cannot be faithfully remapped -> fail loud instead of mis-measuring.
        record = make_record()
        record["gate"]["cwd"] = "/some/original/checkout/backend"

        def executor(prompt, model, workdir):
            (workdir / "slug.py").write_text(GOOD_IMPL)

        result = gr.replay(record, "fast", routing=ROUTING, executor=executor, sandbox_factory=temp_sandbox)
        self.assertEqual(result.verdict, "ERROR")
        self.assertIn("absolute", (result.reason or ""))

    def test_error_on_sandbox_escaping_artifact_path(self):
        record = make_record()
        record["upstream_artifacts"].append(
            {"kind": "pinned_acceptance_test", "path": "../escape.py", "pinned_content": "x = 1\n"}
        )

        def executor(prompt, model, workdir):
            (workdir / "slug.py").write_text(GOOD_IMPL)

        result = gr.replay(record, "fast", routing=ROUTING, executor=executor, sandbox_factory=temp_sandbox)
        self.assertEqual(result.verdict, "ERROR")
        self.assertIn("escape", (result.reason or "").lower())


class GateReplayWorktreeTests(unittest.TestCase):
    """Exercise the default git-worktree sandbox end-to-end against the real repo HEAD."""

    def test_default_worktree_sandbox_runs_real_gate(self):
        head = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        record = make_record()
        record["upstream_artifacts"][0]["pinned"]["head"] = head

        def executor(prompt, model, workdir):
            (workdir / "slug.py").write_text(GOOD_IMPL)

        result = gr.replay(record, "fast", routing=ROUTING, executor=executor)  # default sandbox
        self.assertEqual(result.verdict, "PASS", result.reason)


@contextmanager
def temp_git_repo():
    """A small standalone git repo with one commit, for exercising the real sandbox helpers."""
    d = Path(tempfile.mkdtemp(prefix="kh-replay-source-"))
    try:
        subprocess.run(["git", "init", "-q", str(d)], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(d), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(d), "config", "user.name", "Test"], check=True)
        (d / "file.txt").write_text("hello\n")
        subprocess.run(["git", "-C", str(d), "add", "file.txt"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(d), "commit", "-q", "-m", "initial"], check=True, capture_output=True
        )
        yield d
    finally:
        # The read-only test below may leave .git non-writable; restore before removing.
        git_dir = d / ".git"
        if git_dir.is_dir():
            os.chmod(git_dir, 0o755)
        shutil.rmtree(d, ignore_errors=True)


class GateReplayWorktreeFallbackTests(unittest.TestCase):
    """git_worktree_sandbox falls back to a clone when the source repo's .git is not writable."""

    @unittest.skipIf(os.name != "posix", "permission-bit probe requires POSIX")
    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root bypasses permission bits")
    def test_falls_back_to_clone_when_git_dir_is_read_only(self):
        with temp_git_repo() as source_repo:
            head = subprocess.run(
                ["git", "-C", str(source_repo), "rev-parse", "HEAD"],
                capture_output=True, text=True,
            ).stdout.strip()
            record = {"upstream_artifacts": [{"kind": "repository_state", "pinned": {"head": head}}]}

            git_dir = source_repo / ".git"
            mode = git_dir.stat().st_mode
            os.chmod(git_dir, mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
            try:
                with gr.git_worktree_sandbox(record, repo_root=source_repo) as sandbox:
                    self.assertTrue((sandbox / "file.txt").is_file())
                    # A clone gets its own real .git directory; a linked worktree gets a .git
                    # *file* pointing back at the source repo.
                    self.assertTrue((sandbox / ".git").is_dir())
            finally:
                os.chmod(git_dir, mode)

    def test_raises_when_worktree_add_fails_for_a_non_permission_reason(self):
        with temp_git_repo() as source_repo:
            bogus_head = "0" * 40
            record = {
                "upstream_artifacts": [
                    {"kind": "repository_state", "pinned": {"head": bogus_head}}
                ]
            }
            with self.assertRaises(subprocess.CalledProcessError):
                with gr.git_worktree_sandbox(record, repo_root=source_repo):
                    pass


if __name__ == "__main__":
    unittest.main()
