#!/usr/bin/env python3
"""Verify repository-owned toolchain locks without printing environment values."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = json.loads((ROOT / "toolchain.versions.json").read_text(encoding="utf-8"))


def output(command: list[str]) -> str:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    if completed.returncode:
        raise RuntimeError(f"tool unavailable or failed: {command[0]}")
    return (completed.stdout or completed.stderr).strip()


def assert_prefix(label: str, actual: str, expected: str) -> None:
    if not actual.startswith(expected):
        raise AssertionError(f"{label}: expected {expected}, got {actual}")
    print(f"PASS {label} {expected}")


def main() -> int:
    expected_python = VERSIONS["python"]
    actual_python = ".".join(str(item) for item in sys.version_info[:3])
    assert_prefix("python", actual_python, expected_python)
    assert_prefix("uv", output(["uv", "--version"]), f"uv {VERSIONS['uv']}")
    assert_prefix("node", output(["node", "--version"]), f"v{VERSIONS['node']}")
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    assert_prefix("npm", output([npm, "--version"]), VERSIONS["npm"])

    java_text = output(["java", "-version"])
    java_match = re.search(r'version "([0-9]+)', java_text)
    if java_match is None or java_match.group(1) != VERSIONS["java"]:
        raise AssertionError("java major version does not match toolchain lock")
    print(f"PASS java {VERSIONS['java']}")

    wrapper = ROOT / "apps/android/gradle/wrapper/gradle-wrapper.jar"
    wrapper_hash = hashlib.sha256(wrapper.read_bytes()).hexdigest()
    if wrapper_hash != VERSIONS["gradle_wrapper_sha256"]:
        raise AssertionError("Gradle wrapper JAR checksum mismatch")
    properties = (ROOT / "apps/android/gradle/wrapper/gradle-wrapper.properties").read_text(
        encoding="utf-8"
    )
    if (
        VERSIONS["gradle"] not in properties
        or VERSIONS["gradle_distribution_sha256"] not in properties
    ):
        raise AssertionError("Gradle distribution lock is incomplete")
    print(f"PASS gradle wrapper {VERSIONS['gradle']}")

    compose = (ROOT / "infra/compose.yaml").read_text(encoding="utf-8")
    for name, image in VERSIONS["containers"].items():
        if image not in compose:
            raise AssertionError(f"container lock missing from Compose: {name}")
    print(f"PASS container tags {len(VERSIONS['containers'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
