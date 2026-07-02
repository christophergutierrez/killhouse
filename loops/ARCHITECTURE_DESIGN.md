### Purpose

Perform an iterative, autonomous architecture review to identify and resolve high-impact shallow modules, weak boundaries, and domain language disconnects. The loop should improve locality and reduce caller knowledge, not merely rearrange code.

Run until the highest-priority architectural friction is resolved, no Critical/High findings remain, a safety gate requires human confirmation, or `MAX_PASSES` is reached.

### Inputs

- **TARGET_DIR**: Directory or specific modules to review.
- **TEST_COMMAND**: Exact command used to verify the refactoring, such as `npm test` or `cargo test`.
- **DOMAIN_DOCS**: Paths to domain vocabulary, architecture decisions, and product/domain context, such as `CONTEXT.md` or `docs/adr/`.
- **MAX_PASSES**: Maximum iterations before halting. Default: `3`.
- **MODE**: `review-only` | `converge`. Default: `converge`.

### Operating Principles

- Focus on module depth, boundaries, domain vocabulary, and refactoring safety. Do not flag linting, formatting, cosmetic organization, or minor bugs.
- A deep module puts useful behavior behind a small, stable interface. A shallow module makes callers learn almost as much as the implementation knows.
- If understanding one domain concept requires bouncing through many unrelated files, the architecture is failing.
- Treat `DOMAIN_DOCS` as the primary reference for vocabulary and decisions, but flag contradictions when docs appear stale or inconsistent with working code.
- Do not introduce abstractions, renames, type wrappers, or folder moves unless they reduce caller knowledge, improve locality, clarify a real boundary, or align domain behavior.
- Prefer narrow, behavior-preserving refactors. Escalate broad contract changes before editing.
- **Context hygiene.** This loop runs as a delegated subagent by default so the caller's session stays lean. Reviewers read only scoped modules and return findings only; the loop hands back the RFC (review-only) or the converge summary (verdict, resolved findings, tests run) — never its full review transcript or reasoning trace.

### Safety Baseline

Before review or edits:

- Identify whether the workspace has version control. If it does, record the current status and do not overwrite unrelated existing changes.
- If no version control is available, record the files that may be touched and preserve enough original content to support a per-pass rollback.
- Establish the verification command by running or validating `TEST_COMMAND` when practical. If the baseline command already fails, report that fact and use it as a risk input.
- Never roll back user changes or unrelated pre-existing edits. Rollback applies only to changes made during the current pass.

### Roles

- **Reviewers (subagents):** Four parallel reviewers, each using a strict lens. They read only the scoped modules and return high-impact architectural friction points.
  - **Depth Agent**: Finds interfaces that expose too much implementation knowledge, pass-through APIs, excessive getters/setters, data structures that should own behavior, and shallow wrappers.
  - **Seams Agent**: Finds coupling and boundary problems, hidden dependencies, circular imports, leaking abstractions, cross-layer calls, and unstable dependency direction.
  - **Domain Agent**: Compares code to `DOMAIN_DOCS`. Finds primitive obsession, inconsistent names, missing domain types, duplicated concepts, and code/doc vocabulary conflicts.
  - **Tests Agent**: Finds tests coupled to implementation details rather than observable behavior, missing characterization coverage, and brittle safety nets.
- **Architect**: Synthesizes findings, applies severity and blast-radius rubrics, selects the single most valuable target, and writes a precise plan or RFC. The Architect does not edit code.
- **Implementer**: Applies the approved plan, keeps edits scoped, runs verification, and reports changed files and test results.

### Finding Schema

Each reviewer finding must use this shape:

```markdown
- id: stable-content-based-slug
  severity: Critical | High | Medium | Low
  lens: Depth | Seams | Domain | Tests
  files: path:line[, path:line]
  problem: One concrete architectural friction point.
  evidence: Specific code facts showing the friction.
  impact: Why this slows changes, spreads knowledge, or increases risk.
  suggested_direction: The smallest plausible improvement.
```

Finding ids must be stable across passes. Use a slug based on the primary module path plus the friction type, not line numbers.

### Severity Rubric

- **Critical**: The issue blocks safe change, crosses a public or persisted contract, causes repeated domain misunderstanding, or forces many callers to coordinate around implementation details.
- **High**: The issue creates clear refactoring friction in an important module, leaks a boundary into multiple callers, duplicates domain rules, or makes tests reject behavior-preserving improvements.
- **Medium**: The issue is real but localized, has few callers, or can be safely deferred.
- **Low**: The issue is mostly cosmetic, speculative, or not clearly connected to caller knowledge, locality, or domain alignment. Low findings should usually be omitted.

### Scope Discovery

The Architect identifies the top 5-10 modules within `TARGET_DIR` using a mix of:

- size and complexity;
- fan-in and fan-out;
- cross-boundary imports;
- recent churn if available;
- centrality to domain concepts in `DOMAIN_DOCS`;
- test fragility or lack of behavioral coverage;
- public API usage or broad caller impact.

