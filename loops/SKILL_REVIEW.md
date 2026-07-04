# Skill Review Loop

## Purpose

Review active agent-instruction documents as executable policy, not passive prose. This loop protects
Killhouse's skills, loop payloads, agent instructions, plugin manifests, and usage docs from routing
breakage, runtime drift, contradictory instructions, weakened gates, and examples that no longer work.

A good skill is a reusable capability that measurably improves agent performance on its intended tasks,
activates at the right time, and does not degrade unrelated work. Detail, ceremony, and subagent count
are not quality by themselves; they matter only when they improve outcomes, safety, or auditability.

Use this loop for changes to:

- `skills/**/SKILL.md` and skill-local reference files;
- `loops/**/*.md`;
- `AGENTS.md`, `README.md`, plugin manifests, marketplace manifests, and install docs;
- any document an agent is expected to execute as instructions.

Run until all Blocking findings are fixed, only accepted risks remain, or `MAX_PASSES` is reached.

## Inputs

- **TARGET_REPOSITORY**: Repository root.
- **SCOPE**: `wip` | `staged` | `all` | explicit file list. Default: `wip`.
- **MODE**: `review-only` | `converge`. Default: `review-only`.
- **RUNTIMES**: Runtime contracts to preserve. Default: `Claude Code`, `Codex`, and generic
  file-reading agents.
- **VALIDATION_COMMANDS**: Known commands to validate manifests and docs. May be empty.
- **EVAL_SCENARIOS**: Optional deterministic, read-only scenarios that exercise routing or output
  contracts. May be empty.
- **EVAL_MODE**: `none` | `design` | `run-readonly`. Default: `design`.
- **EVAL_REPETITIONS**: Repeated runs per scenario when nondeterminism matters. Default: `3` for
  trigger/routing evals, `1` for static validation.
- **MAX_PASSES**: Maximum review/fix passes. Default: `3`.

## Operating Principles

- Treat instruction files as executable behavior. A sentence that changes what an agent will do is a
  behavior change, not copyediting.
- Preserve existing runtime contracts unless the request explicitly changes them. Adding Codex support
  must not remove Claude Code slash-command behavior; adding Claude examples must not break generic
  file-resolution fallback.
- Findings must be concrete and actionable. Quote or point to the exact instruction, command, file path,
  manifest field, or missing reference that creates the failure.
- Mandatory gates are load-bearing. Never allow wording that lets Autopilot skip hard blockers, budget
  trips, staleness checks, non-vacuous gate checks, or human-confirmation boundaries.
- Prefer dual notation when needed: Claude Code slash commands as primary where they already exist, plus
  runtime-neutral skill names for Codex and generic agents.
- Do not flatten rigorous loop payloads into the caller context. Heavy loop instructions remain delegated
  artifacts; reviews return findings and verdicts only.
- Do not edit `lib/redqueen` as part of skill review unless the user explicitly scopes redqueen changes.

## Skill Quality Rubric

Evaluate changed skills and loops against these properties. This rubric is adapted for Markdown skills:
the boundary is the instruction contract and artifact handoff, not only a callable tool schema.

1. **Trigger clarity**: A fresh agent can tell when to use the skill, when not to use it, and which skill
   comes next. Descriptions use stable workflow language rather than synonyms for the same action.
2. **Novelty**: The skill encodes procedural, domain-specific, organization-specific, or workflow
   knowledge the base agent does not reliably apply unaided. Do not preserve instructions that merely
   restate generic reasoning, basic coding, or behavior already covered by another skill.
3. **Progressive disclosure**: Always-visible metadata stays small and precise; `SKILL.md` carries the
   executable workflow; long variants, examples, and background live in `references/`; deterministic or
   repeatedly recreated work lives in `scripts/`.
4. **Context economy**: The main session loads routing contracts and artifact pointers, not full loop
   payloads, reviewer transcripts, or raw command logs. Heavy behavior stays behind delegated loops.
5. **Reference integrity**: Every skill, slash command, loop name, artifact, relative link, and install
   command resolves or has an explicit runtime-specific fallback.
6. **Runtime preservation**: Existing supported runtimes keep their invocation form and install path.
   Runtime additions are additive unless the request explicitly removes support.
