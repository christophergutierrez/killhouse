# Verified Planning Loop

Produce a repository-grounded, executable implementation plan through right-sized discovery,
adversarial review, falsification, and revision. The output must let another coding agent execute
the work without rediscovering major design decisions, guessing intent, or trusting unproven gates.

**This is a planning loop only. It does not modify production code.**

Tuned for the hardest case, a migration that adds new behavior and fully removes old behavior, but
it scales down rather than applying full machinery to everything.

**Context hygiene.** This loop runs as a delegated subagent by default so the caller's session stays
lean. Reviewers return findings only; the loop hands back the plan file at `OUTPUT_PATH` plus its
machine-readable verdict block — never its discovery notes, reviewer transcripts, or reasoning trace.

## Inputs

- **REQUEST**: Natural-language description of the change, including any removal/replacement.
- **TARGET_REPOSITORY**: Repository root or working directory.
- **CONTEXT_DOCS**: Architecture docs, ADRs, specs, READMEs, prior plans. May be empty.
- **TEST_COMMANDS**: Known build/lint/typecheck/test/smoke commands. May be empty.
- **OUTPUT_PATH**: Where to write the final plan. Default: `implementation-plan.md`.
- **MAX_PASSES**: Maximum review-revise passes. Default: `5`.
- **MODE**: `create` | `review-existing` | `review-only` | `converge`. Default: `converge`.
- **TIER_OVERRIDE**: Force a task tier (`light` | `standard` | `full`). Optional.
- **EXECUTION_POLICY**: `cost_optimized` | `time_optimized`. Default: `cost_optimized`.

---

## 1. Task Tiering (do this first)

A fast triage classifies the change and selects how much of the loop runs, preventing both
under-planning risky work and over-planning trivial work. Classify by the **most severe** trigger
that applies; record tier and trigger in the plan verdict. When uncertain between tiers, pick the
higher one.

| Tier | Triggers | Machinery that runs |
| --- | --- | --- |
| **light** | Single-file or localized change; no removal of used behavior; no public contract, persisted data, CI/deploy/security/auth/billing, or ownership surface; a fresh agent could execute from a one-paragraph description. | Scout + one combined review pass. Gate Standard + Falsifiability (sec 8). At least one presence or regression gate. Outcome-to-gate mapping instead of a matrix. Skip: decomposition, traceability matrix, multi-analyst discovery, spikes, cold-start walk, state diagram, downstream handoff. |
| **standard** | Multi-file feature or refactor; limited removal with clear consumers; no high-blast-radius surface. | Scout + Dependency/Test analysts; reviewer lenses (sec 5); traceability matrix; invariants; sec 8; falsification + conflict triage (sec 11); adversarial gate audit (sec 13). Migration analyst and state diagram only when removal is present. |
| **full** | Migration (add + fully remove); public/consumed interface, persisted data, wire format, CI/deploy/security/auth/billing, or cross-team boundary in scope; unclear consumers; any Blast-Radius trigger (sec 16). | Everything: all analysts, REQUEST decomposition, bidirectional traceability, cost-aware invariants, spikes, migration coverage + state diagram, falsification, conflict triage, adversarial gate audit, downstream handoff. |

A light or standard plan that discovery reveals to touch a full trigger is **re-tiered up**
immediately. Never down-tier to skip a safety mechanism. Sections marked "(standard+)" or "(full)"
are omitted by lighter tiers.

---

## 2. Operating Principles

1. **Ground in the repository, not the request.** Inspect real files, entry points, dependencies,
   and conventions before planning. Never infer structure from the REQUEST alone.
2. **Right-size the plan.** Match rigor to the tier. Neither skip a safety trigger nor pad a
   trivial change with ceremony.
3. **Addition and removal are one migration**, not unrelated tasks.
4. **The final repository state is the product.** No obsolete behavior, reference, entry point,
   dependency, doc, or term may survive final verification unless explicitly preserved.
5. **Every milestone yields an observable repository state** with an objective, falsifiable gate.
   "Investigate", "clean up", and "make it work" are activities, not milestones.
