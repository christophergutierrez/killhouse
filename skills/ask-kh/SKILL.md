---
name: ask-kh
description: Drive a code change through the Killhouse pipeline. Routes you to the right stage and runs the gauntlet at the autonomy level you choose.
disable-model-invocation: false
---

# Ask KH

One destination: ship a code change through the Killhouse gauntlet. Tracks which stage you're at,
what to invoke next, and how much to stop and check with you.

Every stage is a pointer. Heavy loops run as delegated subagents — never inlined into this session.

## Instruction-document changes

If the request is primarily about changing active agent-instruction documents, route to
`loops/SKILL_REVIEW.md` instead of the code-change pipeline. This includes `skills/**/SKILL.md`,
`loops/**/*.md`, `AGENTS.md`, `README.md`, plugin manifests, marketplace manifests, install docs, and
any document an agent is expected to execute as instructions.

Use the normal code-change gauntlet only when the instruction-document change is part of a broader
application-code change. In that case, run `SKILL_REVIEW` on the instruction surfaces before declaring
the pipeline done.

## Resume

On startup, check for `.killhouse/run-state.json`. If found, read it and ask the user:

- **Resume** — restore state and continue from the recorded stage.
- **Start fresh** — delete the state file and begin a new run.

At every courtesy checkpoint, write current state to `.killhouse/run-state.json`. On pipeline
completion or Abort, delete it.

## The pipeline

```
/classify
  ├─ trivial ───────────────────────────────────────────────┐
  └─ major → /grill-with-docs → [POST-GRILL GATE] → /to-prd  │
             → loops/REVIEW_DOCUMENT  (spec audit)            │
             → loops/PLAN             (verified planning)     │
             → lib/redqueen           (evolve exec prompt)    │
             → loops/IMPLEMENT_MILESTONE  ◄───────────────────┘  (per milestone; TDD)
             → loops/CODE_REVIEW_TRIBUNAL (blocking findings fixed)
             → loops/ARCHITECTURE_DESIGN  (depth & boundary check)
             → done
```

