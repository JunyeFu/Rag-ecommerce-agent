#!/usr/bin/env python3
"""Run reproducible ablations on the project-authored V3 demo catalog."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/retrieval/src"))

from ragcommerce_retrieval import HybridIndex, load_demo_documents, ndcg, recall  # noqa: E402
from ragcommerce_retrieval.search import SearchDocument, tokenize  # noqa: E402

OUTPUT = ROOT / "evals/v3/ablation-report.json"


def vector_rank(documents: tuple[SearchDocument, ...], query: str) -> list[str]:
    query_terms = set(tokenize(query))
    scored = []
    for document in documents:
        terms = set(tokenize(document.searchable_text))
        union = query_terms | terms
        score = len(query_terms & terms) / len(union) if union else 0.0
        scored.append((score, document.seed_id))
    return [seed_id for _, seed_id in sorted(scored, key=lambda item: (-item[0], item[1]))[:10]]


def reciprocal_rank_fusion(*rankings: list[str]) -> list[str]:
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for index, value in enumerate(ranking, 1):
            scores[value] += 1 / (60 + index)
    return [value for value, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:10]]


def evaluate(cases: list[dict[str, object]], search) -> dict[str, object]:
    recalls, ndcgs = [], []
    for case in cases:
        relevant = {str(case["expected_product_id"])}
        ranked = search(case)
        recalls.append(recall(ranked, relevant))
        ndcgs.append(ndcg(ranked, relevant))
    return {"cases": len(cases), "recall_at_10": mean(recalls), "ndcg_at_10": mean(ndcgs)}


def render() -> bytes:
    documents = load_demo_documents(ROOT / "data/demo/catalog.v3.jsonl")
    cases = json.loads((ROOT / "evals/v3/golden-scenarios.json").read_text(encoding="utf-8"))[
        "scenarios"
    ]
    lexical = HybridIndex(documents)

    def bm25(case):
        return [hit.document.seed_id for hit in lexical.search(str(case["query"]), 10)]

    def vectors(case):
        return vector_rank(documents, str(case["query"]))

    variants = {
        "bm25": evaluate(cases, bm25),
        "deterministic_vector": evaluate(cases, vectors),
        "rrf_hybrid": evaluate(
            cases, lambda case: reciprocal_rank_fusion(bm25(case), vectors(case))
        ),
    }
    for value in variants.values():
        value["recall_target_met"] = value["recall_at_10"] >= 0.90
        value["ndcg_target_met"] = value["ndcg_at_10"] >= 0.80
    report = {
        "schema_version": 1,
        "evidence_level": "project_authored_demo_ablation",
        "dataset": "data/demo/catalog.v3.jsonl",
        "evaluation": "evals/v3/golden-scenarios.json",
        "variants": variants,
        "heldout_consumed": False,
        "real_provider_calls": 0,
        "numeric_guard": {
            "all_metrics_finite": all(
                math.isfinite(float(metric))
                for variant in variants.values()
                for key, metric in variant.items()
                if key in {"recall_at_10", "ndcg_at_10"}
            )
        },
        "limitations": [
            "Deterministic vectors are a CI fixture, not real-provider evidence.",
            "The ten golden scenarios are public and not a held-out human evaluation.",
        ],
    }
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write == args.check:
        parser.error("choose exactly one of --write or --check")
    expected = render()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_bytes() != expected:
            print("DRIFT evals/v3/ablation-report.json")
            return 1
        print("ablation=deterministic variants=3 cases=10")
        return 0
    OUTPUT.write_bytes(expected)
    print("generated evals/v3/ablation-report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
