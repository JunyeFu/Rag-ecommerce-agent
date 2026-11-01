"""Deterministic extraction of the public shopping-mission structure."""

from __future__ import annotations

import re

_CATEGORY_ALIASES = (
    ("显示器", ("显示器", "屏幕")),
    ("键盘", ("键盘",)),
    ("鼠标", ("鼠标",)),
    ("耳机", ("耳机", "耳麦")),
    ("手机", ("手机",)),
    ("笔记本", ("笔记本电脑", "笔记本")),
    ("电脑", ("台式电脑", "电脑")),
    ("相机", ("相机",)),
    ("运动鞋", ("运动鞋",)),
)
_CHINESE_NUMBERS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5}
_CLAUSE_SPLIT = re.compile("[\uff0c,\u3002\uff1b;]\\s*")


def parse_shopping_mission(goal: str, *, version: int = 1) -> dict[str, object]:
    """Extract only constraints explicitly stated by the user."""

    normalized = goal.strip()
    items = []
    for category, aliases in _CATEGORY_ALIASES:
        alias = next((value for value in aliases if value in normalized), None)
        if alias is None or (category == "电脑" and "笔记本" in normalized):
            continue
        quantity_match = re.search(
            rf"(?P<count>\d+|[一二两三四五])\s*(?:个|件|台|副|双)?\s*{re.escape(alias)}",
            normalized,
        )
        raw_count = quantity_match.group("count") if quantity_match else "1"
        quantity = int(raw_count) if raw_count.isdigit() else _CHINESE_NUMBERS[raw_count]
        items.append({"category": category, "quantity": quantity})

    budget_match = re.search(
        r"(?:总预算|预算)\s*(?:为|是|约|控制在)?\s*[¥￥]?\s*(\d+(?:\.\d+)?)\s*(元|万)?",
        normalized,
    )
    budget_total_minor = None
    if budget_match:
        amount = float(budget_match.group(1))
        if budget_match.group(2) == "万":
            amount *= 10_000
        budget_total_minor = round(amount * 100)

    hard_constraints: list[str] = []
    soft_preferences: list[str] = []
    for clause in filter(None, (part.strip() for part in _CLAUSE_SPLIT.split(normalized))):
        if any(
            marker in clause
            for marker in ("必须", "不能", "不要", "只要", "不超过", "以内", "前送到", "前送达")
        ):
            hard_constraints.append(clause)
        elif any(marker in clause for marker in ("优先", "可以妥协", "偏好", "更喜欢")):
            soft_preferences.append(clause)

    unknowns: list[str] = []
    if not items:
        unknowns.append("商品品类")
    if budget_total_minor is None:
        unknowns.append("预算上限")
    if len(items) > 1 and not re.search(r"(?:分项|各自|分别).{0,8}预算", normalized):
        unknowns.append("各品类预算分配")

    return {
        "goal": normalized,
        "version": version,
        "items": items,
        "hard_constraints": list(dict.fromkeys(hard_constraints)),
        "soft_preferences": list(dict.fromkeys(soft_preferences)),
        "unknowns": unknowns,
        "budget_total_minor": budget_total_minor,
        "currency": "CNY",
    }
