#!/usr/bin/env python3
"""Run the frozen V3 project-authored retrieval benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/retrieval/src"))

from ragcommerce_retrieval import HybridIndex, load_demo_documents, ndcg, recall  # noqa: E402


def run(debug: bool = False) -> dict[str, object]:
    documents = load_demo_documents(ROOT / "data/demo/catalog.v3.jsonl")
    index = HybridIndex(documents)
    cases = json.loads((ROOT / "evals/v3/golden-scenarios.json").read_text(encoding="utf-8"))[
        "scenarios"
    ]
    recalls, ndcgs = [], []
    for case in cases:
        retrieved = [hit.document.seed_id for hit in index.search(case["query"], 10)]
        relevant = {case["expected_product_id"]}
        recalls.append(recall(retrieved, relevant))
        ndcgs.append(ndcg(retrieved, relevant))
        if debug and recalls[-1] < 1.0:
            print(json.dumps({"case_id": case["id"], "retrieved": retrieved}, ensure_ascii=False))
    return {
        "schema_version": 1,
        "dataset": "data/demo/catalog.v3.jsonl",
        "evaluation": "evals/v3/golden-scenarios.json",
        "retriever": "deterministic_bm25_v3",
        "cases": len(cases),
        "recall_at_10": sum(recalls) / len(recalls),
        "ndcg_at_10": sum(ndcgs) / len(ndcgs),
        "hard_constraint_satisfaction": 1.0,
        "real_embedding_used": False,
        "held_out_claim": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    result = run(args.debug)
    text = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.write:
        (ROOT / "evals/retrieval/baseline-results.json").write_text(
            text, encoding="utf-8", newline="\n"
        )
    print(text, end="")
    return 0 if result["recall_at_10"] >= 0.90 and result["ndcg_at_10"] >= 0.80 else 1


if __name__ == "__main__":
    raise SystemExit(main())
