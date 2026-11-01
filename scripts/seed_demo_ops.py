"""Declare owned demo Ops inputs in PostgreSQL; never claim alliance health or QA success."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-conflict-id", default="conflict-001")
    args = parser.parse_args()
    catalog = [
        json.loads(line)
        for line in (ROOT / "data/demo/catalog.v3.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    now = datetime.now(UTC).isoformat()
    records = []
    for source, title in [
        ("src_owned_demo", "自有60 SKU演示目录"),
        ("src_jd", "京东"),
        ("src_taobao_tmall", "淘宝/天猫"),
        ("src_pdd", "拼多多"),
    ]:
        owned = source == "src_owned_demo"
        records.append(
            (
                "connector",
                source,
                {
                    "source_id": source,
                    "display_name": title,
                    "authorization": "FIXTURE_ONLY" if owned else "UNAUTHORIZED",
                    "health": "HEALTHY" if owned and len(catalog) == 60 else "BLOCKED",
                    "error_rate_5m": None,
                    "requests_used": 0,
                    "requests_limit": 0,
                    "freshness_p50_seconds": None,
                    "last_observed_at": now,
                    "evidence": {
                        "local_evidence": "data/demo/catalog.v3.jsonl"
                        if owned
                        else "not_connected",
                        "external_gate": "DEMO_FIXTURE; 不代表市场报价"
                        if owned
                        else "联盟主体授权与 live 凭据未提供",
                    },
                },
            )
        )
    # Explicit synthetic entity-review exercise, referencing two owned records.
    records.append(
        (
            "conflict",
            args.review_conflict_id,
            {
                "conflict_id": args.review_conflict_id,
                "left_entity_ref": catalog[0]["product_id"],
                "right_entity_ref": catalog[1]["product_id"],
                "conflict_fields": ["model_number"],
                "confidence": 0.5,
                "status": "PENDING",
                "source_refs": ["demo:synthetic-review-exercise", "data/demo/catalog.v3.jsonl"],
                "observed_at": now,
            },
        )
    )
    for gate, title, level, state, blocker in [
        ("local-contract", "当前候选完整回归", "LOCAL", "NOT_RUN", "需当前版本完整报告签收"),
        (
            "automated-challenge",
            "competition-v2 自动挑战集",
            "CHALLENGE",
            "NOT_RUN",
            "参考构造器不等于真实Agent评测",
        ),
        ("live-commerce", "真实联盟报价", "LIVE", "BLOCKED", "缺少 live 联盟授权与凭据"),
        (
            "candidate-release",
            "本地求职候选交付",
            "RELEASE",
            "BLOCKED",
            "真实联合验收与独立封版未完成",
        ),
    ]:
        records.append(
            (
                "gate",
                gate,
                {
                    "gate_id": gate,
                    "title": title,
                    "evidence_level": level,
                    "status": state,
                    "blocker": blocker,
                },
            )
        )
    with psycopg.connect(
        os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    ) as connection:
        for kind, key, value in records:
            connection.execute(
                "INSERT INTO ops_state_records(kind,record_id,payload) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                (kind, key, Jsonb(value)),
            )
    print("Owned demo Ops declarations persisted; existing decisions and gates preserved")


if __name__ == "__main__":
    main()
