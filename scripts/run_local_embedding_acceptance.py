#!/usr/bin/env python3
"""Evaluate the pinned local BGE ONNX model on the public V3 golden scenarios."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
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
    ndcg,
    recall,
)

MODEL_ID = "Qdrant/bge-small-zh-v1.5"
REVISION = "46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59"
OUTPUT = ROOT / "docs/evidence/v3/local-bge-small-zh-evaluation.json"


async def evaluate() -> dict[str, object]:
    model_dir = Path(snapshot_download(repo_id=MODEL_ID, revision=REVISION, local_files_only=True))
    provider = LocalOnnxEmbeddingProvider(model_dir)
    documents = load_demo_documents(ROOT / "data/demo/catalog.v3.jsonl")
    index = QdrantHybridSemanticIndex(
        documents, provider, QdrantClient(":memory:"), "local-bge-acceptance"
    )
    await index.build_index()
    cases = json.loads((ROOT / "evals/v3/golden-scenarios.json").read_text(encoding="utf-8"))[
        "scenarios"
    ]
    recalls: list[float] = []
    ndcgs: list[float] = []
    latencies: list[float] = []
    results: list[dict[str, object]] = []
    ablations: dict[str, list[list[str]]] = {"bm25": [], "bge_vector": [], "rrf_hybrid": []}
    for case in cases:
        started = perf_counter()
        hits = await index.search(str(case["query"]), 10)
        latencies.append((perf_counter() - started) * 1000)
        ranked = [hit.document.seed_id for hit in hits]
        lexical = [hit.document.seed_id for hit in index.lexical.search(str(case["query"]), 10)]
        query_vector = await provider.embed_query(str(case["query"]))
        vector_result = await asyncio.to_thread(
            index.client.query_points,
            index.collection,
            query=list(query_vector),
            limit=10,
            with_payload=True,
        )
        vector_ranked = [str(point.payload["seed_id"]) for point in vector_result.points]
        ablations["bm25"].append(lexical)
        ablations["bge_vector"].append(vector_ranked)
        ablations["rrf_hybrid"].append(ranked)
        relevant = {str(case["expected_product_id"])}
        recalls.append(recall(ranked, relevant))
        ndcgs.append(ndcg(ranked, relevant))
        results.append(
            {
                "scenario_id": case["id"],
                "expected_product_id": case["expected_product_id"],
                "rank": (
                    ranked.index(str(case["expected_product_id"])) + 1
                    if str(case["expected_product_id"]) in ranked
                    else None
                ),
            }
        )
    recall_at_10 = mean(recalls)
    ndcg_at_10 = mean(ndcgs)
    ablation_metrics = {
        name: {
            "cases": len(cases),
            "recall_at_10": mean(
                recall(rank, {str(case["expected_product_id"])})
                for rank, case in zip(rankings, cases, strict=True)
            ),
            "ndcg_at_10": mean(
                ndcg(rank, {str(case["expected_product_id"])})
                for rank, case in zip(rankings, cases, strict=True)
            ),
        }
        for name, rankings in ablations.items()
    }
    return {
        "schema_version": 1,
        "evidence_level": "local_real_embedding_public_golden_set",
        "model": MODEL_ID,
        "revision": REVISION,
        "runtime": "ONNX Runtime CPU",
        "embedding_dimensions": 512,
        "documents": len(documents),
        "scenarios": len(cases),
        "retrieval": "BGE vector + BM25 + RRF",
        "recall_at_10": recall_at_10,
        "ndcg_at_10": ndcg_at_10,
        "ablations": ablation_metrics,
        "targets_met": recall_at_10 >= 0.90 and ndcg_at_10 >= 0.80,
        "latency_ms": {
            "first_search_including_index_build": round(latencies[0], 2),
            "subsequent_search_mean": round(mean(latencies[1:]), 2),
        },
        "results": results,
        "limitations": [
            "The ten golden scenarios are public project-authored cases, not the automated challenge split.",
            "Latency is a local machine observation and not a cross-device benchmark.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(evaluate())
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(rendered, encoding="utf-8")
        print(f"generated {OUTPUT.relative_to(ROOT)}")
    else:
        print(rendered, end="")
    return 0 if report["targets_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
