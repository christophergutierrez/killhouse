# Autonomy, Budget, and Execution Policy — Reference

Loaded on demand by `ask-kh`. Do not inline this into the main session.

---

## Checkpoint mode — full option set

At each **courtesy checkpoint**, present a tight status (what just finished, artifact produced, what runs next) and ask:

- **Continue** — advance and keep stopping at each checkpoint.
- **Switch to Autopilot** — advance and run to completion without further courtesy stops.
- **Revise** — re-run or adjust the stage just completed.
- **Abort** — stop the run.

Re-ask at every checkpoint so the user can flip to Autopilot at any time.

---

## Autopilot mode — full stop conditions

Run through every courtesy checkpoint without stopping. Halt **only** for:

1. **Completion** — pipeline reaches `done`.
2. **Hard blocker** — a mandatory gate fires, or a stage returns `BLOCKED`/halt it cannot resolve.
3. **Genuinely unforeseen decision** — exhausted the paper trail (`CONTEXT.md`, ADRs, PRD, `implementation-plan.md`) and the decision is both unresolvable from context *and* material. Log low-risk defaults and proceed rather than interrupting; only stop when the decision crosses a mandatory gate or cannot safely be defaulted.
4. **Budget guard trip** — run crosses a ceiling set at the post-grill gate (see below).

When stopping for (3), surface exactly what you need and the options you see so one answer unblocks the whole run.

---

## Autopilot budget guard — detail

Every loop is individually capped, but the pipeline multiplies them — one `IMPLEMENT_MILESTONE` per milestone, and `PLAN` does not cap milestone count. Budget guard fields set at the post-grill gate:

| Field | Default | Trips when |
|---|---|---|
| `max_milestones_unattended` | 8 | `PLAN` emits more milestones than this |
| `max_pipeline_reentries` | 3 | Total loop re-entries (bounce to replan, tribunal FAIL reopening implementation) exceeds this |
| `token_budget` | none | Runtime-exposed usage crosses the set ceiling |

On any trip: **degrade to Checkpoint mode and ask** whether to continue. Do not silently halt; do not silently keep spending. Record what tripped in `budget` state.

Checkpoint mode is often right when a run spans several sessions — pausing at a checkpoint keeps work from getting stranded midstream.

---

## Execution policy — rationale

Quality is held constant by gates and review. The policy only chooses the route to that quality bar.

**`cost_optimized`** (default) — prefer the cheapest capable tier for bounded work. Escalate only after evidence: failed gates, repeated same failure, scope expansion, security/architecture uncertainty, or reviewer rejection. Reasoning-tier agents write file contracts; standard-tier handles routine contract review; cheaper tiers write first-pass production code.

**`time_optimized`** — prefer stronger tiers earlier to reduce wall-clock retries. Still delegate mechanical checks and independent review to cheaper tiers where safe. Reasoning-tier production-code edits still require an explicit rescue, safety, or cross-cutting refactor exception.

---

## Branching mode

If granular branching is available, choose it at the same post-grill gate as autonomy and execution
policy. The plan owns natural branch/PR breakpoints, usually milestone boundaries with objective gates.

Autopilot may create and move through planned branches only when the breakpoints, gates, and handoff
state are already recorded in the PRD or `implementation-plan.md`. An unplanned branch split that changes
scope, commit behavior, stop conditions, or replay inputs is a genuinely unforeseen decision: degrade to
Checkpoint mode and ask. Delegation records must pin repository state and consumed artifacts on the
branch where the delegation actually ran.
