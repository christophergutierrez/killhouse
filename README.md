# Killhouse

> A rigorous, unforgiving AI pipeline where code is planned, tested, and audited without mercy.

Killhouse is an orchestration hub for AI coding agents. It solves "Skill Hell" and context bloat by utilizing **Delegated Orchestration**.

Instead of loading massive prompts into your main agent session—which burns tokens and degrades reasoning—Killhouse separates the *triggers* from the *payloads*. Lightweight skills act as pointers in your main chat, spawning independent, heavy subagents to handle rigorous Software Development Life Cycle (SDLC) loops.

> **Prefer to watch?** [7-minute explainer →](https://youtu.be/8kxfaLByVbE) — a walkthrough of how the pipeline works.

## Quickstart

Killhouse ships plugin manifests for both Claude Code and Codex:

- Claude Code: `plugin.json` (at repo root)
- Codex: `.codex-plugin/plugin.json`

The pipeline itself is plain Markdown. If a runtime can read files, run shell commands, and follow
`SKILL.md` instructions, it can run Killhouse even without first-class plugin support.

The helper scripts in `bin/` (validator, delegation logging, gate replay, redqueen driver) require
**Python 3.11+** on `PATH` as `python3`. They are stdlib-only — no packages to install.

### Claude Code

Requires [Claude Code](https://docs.claude.com/en/docs/claude-code) v2.1+.

**The lazy way — let an agent do it.** In Claude Code, just say:

```text
> install killhouse from github.com/christophergutierrez/killhouse
```

Add "with redqueen" to include the prompt-evolution engine. The agent runs the `claude plugin` CLI for you.

**The fastest path - install it yourself from the Claude marketplace.** In a terminal:

```bash
claude plugin marketplace add christophergutierrez/killhouse
claude plugin install killhouse@killhouse
```

Then start a fresh Claude Code session (skills activate next session) and kick off the pipeline:

```text
> /ask-kh I want to build a new feature.
```

### Codex

Install Killhouse from a Codex marketplace source that points at this repository. For a local checkout,
first register that checkout as a marketplace source, then install the plugin from it:

```bash
git clone --recursive https://github.com/christophergutierrez/killhouse.git
cd killhouse
codex plugin marketplace add .
codex plugin list
codex plugin add killhouse@<marketplace-name-shown-by-list>
```

Then start a fresh Codex thread so the skills are loaded. Kick off the pipeline by asking Codex to use
the `ask-kh` skill:

```text
> Use ask-kh for this feature: I want to build a new feature.
```

If the plugin is not installed, tell Codex to read `skills/ask-kh/SKILL.md` directly; all stages resolve
to files in this repository.

### Optional Model Routing

Killhouse uses abstract tiers: `fast`, `standard`, and `reasoning`. Model routing is optional. If you
do not configure it, Killhouse uses the current runtime model for every tier.

If you use a proxy or multiple providers, start from `.killhouse/config.example.json` and create either
`.killhouse/config.json` for a project default or `.killhouse/config.local.json` for a local override.
Configured model ids are exact. Killhouse will echo the resolved tier map before using it and will not
substitute nearby versions or equivalent-looking models. If a config exists but is invalid, Killhouse
stops before the pipeline instead of silently falling back.

**Optional - add redqueen (the prompt-evolution engine).** Skip this to just try the pipeline; the
"evolve execution prompt" stage auto-degrades to a plain prompt when redqueen isn't present. Requires
[`uv`](https://docs.astral.sh/uv/):

```bash
git clone --recursive https://github.com/christophergutierrez/killhouse.git
cd killhouse/lib/redqueen && uv sync && cd ../..

# proves plumbing end-to-end; prompt intentionally not written; exit 0 confirms plumbing
bin/evolve_exec_prompt.py --mock --rounds 2 --iterations 3 --init-random 2 --batch 2 \
  --out runs/exec --prompt-out redqueen-exec-prompt.md
```

For a *meaningful* evolved prompt, point it at a local model (`OPENAI_BASE_URL` + `DRQ_MODEL`) and run
without `--mock`. Alternatively, let killhouse drive an OpenAI-compatible provider (e.g. fireworks.ai):
add `base_url`, `api_key_env` (the *name* of the env var holding the token — the secret stays in the
environment), and `redqueen_tier` to `.killhouse/config.*`. When killhouse invokes redqueen, that config
is authoritative and overrides the ambient environment; `bin/evolve_exec_prompt.py --print-routing` shows
the resolved routing. Standalone redqueen runs are unaffected. To remove Killhouse later, use the
uninstall command for your runtime, such as `claude plugin uninstall killhouse` in Claude Code or the
corresponding `codex plugin` removal command in Codex.

## The Architecture

```text
killhouse/
├── skills/       # Pointers: Ultra-lightweight triggers for the main agent
├── loops/        # Payloads: Heavy, multi-agent markdown instructions
└── lib/          # Submodules: Executable code dependencies (e.g., Red Queen)
```

## The Pipeline

Killhouse enforces a strict, multi-stage gauntlet for feature development. For trivial tasks, the pipeline routes directly to execution. For major features, it follows this exact flow:

```mermaid
graph TD
    A[Start] --> B{/classify}
    B -->|Trivial| G
    B -->|Major| C[/grill-with-docs + /to-prd/]
    
    C --> D[REVIEW_DOCUMENT.md]
    D -->|9-Agent Audit Loop| D
    
    D --> E[PLAN.md]
    E -->|Verified Planning Loop| E
    
    E --> F[lib/redqueen]
    F -->|Evolve Execution Prompt| F
    
    F --> G[IMPLEMENT_MILESTONE.md]
    G -->|TDD Execution| G
    
    G --> H[CODE_REVIEW_TRIBUNAL.md]
    H -->|Fix Blocking Findings| H
    
    H --> I[ARCHITECTURE_DESIGN.md]
    I -->|Depth & Boundary Check| I
    
    I --> J[Done]
```

1. **Classify** (`skills/classify/SKILL.md`): Determines task complexity and routes trivial vs. major. Use `/triage` instead when the request comes from a GitHub issue or PR.
2. **Discovery** (`skills/grill-with-docs/SKILL.md` and `skills/to-prd/SKILL.md`): Establishes the domain model and synthesizes the Product Requirements Document (PRD).
3. **Spec Audit** (`loops/REVIEW_DOCUMENT.md`): A 9-subagent loop that computes arithmetic, checks assumptions, and enforces narrative flow until the PRD reaches convergence.
4. **Planning** (`loops/PLAN.md`): Does not write code. Generates an `implementation-plan.md` with traceability matrices and falsifiable terminal gates.
5. **Prompt Evolution** (`lib/redqueen`): The Digital Red Queen evolves the execution prompt before implementation begins.
6. **Execution** (`loops/IMPLEMENT_MILESTONE.md`): TDD-driven execution of the plan's vertical slices.
7. **Code Review** (`loops/CODE_REVIEW_TRIBUNAL.md`): A multi-agent gatekeeper routing files to specialists: Language, Security, Tests, Docs, and a Ponytail simplification reviewer. The Ponytail reviewer looks only for unnecessary complexity that can be deleted, reused, or replaced by existing platform behavior without weakening safety. An architect synthesizes the findings into a `PASS` verdict.
8. **Architecture Review** (`loops/ARCHITECTURE_DESIGN.md`): The final health check to eliminate shallow modules, leaky boundaries, and domain-language disconnects.

## Usage

Once the plugin is installed (see [Quickstart](#quickstart)), start any new project, major feature, or workflow-routing request with:

```text
> /ask-kh I want to build a new feature.
```

In Codex, ask for the same skill by name:

```text
> Use ask-kh for this feature: I want to build a new feature.
```

The agent will parse `skills/ask-kh/SKILL.md` for minimal context cost, classify the request through
`/classify` in Claude Code or the `classify` skill in Codex, and then route either to the trivial fast path
or the full grilling-to-implementation pipeline.

## Operating Principles

- **Single Source of Truth:** Never duplicate reference material. If a template is needed, hide it behind a context pointer.
- **No No-Ops:** Every instruction must explicitly alter agent behavior.
- **Strict Leading Words:** Use dense, predictable vocabulary—for example, "vertical slice"—to steer agent reasoning traces.
- **Falsifiable Gates:** A gate that cannot be proven to fail at baseline is documentation, not a gate.
- **Expensive Reasoning at Boundaries:** Reasoning-tier agents write contracts and handle ambiguous or
  high-risk review; standard-tier agents do routine contract checks, and cheaper capable tiers do
  first-pass production coding unless an explicit rescue or safety exception is recorded.

## Releasing

When skills, loops, or plugin manifests change, bump the plugin version before publishing so runtime
plugin caches can detect the update:

```bash
bin/bump_plugin_version.py --patch
bin/killhouse_validate.py --check manifests
```

## Credits

A big thank-you to [Matt Pocock](https://github.com/mattpocock) — the front end of this pipeline stands on his work. The grilling, domain-modeling, and PRD skills come straight from his excellent [mattpocock/skills](https://github.com/mattpocock/skills) repo; Killhouse just wraps them in a heavier, more opinionated gauntlet. Go read the original — it's worth your time.

- The front-end skills (`triage`, `grill-with-docs`, `grilling`, `domain-modeling`, `to-prd`) are vendored from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) and customized for this pipeline. See [`skills/NOTICE.md`](./skills/NOTICE.md).
- The Digital Red Queen (`lib/redqueen`) is included as a submodule from [christophergutierrez/redqueen](https://github.com/christophergutierrez/redqueen).
