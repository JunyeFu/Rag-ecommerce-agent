"""
Product comparison node - multi-product comparison with backref resolution.

Extracted from agent.py.
"""
import re
import logging

from app.services.agent_state import AgentState
from app.services.product_assembly import _extract_raw_products, _build_user_prefs, _shorten_product_name

logger = logging.getLogger("agent")


async def _resolve_compare_targets(query: str, conversation_id: str, history: list) -> list[str] | None:
    """检测回指：用户是否引用了上一轮推荐中的某几款商品进行对比。

    支持模式：
    - "对比前两款"、"比较前两个" -> 取前2个
    - "对比第1和第3款"、"比较第2个和第3个" -> 取指定索引
    - "对比这两款"、"比较那俩" -> 取前2个（从上一轮）
    - "对比XM5和QC45" -> 不处理（名称匹配走检索），返回None
    """
    if not history or len(history) < 2:
        return None

    q = query.strip()

    # 检测回指关键词
    backref_keywords = ["前两", "前2", "前二", "这两", "那两", "前几", "这俩", "那俩",
                        "第一款", "第二款", "第三款", "第1款", "第2款", "第3款",
                        "第.和第", "第.跟第", "第.与第",
                        "上面", "刚才", "刚刚", "前面推荐"]

    has_backref = any(kw in q for kw in backref_keywords)

    # 也匹配 "对比第1和第3" 这种数字模式
    index_pattern = re.findall(r'第\s*(\d+)\s*(?:款|个)', q)
    if not has_backref and not index_pattern:
        return None

    # 从状态管理器获取上一轮 product_cards
    from app.services import state_manager as sm
    prev_state = await sm.get_state(conversation_id)
    prev_cards = prev_state.get("product_cards", []) if prev_state else []

    if not prev_cards or len(prev_cards) < 2:
        logger.info("Compare backref: no previous product_cards to resolve from")
        return None

    logger.info("Compare backref: query='%s', prev_cards=%d", q[:40], len(prev_cards))

    # 提取用户指定的索引
    if index_pattern:
        indices = [int(i) - 1 for i in index_pattern]  # 转为0-based
    elif any(kw in q for kw in ["前两", "前2", "前二", "这两", "那两", "这俩", "那俩"]):
        indices = [0, 1]  # 默认前2款
    else:
        indices = [0, 1]  # 兜底：前2款

    # 过滤有效索引
    valid_indices = [i for i in indices if 0 <= i < len(prev_cards)]
    if len(valid_indices) < 2:
        return None

    target_ids = [prev_cards[i].get("product_id", "") for i in valid_indices]
    target_ids = [pid for pid in target_ids if pid]

    if len(target_ids) >= 2:
        logger.info("Compare backref resolved: indices=%s -> ids=%s", valid_indices, target_ids)
        return target_ids

    return None


def _detect_compare_brands(query: str, products: list[dict]) -> list[str]:
    """从查询中检测用户明确提到的品牌，返回匹配到的品牌名列表（按查询中出现顺序）。

    例如 "对比华为和Apple手机" -> ["Huawei", "Apple"]（匹配 products 中实际品牌名）
    未检测到明确品牌时返回空列表。
    """
    # 从 products 中收集已知品牌（用于大小写/中英文映射）
    known_brands = {}
    for p in products:
        b = (p.get("brand") or "").strip()
        if b:
            known_brands[b.lower()] = b

    if len(known_brands) < 2:
        return []

    # 构建品牌名关键词列表，按长度降序避免短词误匹配（如 "小米" 不应仅匹配 "米"）
    brand_keys = sorted(known_brands.keys(), key=len, reverse=True)

    # 在 query 中查找品牌名出现的位置和对应的标准品牌名
    found: list[tuple[int, str]] = []  # (position, canonical_brand)
    q_lower = query.lower()

    for key in brand_keys:
        pos = q_lower.find(key)
        if pos >= 0:
            # 排除品牌名是常见词的误匹配（如 "小米" 不在 "对比" 中）
            found.append((pos, known_brands[key]))

    # 按位置排序，去重
    found.sort()
    result = []
    seen = set()
    for _, brand in found:
        if brand.lower() not in seen:
            result.append(brand)
            seen.add(brand.lower())

    return result[:3]  # 最多3个品牌