- **`/classify`** — classify the request as trivial or major. In Codex or generic agents, use the
  `classify` skill by name. Returns `classification: trivial | major` + rationale.
  Use `/triage` (the `triage` skill by name` in Codex) instead when the request comes from a GitHub issue or PR.
- **`/grill-with-docs`** — interactive alignment; builds `CONTEXT.md` and ADRs. Always interactive.
- **`/to-prd`** — synthesize the grilled conversation into a PRD. No new interview.
- **`loops/REVIEW_DOCUMENT`** — 9-subagent spec audit; converges the PRD.
- **`loops/PLAN`** — produces `implementation-plan.md`. Does not write code.
- **`lib/redqueen`** — optional prompt evolution via `bin/evolve_exec_prompt.py`. Self-degrades to
  a plain implementer prompt if not set up or if champion fitness is 0.0.
- **`loops/IMPLEMENT_MILESTONE`** — TDD red-green-refactor per milestone.
- **`loops/CODE_REVIEW_TRIBUNAL`** — multi-specialist review; blocking findings fixed to a `PASS`.
- **`loops/ARCHITECTURE_DESIGN`** — final depth, boundary, and domain-language check.

## Autonomy: the one setting that matters

Autopilot skips *courtesy* checkpoints, never mandatory gates. Choose **once, at the post-grill gate**. Details in `skills/ask-kh/references/autonomy.md`.

### The post-grill gate (always stops)

Stop after `/grill-with-docs` and ask:

1. **Ready for the PRD?** — or run another grilling pass.
2. **Checkpoint or Autopilot?**
   - **Checkpoint** — stop at each stage boundary and wait for go-ahead.
   - **Autopilot** — run to completion. Stops only for completion, hard blockers, genuinely
     unforeseen decisions, or budget trips. See `references/autonomy.md` for full stop conditions.
3. **Execution policy** (optional) — `cost_optimized` (default) or `time_optimized`.
   Reasoning-tier agents write file contracts; standard-tier handles routine contract review;
   cheaper tiers write first-pass production code. See `references/autonomy.md` for full rationale.

Budget guard fields (set at the post-grill gate, defaults in `references/autonomy.md`):
`max_milestones_unattended` (default 8), `max_pipeline_reentries` (default 3), `token_budget` (optional).

### Model tier map

Check for model-tier config in this order: `.killhouse/config.local.json`, `.killhouse/config.json`.

If neither exists: use the current runtime model for every tier, record `model_routing: current-model-only`.

If config exists: `model_tiers.fast`, `.standard`, and `.reasoning` must all be non-empty strings.
Treat values as exact opaque runtime model ids. Do not alias, normalize, upgrade, downgrade, or substitute model names. Echo the
resolved map before running:

```yaml
model_tiers:
  fast: exact-id
  standard: exact-id
  reasoning: exact-id
model_routing: configured | current-model-only | unavailable
```

If config is invalid (missing tiers or not non-empty strings), stop and ask the user to fix or remove it — "If a config exists but is invalid" do not silently fall back. If model routing is unavailable in
the runtime, record `model_routing: unavailable`.

## Context hygiene

- Each heavy loop runs as a **delegated subagent**. Never inline loop rounds, reviewer transcripts,
  or raw tool output into this session.
- A stage returns only its **artifact path + verdict**. The artifact is the handoff; the transcript
  is discarded.
- Interactive front-end skills (`classify`, `grill-with-docs`, `to-prd`) run in the main chat by
  design but externalize output to files (`CONTEXT.md`, ADRs, PRD).
- Before each delegation, append a delegation record per `loops/DELEGATION_LOG.md` for
  routing-calibration data. This is data collection only: it never changes tier selection and never
  gates or blocks a delegation. The log is a git-ignored artifact, never echoed into this session.
  For headless plan execution without orchestration, the standalone conductor (`bin/killhouse_conduct.py`) writes records mechanically using the same schema and semantics.

## Mandatory gates (never skipped, in either mode)

- **PLAN blast-radius gate** — `BLOCKED`: public/persisted-contract changes, migrations,
  security/auth/billing, cross-ownership, or no adequate way to test. Human decision required.
- **IMPLEMENT_MILESTONE halts** — `STALE`, `VACUOUS_GATE`, `BLOCKED_DEPENDENCY`, or `INCOMPLETE`
  after `MAX_SLICES`. Replan signals, not partial passes.
- **CODE_REVIEW_TRIBUNAL** — blocking finding that cannot be auto-fixed.
- **ARCHITECTURE_DESIGN** — safety gate or High blast-radius RFC awaiting confirmation.

## Trivial fast path

When `/classify` returns trivial, skip grilling and route straight to `loops/IMPLEMENT_MILESTONE`
with a minimal milestone (outcome + one acceptance gate). The minimal milestone does not need
`implementation_contracts`; implement directly from scope and gates.
Ask Checkpoint-or-Autopilot before running. Escalate to the full flow if the change crosses a
mandatory-gate boundary, requires a new public surface, or needs architecture judgment.

## State to carry across the run

Track and echo at each checkpoint. Persisted to `.killhouse/run-state.json`:

- `classification`: trivial | major
- `stage`: current pipeline stage
- `autonomy`: checkpoint | autopilot
- `execution_policy`: cost_optimized | time_optimized
- `model_tiers`: exact resolved tier map, or current model for all tiers
- `model_routing`: configured | current-model-only | unavailable
- `artifacts`: file pointers to CONTEXT.md, PRD, implementation-plan.md, evolved exec prompt,
  per-milestone verdicts — never inlined bodies
- `budget`: field values and what has been consumed / what tripped
- `assumptions_logged`: low-risk defaults taken in Autopilot, for review at completion
