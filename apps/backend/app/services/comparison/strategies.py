"""
商品对比 - 胜者判定策略 (Strategy Pattern)
"""
from typing import Protocol, runtime_checkable

from app.services.comparison.utils import _extract_number

_LOWER_IS_BETTER_KEYS = {"重量", "响应时间", "延迟"}


@runtime_checkable
class WinnerStrategy(Protocol):
    def determine(self, values: dict[str, str], products_map: dict[str, dict]) -> str | None:
        ...


class PriceWinnerStrategy:
    def determine(self, values: dict[str, str], products_map: dict[str, dict]) -> str | None:
        if len(values) < 2:
            return None
        return min(
            products_map.keys(),
            key=lambda pid: products_map[pid].get("price", float("inf")),
        )


class RatingWinnerStrategy:
    def determine(self, values: dict[str, str], products_map: dict[str, dict]) -> str | None:
        if len(values) < 2:
            return None
        return max(
            products_map.keys(),
            key=lambda pid: products_map[pid].get("rating", 0),
        )


class NoWinnerStrategy:
    def determine(self, values: dict[str, str], products_map: dict[str, dict]) -> str | None:
        return None


class NumericAttributeWinnerStrategy:
    def __init__(self, lower_is_better: bool = False):
        self.lower_is_better = lower_is_better

    def determine(self, values: dict[str, str], products_map: dict[str, dict]) -> str | None:
        if len(values) < 2:
            return None
        numeric_values: dict[str, float] = {}
        for pid, val in values.items():
            num = _extract_number(val)
            if num is not None:
                numeric_values[pid] = num
        if len(numeric_values) >= 2:
            if self.lower_is_better:
                return min(numeric_values, key=numeric_values.get)
            return max(numeric_values, key=numeric_values.get)
        return None


_STRATEGY_REGISTRY: dict[str, WinnerStrategy] = {
    "价格": PriceWinnerStrategy(),
    "评分": RatingWinnerStrategy(),
    "品牌": NoWinnerStrategy(),
}

_NUMERIC_LOWER = NumericAttributeWinnerStrategy(lower_is_better=True)
_NUMERIC_HIGHER = NumericAttributeWinnerStrategy(lower_is_better=False)


def _select_strategy(dim_name: str) -> WinnerStrategy:
    strategy = _STRATEGY_REGISTRY.get(dim_name)
    if strategy is not None:
        return strategy
    if dim_name in _LOWER_IS_BETTER_KEYS:
        return _NUMERIC_LOWER
    return _NUMERIC_HIGHER


def _determine_winner(
    dim_name: str,
    values: dict[str, str],
    products_map: dict[str, dict],
) -> str | None:
    """判断某维度的最优商品。无法判定时返回 None。"""
    strategy = _select_strategy(dim_name)
    return strategy.determine(values, products_map)
