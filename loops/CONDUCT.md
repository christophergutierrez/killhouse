# Conductor: Mechanical Plan Enforcement

### Purpose

The conductor is a zero-intelligence Python driver (`bin/killhouse_conduct.py`) that executes a
delegation plan: walks the delegation DAG in topological order, dispatches each delegation to its
planned tier via a configured executor, runs the real logged gate, escalates up the tier ladder on
failure, and writes schema-valid delegation records mechanically at the boundary.

This converts the delegation-logging *protocol* (LLM-followed Markdown) into *enforcement* (code):
freeze/finalize becomes deterministic, escalation labels become ground truth by construction, and
tier routing becomes real (cheap slices actually run on cheap models).

The conductor is used for **headless plan execution**: when a prior stage has produced a complete
delegation plan, and you want to replay or extend it without human orchestration. It is **not**
used in the interactive ask-kh pipeline (the loop orchestrators follow the delegation-logging
protocol by hand).

### The plan

A conductor plan is a JSON file specifying what to execute and how. The schema is the single source
of truth: `schemas/conductor_plan.schema.json`. A schema-valid example is at
`schemas/conductor_plan.sample.json`.

The plan contains:

- `plan_id` — unique identifier for this plan
- `target_branch` — the branch name where delegations will be executed and committed
- `delegations` — an array of delegations to execute in topological order

Each delegation in the plan mirrors the frozen half of a delegation record:
`delegation_id`, `plan_position`, `depends_on`, `resolved_prompt`, `planned_tier`, `gate` (with
`command`, `cwd`, `pass_criteria`, `baseline_polarity`), and `upstream_artifacts`.

### Execution semantics

**Topological order.** Delegations execute in the order determined by `depends_on`. The conductor
computes a deterministic topological sort (plan order as tiebreaker among ready nodes); if a cycle
or unknown dependency is detected, validation fails before anything runs.

**Per-delegation flow:**

1. **Freeze** the record with identity, inputs, and planned tier before execution
2. **Sandbox** at the target branch's HEAD via a throwaway git worktree (reusing the gate-replay
   sandbox logic)
3. **Materialize** upstream artifacts into the sandbox
4. **Execute** via the configured executor (shell template with `{model}`, `{workdir}`, `{prompt_file}`)
   to generate code in the sandbox
5. **Gate** — run the real verification command in the logged `cwd`; its exit code is the only
   verdict (`pass_criteria` and `baseline_polarity` are recorded context, not judged)
6. **Finalize** the record with the outcome (pass/fail; if escalated, `escalation_magnitude` and
   `escalation_trigger`)
7. **Commit** — on PASS, commit the sandbox diff to the target branch. On FAIL, the record is still
   written, but the branch is not advanced.

**Escalation ladder.** On gate FAIL at the planned tier, retry at the next tier up (fast →
standard → reasoning). Each attempt gets a fresh sandbox at the current branch HEAD (which may
include commits from earlier passing delegations). When the ladder is exhausted, the delegation is
FAILED, its dependents are BLOCKED (will not execute), and independent delegations continue.

**Commit-back.** On final PASS, the conductor commits the sandbox diff to the target branch using
author identity `killhouse-conductor`. The commit is attempted with a compare-and-swap against the
frozen HEAD: if the branch has moved since the delegation's record was frozen, the commit fails
(verdict FAIL for that delegation), but the written record's gate status stays truthful — it
genuinely passed, the commit just could not land.

**Refusal.** The conductor refuses to run without both a `model_tiers` map in `.killhouse/config.*`
and an executor template (`--executor` flag, `KILLHOUSE_CONDUCT_EXECUTOR` env, or `conduct_executor`
in the config). It exits 2 in this case. It never fabricates a tier, never substitutes a model, and
never runs an LLM-judge path; a gate's exit code is the only verdict.

### Hard rules

- **Real gate only.** The gate is always real: a subprocess call in the logged `cwd` with the
  logged `command`, evaluated against `pass_criteria` and `baseline_polarity`. No LLM judgment, no
  shortcuts.
- **Sandbox pinned.** Each delegation's sandbox is pinned to a fixed HEAD (either the plan's
  original target branch HEAD or the current branch HEAD if later delegations passed). Reusing the
  same sandbox for multiple attempts would mix results; each attempt gets a fresh worktree.
- **One record per delegation.** Exactly one delegation record is written per delegation, whether
  it passes or fails. Logging never blocks execution and cannot fail the run.
- **Logging never blocks.** A write to the delegation log cannot cause the conductor to stop. If
  the log cannot be written, a risk note is recorded; execution continues.

### Where the conductor plan lives

The plan is typically produced by a prior stage (e.g. `loops/PLAN.md` with a conductor export
feature) and is passed to the conductor CLI. The conductor itself does not produce a plan; it
consumes one.

### Validation

`python3 bin/killhouse_conduct.py --validate PLAN.json` checks the plan against the schema and
exits non-zero if validation fails. The self-hosting validator (`bin/killhouse_validate.py --check
conductor`) enforces that the schema and sample stay valid, that the conductor doc exists, and that
pointers are wired into AGENTS.md.

### CLI

```bash
# Validate a plan without executing
python3 bin/killhouse_conduct.py --validate PLAN.json

# Print execution order and planned tier per delegation (no subprocess calls)
python3 bin/killhouse_conduct.py --dry-run PLAN.json

# Execute end-to-end; exit 2 if unroutable (no model_tiers or executor)
python3 bin/killhouse_conduct.py --run PLAN.json --executor 'my-agent --model {model} --cwd {workdir} --prompt-file {prompt_file}'

# Print the schema path
python3 bin/killhouse_conduct.py --schema-path
```

`--run` also accepts `--repo-root` (defaults to this repository) and `--target-branch` (overrides
the plan's own `target_branch` field).
