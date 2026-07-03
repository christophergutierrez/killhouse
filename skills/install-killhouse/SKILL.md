---
name: install-killhouse
description: Install the Killhouse plugin for the current runtime, and optionally the redqueen prompt-evolution engine. Use when the user asks to install, set up, or add Killhouse — e.g. "install killhouse", "install killhouse with redqueen", "set up killhouse without redqueen". Ask about redqueen only when the user did not specify.
---

# Install Killhouse

You (the agent) can perform this install end to end with the current runtime's plugin CLI and shell —
no user-typed slash commands are required. Work through the steps in order, running the commands
yourself and reporting results.

## Step 0 — Decide the redqueen scope

`redqueen` is the optional prompt-evolution engine (a git submodule of Python code). Decide whether to
include it from the user's phrasing:

- Said **"with redqueen"** (or "and redqueen", "everything") → include it.
- Said **"without redqueen"** (or "just the skills", "skills only") → skip it.
- **Did not mention redqueen** → **ask before proceeding**: *"Also set up redqueen, the
  prompt-evolution engine? It needs `uv`, and — for a meaningful evolved prompt — a local model
  endpoint. Without it the pipeline still runs; the evolve step just degrades to a plain prompt.
  (yes / no)"* Wait for the answer.

## Step 1 — Get the repository

- If you are already inside a Killhouse checkout (`.claude-plugin/`, `.codex-plugin/`, and `AGENTS.md`
  are present),
  use it. If redqueen is wanted, ensure the submodule is hydrated: `git submodule update --init --recursive`.
- Otherwise clone it when you need a local checkout for Codex marketplace registration, generic
  file-reading use, validation, or redqueen setup. Use `--recursive` whenever redqueen is wanted
  (harmless otherwise):
  ```bash
  git clone --recursive https://github.com/christophergutierrez/killhouse.git
  cd killhouse
  ```
- Claude Code marketplace installs can install from the configured remote marketplace without a local
  checkout. If the user only wants that path and redqueen is not being set up, Step 1 may be skipped.

## Step 2 — Register the plugin (always)

Use the branch for the runtime you are currently running in.

### Claude Code

```bash
claude plugin marketplace add christophergutierrez/killhouse
claude plugin install killhouse@killhouse
```

- Default scope is `user`. Add `--scope project` to tie it to the current repo instead.
- Confirm with `claude plugin list` (expect `killhouse@killhouse`).
- **The skills activate in a new session** — tell the user to restart Claude Code (or start a fresh
  session) before `/ask-kh` and the other slash commands appear.

### Codex

Install from a Codex marketplace source that points at this repository or checkout:

```bash
codex plugin marketplace add .
codex plugin list
codex plugin add killhouse@<marketplace-name-shown-by-list>
```

- For a Git source, use `codex plugin marketplace add christophergutierrez/killhouse` or the HTTPS/SSH
  Git URL, then install `killhouse` from the marketplace name shown by `codex plugin list`.
- If the marketplace source is already configured, skip the `marketplace add` step and install from the
  existing marketplace.
- Confirm with `codex plugin list` (expect `killhouse` from the selected marketplace).
- **The skills activate in a new thread** — tell the user to start a fresh Codex thread before asking
  for the `ask-kh` skill.

## Step 3 — Set up redqueen (only if chosen in Step 0)

```bash
which uv || echo "uv not installed"     # redqueen needs uv
cd lib/redqueen && uv sync && cd ../..
```

- If `uv` is missing, do **not** fail the whole install — report that redqueen was skipped and point
  the user to https://docs.astral.sh/uv/ to install it, then re-run this skill "with redqueen".
- Prove the plumbing works offline (fitness will be `0.0` in mock — that is expected):
  ```bash
  bin/evolve_exec_prompt.py --mock --rounds 2 --iterations 3 --init-random 2 --batch 2 \
    --out runs/exec --prompt-out redqueen-exec-prompt.md
  ```
- Explain the real-use path: a meaningful evolved prompt needs a model endpoint, e.g.
  `OPENAI_BASE_URL=http://localhost:11434/v1 DRQ_MODEL=qwen2.5-coder:32b OPENAI_API_KEY=ollama`
  before running `bin/evolve_exec_prompt.py` without `--mock`.

## Step 4 — Report

Tell the user exactly what happened:

- plugin installed (runtime and scope/marketplace), and that a fresh session/thread is needed for the
  skills to appear;
- whether redqueen was set up, skipped by choice, or skipped because `uv` was missing;
- if redqueen was skipped, how to add it later: run this skill again and say **"install killhouse with
  redqueen"**.

## Edge cases

- **No network / clone fails** → report the failure; nothing was installed.
- **Already installed** → offer the runtime's update/reinstall flow instead of re-installing from
  scratch. In Claude Code, use `claude plugin update killhouse`; in Codex, reinstall from the
  marketplace after updating the plugin cache/version as required by the local Codex workflow.
- **Validation check** (optional, before install) → in Claude Code, `claude plugin validate .` from the
  repo root confirms the Claude manifest is well-formed. In Codex, validate `.codex-plugin/plugin.json`
  with the available Codex plugin validator or at least parse it as JSON before install.