6. **Tracer bullet first.** For any multi-layer feature, the first non-spike milestone must be a thin,
   runnable end-to-end slice through every layer needed for the user-visible path. It may be ugly,
   narrow, and incomplete, but it must pass a real gate from the highest practical seam before any
   single layer is fleshed out. Backend-only, UI-only, schema-only, or infrastructure-only milestones
   may precede it only when they are explicit spikes, characterization, or unavoidable prerequisites,
   and the plan must say why.
7. **A gate you cannot make fail is documentation, not a gate** (sec 8).
8. **An unwritable gate is an unknown, not a milestone**; convert it to a spike (sec 9).
9. **A fact without a citation is an assumption** (sec 12, Evidence Contract).
10. **Resolve reviewer conflicts by principle, not vibes** (sec 11.1).
11. **Preserve unrelated work.** Record existing user changes; never plan rollbacks that would
    discard them.
12. **Separate confirmed facts, working assumptions, and decisions needing human approval.** State
    an assumption and proceed unless the answer would change architecture, public behavior,
    persisted data, security posture, ownership boundaries, or project scope; then stop and ask.
13. **Prefer delegation when it preserves context.** Default to handing cleanly separable work to a
    subagent. Keep work inline only when it is truly trivial, tightly coupled to the current
    reasoning, or handoff overhead is clearly higher than the work itself. Every inline choice must
    carry a brief justification.

---

## 3. Capability Tiers (provider-agnostic; distinct from task tiers)

- **fast**: triage, bounded searches, inventories, call-site discovery, mechanical checks.
- **standard**: repository analysis, dependency tracing, test planning, ordinary planning.
- **reasoning**: synthesis, sequencing, conflict resolution, risk judgment, falsification, final
  approval.

Run roles as parallel subagents when supported; otherwise run each inline as a labeled pass. Tier
labels remain as documented intent when one model performs every role. Prefer delegation when a
role can be handed off cleanly; mark inline only when the work is trivial, tightly coupled to the
current reasoning, or handoff overhead clearly exceeds the work. Every inline choice must be
justified in the matrix or milestone block.

**Reviewer independence**: reviewers receive the plan and evidence, never each other's findings.
Findings stay raw until Lead Planner synthesis. When roles run inline, complete and record each
reviewer pass before starting the next, and do not revise earlier findings in light of later ones.

### 3.1 Execution Policy

Quality is fixed by gates, review, and mandatory halts. Execution policy only changes the route to
that quality bar:

- **cost_optimized** *(default)*: Prefer the cheapest capable tier for bounded implementation,
  mechanical validation, docs sync, and other reversible work. Escalate after evidence: failed gates,
  repeated same failure, scope expansion, security/architecture uncertainty, or reviewer rejection.
- **time_optimized**: Prefer stronger tiers earlier when failed attempts would likely cost more
  wall-clock time than they save. Still use cheaper tiers for mechanical checks, inventories, and
  independent review where safe.

The plan must record the selected policy and explain tier choices in the Subagent Matrix. Do not
lower tier for safety decisions, architecture judgment, final verdicts, or mandatory gates just to
save model cost.

---

## 4. Roles

- **Repository Scout** *(fast/standard, all tiers)*: Inventory relevant source, scripts, entry
  points, tests, fixtures, config, docs, generated artifacts, dependencies, integration points, and
  existing user changes. Identify standard build/lint/test/smoke commands. **Dry-run** candidate
  gate commands where safe and record actual baseline outputs. Return repo-relative paths with the
  command that produced each observation (sec 12).
- **Dependency & Boundary Analyst** *(standard, standard+)*: Trace imports, registrations, routes,
  CLI names, public interfaces, persisted/wire formats, config contracts, package/ownership
  boundaries. Return a dependency map and blast-radius notes.
- **Test & Gate Analyst** *(standard, standard+)*: Identify coverage gaps, characterization needs,
  feasible gates, invariant checks, and regression commands, each with proposed baseline polarity,
  post_condition, failure reasoning, and cost.
- **Migration & Cleanup Analyst** *(standard, full or any removal)*: Produce a
  reuse/rename/delete/preserve matrix. Search stale terminology, wrappers, aliases, docs, fixtures,
  CI refs, generated output. Recommend absence checks; confirm each is non-vacuous at baseline.
