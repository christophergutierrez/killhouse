# Good Enough Code Review Tribunal Loop

## Overview

Run a devtribunal-style code review without depending on the devtribunal MCP server or Claude Code-specific commands. The loop works in Codex, Grok, Gemini, or any agent runtime that can read files, run shell commands, and optionally launch subagents.

The core pattern is:

1. Detect the review scope.
2. Route files to a small set of practical specialist reviewers.
3. Run static tools and tests when available.
4. Synthesize findings into an action plan.
5. In converge mode, fix only blocking findings, re-review the affected scope, and stop with a PASS/FAIL verdict.

This is intentionally smaller than devtribunal. Use "good enough" subagents: enough independence to catch real issues, not so many reviewers that orchestration becomes the work.

**Context hygiene.** This loop runs as a delegated subagent by default so the caller's session stays lean. Specialist reviewers return only actionable findings; the loop hands back the findings table and the PASS/FAIL verdict — never the reviewers' reasoning traces or raw tool output. When this loop spawns specialist subagents, log each delegation per `loops/DELEGATION_LOG.md`; that is data collection only and never changes tier selection.

## Prompt

````markdown
Perform a practical, devtribunal-style code review and, when requested, converge the changes to a PASS/FAIL verdict.

### Operating Principles

- Findings first: prioritize bugs, security issues, data loss, runtime failures, incorrect API contracts, concurrency hazards, and test gaps.
- Skip style-only comments unless style causes a real correctness, safety, or maintenance problem.
- Prefer evidence from code, tests, linters, and git diffs over general advice.
- Keep fixes minimal and localized unless a broader change is required to remove the root cause.
- Do not revert user changes unless explicitly asked.
- Use existing project patterns, tools, test commands, and formatting.
- If a tool is unavailable, continue with manual review and note the missing signal.
- Review commits, diffs, artifacts, and gate output rather than the implementation session transcript.
  This keeps cost-optimized execution disposable: a weak-model attempt is accepted or rejected from its
  repository evidence, not from its noisy conversation history.

### Execution Modes

Choose the mode from the user's request:

- **full**: Review the whole repository.
- **wip**: Review all uncommitted changes, including staged, unstaged, and untracked files. This is the default when the user asks for a review without a scope.
- **staged**: Review only staged changes.
- **pr-ready**: Review commits not yet pushed to the upstream branch.
- **converge**: Review WIP changes, fix blocking findings, re-review affected scope, run tests, and repeat until PASS or a guard stops the loop.

If the user provides explicit files or directories, scope the review to those paths.

### Subagent Policy

Use subagents when the runtime supports them. Run them in parallel where possible. If subagents are unavailable, perform the same roles inline as separate review passes.

Good enough default roster:

1. **Language reviewer**: correctness, type/API contracts, async/concurrency, resource handling, and idioms for the changed language.
2. **Security/config reviewer**: injection, secrets, auth boundaries, filesystem/process/network risks, CI/container/IaC/config risks.
3. **Tests reviewer**: missing regression tests, weak assertions, flaky tests, test command failures, and changed behavior without coverage.
4. **Docs/contracts reviewer**: README/API/docs/comments/config examples that drift from behavior, public interface contract mismatches.
5. **Ponytail simplification reviewer**: over-engineering, speculative abstractions, avoidable new dependencies, hand-rolled stdlib/native behavior, pass-through wrappers, dead flexibility, and code that can be deleted without weakening safety or requested behavior.
6. **Architect synthesizer**: cross-file risks, systemic patterns, dependency direction, error boundaries, state ownership, and severity calibration.
7. **Manager planner**: priority order, effort estimates, minimal fix plan, and deferred items.

For tiny changes, collapse to three passes:

1. Language reviewer.
2. Tests/security reviewer.
3. Architect/manager synthesis.

For tiny changes, the architect/manager synthesis still runs the Ponytail check inline: can this
diff be deleted, replaced by existing code, stdlib, native platform behavior, or an already-installed
dependency, and are any new abstractions/config/layers speculative?

