# VALIDATE: Standing ADR/Code Drift Audit Loop

## Overview

A standing, change-independent audit that checks whether the codebase still matches its accepted
ADRs, in both directions, and reports drift. Run any time, independent of any single change. It is
**standalone maintenance, not part of the per-change pipeline** (triage to architecture). It
complements the change-time gauntlet; it does not replace any stage of it.

This is a heavy loop: run it as delegated orchestration when the runtime supports delegation, and
return only the report artifact path plus a machine-readable verdict block to the caller. When this
loop spawns role subagents, log each delegation per `loops/DELEGATION_LOG.md`; that is data
collection only and never changes tier selection.

The mechanical grep/parse/search passes are delegated to `bin/adr_drift.py`, a standard-library-only
helper that emits JSON. The loop consumes that JSON, applies judgment to the findings, works the
Needs-input list interactively, and produces the report. The helper is deterministic for the same
tree and inputs; the loop's judgment layer is where blocking-severity calls live.

## What it is NOT

- Not `bin/killhouse_gate_replay.py`: gate_replay re-runs a plan's acceptance gates; VALIDATE checks
  ADR/code consistency, which no gate necessarily covers.
- Not `CODE_REVIEW_TRIBUNAL`: the tribunal reviews a diff for quality/correctness; VALIDATE audits
  the whole tree against decisions.
- Not `ARCHITECTURE_DESIGN`: that checks depth/boundary/domain on a change's scope; VALIDATE checks
  decision-conformance across the repo over time.

## Inputs

- **ADRS_PATH**: where accepted ADRs live. Default: `docs/adr/`. Must not assume a specific store;
  accept a glob. When no ADRs exist, the loop emits an empty report with verdict `PASS`.
- **SOURCE_ROOT**: codebase root to audit. Default: repo root.
- **CONTEXT_DOCS**: glossary, PRDs, feature designs used as bridges between an ADR and code. An ADR
  often names a concept the code implements under a different literal string; a context doc links
  them. These bridge ADR terminology to the literal strings the code uses.
- **TEST_COMMANDS**: optional; used only to confirm a claimed behavior is exercised, never required.
- **MODE**: `report` (default) | `report-and-file` (open a finding/TODO per drift).
- **OUTPUT_PATH**: where to write the report artifact. Required in `report-and-file` mode.

## Modes

- **report** (default): emit the report artifact and verdict block. Does not mutate any files.
- **report-and-file**: emit the report and write one finding/TODO per drift under `OUTPUT_PATH` (or
  a TODO directory). The helper writes only under an explicit output path; it never mutates source.

## Verdicts

- `PASS`: no drift, no blocking findings. Expected gaps and advisory undocumented findings may be
  present and are listed but do not affect the verdict.
- `PASS_WITH_FINDINGS`: drift or needs-input findings exist, but none are blocking.
- `BLOCKING_DRIFT`: at least one accepted ADR marked `shipped` + `load_bearing: true` is in the
  `drift` bucket (contradiction or absence).
- `NEEDS_INPUT`: one or more ADRs are in `needs_input` and require human adjudication before the
  audit can converge. Worked interactively one ADR at a time after the report.
- `BLOCKED`: the audit cannot run safely (missing inputs, unreadable ADRs, scope boundary crossed).

## Buckets

Canonical machine-readable form is snake_case. Title Case is allowed in the human report only.

- `confirmed`: executable source evidence found for the ADR's terms or bridged patterns.
- `drift`: a direct contradiction: the ADR declares concrete forbidden terms/patterns and they
  appear in executable source. A shipped, load-bearing ADR with no source evidence is also drift,
  because the implementation was expected but cannot be found. Blocking only when the ADR is
  `shipped` + `load_bearing: true`.
- `needs_input`: no evidence found and the ADR's implementation status is `unknown` or `partial`.
  Surface to the human: is this planned, partially implemented, or conceptual-only?
- `expected_gap`: no evidence found and the ADR is marked `planned`. Not drift, not noise.
- `not_applicable`: the ADR is marked `conceptual`. No code evidence is expected.
- `undocumented`: a load-bearing code pattern with no covering ADR. Advisory only, non-blocking in
  v1.
- `draft_adr_conflicts`: code that already contradicts a non-accepted (draft/in-review) ADR.
  Advisory only.

## Evidence separation

The helper distinguishes executable-source matches from comments/docs matches. A term that appears
only in `.md`, `.txt`, or comment lines must not produce `confirmed`. This guards against grep
matching its own citation: an ADR that cites a term in prose, and that prose is the only place the
term appears, is not confirmed.

## Capability Tiers (provider-agnostic)

- **fast**: the grep/term-extraction/inventory passes (run by `bin/adr_drift.py`).
- **standard**: bridging ADR intent to code via context docs, pattern recognition in the reverse
  pass.
- **reasoning**: final drift judgment, blocking-severity calls, the interactive Needs-input
  adjudication.