Do not select modules by size alone. Small central interfaces can be higher leverage than large isolated files.

### Blast-Radius Rubric

A plan is **high blast radius** and must become an RFC before editing if it:

- changes an exported/public interface used by more than a few call sites;
- changes persisted data, wire formats, API contracts, CLI behavior, migrations, or configuration shape;
- moves responsibilities across packages, layers, services, or ownership boundaries;
- requires coordinated edits in many unrelated modules;
- changes domain terminology where `DOMAIN_DOCS` and code disagree;
- lacks adequate behavioral tests for the affected contract.

Otherwise, a plan may be applied in `converge` mode if tests are adequate and edits are narrowly scoped.

### Refactoring Plan Schema

Before implementation, the Architect must produce:

```markdown
### Plan
- target: Primary module/interface to deepen.
- findings_addressed: Finding ids this pass intends to resolve.
- current_problem: Why the current design is shallow, leaky, or domain-misaligned.
- intended_shape: The new responsibility boundary and smaller caller contract.
- files_to_touch: Expected files and why.
- blast_radius: Low | Medium | High, with rationale.
- test_strategy: Existing or new behavioral tests that will verify the change.
- rollback_strategy: How to undo only this pass if verification fails.
```

### Execution Loop

1. **Baseline**: Apply the Safety Baseline checks.
2. **Scope Discovery**: Select the bounded module set.
3. **Parallel Review**: Run all reviewers over the scoped modules.
4. **Synthesis**: Deduplicate findings, assign severity, and classify by finding id.
5. **No Good Target Check**: If no Critical or High findings remain, halt with: `No high-impact architectural friction found.`
6. **Target Selection**: Pick one target module whose improvement has the best leverage-to-risk ratio.
7. **Plan or RFC**: Produce the Refactoring Plan. If `MODE` is `review-only` or blast radius is High, output the RFC and stop for human confirmation.
8. **Test Coverage Check**: Confirm the affected behavior has adequate tests. If not, add characterization tests first when safe; otherwise halt or choose the next target.
9. **Test Realignment**: If tests are implementation-coupled, refactor them to assert observable behavior before deepening the module. Run `TEST_COMMAND` after realignment.
10. **Apply**: Implement the scoped refactor.
11. **Verify**: Run `TEST_COMMAND`.
    - If tests fail, the Architect gets one revision attempt.
    - If tests still fail after one revision, roll back only this pass and halt or choose the next target.
12. **Re-review Blast Radius**: Re-run reviewers on modified files plus dependents and call sites of changed interfaces.
13. **Diff Findings**: Compare findings by id and classify each as resolved, persisting, new, or regressed.
14. **Decide**: Stop when tests pass and either no Critical/High findings remain, `MAX_PASSES` is reached, or a thrash halt fires. Otherwise start the next pass.

### Test Coverage Standard

Adequate coverage means the affected public behavior is tested at the level callers rely on:

- behavior-focused tests exist for the target's current contract;
- important edge cases and failure modes are covered;
- tests do not require the old internal shape to remain intact;
- changed call sites are exercised directly or through integration coverage;
- the verification command is capable of failing if the refactor breaks the intended behavior.

If the safety net is inadequate, prefer adding characterization tests before changing production code.

### Convergence & Halting

- **Deeper, not just different**: Convergence requires the target's prior Critical/High findings to be resolved by id. If equivalent Critical/High findings appear in immediate dependents, treat the target as not improved.
- **No complexity laundering**: Do not claim success if the module looks cleaner only because callers now perform the same coordination, validation, translation, or domain decisions themselves.
- **Thrash halt**: Stop and escalate if a resolved finding id reappears, or if the Architect selects the same target across consecutive passes without reducing its Critical/High count.
- **Per-pass rollback**: A failed pass rolls back only changes from that pass. Previously verified passes remain.

### RFC Output

For `review-only` mode or High blast-radius plans, output:

```markdown
### RFC: <target>

#### Files
- path: why it matters

#### Problem
The architectural friction, with evidence.

#### Proposed Change
The smallest design change that improves locality, module depth, or domain alignment.

#### Benefits
Expected locality, leverage, and caller-simplification gains.

#### Blast Radius
Affected interfaces, call sites, contracts, data shapes, and ownership boundaries.

#### Risks
Likely regressions, migration concerns, stale docs, or missing tests.

#### Test Plan
Existing and proposed verification.

#### Alternatives
Reasonable options considered and why they were not selected.

#### Stop Conditions
Conditions that should halt or require human confirmation.
```

### Final Output

In `review-only` mode, output the RFC only.

In `converge` mode, output:

- verdict;
- passes used;
- refactored modules;
- findings resolved, persisting, new, or regressed;
- tests run and results;
- any remaining risks or follow-up RFCs.
