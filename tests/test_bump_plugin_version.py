import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
import bump_plugin_version as bump


class TestManifestVersions(unittest.TestCase):
    def test_versions_consistent_and_semver(self):
        versions = bump.manifest_versions()
        self.assertEqual(len(set(versions.values())), 1, f"manifest versions differ: {versions}")
        version = next(iter(versions.values()))
        self.assertRegex(version, r"^\d+\.\d+\.\d+", f"version not semver: {version}")

    def test_manifest_paths_exist(self):
        for path in bump.MANIFEST_PATHS:
            self.assertTrue((ROOT / path).is_file(), f"manifest not found: {path}")


if __name__ == "__main__":
    unittest.main()
