"""
商品对比 - 多商品多维度对比服务
从 PostgreSQL 检索商品详情 -> 构建对比维度 -> LLM 生成总结
"""
import logging
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.llm_client import chat_completion

logger = logging.getLogger("comparator")

# ── 维度自动推断 ──────────────────────────────────────────

# 核心固定维度（始终包含）
CORE_DIMENSIONS = ["价格", "评分", "品牌"]

# 属性维度白名单：从 attributes 中优先提取的键
ATTRIBUTE_PRIORITY = [
    "降噪", "续航", "连接方式", "屏幕", "分辨率", "刷新率",
    "处理器", "内存", "存储", "电池", "快充", "摄像头",
    "重量", "防水", "尺寸", "类型", "色域", "亮度",
    "CPU", "显卡", "系统", "材质", "容量", "功率",
    "声道", "驱动单元", "频率响应", "阻抗", "灵敏度",
]


def _auto_dimensions(products: list[dict]) -> list[str]:
    """从商品属性中自动推断对比维度"""
    dims = list(CORE_DIMENSIONS)

    # 收集所有商品共有的属性键
    common_keys = None
    for p in products:
        attrs = set(p.get("attributes", {}).keys())
        if common_keys is None:
            common_keys = attrs
        else:
            common_keys = common_keys & attrs

    if common_keys:
        # 按优先级排序
        prioritized = [k for k in ATTRIBUTE_PRIORITY if k in common_keys]
        remaining = [k for k in sorted(common_keys) if k not in prioritized]
        dims.extend(prioritized)
        dims.extend(remaining[:6])  # 最多额外 6 个属性维度

    return dims


def _dimension_value(product: dict, dim_name: str) -> str:
    """获取某商品在指定维度上的值"""
    if dim_name == "价格":
        price = product.get("price", 0)
        return f"¥{price}"
    elif dim_name == "评分":
        rating = product.get("rating", 0)
        count = product.get("rating_count", 0)
        return f"{rating}★ ({count}评价)"
    elif dim_name == "品牌":
        return product.get("brand", "未知")
    else:
        # 从 attributes 中取
        attrs = product.get("attributes", {})
        return attrs.get(dim_name, "—")


def _determine_winner(
    dim_name: str,
    values: dict[str, str],
    products_map: dict[str, dict],
) -> str | None:
    """判断某维度的最优商品。无法判定时返回 None。"""
    if len(values) < 2:
        return None

    # 价格：越低越好
    if dim_name == "价格":
        best_pid = min(
            products_map.keys(),
            key=lambda pid: products_map[pid].get("price", float("inf")),
        )
        return best_pid

    # 评分：越高越好
    if dim_name == "评分":
        best_pid = max(
            products_map.keys(),
            key=lambda pid: products_map[pid].get("rating", 0),
        )
        return best_pid

    # 品牌：无法直接判定优劣
    if dim_name == "品牌":
        return None

    # 属性维度：尝试提取数值比较
    numeric_values: dict[str, float] = {}
    for pid, val in values.items():
        num = _extract_number(val)
        if num is not None:
            numeric_values[pid] = num

    if len(numeric_values) >= 2:
        # 对于重量、价格类属性，越小越好；其他越大越好
        lower_is_better_keys = {"重量", "响应时间", "延迟"}
        if dim_name in lower_is_better_keys:
            return min(numeric_values, key=numeric_values.get)
        else:
            return max(numeric_values, key=numeric_values.get)

    return None


def _extract_number(text: str) -> float | None:
    """从文本中提取数值（如 '30小时' → 30.0, '¥2499' → 2499.0）"""
    import re
    # 去掉 ¥ 符号和逗号
    cleaned = text.replace("¥", "").replace(",", "").replace("，", "")
    match = re.search(r"(\d+\.?\d*)", cleaned)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


# ── PostgreSQL 检索 ────────────────────────────────────────

