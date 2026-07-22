#!/usr/bin/env python3
"""Mechanical ADR/code drift audit helper.

Parses ADR frontmatter, classifies into evidence buckets, separates source from
docs evidence, detects drift, runs an advisory reverse scan, and emits JSON.

Stdlib-only. Deterministic for the same tree + inputs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

_EXECUTABLE_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb", ".sh"}
_DOCS_EXTS = {".md", ".txt", ".rst"}


def _read_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (frontmatter_dict, body). Unsupported shapes -> empty frontmatter."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    fm: dict[str, str] = {}
    end_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
        if ":" not in lines[i]:
            # Unsupported shape (not a simple key: value line) -> no frontmatter.
            return {}, text
        key, _, value = lines[i].partition(":")
        fm[key.strip()] = value.strip()
    if end_idx == -1:
        # Unterminated frontmatter block -> treat as no frontmatter.
        return {}, text
    body = "\n".join(lines[end_idx + 1 :])
    return fm, body


def _extract_forbidden_terms(fm: dict[str, str], body: str) -> list[str]:
    """Forbidden terms from frontmatter value or a 'Forbidden:' body section."""
    if "forbidden_terms" in fm:
        return [t.strip() for t in fm["forbidden_terms"].split(",") if t.strip()]
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("forbidden:"):
            rest = stripped[len("forbidden:") :]
            return [t.strip() for t in rest.split(",") if t.strip()]
    return []


def parse_adr(path: Path) -> dict[str, Any]:
    """Parse a markdown ADR. Extract optional ---delimited frontmatter."""
    text = path.read_text()
    fm, body = _read_frontmatter(text)
    title = ""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            break
    return {
        "id": path.stem,
        "title": title,
        "status": fm.get("status", "accepted"),
        "implementation": fm.get("implementation", "unknown"),
        "load_bearing": fm.get("load_bearing", "unknown"),
        "supersedes": fm.get("supersedes", ""),
        "superseded_by": fm.get("superseded_by", ""),
        "forbidden_terms": _extract_forbidden_terms(fm, body),
        "load_bearing_patterns": fm.get("load_bearing_patterns", ""),
        "body": body,
    }


def _is_executable_source(path: Path) -> bool:
    return path.suffix in _EXECUTABLE_EXTS


def _is_docs(path: Path) -> bool:
    return path.suffix in _DOCS_EXTS


def _search_needles(adr: dict[str, Any], context_docs: list[str]) -> list[str]:
    """Build search needles from ADR title/terms + context-doc bridging terms."""
    needles: list[str] = []
    if adr.get("title"):
        needles.append(adr["title"])
    needles.extend(adr.get("forbidden_terms", []))
    for doc_path in context_docs:
        p = Path(doc_path)
        if p.exists():
            for line in p.read_text().splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    needles.append(stripped)
    # Deduplicate, preserve order.
    seen: set[str] = set()
    unique: list[str] = []
    for n in needles:
        if n and n not in seen:
            seen.add(n)
            unique.append(n)
    return unique


def search_evidence(
    adr: dict[str, Any], source_root: Path, context_docs: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (source_evidence, docs_evidence).

    Source = matches in executable files. Docs = matches in .md/.txt.
    """
    source_evidence: list[dict[str, Any]] = []
    docs_evidence: list[dict[str, Any]] = []
    needles = _search_needles(adr, context_docs)
    if not source_root.exists():
        return source_evidence, docs_evidence
    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for needle in needles:
            if needle and needle in text:
                entry = {"file": str(path), "needle": needle}
                if _is_executable_source(path):
                    source_evidence.append(entry)
                elif _is_docs(path):
                    docs_evidence.append(entry)
    return source_evidence, docs_evidence


def classify(
    adr: dict[str, Any],
    source_evidence: list[dict[str, Any]],
    docs_evidence: list[dict[str, Any]],
) -> str:
    """Return the evidence bucket for an ADR."""
    impl = adr.get("implementation", "unknown")
    if impl == "conceptual":
        return "not_applicable"
    if impl == "planned":
        if not source_evidence:
            return "expected_gap"
        return "confirmed"
    # shipped / partial / unknown
    # Drift: shipped + load_bearing: true + forbidden term found in source.
    if (
        impl == "shipped"
        and adr.get("load_bearing", "unknown") == "true"
        and adr.get("forbidden_terms")
        and _forbidden_in_source(adr, source_evidence)
    ):
        return "drift"
    if source_evidence:
        return "confirmed"
    return "needs_input"


