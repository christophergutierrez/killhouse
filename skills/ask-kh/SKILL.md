---
name: ask-kh
description: Drive a code change through the Killhouse pipeline. Routes you to the right stage and runs the gauntlet at the autonomy level you choose.
disable-model-invocation: false
---

# Ask KH

One destination: ship a code change through the Killhouse gauntlet. Unlike a generic
"which skill fits?" router, `ask-kh` has a single flow and drives it — it tracks which
stage you're at, what to invoke next, and how much to stop and check with you along the way.

Every stage is a pointer. `ask-kh` invokes lightweight skills for the front end and, when the runtime
supports it, spawns subagents that read the heavy `loops/` payloads for the rigorous middle. It never
inlines a loop's contents into the main session.

## The pipeline

```
/triage
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

- **`/triage`** — classify the request. In Codex, use the `triage` skill by name. **Trivial** (small,
  low-risk, well-understood bug or
  change) routes straight to `loops/IMPLEMENT_MILESTONE`. **Major** enters the full flow.
- **`/grill-with-docs`** — the human-alignment stage. In Codex, use the `grill-with-docs` skill by
  name. Interview to sharpen the idea, building
  `CONTEXT.md` and ADRs as it goes. This is where you front-load everything the pipeline needs
  to run unattended, so it is always interactive.
- **`/to-prd`** — synthesize the grilled conversation into a PRD. In Codex, use the `to-prd` skill by
  name. No new interview.
- **`loops/REVIEW_DOCUMENT`** — 9-subagent spec audit; converges the PRD.
- **`loops/PLAN`** — produces `implementation-plan.md` with traceability, invariants, and
  falsifiable acceptance gates. Does not write code.
- **`lib/redqueen`** — evolves the adversarially-robust execution prompt handed to the implementer.
  Run it via `bin/evolve_exec_prompt.py`, which drives redqueen and writes the champion prompt to an
  artifact (default `redqueen-exec-prompt.md`) that `IMPLEMENT_MILESTONE` reads as `REDQUEEN_PROMPT`:
  ```bash
  # extract from a champions.json evolved earlier (cheap; the usual path)
  bin/evolve_exec_prompt.py --champions runs/exec/champions.json --prompt-out redqueen-exec-prompt.md
  # or evolve fresh (needs OPENAI_BASE_URL/DRQ_MODEL; add --mock for an offline plumbing check)
  bin/evolve_exec_prompt.py --out runs/exec --prompt-out redqueen-exec-prompt.md
  ```
  This stage is **optional**: if redqueen isn't set up or the prompt's fitness is `0.0`, the pipeline
  degrades to a plain implementer prompt (no hard failure).
- **`loops/IMPLEMENT_MILESTONE`** — TDD red-green-refactor of one milestone at a time, exiting only
  when the plan's acceptance gates pass in the terminal.
- **`loops/CODE_REVIEW_TRIBUNAL`** — multi-specialist review; blocking findings fixed to a `PASS`.
- **`loops/ARCHITECTURE_DESIGN`** — final depth, boundary, and domain-language check.

## Autonomy: the one setting that matters

The pipeline can stop and check with you at every stage boundary, or run end to end. You choose
**once, at the post-grill gate**, and can change your mind at any checkpoint.

### The post-grill gate (always stops)

`/grill-with-docs` is where you and the agent get aligned, so the pipeline **always** stops when it
ends and asks two things:

1. **Ready for the PRD?** — or do you want another grilling pass first.
2. **Checkpoint or Autopilot?** — how the rest of the run should behave:
   - **Checkpoint** — stop at each courtesy checkpoint (each stage boundary) and wait for your go-ahead.
   - **Autopilot** — run to completion without stopping at courtesy checkpoints. "Set and forget."

The reasoning behind this placement: if the grilling did its job, everything the pipeline needs is
already captured in `CONTEXT.md`, the ADRs, and the conversation — so Autopilot is safe to choose here
and nowhere earlier.

### Checkpoint mode

At each **courtesy checkpoint** (the boundary after a stage completes), present a tight status — what
just finished, the artifact produced, what runs next — and ask:

- **Continue** — advance to the next stage and **keep stopping at each checkpoint**.
- **Switch to Autopilot** — advance and run the rest to completion without further courtesy stops.
- **Revise** — re-run or adjust the stage just completed before advancing.
- **Abort** — stop the run.

Re-ask this at **every** checkpoint, so you can flip to Autopilot the moment you're satisfied things
are on rails.

### Autopilot mode

Run through every courtesy checkpoint without stopping. Halt **only** for:

1. **Completion** — the pipeline reaches `done`.
2. **A hard blocker it cannot pass** — a mandatory gate fires (see below), or a stage returns a
   `BLOCKED` / halt verdict it cannot resolve on its own.
3. **A genuinely unforeseen decision** it cannot resolve from the captured context.
4. **A tripped budget guard** — the run crosses a ceiling set at the post-grill gate (see below).

**Try hard to avoid (3).** Before ever stopping to ask, exhaust the paper trail first: re-read
`CONTEXT.md`, the ADRs, the PRD, and `implementation-plan.md`. If the decision is low-risk and the
context implies a reasonable default, **log the assumption and proceed** (mirroring PLAN's
`READY_WITH_ASSUMPTIONS`) rather than interrupting. Only a decision that is both unresolvable from
context *and* material — or one that crosses a mandatory gate — earns an interruption. When you must
stop, surface exactly what you need and the options you see, so one answer unblocks the whole run.

### Autopilot budget guard

Every loop is individually capped (`REVIEW_DOCUMENT` ≤10 rounds, `PLAN` `MAX_PASSES`, `IMPLEMENT_MILESTONE`
`MAX_SLICES`×`MAX_ATTEMPTS`, tribunal/architecture `MAX_PASSES`), but the **pipeline multiplies them** —
one `IMPLEMENT_MILESTONE` run per milestone, and `PLAN` does not cap milestone count. So "set and forget"
must not mean "burn everything." Set a run budget at the post-grill gate and treat crossing it as a
budget-guard halt (Autopilot stop condition 4):

- `max_milestones_unattended` (default **8**) — if `PLAN` emits more milestones than this, stop at the
  pre-implementation checkpoint and confirm before blasting through all of them.
- `max_pipeline_reentries` (default **3**) — total loop re-entries across the run (a milestone bounced
  back to replan, a tribunal `FAIL` that reopens implementation) beyond this forces a stop.
- `token_budget` (optional) — if the runtime exposes usage, stop and report when the run crosses it.

On any budget trip, **degrade to Checkpoint mode and ask** whether to continue — do not silently halt the
work, and do not silently keep spending. Record what tripped in `budget` state.

## Context hygiene (governing rule)

Keeping the main session lean is a core feature, not a side effect — enforce it at every stage:

- Each heavy loop (`REVIEW_DOCUMENT`, `PLAN`, `IMPLEMENT_MILESTONE`, `CODE_REVIEW_TRIBUNAL`,
  `ARCHITECTURE_DESIGN`) runs as a **delegated subagent** when the runtime supports subagents. If it
  does not, run the loop inline as labeled passes using the loop's Runtime Degradation section.
  `ask-kh` never inlines a loop's rounds, reviewer transcripts, or raw tool output into the main
  session.
- A stage returns only its **artifact path + verdict** (e.g. `implementation-plan.md` + `READY`), which
  `ask-kh` records as a pointer. The artifact is the handoff; the transcript is discarded.
- The interactive front-end skills (`triage`, `grill-with-docs`, `to-prd`) run in the main chat by design,
  but they externalize their output to files (`CONTEXT.md`, ADRs, the PRD) so what flows forward is the
  artifact, not the raw conversation.

## Mandatory gates (never skipped, in either mode)

Autopilot skips *courtesy* checkpoints, never these. When one fires, stop and surface it with what's
needed to proceed:

- **PLAN blast-radius gate** — verdict `BLOCKED`: public/persisted-contract changes, migrations,
  security/auth/billing behavior, cross-ownership edits, or no adequate way to test. Human decision required.
- **IMPLEMENT_MILESTONE halts** — `STALE` (plan's repository state moved), `VACUOUS_GATE` (an acceptance
  gate already passes at baseline), `BLOCKED_DEPENDENCY`, or `INCOMPLETE` after `MAX_SLICES`. These are
  replan signals, not partial passes.
- **CODE_REVIEW_TRIBUNAL** — a blocking finding that cannot be auto-fixed.
- **ARCHITECTURE_DESIGN** — a safety gate or High blast-radius RFC awaiting confirmation.

## Trivial fast path

When `/triage` classifies the request as trivial, skip the front end and grilling entirely and route
straight to `loops/IMPLEMENT_MILESTONE` with a minimal milestone (outcome + acceptance gate). The
autonomy setting still applies: ask Checkpoint-or-Autopilot before running. Escalate back into the full
flow the moment the "trivial" change turns out to touch a mandatory-gate boundary.

## State to carry across the run

`ask-kh` is stateful. Track, and echo at each checkpoint:

- `classification`: trivial | major
- `stage`: current pipeline stage
- `autonomy`: checkpoint | autopilot
- `artifacts`: **file pointers** to CONTEXT.md, PRD, implementation-plan.md, evolved exec prompt, per-milestone verdicts — never the inlined bodies
- `budget`: `max_milestones_unattended`, `max_pipeline_reentries`, optional `token_budget`, and what has been consumed / what tripped
- `assumptions_logged`: low-risk defaults taken in Autopilot, for your review at completion
