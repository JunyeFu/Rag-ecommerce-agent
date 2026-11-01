#!/usr/bin/env python3
"""Validate the fully automated competition-v2 evaluation suite."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evals" / "v2"
EXPECTED_FAMILIES = {
    "retrieval_exact": 120,
    "retrieval_semantic": 120,
    "constraint_conflict": 100,
    "no_match": 80,
    "multi_turn": 120,
    "approval_state": 100,
    "quote_evidence": 100,
    "multimodal": 80,
    "recovery_concurrency": 80,
    "security": 100,
}
EXPECTED_SPLITS = {"dev": 600, "test": 250, "challenge": 150}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_jsonl(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    values = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}:{line_number}: invalid JSON: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"{path.name}:{line_number}: record is not an object")
            continue
        values.append(value)
    return values


def main() -> int:
    errors: list[str] = []
    manifest = json.loads((EVAL / "manifest.json").read_text(encoding="utf-8"))
    for relative, record in manifest["files"].items():
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"missing manifest file: {relative}")
        elif sha256(path) != record["sha256"]:
            errors.append(f"hash drift: {relative}")

    cases = load_jsonl(EVAL / "cases.v2.jsonl", errors)
    ids = [item.get("case_id") for item in cases]
    queries = [item.get("query_sha256") for item in cases]
    if len(cases) != 1000:
        errors.append(f"case count must be 1000: {len(cases)}")
    if len(ids) != len(set(ids)):
        errors.append("duplicate case ids")
    if len(queries) != len(set(queries)):
        errors.append("duplicate query fingerprints")
    family_counts = Counter(item.get("family") for item in cases)
    split_counts = Counter(item.get("split") for item in cases)
    if family_counts != Counter(EXPECTED_FAMILIES):
        errors.append(f"unexpected family counts: {dict(family_counts)}")
    if split_counts != Counter(EXPECTED_SPLITS):
        errors.append(f"unexpected split counts: {dict(split_counts)}")

    required = {
        "schema_version",
        "case_id",
        "family",
        "split",
        "turns",
        "media",
        "injected_faults",
        "risk_tags",
        "query_sha256",
        "expected",
        "provenance",
    }
    for item in cases:
        case_id = item.get("case_id")
        if not required <= set(item) or item.get("schema_version") != 2:
            errors.append(f"case schema incomplete: {case_id}")
            continue
        expected = item["expected"]
        if not set(expected["required_tools"]) <= set(expected["allowed_tools"]):
            errors.append(f"required tool not allowed: {case_id}")
        if set(expected["allowed_tools"]) & set(expected["forbidden_tools"]):
            errors.append(f"allowed and forbidden tools overlap: {case_id}")
        provenance = item["provenance"]
        if (
            provenance.get("gold_status") != "machine_rule_frozen"
            or provenance.get("license_status") != "project_generated"
        ):
            errors.append(f"non-automated or unclear provenance: {case_id}")

    retired = [
        EVAL / "public-cases.v1.jsonl",
        EVAL / "heldout" / "review-queue.v1.jsonl",
        EVAL / "heldout" / "human-review-status.json",
    ]
    for path in retired:
        if path.exists():
            errors.append(
                f"retired human-evaluation artifact still exists: {path.relative_to(ROOT)}"
            )

    print(
        f"evaluation_cases={len(cases)} errors={len(errors)} splits={dict(sorted(split_counts.items()))} families={dict(sorted(family_counts.items()))}"
    )
    for error in errors:
        print("ERROR", error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
