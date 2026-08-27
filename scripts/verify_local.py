#!/usr/bin/env python3
"""Run the BASE verification suite without reading ignored local secrets."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, cwd: Path = ROOT) -> int:
    display_command = ["python", *command[1:]] if command[0] == sys.executable else command
    print(f"> {' '.join(display_command)}", flush=True)
    executable_command = command
    if os.name == "nt" and command[0].lower().endswith("gradlew.bat"):
        executable_command = [str(cwd / command[0]), *command[1:]]
    try:
        return subprocess.run(executable_command, cwd=cwd, check=False).returncode
    except FileNotFoundError:
        print(f"required executable not found: {command[0]}")
        return 127


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="skip Web, Android, and Compose")
    args = parser.parse_args()

    if os.name == "nt" and not os.environ.get("ANDROID_HOME"):
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            standard_sdk = Path(local_app_data) / "Android" / "Sdk"
            if standard_sdk.is_dir():
                # Process-local only; never write local.properties or print the machine path.
                os.environ["ANDROID_HOME"] = str(standard_sdk)

    python = sys.executable
    checks: list[tuple[list[str], Path]] = [
        ([python, "scripts/verify_versions.py"], ROOT),
        ([python, "scripts/check_ci_policy.py"], ROOT),
        ([python, "scripts/export_openapi.py", "--check"], ROOT),
        ([python, "scripts/generate_contracts.py", "--check"], ROOT),
        ([python, "scripts/generate_agent_artifacts.py", "--check"], ROOT),
        ([python, "scripts/generate_competition_eval.py", "--check"], ROOT),
        ([python, "scripts/validate_evaluation_suite.py"], ROOT),
        ([python, "scripts/run_evaluation_baseline.py", "--check"], ROOT),
        ([python, "scripts/run_evaluation_ablations.py", "--check"], ROOT),
        ([python, "scripts/summarize_human_review.py", "--check"], ROOT),
        ([python, "scripts/generate_sbom.py", "--check"], ROOT),
        ([python, "scripts/security_gate.py", "--check"], ROOT),
        ([python, "scripts/run_security_tabletop.py", "--check"], ROOT),
        ([python, "scripts/validate_task_packages.py"], ROOT),
        ([python, "-m", "ruff", "check", "apps", "packages", "scripts"], ROOT),
        ([python, "-m", "ruff", "format", "--check", "apps", "packages", "scripts"], ROOT),
        ([python, "-m", "pytest", "-q"], ROOT),
    ]
    if not args.quick:
        npm = "npm.cmd" if os.name == "nt" else "npm"
        gradle = "gradlew.bat" if os.name == "nt" else "./gradlew"
        checks.extend(
            [
                ([npm, "run", "check"], ROOT),
                ([npm, "run", "test"], ROOT),
                ([npm, "run", "build"], ROOT),
                (
                    [
                        gradle,
                        ":app:compileDebugKotlin",
                        ":app:testDebugUnitTest",
                        ":app:lintDebug",
                        ":app:assembleBenchmark",
                        "-PapiUrl=https://ci.invalid",
                    ],
                    ROOT / "apps/android",
                ),
                (["docker", "compose", "-f", "infra/compose.yaml", "config", "--quiet"], ROOT),
            ]
        )

    failures = 0
    for command, cwd in checks:
        code = run(command, cwd=cwd)
        if code:
            failures += 1
            print(f"FAIL exit={code}: {command[0]}")
    if failures:
        print(f"verification failed: {failures}/{len(checks)} commands")
        return 1
    print(f"verification passed: {len(checks)} commands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
