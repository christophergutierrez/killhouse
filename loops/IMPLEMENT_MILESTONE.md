# Milestone Implementation Loop

### Purpose

Execute one atomic milestone from an approved implementation plan through disciplined,
test-first vertical slices, and hand a verified repository state to the code-review stage.
The loop builds behavior one slice at a time, proves every test is non-vacuous before making
it pass, and declares the milestone complete only when the plan's own acceptance gates pass in
the terminal — never on subjective judgment.

This loop implements. It does not plan, re-scope, or review. It consumes a single milestone from
`PLAN.md`'s downstream handoff and, on success, hands state to `CODE_REVIEW_TRIBUNAL.md`.

Run until the milestone's acceptance gates all pass and its at-risk invariants hold, a stop
condition or safety gate fires, or `MAX_SLICES` / `MAX_ATTEMPTS` is reached.

### Inputs

- **MILESTONE**: One atomic milestone from `PLAN.md`'s handoff (sec 17/18). It carries:
  - `outcome` (observable, not an activity) and `implementation_scope` — the only files/behavior this loop may touch;
  - `acceptance_gates` — exact commands + expected results + `baseline_polarity` + `post_condition` + evidence;
  - `invariants_at_risk` — the invariant ids this milestone could break, each with scope and `baseline_polarity`;
  - `dependencies`, `evidence_to_record`, `rollback_unit`, `stop_conditions`, `gate_failure_reasoning`.
- **REDQUEEN_PROMPT**: The evolved, adversarially-tested system prompt produced by the `lib/redqueen`
  step. It is the Implementer's guiding system prompt — its job is to steer the agent away from brittle,
  overfit logic toward robust code. Treat it as governing style/robustness, never as a source of scope.
- **PLAN_PATH**: Path to the approved `implementation-plan.md`, for the Staleness Contract, the cheap
  per-pass invariant subset, and the consolidated verification sequence.
- **TARGET_REPOSITORY**: The working tree to modify.
- **TEST_COMMAND(s)**: The exact terminal commands drawn from the milestone's `acceptance_gates`
  (e.g. `uv run pytest tests/test_foo.py::test_bar`). Never invented here.
- **MAX_SLICES**: Maximum vertical slices before halting for re-plan. Default: `10`.
- **MAX_ATTEMPTS**: Green attempts allowed per slice before rollback. Default: `2`.
- **MODE**: `converge` | `dry-run`. Default: `converge`. `dry-run` proves gates fail at baseline and
  reports the slice plan without editing production code.

### Operating Principles

- **One milestone, nothing else.** Edits stay inside `implementation_scope`. Work that belongs to another
  milestone is out of scope; if it appears necessary, that is a replan trigger, not a license to expand.
- **Vertical slices, not horizontal layers.** Build one thin end-to-end slice (the smallest behavior a
  single gate or sub-behavior can observe), not all of one layer then all of the next. Each slice is a
  tracer bullet that responds to what the last one taught you.
- **Red before green, always.** A test that has never been observed failing is not evidence. Prove the
  test fails for the intended reason before writing code to pass it.
- **Minimal green.** Write only enough code to make the current failing command pass. No speculative
  features, no anticipating later slices.
- **Refactor within the slice.** After green, clean up only the slice just built, and only while its test
  stays green. Refactoring never crosses into un-sliced behavior.
- **Robustness via the Red Queen prompt.** The Implementer runs under `REDQUEEN_PROMPT` so slices resist
  the adversarial cases that prompt was evolved against — no brittle special-casing to satisfy one gate.
- **Gates decide completion, not vibes.** The milestone is complete only when its `acceptance_gates`
  produce the expected terminal output and its at-risk invariants still hold.
- **Preserve unrelated behavior.** The cheap per-pass invariant subset from the plan runs every slice;
  a regression halts the slice.
- **Context hygiene.** This loop runs as a delegated subagent by default so the caller's session stays
  lean. It is the noisiest stage — per-slice failing/passing test output, multiplied by slices and
  milestones — and none of that belongs in the caller. Return only the verdict block plus
  artifact/evidence pointers; keep raw test logs and the loop's reasoning trace inside the loop.

### Safety Baseline

Before any slice:

- Confirm the workspace has version control. If it does, record current status and never overwrite
  unrelated existing changes. If it does not, snapshot the files named by `rollback_unit` well enough
  to restore this loop's changes per slice.
