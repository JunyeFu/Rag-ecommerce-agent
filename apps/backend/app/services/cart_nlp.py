"""
Cart NLP parsing - regex-based cart action extraction and product resolution.

Extracted from agent.py.
"""
import re
import logging

from app.services import cart_service
from app.services.agent_state import AgentState

logger = logging.getLogger("agent")


def _extract_cart_action(query: str) -> str:
    """从用户查询中提取购物车操作类型"""
    q = query.lower()
    if any(kw in q for kw in ["加入购物车", "加到购物车", "加购", "放入购物车", "拍下"]):
        return "add"
    if any(kw in q for kw in ["剩下", "其余", "余下", "剩余"]) and any(kw in q for kw in ["买", "购买", "加入"]):
        return "add"
    quantity_patterns = [
        r"(?:数量|数目|件数|个数)",
        r"(?:改成|改为|设为|设置为|调整为|调为|调到|改到|变成)\s*[0-9一二两三四五六七八九十]",
        r"(?:买|要|来)\s*[0-9一二两三四五六七八九十]+\s*(?:件|个|台|本|双|套|份)",
        r"(?:加|增加|再加|多买|减|减少|少买|去掉)\s*[0-9一二两三四五六七八九十]+\s*(?:件|个|台|本|双|套|份)",
        r"(?:加|增加|再加|多买|减|减少|少买|去掉).{0,6}?(?:到|为|成)\s*[0-9一二两三四五六七八九十]+\s*(?:件|个|台|本|双|套|份)",
    ]
    if any(re.search(pattern, q) for pattern in quantity_patterns):
        return "quantity"
    if any(kw in q for kw in ["清空", "全部删除", "全部移除"]):
        return "clear"
    if any(kw in q for kw in ["下单", "结算", "结账", "支付", "买单", "确认下单"]):
        return "checkout"
    if any(kw in q for kw in ["删除", "移除", "去掉", "不要第"]):
        return "remove"
    if any(kw in q for kw in ["查看", "看看", "显示", "我的购物车", "购物车里有"]):
        return "view"
    if any(kw in q for kw in ["加入", "加购", "加到", "添加", "放入", "加一个", "加第"]):
        return "add"
    return "view"  # 默认查看


def _parse_quantity(query: str) -> int | None:
    """解析"设置为 N 件"类绝对数量。"""
    clear_match = re.search(
        r"(?:买|要|来|加购|加入|放入|加到|拍)\s*([0-9]+|[一二两三四五六七八九十]+)\s*(?:件|个|台|只|双|套|份)",
        query,
        re.I,
    )
    if clear_match:
        return _quantity_token_to_int(clear_match.group(1))

    patterns = [
        r"(?:数量|数目|件数|个数).{0,8}?(?:改成|改为|设为|设置为|调整为|调为|调到|改到|变成|到|为)?\s*([0-9]+|[一二两三四五六七八九十]+)",
        r"(?:改成|改为|设为|设置为|调整为|调为|调到|改到|变成)\s*([0-9]+|[一二两三四五六七八九十]+)",
        r"(?:减|减少|少买|加|增加|多买).{0,6}?(?:到|为|成)\s*([0-9]+|[一二两三四五六七八九十]+)\s*(?:件|个|台|本|双|套|份)",
        r"(?:买|要|来)\s*([0-9]+|[一二两三四五六七八九十]+)\s*(?:件|个|台|本|双|套|份)",
    ]
    for pattern in patterns:
        match = re.search(pattern, query, re.I)
        if match:
            return _quantity_token_to_int(match.group(1))

    for match in re.finditer(r"([0-9]+|[一二两三四五六七八九十]+)\s*(?:件|个|台|本|双|套|份)", query, re.I):
        if match.start() > 0 and query[match.start() - 1] == "第":
            continue
        return _quantity_token_to_int(match.group(1))

    return None


def _parse_quantity_delta(query: str) -> int | None:
    """解析"加一件/减两件"类相对数量。"""
    match = re.search(
        r"(?:加|增加|再加|多买)\s*([0-9]+|[一二两三四五六七八九十]+)\s*(?:件|个|台|本|双|套|份)",
        query,
        re.I,
    )
    if match:
        return _quantity_token_to_int(match.group(1))

    match = re.search(
        r"(?:减|减少|少买|去掉)\s*([0-9]+|[一二两三四五六七八九十]+)\s*(?:件|个|台|本|双|套|份)",
        query,
        re.I,
    )
    if match:
        value = _quantity_token_to_int(match.group(1))
        return -value if value is not None else None

    return None