def _forbidden_in_source(adr: dict[str, Any], source_evidence: list[dict[str, Any]]) -> bool:
    """True if any forbidden term appears in source evidence needles."""
    forbidden = set(adr.get("forbidden_terms", []))
    for entry in source_evidence:
        if entry.get("needle") in forbidden:
            return True
    return False


def reverse_scan(
    source_root: Path, adrs: list[dict[str, Any]], context_docs: list[str]
) -> list[dict[str, Any]]:
    """Return undocumented candidates. Advisory only (non-blocking in v1).

    Scans source for load-bearing patterns (from context-docs or
    load_bearing_patterns frontmatter) with no covering ADR.
    """
    if not source_root.exists():
        return []
    # Collect load-bearing patterns to scan for.
    patterns: list[str] = []
    for doc_path in context_docs:
        p = Path(doc_path)
        if p.exists():
            for line in p.read_text().splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    patterns.append(stripped)
    for adr in adrs:
        fm_patterns = adr.get("load_bearing_patterns", "")
        if fm_patterns:
            patterns.extend(t.strip() for t in fm_patterns.split(",") if t.strip())
    # Deduplicate.
    seen: set[str] = set()
    unique_patterns: list[str] = []
    for pat in patterns:
        if pat and pat not in seen:
            seen.add(pat)
            unique_patterns.append(pat)
    # Patterns covered by an ADR (by title or forbidden terms) are not undocumented.
    covered: set[str] = set()
    for adr in adrs:
        if adr.get("title"):
            covered.add(adr["title"])
        covered.update(adr.get("forbidden_terms", []))
    findings: list[dict[str, Any]] = []
    for path in sorted(source_root.rglob("*")):
        if not path.is_file() or not _is_executable_source(path):
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in unique_patterns:
            if pattern in covered:
                continue
            if pattern in text:
                findings.append(
                    {
                        "id": f"undocumented-{path.stem}-{pattern}",
                        "title": pattern,
                        "bucket": "undocumented",
                        "evidence": {"source": [{"file": str(path), "needle": pattern}], "docs": []},
                        "reason": f"load-bearing pattern '{pattern}' in source with no covering ADR (advisory)",
                    }
                )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR/code drift audit helper")
    parser.add_argument("--adrs", required=True, help="Path or glob to ADR file(s)")
    parser.add_argument("--source-root", required=True, help="Source tree root")
    parser.add_argument("--context-docs", nargs="*", default=[], help="Context doc paths")
    parser.add_argument("--mode", choices=["report", "report-and-file"], default="report")
    parser.add_argument("--out", help="Output path for report-and-file mode")
    args = parser.parse_args()

    adr_paths = sorted(Path().glob(args.adrs)) if "*" in args.adrs else [Path(args.adrs)]
    adr_paths = [p for p in adr_paths if p.exists()]
    source_root = Path(args.source_root)

    results: list[dict[str, Any]] = []
    parsed_adrs: list[dict[str, Any]] = []
    for adr_path in adr_paths:
        adr = parse_adr(adr_path)
        parsed_adrs.append(adr)
        source_ev, docs_ev = search_evidence(adr, source_root, args.context_docs)
        bucket = classify(adr, source_ev, docs_ev)
        results.append(
            {
                "id": adr["id"],
                "title": adr["title"],
                "status": adr["status"],
                "implementation": adr["implementation"],
                "load_bearing": adr["load_bearing"],
                "bucket": bucket,
                "evidence": {"source": source_ev, "docs": docs_ev},
                "reason": _reason(adr, bucket, source_ev, docs_ev),
            }
        )

    # Advisory reverse scan: undocumented load-bearing patterns (non-blocking in v1).
    results.extend(reverse_scan(source_root, parsed_adrs, args.context_docs))

    output = json.dumps(results, indent=2)
    if args.mode == "report-and-file":
        if not args.out:
            print("error: --out required for report-and-file mode", file=sys.stderr)
            return 1
        Path(args.out).write_text(output)
    else:
        print(output)
    return 0


def _reason(
    adr: dict[str, Any],
    bucket: str,
    source_ev: list[dict[str, Any]],
    docs_ev: list[dict[str, Any]],
) -> str:
    impl = adr.get("implementation", "unknown")
    if bucket == "not_applicable":
        return "conceptual ADR: no code expected"
    if bucket == "expected_gap":
        return "planned ADR with no source evidence: absence is expected"
    if bucket == "confirmed":
        return f"{impl} ADR with source evidence found"
    if bucket == "needs_input":
        return f"{impl} ADR with no source evidence: needs input"
    return bucket


if __name__ == "__main__":
    sys.exit(main())