7. **Fail-safe boundaries**: Inputs, modes, autonomy choices, budgets, verdicts, and halt states are
   constrained by explicit enums or named states wherever practical. Invalid or unsupported states tell
   the agent how to recover.
8. **Output contract**: The skill or loop returns a concrete artifact, verdict, findings table, or next
   handoff. It does not end with vague completion language.
9. **Composability**: Scope boundaries and "when not to use" guidance prevent conflicts with adjacent
   skills. Multi-skill workflows have a clear owner, handoff, and conflict-resolution rule.
10. **Skill decomposition**: Large or branching skills split into focused child skills only when doing so
   reduces context load, improves reuse, clarifies activation, or isolates a reusable workflow. Parent
   skills own routing and state; child skills own one capability and return a clear artifact or verdict.
11. **Capability tiering**: Delegated roles declare the intended capability tier when tier matters,
   why that tier is needed, and how to degrade when model routing is unavailable. Use abstract tiers
   rather than provider-specific model names unless a runtime contract requires a named model.
12. **Execution policy clarity**: Cost and time optimization are routing strategies, not quality levels.
   Skills preserve `cost_optimized` and `time_optimized` terminology and keep quality gates identical.
13. **Exact model mapping**: Optional model-tier config is strict. If present, it defines exact model ids
   for `fast`, `standard`, and `reasoning`; agents must echo the resolved map and must not substitute
   nearby versions, families, providers, or "equivalent" models. Invalid config stops before the
   pipeline instead of silently falling back.
14. **Gate strength**: Mandatory stops, non-vacuous baseline checks, staleness checks, rollback rules,
   blast-radius decisions, and human-confirmation points remain enforceable.
15. **Eval readiness**: A deterministic, read-only scenario could verify the routing or output contract
   without relying on subjective prose judgment.

## Evaluation Model

When a change affects activation, routing, output contracts, or safety gates, design or run evals in
three modes:

| Mode | Measures |
| --- | --- |
| **Baseline**: skill unavailable | How well the agent performs naturally. |
| **Forced skill**: skill explicitly invoked | Whether the skill's loaded instructions improve execution. |
| **Automatic skill**: agent chooses whether to invoke it | Whether name, description, and routing work. |

Track these metrics when data exists:

```text
content_lift = forced_skill_pass_rate - baseline_pass_rate
routing_loss = forced_skill_pass_rate - automatic_skill_pass_rate
net_skill_lift = automatic_skill_pass_rate - baseline_pass_rate
variance_delta = baseline_pass_rate_stddev - skill_pass_rate_stddev
context_delta = skill_loaded_tokens - baseline_loaded_tokens
latency_delta = skill_duration_ms - baseline_duration_ms
overfit_gap = dev_pass_rate - held_out_pass_rate
```

Interpretation:

- Low or negative `content_lift`: the skill body is weak, overcomplicated, or harmful.
- High `content_lift` plus high `routing_loss`: the skill is useful but its name, description, or trigger
  examples need work.
- Low or negative `net_skill_lift`: the skill should be rewritten, merged into another skill, narrowed,
  or deleted.
- Positive `variance_delta`: the skill made execution more consistent. Negative `variance_delta`: the
  skill increased nondeterminism and needs simplification or tighter contracts.
- Large positive `context_delta` or `latency_delta` with little pass-rate lift: the skill is too expensive
  for the value it creates.
- Large `overfit_gap`: the skill was tuned to examples instead of capturing a general policy.

For early Killhouse work, do not require a large benchmark suite. Prefer 3-10 deterministic read-only
cases that catch routing, gate, or output-contract regressions. Grow to larger suites only for stable,
frequently used skills.

Use held-out scenarios when iterating on a skill. Tune wording on a small development set, then judge on
queries the author did not use while editing. For trigger evals, include near-miss negatives with shared
keywords or adjacent workflows; obviously unrelated prompts do not prove much.

Use ablation for bloated or contested sections: remove or disable one instruction section, rerun the
same scenarios, and keep the section only if pass rate, safety, variance, or efficiency gets worse
without it. If ablation has no measurable effect, the section is context cost without policy value.

Safety is a gate, not a score. Any critical safety failure disqualifies the change until fixed:

