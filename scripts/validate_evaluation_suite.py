#!/usr/bin/env python3
"""Validate evaluation counts, hashes, split isolation and blinded held-out structure."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evals" / "v2"
MINIMUMS = {
    "shopping": 300,
    "multi_turn": 100,
    "multimodal": 80,
    "quote_failure": 60,
    "security": 60,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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

    public = load_jsonl(EVAL / "public-cases.v1.jsonl", errors)
    heldout = load_jsonl(EVAL / "heldout" / "review-queue.v1.jsonl", errors)
    cases = public + heldout
    ids = [item.get("case_id") for item in cases]
    queries = [item.get("query_sha256") for item in cases]
    if len(cases) < 600:
        errors.append(f"case count below 600: {len(cases)}")
    if len(ids) != len(set(ids)):
        errors.append("duplicate case ids")
    if len(queries) != len(set(queries)):
        errors.append("duplicate query fingerprints")
    family_counts = Counter(item.get("family") for item in cases)
    for family, minimum in MINIMUMS.items():
        if family_counts[family] < minimum:
            errors.append(f"{family} below minimum {minimum}: {family_counts[family]}")
    split_counts = Counter(item.get("split") for item in cases)
    if split_counts != Counter({"dev": 360, "test": 140, "heldout": 100}):
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
        "provenance",
    }
    for item in public:
        if not required <= set(item) or "expected" not in item:
            errors.append(f"public case schema incomplete: {item.get('case_id')}")
        if item.get("split") == "heldout":
            errors.append(f"heldout case leaked into public data: {item.get('case_id')}")
        if item.get("provenance", {}).get("license_status") != "project_generated":
            errors.append(f"non-clear public license: {item.get('case_id')}")
    for item in heldout:
        if not required <= set(item) or "expected" in item:
            errors.append(f"heldout blinding violated: {item.get('case_id')}")
        if item.get("split") != "heldout" or not item.get("blind_token"):
            errors.append(f"invalid heldout record: {item.get('case_id')}")

    result_files = list((EVAL / "results").glob("*.json")) if (EVAL / "results").exists() else []
    heldout_ids = {str(item["case_id"]) for item in heldout}
    for path in result_files:
        text = path.read_text(encoding="utf-8")
        leaked = sorted(case_id for case_id in heldout_ids if case_id in text)
        if leaked:
            errors.append(f"heldout ids leaked into {path.name}: {len(leaked)}")

    print(
        "evaluation_cases="
        f"{len(cases)} public={len(public)} heldout={len(heldout)} "
        f"errors={len(errors)} families={dict(sorted(family_counts.items()))}"
    )
    for error in errors:
        print("ERROR", error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
