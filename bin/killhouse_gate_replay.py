#!/usr/bin/env python3
"""Gate-replay harness: the offline "guessed-too-high" test for routing calibration.

This is a standalone program, NOT a Killhouse run behavior. It loads one logged delegation
(see loops/DELEGATION_LOG.md), re-executes it on a specified LOWER capability tier, and runs the
SAME logged gate against the cheaper output. It records PASS/FAIL from the real gate's exit code.

Hard rules this harness embodies:
  * The gate is ALWAYS the real logged command run in the logged cwd. There is no code path that
    substitutes a model's judgment of whether the cheaper output "looks fine" for running the gate.
  * Replay happens in a sandbox pinned to the delegation's recorded repository SHA.
  * If no model tier map resolves the lower tier (this repo defaults to current-model-only routing),
    the harness records SKIPPED_NO_ROUTING. It never fabricates a cheaper-tier result.

The LLM executor and the sandbox are injected dependencies so the harness's gate-running logic is
exercised in both directions by tests without a live model.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from collections.abc import Callable, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import killhouse_delegation_log as dl  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TIER_ORDER = {"fast": 0, "standard": 1, "reasoning": 2}

# An executor turns a prompt + model into candidate output by editing `workdir` in place.
Executor = Callable[[str, str, Path], None]
# A sandbox factory yields a working directory materialized at the delegation's pinned repo state.
SandboxFactory = Callable[[dict[str, Any]], "Any"]


@dataclass
class ReplayResult:
    delegation_id: str
    lower_tier: str
    chosen_tier: str
    model: str | None
    verdict: str  # PASS | FAIL | SKIPPED_NO_ROUTING | ERROR
    gate_command: str | None
    gate_cwd: str | None
    gate_exit: int | None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_routing(repo_root: Path) -> dict[str, Any]:
    """Resolve model routing the same order ask-kh does: local override, then project config."""
    for name in ("config.local.json", "config.json"):
        path = repo_root / ".killhouse" / name
        if path.is_file():
            return json.loads(path.read_text())
    return {}


def resolve_model(routing: dict[str, Any], tier: str) -> str | None:
    value = routing.get("model_tiers", {}).get(tier)
    return value if isinstance(value, str) and value.strip() else None


def load_record(log: Path | None, delegation_id: str | None, record_path: Path | None) -> dict[str, Any]:
    if record_path is not None:
        return json.loads(record_path.read_text())
    if log is None:
        raise ValueError("provide either a single record or a log")
    records = dl.load_records(log)
    if delegation_id is None:
        if len(records) != 1:
            raise ValueError("log has multiple records; pass --delegation-id to pick one")
        return records[0]
    matches = [r for r in records if r.get("delegation_id") == delegation_id]
    if not matches:
        raise ValueError(f"no delegation '{delegation_id}' in {log}")
    return matches[-1]


@contextmanager
def git_worktree_sandbox(record: dict[str, Any], repo_root: Path = ROOT) -> Iterator[Path]:
    """Materialize the delegation's pinned repo SHA into a throwaway git worktree."""
    head = _pinned_head(record)
    base = Path(tempfile.mkdtemp(prefix="kh-replay-"))
    worktree = base / "wt"  # git worktree add requires a path that does not yet exist
    try:
        subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "add", "--detach", str(worktree), head],
            check=True, capture_output=True, text=True,
        )
        yield worktree
    finally:
        subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "remove", "--force", str(worktree)],
            capture_output=True, text=True,
        )
        shutil.rmtree(base, ignore_errors=True)


def _pinned_head(record: dict[str, Any]) -> str:
    for art in record.get("upstream_artifacts", []):
        if art.get("kind") == "repository_state":
            head = art.get("pinned", {}).get("head")
            if isinstance(head, str) and head:
                return head
    raise ValueError("record has no pinned repository_state head")


def _safe_target(sandbox: Path, rel: str) -> Path:
    """Resolve `rel` under `sandbox`, refusing absolute paths or `..` escapes."""
    if os.path.isabs(rel):
        raise ValueError(f"artifact path must be sandbox-relative, got absolute: {rel!r}")
    target = (sandbox / rel).resolve()
    if not target.is_relative_to(sandbox.resolve()):
        raise ValueError(f"artifact path escapes the sandbox: {rel!r}")
    return target


def _materialize_pinned_artifacts(record: dict[str, Any], sandbox: Path) -> None:
    """Write any inlined pinned content (e.g. the pinned acceptance test) into the sandbox."""
    for art in record.get("upstream_artifacts", []):
        content = art.get("pinned_content")
        path = art.get("path")
        if isinstance(content, str) and isinstance(path, str):
            target = _safe_target(sandbox, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)


def _resolve_cwd(sandbox: Path, gate_cwd: str) -> Path:
    if gate_cwd in ("REPO_ROOT", ".", ""):
        return sandbox
    if os.path.isabs(gate_cwd):
        # An absolute cwd from the original checkout cannot be faithfully remapped to the sandbox
        # (its subdirectory component would be silently lost). Fail loud rather than mis-measure.
        raise ValueError(
            f"gate.cwd is absolute ({gate_cwd!r}); re-log it relative to the repo root (e.g. REPO_ROOT)"
        )
    return _safe_target(sandbox, gate_cwd)


