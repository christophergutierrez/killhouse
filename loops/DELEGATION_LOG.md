# Delegation Logging Protocol

### Purpose

Collect routing-calibration data at Killhouse's own delegation boundary. Before each subagent
delegation, Killhouse captures one record of exactly what that delegation received and why it was
routed the way it was; after the subagent returns, it finalizes the record with the outcome. The
resulting log is the ground-truth substrate for measuring routing calibration — where a tier was
guessed too low (an escalation fired) and, offline, where it was guessed too high (the gate-replay
harness).

**This protocol collects data only. It does not change classify/triage/plan tiering.** Logging never
alters which tier is chosen, never gates execution, and never blocks a delegation. A logging failure is
recorded as a risk note; it does not stop the pipeline.

### When to log

Every point where `ask-kh` or a heavy loop hands work to a subagent is a delegation. Log one record per
delegation at these boundaries:

- `ask-kh` spawning a heavy loop (`REVIEW_DOCUMENT`, `PLAN`, `IMPLEMENT_MILESTONE`,
  `CODE_REVIEW_TRIBUNAL`, `ARCHITECTURE_DESIGN`, `SKILL_REVIEW`).
- A heavy loop spawning its own role subagents (e.g. `PLAN`'s reviewers, `IMPLEMENT_MILESTONE`'s
  Implementer / Contract Reviewer / Gate Verifier, the tribunal's specialists).

Logging is per-boundary, so it nests: when `ask-kh` delegates to a heavy loop, `ask-kh` logs the outer
delegation and the loop logs each inner role delegation. `plan_position` and `depends_on` encode that
tree.

In a single-agent runtime that runs roles as labeled inline passes instead of subagents, log one record
per labeled pass that stands in for a delegation, so the log shape is identical across runtimes.

### The record

The schema is the single source of truth for the field list, types, and required fields:
`schemas/delegation_record.schema.json`. A schema-valid example is at
`schemas/delegation_record.sample.json`, shown pretty-printed for readability — on disk each log entry is
one single-line JSON object (JSONL), not multi-line.

The list below is a **non-normative reading guide**; when it disagrees with the schema, the schema wins.

- `delegation_id`, `plan_position`, `depends_on` — identity and which prior delegations it consumed.
- `resolved_prompt` — the prompt sent to the subagent, **verbatim**.
- `chosen_tier`, `chosen_model`, `tier_price` — the actual executed tier/model and the tier's price
  basis (see Pricing), not just the tier's identity. `chosen_model` is optional when the runtime does
  not expose a concrete model id.
- `decision_signals` — the classify/triage output plus the confidence and reasoning that drove the tier.
- `routing_request` — optional future router-serving request metadata derived from the delegation
  boundary. It is frozen before delegated output exists.
- `router_decision` — optional future router-serving response metadata: selected tier/model, fallback
  ladder, routing reason, trace id, policy artifact version, whether it was applied, and any fallback
  reason.
- `gate` — the exact verification command, its `cwd`, pass criteria, and baseline polarity.
- `upstream_artifacts` — the resolved inputs consumed, enough to replay.
- `outcome` — pass/fail, and if escalated, the magnitude (tiers jumped) and the triggering signal.

**Pricing.** `tier_price.basis` records where the numbers come from: `configured` (from an optional
`prices` map in `.killhouse/config.json`, keyed by tier or model id), `illustrative` (a documented
stand-in), or `unpriced` when no price is known — the honest value under `current-model-only` routing,
where no tier map or price exists. Never invent `input`/`output` numbers; when unknown, set
`basis: unpriced` and omit them. `currency` and `basis` are always present so the calibration analysis
can tell real costs from stand-ins.

### Freeze before, finalize after

Write exactly **one** record per delegation, in two phases so the pre-decision fields cannot be
back-filled after the fact:

1. **Freeze (before the subagent runs).** Capture `resolved_prompt`, `decision_signals`, `chosen_tier`,
   `tier_price`, optional `routing_request`, optional `router_decision`, `gate`, `upstream_artifacts`,
   `plan_position`, `depends_on`, and `delegation_id` at the boundary. These are the ground truth of
   *what was decided before seeing any output*; treat them as immutable once frozen.
2. **Finalize (after the subagent returns).** Append `outcome`. A fired escalation is a ground-truth
   "guessed-too-low" label: record `escalation_magnitude` (tiers jumped) and `escalation_trigger`, not
   just the pass/fail bit.

Then append the finalized record as one line to the delegation log.

### Replayability is mandatory (Gate 0)

A record is only useful if the delegation can be reconstructed and re-executed from it alone. The
HERMETIC probe (Gate 0) proved two capture requirements without which replay is not faithful:

- `upstream_artifacts` **must** include a `repository_state` pinning the VCS `head` (and dirty files).
  A prompt without a pinned repo state is not replayable.
- `gate` **must** record `cwd`, not only `command`. The same command run from a different directory can
  pass or fail for reasons unrelated to the delegation's output.

Anything else the delegation consumed (an evolved prompt, a plan milestone, a pinned acceptance test)
goes in `upstream_artifacts` as a path plus a content hash, or as inlined pinned content when small.
If the planner later chooses natural branch or PR breakpoints, each delegation record still pins the
repository state for the branch it actually ran on. Record branch/base context when available, and never
infer branch state from the current checkout during replay.

### Router-serving contract

Future router-serving integration belongs in two optional delegation-record fields:

- `routing_request` records the client-side request metadata Killhouse built from the current
  delegation boundary.
- `router_decision` records the response Killhouse consumed: selected tier/model, fallback ladder,
  routing reason, trace id, policy artifact version, whether it was applied, and any fallback reason.

The router decision is advisory. A router can select a tier or model, but it cannot declare delegated
work correct; only the logged gate and finalized `outcome` do that. `chosen_tier` records the actual
executed tier. If `router_decision.applied` is true, `router_decision.selected_tier` must match
`chosen_tier`; if it is false, record `fallback_reason`. Keep route-logic training labels, including
`minimum_viable_tier`, out of Killhouse's live decision code. Those labels belong in routerescalation
artifacts produced from replay and measurement, not in production orchestration.

### Where the log lives

Append records to `KILLHOUSE_DELEGATION_LOG` if set, otherwise `.killhouse/delegations.jsonl`. The log
is run data, not source: it is git-ignored. This protocol operates on **real runs**, never a dry-run
mode — the escalation labels only mean something when they come from live tier decisions.

When a run is driven by the conductor (`bin/killhouse_conduct.py` + `loops/CONDUCT.md`), records are
written by code, not by the orchestrator following this protocol. The schema and semantics are
identical; the difference is mechanical enforcement instead of orchestrator discipline.

### Validation

`python3 bin/killhouse_delegation_log.py --validate <log.jsonl>` checks every record against the schema
and exits non-zero if any required field is missing or malformed. The self-hosting validator
(`bin/killhouse_validate.py --check delegation-logging`) enforces that the schema and sample stay valid
and that this protocol is wired into the loops.

### Context hygiene

The log is an artifact written to disk, not conversation. Never echo captured records, resolved prompts,
or upstream artifact bodies back into the caller's session — write them to the log and return only the
delegation's normal verdict and artifact pointers, exactly as every other stage does.
