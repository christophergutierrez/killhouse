#!/usr/bin/env python3
"""Validate Killhouse delegation-log records against the record schema.

Killhouse logs one JSONL record per subagent delegation (see loops/DELEGATION_LOG.md).
This module is the single enforcement point for that schema: it is imported by the
self-hosting validator, by the gate-replay harness, and exercised directly by tests.

It intentionally depends only on the standard library. It interprets the subset of
JSON Schema (draft 2020-12) keywords used by schemas/delegation_record.schema.json --
type, required, properties, items, contains, enum, const, minLength, minItems, and a
single if/then -- so the schema file stays the one source of truth and cannot silently
drift from the checker.

CLI:
    killhouse_delegation_log.py --validate LOG.jsonl   # exit 0 if every record valid, 1 otherwise
    killhouse_delegation_log.py --schema-path          # print the schema path
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "delegation_record.schema.json"

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    # bool is a subclass of int in Python; exclude it from number/integer.
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
}


def load_schema() -> dict[str, Any]:
    """Load the delegation-record schema."""
    return json.loads(SCHEMA_PATH.read_text())


def _matches(instance: Any, schema: dict[str, Any]) -> bool:
    return not _errors(instance, schema, "")


def _errors(instance: Any, schema: dict[str, Any], path: str) -> list[str]:
    """Return schema-violation messages for `instance`, empty if it conforms."""
    out: list[str] = []
    here = path or "<root>"

    expected_type = schema.get("type")
    if expected_type is not None:
        check = _TYPE_CHECKS.get(expected_type)
        if check is None:
            out.append(f"{here}: schema uses unsupported type {expected_type!r}")
            return out
        if not check(instance):
            out.append(f"{here}: expected {expected_type}, got {type(instance).__name__}")
            return out

    if "const" in schema and instance != schema["const"]:
        out.append(f"{here}: expected const {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        out.append(f"{here}: {instance!r} not in enum {schema['enum']!r}")
    if "minLength" in schema and isinstance(instance, str) and len(instance) < schema["minLength"]:
        out.append(f"{here}: string shorter than minLength {schema['minLength']}")
    if "minItems" in schema and isinstance(instance, list) and len(instance) < schema["minItems"]:
        out.append(f"{here}: fewer than minItems {schema['minItems']} items")

    if isinstance(instance, dict):
        for field in schema.get("required", []):
            if field not in instance:
                out.append(f"{here}: missing required field '{field}'")
        for key, subschema in schema.get("properties", {}).items():
            if key in instance:
                out.extend(_errors(instance[key], subschema, f"{path}.{key}" if path else key))

    if isinstance(instance, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(instance):
                out.extend(_errors(item, item_schema, f"{path}[{i}]"))
        contains = schema.get("contains")
        if isinstance(contains, dict) and not any(_matches(item, contains) for item in instance):
            out.append(f"{here}: no array item satisfies `contains` constraint")

    if_schema = schema.get("if")
    if isinstance(if_schema, dict) and _matches(instance, if_schema):
        then_schema = schema.get("then")
        if isinstance(then_schema, dict):
            out.extend(_errors(instance, then_schema, path))

    return out


def validate_record(record: Any, schema: dict[str, Any] | None = None) -> list[str]:
    """Return the list of schema violations for one record (empty means valid)."""
    return _errors(record, schema if schema is not None else load_schema(), "")


def load_records(log_path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL delegation log into records, skipping blank lines."""
    records: list[dict[str, Any]] = []
    for lineno, line in enumerate(log_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{log_path}:{lineno}: invalid JSON: {exc}") from exc
    return records


def validate_log(log_path: Path) -> list[tuple[int, list[str]]]:
    """Validate every record in a JSONL log. Returns (record_index, errors) for each."""
    schema = load_schema()
    return [(i, validate_record(rec, schema)) for i, rec in enumerate(load_records(log_path))]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Killhouse delegation-log records.")
    parser.add_argument("--validate", metavar="LOG.jsonl", help="validate every record in a JSONL log")
    parser.add_argument("--schema-path", action="store_true", help="print the record schema path")
    args = parser.parse_args(argv)

    if args.schema_path:
        print(SCHEMA_PATH)
        return 0

    if not args.validate:
        parser.error("nothing to do: pass --validate LOG.jsonl or --schema-path")

    log_path = Path(args.validate)
    if not log_path.is_file():
        print(f"[fail] no such log: {log_path}", file=sys.stderr)
        return 1

    results = validate_log(log_path)
    if not results:
        print(f"[fail] {log_path} has no records", file=sys.stderr)
        return 1

    ok = True
    for index, errors in results:
        if errors:
            ok = False
            for err in errors:
                print(f"[fail] record {index}: {err}", file=sys.stderr)
        else:
            print(f"[ok] record {index}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
