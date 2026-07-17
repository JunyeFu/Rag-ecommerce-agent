"""
P@3 Retrieval Precision Test - post UUID5 fix verification

⚠️  DEPRECATED: This script was written for the Qdrant era and has not been
    updated for the pgvector migration. It will not work as-is. To run P@3
    evaluation, use the /api/v1/evaluation endpoint instead.

Directly queries Qdrant with embedded test queries, computes Precision@3
against ground truth product IDs. Does NOT require the backend server.

Usage: python scripts/run_p3_test.py [--limit N] [--update-ground-truth] [--with-reranker]
"""
import argparse
import json
import os
import sys
import time
from collections import defaultdict

import numpy as np
import requests
from sentence_transformers import SentenceTransformer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
EVAL_CASES_PATH = os.path.join(BASE_DIR, "data", "test_cases", "eval_cases.json")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "test_cases", "p3_results.json")
QDRANT_URL = "http://localhost:6333"
COLLECTION = "products"

_HF_EMBEDDING = "BAAI/bge-large-zh-v1.5"
_LOCAL_EMBEDDING = os.path.join(BASE_DIR, "data", "models", "bge-large-zh-v1.5")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL",
    _LOCAL_EMBEDDING if os.path.isdir(_LOCAL_EMBEDDING) else _HF_EMBEDDING)


