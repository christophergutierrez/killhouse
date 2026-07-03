#!/usr/bin/env python3
"""Read-only Killhouse self-hosting contract checks."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CheckFailure(Exception):
    pass


def read(path: str) -> str:
    return (ROOT / path).read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


def contains(path: str, needle: str) -> None:
    require(needle in read(path), f"{path} missing required text: {needle!r}")


def not_contains(path: str, needle: str) -> None:
    require(needle not in read(path), f"{path} contains forbidden text: {needle!r}")


def check_json(path: str) -> None:
    json.loads((ROOT / path).read_text())


def check_manifests() -> None:
    check_json(".codex-plugin/plugin.json")
    check_json(".claude-plugin/plugin.json")
    check_json(".claude-plugin/marketplace.json")

    claude = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    for skill_path in claude["skills"]:
        require((ROOT / skill_path / "SKILL.md").is_file(), f"missing Claude skill path {skill_path}")

    codex = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
    require((ROOT / codex["skills"]).is_dir(), "Codex skills directory does not exist")


def check_runtime_contracts() -> None:
    contains("AGENTS.md", "/ask-kh")
    contains("AGENTS.md", "ask-kh` skill by name")
    contains("AGENTS.md", "If your runtime supports Codex plugins")
    contains("skills/ask-kh/SKILL.md", "/triage")
    contains("skills/ask-kh/SKILL.md", "triage` skill by name")
    contains("skills/grill-with-docs/SKILL.md", "skills/grilling/SKILL.md")
    contains("skills/grill-with-docs/SKILL.md", "skills/domain-modeling/SKILL.md")
    contains("skills/triage/SKILL.md", "skills/grill-with-docs/SKILL.md")


def check_instruction_review() -> None:
    contains("AGENTS.md", "loops/SKILL_REVIEW.md")
    contains("skills/ask-kh/SKILL.md", "Instruction-document changes")
    contains("skills/ask-kh/SKILL.md", "loops/SKILL_REVIEW.md")
    contains("loops/SKILL_REVIEW.md", "Capability Tiering & Model Routing")


def check_delegation() -> None:
    heavy_loops = [
        "loops/REVIEW_DOCUMENT.md",
        "loops/PLAN.md",
        "loops/IMPLEMENT_MILESTONE.md",
        "loops/CODE_REVIEW_TRIBUNAL.md",
        "loops/ARCHITECTURE_DESIGN.md",
        "loops/SKILL_REVIEW.md",
    ]
    for path in heavy_loops:
        text = read(path)
        require("delegat" in text.lower() or "subagent" in text.lower(), f"{path} lacks delegation wording")
        require("verdict" in text.lower(), f"{path} lacks verdict wording")
    contains("loops/REVIEW_DOCUMENT.md", "verdict: CONVERGED | OPEN_QUESTIONS | MAX_ROUNDS | BLOCKED")
    contains("loops/REVIEW_DOCUMENT.md", "Never return reviewer transcripts or raw round output")


def check_install() -> None:
    contains("skills/install-killhouse/SKILL.md", "claude plugin validate .")
    contains("skills/install-killhouse/SKILL.md", "codex plugin marketplace add .")
    contains("skills/install-killhouse/SKILL.md", "codex plugin add killhouse@")
    contains("README.md", "codex plugin marketplace add .")
    not_contains("README.md", "instruct you to begin with")
    not_contains("README.md", "no clone needed")


def check_mandatory_gates() -> None:
    contains("AGENTS.md", "Mandatory gates always stop")
    contains("skills/ask-kh/SKILL.md", "Mandatory gates (never skipped")
    contains("skills/ask-kh/SKILL.md", "Autopilot skips *courtesy* checkpoints")
    contains("loops/PLAN.md", "Tracer bullet first")


def check_docs_sync() -> None:
    contains("README.md", "/triage")
    contains("README.md", "Ponytail reviewer")
    contains("skills/to-prd/SKILL.md", "Do not check with the user during this skill")
    contains("skills/to-prd/SKILL.md", "Do not publish it to an issue tracker")
    not_contains("skills/to-prd/SKILL.md", "publish it to the project issue tracker")
    not_contains("skills/to-prd/SKILL.md", "Apply the `ready-for-agent` triage label")


def check_redqueen() -> None:
    contains("AGENTS.md", "optional and self-degrading")
    contains("skills/ask-kh/SKILL.md", "degrades to a plain implementer prompt")
    contains("bin/evolve_exec_prompt.py", "Exit codes: 0 ok; 2 redqueen run/extract failed; 3 no usable champion")


CHECKS = {
    "manifests": check_manifests,
    "runtime-contracts": check_runtime_contracts,
    "instruction-review": check_instruction_review,
    "delegation": check_delegation,
    "install": check_install,
    "mandatory-gates": check_mandatory_gates,
    "docs-sync": check_docs_sync,
    "redqueen": check_redqueen,
}


def run_check(name: str) -> None:
    CHECKS[name]()
    print(f"[ok] {name}")


def run_command(command: list[str]) -> None:
    proc = subprocess.run(command, cwd=ROOT)
    if proc.returncode != 0:
        raise CheckFailure(f"command failed: {' '.join(command)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Killhouse self-hosting contracts.")
    parser.add_argument("--check", default="all", choices=["all", *CHECKS.keys()])
    parser.add_argument("--with-claude", action="store_true", help="also run claude plugin validate .")
    args = parser.parse_args()

    try:
        run_command(["git", "diff", "--check"])
        if args.check == "all":
            for name in CHECKS:
                run_check(name)
        else:
            run_check(args.check)
        if args.with_claude:
            run_command(["claude", "plugin", "validate", "."])
    except CheckFailure as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
