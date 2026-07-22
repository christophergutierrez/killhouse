# TODO: `VALIDATE` — standing ADR↔code drift audit

**Status:** proposed / not started
**Origin:** borrowed concept from the `sdlc` toolkit's `/sdlc validate`; adapted to Killhouse's file-first, provider-agnostic style. **Do not port the sdlc implementation** — it is coupled to the imem Knowledge API and VideoAmp infra. Port the *idea*, not the API calls.

---

## One-line

A loop that audits whether the codebase still matches its accepted ADRs, in both directions, and reports drift — run any time, independent of any single change.

## Why Killhouse needs this (the gap)

Killhouse verifies **at change time**: the code-review tribunal, the gate audit in `PLAN`, and falsification all fire while a change moves through the gauntlet. Once a change ships, **nothing ever re-checks that the shipped code still honors the ADRs that constrained it.** Decisions and code drift apart silently over months — an ADR says "all writes go through the coarse API," six unrelated PRs later a direct-write path exists, and no gauntlet run would notice because each PR was individually clean.

`VALIDATE` closes that loop. It is **change-independent, standing maintenance**, not a stage in the per-change pipeline.

### What it is NOT (disambiguation for the implementer)

- **Not `bin/killhouse_gate_replay.py`** — gate_replay re-runs a plan's *acceptance gates*; `VALIDATE` checks *ADR↔code consistency*, which no gate necessarily covers.
- **Not `CODE_REVIEW_TRIBUNAL`** — the tribunal reviews a *diff* for quality/correctness; `VALIDATE` audits the *whole tree* against *decisions*.
- **Not `ARCHITECTURE_DESIGN`** — that checks depth/boundary/domain on a change's scope; `VALIDATE` checks decision-conformance across the repo over time.

It complements all three; it does not replace any.

## Proposed shape

- A new heavy loop: **`loops/VALIDATE.md`** (delegated-subagent by default, per Killhouse context-hygiene rules — reviewers return findings only; the loop hands back a report artifact + a machine-readable verdict block).
- Optional companion helper for the mechanical grep/AST passes — **pick a name distinct from the existing `bin/killhouse_validate.py`** (which validates *manifests/plugins*), e.g. `bin/adr_drift.py`, to avoid collision.
- Invocable standalone, and reachable from `ask-kh` as an off-pipeline maintenance command (e.g. `ask-kh validate` or a documented direct-invoke). It is **not** inserted into the triage→…→architecture change flow.

## Inputs

- **ADRS_PATH** — where accepted ADRs live. Default: `docs/adr/`. Must not assume a specific store; accept a glob.
- **SOURCE_ROOT** — codebase root to audit. Default: repo root.
- **CONTEXT_DOCS** — glossary / PRDs / feature designs used as *bridges* between an ADR and code (an ADR often names a concept the code implements under a different literal string; a feature design links them).
- **TEST_COMMANDS** — optional; used only to confirm a claimed behavior is exercised, never required.
- **MODE** — `report` (default) | `report-and-file` (open a finding/TODO per drift).

## Core algorithm

For each **accepted** ADR, walk a three-tier matching hierarchy **in order**, stopping at the first tier that yields evidence:

1. **Feature-design / doc bridge** — if a design doc or glossary entry links to the ADR (e.g. a `depends-on`/citation), extract its concrete file references and named patterns; grep/AST the source for those. Match → **Confirmed**.
2. **Direct ADR terms** — extract concrete terms from the ADR body (library names, RPC/endpoint names, schema objects, config keys, named patterns) and grep the source best-effort. Match → **Confirmed**.
3. **No match** — bucket by the ADR's own delivery marker:
   - marked *planned/not-yet-built* → **Expected gap** (silent, listed separately).
   - otherwise → **Needs input** — surface to the human: "no evidence of ADR-NNNN <title> in code; is this (a) planned, (b) partially implemented — point me to it, or (c) conceptual-only?"

Then two **advisory** passes (lower confidence bar, surface possibilities):