- destructive action outside declared scope;
- secret leakage or accidental credential exposure;
- silently ignoring failed validation;
- claiming success when gates or tests failed;
- modifying unrelated files;
- bypassing required approval;
- inventing evidence, citations, command output, or artifact paths;
- continuing after prerequisites are missing.

## Severity Rubric

- **Blocking**: Would cause a runtime to miss or misinvoke a skill; points to a missing file, command,
  loop, manifest, or impossible install path; weakens a mandatory gate; creates contradictory autonomy or
  budget behavior; changes Claude slash-command behavior while adding another runtime; omits a concrete
  output/verdict contract for an executable stage; delegates to another skill without a clear handoff
  contract and loses required state/artifacts; assigns safety, synthesis, final approval, or mandatory-gate
  judgment to an underpowered tier in a way that could produce an unsafe pass; creates any critical safety
  failure; or makes a loop unsafe to execute.
- **Material**: Ambiguous routing, stale examples, unclear runtime branch, weak handoff contract,
  unvalidated manifest field, unsupported but non-critical command, missing eval scenario for a changed
  routing contract, unnecessary context load in the main session, a large skill with separable branches
  that should be split into focused skills, missing capability tier for a role where tier matters,
  expensive/reasoning-tier delegation for mechanical work without justification, missing model-routing
  fallback, inline work chosen without a brief justification where delegation would preserve context,
  execution-policy wording that implies different quality gates for cost/time modes, loose model-tier
  mapping that permits aliases or unreported substitutions,
  or wording likely to make agents over- or under-apply a stage.
- **Minor**: Non-blocking clarity, naming consistency, discoverability, or formatting issue that does not
  change execution semantics.

## Roles

Use subagents when the runtime supports them. Run reviewers independently and in parallel where possible.
If subagents are unavailable, run each role inline as a labeled pass.

Default capability tiers:

| Role | Tier | Why |
| --- | --- | --- |
| Invocation & Routing Reviewer | `fast` | Path, command, link, and artifact checks are bounded inventory work. |
| Runtime Compatibility Reviewer | `standard` | Requires comparing runtime contracts and examples across files. |
| Instruction Conflict Reviewer | `reasoning` | Must reconcile contradictory instructions, autonomy, budgets, and gates. |
| Gate & Safety Reviewer | `reasoning` | Must judge whether mandatory gates remain non-vacuous and fail-safe. |
| Active-Doc Clarity Reviewer | `standard` | Requires executable-instruction review but not final safety judgment. |
| Context & Output Contract Reviewer | `standard` | Requires routing and handoff analysis across instruction surfaces. |
| Novelty & Progressive Disclosure Reviewer | `standard` | Requires value and context-placement judgment. |
| Composability & Decomposition Reviewer | `reasoning` | Must judge boundaries, ownership, and skill-splitting tradeoffs. |
| Capability Tiering Reviewer | `reasoning` | Must judge underpowered safety work and overpowered mechanical work. |
| Manifest & Install Reviewer | `fast` | JSON, manifest, install, and validator checks are mostly mechanical. |
| Scripts & References Reviewer | `standard` | Requires dependency, determinism, and reference-path judgment. |
| Eval Readiness Reviewer | `standard` | Requires scenario design and pass/fail-contract analysis. |
| Efficiency & Ablation Reviewer | `standard` | Requires cost/value judgment and ablation proposal. |
| Synthesis Editor | `reasoning` | Owns severity calibration, deduplication, final verdict, and accepted risks. |

Fallback for every role: if model routing is unavailable, run the role with the current model and record
`capability_tiering: current-model-only` and `model_routing: unavailable` in the verdict.

- **Invocation & Routing Reviewer**: Verifies every slash command, skill name, loop name, relative link,
  and artifact path resolves to an actual file or documented runtime command.
- **Runtime Compatibility Reviewer**: Checks Claude Code, Codex, and generic file-reading behavior. Flags
  runtime-specific wording that displaced another supported runtime.
- **Instruction Conflict Reviewer**: Finds contradictory ordering, autonomy, budget, delegation, or
  mandatory-gate instructions across changed files and their nearest callers.
- **Gate & Safety Reviewer**: Audits mandatory stops, staleness checks, blast-radius gates, non-vacuous
  gate rules, rollback boundaries, and redqueen fallback behavior for weakening or bypass.
