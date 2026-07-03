#!/usr/bin/env python3
"""Run deterministic read-only Killhouse contract scenarios."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def read_repo_file(path: str) -> str:
    target = (ROOT / path).resolve()
    if ROOT not in target.parents and target != ROOT:
        raise ValueError(f"path escapes repository: {path}")
    return target.read_text()


def run_check(check: dict) -> str | None:
    text = read_repo_file(check["path"])
    expected = check["text"]
    check_type = check["type"]
    if check_type == "contains" and expected not in text:
        return f"{check['path']} missing {expected!r}"
    if check_type == "not_contains" and expected in text:
        return f"{check['path']} contains forbidden {expected!r}"
    if check_type not in {"contains", "not_contains"}:
        return f"unknown check type {check_type!r}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only Killhouse eval scenarios.")
    parser.add_argument("scenario_file", type=Path)
    parser.add_argument("--group", default="all", help="scenario group to run, or all")
    args = parser.parse_args()

    data = load(args.scenario_file)
    scenarios = data.get("scenarios", [])
    failures: list[str] = []
    selected = 0
    for scenario in scenarios:
        if args.group != "all" and scenario.get("group") != args.group:
            continue
        selected += 1
        for check in scenario.get("checks", []):
            failure = run_check(check)
            if failure:
                failures.append(f"{scenario['id']}: {failure}")

    if selected == 0:
        print(f"[fail] no scenarios selected for group {args.group!r}", file=sys.stderr)
        return 1
    if failures:
        for failure in failures:
            print(f"[fail] {failure}", file=sys.stderr)
        return 1
    print(f"[ok] {selected} scenario(s) passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