Use mid-tier or "good enough" models for specialist reviewers. Use the strongest available model for architect synthesis, final triage, and editing in converge mode. If model routing is not available, use the current model for all roles.

### Scope Detection

Before reviewing, identify the repo root:

```bash
git rev-parse --show-toplevel
```

For **wip** scope:

```bash
git diff --name-only HEAD
git ls-files --others --exclude-standard
```

For **staged** scope:

```bash
git diff --cached --name-only
```

For **pr-ready** scope:

```bash
git rev-parse --abbrev-ref --symbolic-full-name @{u}
git diff --name-only @{u}...HEAD
```

For **full** scope, enumerate tracked source/config/docs files and exclude generated/vendor/build directories.

Always deduplicate paths and filter to files that still exist. If no files remain, report that there is nothing to review for the selected scope.

### File Routing

Route by extension and path. A file can receive more than one reviewer.

Language reviewers:

- TypeScript/JavaScript: `.ts`, `.tsx`, `.js`, `.jsx`
- Python: `.py`
- Rust: `.rs`
- Go: `.go`
- Java: `.java`
- PHP: `.php`
- C#: `.cs`
- C: `.c`, `.h`
- C++: `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hxx`
- Dart: `.dart`
- Lua: `.lua`
- SQL: `.sql`
- Protobuf: `.proto`
- Shell: `.sh`, `.bash`
- Frontend: `.html`, `.css`, `.scss`, `.less`

Overlay reviewers:

- Tests: `*_test.*`, `*_spec.*`, `*.test.*`, `*.spec.*`, files under `test/`, `tests/`, `spec/`, or `__tests__/`
- Migrations: `.sql` under `migrations/`, `migrate/`, or `db/migrate/`
- Config/security: `Dockerfile`, `docker-compose.*`, `compose.*`, `.tf`, `.tfvars`, `.github/workflows/*.yml`, `.github/workflows/*.yaml`, `*.yaml`, `*.yml`, `*.json`, `*.toml`, `*.ini`
- Docs/contracts: `README*`, `CHANGELOG*`, `docs/**`, `*.md`, public API schema files, OpenAPI specs, protobuf files

Skip by default:

- `.git/`, `node_modules/`, `target/`, `dist/`, `build/`, `.next/`, `.nuxt/`, `coverage/`, `.nyc_output/`, `vendor/`, `__pycache__/`, generated lockfile-only noise unless the lockfile itself is the review target.

### Tool Use

Run relevant commands from the repo root. Prefer existing package scripts or project configuration.

Useful discovery commands:

```bash
git status --short
find . -maxdepth 3 -type f \( -name 'package.json' -o -name 'pyproject.toml' -o -name 'Cargo.toml' -o -name 'go.mod' -o -name 'pom.xml' -o -name 'build.gradle*' -o -name 'Makefile' \)
```

Useful static tools when present:

- TypeScript/JavaScript: `npm test`, `npm run lint`, `npm run typecheck`, `npx eslint`, `npx tsc --noEmit`, `npx biome`
- Python: `pytest`, `ruff check`, `mypy`, `pylint`
- Rust: `cargo test`, `cargo clippy`, `cargo audit`
- Go: `go test ./...`, `go vet ./...`, `golangci-lint run`, `staticcheck ./...`
- Java: `mvn test`, `gradle test`, `checkstyle`, `spotbugs`, `pmd`
- PHP: `phpstan`, `psalm`, `vendor/bin/phpunit`
- C/C++: `clang-tidy`, `cppcheck`, project build/test command
- Shell: `shellcheck`, `shfmt -d`
- SQL: `sqlfluff lint`
- Protobuf: `buf lint`, `buf breaking`
- Frontend/CSS: `stylelint`, `htmlhint`
- Config: `actionlint`, `hadolint`, `tflint`
- Secrets: `gitleaks detect --no-banner --redact`