- **Active-Doc Clarity Reviewer**: Checks whether instructions are imperative, scoped, testable, and
  executable by a fresh agent. Flags passive descriptions where a command contract is needed.
- **Context & Output Contract Reviewer**: Checks trigger clarity, context economy, output artifacts,
  verdict enums, handoff shape, and whether invalid states tell the agent how to recover.
- **Novelty & Progressive Disclosure Reviewer**: Checks whether changed instructions add non-obvious
  policy value, avoid duplicating base-model knowledge or other skills, and place long details in
  references or scripts instead of always-loaded surfaces.
- **Composability & Decomposition Reviewer**: Checks adjacent skills for overlapping triggers, unclear
  ownership, handoff conflicts, duplicated instructions, missing "when not to use" boundaries, and
  branches that should be split into focused child skills or merged back into a driver skill.
- **Capability Tiering Reviewer**: Checks role-to-tier assignments, underpowered safety or synthesis
  work, overpowered mechanical work, provider-neutral tier labels, and fallback behavior when model
  routing is unavailable.
- **Manifest & Install Reviewer**: Validates plugin manifests, marketplace files, install/update commands,
  restart/new-session guidance, and optional dependency branches.
- **Scripts & References Reviewer**: Checks optional scripts, references, and assets for relative paths,
  dependency declarations, deterministic behavior, error handling, and one-hop discoverability from
  `SKILL.md`.
- **Eval Readiness Reviewer**: Proposes or checks deterministic, read-only scenarios for changed routing
  or output contracts. Flags gaps when a high-risk instruction change has no objective way to verify it.
- **Efficiency & Ablation Reviewer**: Checks whether changed instructions reduce rediscovery, token load,
  latency, retries, or variance. Proposes ablations for sections whose value is unclear.
- **Synthesis Editor**: Deduplicates findings, assigns severity, selects fixes in `converge` mode, runs
  validation commands, and emits the verdict.

## Scope Discovery

Identify the repository root:

```bash
git rev-parse --show-toplevel
```

For `wip` scope:

```bash
git diff --name-only HEAD
git ls-files --others --exclude-standard
```

For `staged` scope:

```bash
git diff --cached --name-only
```

For `all` scope, include active instruction surfaces:

```bash
find skills loops -type f
printf '%s\n' AGENTS.md README.md .claude-plugin/plugin.json .claude-plugin/marketplace.json .codex-plugin/plugin.json
```

Filter to existing files. Include related caller/callee files for changed instructions:

- if `skills/ask-kh/SKILL.md` changes, include referenced `skills/*/SKILL.md` and all `loops/*.md`;
- if a loop changes, include `skills/ask-kh/SKILL.md` and any docs that describe the pipeline;
- if install docs or manifests change, include `.claude-plugin/*`, `.codex-plugin/*`, `README.md`,
  `AGENTS.md`, and `skills/install-killhouse/SKILL.md`.

## Required Checks

Run what is available and record unavailable tools as risks, not silent skips.

### Reference Resolution

- Every `/name` command intended as a Killhouse skill resolves to `skills/<name>/SKILL.md`.
- Every bare skill name used as an invocation target resolves to `skills/<name>/SKILL.md`.
- Every `loops/NAME` or `NAME.md` loop reference resolves to `loops/<NAME>.md`.
- Relative Markdown links resolve from their containing file.
- Mentioned artifacts have clear producer and consumer stages.

### Runtime Compatibility

- Claude Code examples keep slash-command forms where they existed: `/ask-kh`, `/triage`,
  `/grill-with-docs`, `/grilling`, `/domain-modeling`, `/to-prd`.
- Codex instructions use skill names or plugin install language appropriate to Codex.
- Generic fallback remains: read `SKILL.md`/`loops/*.md` directly and run shell commands.
- Runtime-specific fields are either accepted by that runtime or documented as runtime-specific.

### Context & Output Contracts

- Skill frontmatter descriptions are short enough to act as triggers and specific enough to avoid
  accidental invocation. They say what the skill does, when to use it, and the most important "when not
  to use it" boundary when near-miss skills exist.
- Heavy loop content is referenced by file path and delegated when possible; main-session skills do not
  inline reviewer rosters, pass transcripts, or raw command output unnecessarily.
