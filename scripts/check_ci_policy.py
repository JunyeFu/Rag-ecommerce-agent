#!/usr/bin/env python3
"""Fail closed if the BASE CI starts reading local secrets or mutable installs."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ci.yml"
FORBIDDEN = (
    ".env",
    "local.properties",
    "printenv",
    "set -x",
    "${{ secrets.",
    "pip install uv ",
    "npm install",
)
REQUIRED = (
    "permissions:\n  contents: read",
    "uv==0.11.13",
    "uv sync --locked",
    "npm ci",
    "scripts/generate_contracts.py --check",
    "scripts/generate_agent_artifacts.py --check",
    "scripts/generate_competition_eval.py --check",
    "scripts/validate_evaluation_suite.py",
    "scripts/run_evaluation_baseline.py --check",
    "scripts/run_evaluation_ablations.py --check",
    "scripts/summarize_human_review.py --check",
    "scripts/generate_sbom.py --check",
    "scripts/security_gate.py --check",
    "scripts/run_security_tabletop.py --check",
    "scripts/validate_task_packages.py",
    "gradle-wrapper.jar",
    "docker compose -f infra/compose.yaml config --quiet",
)


def main() -> int:
    text = WORKFLOW.read_text(encoding="utf-8")
    forbidden_hits = [value for value in FORBIDDEN if value.lower() in text.lower()]
    missing = [value for value in REQUIRED if value not in text]
    if forbidden_hits:
        print("CI policy violation: forbidden local or mutable input reference")
        return 1
    if missing:
        print(f"CI policy violation: {len(missing)} required gates missing")
        return 1
    print(f"CI policy passed: {len(REQUIRED)} required gates, 0 forbidden inputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