Treat tool output as evidence. Do not paste huge raw logs. Extract the actionable failures with command names and relevant file/line references.

### Specialist Review Prompt

Each specialist receives:

```text
Review scope: {mode}
Repository: {repo_root}
Files assigned: {file_list}
Relevant diff or file excerpts: {content}
Tool output: {tool_output}
Context: {user_request_or_focus}

Return only actionable findings in the required format. Do not edit files.
Only flag issues directly supported by code, diff, tests, or tool output.
Skip style preferences and speculative rewrites.
```

### Ponytail Simplification Reviewer

This reviewer is narrow: find unnecessary complexity only. Do not flag correctness, security,
performance, or test issues unless the proposed simplification preserves those properties.

Apply this ladder in order:

1. Does this code need to exist for the stated change?
2. Does the repository already have a helper, pattern, component, type, or command that should be reused?
3. Does the language standard library cover it?
4. Does the native platform cover it?
5. Does an already-installed dependency cover it?
6. Can the same behavior be expressed with fewer files, layers, branches, options, or configuration?

Finding format:

```text
<file>:L<line>: <tag>: <what to cut>. <replacement>.
```

Tags:

- `delete`: dead code, unused flexibility, speculative feature. Replacement: nothing.
- `reuse`: duplicated local helper/pattern. Name the existing repo construct.
- `stdlib`: hand-rolled behavior the standard library provides. Name the API.
- `native`: dependency or custom code doing what the platform already does. Name the feature.
- `yagni`: abstraction/config/layer with no current caller or second implementation.
- `shrink`: same behavior with fewer lines or fewer files.

End with `net: -<N> lines possible, -<M> deps possible.` If there is nothing material to cut, say
`Lean already. Ship.`

### Finding Format

Each specialist must return:

```text
**[High-Level Summary]**
2-3 sentences about the reviewed scope.

**[Critical Issues]**
Blocking bugs, security issues, data loss risks, failing tests, or severe regressions. Write `None` if empty.

* **Issue:** ...
* **Severity:** critical | high
* **Confidence:** confirmed | likely | possible
* **Location:** repo-relative-path:line or function/section
* **Why:** ...
* **Fix:** ...

**[Improvements]**
Non-blocking correctness, maintainability, or test/doc improvements. Write `None` if empty.

* **Issue:** ...
* **Severity:** medium | low
* **Confidence:** confirmed | likely | possible
* **Location:** repo-relative-path:line or function/section
* **Why:** ...
* **Fix:** ...
```

Then emit exactly one fenced JSON block:

```json
{
  "findings": [
    {
      "severity": "critical | high | medium | low",
      "confidence": "confirmed | likely | possible",
      "category": "correctness | security | data_loss | concurrency | type_safety | api_contract | tests | docs | config | performance | maintainability",
      "file": "repo-relative/path",
      "line": 123,
      "title": "stable one-line title without a line number",
      "description": "why it matters",
      "suggested_fix": "minimal concrete fix"
    }
  ]
}
```

If there are no findings, emit `{ "findings": [] }`.

### Architect Synthesis

After specialist reviews, the architect reads all findings and produces:

```text
**[High-Level Summary]**
Overall review health and the highest-risk area.

**[Cross-Cutting Concerns]**
Systemic issues spanning multiple findings or files. Write `None` if empty.

* **Theme:** ...
* **Type:** risk | debt
* **Severity:** critical | high | medium | low
* **Confidence:** confirmed | likely | possible
* **Related Findings:** concise references
* **Observation:** ...
* **Recommendation:** ...

**[Severity Overrides]**
Escalate, downgrade, or dismiss specialist findings only with evidence. Write `None` if empty.

* **Finding:** ...
* **Action:** escalate | downgrade | dismiss
* **Reason:** ...
```

Architect rules:

- Do not restate every specialist finding.
- Do not turn one local issue into a systemic claim unless the code evidence supports it.
- Distinguish architectural risk from ordinary debt.
- State confidence when evidence is thin.

### Manager Plan

The manager produces:

