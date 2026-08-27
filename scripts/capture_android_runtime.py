#!/usr/bin/env python3
"""Capture a secret-free Android emulator runtime summary for a task package."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path


def adb(adb_path: str, serial: str, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        [adb_path, "-s", serial, *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and completed.returncode != 0:
        raise RuntimeError(f"adb command failed ({completed.returncode}): {' '.join(args)}")
    return completed.stdout.strip()


def parse_launch(output: str) -> dict[str, object]:
    values: dict[str, object] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        if key in {"TotalTime", "WaitTime"} and value.isdigit():
            values[f"{key.lower()}_ms"] = int(value)
        elif key in {"Status", "LaunchState", "Activity"}:
            values[key.lower()] = value
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adb", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--activity", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    devices = subprocess.run(
        [args.adb, "devices"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    if not re.search(rf"^{re.escape(args.serial)}\s+device$", devices, re.MULTILINE):
        raise RuntimeError(f"requested device is not available: {args.serial}")

    adb(args.adb, args.serial, "logcat", "-c")
    adb(args.adb, args.serial, "shell", "am", "force-stop", args.package)
    launch_output = adb(
        args.adb,
        args.serial,
        "shell",
        "am",
        "start",
        "-W",
        "-n",
        f"{args.package}/{args.activity}",
    )
    time.sleep(3)
    pid = adb(args.adb, args.serial, "shell", "pidof", args.package, check=False).strip()
    log_args = ["logcat", "-d", "-v", "brief", "AndroidRuntime:E", "StrictMode:V", "*:S"]
    if pid.isdigit():
        log_args[1:1] = ["--pid", pid]
    error_log = adb(args.adb, args.serial, *log_args, check=False)
    fatal_markers = [
        line.strip()
        for line in error_log.splitlines()
        if "FATAL EXCEPTION" in line or ("AndroidRuntime" in line and "Process:" in line)
    ]
    strict_mode_markers = [
        line.strip() for line in error_log.splitlines() if "StrictMode policy violation" in line
    ]

    evidence = {
        "schema_version": 1,
        "verified_at": datetime.now(UTC).isoformat(),
        "command": "adb -s <serial> shell am start -W -n <package>/<activity>",
        "device": {
            "kind": "emulator" if args.serial.startswith("emulator-") else "physical",
            "model": adb(args.adb, args.serial, "shell", "getprop", "ro.product.model"),
            "sdk": int(adb(args.adb, args.serial, "shell", "getprop", "ro.build.version.sdk")),
            "resolution": adb(args.adb, args.serial, "shell", "wm", "size").removeprefix(
                "Physical size: "
            ),
        },
        "launch": parse_launch(launch_output),
        "process_running": bool(pid),
        "fatal_exception_count": len(fatal_markers),
        "strict_mode_violation_count": len(strict_mode_markers),
        "failure_summary": (fatal_markers + strict_mode_markers)[:5],
        "log_policy": "Only fatal and StrictMode violation markers were retained; full logcat and local paths were not stored.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return (
        0
        if not fatal_markers
        and not strict_mode_markers
        and evidence["launch"].get("status") == "ok"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
