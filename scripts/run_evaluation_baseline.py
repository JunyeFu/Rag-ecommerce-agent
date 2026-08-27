#!/usr/bin/env python3
"""Run the public 500-case deterministic harness reference and preserve all denominators."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/evaluation/src"))

from ragcommerce_evaluation import (  # noqa: E402
    EvalCase,
    EvalResult,
    aggregate,
    grade_case,
    reference_result,
)

DATASET = ROOT / "evals/v2/public-cases.v1.jsonl"
RESULTS = ROOT / "evals/v2/results"
CASE_RESULTS = RESULTS / "deterministic-reference-cases.jsonl"
SUMMARY = RESULTS / "deterministic-reference-summary.json"
RUN_MANIFEST = RESULTS / "deterministic-reference-manifest.json"
RUN_ID = "eval-reference-competition-v1-20260826"


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"


def render() -> dict[Path, bytes]:
    raw_cases = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines()]
    cases = [EvalCase.from_dict(value) for value in raw_cases]
    results = [reference_result(case) for case in cases]
    grades = [grade_case(case, result) for case, result in zip(cases, results, strict=True)]
    by_family: dict[str, list[int]] = defaultdict(list)
    by_split: dict[str, list[int]] = defaultdict(list)
    for index, case in enumerate(cases):
        by_family[case.family].append(index)
        by_split[case.split].append(index)

    case_rows = [
        {
            "schema_version": 1,
            "run_id": RUN_ID,
            "case_id": case.case_id,
            "family": case.family,
            "split": case.split,
            "result_sha256": sha256(canonical(asdict(result))),
            "grade": grade.to_dict(),
            "latency_ms": result.latency_ms,
            "estimated_cost_microunits": result.estimated_cost_microunits,
        }
        for case, result, grade in zip(cases, results, grades, strict=True)
    ]
    case_bytes = b"".join(canonical(value) + b"\n" for value in case_rows)

    def subset(indices: list[int]) -> dict[str, object]:
        return aggregate(
            [grades[index] for index in indices], [results[index] for index in indices]
        )

    negative_case = cases[0]
    negative_result = EvalResult(
        case_id=negative_case.case_id,
        outcome="failed",
        tool_calls=("cart.update",),
        evidence_refs=(),
        commercial_facts=({"price_minor": 1},),
        approval_requested=False,
        deep_links=("http://blocked.invalid",),
        exposed_sensitive_fields=("credential",),
        latency_ms=999,
        estimated_cost_microunits=1,
        error="negative_control",
    )
    negative_grade = grade_case(negative_case, negative_result)
    summary = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "evidence_level": "deterministic_contract_reference_only",
        "dataset_version": "competition-v1-public",
        "dataset_sha256": sha256(DATASET.read_bytes()),
        "case_results_sha256": sha256(case_bytes),
        "overall": aggregate(grades, results),
        "by_family": {name: subset(indices) for name, indices in sorted(by_family.items())},
        "by_split": {name: subset(indices) for name, indices in sorted(by_split.items())},
        "negative_control": negative_grade.to_dict(),
        "heldout_cases_consumed": 0,
        "real_provider_calls": 0,
        "claims": {
            "grader_and_denominator_contract_validated": True,
            "model_quality_measured": False,
            "live_commercial_quality_measured": False,
            "human_quality_measured": False,
        },
    }
    summary_bytes = json_bytes(summary)
    manifest = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "command": "uv run python scripts/run_evaluation_baseline.py --check",
        "dataset_version": "competition-v1",
        "dataset_sha256": sha256(DATASET.read_bytes()),
        "runner_version": "deterministic-reference-v1",
        "grader_version": "policy-grounding-grader-v1",
        "model_version": "none-reference-constructor",
        "prompt_version": "none",
        "policy_version": "agent-policy-v1",
        "contract_version": "0.1.0",
        "seed": 20260826,
        "splits_consumed": ["dev", "test"],
        "heldout_consumed": False,
        "artifacts": {
            "evals/v2/results/deterministic-reference-cases.jsonl": sha256(case_bytes),
            "evals/v2/results/deterministic-reference-summary.json": sha256(summary_bytes),
        },
        "replay_environment": ["Python 3.12.11", "uv.lock", "pyproject.toml"],
    }
    return {
        CASE_RESULTS: case_bytes,
        SUMMARY: summary_bytes,
        RUN_MANIFEST: json_bytes(manifest),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write == args.check:
        parser.error("choose exactly one of --write or --check")
    outputs = render()
    drift: list[str] = []
    for path, content in outputs.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != content:
                drift.append(path.relative_to(ROOT).as_posix())
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            print(f"generated {path.relative_to(ROOT).as_posix()}")
    if drift:
        for value in drift:
            print("DRIFT", value)
        return 1
    if args.check:
        print("reference_eval=deterministic public_cases=500 heldout_consumed=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