- Each executable stage has a named output: artifact path, verdict, findings table, handoff line, or
  machine-readable block.
- Modes, verdicts, halt states, and budget settings use explicit names. Unsupported states produce a
  clear recovery action instead of leaving the agent to infer behavior.

### Novelty & Progressive Disclosure

- Each major instruction earns its place by improving routing, safety, output quality, robustness, or
  efficiency beyond what the base agent would reliably do.
- Generic advice, repeated policy, and duplicated neighboring-skill instructions are removed, linked, or
  factored into a shared reference.
- `SKILL.md` remains the executable workflow. Long examples, variants, background, and checklists move to
  `references/` with a clear pointer from the skill.
- Deterministic transformations, validations, or repeatedly recreated code move to `scripts/` when a
  script would reduce tokens, errors, or latency.
- References stay one hop from the skill unless there is a strong reason; long references include a table
  of contents or routing note so the agent reads only the needed section.

### Composability & Boundaries

- Adjacent skills do not compete for the same prompt without a clear priority or handoff.
- A skill's description and body state its scope narrowly enough that it can compose with other skills.
- Multi-skill workflows identify the driver skill and which artifacts flow between stages.
- "When not to use" guidance is required when a plausible near-miss skill exists.
- Shared instructions are linked or centralized rather than copied into multiple skills.

### Skill Decomposition & Handoffs

- Prefer a driver skill when one workflow routes through multiple focused capabilities. The driver owns
  classification, state, autonomy, and stage sequencing; child skills own one reusable capability.
- Break a skill apart when a branch has its own trigger, artifact, reference set, validation rules, or
  reusable workflow, and splitting would reduce context load or improve activation accuracy.
- Do not split merely to create ceremony. Keep a branch inline when it is short, not reusable, and tightly
  coupled to the parent workflow.
- Every skill-to-skill handoff names the target skill, when to invoke it, what inputs/context it receives,
  what artifact/verdict it returns, and who resumes control afterward.
- Child skills must not silently mutate parent state. They return artifacts or decisions that the driver
  records explicitly.
- If a skill delegates to another skill in Claude slash-command form, include the equivalent Codex/generic
  skill-name fallback when those runtimes are supported.

### Capability Tiering & Model Routing

- Use abstract capability tiers for delegated work:
  - `fast`: bounded search, inventory, formatting checks, static validation, and other mechanical work.
  - `standard`: repository analysis, implementation, ordinary review, and routine synthesis.
  - `reasoning`: safety decisions, architecture tradeoffs, conflict triage, final verdicts, and mandatory
    gate judgment.
- Roles that spawn or imply subagents declare `Tier`, `Why`, and `Fallback` when tier materially affects
  cost, safety, or quality.
- Do not require provider-specific model names unless a runtime integration actually supports and needs
  them. Prefer capability intent over model branding so Claude Code, Codex, and generic agents can adapt.
- If `.killhouse/config.json` or `.killhouse/config.local.json` defines model tiers, validate that all
  three tiers exist as non-empty strings and treat each value as an exact opaque runtime id. Do not
  substitute model names. Echo the resolved map before use. If the config is invalid, require a stop
  until the user fixes or removes it.
- Flag reasoning-tier agents assigned to mechanical validation or file inventory as Material unless the
  risk profile justifies the cost.
- Flag fast/low-capability agents assigned to safety gates, synthesis, final approval, or architecture
  decisions as Blocking when that assignment could produce an unsafe pass.
- If model routing is unavailable, the current model may run every role, but the verdict records the
  degradation rather than pretending tiering happened.
- Prefer delegation when a task can be handed off cleanly without losing required context. Keep work
  inline only when it is truly trivial, tightly coupled to the current reasoning, or the handoff
  overhead is clearly higher than the work itself. Any inline assignment in a matrix or milestone
  block should include a brief justification.
- Example role declaration:

```markdown
- **Gate Auditor**
  - Tier: `reasoning`
  - Why: Must judge whether gates are non-vacuous and safety criteria hold.
  - Fallback: If model routing is unavailable, run with the current model and record
    `gate_audit: inline/current-model`.
```

### Execution Policy

- Preserve the policy names `cost_optimized` and `time_optimized`.
- Treat execution policy as a cost/time routing choice, not a quality setting. Gates, mandatory stops,
  review standards, and final verdicts stay the same in both modes.
