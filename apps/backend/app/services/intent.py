"""
意图识别 + 槽位填充 + 查询改写 — fast LLM (DeepSeek) + 关键词回退
"""
import json
import logging
import re
from enum import Enum
from app.services.llm_client import fast_chat_completion
from app.services.exclusion_rules import expand_exclude_brands, expand_exclude_text_terms

logger = logging.getLogger("intent")


def _clean_json(raw: str) -> str:
    """清洗 LLM 输出的 JSON，处理 markdown 代码块、额外文本等"""
    raw = raw.strip()
    # 去除 markdown 代码块
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1] if "\n" in raw else raw[3:]
        if raw.rstrip().endswith("```"):
            raw = raw.rsplit("\n```", 1)[0] if "\n```" in raw else raw[:-3]
    # 去除 "json" 语言标识
    if raw.startswith("json\n"):
        raw = raw[5:]
    raw = raw.strip()
    # 找到第一个 { 和最后一个 }
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start:end+1]
    # 修复常见 LLM 错误：末尾多余逗号
    raw = re.sub(r',\s*}', '}', raw)
    raw = re.sub(r',\s*]', ']', raw)
    return raw


class IntentType(str, Enum):
    RECOMMEND = "commodity_recommend"
    COMPARE = "commodity_compare"
    DETAIL = "commodity_detail"
    SCENARIO = "scenario_shopping"
    AFTERSALE = "after_sales"
    CHITCHAT = "chitchat"
    ANTI_SELECTION = "anti_selection"  # 反选/排除场景（场景4）
    CART = "cart_operation"  # 购物车操作（场景6）
    IMAGE_SEARCH = "image_search"  # 拍照找货（场景7）
    WEB_SEARCH = "web_search"  # 联网搜索（外部信息查询）


INTENT_CLASSIFY_PROMPT = """你是一个电商导购意图分类器。分析用户输入，输出JSON。

**核心原则**：只要用户表达了购买意愿或商品检索需求，无论是否有"推荐"二字，都应归类为 commodity_recommend。
仅有明确询问外部信息（时效性/新闻/趋势/评测网站）的才归 web_search。

意图类型（10选1）：
- commodity_recommend: 推荐/寻找/筛选商品。含价格/品牌/品类/属性限定词即属此类。
  例子："推荐降噪耳机"、"3000元以下的手表"、"华为手机"、"500以内蓝牙耳机"、"降噪耳机哪个牌子好"、"3000以内"
- commodity_compare: 对比商品（"XM5和QC45哪个好"、"iPhone和华为怎么选"）
- commodity_detail: 了解商品参数/详情（"这款降噪多少分贝"）
- scenario_shopping: 场景化购物（"送女朋友礼物"、"北方冬天通勤鞋"）
- after_sales: 售后/保修/退换（"保修多久"、"支持7天无理由吗"）
- chitchat: 闲聊/问候/无关话题（"你好"、"谢谢"）
- anti_selection: 反选/排除条件（"不要含酒精的"、"除了日系品牌"、"讨厌苹果手机"、"不喜欢入耳式耳机"）
- cart_operation: 购物车操作（"加入购物车"、"查看购物车"、"下单"）
- image_search: 拍照找货/图片搜索（"这个是什么"）
- web_search: 联网搜索/外部信息查询。仅限询问时效信息、新闻、流行趋势、评测网站。
  例子："最近有什么新手机"、"2025年流行什么穿搭"、"网上说XX怎么样"、"今年双11什么时候"

用户输入：{query}{context}

仅输出JSON（不要markdown代码块）：
{{"intent": "commodity_recommend", "confidence": 0.92}}"""


SLOT_EXTRACT_PROMPT = """从用户输入中提取购物结构化信息。未知填null。

用户输入：{query}
意图：{intent}

输出JSON（不要markdown代码块）：
{{
  "category": "品类" or null,
  "price_min": 数字 or null,
  "price_max": 数字 or null,
  "brand_preference": "品牌" or null,
  "attributes": {{"属性名":"属性值"}} or {{}},
  "scenario": "场景" or null,
  "missing_slots": ["缺少的关键信息"]
}}"""


