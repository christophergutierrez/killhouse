"""Hermetic unittest suite for bin/adr_drift.py.

Tests external behavior via CLI/JSON output, not internal helpers.
Uses tempfile.TemporaryDirectory + synthetic ADR/source fixtures.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import adr_drift  # noqa: E402

SCRIPT = ROOT / "bin" / "adr_drift.py"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _run_cli(*args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


class TestPlannedExpectedGap(unittest.TestCase):
    """planned + no source evidence -> expected_gap."""

    def test_planned_no_source_is_expected_gap(self):
        with tempfile.TemporaryDirectory() as d:
            adr = _write(
                Path(d) / "adr-0001.md",
                "---\nimplementation: planned\n---\n\n# Use SQLite\n\nPlanned.\n",
            )
            src = _write(Path(d) / "src" / "empty.py", "# nothing here\n")
            rc, out, _ = _run_cli(
                "--adrs", str(adr), "--source-root", str(src.parent), "--mode", "report"
            )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["bucket"], "expected_gap")


class TestSeededContradictionDrift(unittest.TestCase):
    """shipped + load_bearing: true + forbidden term in source -> drift."""

    def test_forbidden_term_in_source_is_drift(self):
        with tempfile.TemporaryDirectory() as d:
            adr = _write(
                Path(d) / "adr-0001.md",
                "---\nimplementation: shipped\nload_bearing: true\n"
                "forbidden_terms: mysql, postgres\n---\n\n# Use SQLite\n\nWe use SQLite.\n",
            )
            # Source contains a forbidden term.
            _write(Path(d) / "src" / "app.py", "import mysql.connector\n# Use SQLite\n")
            rc, out, _ = _run_cli(
                "--adrs", str(adr), "--source-root", str(Path(d) / "src"), "--mode", "report"
            )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data[0]["bucket"], "drift")


class TestUndocumentedPattern(unittest.TestCase):
    """Load-bearing code pattern with no covering ADR -> undocumented (advisory)."""

    def test_undocumented_pattern_reported(self):
        with tempfile.TemporaryDirectory() as d:
            adr = _write(
                Path(d) / "adr-0001.md",
                "---\nimplementation: shipped\n---\n\n# Use SQLite\n\nWe use SQLite.\n",
            )
            _write(Path(d) / "src" / "app.py", "import sqlite3\nimport redis_cache\n# Use SQLite\n")
            # Context doc declares a load-bearing pattern not covered by any ADR.
            ctx = _write(Path(d) / "ctx.txt", "redis_cache\n")
            rc, out, _ = _run_cli(
                "--adrs", str(adr),
                "--source-root", str(Path(d) / "src"),
                "--context-docs", str(ctx),
                "--mode", "report",
            )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        # The ADR itself is confirmed.
        adr_entry = [e for e in data if e["id"] == "adr-0001"][0]
        self.assertEqual(adr_entry["bucket"], "confirmed")
        # There should be an undocumented finding for redis_cache.
        undocumented = [e for e in data if e["bucket"] == "undocumented"]
        self.assertTrue(len(undocumented) >= 1, f"expected undocumented finding, got: {data}")
        self.assertTrue(any("redis_cache" in str(e) for e in undocumented))


class TestDocsOnlyNotConfirmed(unittest.TestCase):
    """A docs/comments-only match does not produce confirmed."""

    def test_docs_only_match_is_needs_input(self):
        with tempfile.TemporaryDirectory() as d:
            adr = _write(
                Path(d) / "adr-0001.md",
                "---\nimplementation: shipped\n---\n\n# Use SQLite\n\nWe use SQLite.\n",
            )
            # Match only in a .md file, not in source.
            _write(Path(d) / "src" / "notes.md", "We use SQLite here.\n")
            _write(Path(d) / "src" / "app.py", "# no sqlite references\n")
            rc, out, _ = _run_cli(
                "--adrs", str(adr), "--source-root", str(Path(d) / "src"), "--mode", "report"
            )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data[0]["bucket"], "needs_input")
        self.assertNotEqual(data[0]["bucket"], "confirmed")


class TestSourceMatchConfirmed(unittest.TestCase):
    """shipped + source evidence -> confirmed."""

    def test_source_match_is_confirmed(self):
        with tempfile.TemporaryDirectory() as d:
            adr = _write(
                Path(d) / "adr-0001.md",
                "---\nimplementation: shipped\n---\n\n# Use SQLite\n\nWe use SQLite.\n",
            )
            _write(Path(d) / "src" / "app.py", "import sqlite3\n# Use SQLite\n")
            rc, out, _ = _run_cli(
                "--adrs", str(adr), "--source-root", str(Path(d) / "src"), "--mode", "report"
            )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data[0]["bucket"], "confirmed")


class TestConceptualNoCode(unittest.TestCase):
    """conceptual ADR -> not_applicable (no evidence search needed)."""

    def test_conceptual_is_not_applicable(self):
        with tempfile.TemporaryDirectory() as d:
            adr = _write(
                Path(d) / "adr-0001.md",
                "---\nimplementation: conceptual\n---\n\n# Architecture Vision\n\nIdea.\n",
            )
            _write(Path(d) / "src" / "app.py", "# Architecture Vision\n")
            rc, out, _ = _run_cli(
                "--adrs", str(adr), "--source-root", str(Path(d) / "src"), "--mode", "report"
            )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data[0]["bucket"], "not_applicable")


class TestJsonOutput(unittest.TestCase):
    """CLI emits valid JSON with required fields."""

    def test_json_has_required_fields(self):
        with tempfile.TemporaryDirectory() as d:
            adr = _write(
                Path(d) / "adr-0001.md",
                "---\nimplementation: shipped\n---\n\n# Use SQLite\n\nWe use SQLite.\n",
            )
            _write(Path(d) / "src" / "app.py", "import sqlite3\n")
            rc, out, _ = _run_cli(
                "--adrs", str(adr), "--source-root", str(Path(d) / "src"), "--mode", "report"
            )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(len(data), 1)
        entry = data[0]
        for field in ("id", "title", "status", "implementation", "load_bearing", "bucket", "evidence", "reason"):
            self.assertIn(field, entry)
        self.assertIn("source", entry["evidence"])
        self.assertIn("docs", entry["evidence"])

    def test_report_and_file_writes_to_out(self):
        with tempfile.TemporaryDirectory() as d:
            adr = _write(
                Path(d) / "adr-0001.md",
                "---\nimplementation: planned\n---\n\n# Use SQLite\n\nPlanned.\n",
            )
            out_path = Path(d) / "report.json"
            rc, _, _ = _run_cli(
                "--adrs", str(adr),
                "--source-root", str(Path(d)),
                "--mode", "report-and-file",
                "--out", str(out_path),
            )
            self.assertEqual(rc, 0)
            data = json.loads(out_path.read_text())
            self.assertEqual(data[0]["bucket"], "expected_gap")


class TestFrontmatterDefaults(unittest.TestCase):
    """parse_adr extracts frontmatter and applies defaults."""

    def test_no_frontmatter_uses_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            adr = _write(Path(d) / "adr-0001.md", "# Use SQLite\n\nBody text.\n")
            result = adr_drift.parse_adr(adr)
        self.assertEqual(result["id"], "adr-0001")
        self.assertEqual(result["title"], "Use SQLite")
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["implementation"], "unknown")
        self.assertEqual(result["load_bearing"], "unknown")
        self.assertEqual(result["forbidden_terms"], [])

    def test_frontmatter_fields_parsed(self):
        with tempfile.TemporaryDirectory() as d:
            adr = _write(
                Path(d) / "adr-0002.md",
                "---\nstatus: accepted\nimplementation: shipped\nload_bearing: true\n"
                "supersedes: ADR-0001\nsuperseded_by: ADR-0007\nforbidden_terms: mysql, postgres\n---\n\n"
                "# Use SQLite\n\nBody.\n",
            )
            result = adr_drift.parse_adr(adr)
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["implementation"], "shipped")
        self.assertEqual(result["load_bearing"], "true")
        self.assertEqual(result["supersedes"], "ADR-0001")
        self.assertEqual(result["superseded_by"], "ADR-0007")
        self.assertEqual(result["forbidden_terms"], ["mysql", "postgres"])
        self.assertEqual(result["title"], "Use SQLite")

    def test_forbidden_body_section(self):
        with tempfile.TemporaryDirectory() as d:
            adr = _write(
                Path(d) / "adr-0003.md",
                "# No ORM\n\nSome context.\n\nForbidden: sqlalchemy, peewee\n",
            )
            result = adr_drift.parse_adr(adr)
        self.assertEqual(result["forbidden_terms"], ["sqlalchemy", "peewee"])


if __name__ == "__main__":
    unittest.main()
