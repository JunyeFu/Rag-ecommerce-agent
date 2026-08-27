#!/usr/bin/env python3
"""Run one Android instrumentation case and retain only a bounded result summary."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adb", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--app-apk", required=True, type=Path)
    parser.add_argument("--test-apk", required=True, type=Path)
    parser.add_argument("--test", required=True)
    parser.add_argument("--runner", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    for apk in (args.app_apk, args.test_apk):
        if not apk.is_file():
            raise FileNotFoundError(apk)
        installed = run([args.adb, "-s", args.serial, "install", "-r", str(apk)])
        if installed.returncode != 0 or "Success" not in installed.stdout:
            raise RuntimeError(f"failed to install instrumentation artifact: {apk.name}")

    completed = run(
        [
            args.adb,
            "-s",
            args.serial,
            "shell",
            "am",
            "instrument",
            "-w",
            "-r",
            "-e",
            "class",
            args.test,
            args.runner,
        ],
    )
    output = completed.stdout + "\n" + completed.stderr
    match = re.search(r"OK \((\d+) tests?\)", output)
    passed = (
        completed.returncode == 0 and match is not None and "INSTRUMENTATION_CODE: -1" in output
    )
    failure_summary = [
        line.strip()
        for line in output.splitlines()
        if any(marker in line for marker in ("FAILURES", "AssertionError", "Process crashed"))
    ][:5]
    evidence = {
        "schema_version": 1,
        "verified_at": datetime.now(UTC).isoformat(),
        "evidence_level": "android_emulator_fixture_integration",
        "command": "adb -s <serial> shell am instrument -w -r -e class <test> <runner>",
        "test": args.test,
        "tests": int(match.group(1)) if match else 0,
        "exit_code": completed.returncode,
        "passed": passed,
        "failure_summary": failure_summary,
        "log_policy": "Full instrumentation output and local absolute paths were not retained.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
