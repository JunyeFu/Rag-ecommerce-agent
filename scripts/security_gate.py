#!/usr/bin/env python3
"""Run deterministic local security controls and fail closed on external scan gaps."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/security/evidence/security-gate.json"
EXCLUDED = {".git", ".venv", "node_modules", ".gradle", "build", "dist", ".playwright-cli"}
TEXT_SUFFIXES = {".py", ".kt", ".kts", ".ts", ".tsx", ".js", ".json", ".yaml", ".yml", ".toml"}
PLACEHOLDERS = {"example", "placeholder", "changeme", "not-a-live-secret", "localdev", "none"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and path.suffix.lower() in TEXT_SUFFIXES
        and not EXCLUDED.intersection(path.relative_to(ROOT).parts)
        and "docs/security/evidence" not in path.relative_to(ROOT).as_posix()
    ]


def secret_findings(paths: list[Path]) -> list[str]:
    assignment = re.compile(
        r"(?i)\b(?:api[_-]?key|client[_-]?secret|access[_-]?token|password)\b\s*[:=]\s*[\"']?([^\"'\s,}]{8,})"
    )
    direct = re.compile(r"(?:-----BEGIN (?:RSA |EC )?PRIVATE KEY-----|\bsk-[A-Za-z0-9]{20,})")
    findings = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        if direct.search(text):
            findings.append(path.relative_to(ROOT).as_posix())
            continue
        for match in assignment.finditer(text):
            value = match.group(1).lower()
            if not any(marker in value for marker in PLACEHOLDERS) and not value.startswith(
                ("${", "<")
            ):
                findings.append(path.relative_to(ROOT).as_posix())
                break
    return sorted(set(findings))


def sast_findings(paths: list[Path]) -> list[str]:
    patterns = {
        "dynamic_eval": re.compile(r"(?m)(?<![.A-Za-z])(?:eval|exec)\s*\("),
        "shell_true": re.compile(r"shell\s*=\s*True"),
        "unsafe_pickle": re.compile(r"pickle\.loads?\s*\("),
        "tls_disabled": re.compile(r"verify\s*=\s*False"),
        "dangerous_html": re.compile(r"dangerouslySetInnerHTML"),
    }
    findings = []
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        if not relative.startswith(("apps/", "packages/", "scripts/")):
            continue
        if relative == "scripts/security_gate.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for name, pattern in patterns.items():
            if pattern.search(text):
                findings.append(f"{name}:{relative}")
    return sorted(findings)


def render() -> tuple[str, bool]:
    paths = source_files()
    secrets = secret_findings(paths)
    sast = sast_findings(paths)
    required_docs = [
        "docs/security/threat-model.md",
        "docs/security/retention-and-erasure.md",
        "docs/security/incident-response.md",
        "docs/security/connector-revocation.md",
        "docs/security/security-gates.md",
    ]
    missing_docs = [value for value in required_docs if not (ROOT / value).is_file()]
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    ignore_missing = [
        value
        for value in (".env", "local.properties", "*.jks", "*.keystore")
        if value not in ignored
    ]
    registry = json.loads(
        (ROOT / "packages/contracts/agent/tool-registry.json").read_text(encoding="utf-8")
    )
    registry_text = json.dumps(registry).lower()
    forbidden_tools = [
        name for name in ("payment", "refund", "order.create") if name in registry_text
    ]
    local_issues = secrets + sast + missing_docs + ignore_missing + forbidden_tools
    report = {
        "schema_version": 1,
        "status": "passed_local_controls_external_scans_fail_closed"
        if not local_issues
        else "failed",
        "local_gate_passed": not local_issues,
        "commercial_release_eligible": False,
        "checks": {
            "secret_scan": {"status": "passed" if not secrets else "failed", "findings": secrets},
            "sast_patterns": {"status": "passed" if not sast else "failed", "findings": sast},
            "required_security_docs": {
                "status": "passed" if not missing_docs else "failed",
                "missing": missing_docs,
            },
            "sensitive_ignore_policy": {
                "status": "passed" if not ignore_missing else "failed",
                "missing": ignore_missing,
            },
            "transaction_tool_exclusion": {
                "status": "passed" if not forbidden_tools else "failed",
                "findings": forbidden_tools,
            },
            "locked_inputs": {
                "status": "passed",
                "uv_lock_sha256": digest(ROOT / "uv.lock"),
                "npm_lock_sha256": digest(ROOT / "package-lock.json"),
                "gradle_wrapper_sha256": digest(
                    ROOT / "apps/android/gradle/wrapper/gradle-wrapper.jar"
                ),
            },
        },
        "external_fail_closed": {
            "dependency_advisory_scan": "BLOCKED_NO_FROZEN_ADVISORY_DB_OR_EXECUTED_CI_SCAN",
            "container_scan": "BLOCKED_NO_RELEASE_IMAGE_OR_EXECUTED_SCANNER_REPORT",
            "independent_penetration_test": "BLOCKED_EXTERNAL_AUTHORIZATION_REQUIRED",
            "credential_rotation": "BLOCKED_NO_LIVE_CREDENTIAL_AUTHORITY",
            "license_legal_review": "BLOCKED_NOASSERTION_ENTRIES_REQUIRE_REVIEW",
        },
        "evidence_boundary": "Local deterministic controls passed does not imply penetration, vulnerability, legal, credential, or release approval.",
    }
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", not local_issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected, passed = render()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != expected:
            print("DRIFT docs/security/evidence/security-gate.json")
            return 1
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(expected, encoding="utf-8", newline="\n")
    report = json.loads(expected)
    print(
        f"security_local={str(passed).lower()} "
        f"secret_findings={len(report['checks']['secret_scan']['findings'])} "
        f"sast_findings={len(report['checks']['sast_patterns']['findings'])} "
        "external_scans=fail_closed"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
