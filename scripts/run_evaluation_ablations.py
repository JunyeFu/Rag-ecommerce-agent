#!/usr/bin/env python3
"""Run reproducible development-only retrieval ablations without provider claims."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/retrieval/src"))

from ragcommerce_retrieval import HybridIndex, load_seed_documents, ndcg, recall  # noqa: E402
from ragcommerce_retrieval.search import SearchDocument, tokenize  # noqa: E402

OUTPUT = ROOT / "evals/v2/results/ablation-report.json"


def constraints(case: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in case["expected_slots"].items()
        if key in {"category", "price_max", "brand_candidates", "exclude_brands", "exclude_terms"}
    }


def vector_rank(
    documents: tuple[SearchDocument, ...], query: str, values: dict[str, object]
) -> list[str]:
    query_terms = set(tokenize(query))
    scored = []
    for document in documents:
        if not HybridIndex._satisfies(document, values):
            continue
        terms = set(tokenize(document.searchable_text))
        union = query_terms | terms
        score = len(query_terms & terms) / len(union) if union else 0.0
        if score > 0 or values:
            scored.append((score, document.seed_id))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [seed_id for _, seed_id in scored[:10]]


def reciprocal_rank_fusion(*rankings: list[str]) -> list[str]:
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for index, value in enumerate(ranking):
            scores[value] += 1 / (60 + index + 1)
    return [value for value, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:10]]


def evaluate(
    cases: list[dict[str, object]],
    search: Callable[[dict[str, object]], list[str]],
) -> dict[str, object]:
    recalls: list[float] = []
    ndcgs: list[float] = []
    for case in cases:
        relevant = set(case["ground_truth_seed_ids"])
        ranked = search(case)
        recalls.append(recall(ranked, relevant))
        ndcgs.append(ndcg(ranked, relevant))
    return {
        "cases": len(cases),
        "recall_at_10": mean(recalls),
        "ndcg_at_10": mean(ndcgs),
    }


def render() -> bytes:
    documents = load_seed_documents(ROOT / "data/seed/catalog.v1.jsonl")
    no_prior_documents = tuple(replace(item, development_rank_prior=(0, 0)) for item in documents)
    prior_index = HybridIndex(documents)
    no_prior_index = HybridIndex(no_prior_documents)
    package = json.loads((ROOT / "evals/seed/evaluation.v1.json").read_text(encoding="utf-8"))
    cases = [
        item
        for item in package["cases"]
        if item["ground_truth_seed_ids"] and not item["expected_slots"].get("requires_context")
    ]

    def lexical(index: HybridIndex, case: dict[str, object]) -> list[str]:
        return [hit.document.seed_id for hit in index.search(case["query"], 10, constraints(case))]

    variants = {
        "bm25_structured_with_development_prior": evaluate(
            cases, lambda case: lexical(prior_index, case)
        ),
        "bm25_structured_without_development_prior": evaluate(
            cases, lambda case: lexical(no_prior_index, case)
        ),
        "sparse_token_vector_without_production_embedding": evaluate(
            cases,
            lambda case: vector_rank(documents, case["query"], constraints(case)),
        ),
        "rrf_lexical_sparse_vector": evaluate(
            cases,
            lambda case: reciprocal_rank_fusion(
                lexical(no_prior_index, case),
                vector_rank(documents, case["query"], constraints(case)),
            ),
        ),
    }
    for value in variants.values():
        value["recall_target_met"] = value["recall_at_10"] >= 0.90
        value["ndcg_target_met"] = value["ndcg_at_10"] >= 0.80
    report = {
        "schema_version": 1,
        "evidence_level": "development_seed_ablation_only",
        "dataset": "V2-DATA-01-SEED-v1-pending-license-and-gold-review",
        "variants": variants,
        "agent_state_ablations": {
            "memory": {
                "status": "CONTRACT_TESTED_NOT_PROVIDER_SCORED",
                "evidence": "packages/agent-runtime/tests/test_runtime.py",
            },
            "tool_planning": {
                "status": "DETERMINISTIC_FAKE_TESTED_NOT_PROVIDER_SCORED",
                "evidence": "packages/agent-runtime/tests/test_runtime.py",
            },
            "production_embedding": {
                "status": "NOT_RUN_EXTERNAL_GATE",
                "evidence": None,
            },
        },
        "heldout_consumed": False,
        "real_provider_calls": 0,
        "limitations": [
            "Sparse token overlap is an offline vector-shaped baseline, not a production embedding model.",
            "The old 226-case seed remains development-only pending license and gold review.",
            "No score in this report is a held-out, LIVE or human-quality result.",
        ],
        "numeric_guard": {
            "all_metrics_finite": all(
                math.isfinite(float(metric))
                for variant in variants.values()
                for key, metric in variant.items()
                if key in {"recall_at_10", "ndcg_at_10"}
            )
        },
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
            print("DRIFT evals/v2/results/ablation-report.json")
            return 1
        print("ablation=deterministic variants=4 heldout_consumed=0")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(expected)
    print("generated evals/v2/results/ablation-report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
