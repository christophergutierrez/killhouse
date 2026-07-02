# AGENTS.md — operating instructions for Killhouse

This repository is not an app to build; it **is** a pipeline you (the agent) run. It moves a code
change through a strict gauntlet: triage → grilling → PRD → spec audit → planning → prompt evolution
→ TDD implementation → code-review tribunal → architecture review. Read this file first, then start
at the entrypoint.

## Installing (if the plugin isn't set up yet)

If the user asks to install/set up Killhouse, follow **`skills/install-killhouse/SKILL.md`** — it
handles the redqueen branch (include when they say "with redqueen"; ask when unspecified). The whole
install is agent-runnable via the `claude plugin` CLI; no user-typed slash commands are needed. Cold-start
essentials:

```bash
git clone --recursive https://github.com/christophergutierrez/killhouse.git && cd killhouse
claude plugin marketplace add christophergutierrez/killhouse
claude plugin install killhouse@killhouse           # skills activate next session
# optional redqueen: cd lib/redqueen && uv sync && cd ../..
```

## Entrypoint

To run the pipeline, read and follow **`skills/ask-kh/SKILL.md`** (invocable as `/ask-kh` when the
plugin is installed). It is the stateful driver: it classifies the request, routes it through the
stages, and holds the autonomy setting (Checkpoint vs Autopilot).

## How references resolve

The skills invoke each other and the loops by name. Resolve them as files:

- `/triage`, `/grill-with-docs`, `/grilling`, `/domain-modeling`, `/to-prd`, `/ask-kh`
  → `skills/<name>/SKILL.md`
- A loop stage named in caps (e.g. `REVIEW_DOCUMENT`, `PLAN`, `IMPLEMENT_MILESTONE`,
  `CODE_REVIEW_TRIBUNAL`, `ARCHITECTURE_DESIGN`) → `loops/<NAME>.md`
- The prompt-evolution engine → `lib/redqueen` (a git submodule; see below)

If your runtime supports Claude Code plugins, the skills register as real slash commands via
`.claude-plugin/plugin.json`. If not, reach every skill by reading its `SKILL.md` directly — the
pipeline is plain markdown and works in any agent that can read files and run shell commands.

## Non-negotiables (hold these even if you never open `ask-kh`)

- **Context hygiene.** Each heavy loop runs as a *delegated subagent*. Never inline a loop's rounds,
  reviewer transcripts, or raw tool output into the main session. A stage returns only its **artifact
  path + verdict**; the artifact is the handoff, the transcript is discarded.
- **Budget caps.** Every loop is individually capped, and Autopilot has an aggregate budget guard
  (`max_milestones_unattended`, `max_pipeline_reentries`, optional `token_budget`). On a trip, degrade
  to Checkpoint mode and ask — never silently keep spending, never silently halt the work.
- **Mandatory gates always stop**, in either autonomy mode: PLAN blast-radius `BLOCKED`,
  IMPLEMENT_MILESTONE `STALE`/`VACUOUS_GATE`/`BLOCKED_DEPENDENCY`, an un-auto-fixable tribunal finding,
  or an architecture safety gate.

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

# offline plumbing check — proves the wiring; fitness is 0.0, so the prompt is NOT meaningful
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
