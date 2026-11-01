"""Thirty real process-cold launches on the owned QA AVD; no business input."""

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def measure(adb, serial, port):
    package = "com.ragcommerce.agent.safetytest"

    def command(*args):
        return subprocess.check_output(
            [str(adb), "-P", str(port), "-s", serial, *args], text=True, encoding="utf-8"
        ).strip()

    avd = command("shell", "getprop", "ro.boot.qemu.avd_name")
    if avd != "RagFinalSafety20261012":
        raise ValueError("Only the owned RagFinalSafety20261012 AVD is in scope")
    identity = command("shell", "pm", "list", "packages", "-U", package)
    uid = int(re.search(rf"^package:{re.escape(package)} uid:(\d+)$", identity, re.MULTILINE)[1])
    apk = command("shell", "pm", "path", package).removeprefix("package:")
    apk_sha256 = command("shell", "sha256sum", apk).split()[0]
    compilation = re.search(
        r"\[status=([^\]]+)\]", command("shell", "dumpsys", "package", package)
    )[1]
    start_epoch = int(command("shell", "date", "+%s"))
    samples = []
    for index in range(30):
        receipt = command(
            "shell",
            "am",
            "start",
            "-S",
            "-W",
            "-n",
            f"{package}/com.ragcommerce.agent.MainActivity",
        )
        values = dict(re.findall(r"^([A-Za-z]+):\s*(.*)$", receipt, re.MULTILINE))
        if values.get("Status") != "ok" or values.get("LaunchState") != "COLD":
            raise ValueError(f"Launch {index + 1} was not an actual successful cold start")
        samples.append(
            {
                "launch": index + 1,
                "total_time_ms": int(values["TotalTime"]),
                "wait_time_ms": int(values["WaitTime"]),
            }
        )
        print(f"cold_launch={index + 1} total_ms={values['TotalTime']}", flush=True)
    logs = command("logcat", "-d", "-v", "epoch", f"--uid={uid}")
    lines = [
        line
        for line in logs.splitlines()
        if re.match(r"^\s*\d+\.\d+", line) and float(line.split()[0]) >= start_epoch
    ]
    fatal = sum("FATAL EXCEPTION" in line or "Fatal signal" in line for line in lines)
    strict = sum("StrictMode policy violation" in line for line in lines)
    p95 = sorted(row["total_time_ms"] for row in samples)[28]
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "avd": avd,
        "serial": serial,
        "package": package,
        "android_api": int(command("shell", "getprop", "ro.build.version.sdk")),
        "build": "installed debug QA APK",
        "installed_apk_sha256": apk_sha256,
        "compilation_state": compilation,
        "run_count": 30,
        "samples": samples,
        "cold_start_p95_ms": p95,
        "fatal_count": fatal,
        "strictmode_violation_count": strict,
        "app_uid_log_lines_checked": len(lines),
        "log_window_epoch": start_epoch,
        "passed_for_installed_binary": p95 < 2000 and fatal == 0 and strict == 0,
        "raw_logs_saved": False,
        "data_or_logs_cleared": False,
        "limitations": [
            "am start TotalTime measures initial display, not fully restored Agent readiness",
            "Process-cold with OS/disk caches retained; not device reboot",
            "Installed QA binary only; final same-source APK must be separately checked",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adb", required=True, type=Path)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb-server-port", type=int, default=20884)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Preserve existing results")
    report = measure(args.adb, args.serial, args.adb_server_port)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"cold_start_passed={report['passed_for_installed_binary']}")
    return 0 if report["passed_for_installed_binary"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