- `cost_optimized` may try cheaper tiers first only for bounded, reversible work with objective gates
  and explicit escalation triggers.
- `time_optimized` may choose stronger tiers earlier to reduce wall-clock time and failed attempts, but
  should still delegate mechanical checks and independent review to cheaper tiers where safe.
- Flag provider-specific examples in core instructions unless they are clearly marked as examples or
  runtime-specific mappings.

### Gate Integrity

- Autopilot skips only courtesy checkpoints, never mandatory gates.
- Budget guard trips degrade to Checkpoint mode and ask.
- PLAN blast-radius `BLOCKED`, IMPLEMENT_MILESTONE `STALE`/`VACUOUS_GATE`/`BLOCKED_DEPENDENCY`,
  unfixable tribunal findings, and architecture safety gates still halt.
- TDD, non-vacuous baseline, staleness, rollback, and tracer-bullet requirements remain enforceable.

### Manifest & Install Validation

Prefer official runtime validators when available:

```bash
claude plugin validate .
python3 -m json.tool .codex-plugin/plugin.json
python3 -m json.tool .claude-plugin/plugin.json
python3 -m json.tool .claude-plugin/marketplace.json
```

If a Codex plugin validator is available, run it. If it is unavailable, validate the JSON shape and record
the missing validator in the verdict.

### Eval Readiness

For changed skill or loop contracts, propose or run deterministic read-only scenarios. Prefer a small
matrix over broad prose review:

- 3-5 scenarios for a localized skill edit;
- 5-10 scenarios for routing, runtime compatibility, or mandatory-gate changes;
- each scenario includes input prompt, mode (`baseline`, `forced`, or `automatic`), expected selected
  skill or loop when applicable, expected artifact/verdict shape, and hard pass/fail criteria.
- trigger evals include positive prompts and near-miss negative prompts, and should use repeated runs
  when the runtime's automatic skill selection is stochastic.
- scenario sets distinguish `dev` and `held_out` cases once wording has been tuned.

Examples:

```yaml
- id: codex-ask-kh-automatic-routing
  mode: automatic
  prompt: "Use ask-kh for this feature: add saved filters"
  expected_route: skills/ask-kh/SKILL.md
  expected_next_gate: triage classification
  pass_criteria: final response records classification and next stage without loading loop bodies
- id: ask-kh-forced-content
  mode: forced
  prompt: "Run skills/ask-kh/SKILL.md for this feature: add saved filters"
  expected_route: skills/ask-kh/SKILL.md
  expected_next_gate: triage classification
  pass_criteria: final response records classification, autonomy state, and next stage
- id: claude-slash-preserved-automatic
  mode: automatic
  prompt: "/ask-kh I want to add saved filters"
  expected_route: skills/ask-kh/SKILL.md
  expected_runtime_contract: Claude slash-command form remains documented
  pass_criteria: docs still show /ask-kh and /grill-with-docs for Claude Code
```

Do not require evals for every typo fix. Require them when a change affects invocation, routing,
autonomy, mandatory gates, manifests, or output contracts.

When evals are run, report baseline, forced, and automatic pass rates where available, plus
`content_lift`, `routing_loss`, `net_skill_lift`, variance/stddev when repeated runs exist, and token or
latency deltas when the runtime exposes them. When evals are only designed, report the scenario matrix
and the exact pass/fail checks needed to run them later.

### Efficiency & Ablation

- Measure cost per successful task when possible, not only average cost per run.
- Prefer bundled scripts or references when they prevent repeated rediscovery, but only if they reduce
  total tokens, latency, retries, or errors in practice.
- Track loaded context by tier: always-present metadata, triggered `SKILL.md`, and on-demand references
  or scripts. Metadata is the most expensive surface because it is considered before skill selection.
- Lean toward delegation when it preserves main-session context. Inline work should be the exception
  for trivial or tightly coupled tasks, not the default. Require a brief justification for any inline
  decision that could have been delegated cleanly.
- Flag repeated re-reading, repeated unchanged command runs, duplicate reviewer findings, and continued
  execution after the definition of done as thrash.
- For any long or rigid instruction section, propose an ablation unless the section is required for a
  safety gate or output contract.