- **Reviewers** *(standard; parallel; findings only; adversarial stance)*: Find the input,
  ordering, or omission that makes execution fail. On safety-relevant uncertainty (contracts,
  persisted data, removal), default to **Blocking**. Lenses (light collapses these into one pass):
  Gate Quality; Completeness; Migration/Removal; Sequencing; Risk & Rollback; Repository Alignment;
  Simplification.
  The Simplification lens includes a Ponytail check: before accepting a milestone, ask whether the
  outcome needs to exist, whether the repository already has the pattern/helper, whether stdlib or
  native platform behavior covers it, whether an installed dependency already solves it, and whether
  the milestone or gate can be smaller without weakening safety, falsifiability, or removal
  completeness.
- **Lead Planner** *(reasoning, all tiers)*: Triage the task; synthesize evidence and findings;
  dedupe by stable id; triage findings (accept/adapt/reject with reason), resolving conflicts per
  sec 11.1; draft and revise the plan; run falsification; hand the near-final plan to the
  Adversarial Gate Audit (sec 13); approve the artifact. Does not implement production changes.
- **Gate Auditor** *(reasoning; standard+; fresh instance)*: Receives only the plan and repository
  access, none of the planning conversation. Audits every gate and invariant against sec 8 and the
  Evidence Contract. See sec 13.

---

## 5. REQUEST Decomposition *(full)*

Restate the REQUEST as a flat list of **atomic outcomes**, each a single verifiable end state.
Include **implied** outcomes the REQUEST does not spell out: a removal implies removing its docs,
CI references, dependencies, fixtures, and terminology (sec 10). Mark each `explicit` or `implied`;
list explicit **non-goals**. This is the left column of the traceability matrix. At standard tier,
enumerate outcomes informally without the tagging. At light tier, a short outcome-to-gate mapping
replaces this section entirely.

---

## 6. Outcome Traceability Matrix *(standard+, bidirectional)*

Every outcome maps forward to at least one milestone, one invariant, and one final check. Every
milestone maps back to an outcome or an explicit non-goal. **No orphan rows in either direction**:
a milestone with no outcome parent is scope creep; cut it or justify it as a named prerequisite.

```markdown
| outcome_id | outcome (explicit/implied) | milestone_id(s) | invariant_id(s) | final_check | baseline_verified |
| --- | --- | --- | --- | --- | --- |
```

---

## 7. Final-State Invariants *(standard+)*

Plan-level properties re-checked at final verification so a violation cannot hide behind a passing
milestone.

```yaml
- id: stable-slug
  statement: Property that must hold at completion.
  category: presence | absence | regression
  check: Exact command or objective check with expected result.
  baseline_polarity: Result BEFORE the work (must be the failing result; see sec 8).
  post_condition: Expected result AFTER the relevant milestone / at final verification.
  failure_reasoning: The concrete broken or absent state that makes this check fail.
  scope: every-pass | phase-end | final
  cost: cheap | expensive
  rationale: Which REQUEST outcome this protects.
  evidence: Command output proving baseline_polarity, or "unrun: <reason>" (sec 12).
```

Rules: every removal/replacement gets at least one **absence** invariant (default `every-pass`);
every new user-visible capability gets a **presence** invariant; every cross-cutting change gets a
**regression** invariant. **Cost-aware suite**: name the cheap `every-pass` subset vs the full
suite at `phase-end`/`final`; every `expensive` check still runs at `final`. **No invariant
laundering**: never satisfy an absence invariant by broad allowlisting; every allowlist entry must
be enumerated and justified in the plan, and the executor may not add entries.

---

## 8. Gates: Standard, Falsifiability & Characterization *(all tiers)*

