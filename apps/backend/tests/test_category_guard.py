import pytest
pytestmark = pytest.mark.unit

from app.services.agent import (
    _filter_chunks_by_requested_category,
    _filter_products_by_requested_category,
)


def test_tablet_category_guard_drops_ipad_accessories():
    chunks = [
        {"payload": {"product_id": "ipad", "title": "iPad 11英寸 平板电脑", "category": "平板"}},
        {"payload": {"product_id": "film", "title": "闪魔 iPad钢化膜", "category": "配件"}},
        {"payload": {"product_id": "matepad", "title": "华为 MatePad 平板", "category": "平板电脑"}},
    ]

    filtered = _filter_chunks_by_requested_category(chunks, "平板")

    assert [c["payload"]["product_id"] for c in filtered] == ["ipad", "matepad"]


def test_rank_candidates_keep_only_requested_tablet_category():
    products = [
        {"product_id": "xiaomi", "title": "小米平板8 Pro", "category": "平板"},
        {"product_id": "film", "title": "iPad钢化膜", "category": "配件"},
    ]

    filtered = _filter_products_by_requested_category(products, "平板")

    assert [p["product_id"] for p in filtered] == ["xiaomi"]


def test_category_guard_filters_shoe_aliases():
    chunks = [
        {"payload": {"product_id": "running", "title": "跑鞋", "category": "跑鞋"}},
        {"payload": {"product_id": "sport", "title": "运动鞋", "category": "运动鞋"}},
        {"payload": {"product_id": "phone", "title": "手机", "category": "手机"}},
    ]

    filtered = _filter_chunks_by_requested_category(chunks, "鞋")

    assert [c["payload"]["product_id"] for c in filtered] == ["running", "sport"]


def test_category_guard_filters_clothing_aliases():
    products = [
        {"product_id": "tee", "title": "夏季T恤", "category": "T恤"},
        {"product_id": "coat", "title": "轻薄外套", "category": "外套"},
        {"product_id": "phone", "title": "手机", "category": "手机"},
    ]

    filtered = _filter_products_by_requested_category(products, "衣服")

    assert [p["product_id"] for p in filtered] == ["tee", "coat"]


def test_category_guard_does_not_filter_unlisted_categories():
    chunks = [
        {"payload": {"product_id": "decor", "title": "桌面摆件", "category": "摆件"}},
        {"payload": {"product_id": "model", "title": "模型", "category": "模型"}},
    ]

    assert _filter_chunks_by_requested_category(chunks, "摆件") == chunks