- Prefer instructions that state intent and decision criteria over brittle keystroke-level procedures,
  unless exact commands are the contract being validated.

### Format & Resource Hygiene

- Skill frontmatter has `name` and `description`; the name matches the skill directory and runtime naming
  constraints.
- Referenced scripts, references, and assets exist at relative paths and are intentionally loaded only
  when needed.
- Scripts are deterministic for the same inputs when determinism is expected, declare required
  dependencies, emit actionable errors, and do not silently mutate out-of-scope files.
- Plugin manifests and marketplace entries point only to resources that exist in the repository.

## Finding Schema

```markdown
- id: stable-content-slug
  severity: Blocking | Material | Minor
  lens: InvocationRouting | RuntimeCompatibility | InstructionConflict | GateSafety | ActiveDocClarity | ContextOutput | NoveltyDisclosure | Composability | CapabilityTiering | ManifestInstall | ScriptsReferences | EvalReadiness | EfficiencyAblation
  location: path:line or section
  problem: Concrete executable-instruction failure.
  evidence: Exact text, command, path, or manifest field that proves the issue.
  impact: What agent behavior would break or become unsafe.
  required_change: Smallest change that preserves existing contracts.
```

Finding ids are content-based and stable across passes. Do not key ids to line numbers.

## Execution Loop

1. **Baseline**: Record VCS status and scope. Do not overwrite unrelated user changes.
2. **Scope Discovery**: Select changed files and related instruction surfaces.
3. **Validation Pass**: Run available manifest/reference checks and capture command outcomes.
4. **Skill Quality Pass**: Apply the Skill Quality Rubric to every changed active instruction surface.
5. **Independent Review**: Run reviewer roles over the scoped files. Reviewers return findings only.
6. **Synthesis**: Deduplicate by id, calibrate severity, reject style-only items, and produce a findings
   table.
7. **Converge**: If `MODE=converge`, fix Blocking findings only unless the user requested broader cleanup.
   Keep edits minimal and preserve existing runtime contracts. Re-run affected checks.
8. **Re-review**: Re-run reviewers on changed files plus related callers/callees. Classify findings as
   resolved, persisting, new, or regressed.
9. **Decide**:
   - `PASS`: no Blocking findings remain and validation commands either pass or have documented,
     non-blocking unavailability.
   - `FAIL`: Blocking findings remain.
   - `PASS_WITH_RISKS`: no Blocking findings remain, but validators/tools were unavailable or Material
     findings were accepted for later work.
   - `BLOCKED`: safe fix requires a human decision, missing runtime behavior, or scope expansion.

Stop at `MAX_PASSES`. Do not continue spending passes after the same finding regresses twice; report a
thrash halt as `BLOCKED`.

## Final Output

Return only:

- verdict: `PASS` | `PASS_WITH_RISKS` | `FAIL` | `BLOCKED`;
- scope reviewed;
- validation commands run and outcomes;
- findings table with severity, lens, location, problem, required_change, and status;
- skill-quality rubric results for changed active instruction surfaces;
- novelty, progressive-disclosure, composability, and skill-decomposition issues found or explicitly
  cleared;
- capability-tiering findings and runtime degradation recorded;
- eval scenarios run or proposed, with pass/fail criteria;
- eval metrics when run: baseline pass rate, forced pass rate, automatic pass rate, content_lift,
  routing_loss, net_skill_lift, variance/stddev, context_delta, latency_delta, overfit_gap;
- ablations run or proposed, with keep/remove rationale;
- files changed in `converge` mode;
- residual risks and the next recommended gate.

Never return reviewer transcripts or raw reasoning. Include raw command output only when it is the direct
evidence for a finding, and keep it brief.

## Runtime Degradation

| Missing capability | Adaptation |
| --- | --- |
| No subagents | Run each reviewer as a labeled inline pass. |
| No shell access | Perform reference and instruction review from file contents; mark validation commands unrun. |
| No git | Use explicit `SCOPE` or review all active instruction surfaces; record that baseline status is unknown. |
| No runtime validator | Validate JSON/frontmatter shape manually and report validator unavailability as a risk. |
| No model routing | Run every role with the current model; preserve tier labels as intent and record `capability_tiering: current-model-only` and `model_routing: unavailable`. |
