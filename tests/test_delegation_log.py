import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import killhouse_delegation_log as dl  # noqa: E402

SAMPLE_PATH = ROOT / "schemas" / "delegation_record.sample.json"
SCRIPT = ROOT / "bin" / "killhouse_delegation_log.py"


def sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text())


class RecordSchemaTests(unittest.TestCase):
    def test_canonical_sample_is_valid(self):
        self.assertEqual(dl.validate_record(sample()), [])

    def test_missing_any_required_top_level_field_fails(self):
        record = sample()
        for field in dl.load_schema()["required"]:
            broken = copy.deepcopy(record)
            del broken[field]
            errors = dl.validate_record(broken)
            self.assertTrue(errors, f"deleting '{field}' should invalidate the record")
            self.assertTrue(
                any(f"missing required field '{field}'" in e for e in errors),
                f"error for missing '{field}' not reported: {errors}",
            )

    def test_optional_router_fields_may_be_absent(self):
        record = sample()
        for field in ("chosen_model", "routing_request", "router_decision"):
            record.pop(field, None)
        self.assertEqual(dl.validate_record(record), [])

    def test_missing_gate_cwd_fails(self):
        # Gate 0 finding: replay fidelity depends on the gate's cwd, so it is required.
        broken = sample()
        del broken["gate"]["cwd"]
        errors = dl.validate_record(broken)
        self.assertTrue(any("missing required field 'cwd'" in e for e in errors), errors)

    def test_upstream_without_repository_state_fails(self):
        # A record must pin repo state to be replayable (Gate 0: HERMETIC condition).
        broken = sample()
        broken["upstream_artifacts"] = [{"kind": "redqueen_prompt", "status": "absent"}]
        errors = dl.validate_record(broken)
        self.assertTrue(any("contains" in e for e in errors), errors)

    def test_repository_state_without_head_fails(self):
        broken = sample()
        broken["upstream_artifacts"] = [
            {"kind": "repository_state", "pinned": {"vcs": "git", "dirty_files": []}}
        ]
        errors = dl.validate_record(broken)
        self.assertTrue(any("contains" in e for e in errors), errors)

    def test_repository_state_without_dirty_files_fails(self):
        broken = sample()
        repo_state = next(item for item in broken["upstream_artifacts"] if item["kind"] == "repository_state")
        del repo_state["pinned"]["dirty_files"]
        errors = dl.validate_record(broken)
        self.assertTrue(any("contains" in e for e in errors), errors)

    def test_dirty_file_requires_replay_content(self):
        broken = sample()
        repo_state = next(item for item in broken["upstream_artifacts"] if item["kind"] == "repository_state")
        repo_state["pinned"]["dirty_files"] = [{"path": "changed.py", "status": "modified"}]
        errors = dl.validate_record(broken)
        self.assertTrue(any("requires pinned_content or content_artifact" in e for e in errors), errors)

    def test_deleted_dirty_file_needs_no_content(self):
        record = sample()
        repo_state = next(item for item in record["upstream_artifacts"] if item["kind"] == "repository_state")
        repo_state["pinned"]["dirty_files"] = [{"path": "removed.py", "status": "deleted"}]
        self.assertEqual(dl.validate_record(record), [])

    def test_applied_router_decision_must_match_chosen_tier(self):
        broken = sample()
        broken["router_decision"]["selected_tier"] = "reasoning"
        errors = dl.validate_record(broken)
        self.assertTrue(any("selected_tier to equal chosen_tier" in e for e in errors), errors)

    def test_unapplied_router_decision_requires_fallback_reason(self):
        broken = sample()
        broken["router_decision"]["applied"] = False
        errors = dl.validate_record(broken)
        self.assertTrue(any("fallback_reason" in e for e in errors), errors)

    def test_escalated_outcome_requires_magnitude_and_trigger(self):
        broken = sample()
        broken["outcome"] = {"status": "fail", "escalated": True}
        errors = dl.validate_record(broken)
        self.assertTrue(any("escalation_magnitude" in e for e in errors), errors)
        self.assertTrue(any("escalation_trigger" in e for e in errors), errors)

    def test_escalated_outcome_with_fields_is_valid(self):
        record = sample()
        record["outcome"] = {
            "status": "fail",
            "escalated": True,
            "escalation_magnitude": 2,
            "escalation_trigger": "same gate failed twice under fast tier",
        }
        self.assertEqual(dl.validate_record(record), [])

    def test_wrong_tier_enum_fails(self):
        broken = sample()
        broken["chosen_tier"] = "cheap"
        errors = dl.validate_record(broken)
        self.assertTrue(any("enum" in e for e in errors), errors)

    def test_tier_price_requires_basis(self):
        broken = sample()
        broken["tier_price"] = {"currency": "USD", "input": 1.0, "output": 2.0}
        errors = dl.validate_record(broken)
        self.assertTrue(any("basis" in e for e in errors), errors)

    def test_priced_basis_requires_numbers(self):
        broken = sample()
        broken["tier_price"] = {"currency": "USD", "basis": "configured"}
        errors = dl.validate_record(broken)
        self.assertTrue(any("input" in e for e in errors), errors)
        self.assertTrue(any("output" in e for e in errors), errors)

    def test_unpriced_basis_needs_no_numbers(self):
        # Honest logging under current-model-only routing: no price known, none invented.
        record = sample()
        record["tier_price"] = {"currency": "USD", "basis": "unpriced"}
        self.assertEqual(dl.validate_record(record), [])


class CliTests(unittest.TestCase):
    def _run(self, log_text: str):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "delegations.jsonl"
            log.write_text(log_text)
            return subprocess.run(
                [sys.executable, str(SCRIPT), "--validate", str(log)],
                text=True,
                capture_output=True,
            )

    def test_cli_passes_on_valid_log(self):
        result = self._run(json.dumps(sample()) + "\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[ok] record 0", result.stdout)

    def test_cli_fails_on_missing_field(self):
        broken = sample()
        del broken["resolved_prompt"]
        result = self._run(json.dumps(broken) + "\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing required field 'resolved_prompt'", result.stderr)

    def test_cli_fails_on_empty_log(self):
        result = self._run("\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no records", result.stderr)


if __name__ == "__main__":
    unittest.main()