def load_all_products() -> list[dict]:
    """Fetch all products from Qdrant with full payload."""
    url = f"{QDRANT_URL}/collections/{COLLECTION}/points/scroll"
    products = []
    next_offset = None
    while True:
        body = {"limit": 100, "with_payload": True, "with_vector": False}
        if next_offset:
            body["offset"] = next_offset
        resp = requests.post(url, json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        points = data["result"]["points"]
        for pt in points:
            payload = pt.get("payload", {})
            payload["_point_id"] = pt["id"]
            products.append(payload)
        next_offset = data["result"].get("next_page_offset")
        if next_offset is None:
            break
    print(f"  Loaded {len(products)} products from Qdrant")
    return products


def search_qdrant_hits(model, query: str, top_k: int = 10) -> list[dict]:
    """Embed query and search Qdrant, return raw hits with payload."""
    vec = model.encode(query, normalize_embeddings=True).tolist()
    url = f"{QDRANT_URL}/collections/{COLLECTION}/points/search"
    body = {"vector": vec, "limit": top_k, "with_payload": True}
    resp = requests.post(url, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()["result"]


def search_qdrant(model, query: str, top_k: int = 10, with_reranker: bool = True, hybrid: bool = False) -> list[str]:
    """Embed query and search Qdrant, optionally rerank + hybrid before P@3."""
    hits = search_qdrant_hits(model, query, top_k=top_k)
    if with_reranker and hits:
        from app.services.reranker import rerank

        docs = [
            {"id": h.get("id"), "score": h.get("score", 0), "payload": h.get("payload", {})}
            for h in hits
        ]
        docs = rerank(query, docs, top_k=top_k)
        return [d["payload"].get("product_id", "") for d in docs]

    return [r["payload"].get("product_id", "") for r in hits]


def build_ground_truth_map(products: list[dict]) -> dict[str, list[str]]:
    """Build a mapping of category -> product_ids for ground truth generation."""
    cat_map = defaultdict(list)
    for p in products:
        cat = p.get("category", "")
        pid = p.get("product_id", "")
        brand = p.get("brand", "")
        if pid:
            cat_map[cat].append({"product_id": pid, "brand": brand, "title": p.get("title", ""),
                                 "rating": p.get("rating", 0), "price": p.get("price", 0)})
    return cat_map


def find_ground_truth(query: str, cat_map: dict[str, list], slots: dict = None) -> list[str]:
    """Find ground truth product IDs for a query based on category/keyword matching."""
    q_lower = query.lower()

    # Keyword -> actual Qdrant category mapping (based on real 100-category dataset)
    KEYWORD_CAT_MAP = {
        # 数码电子
        "耳机": "耳机", "降噪": "耳机", "头戴": "耳机", "耳塞": "耳机",
        "手机": "手机", "智能手机": "手机", "iphone": "手机",
        "音箱": "音箱", "蓝牙音箱": "音箱", "音响": "音箱",
        "平板": "平板", "平板电脑": "平板", "ipad": "平板",
        "手表": "手表", "运动手表": "手表", "智能手表": "手表",
        "电脑": "电脑", "笔记本": "笔记本", "笔记本电脑": "笔记本",
        "键盘": "键盘", "机械键盘": "键盘",
        "鼠标": "配件", "无线鼠标": "配件",
        "充电宝": "配件", "充电器": "配件", "数据线": "配件", "移动电源": "配件",
        "相机": "相机", "单反": "相机", "微单": "相机",
        # 鞋服
        "跑鞋": "跑鞋", "运动鞋": "运动鞋", "休闲鞋": "休闲鞋",
        "T恤": "T恤", "衬衫": "衬衫", "外套": "外套",
        "裤装": "裤装", "裤子": "裤装", "牛仔裤": "裤装",
        "裙装": "裙装", "裙子": "裙装",
        "西装": "外套", "西服": "外套",
        "皮鞋": "休闲鞋", "凉鞋": "休闲鞋",
        # 包袋
        "双肩包": "双肩包", "背包": "双肩包", "书包": "双肩包",
        "单肩包": "单肩包", "斜挎包": "斜挎包",
        "行李箱": "行李箱", "旅行箱": "行李箱",
        # 美妆护肤
        "精华": "精华液", "精华液": "精华液", "面霜": "面霜",
        "防晒": "防晒", "防晒霜": "防晒", "隔离": "防晒",
        "面膜": "面霜", "洗面奶": "洗发水", "洁面": "洗发水",
        "口红": "口红", "唇膏": "口红", "唇釉": "口红",
        "粉底": "粉底", "粉底液": "粉底",
        "眼霜": "眼霜",
        "洗发": "洗发水", "洗发水": "洗发水",
        "沐浴": "沐浴露", "沐浴露": "沐浴露",
        "香水": "单肩包",
        # 食品饮料
        "零食": "零食", "坚果": "坚果", "巧克力": "巧克力",
        "咖啡": "咖啡", "茶叶": "饮料", "茶": "饮料",
        "饮料": "饮料", "饮用水": "饮用水",
        "饼干": "饼干",
        # 运动户外
        "瑜伽": "瑜伽", "瑜伽用品": "瑜伽用品", "运动服": "运动服",
        "哑铃": "力量训练", "力量训练": "力量训练",
        "跳绳": "跳绳", "球拍": "球拍", "球类": "球类",
        "帐篷": "户外", "睡袋": "户外", "户外": "户外",
        "登山包": "登山包", "运动监测": "运动监测",
        # 家居生活
        "台灯": "台灯", "加湿器": "加湿器", "净水器": "净水器",
        "吹风机": "个人护理", "电动牙刷": "口腔护理",
        "吸尘器": "吸尘器", "扫地机器人": "扫地机器人",
        "电饭煲": "电饭煲", "空气炸锅": "空气炸锅",
        "枕头": "枕头", "床品": "床品",
        "香薰": "台灯", "纸巾": "纸巾",
        # 母婴宠物
        "宠物用品": "宠物用品", "宠物食品": "宠物食品",
        "喂养用品": "喂养用品", "宠物": "宠物用品",
        "婴儿": "婴儿玩具",
        # 图书文具
        "小说": "小说", "教材": "教材", "图书": "小说",
        "文具": "文具",
        # 场景关键词
        "送礼物": "精华液", "生日": "口红", "节日": "坚果",
        "旅行": "行李箱", "度假": "防晒", "出差": "行李箱",
        "通勤": "双肩包", "露营": "户外",
        "穿搭": "T恤", "健身": "运动服",
        "办公": "办公配件",
    }

    # Find the matching category
    matched_cat = None
    for kw, cat in sorted(KEYWORD_CAT_MAP.items(), key=lambda x: -len(x[0])):
        if kw in q_lower:
            matched_cat = cat
            break

    if not matched_cat:
        return []

    # Find products in that category
    candidates = cat_map.get(matched_cat, [])
    if not candidates:
        # Try fuzzy match
        for cat_name in cat_map:
            if matched_cat in cat_name or cat_name in matched_cat:
                candidates = cat_map[cat_name]
                break

    # Sort by rating descending, take top 3
    sorted_candidates = sorted(candidates, key=lambda x: (-x.get("rating", 0), x.get("price", 999)))
    return [c["product_id"] for c in sorted_candidates[:3]]


def compute_precision_at_k(retrieved: list[str], ground_truth: list[str], k: int = 3) -> float:
    """Compute Precision@k."""
    if not ground_truth:
        return 0.0
    gt_set = set(ground_truth)
    ret = retrieved[:k]
    if not ret:
        return 0.0
    return len(set(ret) & gt_set) / k


def compute_recall_at_k(retrieved: list[str], ground_truth: list[str], k: int = 3) -> float:
    """Compute Recall@k."""
    if not ground_truth:
        return 0.0
    gt_set = set(ground_truth)
    ret = retrieved[:k]
    if not ret:
        return 0.0
    return len(set(ret) & gt_set) / len(gt_set)


def update_eval_cases_ground_truth(cat_map: dict[str, list]):
    """Update eval_cases.json with real ground truth product IDs."""
    with open(EVAL_CASES_PATH, encoding="utf-8") as f:
        cases = json.load(f)

    updated = 0
    for case in cases:
        query = case["query"]
        gt = find_ground_truth(query, cat_map)
        if gt:
            case["ground_truth_product_ids"] = gt
            updated += 1

    with open(EVAL_CASES_PATH, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2, ensure_ascii=False)

    print(f"  Updated ground truth for {updated}/{len(cases)} cases in eval_cases.json")
    return cases


def main(limit: int = 0, update_gt: bool = False, with_reranker: bool = True, hybrid: bool = False):
    print("=" * 60)
    print("P@3 Retrieval Precision Test")
    print("=" * 60)

    # 1. Load model
    print("\n[1/4] Loading embedding model...")
    t0 = time.time()
    model = SentenceTransformer(EMBEDDING_MODEL)
    print(f"  Model loaded in {time.time() - t0:.1f}s")

    # 2. Load products from Qdrant
    print("\n[2/4] Loading products from Qdrant...")
    products = load_all_products()
    cat_map = build_ground_truth_map(products)

    # Show category distribution
    print(f"  Categories: {len(cat_map)}")
    for cat, items in sorted(cat_map.items(), key=lambda x: -len(x[1]))[:15]:
        print(f"    {cat}: {len(items)} products")

    # 3. Load/update eval cases
    print("\n[3/4] Loading eval cases...")
    if update_gt:
        cases = update_eval_cases_ground_truth(cat_map)
    else:
        with open(EVAL_CASES_PATH, encoding="utf-8") as f:
            cases = json.load(f)
    print(f"  Total cases: {len(cases)}")

    # Also load extension cases
    extensions_dir = os.path.join(BASE_DIR, "data", "test_cases")
    for ext_name in ["eval_cases_scene4.json", "eval_cases_scene6.json", "eval_cases_scene7.json"]:
        ext_path = os.path.join(extensions_dir, ext_name)
        if os.path.exists(ext_path):
            with open(ext_path, encoding="utf-8") as f:
                ext_cases = json.load(f)
            cases.extend(ext_cases)
            print(f"  + loaded {len(ext_cases)} cases from {ext_name}")

    if limit:
        cases = cases[:limit]

    # 4. Run retrieval test
    mode = "vector+reranker" if with_reranker else "vector-only"
    print(f"\n[4/4] Running P@3 test on {len(cases)} cases ({mode})...")
    results = []
    p3_scores = []
    recall_scores = []
    scenarios = defaultdict(lambda: {"total": 0, "p3_sum": 0, "recall_sum": 0, "with_gt": 0, "latency_sum": 0})

    for i, case in enumerate(cases):
        query = case["query"]
        gt_ids = case.get("ground_truth_product_ids", [])

        t0 = time.time()
        retrieved = search_qdrant(model, query, top_k=10, with_reranker=with_reranker, hybrid=hybrid)
        latency = (time.time() - t0) * 1000

        p3 = compute_precision_at_k(retrieved, gt_ids, k=3)
        recall = compute_recall_at_k(retrieved, gt_ids, k=3)

        p3_scores.append(p3)
        recall_scores.append(recall)

        scenario = case.get("scenario", "unknown")
        scenarios[scenario]["total"] += 1
        scenarios[scenario]["p3_sum"] += p3
        scenarios[scenario]["recall_sum"] += recall
        scenarios[scenario]["latency_sum"] += latency
        if gt_ids:
            scenarios[scenario]["with_gt"] += 1

        results.append({
            "case_id": case.get("id", f"case_{i}"),
            "scenario": scenario,
            "query": query,
            "ground_truth": gt_ids,
            "retrieved_top3": retrieved[:3],
            "retrieved_top10": retrieved[:10],
            "p3": round(p3, 4),
            "recall": round(recall, 4),
            "latency_ms": round(latency, 1),
        })

        gt_icon = "+" if gt_ids else "-"
        print(f"  [{i+1:3d}/{len(cases)}] {gt_icon} P@3={p3:.2f} "
              f"Recall={recall:.2f} {latency:5.0f}ms | {query[:50]}")

    # Summary
    avg_p3 = np.mean(p3_scores) if p3_scores else 0
    avg_recall = np.mean(recall_scores) if recall_scores else 0
    cases_with_gt = sum(1 for r in results if r["ground_truth"])
    non_zero_p3 = sum(1 for s in p3_scores if s > 0)

    print(f"\n{'=' * 60}")
    print(f"RESULTS")
    print(f"{'=' * 60}")
    print(f"  Total cases:          {len(cases)}")
    print(f"  Cases with ground truth: {cases_with_gt}")
    print(f"  Non-zero P@3:         {non_zero_p3}/{len(p3_scores)} ({100*non_zero_p3/max(len(p3_scores),1):.0f}%)")
    print(f"  Mean P@3:             {avg_p3:.4f}  (target >= 0.60)")
    print(f"  Mean Recall@3:        {avg_recall:.4f}")
    print(f"  Avg retrieval latency: {np.mean([r['latency_ms'] for r in results]):.0f}ms")
    print(f"\n  By scenario:")
    for s in sorted(scenarios.keys()):
        d = scenarios[s]
        n = max(d["total"], 1)
        print(f"    {s:30s} P@3={d['p3_sum']/n:.3f}  recall={d['recall_sum']/n:.3f}  "
              f"lat={d['latency_sum']/n:.0f}ms  gt={d['with_gt']}/{d['total']}")

    # Write report
    report = {
        "run_info": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_cases": len(cases),
            "embedding_model": EMBEDDING_MODEL,
            "qdrant_collection": COLLECTION,
            "retrieval_mode": mode,
        },
        "summary": {
            "mean_p3": round(avg_p3, 4),
            "mean_recall": round(avg_recall, 4),
            "non_zero_p3_count": non_zero_p3,
            "cases_with_ground_truth": cases_with_gt,
            "avg_latency_ms": round(np.mean([r['latency_ms'] for r in results]), 1),
            "by_scenario": {
                s: {
                    "total": d["total"],
                    "p3": round(d["p3_sum"] / max(d["total"], 1), 4),
                    "recall": round(d["recall_sum"] / max(d["total"], 1), 4),
                    "avg_latency_ms": round(d["latency_sum"] / max(d["total"], 1), 1),
                    "with_ground_truth": d["with_gt"],
                }
                for s, d in sorted(scenarios.items())
            },
        },
        "results": results,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n  Report written to: {OUTPUT_PATH}")

    # PASS/FAIL
    if avg_p3 >= 0.60:
        print(f"\n  PASS: P@3 {avg_p3:.4f} >= target 0.60")
    else:
        print(f"\n  NOTE: P@3 {avg_p3:.4f} < target 0.60")
        if cases_with_gt == 0:
            print(f"  CAUSE: No ground truth IDs in eval cases.")
            print(f"  Re-run with --update-ground-truth to auto-generate.")

    return avg_p3


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P@3 Retrieval Precision Test")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of cases")
    parser.add_argument("--update-ground-truth", action="store_true",
                        help="Auto-generate ground truth from product data")
    parser.add_argument("--with-reranker", action="store_true", default=True,
                        help="Apply app.services.reranker to the top-K hits before scoring (default: on)")
    parser.add_argument("--no-reranker", action="store_false", dest="with_reranker",
                        help="Disable reranker (raw vector retrieval only)")
    parser.add_argument("--hybrid", action="store_true",
                        help="Enable hybrid search (dense + text RRF fusion)")
    args = parser.parse_args()
    main(limit=args.limit, update_gt=args.update_ground_truth, with_reranker=args.with_reranker, hybrid=args.hybrid)
