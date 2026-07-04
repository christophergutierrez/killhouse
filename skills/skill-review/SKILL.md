---
name: skill-review
description: Review and optionally fix active agent-instruction documents (skills, loops, AGENTS.md, manifests). Use when the user asks to review, audit, or improve Killhouse's own skills or loops. Runs loops/SKILL_REVIEW.md. When not to use: for application code changes, use /ask-kh instead.
---

# Skill Review

This skill runs `loops/SKILL_REVIEW.md` directly. Read that file and follow it.

## Default inputs

- **TARGET_REPOSITORY**: current working directory (repo root).
- **SCOPE**: `wip` — changed and untracked files. Pass `all` to review every instruction surface.
- **MODE**: `review-only`. The user must explicitly request `converge` to apply fixes.
- **RUNTIMES**: Claude Code, Codex, and generic file-reading agents.
- **MAX_PASSES**: 3.

## How to invoke

In Claude Code: `/skill-review` (review WIP), `/skill-review all` (full audit), `/skill-review converge` (review + fix).

In Codex or generic agents: ask for the `skill-review` skill by name, or read `loops/SKILL_REVIEW.md` directly and set `SCOPE` and `MODE` as needed.
