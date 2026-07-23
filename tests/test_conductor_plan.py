import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import killhouse_conduct as conduct  # noqa: E402

SAMPLE_PATH = ROOT / "schemas" / "conductor_plan.sample.json"
SCRIPT = ROOT / "bin" / "killhouse_conduct.py"


def sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text())


class PlanSchemaTests(unittest.TestCase):
    def test_canonical_sample_is_valid(self):
        self.assertEqual(conduct.validate_plan(sample()), [])

    def test_missing_plan_id_fails(self):
        plan = sample()
        del plan["plan_id"]
        errors = conduct.validate_plan(plan)
        self.assertTrue(errors, "deleting 'plan_id' should invalidate the plan")
        self.assertTrue(
            any("missing required field 'plan_id'" in e for e in errors),
            f"error for missing 'plan_id' not reported: {errors}",
        )

    def test_missing_target_branch_fails(self):
        plan = sample()
        del plan["target_branch"]
        errors = conduct.validate_plan(plan)
        self.assertTrue(errors, "deleting 'target_branch' should invalidate the plan")
        self.assertTrue(
            any("missing required field 'target_branch'" in e for e in errors),
            f"error for missing 'target_branch' not reported: {errors}",
        )

    def test_missing_delegations_fails(self):
        plan = sample()
        del plan["delegations"]
        errors = conduct.validate_plan(plan)
        self.assertTrue(errors, "deleting 'delegations' should invalidate the plan")
        self.assertTrue(
            any("missing required field 'delegations'" in e for e in errors),
            f"error for missing 'delegations' not reported: {errors}",
        )

    def test_missing_delegation_id_fails(self):
        plan = sample()
        del plan["delegations"][0]["delegation_id"]
        errors = conduct.validate_plan(plan)
        self.assertTrue(errors)
        self.assertTrue(
            any("missing required field 'delegation_id'" in e for e in errors),
            f"error for missing 'delegation_id' not reported: {errors}",
        )

    def test_missing_plan_position_fails(self):
        plan = sample()
        del plan["delegations"][0]["plan_position"]
        errors = conduct.validate_plan(plan)
        self.assertTrue(errors)
        self.assertTrue(
            any("missing required field 'plan_position'" in e for e in errors),
            f"error for missing 'plan_position' not reported: {errors}",
        )

    def test_missing_depends_on_fails(self):
        plan = sample()
        del plan["delegations"][0]["depends_on"]
        errors = conduct.validate_plan(plan)
        self.assertTrue(errors)
        self.assertTrue(
            any("missing required field 'depends_on'" in e for e in errors),
            f"error for missing 'depends_on' not reported: {errors}",
        )

    def test_missing_resolved_prompt_fails(self):
        plan = sample()
        del plan["delegations"][0]["resolved_prompt"]
        errors = conduct.validate_plan(plan)
        self.assertTrue(errors)
        self.assertTrue(
            any("missing required field 'resolved_prompt'" in e for e in errors),
            f"error for missing 'resolved_prompt' not reported: {errors}",
        )

    def test_missing_planned_tier_fails(self):
        plan = sample()
        del plan["delegations"][0]["planned_tier"]
        errors = conduct.validate_plan(plan)
        self.assertTrue(errors)
        self.assertTrue(
            any("missing required field 'planned_tier'" in e for e in errors),
            f"error for missing 'planned_tier' not reported: {errors}",
        )

    def test_missing_gate_fails(self):
        plan = sample()
        del plan["delegations"][0]["gate"]
        errors = conduct.validate_plan(plan)
        self.assertTrue(errors)
        self.assertTrue(
            any("missing required field 'gate'" in e for e in errors),
            f"error for missing 'gate' not reported: {errors}",
        )

    def test_missing_upstream_artifacts_fails(self):
        plan = sample()
        del plan["delegations"][0]["upstream_artifacts"]
        errors = conduct.validate_plan(plan)
        self.assertTrue(errors)
        self.assertTrue(
            any("missing required field 'upstream_artifacts'" in e for e in errors),
            f"error for missing 'upstream_artifacts' not reported: {errors}",
        )

    def test_invalid_planned_tier_enum_fails(self):
        plan = sample()
        plan["delegations"][0]["planned_tier"] = "cheap"
        errors = conduct.validate_plan(plan)
        self.assertTrue(errors)
        self.assertTrue(
            any("enum" in e for e in errors),
            f"error for invalid 'planned_tier' not reported: {errors}",
        )

    def test_duplicate_delegation_id_fails(self):
        plan = sample()
        plan["delegations"][1]["delegation_id"] = plan["delegations"][0]["delegation_id"]
        errors = conduct.validate_plan(plan)
        self.assertTrue(errors)
        dup_id = plan["delegations"][0]["delegation_id"]
        self.assertTrue(
            any(f"duplicate delegation_id '{dup_id}'" in e for e in errors),
            f"error for duplicate delegation_id not reported: {errors}",
        )

    def test_unknown_dependency_fails(self):
        plan = sample()
        plan["delegations"][1]["depends_on"] = ["nonexistent-delegation"]
        errors = conduct.validate_plan(plan)
        self.assertTrue(errors)
        self.assertTrue(
            any("unknown dependency 'nonexistent-delegation'" in e for e in errors),
            f"error for unknown dependency not reported: {errors}",
        )

    def test_missing_gate_command_fails(self):
        plan = sample()
        del plan["delegations"][0]["gate"]["command"]
        errors = conduct.validate_plan(plan)
        self.assertTrue(errors)
        self.assertTrue(
            any("missing required field 'command'" in e for e in errors),
            f"error for missing gate 'command' not reported: {errors}",
        )

    def test_missing_gate_cwd_fails(self):
        plan = sample()
        del plan["delegations"][0]["gate"]["cwd"]
        errors = conduct.validate_plan(plan)
        self.assertTrue(errors)
        self.assertTrue(
            any("missing required field 'cwd'" in e for e in errors),
            f"error for missing gate 'cwd' not reported: {errors}",
        )

    def test_missing_gate_pass_criteria_fails(self):
        plan = sample()
        del plan["delegations"][0]["gate"]["pass_criteria"]
        errors = conduct.validate_plan(plan)
        self.assertTrue(errors)
        self.assertTrue(
            any("missing required field 'pass_criteria'" in e for e in errors),
            f"error for missing gate 'pass_criteria' not reported: {errors}",
        )

    def test_missing_gate_baseline_polarity_fails(self):
        plan = sample()
        del plan["delegations"][0]["gate"]["baseline_polarity"]
        errors = conduct.validate_plan(plan)
        self.assertTrue(errors)
        self.assertTrue(
            any("missing required field 'baseline_polarity'" in e for e in errors),
            f"error for missing gate 'baseline_polarity' not reported: {errors}",
        )

    def test_valid_empty_depends_on(self):
        plan = sample()
        plan["delegations"][0]["depends_on"] = []
        errors = conduct.validate_plan(plan)
        self.assertEqual(errors, [])

    def test_valid_empty_upstream_artifacts(self):
        plan = sample()
        plan["delegations"][0]["upstream_artifacts"] = []
        errors = conduct.validate_plan(plan)
        self.assertEqual(errors, [])


