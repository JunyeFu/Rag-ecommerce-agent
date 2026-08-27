#!/usr/bin/env python3
"""Run the frozen development-seed retrieval benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ragcommerce_retrieval import HybridIndex, load_seed_documents, ndcg, recall

ROOT = Path(__file__).resolve().parents[2]


def run(debug: bool = False) -> dict[str, object]:
    documents = load_seed_documents(ROOT / "data/seed/catalog.v1.jsonl")
    index = HybridIndex(documents)
    package = json.loads((ROOT / "evals/seed/evaluation.v1.json").read_text(encoding="utf-8"))
    recalls, ndcgs, constraint_scores = [], [], []
    excluded_context_cases = 0
    excluded_non_retrieval_cases = 0
    for case in package["cases"]:
        if case["expected_slots"].get("requires_context"):
            excluded_context_cases += 1
            continue
        if not case["ground_truth_seed_ids"]:
            excluded_non_retrieval_cases += 1
            continue
        constraints = {
            key: value
            for key, value in case["expected_slots"].items()
            if key
            in {"category", "price_max", "brand_candidates", "exclude_brands", "exclude_terms"}
        }
        hits = index.search(case["query"], 10, constraints)
        retrieved = [hit.document.seed_id for hit in hits]
        relevant = set(case["ground_truth_seed_ids"])
        recalls.append(recall(retrieved, relevant))
        ndcgs.append(ndcg(retrieved, relevant))
        if debug and recalls[-1] < 1.0:
            print(
                json.dumps(
                    {
                        "case_id": case["case_id"],
                        "scenario": case["scenario"],
                        "query": case["query"],
                        "relevant": sorted(relevant),
                        "retrieved": retrieved,
                        "recall": recalls[-1],
                    },
                    ensure_ascii=False,
                )
            )
        if constraints:
            satisfied = sum(index._satisfies(hit.document, constraints) for hit in hits)
            constraint_scores.append(satisfied / len(hits) if hits else 0.0)
    return {
        "schema_version": 1,
        "dataset": "V2-DATA-01-SEED-v1",
        "retriever": "deterministic_bm25_structured_v1",
        "cases": len(recalls),
        "excluded_requires_context_cases": excluded_context_cases,
        "excluded_non_retrieval_cases": excluded_non_retrieval_cases,
        "recall_at_10": sum(recalls) / len(recalls),
        "ndcg_at_10": sum(ndcgs) / len(ndcgs),
        "hard_constraint_satisfaction": sum(constraint_scores) / len(constraint_scores),
        "production_embedding_used": False,
        "held_out_claim": False,
        "development_rank_prior_used": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    result = run(args.debug)
    text = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    output = ROOT / "evals/retrieval/baseline-results.json"
    if args.write:
        output.write_text(text, encoding="utf-8", newline="\n")
    print(text, end="")
    targets = (
        result["recall_at_10"] >= 0.90
        and result["ndcg_at_10"] >= 0.80
        and result["hard_constraint_satisfaction"] >= 0.90
    )
    return 0 if targets else 1


if __name__ == "__main__":
    raise SystemExit(main())
