#!/usr/bin/env python3
"""Bump Killhouse plugin versions across all runtime manifests."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+][0-9A-Za-z.-]+)?$")
CORE_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

MANIFEST_PATHS = [
    "plugin.json",
    ".codex-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
]


def read_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


def write_json(path: str, data: dict) -> None:
    (ROOT / path).write_text(json.dumps(data, indent=2) + "\n")


def manifest_versions() -> dict[str, str]:
    claude = read_json("plugin.json")
    codex = read_json(".codex-plugin/plugin.json")
    marketplace = read_json(".claude-plugin/marketplace.json")
    plugin = next((item for item in marketplace["plugins"] if item.get("name") == "killhouse"), None)
    if plugin is None:
        raise SystemExit("marketplace manifest has no killhouse plugin entry")
    return {
        "plugin.json": claude["version"],
        ".codex-plugin/plugin.json": codex["version"],
        ".claude-plugin/marketplace.json": plugin["version"],
    }


def require_consistent_current() -> str:
    versions = manifest_versions()
    unique = set(versions.values())
    if len(unique) != 1:
        formatted = ", ".join(f"{path}={version}" for path, version in versions.items())
        raise SystemExit(f"manifest versions differ: {formatted}")
    current = unique.pop()
    if not SEMVER.match(current):
        raise SystemExit(f"current version is not semver-like: {current}")
    return current


def increment(version: str, part: str) -> str:
    match = CORE_SEMVER.match(version)
    if match is None:
        raise SystemExit(f"cannot auto-increment non-core semver version: {version}")
    major, minor, patch = map(int, match.groups())
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise SystemExit(f"unknown increment part: {part}")


def set_version(version: str) -> None:
    if not SEMVER.match(version):
        raise SystemExit(f"target version is not semver-like: {version}")

    claude = read_json("plugin.json")
    claude["version"] = version
    write_json("plugin.json", claude)

    codex = read_json(".codex-plugin/plugin.json")
    codex["version"] = version
    write_json(".codex-plugin/plugin.json", codex)

    marketplace = read_json(".claude-plugin/marketplace.json")
    updated = False
    for plugin in marketplace["plugins"]:
        if plugin.get("name") == "killhouse":
            plugin["version"] = version
            updated = True
    if not updated:
        raise SystemExit("marketplace manifest has no killhouse plugin entry")
    write_json(".claude-plugin/marketplace.json", marketplace)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bump Killhouse plugin manifest versions.")
    parser.add_argument("version", nargs="?", help="exact semver version to set, e.g. 0.1.1")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--major", action="store_true", help="increment major version")
    group.add_argument("--minor", action="store_true", help="increment minor version")
    group.add_argument("--patch", action="store_true", help="increment patch version")
    args = parser.parse_args()

    increments = [name for name in ("major", "minor", "patch") if getattr(args, name)]
    if args.version and increments:
        parser.error("provide either an exact version or one increment flag, not both")

    current = require_consistent_current()
    if args.version:
        target = args.version
    elif increments:
        target = increment(current, increments[0])
    else:
        parser.error("provide an exact version or --major/--minor/--patch")

    set_version(target)
    print(f"plugin version: {current} -> {target}")
    for path in MANIFEST_PATHS:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