async def node_compare(state: AgentState) -> AgentState:
    """商品对比节点 - 从检索结果中取 top 2-3 商品，调用 comparator 生成多维度对比。
    支持 _target_product_ids 跳过检索直接对比指定商品。
    """
    from app.services.comparator import compare_products as run_comparison
    from app.services.product_ranker import rank_products

    query = state.get("rewritten_query") or state.get("query", "")
    slots = state.get("slots", {})
    target_product_ids = state.get("_target_product_ids", [])
    chunks = state.get("retrieved_chunks", [])

    # 使用已解析的目标商品 ID（来自回指解析）或从检索结果中取 top-N
    if target_product_ids and len(target_product_ids) >= 2:
        product_ids = target_product_ids
        # 从缓存/检索结果中获取商品详情
        raw_products = _extract_raw_products(chunks) if chunks else []
        if not raw_products:
            # 需要从 PostgreSQL fetch 这些产品的 payload
            from app.services.comparator import _fetch_products_from_db
            raw_products = await _fetch_products_from_db(product_ids)
        ranked = list(raw_products)  # 保持原始顺序
        logger.info("node_compare: using resolved target IDs: %s", product_ids)
    else:
        if not chunks:
            logger.warning("node_compare: no retrieved chunks, falling back to text-only")
            state["response"] = "抱歉，没有找到可对比的商品，试试更具体的商品名称吧。"
            state["product_cards"] = []
            return state

        raw_products = _extract_raw_products(chunks)
        user_prefs = _build_user_prefs(slots)
        ranked = rank_products(raw_products, user_prefs, "commodity_compare", top_k=3)

        if len(ranked) < 2:
            state["response"] = "需要至少 2 个商品才能进行对比。试试提供更具体的商品名称。"
            state["product_cards"] = []
            return state

        # 用户明确提了N个品牌 -> 每个品牌只取最优的1款，避免多选
        query_brands = _detect_compare_brands(query, ranked)
        if query_brands and len(query_brands) == 2:
            brand_picks = []
            for brand in query_brands:
                match = next((r for r in ranked if (r.get("brand") or "").lower() == brand.lower()), None)
                if match:
                    brand_picks.append(match)
            if len(brand_picks) == 2:
                ranked = brand_picks
                logger.info("node_compare: brand-filtered to 2: %s", [r.get("brand") for r in ranked])

        product_ids = [r["product_id"] for r in ranked]

    logger.info("node_compare: comparing %d products: %s", len(product_ids), product_ids)

    try:
        comparison = await run_comparison(product_ids=product_ids, dimensions=None)
    except Exception as e:
        logger.error("node_compare: comparison failed: %s", e)
        state["response"] = "对比分析暂时不可用，请稍后再试。"
        state["product_cards"] = []
        return state

    # 构建对比文本（无 markdown，纯文本格式）
    dims = comparison.get("dimensions", [])
    summary = comparison.get("summary", "")

    # 构建 products_map：优先用 ranked，否则从 raw_products 构建
    if not target_product_ids:
        products_map = {r["product_id"]: r for r in ranked}
    else:
        products_map = {p.get("product_id", ""): p for p in raw_products}

    lines = ["📊 商品对比"]
    for dim in dims:
        dim_name = dim['name']
        lines.append(f"\n▎{dim_name}")
        for pid, val in dim.get("values", {}).items():
            product = products_map.get(pid, {})
            name = product.get("title", pid)
            # 截短产品名以提高可读性
            short_name = _shorten_product_name(name)
            marker = " 🏆" if dim.get("winner") == pid else ""
            lines.append(f"  {short_name}: {val}{marker}")

    if summary:
        lines.append(f"\n💡 {summary}")

    response_text = "\n".join(lines)
    state["response"] = response_text

    # 构建 product_cards 供客户端展示
    cards = []
    products_for_cards = ranked if not target_product_ids else raw_products
    for i, p in enumerate(products_for_cards):
        if isinstance(p, str):
            # 原始 product_id，从 products_map 取
            p = products_map.get(p, {})
        cards.append({
            "product_id": p.get("product_id", ""),
            "title": p.get("title", ""),
            "price": float(p.get("price", 0)),
            "rating": float(p.get("rating", 3.0)),
            "highlights": (p.get("highlights") or [])[:3] if isinstance(p.get("highlights"), list) else [],
            "image_url": (p.get("image_urls") or [None])[0] if p.get("image_urls") else None,
            "image_urls": p.get("image_urls") if isinstance(p.get("image_urls"), list) else [],
            "brand": p.get("brand", ""),
            "category": p.get("category", ""),
        })
    state["product_cards"] = cards
    state["_comparison_dims"] = dims  # 暂存维度数据，供 SSE 发射

    return state
