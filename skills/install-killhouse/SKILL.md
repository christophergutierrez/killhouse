---
name: install-killhouse
description: Install the Killhouse plugin, and optionally the redqueen prompt-evolution engine. Use when the user asks to install, set up, or add Killhouse — e.g. "install killhouse", "install killhouse with redqueen", "set up killhouse without redqueen". Ask about redqueen only when the user did not specify.
---

# Install Killhouse

You (the agent) can perform this install end to end with the `claude plugin` CLI and shell — no
user-typed slash commands are required. Work through the steps in order, running the commands
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

- If you are already inside a Killhouse checkout (a `.claude-plugin/` and `AGENTS.md` are present),
  use it. If redqueen is wanted, ensure the submodule is hydrated: `git submodule update --init --recursive`.
- Otherwise clone it. Use `--recursive` whenever redqueen is wanted (harmless otherwise):
  ```bash
  git clone --recursive https://github.com/christophergutierrez/killhouse.git
  cd killhouse
  ```

## Step 2 — Register the plugin (always)

```bash
claude plugin marketplace add christophergutierrez/killhouse
claude plugin install killhouse@killhouse
```

- Default scope is `user`. Add `--scope project` to tie it to the current repo instead.
- Confirm with `claude plugin list` (expect `killhouse@killhouse`).
- **The skills activate in a new session** — tell the user to restart Claude Code (or start a fresh
  session) before `/ask-kh` and the other commands appear.

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

- plugin installed (and scope), and that a fresh session is needed for the commands to appear;
- whether redqueen was set up, skipped by choice, or skipped because `uv` was missing;
- if redqueen was skipped, how to add it later: run this skill again and say **"install killhouse with
  redqueen"**.

## Edge cases

- **No network / clone fails** → report the failure; nothing was installed.
- **Already installed** → offer `claude plugin update killhouse` instead of re-installing (restart
  required to apply).
- **Validation check** (optional, before install) → `claude plugin validate .` from the repo root
  confirms the manifests are well-formed.
