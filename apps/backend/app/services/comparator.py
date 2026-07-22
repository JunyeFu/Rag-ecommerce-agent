"""
商品对比 - 多商品多维度对比服务
从 PostgreSQL 检索商品详情 -> 构建对比维度 -> LLM 生成总结
"""
from app.services.comparison import (
    logger,
    CORE_DIMENSIONS,
    ATTRIBUTE_PRIORITY,
    _COMPARISON_SYSTEM_PROMPT,
    _auto_dimensions,
    _dimension_value,
    _fetch_products_from_db,
    _generate_summary,
    ComparisonPipeline,
    compare_products,
    WinnerStrategy,
    PriceWinnerStrategy,
    RatingWinnerStrategy,
    NoWinnerStrategy,
    NumericAttributeWinnerStrategy,
    _determine_winner,
    _extract_number,
    _build_comparison_table,
    _fallback_summary,
)

__all__ = [
    "logger",
    "CORE_DIMENSIONS",
    "ATTRIBUTE_PRIORITY",
    "_COMPARISON_SYSTEM_PROMPT",
    "_auto_dimensions",
    "_dimension_value",
    "_fetch_products_from_db",
    "_generate_summary",
    "ComparisonPipeline",
    "compare_products",
    "WinnerStrategy",
    "PriceWinnerStrategy",
    "RatingWinnerStrategy",
    "NoWinnerStrategy",
    "NumericAttributeWinnerStrategy",
    "_determine_winner",
    "_extract_number",
    "_build_comparison_table",
    "_fallback_summary",
]
