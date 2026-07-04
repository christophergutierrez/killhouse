---
name: classify
description: Classify a request as trivial or major for the Killhouse pipeline. Use when ask-kh needs a routing decision from a conversation request (not an issue tracker). Returns classification and rationale. When not to use: if the request comes from a GitHub issue or PR, use /triage instead.
---

# Classify

Return `classification: trivial | major` and a one-line rationale to the caller.

## Trivial

All of the following must hold:

- Touches ≤ 5 files.
- No public API / persistent data / migrations / security / auth / billing / cross-ownership impact.
- Clear solution that does not require architecture judgment.
- Can be gate-checked by a single objective terminal command.

## Major

Any of the following applies:

- Touches a public contract, persisted data, migrations, security/auth/billing, or cross-ownership files.
- Scope is unclear or requires architecture judgment.
- Spans more than a handful of files.
- Benefits from a grilling pass to surface unstated requirements.

## Escalation rule

If a change classified as trivial turns out to cross a major boundary during implementation, re-classify as major and return to the full pipeline at `/grill-with-docs` (Claude Code) or the `grill-with-docs` skill (Codex).

## Output

Return exactly:

```
classification: trivial | major
rationale: one sentence
```
