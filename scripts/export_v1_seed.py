#!/usr/bin/env python3
"""Deterministically export reviewed V1 fixture fields into development-only V2 seeds."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_PATH = Path("apps/backend/data/qdrant/products_expanded_100.jsonl")
EVAL_PATH = Path("apps/backend/data/test_cases/eval_cases.json")
PRODUCT_SHA = "e11516a8012918d9f12f52c3d590d43d7a1299483935e3bb77f053ddf6322ad1"
EVAL_SHA = "337b5b3c00c51b6d82b5bce14fab2e99f7f557806d7ee8c8a9448b39dbe4d514"
SOURCE_HEAD = "8df480f2264fc937ba156d2bc3e083cb07d3619f"
FORBIDDEN_KEYS = {
    "user",
    "user_id",
    "email",
    "phone",
    "address",
    "password",
    "token",
    "secret",
    "message",
    "conversation",
    "cart",
    "order",
    "payment",
    "refund",
    "credential",
    "log",
}
PII_PATTERNS = (re.compile(r"\b1[3-9][0-9]{9}\b"), re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def minor_units(value: Any) -> int:
    decimal = Decimal(str(value))
    scaled = decimal * 100
    if scaled != scaled.to_integral_value():
        raise ValueError(f"historical price has more than two decimal places: {value}")
    return int(scaled)


def safe_images(values: Any) -> list[str]:
    images = values if isinstance(values, list) else []
    result: set[str] = set()
    for value in images:
        if not isinstance(value, str) or not value.startswith("/images/products/"):
            continue
        path = PurePosixPath(value.removeprefix("/"))
        if ".." not in path.parts:
            result.add(path.as_posix())
    return sorted(result)


def forbidden_key_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(str(key).lower() in FORBIDDEN_KEYS for key in value) + sum(
            forbidden_key_count(item) for item in value.values()
        )
    if isinstance(value, list):
        return sum(forbidden_key_count(item) for item in value)
    return 0


def pii_match_count(value: Any) -> int:
    text = json.dumps(value, ensure_ascii=False)
    return sum(len(pattern.findall(text)) for pattern in PII_PATTERNS)


def render(source: Path) -> dict[Path, str]:
    product_bytes = (source / PRODUCT_PATH).read_bytes()
    eval_bytes = (source / EVAL_PATH).read_bytes()
    if digest(product_bytes) != PRODUCT_SHA or digest(eval_bytes) != EVAL_SHA:
        raise ValueError("source hash drift; stop and re-audit inputs")

    raw_products = [
        json.loads(line) for line in product_bytes.decode("utf-8").splitlines() if line.strip()
    ]
    raw_evaluations = json.loads(eval_bytes.decode("utf-8"))
    if len(raw_products) != 287 or len(raw_evaluations) != 226:
        raise ValueError("source count drift; stop and re-audit inputs")

    catalog: list[dict[str, Any]] = []
    for item in raw_products:
        catalog.append(
            {
                "schema_version": 1,
                "seed_id": str(item["product_id"]),
                "canonical_name_candidate": str(item["title"]).strip(),
                "brand_candidate": str(item.get("brand") or "").strip() or None,
                "category_candidate": str(item.get("category") or "").strip() or None,
                "description_candidate": str(item.get("description") or "").strip(),
                "highlights": sorted(set(item.get("highlights") or [])),
                "development_rank_prior": {
                    "rating_milli": int(Decimal(str(item.get("rating", 0))) * 1000),
                    "rating_count": int(item.get("rating_count", 0)),
                    "use_scope": "development_benchmark_only",
                },
                "historical_price": {
                    "amount_minor": minor_units(item["price"]),
                    "currency": "CNY",
                    "verification": "DEVELOPMENT_SEED_ONLY",
                    "observed_at": None,
                },
                "attributes": dict(sorted((item.get("attributes") or {}).items())),
                "scenarios": sorted(set(item.get("scenarios") or [])),
                "image_refs": safe_images(item.get("image_urls")),
                "provenance": {
                    "source_path": PRODUCT_PATH.as_posix(),
                    "source_sha256": PRODUCT_SHA,
                    "license_status": "pending_review",
                    "use_scope": "development_only",
                },
            }
        )
    catalog.sort(key=lambda item: item["seed_id"])
    if len({item["seed_id"] for item in catalog}) != 287:
        raise ValueError("duplicate product seed IDs")

    evaluations: list[dict[str, Any]] = []
    for item in raw_evaluations:
        evaluations.append(
            {
                "schema_version": 1,
                "case_id": str(item["id"]),
                "scenario": str(item["scenario"]),
                "query": str(item["query"]),
                "difficulty": str(item["difficulty"]),
                "expected_intent": str(item["expected_intent"]),
                "expected_slots": dict(sorted((item.get("expected_slots") or {}).items())),
                "ground_truth_seed_ids": sorted(set(item.get("ground_truth_product_ids") or [])),
                "min_expected_results": int(item.get("min_expected_results", 0)),
                "provenance": {
                    "source_path": EVAL_PATH.as_posix(),
                    "source_sha256": EVAL_SHA,
                    "license_status": "pending_review",
                    "gold_status": "pending_review",
                    "use_scope": "development_only",
                },
            }
        )
    evaluations.sort(key=lambda item: item["case_id"])
    if len({item["case_id"] for item in evaluations}) != 226:
        raise ValueError("duplicate evaluation case IDs")

    forbidden = forbidden_key_count(catalog) + forbidden_key_count(evaluations)
    pii = pii_match_count(catalog) + pii_match_count(evaluations)
    if forbidden or pii:
        raise ValueError(f"unsafe seed content: forbidden_keys={forbidden} pii_matches={pii}")

    catalog_text = "".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in catalog
    )
    evaluation_text = json_text({"schema_version": 1, "cases": evaluations})
    ledger = {
        "schema_version": 1,
        "source_head": SOURCE_HEAD,
        "assets": [
            {
                "id": "v1-products",
                "source_path": PRODUCT_PATH.as_posix(),
                "sha256": PRODUCT_SHA,
                "license_status": "pending_review",
                "use_scope": "development_only",
                "commercial_use_allowed": False,
            },
            {
                "id": "v1-evaluation",
                "source_path": EVAL_PATH.as_posix(),
                "sha256": EVAL_SHA,
                "license_status": "pending_review",
                "use_scope": "development_only",
                "commercial_use_allowed": False,
            },
        ],
        "decision": "No exported record is licensed for production or commercial distribution.",
    }
    image_refs = [reference for item in catalog for reference in item["image_refs"]]
    image_root = source / "apps/backend/data"
    existing_images = sum((image_root / reference).is_file() for reference in image_refs)
    catalog_ids = {item["seed_id"] for item in catalog}
    ground_truth_ids = {
        reference for item in evaluations for reference in item["ground_truth_seed_ids"]
    }
    quality = {
        "schema_version": 1,
        "catalog": {
            "rows": 287,
            "unique_ids": 287,
            "categories": len({item["category_candidate"] for item in catalog}),
            "brands": len({item["brand_candidate"] for item in catalog}),
            "price_min_minor": min(item["historical_price"]["amount_minor"] for item in catalog),
            "price_max_minor": max(item["historical_price"]["amount_minor"] for item in catalog),
            "image_references": sum(len(item["image_refs"]) for item in catalog),
            "image_references_existing": existing_images,
            "image_references_missing": len(image_refs) - existing_images,
            "blank_source_fields_in_v1": sum(
                not str(item.get("source") or "").strip() for item in raw_products
            ),
        },
        "evaluation": {
            "cases": 226,
            "unique_ids": 226,
            "ground_truth_references": sum(
                len(item["ground_truth_seed_ids"]) for item in evaluations
            ),
            "unique_ground_truth_seed_ids": len(ground_truth_ids),
            "ground_truth_seed_ids_missing_from_catalog": len(ground_truth_ids - catalog_ids),
        },
        "safety": {
            "forbidden_keys": forbidden,
            "pii_matches": pii,
            "user_records": 0,
            "order_records": 0,
            "credential_records": 0,
        },
        "known_gaps": [
            "commercial_license_pending",
            "evaluation_gold_review_pending",
            "historical_price_has_no_observed_at",
            "image_binary_license_not_exported",
            "rating_fields_are_development_rank_prior_not_commercial_facts",
        ],
    }
    ledger_text, quality_text = json_text(ledger), json_text(quality)
    manifest = {
        "schema_version": 1,
        "package_id": "V2-DATA-01-SEED-v1",
        "source_head": SOURCE_HEAD,
        "generation_command": "python scripts/export_v1_seed.py --source <source-repository>",
        "deterministic": True,
        "license_status": "development_only_pending_review",
        "inputs": {
            "products": {"path": PRODUCT_PATH.as_posix(), "sha256": PRODUCT_SHA},
            "evaluation": {"path": EVAL_PATH.as_posix(), "sha256": EVAL_SHA},
        },
        "outputs": {
            "catalog": {
                "path": "data/seed/catalog.v1.jsonl",
                "sha256": digest(catalog_text.encode()),
                "rows": 287,
            },
            "evaluation": {
                "path": "evals/seed/evaluation.v1.json",
                "sha256": digest(evaluation_text.encode()),
                "cases": 226,
            },
            "license_ledger": {
                "path": "docs/data/license-ledger.json",
                "sha256": digest(ledger_text.encode()),
            },
            "quality_report": {
                "path": "docs/data/quality-report.json",
                "sha256": digest(quality_text.encode()),
            },
        },
    }
    return {
        ROOT / "data/seed/catalog.v1.jsonl": catalog_text,
        ROOT / "evals/seed/evaluation.v1.json": evaluation_text,
        ROOT / "docs/data/license-ledger.json": ledger_text,
        ROOT / "docs/data/quality-report.json": quality_text,
        ROOT / "docs/data/seed-manifest.json": json_text(manifest),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    drift: list[str] = []
    for path, expected in render(args.source.resolve()).items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != expected:
                drift.append(path.relative_to(ROOT).as_posix())
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8", newline="\n")
    if drift:
        print(f"seed drift: {len(drift)} files")
        return 1
    print("seed export check passed" if args.check else "seed export wrote 5 deterministic files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
