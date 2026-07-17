import pytest
pytestmark = pytest.mark.unit

"""
pgvector retriever unit tests - tests pure functions without database dependency

Covers:
- _build_where_clause: SQL WHERE clause construction with various filters
- _rrf_fuse: Reciprocal Rank Fusion of dense + keyword results
- _row_to_payload: SQLAlchemy Row to payload dict conversion
- _category_match_values: Category alias expansion
"""
import pytest
from collections import namedtuple

from app.services.retriever import (
    _build_where_clause,
    _rrf_fuse,
    _row_to_payload,
    _category_match_values,
)


# ── _build_where_clause tests ──

class TestBuildWhereClause:
    def test_no_filters_returns_embedding_not_null(self):
        clause, params = _build_where_clause(None, None, None, None, None, None)
        assert clause == "embedding IS NOT NULL"
        assert params == {}

    def test_single_category(self):
        clause, params = _build_where_clause("耳机", None, None, None, None, None)
        assert "category = ANY(:categories)" in clause
        assert "耳机" in params["categories"]

    def test_unknown_category_single_value(self):
        clause, params = _build_where_clause("无人机", None, None, None, None, None)
        assert "category = :category" in clause
        assert params["category"] == "无人机"

    def test_price_range(self):
        clause, params = _build_where_clause(None, 100, 500, None, None, None)
        assert "price >= :price_min" in clause
        assert "price <= :price_max" in clause
        assert params["price_min"] == 100
        assert params["price_max"] == 500

    def test_price_min_only(self):
        clause, params = _build_where_clause(None, 50, None, None, None, None)
        assert "price >= :price_min" in clause
        assert "price_max" not in params

    def test_exclude_brands(self):
        clause, params = _build_where_clause(None, None, None, ["Sony", "Apple"], None, None)
        assert "NOT (brand = ANY(:exclude_brands))" in clause
        assert params["exclude_brands"] == ["Sony", "Apple"]

    def test_exclude_categories(self):
        clause, params = _build_where_clause(None, None, None, None, ["配件", "壳"], None)
        assert "NOT (category = ANY(:exclude_categories))" in clause
        assert params["exclude_categories"] == ["配件", "壳"]

    def test_exclude_attributes(self):
        attrs = {"color": "红色", "size": "XL"}
        clause, params = _build_where_clause(None, None, None, None, None, attrs)
        assert "NOT (attributes->>:excl_attr_key_0 = :excl_attr_val_0)" in clause
        assert "NOT (attributes->>:excl_attr_key_1 = :excl_attr_val_1)" in clause
        assert params["excl_attr_key_0"] == "color"
        assert params["excl_attr_val_0"] == "红色"
        assert params["excl_attr_key_1"] == "size"
        assert params["excl_attr_val_1"] == "XL"

    def test_all_filters_combined(self):
        clause, params = _build_where_clause(
            category="耳机",
            price_min=100,
            price_max=500,
            exclude_brands=["Sony"],
            exclude_categories=["配件"],
            exclude_attributes={"color": "红色"},
        )
        assert "embedding IS NOT NULL" in clause
        assert "category = ANY(:categories)" in clause
        assert "price >= :price_min" in clause
        assert "price <= :price_max" in clause
        assert "NOT (brand = ANY(:exclude_brands))" in clause
        assert "NOT (category = ANY(:exclude_categories))" in clause
        assert "NOT (attributes->>:excl_attr_key_0 = :excl_attr_val_0)" in clause
        assert " AND " in clause

    def test_exclude_attribute_param_names_are_unique(self):
        attrs = {"a": "1", "b": "2", "c": "3"}
        _, params = _build_where_clause(None, None, None, None, None, attrs)
        keys = [k for k in params if k.startswith("excl_attr_key_")]
        vals = [v for v in params if v.startswith("excl_attr_val_")]
        assert len(set(keys)) == 3
        assert len(set(vals)) == 3


# ── _rrf_fuse tests ──

