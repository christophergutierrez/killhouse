---
name: grill-with-docs
description: Front-load alignment for a major change through a relentless interview that also builds docs (ADRs and a glossary) as you go. Use at the start of the Killhouse flow, after triage classifies a request as major, to capture everything the pipeline needs to run unattended.
---

Run a `/grilling` session, using the `/domain-modeling` skill.

## Killhouse handoff

> Vendored from `mattpocock/skills` (MIT — see `skills/THIRD-PARTY-LICENSE-mattpocock.txt`) and adapted for Killhouse; customize freely.

This is the human-alignment stage and the pivot point of the pipeline: it runs **in the main chat** (the
interview is interactive, not delegated to a subagent), and everything it captures in `CONTEXT.md` and the
ADRs is what lets the later loops run without stopping to ask you. Grill hard here — a shallow grilling is
what forces Autopilot to interrupt you later.

When the interview reaches convergence, do **not** proceed silently. Return to `ask-kh`'s **post-grill gate**
and ask the two questions that set the rest of the run:

1. **Ready for the PRD?** (or another grilling pass)
2. **Checkpoint or Autopilot?** (stop at each stage, or run to completion)

On "ready + mode chosen," `ask-kh` advances to `/to-prd`.
