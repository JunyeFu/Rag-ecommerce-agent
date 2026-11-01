"""Read back a clean candidate's real API, durable Worker and database result."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg

from run_v3_durable_load import mission


async def verify(api_url: str, candidate: Path) -> dict:
    manifest = json.loads((candidate / "CANDIDATE-MANIFEST.json").read_text(encoding="utf-8"))
    runtime = json.loads((candidate / "output/v3-demo/processes.json").read_text(encoding="utf-8"))
    if runtime["provider"] != "fake" or runtime["retrieval"] != "local":
        raise ValueError("Clean-start verification must not authorize paid model calls")
    async with httpx.AsyncClient(base_url=api_url, timeout=120) as client:
        result = await mission(client)
    dsn = os.environ["API_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as connection:
        database = connection.execute("SELECT current_database()").fetchone()[0]
        if database != runtime["database"]:
            raise ValueError("Evidence database differs from the launched clean candidate")
        model = connection.execute(
            "SELECT model_version FROM agent_runs WHERE id=%s", (result["run_id"],)
        ).fetchone()[0]
        events = connection.execute(
            "SELECT event_type,data FROM agent_events WHERE run_id=%s ORDER BY event_id",
            (result["run_id"],),
        ).fetchall()
        terminals = [kind for kind, _ in events if kind in {"completed", "failed"}]
        products = [
            item for kind, data in events if kind == "products" for item in data["products"]
        ]
        jobs = connection.execute(
            "SELECT status FROM api_turns WHERE run_id=%s", (result["run_id"],)
        ).fetchall()
    passed = (
        model == "deterministic-demo"
        and terminals == ["completed"]
        and result["snapshot_status"] == "COMPLETED"
        and bool(products)
        and all(item["evidence_refs"] for item in products)
        and len(jobs) == 1
        and jobs[0][0] == "COMPLETED"
    )
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_level": "INDEPENDENT_SOURCE_CLEAN_DURABLE_START",
        "candidate_directory": candidate.name,
        "candidate_manifest": {
            "git_head": manifest["git_head"],
            "files": len(manifest["files"]),
            "sha256": hashlib.sha256(
                (candidate / "CANDIDATE-MANIFEST.json").read_bytes()
            ).hexdigest(),
        },
        "provider": runtime["provider"],
        "retrieval": runtime["retrieval"],
        "runtime_source_hashes": runtime.get("runtime_source_hashes"),
        "mission": result,
        "database_model": model,
        "terminal_events": terminals,
        "durable_job_statuses": [status for (status,) in jobs],
        "recommended_products": len(products),
        "evidence_coverage": bool(products) and all(item["evidence_refs"] for item in products),
        "paid_model_calls": 0,
        "passed": passed,
        "limitations": [
            "Preliminary clean-start snapshot, not final portfolio sign-off",
            "Independent venv, database and storage; system dependency/download caches were reused",
            "Not native Android or real-provider acceptance",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Preserve existing evidence; choose a new report")
    report = asyncio.run(verify(args.api_url, args.candidate))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Clean candidate mission passed={report['passed']}; paid model calls=0")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
