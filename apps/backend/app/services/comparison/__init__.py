"""
商品对比服务包
"""
from app.services.comparison.pipeline import (
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
)
from app.services.comparison.strategies import (
    WinnerStrategy,
    PriceWinnerStrategy,
    RatingWinnerStrategy,
    NoWinnerStrategy,
    NumericAttributeWinnerStrategy,
    _determine_winner,
)
from app.services.comparison.utils import (
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
