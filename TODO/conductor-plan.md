# Execution Plan: Deterministic Conductor (dumb driver)

## Goal

A zero-intelligence Python conductor (`bin/killhouse_conduct.py`) that executes a killhouse
delegation plan: walks the delegation DAG, dispatches each delegation to its planned tier via the
configured executor, runs the real logged gate, escalates up the tier ladder on failure, and writes
schema-valid delegation records mechanically at the boundary.

This converts the delegation-logging *protocol* (LLM-followed Markdown) into *enforcement* (code):
freeze/finalize becomes deterministic, escalation labels become ground truth by construction, and
tier routing becomes real (cheap slices actually run on cheap models).

## Design contract

**Inputs**
- A conductor plan: JSON, one entry per delegation. Fields mirror the delegation record's frozen
  half: `delegation_id`, `plan_position`, `depends_on`, `resolved_prompt`, `planned_tier`,
  `gate` (`command`, `cwd`, `pass_criteria`, `baseline_polarity`), `upstream_artifacts`.
  Schema: `schemas/conductor_plan.schema.json` (single source of truth, same interpreter subset
  as the delegation-record schema).
- killhouse config (`.killhouse/config.local.json` then `config.json`): `model_tiers`,
  `replay_executor` (shell template with `{model}` `{workdir}` `{prompt_file}` — same contract as
  the gate-replay harness).
- A target branch. Each delegation runs in a throwaway worktree at that branch's HEAD; on gate
  PASS the conductor commits the sandbox diff back to the target branch, so later delegations
  build on earlier ones.

**Execution semantics**
- Topological order over `depends_on`; cycle or unknown dep is a plan-validation error before
  anything runs.
- Per delegation: freeze record → sandbox at branch HEAD (reuse `git_worktree_sandbox`) →
  materialize pinned artifacts → executor(prompt, model, sandbox) → run the REAL gate in the
  logged cwd → finalize record with outcome → on PASS, commit diff to target branch.
- Escalation ladder: on gate FAIL at tier T, retry at the next tier up (`fast → standard →
  reasoning`), fresh sandbox each attempt. Record `escalated: true`, `escalation_magnitude`
  (tiers jumped from planned tier), `escalation_trigger` (the gate failure). Ladder exhausted →
  delegation FAILED; dependents are BLOCKED, independent delegations continue.
- No tier map / no executor template → the run refuses to start (exit 2). The conductor never
  fabricates a result and has no LLM-judge path; a gate's exit code is the only verdict.

**Non-goals (v1)**
- No planning intelligence: the conductor never writes or re-orders a plan, never re-tiers a
  delegation except via the escalation ladder.
- No parallel dispatch (sequential topo order; parallelism is a v2 concern).
- No hint-miner / calibration policy artifact (follow-on project, depends on this data).
- Never modifies classify/triage/plan tiering logic or `lib/redqueen`.

## Milestones

Each milestone's gate must be able to fail. All code stdlib-only, unittest (not pytest),
ruff (line 110) + mypy clean, house docstring style matching `bin/killhouse_gate_replay.py`.

### M1 — Plan schema + validation (tier: fast/Haiku)
- `schemas/conductor_plan.schema.json` + `schemas/conductor_plan.sample.json` (2+ delegations
  with a dependency between them).
- `bin/killhouse_conduct.py::load_plan/validate_plan` reusing `killhouse_delegation_log._errors`
  as the schema interpreter; CLI `--validate PLAN.json`.
- **Gate:** new tests prove sample validates, each required field's removal fails, unknown
  `planned_tier` fails, duplicate `delegation_id` fails. `python3 -m unittest discover tests` OK.

### M2 — DAG walk + dry-run (tier: fast/Haiku)
- Topological sort with deterministic order (plan order among ready nodes); cycle and
  unknown-dep detection as validation errors.
- CLI `--dry-run`: prints execution order + planned tier per delegation, executes nothing.
- **Gate:** tests prove topo order respects `depends_on`, cycle detected, unknown dep detected,
  dry-run performs no subprocess/executor calls (assert via injected spy).

### M3 — Single-delegation execution + mechanical logging (tier: standard/Sonnet)
- `run_delegation()`: sandbox via `git_worktree_sandbox`-equivalent at target branch HEAD,
  artifact materialization + `_safe_target` path guards (reuse gate-replay helpers), pluggable
  executor, real gate in logged cwd, freeze/finalize delegation record appended to
  `KILLHOUSE_DELEGATION_LOG` or `.killhouse/delegations.jsonl`.
- Records must validate against `schemas/delegation_record.schema.json` (asserted in tests via
  `killhouse_delegation_log.validate_record`).
- **Gate:** tests with a fake executor prove PASS and FAIL both come from the real gate's exit
  code; the written record is schema-valid in both cases; a record is written even when the gate
  fails (logging never blocks).

### M4 — Escalation ladder + commit-back (tier: standard/Sonnet)
- Tier ladder retry with fresh sandbox per attempt; escalation fields recorded per contract.
- On final PASS: commit sandbox diff to the target branch (author identity
  `killhouse-conductor`); dependents see the new HEAD. On ladder exhaustion: delegation FAILED,
  dependents BLOCKED, run summary JSON to stdout with per-delegation verdicts.
- **Gate:** tests prove fast-FAIL→standard-PASS yields `escalated: true, escalation_magnitude: 1`
  and the commit lands on the target branch; exhausted ladder blocks dependents but not
  independents; both-directions (a plan that should fail, fails).

### M5 — Wiring + docs (tier: fast/Haiku)
- `loops/CONDUCT.md` protocol doc (house style); pointers from `AGENTS.md` and
  `skills/ask-kh/SKILL.md`; validator check `conductor` in `bin/killhouse_validate.py`
  (schema+sample stay valid, doc pointers present); README section; version bump.
- **Gate:** `python3 bin/killhouse_validate.py` all checks OK including the new one; full test
  suite, ruff, mypy green.

## Measurable acceptance (whole project)

1. `killhouse_conduct.py --validate` rejects a hand-broken plan (demonstrated, not assumed).
2. A 3-delegation demo plan (one dependency chain, one independent) executes end-to-end with a
   scripted fake executor: produces 3+ schema-valid delegation records, 1 forced escalation, and
   commits on a scratch branch matching the passing delegations.
3. With no `model_tiers` configured, the conductor exits 2 without executing anything.
4. Full gate suite green: unittests, ruff, mypy, `killhouse_validate.py` (all checks).