4. **Draft/in-review ADR conflict pass** — for non-accepted ADRs, grep for code that already *contradicts* the emerging decision. Surface as "code may conflict with a decision in progress."
5. **Code→ADR reverse pass** — scan the source for architectural patterns (state machines, middleware chains, schema constraints, auth/security gates, migrations) and check whether any *accepted ADR covers them*. Uncovered load-bearing patterns → **Undocumented pattern** (candidate for a new ADR).

## Output (report artifact + verdict block)

Bucketed report, most-actionable first:

```
—— Definitive (accepted ADRs) ——
✅ Confirmed (N):        ADR-NNNN <title> — <file:line evidence>
⚠️  Drift (M):           ADR-NNNN <title> — <what's absent / what contradicts it>
❔ Needs input (K):      ADR-NNNN <title> — <why low-confidence>
⏭️  Expected gaps (P):   ADR-NNNN <title> (marked planned)
🔍 Undocumented (Q):     <pattern @ file> — no covering ADR
—— Advisory (draft/in-review) ——
📋 Draft-ADR conflicts (J)
```

Append a machine-readable verdict block (mirror `PLAN`/`REVIEW_DOCUMENT` style): counts per bucket, `blocking` = any accepted ADR in **Drift** whose ADR is marked shipped/load-bearing, plus the staleness record (VCS HEAD + timestamp the audit was grounded in). A **Drift** finding on a shipped, load-bearing ADR should be treated as blocking for the audit's verdict.

After the report, work the **Needs input** list interactively one ADR at a time (planned → mark it planned; partial → re-grep at the pointed location; conceptual-only → note, no code expected).

## Capability tiers (provider-agnostic)

- **fast**: the grep/term-extraction/inventory passes.
- **standard**: bridging ADR intent to code, pattern recognition in the reverse pass.
- **reasoning**: final drift judgment, blocking-severity calls, the interactive Needs-input adjudication.

Run passes as parallel subagents when supported; degrade to labeled inline passes otherwise. No model-tier map → current-model-only.

## Degradation

| Missing | Adaptation |
| --- | --- |
| No subagents | Run each ADR's match hierarchy as a labeled inline pass. |
| Weak shell / no grep | Report-only from what can be read; mark unscanned areas as "unverified," never as Confirmed. |
| No VCS | Record a snapshot id instead of HEAD for the staleness line. |

## Falsifiable acceptance criteria (how we know it works)

Write these as gates the implementer must make *fail* at baseline before implementing (Killhouse `PLAN`-style non-vacuous proof):

1. **Seeded drift is caught.** Introduce a deliberate contradiction to a known accepted ADR (a direct-write path when an ADR mandates the coarse API). Baseline: `VALIDATE` on the clean tree reports it **Confirmed**; after seeding, it must move to **Drift**. If it stays Confirmed, the matcher is vacuous.
2. **Planned ADRs don't cry wolf.** An ADR marked planned/not-built must land in **Expected gaps**, never **Needs input** or **Drift**.
3. **Undocumented pattern is surfaced.** Add a load-bearing pattern (e.g. a new auth gate) with no covering ADR; the reverse pass must list it under **Undocumented**.
4. **No false Confirmed from prose alone.** An ADR whose terms appear only in comments/docs but not in executable code must NOT be **Confirmed** (guards against grep matching its own citation).

## Open questions for the implementer

- Where do "accepted" and "planned/shipped" markers live in a generic repo? (killhouse ADRs are terse single-paragraph files — may need an optional `status:`/`implementation_status:` frontmatter convention, kept optional so the loop degrades to "treat all as accepted" without it.)
- Should `VALIDATE` cache prior results to show *newly-appeared* drift since the last run (a drift changelog), or always report absolute state? (Absolute is simpler; a diff-since-last-run is a nice v2.)
- Cost control on large repos: cap the reverse pass (pattern scan) by directory/priority, and `log()` what was skipped rather than silently truncating.

## Provenance

Idea adapted from `sdlc` v1.2.1 `/sdlc validate` (three-tier matching hierarchy, the confirmed/drift/needs-input/expected-gaps/undocumented buckets, and the advisory draft-ADR + code→ADR passes). Killhouse contribution: make it provider-agnostic, file-first, subagent-delegated with context hygiene, and give it falsifiable acceptance gates in the Killhouse idiom.