async def _fetch_products_from_db(product_ids: list[str]) -> list[dict]:
    """按 product_id 从 PostgreSQL 检索商品详情"""
    if AsyncSessionLocal is None:
        logger.warning("Database not configured, returning empty results")
        return []

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT source_product_id, title, category, brand, price, rating,
                       highlights, scenarios, attributes, image_urls
                FROM products
                WHERE source_product_id = ANY(:ids)
            """),
            {"ids": product_ids},
        )
        rows = result.fetchall()

    products = []
    for row in rows:
        image_urls = list(row.image_urls or [])
        products.append({
            "product_id": row.source_product_id or "",
            "title": row.title or "",
            "category": row.category or "",
            "brand": row.brand or "",
            "price": float(row.price or 0),
            "rating": float(row.rating or 0),
            "rating_count": 0,
            "attributes": dict(row.attributes or {}),
            "highlights": list(row.highlights or []),
            "scenarios": list(row.scenarios or []),
            "image_urls": image_urls,
        })

    logger.info("Fetched %d/%d products from PostgreSQL", len(products), len(product_ids))
    return products


# Backward-compatible alias
_fetch_products_from_qdrant = _fetch_products_from_db


# ── LLM 总结生成 ──────────────────────────────────────────

_COMPARISON_SYSTEM_PROMPT = (
    "你是一个专业的电商导购助手。请根据以下商品对比数据，生成一段简洁的对比总结。"
    "总结应包含：\n"
    "1. 各商品的核心差异\n"
    "2. 每个商品的适用人群/场景\n"
    "3. 综合推荐意见\n"
    "用纯文本中文回复，控制在 200 字以内。不要使用 markdown 格式（如 **、##、- 等标记），"
    "不要输出代码块或表格。直接给出自然语句结论。"
)


def _build_comparison_table(
    dimensions: list[dict],
    products_map: dict[str, dict],
) -> str:
    """构建供 LLM 阅读的对比文本（纯文本格式，无 markdown）"""
    lines = ["商品对比表"]
    for p in products_map.values():
        highlights = " / ".join(p.get("highlights", [])[:3])
        lines.append(
            f"• [{p['title']}] ({p['brand']}) "
            f"¥{p['price']} | {p['rating']}★"
            + (f" | 亮点: {highlights}" if highlights else "")
        )

    lines.append("\n维度对比")
    for dim in dimensions:
        lines.append(f"\n▎{dim['name']}")
        for pid, val in dim["values"].items():
            product = products_map.get(pid, {})
            marker = " 最佳" if dim.get("winner") == pid else ""
            title = product.get("title", pid)
            # 截短产品名
            if len(title) > 30:
                for sep in ("（", "(", "，", ","):
                    pos = title.find(sep)
                    if 6 < pos < 30:
                        title = title[:pos]
                        break
                else:
                    title = title[:28] + "…"
            lines.append(f"  {title}: {val}{marker}")

    return "\n".join(lines)


async def _generate_summary(
    dimensions: list[dict],
    products_map: dict[str, dict],
) -> str:
    """调用 LLM 生成对比总结"""
    table = _build_comparison_table(dimensions, products_map)

    messages = [
        {"role": "system", "content": _COMPARISON_SYSTEM_PROMPT},
        {"role": "user", "content": f"请分析以下商品对比数据并给出总结：\n\n{table}"},
    ]

    try:
        summary = await chat_completion(
            messages=messages,
            temperature=0.5,
            max_tokens=512,
        )
        return summary.strip()
    except Exception as e:
        logger.error("LLM summary generation failed: %s", e)
        return _fallback_summary(dimensions, products_map)


def _fallback_summary(
    dimensions: list[dict],
    products_map: dict[str, dict],
) -> str:
    """LLM 不可用时的兜底总结"""
    products = list(products_map.values())
    if not products:
        return "暂无商品数据"

    titles = "、".join(p["title"][:12] for p in products)
    cheapest = min(products, key=lambda p: p["price"])
    highest_rated = max(products, key=lambda p: p["rating"])

    parts = [f"对比了 {len(products)} 款商品：{titles}。"]
    parts.append(
        f"价格最低的是 {cheapest['title']}（¥{cheapest['price']}），"
        f"评分最高的是 {highest_rated['title']}（{highest_rated['rating']}★）。"
    )

    # 统计各维度 winner
    winners = {}
    for dim in dimensions:
        w = dim.get("winner")
        if w and w in products_map:
            name = products_map[w]["title"][:10]
            winners[w] = winners.get(w, [])
            winners[w].append(dim["name"])

    if winners:
        for pid, dims in winners.items():
            name = products_map[pid]["title"][:10]
            parts.append(f"{name} 在 {', '.join(dims)} 方面表现最优。")

    parts.append("建议根据个人需求和预算选择。")
    return "".join(parts)


# ── 主入口 ────────────────────────────────────────────────

async def compare_products(
    product_ids: list[str],
    dimensions: list[str] | None = None,
) -> dict:
    """
    多商品横向对比

    Args:
        product_ids: 要对比的商品 ID 列表
        dimensions: 对比维度，None 则自动推断

    Returns:
        {dimensions: [{name, values, winner}, ...], summary: str}
    """
    # 1. 从 PostgreSQL 获取商品
    products = await _fetch_products_from_db(product_ids)

    if not products:
        return {
            "dimensions": [],
            "summary": "未找到指定的商品，请检查商品 ID 是否正确。",
        }

    # 检查缺失的商品
    found_ids = {p["product_id"] for p in products}
    missing_ids = set(product_ids) - found_ids
    if missing_ids:
        logger.warning("Missing products: %s", missing_ids)

    products_map = {p["product_id"]: p for p in products}

    # 2. 确定对比维度
    if dimensions is None:
        dimensions = _auto_dimensions(products)

    # 3. 构建维度结果
    dim_results = []
    for dim_name in dimensions:
        values = {}
        for pid in product_ids:
            if pid in products_map:
                values[pid] = _dimension_value(products_map[pid], dim_name)
            else:
                values[pid] = "商品不存在"

        winner = _determine_winner(dim_name, values, products_map)
        dim_results.append({
            "name": dim_name,
            "values": values,
            "winner": winner,
        })

    # 4. 生成 LLM 总结
    summary = await _generate_summary(dim_results, products_map)

    return {
        "dimensions": dim_results,
        "summary": summary,
    }