Run passes as parallel subagents when supported; degrade to labeled inline passes otherwise. No
model-tier map means current-model-only; tier labels document intent.

## Core algorithm

For each accepted ADR, walk a matching hierarchy in order, stopping at the first tier that yields
evidence:

1. **Context-doc bridge**: if a context doc links to the ADR, extract its concrete file references
   and named patterns; search executable source for those. Match to `confirmed`.
2. **Direct ADR terms**: extract concrete terms from the ADR body (library names, endpoint names,
   schema objects, config keys, named patterns) and search executable source. Match to `confirmed`.
3. **No match**: bucket by the ADR's `implementation` field:
   - `conceptual` to `not_applicable`.
   - `planned` to `expected_gap`.
   - `partial` or `unknown` to `needs_input`.
   - `shipped` + `load_bearing: true` to `drift` when source evidence is absent or a forbidden term is
     found in source.
   - other `shipped` ADRs to `needs_input` when source evidence is absent.

Then two advisory passes (lower confidence bar, surface possibilities):

4. **Draft-ADR conflict pass**: for non-accepted ADRs, search for code that already contradicts the
   emerging decision. Surface as `draft_adr_conflicts`.
5. **Code-to-ADR reverse pass**: scan source for load-bearing patterns (declared via context docs
   or a `load_bearing_patterns` frontmatter field) and check whether any accepted ADR covers them.
   Uncovered patterns to `undocumented` (candidate for a new ADR). Advisory, non-blocking in v1.

## Context Hygiene

This loop runs as a delegated subagent by default so the caller's session stays lean. The helper's
JSON output is the evidence substrate; the loop cites stable evidence from it without loading raw
grep output into the main session. Return only the report artifact path plus the machine-readable
verdict block. Never return raw grep output, per-ADR transcripts, or the loop's reasoning trace.

## Output Report Shape

Bucketed report, most-actionable first:

```
-- Definitive (accepted ADRs) --
Confirmed (N):        ADR-NNNN <title> -- <file:line evidence>
Drift (M):            ADR-NNNN <title> -- <what contradicts it>
Needs input (K):      ADR-NNNN <title> -- <why low-confidence>
Expected gaps (P):    ADR-NNNN <title> (marked planned)
Not applicable (Q):   ADR-NNNN <title> (marked conceptual)
-- Advisory --
Undocumented (R):     <pattern @ file> -- no covering ADR
Draft-ADR conflicts (J): ADR-NNNN <title> -- <conflicting code>
```

Append a machine-readable verdict block (below).

After the report, work the `needs_input` list interactively one ADR at a time: planned to mark it
planned; partial to re-search at the pointed location; conceptual-only to note, no code expected.

## Machine-Readable Verdict Block

```json
{
  "verdict": "PASS | PASS_WITH_FINDINGS | BLOCKING_DRIFT | NEEDS_INPUT | BLOCKED",
  "buckets": {
    "confirmed": 0,
    "drift": 0,
    "needs_input": 0,
    "expected_gap": 0,
    "not_applicable": 0,
    "undocumented": 0,
    "draft_adr_conflicts": 0
  },
  "blocking": false,
  "blocking_adrs": [],
  "staleness": { "head": "string", "discovered_at": "iso-8601" }
}
```

`blocking` is true when any accepted ADR in `drift` is marked `shipped` + `load_bearing: true`.

## Direct Invocation (generic/Codex agents)

VALIDATE is invocable standalone without the full change gauntlet. Run the helper directly:

```bash
python3 bin/adr_drift.py --adrs docs/adr/ --source-root . --context-docs CONTEXT.md --mode report
```

For `report-and-file` mode, pass `--out <path>`:

```bash
python3 bin/adr_drift.py --adrs docs/adr/ --source-root . --mode report-and-file --out TODO/adr-drift-findings/
```

The helper emits JSON to stdout (`report`). In `report-and-file`, `--out` may be a JSON file path or a
directory; directory output writes `adr-drift-report.json` plus one Markdown file per drift finding.
The loop consumes the JSON report and applies the judgment layer.

## Degradation

| Missing capability | Adaptation |
| --- | --- |
| No subagents | Run each ADR's match hierarchy as a labeled inline pass. |
| No ADRs at ADRS_PATH | Emit an empty report with verdict `PASS`. |
| Weak shell / no grep | Report-only from what can be read; mark unscanned areas as unverified, never as `confirmed`. |
| No VCS | Record a snapshot id instead of HEAD for the staleness line. |
| No model-tier map | Current-model-only; tier labels document intent. |

## Reverse-pass scope (v1)

Reverse scanning can become noisy on large repos. v1 caps scope by directory/priority and logs
skipped paths rather than silently truncating. Reverse-pass findings are advisory and non-blocking in
v1 unless a future ADR convention explicitly marks a pattern class as required.