QUERY_REWRITE_PROMPT = """将用户口语化查询改写为适合向量检索的结构化查询。保留所有关键信息，去掉语气词。

用户输入：{query}
槽位信息：{slots}

只输出改写后的查询文本（一行纯文本，不要JSON）。"""


NEGATION_EXTRACT_PROMPT = """从用户输入中提取否定/排除条件。用户明确表示"不要"、"除了"、"非"、"不含"、"讨厌"、"不喜欢"、"反感"的内容。

用户输入：{query}

输出JSON（不要markdown代码块）：
{{
  "exclude_brands": ["排除的品牌"] or [],
  "exclude_categories": ["排除的品类"] or [],
  "exclude_attributes": {{"属性名":"排除的属性值"}} or {{}},
  "positive_query": "去掉否定词后的正向查询意图"
}}"""


async def classify_intent(query: str, context: str = "") -> dict:
    """
    Fast LLM-based 意图分类 (DeepSeek, ~0.5s)。
    返回 {"intent": "commodity_recommend", "confidence": 0.92}
    context: 多轮对话上文，用于理解省略表达（如"要轻量的"）
    LLM失败时回退到关键词规则。
    """
    try:
        ctx_hint = ""
        if context:
            ctx_hint = f"\n对话上文：{context}\n请结合上文理解当前查询的意图。省略表达应继承上文的意图类型。"
        prompt = INTENT_CLASSIFY_PROMPT.format(query=query, context=ctx_hint)
        raw = await fast_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=100,
        )
        raw = _clean_json(raw)
        result = json.loads(raw)
        intent = result.get("intent", "commodity_recommend")
        confidence = float(result.get("confidence", 0.5))
        keyword = _keyword_classify(query)
        if intent == "chitchat" and keyword.get("intent") != "chitchat":
            logger.info("Intent guard: overriding chitchat -> %s for shopping query", keyword["intent"])
            intent = keyword["intent"]
            confidence = max(confidence, keyword.get("confidence", 0.5))
        elif any(kw in query for kw in ["不要", "除了", "非", "不含", "排除", "去掉"]):
            if keyword.get("intent") == "anti_selection" and intent not in {"cart_operation", "web_search"}:
                intent = "anti_selection"
                confidence = max(confidence, 0.7)
        logger.info("Intent: %s (confidence=%.2f)", intent, confidence)
        return {"intent": intent, "confidence": confidence}
    except Exception as e:
        logger.warning("Fast LLM intent classify failed, fallback to keyword: %s", e)
        return _keyword_classify(query)


def _keyword_classify(query: str) -> dict:
    """关键词规则回退 + 短词品类检测"""
    q = query.lower()
    # Priority: most specific intents first, then generic
    # 1. 联网搜索 — 明确的外部信息查询
    if any(kw in q for kw in ["最新", "新闻", "趋势", "流行", "网上", "搜索", "查一下", "最近有什么", "现在什么"]):
        return {"intent": "web_search", "confidence": 0.7}
    # 2. 明确闲聊词 — 最短最明确
    if any(kw in q for kw in ["你好", "谢谢", "天气", "再见", "哈哈", "呵呵"]):
        return {"intent": "chitchat", "confidence": 0.9}
    # 2. 购物车操作 — 非常具体的关键词
    if any(kw in q for kw in ["购物车", "加购", "加入购物车", "下单", "结算", "清空购物车", "我的购物车"]):
        return {"intent": "cart_operation", "confidence": 0.7}
    # 3. 售后
    if any(kw in q for kw in ["售后", "退货", "维修", "保修", "退换"]):
        return {"intent": "after_sales", "confidence": 0.6}
    # 4. 反选/排除
    if any(kw in q for kw in ["不要", "除了", "非", "不含", "排除", "去掉", "讨厌", "不喜欢", "反感"]):
        return {"intent": "anti_selection", "confidence": 0.7}
    # 5. 对比
    if any(kw in q for kw in ["对比", "比较", "区别", "哪个好", "怎么选"]):
        return {"intent": "commodity_compare", "confidence": 0.6}
    # 6. 场景购物 — 送礼/场景/生活方式关键词
    if any(kw in q for kw in [
        "送", "礼物", "生日", "节日", "场合", "场景",
        "度假", "旅行", "旅游", "出差", "通勤", "露营", "户外",
        "穿搭", "方案", "装备", "全套", "搭配",
    ]):
        return {"intent": "scenario_shopping", "confidence": 0.6}
    # 7. 推荐 — 明确购物意图动词（需在 detail 之前，因为 "推荐降噪耳机" 主体是推荐）
    if any(kw in q for kw in ["推荐", "建议", "想买", "想搞", "整一个", "买个"]):
        return {"intent": "commodity_recommend", "confidence": 0.6}
    # 7b. 价格/品牌/属性的购物意图 — "3000元以下"、"华为手机"、"降噪耳机"
    _price_brand_recommend = [
        r'\d+元', r'\d+块', r'以下', r'以内', r'以上', r'左右',
        '买', '购', '哪个好', '怎么选', '什么牌子',
    ]
    if any(re.search(kw, q) if kw.startswith(r'\d') else kw in q for kw in _price_brand_recommend):
        return {"intent": "commodity_recommend", "confidence": 0.55}
    # 8. 商品详情 — 参数/属性询问
    if any(kw in q for kw in ["多少", "参数", "配置", "续航", "降噪", "重量", "尺寸"]):
        return {"intent": "commodity_detail", "confidence": 0.6}
    # 9. 模糊购买意图 — "买", "购" 单独出现（避免误杀购物车）
    if any(kw in q for kw in ["买", "购"]):
        return {"intent": "commodity_recommend", "confidence": 0.5}
    # 10. 短词/单字可能是品类关键词 → 视为推荐意图
    return {"intent": "commodity_recommend", "confidence": 0.45}


