#!/usr/bin/env python3
"""Zero-intelligence conductor: executes a killhouse delegation plan (dumb driver).

The conductor walks the delegation DAG, dispatches each delegation to its planned
tier via the configured executor, runs the real logged gate, escalates on failure,
and writes schema-valid delegation records mechanically at the boundary.

This module is the single enforcement point for conductor plan schema validation:
imported by tests and exercised directly via CLI.

It intentionally depends only on the standard library. It interprets the subset of
JSON Schema (draft 2020-12) keywords used by schemas/conductor_plan.schema.json --
type, required, properties, items, contains, enum, const, minLength, minItems,
and a single if/then -- so the schema file stays the one source of truth.

CLI:
    killhouse_conduct.py --validate PLAN.json   # exit 0 if plan valid, 1 otherwise
    killhouse_conduct.py --dry-run PLAN.json    # print execution order, no subprocess calls
    killhouse_conduct.py --run PLAN.json        # execute end-to-end; exit 2 if unroutable
    killhouse_conduct.py --schema-path          # print the schema path
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from collections.abc import Callable, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import killhouse_delegation_log as dl  # noqa: E402
import killhouse_gate_replay as gr  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PLAN_SCHEMA_PATH = ROOT / "schemas" / "conductor_plan.schema.json"

# Escalation ladder in rank order, derived from the gate-replay tier map so this module
# never carries a second copy of tier ordering that could drift from killhouse_gate_replay.
TIER_LADDER = sorted(gr.TIER_ORDER, key=lambda t: gr.TIER_ORDER[t])


def load_plan_schema() -> dict[str, Any]:
    """Load the conductor-plan schema."""
    return json.loads(PLAN_SCHEMA_PATH.read_text())


def load_plan(path: Path | str) -> dict[str, Any]:
    """Load a conductor plan from a JSON file."""
    plan_path = Path(path)
    return json.loads(plan_path.read_text())


def validate_plan(plan: Any, schema: dict[str, Any] | None = None) -> list[str]:
    """Return the list of schema violations for a plan (empty means valid).

    Includes both schema validation and semantic checks:
    - duplicate delegation_id values
    - depends_on referencing an id not in the plan
    """
    if schema is None:
        schema = load_plan_schema()
    return dl._errors(plan, schema, "") + _semantic_errors(plan)


def _semantic_errors(plan: Any) -> list[str]:
    """Validate plan semantics that JSON Schema cannot express."""
    if not isinstance(plan, dict):
        return []

    out: list[str] = []
    delegations = plan.get("delegations")
    if not isinstance(delegations, list):
        return out

    delegation_ids: set[str] = set()
    duplicates: set[str] = set()
    for delegation in delegations:
        if not isinstance(delegation, dict):
            continue
        did = delegation.get("delegation_id")
        if isinstance(did, str):
            if did in delegation_ids:
                duplicates.add(did)
            delegation_ids.add(did)
    for dup_id in sorted(duplicates):
        out.append(f"duplicate delegation_id '{dup_id}'")

    for delegation in delegations:
        if not isinstance(delegation, dict):
            continue
        depends_on = delegation.get("depends_on")
        if not isinstance(depends_on, list):
            continue
        for dep_id in depends_on:
            if isinstance(dep_id, str) and dep_id not in delegation_ids:
                out.append(f"unknown dependency '{dep_id}'")

    try:
        topo_order(plan)
    except ValueError as exc:
        out.append(str(exc))

    return out


def topo_order(plan: dict) -> list[dict]:
    """Return delegations in topological order respecting depends_on.

    Among nodes whose dependencies are satisfied, preserves plan order
    (Kahn's algorithm with plan order as tiebreaker).

    Raises ValueError if a cycle is detected.
    """
    delegations = plan.get("delegations", [])
    if not isinstance(delegations, list):
        return []

    delegation_map: dict[str, dict[str, Any]] = {}
    delegation_ids: list[str] = []
    for delegation in delegations:
        if isinstance(delegation, dict):
            did = delegation.get("delegation_id")
            if isinstance(did, str):
                delegation_map[did] = delegation
                delegation_ids.append(did)

    id_set = set(delegation_ids)
    in_degree = {did: 0 for did in delegation_ids}
    adj: dict[str, list[str]] = {did: [] for did in delegation_ids}

    for delegation in delegations:
        if not isinstance(delegation, dict):
            continue
        did = delegation.get("delegation_id")
        if not isinstance(did, str):
            continue
        depends_on = delegation.get("depends_on")
        if not isinstance(depends_on, list):
            continue
        for dep_id in depends_on:
            if isinstance(dep_id, str) and dep_id in id_set:
                adj[dep_id].append(did)
                in_degree[did] += 1

    queue = [did for did in delegation_ids if in_degree[did] == 0]
    result: list[dict[str, Any]] = []
    while queue:
        current = queue.pop(0)
        result.append(delegation_map[current])

        for neighbor in adj[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) < len(delegation_ids):
        stuck = sorted(did for did in delegation_ids if in_degree[did] > 0)
        raise ValueError(f"cycle detected involving: {', '.join(stuck)}")

    return result


def dry_run(plan: dict) -> list[dict]:
    """Return a dry-run summary in execution order.

    Returns a list of dicts with delegation_id, planned_tier, and
    plan_position fields in topological order. Performs no I/O or
    subprocess calls.
    """
    ordered = topo_order(plan)
    result = []
    for delegation in ordered:
        result.append(
            {
                "delegation_id": delegation.get("delegation_id"),
                "planned_tier": delegation.get("planned_tier"),
                "plan_position": delegation.get("plan_position"),
            }
        )
    return result


@contextmanager
def branch_sandbox(repo_root: Path, branch: str) -> Iterator[Path]:
    """Materialize `branch`'s current tip into a throwaway git worktree.

    Resolves `branch` to a SHA up front (fail loud, naming the branch, if it does not
    resolve) then delegates worktree/clone mechanics to `gr.git_worktree_sandbox`.
    """
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", f"{branch}^{{commit}}"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise ValueError(f"branch '{branch}' does not resolve to a commit in {repo_root}")
    head = proc.stdout.strip()
    record = {"upstream_artifacts": [{"kind": "repository_state", "pinned": {"head": head}}]}
    with gr.git_worktree_sandbox(record, repo_root) as sandbox:
        yield sandbox


def default_log_path(repo_root: Path) -> Path:
    """Resolve the delegation log path: env override, else repo_root/.killhouse/delegations.jsonl."""
    env_path = os.environ.get("KILLHOUSE_DELEGATION_LOG")
    if env_path:
        return Path(env_path)
    return repo_root / ".killhouse" / "delegations.jsonl"


def _freeze_record(
    delegation: dict[str, Any], *, tier: str, model: str, repo_root: Path, target_branch: str
) -> dict[str, Any]:
    """Build the pre-execution half of a delegation record, before anything runs."""
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", f"{target_branch}^{{commit}}"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise ValueError(f"branch '{target_branch}' does not resolve to a commit in {repo_root}")
    head = proc.stdout.strip()

    actual_repo_state = {
        "kind": "repository_state",
        "pinned": {"vcs": "git", "head": head, "branch": target_branch, "dirty_files": []},
    }
    upstream_artifacts = [
        art for art in delegation.get("upstream_artifacts", []) if art.get("kind") != "repository_state"
    ]
    upstream_artifacts.insert(0, actual_repo_state)

    return {
        "delegation_id": delegation["delegation_id"],
        "plan_position": delegation["plan_position"],
        "depends_on": delegation.get("depends_on", []),
        "resolved_prompt": delegation["resolved_prompt"],
        "chosen_tier": tier,
        "chosen_model": model,
        "tier_price": {"currency": "USD-per-Mtok", "basis": "unpriced"},
        "decision_signals": {
            "source": "conductor:planned-tier",
            "task_tier": tier,
            "confidence": 1.0,
            "reasoning": "tier taken verbatim from the conductor plan",
        },
        "gate": delegation["gate"],
        "upstream_artifacts": upstream_artifacts,
    }


def _append_log(record: dict[str, Any], log_path: Path) -> None:
    """Append one record to the JSONL log. On I/O failure, note it on the record instead of raising."""
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a") as handle:
            handle.write(json.dumps(record) + "\n")
    except OSError as exc:
        record["_log_error"] = str(exc)


def run_delegation(
    delegation: dict[str, Any],
    *,
    repo_root: Path,
    target_branch: str,
    tier: str,
    model: str,
    executor: gr.Executor,
    log_path: Path,
    log: bool = True,
) -> tuple[dict[str, Any], str]:
    """Execute one delegation at one tier and return (finalized record, sandbox diff text).

    When `log` is False, the record is finalized but not appended to `log_path`; the
    caller (run_with_escalation) owns logging exactly one record per delegation, after
    possibly amending it with escalation fields.
    """
    record = _freeze_record(
        delegation, tier=tier, model=model, repo_root=repo_root, target_branch=target_branch
    )

    notes: str | None = None
    gate_exit: int | None = None
    # Sandbox from the frozen record itself, not a second branch resolution: the executed
    # tree must be the exact head the record pins, even if the branch moves mid-run.
    with gr.git_worktree_sandbox(record, repo_root) as sandbox:
        gr._materialize_pinned_artifacts(record, sandbox)
        try:
            executor(record["resolved_prompt"], model, sandbox)
        except subprocess.CalledProcessError as exc:
            notes = f"executor failed with exit {exc.returncode}"
        else:
            gate = record["gate"]
            proc = subprocess.run(
                gate["command"], shell=True, cwd=str(gr._resolve_cwd(sandbox, gate["cwd"])),
                capture_output=True, text=True,
            )
            gate_exit = proc.returncode

        subprocess.run(["git", "-C", str(sandbox), "add", "-A"], capture_output=True, text=True)
        diff_proc = subprocess.run(
            ["git", "-C", str(sandbox), "diff", "--cached", "--binary"],
            capture_output=True, text=True,
        )
        diff_text = diff_proc.stdout

    status = "pass" if gate_exit == 0 else "fail"
    outcome: dict[str, Any] = {"status": status, "escalated": False}
    if notes is not None:
        outcome["notes"] = notes
    record["outcome"] = outcome

    if log:
        _append_log(record, log_path)

    return record, diff_text


def run_with_escalation(
    delegation: dict[str, Any],
    *,
    repo_root: Path,
    target_branch: str,
    routing: dict[str, Any],
    executor_factory: Callable[[str], gr.Executor],
    log_path: Path,
) -> tuple[dict[str, Any], str | None]:
    """Run one delegation, escalating up TIER_LADDER on gate failure until it passes or runs out.

    Attempts start at `planned_tier` and retry at each higher rung, a fresh sandbox each
    time (run_delegation already guarantees that). Every attempt is run with log=False;
    only ONE record per delegation is ever appended to log_path -- the first attempt that
    passes (amended with escalation fields if it wasn't the planned tier), or the final
    attempt if every rung fails. Failed intermediate attempts are never logged individually;
    the winning/final record's outcome.notes / escalation_trigger carries their tier history.

    If the PLANNED tier has no routable model, nothing is executed or logged at all: returns
    a minimal fail record and diff=None (mirrors gate_replay's SKIPPED_NO_ROUTING -- refuse to
    fake a result the conductor cannot actually invoke).
    """
    planned_tier = delegation["planned_tier"]
    if planned_tier not in gr.TIER_ORDER:
        raise ValueError(f"unknown planned_tier '{planned_tier}'")

    planned_model = gr.resolve_model(routing, planned_tier)
    if planned_model is None:
        return {
            "delegation_id": delegation["delegation_id"],
            "outcome": {
                "status": "fail",
                "escalated": False,
                "notes": f"no model for planned tier '{planned_tier}'",
            },
        }, None

    rungs = TIER_LADDER[TIER_LADDER.index(planned_tier):]
    failed_tiers: list[str] = []
    last_record: dict[str, Any] | None = None
    last_diff = ""

    for tier in rungs:
        model = gr.resolve_model(routing, tier)
        if model is None:
            # Cannot invoke this rung; skip it rather than fabricate a result for it.
            continue

        executor = executor_factory(model)
        record, diff_text = run_delegation(
            delegation,
            repo_root=repo_root,
            target_branch=target_branch,
            tier=tier,
            model=model,
            executor=executor,
            log_path=log_path,
            log=False,
        )
        last_record, last_diff = record, diff_text

        if record["outcome"]["status"] == "pass":
            if failed_tiers:
                record["outcome"]["escalated"] = True
                record["outcome"]["escalation_magnitude"] = (
                    gr.TIER_ORDER[tier] - gr.TIER_ORDER[planned_tier]
                )
                record["outcome"]["escalation_trigger"] = (
                    "gate failed at tier(s): " + ", ".join(failed_tiers)
                )
            _append_log(record, log_path)
            return record, diff_text

        failed_tiers.append(tier)

    # Ladder exhausted. planned_model resolved, so the loop ran at least once.
    assert last_record is not None
    last_record["outcome"]["notes"] = "gate failed at all tried tiers: " + ", ".join(failed_tiers)
    _append_log(last_record, log_path)
    return last_record, last_diff


def _commit_diff(
    repo_root: Path, target_branch: str, diff_text: str, delegation_id: str, expected_head: str
) -> str:
    """Apply `diff_text` on top of `expected_head` and commit it back to `target_branch`.

    `expected_head` is the branch tip the delegation actually ran against -- the frozen
    record's pinned repository_state head -- not a value re-resolved at commit time. The
    apply+commit happens in a worktree pinned to that exact SHA; landing the result uses
    `git update-ref` with `expected_head` as the explicit old-value. If `target_branch` has
    moved since the delegation ran (another commit landed in between), update-ref fails
    loud (raises CalledProcessError) rather than silently rebuilding on top of, or
    discarding, that intervening state.
    """
    pin_record = {"upstream_artifacts": [{"kind": "repository_state", "pinned": {"head": expected_head}}]}
    with gr.git_worktree_sandbox(pin_record, repo_root) as worktree:
        subprocess.run(
            ["git", "-C", str(worktree), "apply", "--index"],
            input=diff_text, capture_output=True, text=True, check=True,
        )
        subprocess.run(
            [
                "git", "-C", str(worktree),
                "-c", "user.name=killhouse-conductor",
                "-c", "user.email=conductor@killhouse.local",
                "commit", "-m", f"conduct: {delegation_id}",
            ],
            capture_output=True, text=True, check=True,
        )
        new_sha = subprocess.run(
            ["git", "-C", str(worktree), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()

    subprocess.run(
        ["git", "-C", str(repo_root), "update-ref", f"refs/heads/{target_branch}", new_sha, expected_head],
        capture_output=True, text=True, check=True,
    )
    return new_sha


def conduct(
    plan: dict[str, Any],
    *,
    repo_root: Path,
    target_branch: str,
    routing: dict[str, Any],
    executor_factory: Callable[[str], gr.Executor],
    log_path: Path,
) -> dict[str, Any]:
    """Walk the plan in topo order: run+escalate each delegation, commit PASS diffs back.

    A delegation whose deps are not all PASS is BLOCKED: never executed, never logged.
    On PASS with a non-empty diff, commits it to `target_branch` via `_commit_diff`; if
    that commit-back itself fails (e.g. the update-ref race guard fires), the delegation's
    verdict is FAIL even though its gate passed -- gate success and successfully landing
    the diff are different failure modes. The record's outcome.status stays "pass" (the
    gate result is ground truth, already logged); the commit-back failure is reported in
    outcome.notes and the summary verdict only.
    """
    verdicts: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    commits: dict[str, str] = {}

    for delegation in topo_order(plan):
        did = delegation["delegation_id"]
        deps = delegation.get("depends_on", [])
        if any(verdicts.get(dep) != "PASS" for dep in deps):
            verdicts[did] = "BLOCKED"
            continue

        record, diff_text = run_with_escalation(
            delegation,
            repo_root=repo_root,
            target_branch=target_branch,
            routing=routing,
            executor_factory=executor_factory,
            log_path=log_path,
        )
        records.append(record)

        if record.get("outcome", {}).get("status") != "pass":
            verdicts[did] = "FAIL"
            continue

        if diff_text:
            expected_head = next(
                (
                    art["pinned"]["head"]
                    for art in record.get("upstream_artifacts", [])
                    if art.get("kind") == "repository_state"
                ),
                None,
            )
            try:
                if expected_head is None:
                    raise ValueError("record has no pinned repository_state head")
                commits[did] = _commit_diff(repo_root, target_branch, diff_text, did, expected_head)
            except (subprocess.CalledProcessError, ValueError) as exc:
                record["outcome"]["notes"] = f"commit-back failed: {exc}"
                verdicts[did] = "FAIL"
                continue
        verdicts[did] = "PASS"

    return {
        "plan_id": plan.get("plan_id"),
        "verdicts": verdicts,
        "records": records,
        "commits": commits,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and run Killhouse conductor plans.")
    parser.add_argument(
        "--validate", metavar="PLAN.json", help="validate a conductor plan JSON file"
    )
    parser.add_argument(
        "--dry-run", metavar="PLAN.json", help="dry-run a conductor plan (print execution order)"
    )
    parser.add_argument(
        "--run", metavar="PLAN.json", help="execute a conductor plan end-to-end"
    )
    parser.add_argument(
        "--target-branch",
        help="override the plan's target_branch (--run only; defaults to the plan's own field)",
    )
    parser.add_argument(
        "--executor", help="shell template with {model} {workdir} {prompt_file} (--run only)"
    )
    parser.add_argument(
        "--repo-root", type=Path, default=ROOT, help="repo to run against (--run only)"
    )
    parser.add_argument(
        "--schema-path", action="store_true", help="print the plan schema path"
    )
    args = parser.parse_args(argv)

    if args.schema_path:
        print(PLAN_SCHEMA_PATH)
        return 0

    modes = [m for m in (args.validate, args.dry_run, args.run) if m]
    if len(modes) > 1:
        parser.error("--validate, --dry-run, and --run are mutually exclusive")
    if not modes:
        parser.error("nothing to do: pass --validate PLAN.json, --dry-run PLAN.json, --run PLAN.json, "
                     "or --schema-path")

    plan_path_str = args.validate or args.dry_run or args.run
    plan_path = Path(plan_path_str)
    if not plan_path.is_file():
        print(f"[fail] no such plan: {plan_path}", file=sys.stderr)
        return 1

    try:
        plan = load_plan(plan_path)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[fail] invalid JSON in {plan_path}: {exc}", file=sys.stderr)
        return 1

    errors = validate_plan(plan)
    if errors:
        for err in errors:
            print(f"[fail] {err}", file=sys.stderr)
        return 1

    if args.validate:
        plan_id = plan.get("plan_id", "unknown")
        print(f"[ok] plan {plan_id}")
        return 0

    if args.dry_run:
        try:
            result = dry_run(plan)
            for i, entry in enumerate(result, 1):
                did = entry.get("delegation_id")
                tier = entry.get("planned_tier")
                pos = entry.get("plan_position")
                print(f"{i}. {did} [{tier}] {pos}")
            return 0
        except ValueError as exc:
            print(f"[fail] {exc}", file=sys.stderr)
            return 1

    # args.run
    repo_root = args.repo_root
    routing = gr.load_routing(repo_root)
    model_tiers = routing.get("model_tiers")
    if not isinstance(model_tiers, dict) or not model_tiers:
        print("[fail] no model_tiers configured; refusing to run", file=sys.stderr)
        return 2

    template = (
        args.executor
        or os.environ.get("KILLHOUSE_CONDUCT_EXECUTOR")
        or routing.get("conduct_executor")
    )
    if not template:
        print(
            "[fail] no executor configured: pass --executor, set KILLHOUSE_CONDUCT_EXECUTOR, "
            "or set conduct_executor in killhouse config",
            file=sys.stderr,
        )
        return 2

    def executor_factory(model: str) -> gr.Executor:
        return gr.command_executor(template)

    target_branch = args.target_branch or plan["target_branch"]
    try:
        summary = conduct(
            plan,
            repo_root=repo_root,
            target_branch=target_branch,
            routing=routing,
            executor_factory=executor_factory,
            log_path=default_log_path(repo_root),
        )
    except ValueError as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0 if all(v == "PASS" for v in summary["verdicts"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
