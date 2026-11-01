"""Measure BM25, pinned real BGE and actual RRF on the frozen 40/80 query set."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from time import perf_counter

from huggingface_hub import snapshot_download
from qdrant_client import QdrantClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/retrieval/src"))
from ragcommerce_retrieval import (  # noqa: E402
    LocalOnnxEmbeddingProvider,
    QdrantHybridSemanticIndex,
    load_demo_documents,
    recall,
)
from ragcommerce_retrieval.normalization import normalize_brand  # noqa: E402

MODEL = "Qdrant/bge-small-zh-v1.5"
REVISION = "46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59"
SUITE = ROOT / "evals/v3/retrieval-closeout.json"
DEFAULT_OUTPUT = ROOT / "docs/evidence/v3/final-retrieval-20261009.json"


def graded_ndcg(rank: list[str], qrels: dict[str, int]) -> float:
    def gain(grades):
        return sum((2**grade - 1) / math.log2(i + 2) for i, grade in enumerate(grades))

    ideal = gain(sorted(qrels.values(), reverse=True)[:10])
    return gain([qrels.get(item, 0) for item in rank[:10]]) / ideal if ideal else 0


def eligible(row: dict, constraints: dict) -> bool:
    return (
        row["category"] == constraints["category"]
        and (
            "price_max" not in constraints
            or row["offer"]["price_minor"] <= constraints["price_max"] * 100
        )
        and (
            "brand_candidates" not in constraints or row["brand"] in constraints["brand_candidates"]
        )
        and row["brand"] not in constraints.get("exclude_brands", [])
        and all(
            term not in " ".join(row["attributes"].values())
            for term in constraints.get("exclude_terms", [])
        )
        and all(
            key not in row["attributes"] or value in row["attributes"][key]
            for key, value in constraints.items()
        )
    )


async def evaluate(qdrant_url: str) -> dict:
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    catalog = ROOT / suite["catalog"]
    raw_rows = [json.loads(line) for line in catalog.read_text(encoding="utf-8").splitlines()]
    if hashlib.sha256(catalog.read_bytes()).hexdigest() != suite["catalog_sha256"]:
        raise RuntimeError("frozen catalog changed")
    directory = snapshot_download(repo_id=MODEL, revision=REVISION, local_files_only=True)
    provider = LocalOnnxEmbeddingProvider(Path(directory))
    index = QdrantHybridSemanticIndex(
        load_demo_documents(catalog),
        provider,
        QdrantClient(url=qdrant_url),
        "final-retrieval-20261009",
    )
    started = perf_counter()
    await index.build_index()
    build_ms = (perf_counter() - started) * 1000
    results = []
    for case in suite["cases"]:
        constraints = dict(case["constraints"])
        if "brand_candidates" in constraints:
            constraints["brand_candidates"] = [
                normalize_brand(value) for value in constraints["brand_candidates"]
            ]
        started = perf_counter()
        lexical = index.lexical.search(case["query"], len(index.documents), constraints)
        allowed = {hit.document.seed_id for hit in lexical}
        # Independent oracle is frozen from raw catalog criteria, not the
        # retriever's allowed-ID set; violations cannot pass tautologically.
        oracle = {row["product_id"] for row in raw_rows if eligible(row, constraints)}
        query_vector = await provider.embed_query(case["query"])
        vector = await asyncio.to_thread(
            index.client.query_points,
            index.collection,
            query=list(query_vector),
            limit=len(index.documents),
            with_payload=True,
        )
        vector_rank = [
            str(point.payload["seed_id"])
            for point in vector.points
            if str(point.payload["seed_id"]) in allowed
        ]
        hybrid = await index.search(case["query"], 10, constraints)
        ranks = {
            "bm25": [hit.document.seed_id for hit in lexical[:10]],
            "bge_vector": vector_rank[:10],
            "rrf_hybrid": [hit.document.seed_id for hit in hybrid],
        }
        positive = {
            product
            for product, grade in case["qrels"].items()
            if grade >= suite["recall_positive_threshold"]
        }
        results.append(
            {
                "id": case["id"],
                "split": case["split"],
                "family": case["family"],
                "category": case["category"],
                "positive_count": len(positive),
                "latency_ms": round((perf_counter() - started) * 1000, 2),
                "variants": {
                    name: {
                        "ranked": rank,
                        "recall_at_10": recall(rank, positive) if positive else None,
                        "ndcg_at_10": graded_ndcg(rank, case["qrels"]) if positive else None,
                        "no_match_correct": not rank if not positive else None,
                        "hard_constraint_violations": len(set(rank) - oracle),
                    }
                    for name, rank in ranks.items()
                },
            }
        )
    summary = {}
    for split in ("development", "acceptance"):
        selected = [case for case in results if case["split"] == split]
        summary[split] = {}
        for variant in ("bm25", "bge_vector", "rrf_hybrid"):
            positive = [case["variants"][variant] for case in selected if case["positive_count"]]
            negative = [
                case["variants"][variant] for case in selected if not case["positive_count"]
            ]
            summary[split][variant] = {
                "cases": len(selected),
                "positive_cases": len(positive),
                "no_match_cases": len(negative),
                "recall_at_10": mean(case["recall_at_10"] for case in positive),
                "ndcg_at_10": mean(case["ndcg_at_10"] for case in positive),
                "no_match_accuracy": mean(case["no_match_correct"] for case in negative),
                "hard_constraint_violations": sum(
                    case["variants"][variant]["hard_constraint_violations"] for case in selected
                ),
            }
    final = summary["acceptance"]["rrf_hybrid"]
    passed = (
        final["recall_at_10"] >= 0.9
        and final["ndcg_at_10"] >= 0.8
        and final["hard_constraint_violations"] == 0
        and final["no_match_accuracy"] == 1
    )
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_level": "real_local_bge_qdrant_frozen_component_retrieval",
        "model": MODEL,
        "revision": REVISION,
        "suite_sha256": hashlib.sha256(SUITE.read_bytes()).hexdigest(),
        "catalog_sha256": suite["catalog_sha256"],
        "documents": len(index.documents),
        "build_ms": round(build_ms, 2),
        "summary": summary,
        "targets_met": passed,
        "results": results,
        "rrf_gain_over_bm25": {
            metric: final[metric] - summary["acceptance"]["bm25"][metric]
            for metric in ("recall_at_10", "ndcg_at_10")
        },
        "limitations": suite["limitations"],
        "real_model_calls": 0,
        "heldout_consumed_for_tuning": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qdrant-url", default=os.environ.get("QDRANT_TEST_URL"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.qdrant_url:
        parser.error("--qdrant-url required; acceptance does not substitute Qdrant memory mode")
    if args.output.exists():
        parser.error("choose a new report path; never overwrite prior outcomes")
    report = asyncio.run(evaluate(args.qdrant_url))
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"targets_met": report["targets_met"], "summary": report["summary"]}, ensure_ascii=False
        )
    )
    return 0 if report["targets_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
