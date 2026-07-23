# AGENTS.md — operating instructions for Killhouse

This repository is not an app to build; it **is** a pipeline you (the agent) run. It moves a code
change through a strict gauntlet: triage → grilling → PRD → spec audit → planning → prompt evolution
→ TDD implementation → code-review tribunal → architecture review. Read this file first, then start
at the entrypoint.

## Installing (if the plugin isn't set up yet)

If the user asks to install/set up Killhouse, follow **`skills/install-killhouse/SKILL.md`** — it
handles the runtime-specific plugin install and the redqueen branch (include when they say "with
redqueen"; ask when unspecified). The whole install should be agent-runnable via the current runtime's
plugin CLI; no user-typed slash commands are needed. Cold-start essentials:

```bash
git clone --recursive https://github.com/christophergutierrez/killhouse.git && cd killhouse

# Claude Code
claude plugin marketplace add christophergutierrez/killhouse
claude plugin install killhouse@killhouse           # skills activate next session

# Codex (from a local marketplace source that points at this checkout)
codex plugin marketplace add .
codex plugin list
codex plugin add killhouse@<marketplace-name-shown-by-list>  # skills activate next thread

# optional redqueen: cd lib/redqueen && uv sync && cd ../..
```

## Entrypoint

To run the pipeline, read and follow **`skills/ask-kh/SKILL.md`**. In Claude Code it is invocable as
`/ask-kh` when the plugin is installed; in Codex, ask for the `ask-kh` skill by name. It is the
stateful driver: it classifies the request, routes it through the stages, and holds the autonomy
setting (Checkpoint vs Autopilot).

## Model tier map

Killhouse uses abstract capability tiers: `fast`, `standard`, and `reasoning`. A model tier map is
optional. If none exists, use the current runtime model for every tier and record
`model_routing: current-model-only`.

If `.killhouse/config.json` or `.killhouse/config.local.json` exists, treat the configured model ids as
exact opaque runtime identifiers. Do not substitute "nearby" model names. A valid map must define all
three tiers as non-empty strings. If a config exists but is invalid, stop before the pipeline and ask
the user to fix or remove it; do not silently fall back. Before running the pipeline, echo the resolved
map so the user sees exactly which model id is assigned to each tier. If model routing is unavailable,
say so and do not pretend the map was applied.

For changes to active agent-instruction documents rather than application code, run
**`loops/SKILL_REVIEW.md`**. Use it for `skills/**/SKILL.md`, `loops/**/*.md`, `AGENTS.md`,
`README.md`, plugin manifests, marketplace manifests, install docs, and any document an agent is
expected to execute as instructions.

In Claude Code, invoke it directly as `/skill-review` (or `/skill-review converge` to review and
fix). In Codex or generic agents, use the `skill-review` skill by name, or read
`skills/skill-review/SKILL.md` directly.

## How references resolve

The skills invoke each other and the loops by name. Resolve them as files:

- `/triage`, `/grill-with-docs`, `/grilling`, `/domain-modeling`, `/to-prd`, `/ask-kh`
  → `skills/<name>/SKILL.md`
- A loop stage named in caps (e.g. `REVIEW_DOCUMENT`, `PLAN`, `IMPLEMENT_MILESTONE`,
  `CODE_REVIEW_TRIBUNAL`, `ARCHITECTURE_DESIGN`, `SKILL_REVIEW`) → `loops/<NAME>.md`
- The prompt-evolution engine → `lib/redqueen` (a git submodule; see below)

If your runtime supports Claude Code plugins, the skills register as real slash commands via
`.claude-plugin/plugin.json`. If your runtime supports Codex plugins, the skills register via
`.codex-plugin/plugin.json`. If not, reach every skill by reading its `SKILL.md` directly — the
pipeline is plain markdown and works in any agent that can read files and run shell commands.

## Non-negotiables (hold these even if you never open `ask-kh`)

- **Context hygiene.** Each heavy loop runs as a *delegated subagent*. Never inline a loop's rounds,
  reviewer transcripts, or raw tool output into the main session. A stage returns only its **artifact
  path + verdict**; the artifact is the handoff, the transcript is discarded.
- **Budget caps.** Every loop is individually capped, and Autopilot has an aggregate budget guard
  (`max_milestones_unattended`, `max_pipeline_reentries`, optional `token_budget`). On a trip, degrade
  to Checkpoint mode and ask — never silently keep spending, never silently halt the work.
- **Implementation economics.** Reasoning-tier agents write file contracts, architecture decisions, and
  escalation feedback by default. Cheaper capable tiers do first-pass production coding, and
  standard-tier agents handle routine contract review. Use reasoning-tier review or code only for an
  explicit ambiguity, rescue, security/safety patch, cross-cutting refactor, or no-routing fallback, and
  record why the cheaper path was insufficient.
- **Mandatory gates always stop**, in either autonomy mode: PLAN blast-radius `BLOCKED`,
  IMPLEMENT_MILESTONE `STALE`/`VACUOUS_GATE`/`BLOCKED_DEPENDENCY`, an un-auto-fixable tribunal finding,
  or an architecture safety gate.
- **Delegation logging.** Before each subagent delegation, append one routing-calibration record per
  `loops/DELEGATION_LOG.md` (schema: `schemas/delegation_record.schema.json`). This is data collection
  only — it never changes tier selection and never blocks a delegation. The offline gate-replay harness
  (`bin/killhouse_gate_replay.py`) re-runs a logged delegation on a lower tier against its **real** gate;
  it never substitutes a model's judgment for running the gate, and records `SKIPPED_NO_ROUTING` rather
  than faking a cheaper-tier run when no model tier map is configured.
- **Mechanical plan execution.** When a complete delegation plan is ready, the conductor
  (`bin/killhouse_conduct.py` + `loops/CONDUCT.md`) is a zero-intelligence driver that walks the
  delegation DAG in topological order, runs each delegation through its planned tier and real gate,
  escalates on failure, and writes records mechanically—used for headless replay or extension without
  human orchestration.

## Working with the `lib/redqueen` submodule

`lib/redqueen` is a **separate git repository** (the Digital Red Queen engine) vendored in as a
submodule. Treat it as its own project, not as ordinary files in this repo.

**Keeping it current on pull.** A plain `git pull` does *not* update submodules. Always pull Killhouse
and its submodule together:

```bash
git pull --recurse-submodules
```

Run this once so every future pull does it automatically:

```bash
git config submodule.recurse true
```

After a plain clone or pull that missed it, hydrate the submodule with:

```bash
git submodule update --init --recursive
```

(A fresh clone should use `git clone --recursive <url>`.)

**⚠️ Changes to redqueen do NOT go up when you push Killhouse.** Because `lib/redqueen` is a separate
repo, committing and pushing Killhouse only records a *pointer* to a redqueen commit — it does not push
redqueen's own contents anywhere. If you (or the user) edit anything under `lib/redqueen`, **warn the
user** and give them these steps:

```bash
# 1. Publish the redqueen change to ITS repo first
cd lib/redqueen
git add -A && git commit -m "…"
git push                       # pushes to the redqueen remote

# 2. Then record the new pointer in Killhouse and push that
cd ../..
git add lib/redqueen
git commit -m "Bump redqueen to <short-sha>"
git push
```

If Killhouse is pushed **before** redqueen is pushed, Killhouse will point at a commit that does not
exist on redqueen's remote — a dangling submodule pointer that breaks clones for everyone else. As an
agent: never commit only the Killhouse pointer for a redqueen change; either do both steps or stop and
tell the user exactly what remains to push.

## Prompt evolution (the redqueen stage)

The "evolve execution prompt" stage is driven by **`bin/evolve_exec_prompt.py`**, which runs redqueen
and writes the champion prompt to an artifact (`redqueen-exec-prompt.md` by default) that
`loops/IMPLEMENT_MILESTONE` reads as `REDQUEEN_PROMPT`.

Setup and use:

```bash
# one-time (or let `uv run` resolve deps on first call)
cd lib/redqueen && uv sync && cd ../..

# offline plumbing check — proves the wiring; prompt intentionally not written; exit 0 confirms plumbing
bin/evolve_exec_prompt.py --mock --rounds 2 --iterations 3 --init-random 2 --batch 2 \
  --out runs/exec --prompt-out redqueen-exec-prompt.md

# real evolution — needs a model endpoint (the worker generates patches, the evolver mutates prompts)
OPENAI_BASE_URL=http://localhost:11434/v1 DRQ_MODEL=qwen2.5-coder:32b OPENAI_API_KEY=ollama \
  bin/evolve_exec_prompt.py --out runs/exec --prompt-out redqueen-exec-prompt.md

# cheap reuse — extract the champion from an evolution you already ran
bin/evolve_exec_prompt.py --champions runs/exec/champions.json --prompt-out redqueen-exec-prompt.md
```

This stage is **optional and self-degrading**: if the submodule isn't hydrated, `uv` isn't available,
no endpoint is configured, or the champion's fitness is `0.0`, the adapter says so and
`IMPLEMENT_MILESTONE` proceeds with a plain implementer prompt. A real evolution is expensive
(many LLM calls); the intended pattern is to evolve occasionally and reuse the champion via
`--champions`.

**Config precedence — killhouse drives redqueen, not the other way around.** redqueen is a standalone
project with its own env-based config; when *killhouse* invokes it, killhouse's config wins. If
`.killhouse/config.*` declares a `base_url` (with `api_key_env` naming the token's env var and
`redqueen_tier` picking the model), `bin/evolve_exec_prompt.py` injects that OpenAI-compatible routing
into the redqueen subprocess, **overriding the ambient environment** — so you can point redqueen at an
external provider like fireworks.ai without editing the submodule. With no `base_url`, redqueen keeps its
own env/config. `--print-routing` shows what will be injected.