async def extract_slots(query: str, intent: str) -> dict:
    """
    Fast LLM-based 槽位填充 (DeepSeek, ~0.5s)。
    返回 {"category": "耳机", "price_max": 3000, ...}
    """
    try:
        prompt = SLOT_EXTRACT_PROMPT.format(query=query, intent=intent)
        raw = await fast_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
        )
        raw = _clean_json(raw)
        result = json.loads(raw)
        logger.info("Slots: category=%s, price=%s-%s",
                    result.get("category"), result.get("price_min"), result.get("price_max"))
        return result
    except Exception as e:
        logger.warning("Fast LLM slot extract failed: %s", e)
        return {"category": None, "price_min": None, "price_max": None,
                "brand_preference": None, "attributes": {}, "scenario": None, "missing_slots": []}


async def extract_negation_slots(query: str) -> dict:
    """
    Fast LLM-based 否定条件提取 (DeepSeek, ~0.5s)。
    返回 {"exclude_brands": [], "exclude_categories": [], "exclude_attributes": {}, "positive_query": "..."}
    """
    try:
        prompt = NEGATION_EXTRACT_PROMPT.format(query=query)
        raw = await fast_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
        )
        raw = _clean_json(raw)
        result = json.loads(raw)
        logger.info("Negation slots: exclude_brands=%s, exclude_attrs=%s",
                    result.get("exclude_brands"), result.get("exclude_attributes"))
        return result
    except Exception as e:
        logger.warning("Fast LLM negation extract failed: %s", e)
        return _keyword_extract_negation(query)