def _quantity_token_to_int(raw: str) -> int | None:
    clear_cn_nums = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if raw in clear_cn_nums:
        return clear_cn_nums[raw]
    if raw == "十":
        return 10
    if raw.startswith("十") and len(raw) == 2:
        return 10 + clear_cn_nums.get(raw[1], 0)
    if raw.endswith("十") and len(raw) == 2:
        return clear_cn_nums.get(raw[0], 0) * 10
    if "十" in raw and len(raw) == 3:
        return clear_cn_nums.get(raw[0], 0) * 10 + clear_cn_nums.get(raw[2], 0)
    if raw.isdigit():
        return max(0, int(raw))
    cn_nums = {
        "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
        "六": 6, "七": 7, "八": 8, "九": 9,
    }
    if raw == "十":
        return 10
    if raw.startswith("十") and len(raw) == 2:
        return 10 + cn_nums.get(raw[1], 0)
    if raw.endswith("十") and len(raw) == 2:
        return cn_nums.get(raw[0], 0) * 10
    if "十" in raw and len(raw) == 3:
        return cn_nums.get(raw[0], 0) * 10 + cn_nums.get(raw[2], 0)
    return cn_nums.get(raw)


def _resolve_remaining_product_card(query: str, product_cards: list[dict]) -> dict | None:
    """Resolve fuzzy references like "排除前两个，剩下的那个加购"."""
    if not product_cards:
        return None
    remaining_markers = ("剩下", "其余", "余下", "剩余", "留下")
    exclude_markers = ("排除", "不要", "去掉", "剔除", "除了", "删掉")
    if not any(marker in query for marker in remaining_markers):
        return None
    if not any(marker in query for marker in exclude_markers):
        return product_cards[0] if len(product_cards) == 1 else None

    excluded: set[int] = set()
    if re.search(r"(前|头)\s*(?:2|二|两)\s*(?:个|件|款|项)?", query):
        excluded.update([0, 1])
    elif re.search(r"(前|头)\s*(?:3|三)\s*(?:个|件|款|项)?", query):
        excluded.update([0, 1, 2])
    elif re.search(r"(前|头)\s*(?:1|一)\s*(?:个|件|款|项)?", query):
        excluded.add(0)

    ordinal_map = {"一": 0, "1": 0, "二": 1, "两": 1, "2": 1, "三": 2, "3": 2, "四": 3, "4": 3, "五": 4, "5": 4}
    for token, idx in ordinal_map.items():
        if re.search(rf"(?:第\s*{re.escape(token)}|{re.escape(token)}\s*号)", query):
            excluded.add(idx)

    remaining = [card for idx, card in enumerate(product_cards) if idx not in excluded]
    return remaining[0] if len(remaining) == 1 else None


def _product_from_card(card: dict) -> dict:
    return {
        "id": str(card.get("product_id") or card.get("id", "")).strip(),
        "title": card.get("title", ""),
        "price": card.get("price", 0),
    }


def _get_cart_backref_cards(state: AgentState) -> list[dict]:
    product_cards = state.get("product_cards", []) or []
    slots = state.get("slots", {}) or {}
    prev_cards = slots.get("product_cards", []) or []
    return product_cards or prev_cards or []


def _find_products_for_multi_cart(query: str, state: AgentState) -> list[dict]:
    """Resolve multi-item cart commands such as "这两款都加入购物车" from current cards."""
    product_cards = _get_cart_backref_cards(state)
    if not product_cards:
        return []

    normalized = re.sub(r"\s+", "", query)
    indices, _indices_error = _extract_cart_item_indices(query, len(product_cards))
    if len(indices) >= 2:
        selected: list[dict] = []
        seen: set[str] = set()
        for idx in indices:
            card = product_cards[idx]
            product = _product_from_card(card)
            if product["id"] and product["id"] not in seen:
                seen.add(product["id"])
                selected.append(product)
        return selected

    multi_markers = ("都", "全部", "全都", "一起", "这两款", "这两个", "两款", "两个", "前两", "前三")
    if not any(marker in normalized for marker in multi_markers):
        return []

    limit = len(product_cards)
    if any(marker in normalized for marker in ("这两款", "这两个", "两款", "两个", "前两")):
        limit = min(2, len(product_cards))
    elif "前三" in normalized:
        limit = min(3, len(product_cards))

    selected: list[dict] = []
    seen: set[str] = set()
    for card in product_cards[:limit]:
        product = _product_from_card(card)
        if product["id"] and product["id"] not in seen:
            seen.add(product["id"])
            selected.append(product)
    return selected


