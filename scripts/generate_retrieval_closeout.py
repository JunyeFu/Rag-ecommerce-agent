"""Freeze authored graded retrieval cases before first evaluation, never tune on held-out."""

# ruff: noqa: RUF001 -- Chinese punctuation is part of the frozen query input.
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "evals/v3/retrieval-closeout.json"
CATALOG = ROOT / "data/demo/catalog.v3.jsonl"
INTENTS = {
    "手机": [
        "每天坐车想随手记录生活",
        "带着去拍街景同时接电话",
        "只做日常通讯和出行拍照",
        "通勤时记录沿途风景",
        "轻装出门拍照和通讯",
        "上下班路上拍生活照片",
    ],
    "电脑": [
        "背着到图书馆写代码",
        "来回办公室写程序带着不累",
        "常出差要做软件开发",
        "带到咖啡馆写代码",
        "上课后还要写程序和办公",
        "移动办公兼顾开发",
    ],
    "耳机": [
        "地铁太吵想专心听东西",
        "自习室里想隔绝干扰",
        "学习时不想被说话声打断",
        "坐车时想安静听课",
        "专心复习不受周围噪声影响",
        "通勤与学习都想安静",
    ],
    "相机": [
        "旅行想记录画面又拍视频",
        "出门创作视频不想抖动",
        "记录旅途并做短视频",
        "拍风景也记录清晰视频",
        "旅行时拍照兼顾视频创作",
        "走路拍视频想稳定一些",
    ],
}
ALIASES = {
    "手机": ["Nova", "新星"],
    "电脑": ["Arc", "弧算"],
    "耳机": ["Aural", "声域"],
    "相机": ["Luma", "光影"],
}


def render() -> dict:
    rows = [json.loads(line) for line in CATALOG.read_text(encoding="utf-8").splitlines()]
    cases = []
    for category, intents in INTENTS.items():
        products = [p for p in rows if p["category"] == category]
        attribute, attribute_value = next(
            (k, v) for k, v in products[0]["attributes"].items() if k != "演示档位"
        )
        for family in ["alias_exact", "implicit_use", "hard_constraints", "tradeoff", "no_match"]:
            for index in range(6):
                cutoff = 4 + index
                ceiling = products[cutoff - 1]["offer"]["price_minor"] / 100
                constraints = {"category": category, "price_max": ceiling}
                eligible = products[:cutoff]
                query = f"{intents[index]}，预算不超过{ceiling:g}元"
                rationale = (
                    "满足任务已明确的品类及预算；演示目录同品类规格相同，不按SKU名称构造用途正例。"
                )
                grades = {p["product_id"]: 3 for p in eligible}
                if family == "alias_exact":
                    if index % 2 == 0:
                        pair = products[index : index + 2]
                        query = f"比较{pair[0]['title']}和{pair[1]['title']}"
                        constraints = {"category": category}
                        grades = {p["product_id"]: 3 for p in pair}
                        rationale = "用户点名两款，其他款不是此项任务的相关商品。"
                    else:
                        alias = ALIASES[category][index % 2]
                        query = f"{alias}牌的{category}，预算{ceiling:g}元以内"
                        constraints["brand_candidates"] = [alias]
                elif family == "hard_constraints":
                    query = f"{category}需要{attribute}{attribute_value}，预算{ceiling:g}元以内"
                    constraints[attribute] = attribute_value
                elif family == "tradeoff":
                    query = f"{category}轻量档和旗舰档怎么取舍，预算{ceiling:g}元以内"
                    constraints["exclude_terms"] = ["均衡"]
                    grades = {
                        p["product_id"]: 3 if p["attributes"]["演示档位"] == "轻量" else 2
                        for p in eligible
                        if p["attributes"]["演示档位"] != "均衡"
                    }
                    rationale = "比较轻量与旗舰两档：优先轻量，旗舰仍相关；均衡不属于这次比较。"
                elif family == "no_match":
                    if index % 3 == 0:
                        query = f"1元以内的{category}"
                        constraints = {"category": category, "price_max": 1}
                    elif index % 3 == 1:
                        query = f"{category}需要{attribute}未提供的超高规格"
                        constraints = {"category": category, attribute: "未提供的超高规格"}
                    else:
                        query = f"不接受演示目录品牌的{category}"
                        constraints = {
                            "category": category,
                            "exclude_brands": [products[0]["brand"]],
                        }
                    grades = {}
                    rationale = "结构化硬条件无法被任何目录商品满足，独立统计，不纳入Recall/NDCG。"
                cases.append(
                    {
                        "id": f"R{len(cases) + 1:03}",
                        "split": "development" if index < 2 else "acceptance",
                        "family": family,
                        "category": category,
                        "query": query,
                        "constraints": constraints,
                        "qrels": grades,
                        "rationale": rationale,
                        "filter_source": "project-authored task constraints; NLU is not scored by this component test",
                    }
                )
    return {
        "schema_version": 1,
        "frozen_at": "2026-10-09",
        "catalog": str(CATALOG.relative_to(ROOT)).replace("\\", "/"),
        "catalog_sha256": hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
        "cases": cases,
        "grading": {
            "3": "preferred task match",
            "2": "valid tradeoff alternative",
            "0": "not relevant to this task",
        },
        "recall_positive_threshold": 2,
        "development_cases": 40,
        "acceptance_cases": 80,
        "limitations": [
            "Project-authored automatic labels, not human/user validation.",
            "60 SKU have only four distinct specification profiles; equivalent SKUs receive equal grades.",
            "Structured filters are supplied task conditions; category inference and constraint extraction are evaluated in Agent tests, not here.",
            "Public once frozen; acceptance is a development hold-out, not an independently collected blind benchmark.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = (json.dumps(render(), ensure_ascii=False, indent=2) + "\n").encode()
    if args.check:
        return 0 if TARGET.read_bytes() == data else 1
    if TARGET.exists():
        raise RuntimeError(
            "frozen query set already exists; do not overwrite or tune acceptance cases"
        )
    TARGET.write_bytes(data)
    print("frozen retrieval queries=120 development=40 acceptance=80")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
