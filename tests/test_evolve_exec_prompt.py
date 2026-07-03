import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "evolve_exec_prompt.py"


def run_extract(champions):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        champions_path = tmp_path / "champions.json"
        prompt_path = tmp_path / "prompt.md"
        if isinstance(champions, str):
            champions_path.write_text(champions)
        else:
            champions_path.write_text(json.dumps(champions))
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--champions",
                str(champions_path),
                "--prompt-out",
                str(prompt_path),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )


class EvolveExecPromptTests(unittest.TestCase):
    def test_extracts_highest_fitness_champion(self):
        result = run_extract(
            [
                {"fitness": 0.2, "round": 2, "genome": "older"},
                {"fitness": 0.9, "round": 1, "genome": "best"},
            ]
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[ok] wrote execution prompt", result.stdout)

    def test_empty_champions_exit_3(self):
        result = run_extract([])

        self.assertEqual(result.returncode, 3)
        self.assertIn("no usable champion", result.stderr)

    def test_malformed_json_exits_2(self):
        result = run_extract("{")

        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot read champions file", result.stderr)

    def test_missing_genome_exits_3(self):
        result = run_extract([{"fitness": 1.0, "round": 1}])

        self.assertEqual(result.returncode, 3)
        self.assertIn("no usable champion", result.stderr)

    def test_mixed_fitness_types_do_not_traceback(self):
        result = run_extract(
            [
                {"fitness": "high", "round": 1, "genome": "bad"},
                {"fitness": 0.5, "round": 2, "genome": "good"},
            ]
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