def _cart_item_matches_query(item, query: str) -> bool:
    normalized_query = re.sub(r"\s+", "", query.lower())
    normalized_title = re.sub(r"\s+", "", (item.title or "").lower())
    brand = re.sub(r"\s+", "", (getattr(item, "brand", None) or "").lower())
    category = re.sub(r"\s+", "", (getattr(item, "category", None) or "").lower())

    if normalized_title and normalized_title[:4] in normalized_query:
        return True
    if brand and brand in normalized_query:
        return True
    if category and category in normalized_query:
        return True

    ignored = {
        "购物车", "里面", "里的", "商品", "数量", "改成", "改为", "设为", "设置为",
        "调整为", "调到", "改到", "变成", "买", "要", "来", "加", "减", "件", "个",
        "第一", "第二", "第三", "第四", "第五",
    }
    candidates = set()
    for part in re.findall(r"[\u4e00-\u9fff]{2,}", normalized_query):
        for length in range(min(6, len(part)), 1, -1):
            for start in range(0, len(part) - length + 1):
                token = part[start:start + length]
                if token not in ignored and not any(stop in token for stop in ignored):
                    candidates.add(token)
    candidates.update(re.findall(r"[a-z0-9]{2,}", normalized_query))

    return any(token in normalized_title for token in candidates)


def _extract_cart_item_index(query: str, item_count: int) -> tuple[int | None, str | None]:
    ordinal_map = {
        "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
        "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
    }
    match = re.search(r"第\s*([一二两三四五12345])\s*(?:个|件|项|款|样|种)?", query)
    if not match:
        match = re.search(r"([一二两三四五12345])\s*号", query)
    if not match:
        return None, None

    idx = ordinal_map.get(match.group(1))
    if idx is None:
        return None, None
    if idx > item_count:
        return None, f"购物车只有 {item_count} 件商品，没有第 {idx} 个。"
    return idx - 1, None


def _extract_cart_item_indices(query: str, item_count: int) -> tuple[list[int], str | None]:
    normalized = re.sub(r"\s+", "", query)
    if any(marker in normalized for marker in ("全部", "所有", "全都", "整车")):
        return list(range(item_count)), None

    if re.search(r"(?:前|头)(?:2|二|两)(?:个|件|款|项)?", normalized):
        if item_count < 2:
            return [], f"购物车只有 {item_count} 件商品，没有前 2 个。"
        return list(range(2)), None
    if re.search(r"(?:前|头)(?:3|三)(?:个|件|款|项)?", normalized):
        if item_count < 3:
            return [], f"购物车只有 {item_count} 件商品，没有前 3 个。"
        return list(range(3)), None

    ordinal_map = {
        "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
        "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
    }
    found: list[int] = []
    for token, number in ordinal_map.items():
        patterns = (
            rf"第{re.escape(token)}(?:个|件|项|款|样|种)?",
            rf"{re.escape(token)}号",
        )
        if any(re.search(pattern, normalized) for pattern in patterns):
            if number > item_count:
                return [], f"购物车只有 {item_count} 件商品，没有第 {number} 个。"
            found.append(number - 1)

    compact_ordinals = re.findall(r"第([一二两三四五12345]{2,})(?:个|件|项|款|样|种)?", normalized)
    for group in compact_ordinals:
        for char in group:
            number = ordinal_map.get(char)
            if number is None:
                continue
            if number > item_count:
                return [], f"购物车只有 {item_count} 件商品，没有第 {number} 个。"
            found.append(number - 1)

    deduped = sorted(set(found))
    return deduped, None