class TestRRFFuse:
    def _make_item(self, pid: str, title: str = ""):
        return {"id": pid, "score": 0.5, "payload": {"product_id": pid, "title": title}}

    def test_empty_inputs(self):
        result = _rrf_fuse([], [], top_k=10)
        assert result == []

    def test_dense_only(self):
        dense = [self._make_item("p1"), self._make_item("p2")]
        result = _rrf_fuse(dense, [], top_k=10)
        assert len(result) == 2
        assert result[0]["payload"]["product_id"] == "p1"

    def test_keyword_only(self):
        keyword = [self._make_item("p1"), self._make_item("p2")]
        result = _rrf_fuse([], keyword, top_k=10)
        assert len(result) == 2

    def test_fusion_ranks_overlapping_items_higher(self):
        p1 = self._make_item("p1", "headphones")
        dense = [p1, self._make_item("p2"), self._make_item("p3")]
        keyword = [p1, self._make_item("p4"), self._make_item("p5")]
        result = _rrf_fuse(dense, keyword, top_k=5)
        assert result[0]["payload"]["product_id"] == "p1"
        assert result[0]["score"] > result[1]["score"]

    def test_top_k_limits_results(self):
        dense = [self._make_item(f"p{i}") for i in range(10)]
        result = _rrf_fuse(dense, [], top_k=3)
        assert len(result) == 3

    def test_fusion_preserves_payload(self):
        dense = [{"id": "p1", "score": 0.9, "payload": {"product_id": "p1", "title": "test", "price": 99}}]
        result = _rrf_fuse(dense, [], top_k=10)
        assert result[0]["payload"]["title"] == "test"
        assert result[0]["payload"]["price"] == 99

    def test_scores_are_floats(self):
        dense = [self._make_item("p1")]
        result = _rrf_fuse(dense, [], top_k=10)
        assert isinstance(result[0]["score"], float)


# ── _row_to_payload tests ──

Row = namedtuple(
    "Row",
    ["id", "title", "category", "brand", "price", "rating", "highlights",
     "scenarios", "attributes", "image_urls", "source_product_id"],
)


class TestRowToPayload:
    def _make_row(self, **kwargs):
        defaults = {
            "id": "uuid-1",
            "title": "Test Product",
            "category": "耳机",
            "brand": "Sony",
            "price": 299.0,
            "rating": 4.5,
            "highlights": ["降噪", "蓝牙"],
            "scenarios": ["通勤"],
            "attributes": {"color": "黑色"},
            "image_urls": ["http://img1.jpg", "http://img2.jpg"],
            "source_product_id": "SKU-001",
        }
        defaults.update(kwargs)
        return Row(**defaults)

    def test_basic_conversion(self):
        row = self._make_row()
        payload = _row_to_payload(row)
        assert payload["product_id"] == "SKU-001"
        assert payload["title"] == "Test Product"
        assert payload["category"] == "耳机"
        assert payload["brand"] == "Sony"
        assert payload["price"] == 299.0
        assert payload["rating"] == 4.5

    def test_source_product_id_fallback_to_id(self):
        row = self._make_row(source_product_id=None)
        payload = _row_to_payload(row)
        assert payload["product_id"] == "uuid-1"

    def test_image_url_from_image_urls(self):
        row = self._make_row()
        payload = _row_to_payload(row)
        assert payload["image_url"] == "http://img1.jpg"
        assert len(payload["image_urls"]) == 2

    def test_empty_image_urls(self):
        row = self._make_row(image_urls=[])
        payload = _row_to_payload(row)
        assert payload["image_url"] is None
        assert payload["image_urls"] == []

    def test_none_fields_become_defaults(self):
        row = self._make_row(
            title=None, brand=None, price=None, rating=None,
            highlights=None, scenarios=None, attributes=None,
            image_urls=None, source_product_id=None,
        )
        payload = _row_to_payload(row)
        assert payload["title"] == ""
        assert payload["brand"] == ""
        assert payload["price"] == 0
        assert payload["rating"] == 0
        assert payload["highlights"] == []
        assert payload["scenarios"] == []
        assert payload["attributes"] == {}
        assert payload["image_url"] is None

    def test_rating_count_always_zero(self):
        row = self._make_row()
        payload = _row_to_payload(row)
        assert payload["rating_count"] == 0


# ── _category_match_values edge cases ──

class TestCategoryMatchValues:
    def test_none_returns_empty(self):
        assert _category_match_values(None) == []

    def test_empty_string_returns_empty(self):
        assert _category_match_values("") == []

    def test_whitespace_returns_empty(self):
        assert _category_match_values("   ") == []

    def test_known_alias_expands(self):
        values = _category_match_values("鞋")
        assert "运动鞋" in values
        assert "休闲鞋" in values
        assert len(values) > 3

    def test_unknown_category_returns_self(self):
        values = _category_match_values("无人机")
        assert values == ["无人机"]

    def test_no_duplicates(self):
        values = _category_match_values("耳机")
        assert len(values) == len(set(values))