def command_executor(template: str) -> Executor:
    """Build an executor from a shell template with {model}, {workdir}, {prompt_file} placeholders."""
    def run(prompt: str, model: str, workdir: Path) -> None:
        # Keep the prompt file OUTSIDE the sandbox so clean-tree gates don't see spurious files.
        fd, prompt_file = tempfile.mkstemp(prefix="kh-replay-prompt-", suffix=".txt")
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(prompt)
            command = template.format(model=model, workdir=str(workdir), prompt_file=prompt_file)
            subprocess.run(command, shell=True, cwd=str(workdir), check=True)
        finally:
            os.unlink(prompt_file)
    return run


def _result(record: dict[str, Any], lower_tier: str, verdict: str, **kw: Any) -> ReplayResult:
    gate = record.get("gate", {})
    return ReplayResult(
        delegation_id=record.get("delegation_id", "<unknown>"),
        lower_tier=lower_tier,
        chosen_tier=record.get("chosen_tier", "<unknown>"),
        model=kw.get("model"),
        verdict=verdict,
        gate_command=gate.get("command"),
        gate_cwd=gate.get("cwd"),
        gate_exit=kw.get("gate_exit"),
        reason=kw.get("reason"),
    )


def replay(
    record: dict[str, Any],
    lower_tier: str,
    *,
    repo_root: Path = ROOT,
    routing: dict[str, Any] | None = None,
    executor: Executor | None = None,
    sandbox_factory: SandboxFactory | None = None,
) -> ReplayResult:
    """Replay one delegation on a lower tier and score it with the real logged gate."""
    errors = dl.validate_record(record)
    if errors:
        return _result(record, lower_tier, "ERROR", reason=f"record fails schema: {errors[0]}")

    chosen = record["chosen_tier"]
    if lower_tier not in TIER_ORDER:
        return _result(record, lower_tier, "ERROR", reason=f"unknown tier '{lower_tier}'")
    if TIER_ORDER[lower_tier] >= TIER_ORDER.get(chosen, 99):
        return _result(record, lower_tier, "ERROR",
                       reason=f"'{lower_tier}' is not lower than chosen tier '{chosen}'")

    routing = routing if routing is not None else load_routing(repo_root)
    model = resolve_model(routing, lower_tier)
    if model is None:
        return _result(record, lower_tier, "SKIPPED_NO_ROUTING",
                       reason=f"no model_tiers.{lower_tier} configured; refusing to fake a cheaper-tier run")

    if executor is None:
        template = os.environ.get("KILLHOUSE_REPLAY_EXECUTOR") or routing.get("replay_executor")
        if not template:
            return _result(record, lower_tier, "SKIPPED_NO_ROUTING", model=model,
                           reason="no replay_executor configured; cannot invoke the cheaper tier")
        executor = command_executor(template)

    factory = sandbox_factory if sandbox_factory is not None else (
        lambda rec: git_worktree_sandbox(rec, repo_root)
    )
    gate = record["gate"]
    try:
        with factory(record) as sandbox:
            sandbox = Path(sandbox)
            _materialize_pinned_artifacts(record, sandbox)
            try:
                executor(record["resolved_prompt"], model, sandbox)
            except subprocess.CalledProcessError as exc:
                return _result(record, lower_tier, "ERROR", model=model,
                               reason=f"executor failed with exit {exc.returncode}")
            proc = subprocess.run(
                gate["command"], shell=True, cwd=str(_resolve_cwd(sandbox, gate["cwd"])),
                capture_output=True, text=True,
            )
    except Exception as exc:  # sandbox/gate infrastructure failure, not a gate result
        return _result(record, lower_tier, "ERROR", model=model, reason=f"replay error: {exc}")

    verdict = "PASS" if proc.returncode == 0 else "FAIL"
    return _result(record, lower_tier, verdict, model=model, gate_exit=proc.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay a logged delegation on a lower tier against its real gate."
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--log", type=Path, help="JSONL delegation log")
    src.add_argument("--record", type=Path, help="single delegation record JSON")
    parser.add_argument("--delegation-id", help="which delegation in --log to replay")
    parser.add_argument("--lower-tier", required=True, choices=list(TIER_ORDER), help="tier to replay on")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--executor", help="shell template with {model} {workdir} {prompt_file}")
    args = parser.parse_args(argv)

    try:
        record = load_record(args.log, args.delegation_id, args.record)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        return 2

    executor = command_executor(args.executor) if args.executor else None
    result = replay(record, args.lower_tier, repo_root=args.repo_root, executor=executor)
    print(json.dumps(result.to_dict(), indent=2))
    # A produced measurement (PASS/FAIL/SKIPPED) exits 0; only an inability to run is a program error.
    return 2 if result.verdict == "ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
