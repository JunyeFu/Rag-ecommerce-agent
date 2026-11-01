"""Read an existing local-BGE Qdrant index from two independent processes."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from qdrant_client import QdrantClient
from ragcommerce_api.retrieval_config import configured_retrieval

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if os.environ["RETRIEVAL_MODE"] != "local":
        parser.error("Only explicit local embedding mode is supported")
    if args.child:
        index = configured_retrieval(ROOT / "data/demo/catalog.v3.jsonl")
        hits = asyncio.run(index.search("预算1000元的通勤降噪耳机"))
        assert hits
        print(json.dumps({"hits": [hit.document.seed_id for hit in hits]}))
        index.client.close()
        return 0
    if args.output is None or args.output.exists():
        parser.error("Choose a new evidence path; existing receipts are preserved")
    client = QdrantClient(url=os.environ["QDRANT_URL"])
    alias = os.environ["QDRANT_COLLECTION"]

    def snapshot():
        return {
            "aliases": sorted(
                (x.alias_name, x.collection_name) for x in client.get_aliases().aliases
            ),
            "collections": sorted(x.name for x in client.get_collections().collections),
            "points": client.count(collection_name=alias, exact=True).count,
        }

    before = snapshot()
    children = [
        subprocess.Popen(
            [sys.executable, __file__, "--child"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        for _ in range(2)
    ]
    results = []
    for child in children:
        stdout, stderr = child.communicate(timeout=90)
        if child.returncode:
            raise RuntimeError(f"Independent retrieval reader failed: {stderr}")
        results.append(json.loads(stdout))
    after = snapshot()
    report = {
        "evidence_level": "two_independent_local_BGE_read_processes_real_Qdrant",
        "before": before,
        "after": after,
        "readers": results,
        "passed": before == after and before["points"] == 60 and all(x["hits"] for x in results),
        "paid_calls": 0,
        "limitation": "Shared production retrieval composition, not a second capacity or Worker restart test",
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    client.close()
    print(f"shared retrieval passed={report['passed']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
