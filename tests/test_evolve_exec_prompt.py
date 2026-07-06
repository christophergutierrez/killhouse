import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "evolve_exec_prompt.py"

sys.path.insert(0, str(ROOT / "bin"))
import evolve_exec_prompt as eep  # noqa: E402


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


FULL_CONFIG = {
    "base_url": "https://api.fireworks.ai/inference/v1",
    "api_key_env": "FW_KEY",
    "redqueen_tier": "standard",
    "model_tiers": {"fast": "m-fast", "standard": "m-standard", "reasoning": "m-reasoning"},
}


class ResolveRoutingTests(unittest.TestCase):
    def test_killhouse_config_injects_endpoint_model_and_key(self):
        env, notes = eep.resolve_routing({"FW_KEY": "tok"}, FULL_CONFIG)
        self.assertEqual(env["OPENAI_BASE_URL"], "https://api.fireworks.ai/inference/v1")
        self.assertEqual(env["DRQ_MODEL"], "m-standard")
        self.assertEqual(env["OPENAI_API_KEY"], "tok")
        self.assertTrue(notes)

    def test_killhouse_config_overrides_ambient_env(self):
        base = {"FW_KEY": "tok", "OPENAI_BASE_URL": "http://ambient", "DRQ_MODEL": "ambient-model"}
        env, _ = eep.resolve_routing(base, FULL_CONFIG)
        self.assertEqual(env["OPENAI_BASE_URL"], "https://api.fireworks.ai/inference/v1")
        self.assertEqual(env["DRQ_MODEL"], "m-standard")

    def test_default_tier_is_standard(self):
        config = dict(FULL_CONFIG)
        del config["redqueen_tier"]
        env, _ = eep.resolve_routing({"FW_KEY": "tok"}, config)
        self.assertEqual(env["DRQ_MODEL"], "m-standard")

    def test_silent_config_leaves_ambient_untouched(self):
        base = {"OPENAI_BASE_URL": "http://ambient", "DRQ_MODEL": "ambient-model"}
        env, notes = eep.resolve_routing(base, {"model_tiers": {"fast": "x"}})  # no base_url -> no drive
        self.assertEqual(env["OPENAI_BASE_URL"], "http://ambient")
        self.assertEqual(env["DRQ_MODEL"], "ambient-model")
        self.assertEqual(notes, [])

    def test_unset_api_key_env_raises(self):
        with self.assertRaises(eep.ConfigError) as ctx:
            eep.resolve_routing({}, FULL_CONFIG)  # FW_KEY not in env
        self.assertIn("FW_KEY", str(ctx.exception))

    def test_bad_redqueen_tier_raises(self):
        config = dict(FULL_CONFIG, redqueen_tier="ultra")
        with self.assertRaises(eep.ConfigError) as ctx:
            eep.resolve_routing({"FW_KEY": "tok"}, config)
        self.assertIn("ultra", str(ctx.exception))

    def test_base_url_without_model_tiers_raises(self):
        with self.assertRaises(eep.ConfigError):
            eep.resolve_routing({}, {"base_url": "http://x"})


class LoadConfigTests(unittest.TestCase):
    def test_local_config_wins_over_project_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            kh = Path(tmp) / ".killhouse"
            kh.mkdir()
            (kh / "config.json").write_text(json.dumps({"base_url": "http://project"}))
            (kh / "config.local.json").write_text(json.dumps({"base_url": "http://local"}))
            self.assertEqual(eep.load_killhouse_config(Path(tmp))["base_url"], "http://local")

    def test_missing_config_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(eep.load_killhouse_config(Path(tmp)), {})


class PrintRoutingCliTests(unittest.TestCase):
    def test_print_routing_without_config_reports_ambient(self):
        # The real repo ships no .killhouse/config.{local.,}json, so routing falls back to ambient.
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--print-routing"], cwd=ROOT, text=True, capture_output=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no base_url", result.stdout)


if __name__ == "__main__":
    unittest.main()
