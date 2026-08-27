#!/usr/bin/env python3
"""Validate two blinded held-out reviews and create an immutable summary input."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/evaluation/src"))

from ragcommerce_evaluation import cohen_kappa  # noqa: E402

ALLOWED_LABELS = {"PASS", "FAIL", "UNSURE"}
PENDING_STATUS = ROOT / "evals/v2/heldout/human-review-status.json"


def load(path: Path) -> tuple[str, dict[str, dict[str, str]]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    identities = {str(item.get("reviewer_ref", "")) for item in rows}
    if len(rows) != 100 or len(identities) != 1 or not next(iter(identities)):
        raise ValueError(f"{path.name}: exactly 100 rows from one pseudonymous reviewer required")
    values: dict[str, dict[str, str]] = {}
    for item in rows:
        token = str(item.get("blind_token", ""))
        label = str(item.get("label", ""))
        if token in values or label not in ALLOWED_LABELS:
            raise ValueError(f"{path.name}: duplicate token or invalid label")
        if label != "PASS" and not str(item.get("reason", "")).strip():
            raise ValueError(f"{path.name}: FAIL/UNSURE requires a reason")
        values[token] = {"label": label, "reason": str(item.get("reason", ""))}
    return identities.pop(), values


def summarize(path_a: Path, path_b: Path) -> dict[str, object]:
    reviewer_a, values_a = load(path_a)
    reviewer_b, values_b = load(path_b)
    if reviewer_a == reviewer_b:
        raise ValueError("reviewers must be distinct")
    if set(values_a) != set(values_b):
        raise ValueError("review token sets do not match")
    tokens = sorted(values_a)
    labels_a = [values_a[token]["label"] for token in tokens]
    labels_b = [values_b[token]["label"] for token in tokens]
    disagreements = [
        token for token in tokens if values_a[token]["label"] != values_b[token]["label"]
    ]
    return {
        "schema_version": 1,
        "status": "PENDING_ADJUDICATION" if disagreements else "DUAL_REVIEW_COMPLETE",
        "reviewer_refs": [reviewer_a, reviewer_b],
        "reviewed_cases": len(tokens),
        "raw_agreement": 1 - len(disagreements) / len(tokens),
        "cohen_kappa": cohen_kappa(labels_a, labels_b),
        "label_counts_a": dict(Counter(labels_a)),
        "label_counts_b": dict(Counter(labels_b)),
        "disagreement_tokens": disagreements,
        "adjudication_complete": False,
        "notes": ["Original reviewer labels remain in the source files and are not overwritten."],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewer-a", type=Path)
    parser.add_argument("--reviewer-b", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        status = json.loads(PENDING_STATUS.read_text(encoding="utf-8"))
        queue = ROOT / "evals/v2/heldout/review-queue.v1.jsonl"
        queue_size = len(queue.read_text(encoding="utf-8").splitlines())
        pending = (
            status["status"] == "BLOCKED_PENDING_DUAL_HUMAN_REVIEW"
            and status["heldout_cases"] == queue_size == 100
            and status["reviewed_by_reviewer_a"] == 0
            and status["reviewed_by_reviewer_b"] == 0
            and status["adjudicated"] == 0
            and status["cohen_kappa"] is None
        )
        print(f"heldout={queue_size} dual_reviewed=0 adjudicated=0 pending={str(pending).lower()}")
        return 0 if pending else 1
    if args.reviewer_a is None or args.reviewer_b is None or args.output is None:
        parser.error("--reviewer-a, --reviewer-b and --output are required unless --check is used")
    result = summarize(args.reviewer_a, args.reviewer_b)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"reviewed={result['reviewed_cases']} kappa={result['cohen_kappa']:.6f} "
        f"status={result['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
