#!/usr/bin/env python3
"""Killhouse ↔ redqueen integration glue.

Produce the adversarially-robust *execution prompt* that `loops/IMPLEMENT_MILESTONE`
consumes as `REDQUEEN_PROMPT`. This is the concrete command behind the pipeline's
"evolve execution prompt" stage.

Two modes:

  # Evolve fresh, then extract the champion prompt (needs an LLM endpoint for a
  # meaningful result; see the env vars below). Mock mode proves the plumbing only.
  bin/evolve_exec_prompt.py --out runs/exec1 --prompt-out redqueen-exec-prompt.md

  # Skip evolution, just extract the best prompt from a champions.json you already have
  # (the realistic production path — evolve once offline, reuse the champion cheaply).
  bin/evolve_exec_prompt.py --champions runs/exec1/champions.json --prompt-out redqueen-exec-prompt.md

The evolvable genome for the `code_improvement` domain IS a bug-fixing system prompt,
which is exactly what an implementation loop wants steering it. We select the champion
with the highest held-out fitness (ties broken by latest round).

Real runs need a model endpoint (the worker generates patches, the evolver mutates prompts):
  OPENAI_BASE_URL=http://localhost:11434/v1  DRQ_MODEL=qwen2.5-coder:32b   OPENAI_API_KEY=ollama

When killhouse invokes redqueen, killhouse's config is authoritative: if `.killhouse/config.*`
declares a `base_url`, that endpoint + the `redqueen_tier` model id + the `api_key_env` token
OVERRIDE the ambient environment for the redqueen subprocess (the submodule is never edited).
`--print-routing` shows the resolved routing without running an evolution.

Exit codes: 0 ok; 2 redqueen run/extract failed; 3 no usable champion or fitness==0.0 on a real
run (caller should degrade to a plain implementer prompt). --mock always exits 0 to confirm
plumbing; the prompt is intentionally not written since fitness will be 0.0.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# killhouse/bin/evolve_exec_prompt.py -> killhouse/lib/redqueen
KILLHOUSE_ROOT = Path(__file__).resolve().parents[1]
REDQUEEN_DIR = KILLHOUSE_ROOT / "lib" / "redqueen"


class ConfigError(Exception):
    """Raised when killhouse's config asks for external routing it cannot fulfill."""


def load_killhouse_config(root: Path) -> dict[str, Any]:
    """Read killhouse routing config, local override first, then project default."""
    for name in ("config.local.json", "config.json"):
        path = root / ".killhouse" / name
        if path.is_file():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError as exc:
                raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    return {}


def resolve_routing(base_env: dict[str, str], kh: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """Inject killhouse routing into a redqueen subprocess env.

    When killhouse invokes redqueen, killhouse's config is authoritative: if it declares a
    `base_url`, that endpoint (plus the `redqueen_tier` model id and the named API key) OVERRIDES
    whatever is in the ambient environment. When killhouse declares no `base_url`, redqueen keeps
    its own env/config untouched. Returns the new env and human-readable notes on what was set.
    """
    env = dict(base_env)
    notes: list[str] = []

    base_url = kh.get("base_url")
    if not (isinstance(base_url, str) and base_url.strip()):
        return env, notes  # killhouse is not driving external routing; leave redqueen's env alone

    env["OPENAI_BASE_URL"] = base_url
    notes.append(f"base_url={base_url}")

    tiers = kh.get("model_tiers")
    if not isinstance(tiers, dict):
        raise ConfigError("base_url is set but model_tiers is missing; cannot pick redqueen's model")
    tier = kh.get("redqueen_tier", "standard")
    model = tiers.get(tier)
    if not (isinstance(model, str) and model.strip()):
        raise ConfigError(f"redqueen_tier '{tier}' has no model_tiers entry (have: {sorted(tiers)})")
    env["DRQ_MODEL"] = model
    notes.append(f"model={model} (tier={tier})")

    api_key_env = kh.get("api_key_env")
    if isinstance(api_key_env, str) and api_key_env.strip():
        token = base_env.get(api_key_env)
        if not token:
            raise ConfigError(
                f"config api_key_env='{api_key_env}' but that variable is not set in the environment"
            )
        env["OPENAI_API_KEY"] = token
        notes.append(f"api_key<-${api_key_env}")

    return env, notes


def run_evolve(args: argparse.Namespace) -> Path:
    """Run redqueen's evolve subcommand inside the submodule; return champions.json path."""
    if not (REDQUEEN_DIR / "run.py").is_file():
        sys.exit(
            f"[error] redqueen not found at {REDQUEEN_DIR}. The submodule is not hydrated — run:\n"
            "        git submodule update --init --recursive"
        )
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "uv", "run", "--quiet", "python", "run.py", "evolve",
        "--domain", args.domain,
        "--rounds", str(args.rounds),
        "--iterations", str(args.iterations),
        "--init-random", str(args.init_random),
        "--batch", str(args.batch),
        "--workers", str(args.workers),
        "--seed", str(args.seed),
        "--out", str(out_dir),
    ]
    env = os.environ.copy()
    if args.mock:
        env["DRQ_LLM_MOCK"] = "1"
    else:
        try:
            env, notes = resolve_routing(env, load_killhouse_config(KILLHOUSE_ROOT))
        except ConfigError as exc:
            die(2, f"[error] killhouse config: {exc}")
        if notes:
            print(f"[info] redqueen routing from killhouse config: {', '.join(notes)}", file=sys.stderr)
        elif "OPENAI_BASE_URL" not in env and "DRQ_MODEL" not in env:
            print(
                "[warn] no OPENAI_BASE_URL / DRQ_MODEL set and --mock not passed; a real "
                "evolution needs a model endpoint or fitness will be meaningless.",
                file=sys.stderr,
            )
    print(f"[info] evolving in {REDQUEEN_DIR} -> {out_dir}", file=sys.stderr)
    try:
        proc = subprocess.run(cmd, cwd=REDQUEEN_DIR, env=env)
    except FileNotFoundError:
        die(2,
            "[error] uv not found. Install it: https://docs.astral.sh/uv/\n"
            "        Then re-run: bin/evolve_exec_prompt.py ...")
    if proc.returncode != 0:
        sys.exit(2)
    return out_dir / "champions.json"


