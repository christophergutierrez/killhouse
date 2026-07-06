# Iterative Document Review Skill

## Overview

Multi-round document review using parallel subagents for critique and a top-tier model for editing and orchestration. Each round runs nine specialized reviewers: six narrative dimensions (grammar, concision, structure, argument integrity, internal consistency, altitude and framing) and three computational dimensions (an arithmetic verifier that computes rather than reads, a cross-document checker that catches contradictions across related files, and an assumption auditor that surfaces implicit inputs to every derivation). Runs until changes are minor or the maximum loop count (10) is reached. When called from Killhouse, this is a heavy loop: run it as delegated orchestration when the runtime supports delegation, and return only the reviewed artifact path, verdict, rounds used, and open questions to the caller.

## Prompt

```
Review and iteratively improve a document through parallel critique and revision cycles.

### Output Constraints (apply every round)

For artifacts whose contract requires ASCII-only output, the reviewed document must contain only standard 7-bit US-ASCII (code points 0x00-0x7F; in practice the printable range 0x20-0x7E plus newline and tab). Human-facing repository docs may keep intentional non-ASCII typography unless their own contract says otherwise. When ASCII-only applies, never use extended or high ASCII (0x80-0xFF) or any other non-ASCII character. Replace, every round, any of the following with its ASCII equivalent:

- Smart / curly quotes: straight `'` and `"`
- Em dash and en dash: rewrite the sentence to remove the dash (use a comma, colon, semicolon, parentheses, or two sentences). Do not substitute `--`; a dash is not required punctuation and should simply be written around.
- Ellipsis character: `...`
- Multiplication sign: `x`
- Non-breaking space: regular space
- Accented or other special letters: nearest plain ASCII letter

When enabled, this constraint is non-negotiable and survives every edit: if a revision introduces a non-ASCII character, the next round must remove it. Verify with `grep -nP '[^\x00-\x7F]' <file_path>` returning no matches.

### Roles

- **Reviewers (subagents)**: Nine parallel subagents, each reviewing a single dimension. They receive the current document (and all related documents for dimension 8) and return only findings; they never edit. Dimensions 1-5 are mechanical enough for a mid-tier model. Dimension 6 (Altitude & framing) is the hardest judgment and should run on a top-tier model. Dimensions 7-9 are mid-tier but require explicit computation or enumeration, not just reading.
- **Editor / orchestrator (top-tier model)**: Reads all reviewer feedback, triages it (accept, reject, or adapt), applies edits, and decides whether to loop again. The editor uses judgment, and not every finding warrants a change. In Killhouse pipeline runs, this is a delegated orchestrator when the runtime supports delegation (see Execution Modes).

**Model tiers**: Reviewers should be a good but not top-tier model (for example, Anthropic's Sonnet or OpenAI's mini tier); use the equivalent mid-tier model from whichever provider you run. The one exception is the Altitude & framing dimension, which is a top-tier task and should run on the most capable model even though it is launched alongside the mid-tier reviewers. The editor / orchestrator should also be the provider's most capable model (for example, Anthropic's Opus or OpenAI's flagship), since triage, rewriting, and convergence judgment are the harder tasks.

### Execution Modes

**Default for Killhouse pipeline runs (delegated orchestration)**: The caller hands the entire loop to a top-tier orchestrator subagent and gets back only a reviewed artifact path, verdict, rounds used, and open questions. Use this when called from `ask-kh`, when reviewing a PRD before `PLAN`, or when the caller is itself running inside a larger loop.

**Standalone fallback (in-session orchestration)**: The caller's own session plays the orchestrator only when delegation is unavailable or the user explicitly asks for an inline standalone document polish pass. It launches reviewer subagents in parallel when possible, edits, and loops. Record this as runtime degradation because the caller's context grows with the work.

When a user asks to run the orchestrator as a subagent, resolve what that means on the current runtime before starting:

1. Determine whether this runtime lets a subagent spawn its own subagents (nested agents).
2. If nesting is supported, the orchestrator spawns the reviewer subagents and runs them in parallel, exactly like the default but one level down.
3. If nesting is not supported (the common case), the orchestrator runs the review dimensions itself, sequentially or batched into a single pass. The caller still stays lean; the only loss is reviewer parallelism.
4. If you cannot tell which applies, ask the user whether they want true parallel reviewers or a lean caller with inline reviews, rather than guessing.

