"""
商品对比 - 纯工具函数
"""
import re


def _extract_number(text: str) -> float | None:
    """从文本中提取数值（如 '30小时' -> 30.0, '¥2499' -> 2499.0）"""
    # 去掉 ¥ 符号和逗号
    cleaned = text.replace("¥", "").replace(",", "").replace("，", "")
    match = re.search(r"(\d+\.?\d*)", cleaned)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


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