def _keyword_extract_negation(query: str) -> dict:
    """关键词规则提取否定条件（回退） + 常见属性值映射"""
    exclude_brands = []
    exclude_categories = []
    exclude_attributes = {}
    exclude_text_terms = []  # 文本级排除词（用于 title/highlights 模糊匹配）

    # ── 常见属性值 → 属性名映射 ──
    ATTR_VALUE_MAP = {
        "骨传导": ("类型", "骨传导"),
        "入耳式": ("类型", "入耳式"),
        "入耳": ("类型", "入耳式"),
        "头戴式": ("类型", "头戴式"),
        "头戴": ("类型", "头戴式"),
        "挂耳式": ("类型", "挂耳式"),
        "耳夹式": ("类型", "耳夹式"),
        "开放式": ("类型", "开放式"),
        "半入耳": ("类型", "半入耳式"),
        "无线": ("连接方式", "无线"),
        "有线": ("连接方式", "有线"),
        "蓝牙": ("连接方式", "蓝牙"),
        "降噪": ("降噪", "主动降噪"),
        "白色": ("颜色", "白色"),
        "黑色": ("颜色", "黑色"),
        "日系": ("brand", "日系"),
        "日本": ("brand", "日本"),
        "日牌": ("brand", "日牌"),
        "酒精": ("文本", "酒精"),
        "含酒精": ("文本", "酒精"),
        "乙醇": ("文本", "乙醇"),
        "苹果": ("brand", "Apple"),
        "华为": ("brand", "Huawei"),
        "小米": ("brand", "Xiaomi"),
        "三星": ("brand", "Samsung"),
    }

    # 提取 "不要XX" / "非XX" / "除了XX" 模式
    neg_pattern = r'(?:不要|非|不含|排除|拒绝|去掉|避开|别要|别买|讨厌|不喜欢|反感)\s*(.{1,8}?)(?:的|了|啊|吧|哈|嘛|哦|，|。|,|\s|$|耳机|手机|电脑|手表|平板)'
    for m in re.finditer(neg_pattern, query):
        term = m.group(1).strip()
        if not term or len(term) < 1:
            continue

        # 检查是否匹配已知属性值
        matched = False
        for known_val, (attr_key, attr_val) in ATTR_VALUE_MAP.items():
            if known_val in term or term in known_val:
                if attr_key == "brand":
                    exclude_brands.append(attr_val)
                elif attr_key == "文本":
                    exclude_text_terms.append(attr_val)
                else:
                    exclude_attributes[attr_key] = attr_val
                matched = True
                break

        # 检查是否是品牌名
        if not matched and len(term) >= 2:
            # 可能是品牌名或品类名
            exclude_brands.append(term)

        # 同时加入文本级排除（兜底）
        if term and len(term) >= 2:
            exclude_text_terms.append(term)
            # 额外添加短词变体：如 "入耳式" → 也加 "入耳"；英文品牌不做前缀拆分，避免 vivo → vi/viv 误伤。
            if len(term) >= 3 and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]*", term):
                for i in range(2, len(term)):
                    sub = term[:i]
                    if sub not in exclude_text_terms and sub not in ["不要", "除了", "非", "不含", "排除"]:
                        exclude_text_terms.append(sub)

    # 提取 "除了XX品牌/品类"
    except_pattern = r'除了\s*(.{1,10}?)(?:品牌|牌子|品类|类|系|的|，|,|\s|$)'
    for m in re.finditer(except_pattern, query):
        term = m.group(1).strip()
        if term:
            exclude_brands.append(term)
            exclude_text_terms.append(term)

    # 构建正向查询（去掉否定部分）
    positive = query
    for marker in ["不要", "除了", "非", "不含", "排除", "拒绝", "去掉", "避开", "别要", "别买", "讨厌", "不喜欢", "反感"]:
        if marker in positive:
            idx = positive.find(marker)
            if idx == -1:
                continue
            # 找到否定部分结束位置（逗号/句号/空格 或 最多取10字）
            after = positive[idx:]
            end = len(after)
            for sep in ["，", ",", "。", ".", " ", "\n"]:
                pos = after.find(sep, len(marker))
                if 0 < pos < end:
                    end = pos
                    break
            if end > 20:
                end = min(len(marker) + 12, len(after))
            positive = positive[:idx] + positive[idx+end:]

    positive = positive.strip("，,。. ")

    return {
        "exclude_brands": expand_exclude_brands(list(set(exclude_brands))),
        "exclude_categories": exclude_categories,
        "exclude_attributes": exclude_attributes,
        "exclude_text_terms": expand_exclude_text_terms(exclude_text_terms),
        "positive_query": positive or query,
    }


async def rewrite_query(query: str, slots: dict) -> str:
    """
    Fast LLM-based 查询改写 (DeepSeek, ~0.5s)：口语 → 结构化检索语句。
    """
    try:
        prompt = QUERY_REWRITE_PROMPT.format(query=query, slots=json.dumps(slots, ensure_ascii=False))
        rewritten = await fast_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=150,
        )
        rewritten = rewritten.strip().strip('"').strip("'")
        if rewritten and rewritten != query:
            logger.info("Query rewritten: '%s' → '%s'", query[:40], rewritten[:60])
            return rewritten
    except Exception as e:
        logger.warning("Fast LLM query rewrite failed: %s", e)
    return query