A gate is adequate only if it is objective and observable, repeatable, scoped to the milestone,
independent of obsolete code meant to be removed, precise enough for unambiguous pass/fail, and,
for behavior changes, exercised at the caller/user level. Ban subjective language ("works", "looks
good", "clean") and forbidden patterns ("verify everything works", "review the code", "ensure
quality", "confirm no issues"). Categories: **Presence**, **Absence**, **Regression**.

**Falsifiability (non-vacuous proof).** A gate that passes at baseline proves nothing. Record each
gate's **baseline result** (dry-run during discovery where safe); it must be the *failing* one:

| Category | Must at baseline | If not |
| --- | --- | --- |
| Presence | **fail** (feature absent) | milestone is a no-op or gate targets the wrong thing |
| Absence | **match/fail** (legacy still present) | gate is vacuous; fix term, path, or scope |
| Regression | **pass** (behavior works now) | disclose pre-existing failure as a risk input, not a gate |

A gate with no recorded baseline is Material unless the plan records why it was unsafe or
unavailable to run. An absence gate proven vacuous is Blocking.

**Characterization before deletion** *(standard+, and any light task that removes behavior)*: no
milestone may delete or substantially replace behavior unless an earlier milestone adds
characterization tests, or the plan documents why existing coverage suffices, or records an
explicit decision not to preserve it. Violations are Blocking.

If no adequate gate can be written, the milestone is defective: split it, sharpen it, add a
characterization prerequisite, or convert it to a spike (sec 9).

---

## 9. Unknowns Become Spike Milestones *(full; use in standard when needed)*

When discovery cannot produce a non-vacuous gate because a fact is unknown (an API's existence, a
dependency's behavior, whether a consumer still uses the old path), do **not** guess a gate. Insert
a **spike milestone** whose outcome is the discovered fact recorded with evidence (command output,
search result, file reference) and whose gate is that the evidence exists and is cited. Downstream
milestones depend on the spike. Include a stop condition for the case where the discovered fact
contradicts the current plan. Spikes sequence implementation; they do not authorize this loop to
edit production code.

---

## 10. Migration Coverage & State Diagram *(full, or any removal)*

Account for each of: source files; imports and registrations; routes, UI labels, help text,
user-visible names; scripts and CLI entry points; tests, snapshots, fixtures, sample data, mocks;
config and environment variables; package dependencies and lockfiles; build/CI/deploy/release
references; documentation, examples, tutorials, comments; generated and checked-in artifacts;
compatibility wrappers, aliases, redirects; repository-wide references to obsolete names. **Do not
assume deleting one directory constitutes complete removal.**

**State-transition diagram** *(full migrations and structural refactors only; optional otherwise)*:
include a small Mermaid diagram showing baseline state (legacy paths/files/deps), intermediate
states (transitional shims, side-by-side execution), and target state (legacy fully removed). Keep
it to the phases the plan actually defines; it orients the executor and is not a substitute for
gates.

---

## 11. Falsification *(standard+)*

Before the gate audit, the Lead Planner runs two complementary checks and turns each gap into a
finding (lens: ColdStart or PreMortem):

- **Cold-start walk**: traverse the plan (full: every traceability row; standard: every milestone)
  **as a fresh agent with only the plan and the repository**, and report the first point that
  requires a guess, a rediscovered decision, an unstated dependency, an uninterpretable gate, a
  choice between unlisted files or APIs, or proceeding past a missing human decision.
- **Pre-mortem**: assume the plan executed exactly as written; list the top concrete failure modes
  (missing prerequisite, unwritable gate, hidden dependency, baseline masking, scope ambiguity,
  stale repository state) and the smallest plan change that prevents each.

### 11.1 Conflict Triage Protocol

The parallel reviewers are adversarial and will produce conflicting recommendations (e.g.
Simplification wants a gate cut that Gate Quality or Risk & Rollback demands). When the Lead
Planner cannot satisfy both, it resolves the conflict by this fixed priority; higher wins, and the
rejected recommendation is recorded with its reason in the Review Record:

1. **Safety & rollback-boundary integrity** (highest)
2. **Gate falsifiability & verifiability** (including evidence and dry-run proof)
3. **Migration/removal completeness**
4. **Repository & architectural alignment**
5. **Simplification & overhead reduction** (lowest)

Simplification never overrides a safety, falsifiability, or removal-completeness finding; it
prevails only over other simplification or alignment concerns, or when the higher lenses are
already satisfied. A conflict that cannot be resolved without changing architecture, public
behavior, persisted data, or scope escalates to the Blast-Radius gate (sec 16) as a human decision.

Ponytail rule for simplification conflicts: delete or shrink only after the plan is repository
grounded and the gate remains non-vacuous. Prefer no milestone over a speculative milestone, reuse
over new code, stdlib/native behavior over dependencies, installed dependencies over new ones, and
one narrow gate over a broad ceremonial suite. Do not remove characterization, rollback, security,
data-loss, accessibility, migration, or public-contract checks in the name of brevity.

---

## 12. Evidence & Staleness Contract *(new in v6; all tiers, scaled)*

**Evidence Contract.** Every entry in Repository Findings, every baseline_polarity, and every
spike outcome must cite the command (or file path and observation) that produced it. Format:
`fact <- command: <cmd> -> <relevant output>`. A fact without a citation is downgraded to a working
assumption and listed as such. This makes the cold-start walk able to audit the plan's foundations,
not just its milestones: an executor (or auditor) can re-run any citation and detect drift. At
light tier, citations are required only for the gate baselines.

**Staleness Contract.** The plan records the repository state it was grounded in: VCS HEAD (or
snapshot identifier), dirty-file list, and the timestamp of discovery. The Downstream Handoff must
instruct the executor to verify this recorded state before starting:

- HEAD matches and dirty list is unchanged: execute normally.
- HEAD moved but no recorded fact's cited file changed: proceed, note the drift.
- Any file cited by a fact, gate, or invariant changed: the affected items are stale; re-run their
  citations and re-validate before executing, or return the plan to this loop in
  `review-existing` mode.

A plan without a recorded repository state cannot be verdict `READY`; the best it can earn is
`READY_WITH_ASSUMPTIONS` with staleness listed as the assumption.

---

## 13. Adversarial Gate Audit *(new in v6; standard+)*

The final gate check must not be the author grading its own work. After falsification and before
the exit check, a **Gate Auditor** (reasoning tier, fresh instance, no planning-conversation
context) receives only the plan and repository access and answers, for every gate and invariant:

1. What concrete failure would this catch? (If the auditor cannot name one, the gate is vacuous:
   Blocking for absence gates, Material otherwise.)
2. Is the baseline polarity proven by a citation, or asserted? (Asserted: Material.)
3. Could this gate pass while the outcome it traces to is not achieved? (Yes: Material, with the
   scenario named.)

Auditor findings enter the normal finding stream. **Degradation**: if a fresh instance is
unavailable, run the audit as a labeled inline pass with an explicit instruction to adopt the
auditor persona and disregard prior justifications; record in the verdict that the audit was not
independent (`gate_audit: inline`).

---

## 14. Finding Schema *(all tiers)*

Ids are content-based and stable across passes (keyed to the conceptual flaw, not line numbers).

```yaml
- id: stable-content-slug
  severity: Blocking | Material | Minor
  lens: GateQuality | Completeness | MigrationRemoval | Sequencing | RiskRollback | RepositoryAlignment | Simplification | ColdStart | PreMortem | GateAudit
  location: Phase / Milestone / section
  problem: One concrete deficiency.
  evidence: Plan text, omission, or a repository fact or command result.
  impact: Why execution would be unsafe, ambiguous, or wasteful.
  required_change: The smallest correction that resolves it.
```

**Blocking**: unsafe execution; removal with no non-vacuous absence invariant; a gate that cannot
be proven to fail on a contract or persisted-data milestone; deletion without characterization; an
orphan milestone with no outcome parent; a multi-layer plan whose first non-spike milestone is
horizontal instead of a runnable tracer bullet; a cold-start gap on a REQUEST outcome; a contradictory
dependency; an incorrect low tier; a required human decision.
**Material**: vague or unproven gate; gate lacking a recorded baseline without a reason; fact
without citation presented as confirmed; understated blast radius; unspecified subagent contract;
terminology conflicting with CONTEXT_DOCS; expensive every-pass checks without a cheap subset.
**Minor**: localized or cosmetic; usually deferred.

**Thrash** (defined): a resolved finding id reappears; the same span is changed and reverted across
passes; or definitions oscillate without measurably reducing the Blocking/Material count. Thrash
halts the loop with verdict `BLOCKED` and the contested items listed.

---

## 15. Loop

0. **Triage.** Classify the task (sec 1) or apply TIER_OVERRIDE. Record tier + trigger.
1. **Baseline & Discovery.** Record VCS status, HEAD, and dirty files (or plan a snapshot if
   unversioned) for the Staleness Contract. Identify existing user changes to preserve. Read
   CONTEXT_DOCS. Run the Scout and the analysts the tier calls for, in parallel. Run TEST_COMMANDS
   once; disclose baseline failures as risk inputs, never hide them by weakening gates. Dry-run
   candidate gate commands where safe; record citations.
2. **Decompose** *(full)*. Produce atomic outcomes + non-goals (sec 5).
3. **Draft.** Lead Planner produces a plan per sec 18, including the traceability matrix
   (standard+) and invariants with baseline polarity and evidence.
   For multi-layer work, sequence the first non-spike milestone as the tracer bullet required by
   sec 2: a thin, runnable end-to-end path with a highest-practical-seam gate. If a prerequisite
   must come first, mark it as `tracer_bullet: prerequisite` and cite why the tracer bullet cannot
   run before it.
   Apply the Ponytail simplification check to each milestone before review: if the milestone exists
   only for hypothetical future need, duplicates a repo pattern, adds an avoidable dependency, or
   uses a broader implementation than the requested outcome needs, shrink or remove it before
   handing the draft to reviewers.
4. **Review.** Launch reviewers per tier (light: one combined pass) over the plan + evidence,
   independently (sec 3).
5. **Synthesize.** Dedupe findings by id, assign severity, triage accept/adapt/reject, resolving
   lens conflicts via sec 11.1.
6. **Revise.** Apply accepted and adapted changes in one coherent edit; append a "Pass N changes"
   changelog.
7. **Falsify** *(standard+)*. Run sec 11; each gap becomes a finding.
8. **Gate audit** *(standard+)*. Run sec 13; findings enter the stream. (On subsequent passes,
   audit only gates and invariants changed since the prior audit.)
9. **Convergence ledger.** Compare findings to the prior pass by stable id: resolved, persisting,
   new, regressed. Halt `BLOCKED` on thrash (sec 14).
10. **Exit check.** Halt `READY` when, for the task's tier, all of the following hold:
    - no Blocking or Material finding remains;
    - every gate and invariant meets sec 8 with a proven failing baseline or a recorded reason;
    - every fact is cited or reclassified as an assumption (sec 12);
    - repository state is recorded for the Staleness Contract;
    - (standard+) the traceability matrix has no orphan rows in either direction;
    - (standard+) characterization-before-deletion holds; every removal has a non-vacuous absence
      invariant;
    - (standard+) falsification and the gate audit surfaced no open gap;
    - dependencies are explicit, acyclic, and reachable; high-blast-radius work has a human gate;
    - rollback boundaries are concrete and preserve unrelated work;
    - unresolved assumptions are low-risk, or the verdict is not `READY`.
11. **Blast-radius gate** (sec 16). Halt `BLOCKED` (unless already decided) if any trigger applies.
12. **Terminate.** Otherwise continue up to MAX_PASSES, re-reviewing changed sections only. At the
    limit, emit the plan with open findings; verdict is `READY_WITH_ASSUMPTIONS` (executable under
    listed low-risk assumptions only) or `BLOCKED`.

`review-only`: run steps 0-5 and 9 once; emit findings + synthesis; write no plan file.
`review-existing`: load the supplied plan as the step-3 draft; run the Staleness Contract check
against its recorded repository state first.

---

## 16. Blast-Radius Human Gate

Require human approval before implementation (verdict `BLOCKED` unless already decided) if the plan
would: change a public or externally consumed interface; alter persisted data, migrations, or wire
formats; remove behavior that may still have active users; change CI, deploy, release, security,
authentication, authorization, or billing behavior; cross service, package, repository, or team
ownership boundaries; or proceed without an adequate way to test affected behavior. Any such
trigger forces the task to **full** tier. List the specific decisions in `blast_radius_decisions`.

---

## 17. Downstream Handoff *(full; optional for standard)*

End the plan with a section for an execution loop (e.g. PLAN_EXECUTE_LOOP):

- the Staleness Contract check the executor must run first (sec 12);
- ordered milestone ids with dependencies, spikes included;
- the full invariant suite with scopes, baseline polarity, post_condition, and the cheap per-pass
  subset;
- the consolidated final-state verification sequence;
- replan triggers (assumed API missing, gate unwritable, dependency conflict, staleness detected);
- human-confirmation points for high-blast-radius milestones.

This describes what the executor needs; it does not authorize this loop to implement.

---

## 18. Plan Schema (written to OUTPUT_PATH)

```markdown
# Implementation Plan: <goal>

## Planning Verdict
- verdict: READY | READY_WITH_ASSUMPTIONS | BLOCKED
- task_tier: light | standard | full
- tier_trigger: why this tier was selected
- execution_policy: cost_optimized | time_optimized
- reason: <short summary>

## Repository State (Staleness Contract)
- HEAD / snapshot id, dirty files, discovery timestamp.
- Existing user changes to preserve.

## Repository Findings
- Confirmed facts, each with citation: fact <- command -> output.
- Baseline status and known pre-existing failures.
- Unsafe/unrun commands and why. Context docs read or missing.
- Unknowns requiring spikes.

## Requested Outcomes & Non-Goals            (full: explicit/implied tags; light: outcome->gate map)

## Facts, Assumptions, and Decisions         (cited facts / assumptions / human-approval, kept separate)

## Outcome Traceability Matrix               (standard+)

## State Transition Diagram (Mermaid)        (full migrations only)

## Final-State Invariants                    (standard+; baseline_polarity, post_condition, scope, cost, evidence)
Cheap per-pass subset: <ids>. Full suite at: phase-end / final.

## Phased Plan
### Phase: <name>
- objective / rationale / prerequisites / files-components / blast_radius
- rollback_boundary (undo this phase only) / risks / exit_gate

#### Milestone: <stable-slug>
- outcome (observable, not an activity) / traces_to (standard+) / implementation_scope / dependencies
- tracer_bullet: yes | no | prerequisite | not_applicable, with rationale
- subagent_work: role, tier, delegate, policy_rationale, escalation_trigger, scope, inputs, required output
- acceptance_gates: exact commands + expected results + baseline_polarity + post_condition + evidence
- gate_failure_reasoning / invariants_at_risk / evidence_to_record / rollback_unit / stop_conditions

## Subagent Matrix
| Work item | Role | Tier | Delegate? | Policy rationale | Escalation trigger | Inputs | Required output |

## Consolidated Verification
Proves: new behavior works; obsolete assets and references gone; affected tests pass; unrelated
behavior not regressed; docs, config, terminology reflect only the intended final state.

## Replan Triggers                            (all tiers)

## Downstream Handoff                         (full; optional standard)

## Review Record
Accepted / adapted / rejected (+ conflict-triage decisions with winner and loser lens) /
resolved / persisting / regressed / unresolved. Gate-audit findings and dispositions.
```

Append a machine-readable verdict block:

```json
{
  "verdict": "READY | READY_WITH_ASSUMPTIONS | BLOCKED",
  "task_tier": "light | standard | full",
  "tier_trigger": "string",
  "execution_policy": "cost_optimized | time_optimized",
  "passes": 0,
  "open_blocking_findings": 0,
  "open_material_findings": 0,
  "vacuous_gates_found": 0,
  "cold_start_gaps": 0,
  "uncited_facts": 0,
  "gate_audit": "independent | inline | skipped-light-tier",
  "staleness": { "head": "string", "dirty_files": [], "discovered_at": "iso-8601" },
  "traceability_complete": true,
  "orphan_milestones": [],
  "characterization_gaps": [],
  "conflicts_resolved": [ { "id": "string", "winner_lens": "string", "loser_lens": "string" } ],
  "invariants": [
    { "id": "string", "category": "presence | absence | regression", "scope": "every-pass | phase-end | final",
      "cost": "cheap | expensive", "check": "command", "baseline_polarity": "string", "evidence": "string" }
  ],
  "cheap_every_pass_invariants": [],
  "blast_radius_decisions": [],
  "human_decisions_required": [],
  "plan_location": "implementation-plan.md",
  "summary": "short human-readable summary"
}
```

---

## 19. Runtime Degradation

| Missing capability | Adaptation |
| --- | --- |
| No subagents | Run every role as a labeled inline pass; keep reviewer findings raw and sequential (sec 3); gate audit per sec 13 degradation. |
| No model routing | Use the current model for all roles; tier labels document intent. |
| Weak shell access | Run review-only; return the plan with exact commands, expected results, and baseline polarity for a human; mark unrun commands as assumptions/risks; staleness recorded as best available. |
| No version control | Snapshot TARGET_REPOSITORY; express rollback units as preserved file copies; staleness uses the snapshot id. |
| Unsafe baseline commands | Do not run them; record why; require the executor to run them before editing. |
| No fresh instance for audit | Inline audit with persona instruction; record gate_audit: inline. |