def die(code: int, message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(code)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def usable_champion(candidate: Any) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    fitness = candidate.get("fitness")
    round_number = candidate.get("round")
    genome = candidate.get("genome")
    if not is_number(fitness) or not is_number(round_number) or not isinstance(genome, str):
        return None
    if not genome.strip():
        return None
    return candidate


def best_champion(champions_path: Path) -> dict[str, Any]:
    try:
        champions = json.loads(champions_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        die(2, f"[error] cannot read champions file {champions_path}: {e}")
    if not isinstance(champions, list):
        die(2, f"[error] champions file {champions_path} must contain a JSON list")
    usable = [champ for candidate in champions if (champ := usable_champion(candidate)) is not None]
    if not usable:
        die(3, f"[warn] no usable champion found in {champions_path}")
    # highest fitness; tie-break on latest round so a later, equally-fit prompt wins
    return max(usable, key=lambda c: (c["fitness"], c["round"]))


def main() -> None:
    p = argparse.ArgumentParser(
        description="Evolve/extract the redqueen execution prompt for IMPLEMENT_MILESTONE."
    )
    p.add_argument("--champions", metavar="PATH",
                   help="extract from an existing champions.json instead of running evolve")
    p.add_argument("--prompt-out", default="redqueen-exec-prompt.md", metavar="PATH",
                   help="where to write the extracted execution prompt (default: ./redqueen-exec-prompt.md)")
    p.add_argument("--domain", default="code_improvement", choices=["code_improvement", "text2sql"],
                   help="redqueen domain to evolve (default: code_improvement — its genome is a fix prompt)")
    p.add_argument("--out", default="runs/exec",
                   help="redqueen output dir when evolving (default: runs/exec)")
    p.add_argument("--mock", action="store_true", help="offline plumbing check (fitness will be 0.0)")
    p.add_argument("--print-routing", action="store_true",
                   help="resolve killhouse config -> redqueen env and print it, then exit")
    p.add_argument("--rounds", type=int, default=8)
    p.add_argument("--iterations", type=int, default=20)
    p.add_argument("--init-random", type=int, default=6)
    p.add_argument("--batch", type=int, default=4)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    if args.print_routing:
        try:
            _, notes = resolve_routing(os.environ.copy(), load_killhouse_config(KILLHOUSE_ROOT))
        except ConfigError as exc:
            die(2, f"[error] killhouse config: {exc}")
        if notes:
            print("redqueen routing (killhouse config drives, overriding ambient env):")
            for note in notes:
                print(f"  {note}")
        else:
            print("redqueen routing: killhouse config sets no base_url; "
                  "redqueen uses the ambient env / its own config.")
        return

    champions_path = Path(args.champions).resolve() if args.champions else run_evolve(args)
    champ = best_champion(champions_path)
    fitness = champ.get("fitness", 0.0)

    if args.mock:
        # Mock runs confirm plumbing only; fitness is always 0.0 by design, prompt not written.
        print(f"[ok] plumbing verified (mock); prompt intentionally not written (fitness={fitness})")
        return

    prompt_out = Path(args.prompt_out).resolve()

    if fitness == 0.0:
        die(3,
            "[warn] champion fitness is 0.0 — mock run or no improvement found.\n"
            "       Prompt NOT written. IMPLEMENT_MILESTONE will use a plain implementer prompt.\n"
            "       Re-run with a real model endpoint to get a meaningful evolved prompt.")

    header = (
        "<!-- Evolved by redqueen (Digital Red Queen). Consumed by loops/IMPLEMENT_MILESTONE "
        f"as REDQUEEN_PROMPT. domain={args.domain} round={champ.get('round')} fitness={fitness} "
        f"source={champions_path} -->\n\n"
    )
    prompt_out.write_text(header + champ["genome"].rstrip() + "\n")
    print(f"[ok] wrote execution prompt -> {prompt_out} (round={champ.get('round')}, fitness={fitness})")


if __name__ == "__main__":
    main()
