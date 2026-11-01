#!/usr/bin/env python3
"""Run one read-only Gowu sandbox price check without exposing credentials."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/connectors/src"))
sys.path.insert(0, str(ROOT / "packages/domain/src"))

from ragcommerce_connectors import ConnectorError, GowuDemoPriceClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="small-scope product keyword, for example 降噪耳机")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    app_key = os.environ.get("GOWU_DEMO_APP_KEY", "").strip()
    if not app_key:
        print("GOWU_DEMO_APP_KEY is required")
        return 2
    try:
        prices = GowuDemoPriceClient(app_key).search(args.query, limit=args.limit)
    except ConnectorError as exc:
        print(json.dumps({"status": "unavailable", "reason": exc.kind}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "status": "available",
                "authority": "weak_third_party_sandbox",
                "verification": "THIRD_PARTY_DEMO",
                "commercial_release_evidence": False,
                "items": [
                    {
                        "external_product_id": item.external_product_id,
                        "title": item.title,
                        "category": item.category,
                        "brand": item.brand,
                        "price_minor": item.price_minor,
                        "market_price_minor": item.market_price_minor,
                        "availability": item.availability,
                        "collected_at": item.collected_at.isoformat(),
                        "expires_at": item.expires_at.isoformat(),
                        "source_ref": item.source_ref,
                    }
                    for item in prices
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