async def _find_product_for_cart(query: str, state: AgentState) -> dict | None:
    """从查询中识别用户要加购的商品。
    优先级：1. 序号匹配 product_cards  2. 商品名匹配 product_cards  3. PostgreSQL 搜索
    """
    product_cards = _get_cart_backref_cards(state)

    remaining_card = _resolve_remaining_product_card(query, product_cards)
    if remaining_card:
        return _product_from_card(remaining_card)

    # 1. 序号匹配: "第一个"、"第二个"、"第1个"
    ordinal_map = {
        "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
        "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
    }
    for word in sorted(ordinal_map.keys(), key=len, reverse=True):
        if word in query:
            idx = ordinal_map[word]
            if product_cards and idx <= len(product_cards):
                card = product_cards[idx - 1]
                return _product_from_card(card)

    # 2. 按商品名匹配 product_cards（标题前几个字出现在 query 中）
    if product_cards:
        for card in product_cards:
            title = card.get("title", "")
            if title and len(title) >= 3 and title[:4] in query:
                return _product_from_card(card)

    # 3. PostgreSQL 搜索：从 "加入购物车" 前的文本提取搜索词
    for marker in ["加入购物车", "加到购物车", "加购", "添加到购物车"]:
        if marker in query:
            prefix = query.split(marker)[0].strip()
            # 去掉 "把" "将" 等引导词
            for lead in ["把", "将", "这个", "这款", "那个"]:
                if prefix.startswith(lead):
                    prefix = prefix[len(lead):].strip()
            if prefix and len(prefix) >= 2:
                try:
                    from app.services.rag import retrieve as rag_retrieve
                    result = await rag_retrieve(query=prefix, top_k=1)
                    chunks = result.get("chunks", [])
                    if chunks:
                        p = chunks[0].get("payload", {})
                        pid = str(p.get("product_id", "")).strip()
                        if pid:
                            return {
                                "id": pid,
                                "title": p.get("title", ""),
                                "price": p.get("price", 0),
                            }
                except Exception as e:
                    logger.warning("Cart PostgreSQL fallback lookup failed: %s", e)
            break

    return None


async def _remove_from_cart(query: str, session_id: str, db, user_id: str = "") -> str:
    """从购物车中删除商品，按序号或名字匹配"""
    items = await cart_service.get_cart(db, session_id, user_id=user_id)
    if not items:
        return "购物车是空的，没有可删除的商品。"

    item_index, index_error = _extract_cart_item_index(query, len(items))
    if index_error:
        return index_error
    if item_index is not None:
        item = items[item_index]
        await cart_service.remove_from_cart(db, session_id, str(item.product_id), user_id=user_id)
        return f"✅ 已从购物车删除「{item.title}」。"

    # 2. 按商品名匹配
    for item in items:
        if _cart_item_matches_query(item, query):
            await cart_service.remove_from_cart(db, session_id, str(item.product_id), user_id=user_id)
            return f"✅ 已从购物车删除「{item.title}」。"

    return f"没有找到要删除的商品。当前购物车有 {len(items)} 件商品，请指定序号或商品名。"


async def _update_cart_quantity(query: str, session_id: str, db, user_id: str = "") -> str:
    """按序号或商品名修改购物车数量。"""
    quantity = _parse_quantity(query)
    quantity_delta = _parse_quantity_delta(query)
    if quantity_delta is not None:
        quantity = None
    if quantity is None and quantity_delta is None:
        return "请告诉我想改成几件，例如「把第一个数量改成 2」或「把蓝牙耳机加一件」。"

    items = await cart_service.get_cart(db, session_id, user_id=user_id)
    if not items:
        return "购物车是空的，暂时没有可修改数量的商品。"

    target_indices, indices_error = _extract_cart_item_indices(query, len(items))
    if indices_error:
        return indices_error
    targets = [items[idx] for idx in target_indices]

    if not targets:
        for item in items:
            if _cart_item_matches_query(item, query):
                targets = [item]
                break

    if not targets:
        return "没有找到要修改数量的商品，请指定序号或商品名。"

    changed: list[str] = []
    removed: list[str] = []
    for target in targets:
        new_quantity = quantity
        if new_quantity is None and quantity_delta is not None:
            new_quantity = max(0, target.quantity + quantity_delta)

        if new_quantity == 0:
            await cart_service.remove_from_cart(db, session_id, str(target.product_id), user_id=user_id)
            removed.append(target.title)
        else:
            await cart_service.update_quantity(db, session_id, str(target.product_id), new_quantity, user_id=user_id)
            changed.append(f"「{target.title}」数量改为 {new_quantity} 件")

    messages = []
    if changed:
        messages.append("已将" + "，".join(changed))
    if removed:
        messages.append("已将" + "、".join(f"「{title}」" for title in removed) + "从购物车移除")
    return "；".join(messages) + "。"
