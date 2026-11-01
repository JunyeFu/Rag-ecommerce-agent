# ruff: noqa: RUF001

import pytest
from ragcommerce_agent_runtime import parse_shopping_mission


def test_parses_multi_item_budget_and_explicit_constraint_strength() -> None:
    mission = parse_shopping_mission(
        "给我配一套预算 5000 元以内的办公设备，显示器必须 4K，耳机优先降噪，周五前送到公司。"
    )

    assert mission["items"] == [
        {"category": "显示器", "quantity": 1},
        {"category": "耳机", "quantity": 1},
    ]
    assert mission["budget_total_minor"] == 500_000
    assert mission["hard_constraints"] == [
        "给我配一套预算 5000 元以内的办公设备",
        "显示器必须 4K",
        "周五前送到公司",
    ]
    assert mission["soft_preferences"] == ["耳机优先降噪"]
    assert mission["unknowns"] == ["各品类预算分配"]


def test_does_not_guess_missing_budget_or_category() -> None:
    mission = parse_shopping_mission("帮我挑一个适合送礼的产品，外观优先。")

    assert mission["items"] == []
    assert mission["budget_total_minor"] is None
    assert mission["soft_preferences"] == ["外观优先"]
    assert mission["unknowns"] == ["商品品类", "预算上限"]


def test_parses_explicit_quantity() -> None:
    mission = parse_shopping_mission("预算 2000 元，买三双运动鞋，周末前送达。")

    assert mission["items"] == [{"category": "运动鞋", "quantity": 3}]
    assert mission["hard_constraints"] == ["周末前送达"]


@pytest.mark.parametrize(
    ("goal", "categories"),
    [
        ("预算 5000，显示器、键盘、鼠标和耳机一次配齐", ["显示器", "键盘", "鼠标", "耳机"]),
        ("给家人买三双运动鞋，预算 2000", ["运动鞋"]),
        ("通勤降噪耳机，预算 1000", ["耳机"]),
        ("16GB/1TB 的笔记本电脑，预算 6000", ["笔记本"]),
        ("给父亲买手机，预算 2500", ["手机"]),
        ("旅行用相机，预算 8000", ["相机"]),
        ("台式电脑和显示器，总预算 9000", ["显示器", "电脑"]),
        ("人体工学键盘和鼠标，预算 1200", ["键盘", "鼠标"]),
        ("一台 4K 屏幕，预算 3000", ["显示器"]),
        ("会议耳麦，预算 600", ["耳机"]),
    ],
)
def test_complex_task_category_split(goal: str, categories: list[str]) -> None:
    mission = parse_shopping_mission(goal)

    assert [item["category"] for item in mission["items"]] == categories
