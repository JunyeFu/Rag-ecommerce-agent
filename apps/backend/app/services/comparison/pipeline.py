"""
商品对比 - 流水线 (Template Method Pattern)
从 PostgreSQL 检索商品详情 -> 构建对比维度 -> LLM 生成总结
"""
import logging
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.llm_client import chat_completion
from app.services.comparison.utils import _build_comparison_table, _fallback_summary
from app.services.comparison.strategies import _determine_winner

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


# ── Template Method Pipeline ────────────────────────────────

class ComparisonPipeline:
    """商品对比流水线 (Template Method + Strategy)"""

    def __init__(self, product_ids: list[str], dimensions: list[str] | None = None):
        self.product_ids = product_ids
        self.dimensions = dimensions
        self.products: list[dict] = []
        self.products_map: dict[str, dict] = {}

    async def compare(self) -> dict:
        products = await self.fetch_products()
        if not products:
            return self.empty_result()

        self.products = products
        self.products_map = {p["product_id"]: p for p in products}
        self.check_missing()

        dimensions = self.infer_dimensions()
        dim_results = self.extract_values(dimensions)
        dim_results = self.determine_winners(dim_results)
        summary = await self.generate_summary(dim_results)

        return {
            "dimensions": dim_results,
            "summary": summary,
        }

    async def fetch_products(self) -> list[dict]:
        return await _fetch_products_from_db(self.product_ids)

    def empty_result(self) -> dict:
        return {
            "dimensions": [],
            "summary": "未找到指定的商品，请检查商品 ID 是否正确。",
        }

    def check_missing(self) -> None:
        found_ids = {p["product_id"] for p in self.products}
        missing_ids = set(self.product_ids) - found_ids
        if missing_ids:
            logger.warning("Missing products: %s", missing_ids)

    def infer_dimensions(self) -> list[str]:
        if self.dimensions is None:
            return _auto_dimensions(self.products)
        return self.dimensions

    def extract_values(self, dimensions: list[str]) -> list[dict]:
        dim_results = []
        for dim_name in dimensions:
            values = {}
            for pid in self.product_ids:
                if pid in self.products_map:
                    values[pid] = _dimension_value(self.products_map[pid], dim_name)
                else:
                    values[pid] = "商品不存在"

            dim_results.append({
                "name": dim_name,
                "values": values,
                "winner": None,
            })
        return dim_results

    def determine_winners(self, dim_results: list[dict]) -> list[dict]:
        for dim in dim_results:
            dim["winner"] = _determine_winner(
                dim["name"], dim["values"], self.products_map,
            )
        return dim_results

    async def generate_summary(self, dim_results: list[dict]) -> str:
        return await _generate_summary(dim_results, self.products_map)


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
    pipeline = ComparisonPipeline(product_ids, dimensions)
    return await pipeline.compare()