In every delegated run the orchestrator returns a lean result to the caller: reviewed artifact path, verdict, rounds used, short changelog, and any open questions. Never return reviewer transcripts or raw round output. When the orchestrator spawns reviewer subagents, log each delegation per `loops/DELEGATION_LOG.md`; that is data collection only and never changes tier selection.

### Review Dimensions

Launch all nine subagents in parallel each round. Dimensions 1-6 read the document narratively; dimensions 7-9 compute or enumerate, catching errors that narrative reading misses:

1. **Grammar & mechanics**: spelling, punctuation, tense consistency, subject-verb agreement, and standard-ASCII-only characters. Flag every non-ASCII character (smart quotes, em/en dashes, ellipsis, multiplication sign, accented letters, non-breaking spaces) and give the ASCII replacement (`'`, `"`, `...`, `x`, plain space); for dashes, rewrite the sentence to remove them rather than substituting `--`. Not style preferences.
2. **Concision**: redundant sentences, cross-section repetition of the same fact, phrases that can be cut without losing meaning. Flag only material verbosity, not tight prose.
3. **Structure & flow**: section ordering, forward/back references, orphaned sections, whether a cold reader can follow the document top to bottom without confusion.
4. **Argument integrity**: overgeneralized claims, unsupported causal statements, single-run results presented as definitive, numbers asserted without derivation, hedging that should be quantified.
5. **Internal consistency**: numbers in prose matching tables, cross-references resolving to existing sections, config labels used uniformly, derived stats arithmetically correct, no stale content from prior edits.
6. **Altitude & framing**: the document's biggest-picture choices. Does the title match the body? Is the central thesis the right one? Are the key concepts named with the most accurate term (for example, "context window" rather than "memory")? Is there a sharper frame that would serve the reader better? This dimension is divergent rather than convergent, so it is bound by the thrash rules in Convergence: propose a reframing only when it is a clear improvement, never re-open a framing an earlier round already settled, and escalate high-stakes or irreversible calls (title, thesis, terminology, rename) instead of oscillating on them.
7. **Numbers/arithmetic**: Enumerate every numerical claim and verify it by computation, not by reading. For each number: (a) if derived from other values in the document, perform the arithmetic and report any discrepancy; (b) if a statistical claim (sample size, confidence interval, percentage, rate), compute the appropriate bound or verify the percentage; (c) if a table or list where items should sum to a stated total, add them up and flag any mismatch. Do not accept approximation language as a shield; check that stated approximations are in the correct order of magnitude. Report each error with the correct computed value. If the document contains no numerical claims, return "no numerical claims to verify."
8. **Cross-document consistency**: Only active when multiple documents are provided. Read all provided files and check: (a) the same figure or claim appears consistently across documents; (b) terminology for the same concept is uniform; (c) architectural or design claims do not contradict each other. If only one document is provided, return "single document, cross-document check not applicable." This dimension receives all file paths in its prompt, not just one.
9. **Assumption auditor**: Enumerate every assumption embedded in a derivation or empirical claim. For each: (a) is it stated explicitly or left implicit? (b) is it validated in the document or asserted without basis? (c) would a materially different but plausible assumption change the document's central conclusion? Focus on load-bearing assumptions only. The editor should pass a one-line statement of the document's central thesis to this reviewer so it can judge what counts as load-bearing. Report as: "IMPLICIT ASSUMPTION: [what is assumed] in [claim]. Impact if wrong: [how conclusion changes]. Fix: [state explicitly or validate]."

### Subagent Prompt Template

Each subagent receives:

```
Round {N} {dimension} review of {file_path} (for dimension 8, {all_file_paths}). {N-1} rounds of fixes already applied. Only flag genuine {dimension-specific scope}. Numbered list of issues with quotes and fixes, or "{no issues response}."
```

The "N-1 rounds already applied" framing prevents re-flagging fixed issues. In later rounds, include a brief summary of what prior rounds already addressed for that dimension so the reviewer focuses on what remains.

### Editor Protocol

After receiving all nine reviews:

1. **Triage**: Categorize each finding as accept (clear improvement), adapt (valid point but different fix than suggested), or reject (style preference, overreading, or already addressed by existing text).
2. **Apply edits**: Make all accepted/adapted changes in a single pass. Read the relevant sections before editing to avoid stale-context mistakes.
3. **Normalize to ASCII**: After applying edits, scan the full document with `grep -nP '[^\x00-\x7F]' <file_path>` and replace every non-ASCII character with its ASCII equivalent (see Output Constraints). Do this every round so non-ASCII never accumulates, including any the editor's own edits introduced.
4. **Escalate high-stakes calls**: Apply the autonomous changes directly (grammar, concision, structure, consistency, ASCII). For an irreversible or voice-defining change from the Altitude & framing dimension (a title or thesis change, a terminology shift applied across the document, a file rename, or any change you are not confident about), apply it only when confidence is high; otherwise leave the text unchanged and record the recommendation in the summary for a human decision. Never make an irreversible change on low confidence without surfacing it first.
5. **Summarize**: Brief list of what changed, what was rejected with reasoning, and any recommendations bubbled up for a human, so the next round's reviewers (and the user) can track convergence. Include a count of substantive changes applied this round so the convergence check has a clean signal.

### Convergence

- **Stop when**: All nine reviewers return "no issues" or equivalent, OR only style-preference-level feedback remains that the editor judges not worth changing. Use verdict `CONVERGED`.
- **Maximum loops**: 10. This is a hard cap, not a target: never exceed 10 rounds even if reviewers still have suggestions. If the loop reaches this cap with material findings still open, stop with verdict `MAX_ROUNDS`.
- **Open questions**: If only human decisions remain, stop with verdict `OPEN_QUESTIONS` and list the exact decisions needed.
- **Blocked**: If the document cannot be reviewed safely because required inputs are missing, referenced docs cannot be read, or edits would cross a scope boundary, stop with verdict `BLOCKED`.
- **Thrash detection (required whenever a divergent dimension is active, primarily Altitude & framing but also any reviewer that can reasonably flag different items each round)**: because divergent dimensions can keep producing new suggestions indefinitely, watch for oscillation and stop feeding them. Treat any of the following as thrash, then freeze the contested span: the same span is edited and then reverted across rounds (A to B back to A), net change size stops shrinking from one round to the next, the same finding is raised and rejected more than once, or a round's reframing reverses a reframing an earlier round already settled. On detected thrash, stop editing that span, record it as an open question, and bubble it up instead of looping on it further.
- **Escalation pattern**: early rounds typically produce structural and framing changes; later rounds focus on precision and consistency before reaching diminishing returns. If the editor is making fewer than 3 substantive changes per round, consider stopping.

### What Makes This Work

- **Parallel independent reviewers** catch issues that a single pass misses; the grammar reviewer doesn't trade off against argument integrity.
- **Mid-tier for critique, top-tier for editing** uses the faster, cheaper model's speed and precision for focused single-dimension review while reserving the most capable model for the harder judgment calls of triaging conflicting feedback and rewriting.
- **The editor rejects findings**: reviewers will sometimes flag correct prose as problematic, request excessive hedging, or suggest changes that introduce new issues. The editor must push back.
- **Round context in prompts** prevents reviewers from re-litigating resolved issues and focuses them on what remains after prior fixes.
- **Dimensions 7-9 compute, not read**: the arithmetic, cross-document, and assumption dimensions do not assess quality narratively; they enumerate and verify. This catches errors that narrative reviewers miss even when attentive.

### Final Output

Return only this handoff shape to the caller:

```yaml
artifact: path/to/reviewed-document.md
verdict: CONVERGED | OPEN_QUESTIONS | MAX_ROUNDS | BLOCKED
rounds_used: 0
changes_summary:
  - short accepted/adapted change
open_questions:
  - decision needed, or []
handoff:
  next: loops/PLAN | caller
  reason: why this document is ready, blocked, or waiting
```

`CONVERGED` hands the reviewed PRD to `loops/PLAN`. `OPEN_QUESTIONS`, `MAX_ROUNDS`, and `BLOCKED` return to `ask-kh` for the pipeline's autonomy gate. Include raw command output only when it is direct evidence for an open question or blocked state, and keep it brief.
```