class CliTests(unittest.TestCase):
    def _run(self, plan_text: str, args: list[str] | None = None):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan.json"
            plan.write_text(plan_text)
            cmd = [sys.executable, str(SCRIPT), "--validate", str(plan)]
            if args:
                cmd.extend(args)
            return subprocess.run(
                cmd,
                text=True,
                capture_output=True,
            )

    def test_cli_passes_on_valid_plan(self):
        result = self._run(json.dumps(sample()) + "\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[ok] plan", result.stdout)

    def test_cli_fails_on_missing_field(self):
        broken = sample()
        del broken["plan_id"]
        result = self._run(json.dumps(broken) + "\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing required field 'plan_id'", result.stderr)

    def test_cli_fails_on_invalid_json(self):
        result = self._run("{ invalid json }")
        self.assertEqual(result.returncode, 1)
        self.assertIn("[fail]", result.stderr)

    def test_cli_fails_on_duplicate_delegation_id(self):
        broken = sample()
        broken["delegations"][1]["delegation_id"] = broken["delegations"][0]["delegation_id"]
        result = self._run(json.dumps(broken) + "\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("duplicate delegation_id", result.stderr)

    def test_cli_fails_on_unknown_dependency(self):
        broken = sample()
        broken["delegations"][1]["depends_on"] = ["unknown-delegation"]
        result = self._run(json.dumps(broken) + "\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown dependency", result.stderr)

    def test_cli_schema_path(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--schema-path"],
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("conductor_plan.schema.json", result.stdout)


class TopoOrderTests(unittest.TestCase):
    def test_topo_order_respects_dependencies(self):
        """Build a 4-delegation plan where plan order disagrees with dep order."""
        plan = {
            "plan_id": "test-topo",
            "target_branch": "test",
            "delegations": [
                {
                    "delegation_id": "D",
                    "plan_position": "pos-d",
                    "depends_on": ["C"],
                    "resolved_prompt": "prompt-d",
                    "planned_tier": "fast",
                    "gate": {
                        "command": "echo d",
                        "cwd": "/tmp",
                        "pass_criteria": "exit 0",
                        "baseline_polarity": "fail",
                    },
                    "upstream_artifacts": [],
                },
                {
                    "delegation_id": "C",
                    "plan_position": "pos-c",
                    "depends_on": ["B"],
                    "resolved_prompt": "prompt-c",
                    "planned_tier": "fast",
                    "gate": {
                        "command": "echo c",
                        "cwd": "/tmp",
                        "pass_criteria": "exit 0",
                        "baseline_polarity": "fail",
                    },
                    "upstream_artifacts": [],
                },
                {
                    "delegation_id": "A",
                    "plan_position": "pos-a",
                    "depends_on": [],
                    "resolved_prompt": "prompt-a",
                    "planned_tier": "fast",
                    "gate": {
                        "command": "echo a",
                        "cwd": "/tmp",
                        "pass_criteria": "exit 0",
                        "baseline_polarity": "fail",
                    },
                    "upstream_artifacts": [],
                },
                {
                    "delegation_id": "B",
                    "plan_position": "pos-b",
                    "depends_on": ["A"],
                    "resolved_prompt": "prompt-b",
                    "planned_tier": "fast",
                    "gate": {
                        "command": "echo b",
                        "cwd": "/tmp",
                        "pass_criteria": "exit 0",
                        "baseline_polarity": "fail",
                    },
                    "upstream_artifacts": [],
                },
            ],
        }
        result = conduct.topo_order(plan)
        ids = [d.get("delegation_id") for d in result]
        self.assertEqual(ids, ["A", "B", "C", "D"])

    def test_topo_order_preserves_plan_order_for_independent(self):
        """Independent delegations should preserve plan order."""
        plan = {
            "plan_id": "test-independent",
            "target_branch": "test",
            "delegations": [
                {
                    "delegation_id": "X",
                    "plan_position": "pos-x",
                    "depends_on": [],
                    "resolved_prompt": "prompt-x",
                    "planned_tier": "fast",
                    "gate": {
                        "command": "echo x",
                        "cwd": "/tmp",
                        "pass_criteria": "exit 0",
                        "baseline_polarity": "fail",
                    },
                    "upstream_artifacts": [],
                },
                {
                    "delegation_id": "Y",
                    "plan_position": "pos-y",
                    "depends_on": [],
                    "resolved_prompt": "prompt-y",
                    "planned_tier": "fast",
                    "gate": {
                        "command": "echo y",
                        "cwd": "/tmp",
                        "pass_criteria": "exit 0",
                        "baseline_polarity": "fail",
                    },
                    "upstream_artifacts": [],
                },
                {
                    "delegation_id": "Z",
                    "plan_position": "pos-z",
                    "depends_on": [],
                    "resolved_prompt": "prompt-z",
                    "planned_tier": "fast",
                    "gate": {
                        "command": "echo z",
                        "cwd": "/tmp",
                        "pass_criteria": "exit 0",
                        "baseline_polarity": "fail",
                    },
                    "upstream_artifacts": [],
                },
            ],
        }
        result = conduct.topo_order(plan)
        ids = [d.get("delegation_id") for d in result]
        self.assertEqual(ids, ["X", "Y", "Z"])

    def test_topo_order_raises_on_cycle(self):
        """Cycle detection should raise ValueError."""
        plan = {
            "plan_id": "test-cycle",
            "target_branch": "test",
            "delegations": [
                {
                    "delegation_id": "A",
                    "plan_position": "pos-a",
                    "depends_on": ["B"],
                    "resolved_prompt": "prompt-a",
                    "planned_tier": "fast",
                    "gate": {
                        "command": "echo a",
                        "cwd": "/tmp",
                        "pass_criteria": "exit 0",
                        "baseline_polarity": "fail",
                    },
                    "upstream_artifacts": [],
                },
                {
                    "delegation_id": "B",
                    "plan_position": "pos-b",
                    "depends_on": ["A"],
                    "resolved_prompt": "prompt-b",
                    "planned_tier": "fast",
                    "gate": {
                        "command": "echo b",
                        "cwd": "/tmp",
                        "pass_criteria": "exit 0",
                        "baseline_polarity": "fail",
                    },
                    "upstream_artifacts": [],
                },
            ],
        }
        with self.assertRaises(ValueError) as cm:
            conduct.topo_order(plan)
        self.assertIn("cycle", str(cm.exception))

    def test_self_dependency_is_cycle(self):
        """Self-dependency should be detected as a cycle."""
        plan = {
            "plan_id": "test-self",
            "target_branch": "test",
            "delegations": [
                {
                    "delegation_id": "A",
                    "plan_position": "pos-a",
                    "depends_on": ["A"],
                    "resolved_prompt": "prompt-a",
                    "planned_tier": "fast",
                    "gate": {
                        "command": "echo a",
                        "cwd": "/tmp",
                        "pass_criteria": "exit 0",
                        "baseline_polarity": "fail",
                    },
                    "upstream_artifacts": [],
                },
            ],
        }
        errors = conduct.validate_plan(plan)
        self.assertTrue(
            any("cycle" in e for e in errors),
            f"self-dependency not reported as cycle: {errors}",
        )

    def test_cycle_detected_in_validate_plan(self):
        """Cycle should be detected by validate_plan."""
        plan = {
            "plan_id": "test-cycle",
            "target_branch": "test",
            "delegations": [
                {
                    "delegation_id": "A",
                    "plan_position": "pos-a",
                    "depends_on": ["B"],
                    "resolved_prompt": "prompt-a",
                    "planned_tier": "fast",
                    "gate": {
                        "command": "echo a",
                        "cwd": "/tmp",
                        "pass_criteria": "exit 0",
                        "baseline_polarity": "fail",
                    },
                    "upstream_artifacts": [],
                },
                {
                    "delegation_id": "B",
                    "plan_position": "pos-b",
                    "depends_on": ["A"],
                    "resolved_prompt": "prompt-b",
                    "planned_tier": "fast",
                    "gate": {
                        "command": "echo b",
                        "cwd": "/tmp",
                        "pass_criteria": "exit 0",
                        "baseline_polarity": "fail",
                    },
                    "upstream_artifacts": [],
                },
            ],
        }
        errors = conduct.validate_plan(plan)
        self.assertTrue(
            any("cycle" in e for e in errors),
            f"cycle not reported: {errors}",
        )


class DryRunTests(unittest.TestCase):
    def test_dry_run_returns_correct_format(self):
        """dry_run should return list with delegation_id, planned_tier, plan_position."""
        plan = sample()
        result = conduct.dry_run(plan)
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)
        for entry in result:
            self.assertIn("delegation_id", entry)
            self.assertIn("planned_tier", entry)
            self.assertIn("plan_position", entry)

    def test_dry_run_respects_topo_order(self):
        """dry_run should return entries in topological order."""
        plan = {
            "plan_id": "test-dry",
            "target_branch": "test",
            "delegations": [
                {
                    "delegation_id": "B",
                    "plan_position": "pos-b",
                    "depends_on": ["A"],
                    "resolved_prompt": "prompt-b",
                    "planned_tier": "standard",
                    "gate": {
                        "command": "echo b",
                        "cwd": "/tmp",
                        "pass_criteria": "exit 0",
                        "baseline_polarity": "fail",
                    },
                    "upstream_artifacts": [],
                },
                {
                    "delegation_id": "A",
                    "plan_position": "pos-a",
                    "depends_on": [],
                    "resolved_prompt": "prompt-a",
                    "planned_tier": "fast",
                    "gate": {
                        "command": "echo a",
                        "cwd": "/tmp",
                        "pass_criteria": "exit 0",
                        "baseline_polarity": "fail",
                    },
                    "upstream_artifacts": [],
                },
            ],
        }
        result = conduct.dry_run(plan)
        ids = [e["delegation_id"] for e in result]
        self.assertEqual(ids, ["A", "B"])
        self.assertEqual(result[0]["planned_tier"], "fast")
        self.assertEqual(result[1]["planned_tier"], "standard")

    @patch("subprocess.run")
    def test_dry_run_does_not_call_subprocess(self, mock_run):
        """dry_run should not call subprocess.run."""
        mock_run.side_effect = AssertionError("subprocess.run was called during dry_run")
        plan = sample()
        try:
            conduct.dry_run(plan)
        except AssertionError:
            self.fail("dry_run called subprocess.run")


class DryRunCliTests(unittest.TestCase):
    def _run_dry_run(self, plan_text: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan.json"
            plan.write_text(plan_text)
            cmd = [sys.executable, str(SCRIPT), "--dry-run", str(plan)]
            return subprocess.run(
                cmd,
                text=True,
                capture_output=True,
            )

    def test_cli_dry_run_valid_plan(self):
        """--dry-run with valid plan should print numbered lines."""
        result = self._run_dry_run(json.dumps(sample()) + "\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.strip().split("\n")
        self.assertGreaterEqual(len(lines), 2, "should have at least 2 delegations")
        for i, line in enumerate(lines, 1):
            self.assertTrue(
                line.startswith(f"{i}."),
                f"line {i} should start with '{i}.'",
            )
            self.assertIn("[", line)
            self.assertIn("]", line)

    def test_cli_dry_run_cyclic_plan(self):
        """--dry-run with cyclic plan should exit 1 with cycle error."""
        broken = sample()
        broken["delegations"] = [
            {
                "delegation_id": "A",
                "plan_position": "pos-a",
                "depends_on": ["B"],
                "resolved_prompt": "prompt-a",
                "planned_tier": "fast",
                "gate": {
                    "command": "echo a",
                    "cwd": "/tmp",
                    "pass_criteria": "exit 0",
                    "baseline_polarity": "fail",
                },
                "upstream_artifacts": [],
            },
            {
                "delegation_id": "B",
                "plan_position": "pos-b",
                "depends_on": ["A"],
                "resolved_prompt": "prompt-b",
                "planned_tier": "fast",
                "gate": {
                    "command": "echo b",
                    "cwd": "/tmp",
                    "pass_criteria": "exit 0",
                    "baseline_polarity": "fail",
                },
                "upstream_artifacts": [],
            },
        ]
        result = self._run_dry_run(json.dumps(broken) + "\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cycle", result.stderr)

    def test_cli_dry_run_mutually_exclusive(self):
        """--dry-run and --validate should be mutually exclusive."""
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan.json"
            plan.write_text(json.dumps(sample()) + "\n")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--dry-run", str(plan), "--validate", str(plan)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("mutually exclusive", result.stderr)


if __name__ == "__main__":
    unittest.main()
