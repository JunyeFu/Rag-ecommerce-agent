#!/usr/bin/env python3
"""Generate the project-authored V3 fictional 3C demo catalog and assets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/demo"

CATEGORIES = {
    "手机": {
        "brand": "Nova Mobile",
        "family": "Pulse",
        "base_price": 159900,
        "attributes": (
            ("屏幕", "6.1英寸 OLED"),
            ("续航", "4800mAh"),
            ("重量", "178g"),
        ),
        "scenarios": ("日常通勤", "移动摄影"),
        "color": "#6D5CE7",
    },
    "电脑": {
        "brand": "Arc Compute",
        "family": "Forge",
        "base_price": 459900,
        "attributes": (
            ("内存", "16GB"),
            ("存储", "1TB SSD"),
            ("重量", "1.35kg"),
        ),
        "scenarios": ("软件开发", "移动办公"),
        "color": "#2674D9",
    },
    "耳机": {
        "brand": "Aural Audio",
        "family": "Quiet",
        "base_price": 39900,
        "attributes": (
            ("降噪", "自适应主动降噪"),
            ("续航", "32小时"),
            ("连接", "蓝牙多设备"),
        ),
        "scenarios": ("地铁通勤", "专注学习"),
        "color": "#118B65",
    },
    "相机": {
        "brand": "Luma Optics",
        "family": "Frame",
        "base_price": 529900,
        "attributes": (
            ("传感器", "2400万像素"),
            ("防抖", "五轴防抖"),
            ("视频", "4K 60fps"),
        ),
        "scenarios": ("旅行记录", "视频创作"),
        "color": "#D96A2B",
    },
}


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def product(category: str, index: int) -> dict[str, object]:
    spec = CATEGORIES[category]
    key = f"{category}:{index:02d}"
    product_id = uuid5(NAMESPACE_URL, f"urn:rag-commerce:demo-product:{key}")
    variant_id = uuid5(NAMESPACE_URL, f"urn:rag-commerce:demo-variant:{key}")
    offer_id = uuid5(NAMESPACE_URL, f"urn:rag-commerce:demo-offer:{key}")
    suffix = f"{index:02d}"
    title = f"{spec['brand']} {spec['family']} {suffix} 演示{category}"
    attributes = dict(spec["attributes"])
    attributes["演示档位"] = ("轻量", "均衡", "进阶")[(index - 1) % 3]
    price = int(spec["base_price"]) + (index - 1) * 1300
    source_ref = f"demo:v3:{product_id}"
    return {
        "schema_version": 3,
        "product_id": str(product_id),
        "variant_id": str(variant_id),
        "title": title,
        "brand": spec["brand"],
        "category": category,
        "attributes": attributes,
        "scenarios": list(spec["scenarios"]),
        "fit_tags": [*spec["scenarios"], attributes["演示档位"]],
        "image_ref": f"images/{category}-{suffix}.svg",
        "evidence_refs": [source_ref],
        "license_status": "project_authored_demo_only",
        "offer": {
            "offer_id": str(offer_id),
            "variant_id": str(variant_id),
            "merchant_name": "RAG Commerce Demo Store",
            "verification": "DEMO_FIXTURE",
            "availability": "AVAILABLE",
            "price_minor": price,
            "shipping_minor": 0,
            "currency": "CNY",
            "source_ref": f"{source_ref}:offer",
            "link_url": f"https://example.com/?demo_offer={offer_id}",
        },
    }


def svg(row: dict[str, object], color: str) -> str:
    title = str(row["title"])
    category = str(row["category"])
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480">
  <rect width="640" height="480" rx="48" fill="#F4F6F8"/>
  <circle cx="320" cy="190" r="112" fill="{color}" opacity="0.16"/>
  <rect x="238" y="108" width="164" height="164" rx="42" fill="{color}"/>
  <text x="320" y="205" text-anchor="middle" font-size="54" fill="white" font-family="sans-serif">{category}</text>
  <text x="320" y="350" text-anchor="middle" font-size="24" fill="#17211B" font-family="sans-serif">{title}</text>
  <text x="320" y="392" text-anchor="middle" font-size="18" fill="#526159" font-family="sans-serif">PROJECT-AUTHORED DEMO FIXTURE</text>
</svg>
'''


def render() -> dict[Path, str]:
    rows = [product(category, index) for category in CATEGORIES for index in range(1, 16)]
    catalog = "".join(f"{canonical(row)}\n" for row in rows)
    outputs: dict[Path, str] = {OUTPUT / "catalog.v3.jsonl": catalog}
    for row in rows:
        color = str(CATEGORIES[str(row["category"])]["color"])
        outputs[OUTPUT / str(row["image_ref"])] = svg(row, color)
    manifest = {
        "schema_version": 3,
        "dataset": "rag-commerce-project-authored-demo-v3",
        "records": len(rows),
        "categories": {category: 15 for category in CATEGORIES},
        "license_status": "project_authored_demo_only",
        "commercial_claim": False,
        "catalog_sha256": hashlib.sha256(catalog.encode("utf-8")).hexdigest(),
        "generator": "scripts/generate_demo_catalog.py",
    }
    outputs[OUTPUT / "manifest.json"] = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    drift = []
    for path, expected in render().items():
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                drift.append(path.relative_to(ROOT).as_posix())
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8", newline="\n")
    if drift:
        raise SystemExit("demo catalog drift: " + ", ".join(drift))
    print("demo catalog verified" if args.check else "generated 60 demo products and assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