```text
**[Summary]**
N work units, overall effort, and first recommended action.

**[Action Plan]**

### Priority 1: short title
* **Effort:** trivial | small | medium | large
* **Impact:** critical | high | medium | low
* **Findings Addressed:** concise references
* **Steps:**
  1. ...
  2. ...
* **Testing:** exact validation command or manual check
* **Assumptions:** ...
* **Rationale:** ...

**[Deferred]**
Findings that can wait, with revisit triggers. Write `None` if empty.
```

### Converge Mode

Use converge mode when the user asks to review and fix, converge, iterate, or produce a verdict.

Guards:

- `MAX_PASSES = 3` by default.
- Fix only blocking findings: critical/high findings, regressions, failing tests, and findings that block the user's stated goal.
- Do not chase low-severity cleanup during convergence.
- Do not chase Ponytail-only simplifications during convergence unless they remove a blocking
  risk, remove an avoidable new dependency, or directly reduce the blast radius of a blocking fix.
- Stop on thrash: if a finding considered fixed reappears, or the same span keeps changing without reducing risk, stop and report the contested item.

Loop:

1. Initial review of WIP scope.
2. Triage findings:
   - accept: clear and worth fixing now
   - adapt: valid issue, better local fix than reviewer suggested
   - reject: false positive, style preference, already handled, or not worth changing
3. Apply accepted/adapted blocking fixes in one localized edit pass.
4. Run relevant formatting, linting, and tests.
5. Recompute changed files since the prior pass:

```bash
git diff --name-only HEAD
git ls-files --others --exclude-standard
```

6. Re-review only:
   - files changed by the fix pass
   - files with still-open blocking findings
   - directly affected tests or dependents that are obvious from imports, call sites, or blast radius analysis
7. Compare current findings with previous findings by `file + category + title`, ignoring line-number drift.
8. Decide:
   - PASS if no open critical/high findings remain, no regressions are found, and required tests pass.
   - FAIL if blocking findings remain after `MAX_PASSES`, tests still fail, or thrash is detected.

### Verdict Output

At the end of converge mode, write artifacts when filesystem access allows it:

- `.devtribunal/verdict.json`
- `.devtribunal/review-<timestamp>.md`

If writing artifacts is not possible, print the same content in the final response.

`verdict.json` shape:

```json
{
  "verdict": "pass | fail",
  "passes": 1,
  "reason": "passed | budget_exhausted | thrash | tests_failed | blocked_findings",
  "open_blocking_findings": [],
  "fixed_findings": [],
  "new_findings": [],
  "regressed_findings": [],
  "tests": [
    {
      "command": "string",
      "status": "passed | failed | skipped",
      "summary": "string"
    }
  ]
}
```

Final response for converge mode:

```text
Verdict: PASS | FAIL
Passes: N
Changed: concise list of fixes applied
Open blocking findings: none | concise list
Tests: command and result
Artifacts: paths or "not written"
```

### Review-Only Final Response

For non-converge reviews, lead with findings ordered by severity. Then include open questions, tests run, and a short manager plan.

Use this shape:

```text
**Findings**
1. [severity] path:line - title
   Why: ...
   Fix: ...

**Open Questions**
None | ...

**Tests/Tools**
command - result

**Plan**
Priority-ordered work units or "No actionable findings."
```
````

## Notes for Codex, Grok, and Gemini

- If the runtime has a subagent tool, use it for the specialist reviewers and keep the main session as editor/orchestrator, so the loop's churn never lands in the caller's context; the caller receives only the findings table and verdict.
- If the runtime cannot spawn subagents, run each reviewer role inline and keep the same output contracts.
- If the runtime has weak file editing or shell access, perform review-only mode and return exact patches or fix instructions.
- If the runtime supports model routing, send specialist reviewers to cheaper capable models and reserve the strongest model for synthesis and edits.
- Do not require devtribunal MCP tools. This loop duplicates the behavior using normal file reads, shell commands, optional subagents, and structured findings.