- **Staleness Contract check** (from the plan, sec 12): confirm the repository `HEAD`/snapshot and dirty
  files still match what the plan recorded. On mismatch, halt `STALE` — do not implement against a plan
  whose ground truth has moved.
- Run the milestone's `acceptance_gates` **once at baseline** and confirm each fails in the direction its
  `baseline_polarity` predicts. A gate that already passes at baseline is vacuous for this milestone —
  halt `VACUOUS_GATE` and report it rather than claiming a no-op success.
- Establish `dependencies` are satisfied (prior milestones' outcomes present). If a dependency outcome is
  missing, halt `BLOCKED_DEPENDENCY`.
- Rollback applies only to changes made during the current slice. Never roll back user changes or
  unrelated pre-existing edits.

### Roles

- **Slicer**: Decomposes `MILESTONE` into an ordered list of vertical slices, each mapped to the gate or
  sub-behavior it advances. Confirms the seam each slice is tested at. Does not write production code.
- **Implementer** *(runs under `REDQUEEN_PROMPT`)*: Executes the red-green-refactor cycle for one slice —
  writes the failing test, the minimal code to pass it, then refactors the slice. Keeps edits inside
  `implementation_scope`.
- **Gate Verifier**: Runs the milestone's `acceptance_gates` and the plan's invariant checks as raw
  terminal commands, captures their output verbatim, and judges pass/fail strictly on the `post_condition`
  and `baseline_polarity` flip. Does not edit code and does not rationalize partial output as success.

In a single-agent runtime, run each role as a labeled inline pass; keep the Gate Verifier's terminal
capture raw and separate from the Implementer's narration.

### Slice Schema

Each slice the Slicer emits uses this shape:

```markdown
- id: stable-slug-per-behavior
  advances_gate: acceptance_gate id(s) or sub-behavior this slice moves toward
  seam: the public interface/boundary the test observes behavior at
  red_command: exact command expected to FAIL before this slice (baseline_polarity: fail)
  green_condition: the terminal result that proves this slice's behavior exists
  scope_files: files within implementation_scope this slice may touch
  invariants_touched: at-risk invariant ids this slice could affect
```

Slice ids are stable across attempts. Base the slug on the behavior, not on line numbers or attempt count.

### The TDD Cycle (per slice)

For each slice, in order:

1. **Red.** Write the test at the confirmed `seam`. Run `red_command` and confirm it **fails for the
   intended reason** (missing behavior, not a syntax error, import error, or wrong path). A test that
   errors instead of failing meaningfully is not red — fix the test first. Capture the failing output as
   evidence that the gate is non-vacuous.
2. **Green.** Write the minimal code, inside `scope_files`, to make `red_command` pass. Run it and confirm
   the `green_condition`. If it does not pass, the Implementer gets up to `MAX_ATTEMPTS` total; on
   exhaustion, roll back this slice only and halt `SLICE_STUCK` with the failing output.
3. **Refactor.** Improve only the code this slice introduced, re-running `red_command` after each change to
   keep it green. Do not touch un-sliced behavior. Do not add functionality.
4. **Guard.** Run the cheap per-pass invariant subset from the plan. If any regresses, roll back this
   slice only and halt `INVARIANT_REGRESSION` with the offending invariant id and output.

Never write production code before its failing test exists. Never bulk-write tests for future slices.

### Exit Condition (The Gates)

The milestone is **complete** only when the Gate Verifier confirms, from raw terminal output:

- **Every `acceptance_gate` passes** — each gate's command produces its `post_condition` result, and the
  `baseline_polarity` has flipped from its baseline failure (the specific baseline output changed to the
  specific expected output). Paraphrased or partial output does not count; the exact expected result must
  appear.
- **Every at-risk invariant holds** — the `invariants_at_risk` checks pass at their declared scope.
- **Scope is clean** — all edits lie within `implementation_scope`; no unrelated files changed.

Only when all three hold does the loop shut down and hand state to `CODE_REVIEW_TRIBUNAL.md`. If any gate
cannot be made to pass within `MAX_SLICES`, halt `INCOMPLETE` and report the last failing gate output;
this is a replan signal, not a partial pass.

### Execution Loop

1. **Baseline**: Apply the Safety Baseline checks (version control, Staleness Contract, baseline gate run,
   dependencies). Halt on `STALE`, `VACUOUS_GATE`, or `BLOCKED_DEPENDENCY` as applicable.
2. **Slice**: The Slicer decomposes the milestone into ordered vertical slices and confirms seams.
3. **Dry-run stop**: If `MODE` is `dry-run`, output the slice plan plus the baseline failing-gate evidence
   and stop without editing production code.
4. **Implement slice**: For the next slice, run the TDD Cycle (Red → Green → Refactor → Guard) under
   `REDQUEEN_PROMPT`.
5. **Advance or halt**: On a stuck slice or invariant regression, roll back only that slice and halt with
   the captured output. Otherwise continue to the next slice.
6. **Gate check**: When all slices are done (or a gate becomes satisfiable early), the Gate Verifier runs
   every `acceptance_gate` and the at-risk invariants from raw terminal commands.
7. **Decide**: If all gates pass, invariants hold, and scope is clean → verdict `COMPLETE`, hand off. If a
   gate fails and slices remain within `MAX_SLICES` → return to step 4. Otherwise halt `INCOMPLETE`.
8. **Stop conditions**: Honor the milestone's `stop_conditions` and halt for human confirmation whenever an
   edit would exceed `implementation_scope`, touch a blast-radius boundary, or require a plan change.

### Non-Vacuous Gate Standard

A gate is credible evidence only if it could have failed and did fail at baseline:

- it ran at baseline and failed in the direction `baseline_polarity` predicts;
- its `post_condition` is an objective, observable terminal result, not a subjective judgment;
- the same command, re-run after implementation, now produces the expected result;
- the change in output is attributable to this milestone's edits, not unrelated state.

A gate that passed at baseline, cannot be run, or whose "pass" is asserted rather than observed is not a
gate — surface it as a defect against the plan.

### Convergence & Halting

- **Green means observed green.** Never mark a slice or milestone complete without capturing the passing
  terminal output.
- **No scope laundering.** Do not satisfy a gate by editing outside `implementation_scope`, weakening a
  test, or hard-coding a gate's expected output. Any of these voids the milestone.
- **Per-slice rollback.** A failed slice rolls back only that slice's changes; previously green slices
  remain. A failed milestone rolls back to `rollback_unit`.
- **Attempt cap.** Each slice gets `MAX_ATTEMPTS` green attempts; the milestone gets `MAX_SLICES` slices.
  Exhaustion halts with evidence for re-plan, never a silent partial pass.
- **Thrash halt.** Stop and escalate if the same slice id fails green across consecutive attempts, or if a
  guarded invariant regresses more than once.

### Runtime Degradation

| Missing capability | Adaptation |
| --- | --- |
| No subagents | Run Slicer, Implementer, and Gate Verifier as labeled inline passes; keep gate output raw and sequential. |
| No `REDQUEEN_PROMPT` | Proceed with a plain implementer system prompt; record that robustness evolution was skipped as a risk. |
| Weak shell access | Run `dry-run`: emit the slice plan and the exact gate commands with expected results for a human to run; mark gates unverified. |
| No version control | Snapshot `rollback_unit` files before each slice; express rollback as restoring those copies. |
| Unsafe/slow baseline commands | Do not run them; record why; require a human to run baseline gates before the loop edits code. |

### Final Output

**Return only the verdict, the gate-evidence table (baseline → post-implementation), and artifact/evidence
pointers to the caller — keep raw per-slice test output and the loop's reasoning inside the loop.**

In `dry-run` mode, output the slice plan and baseline failing-gate evidence only.

In `converge` mode, output:

- verdict: `COMPLETE` | `INCOMPLETE` | `SLICE_STUCK` | `INVARIANT_REGRESSION` | `STALE` | `VACUOUS_GATE` | `BLOCKED_DEPENDENCY`;
- slices implemented, with each slice's red evidence and green evidence;
- `acceptance_gates` results — baseline output → post-implementation output, verbatim;
- at-risk invariants checked and their results;
- files changed (confirmed within `implementation_scope`);
- `evidence_to_record` captured for the plan's audit trail;
- on success, an explicit handoff line to `CODE_REVIEW_TRIBUNAL.md`; otherwise the failing gate output and the replan trigger it implies.
