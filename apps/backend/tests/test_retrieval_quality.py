"""
检索质量补充测试 - 覆盖 test_retriever_pgvector.py 未涉及的边界场景。

避免与 test_retriever_pgvector.py (29 tests) 重复，专注以下未覆盖路径：
- _build_where_clause: price_max only / 空 exclude 列表跳过
- _rrf_fuse: top_k=0 / 自定义 k 参数 / payload 缺 product_id 回退 id
- _category_match_values: "鞋子"/"服装" 别名键
- _row_to_payload: attributes 内容保留 / scenarios 列表保留
"""
import pytest
from collections import namedtuple

from app.services.retriever import (
    _build_where_clause,
    _rrf_fuse,
    _row_to_payload,
    _category_match_values,
)

pytestmark = pytest.mark.unit


class TestBuildWhereClauseEdgeCases:
    """_build_where_clause 边界场景 - 补充 test_retriever_pgvector.py"""

    def test_price_max_only(self):
        """仅有 price_max（无 price_min）时应生成对应子句"""
        clause, params = _build_where_clause(None, None, 500, None, None, None)
        assert "price <= :price_max" in clause
        assert "price_min" not in params
        assert params["price_max"] == 500

    def test_empty_exclude_brands_list_is_skipped(self):
        """空列表 exclude_brands 为 falsy，不应生成 NOT 子句"""
        clause, params = _build_where_clause(None, None, None, [], None, None)
        assert "exclude_brands" not in clause
        assert "exclude_brands" not in params
        assert clause == "embedding IS NOT NULL"

    def test_empty_exclude_categories_list_is_skipped(self):
        """空列表 exclude_categories 为 falsy，不应生成 NOT 子句"""
        clause, params = _build_where_clause(None, None, None, None, [], None)
        assert "exclude_categories" not in clause
        assert clause == "embedding IS NOT NULL"


class TestRRFFuseEdgeCases:
    """_rrf_fuse 边界场景 - 补充 test_retriever_pgvector.py"""

    def test_top_k_zero_returns_empty(self):
        dense = [{"id": "p1", "score": 0.9, "payload": {"product_id": "p1"}}]
        result = _rrf_fuse(dense, [], top_k=0)
        assert result == []

    def test_custom_k_param_changes_score(self):
        """较小的 k 参数使分数更高（1/(k+rank+1)）"""
        item = {"id": "p1", "score": 0.9, "payload": {"product_id": "p1"}}
        default_k = _rrf_fuse([item], [], top_k=1, k=60)
        small_k = _rrf_fuse([item], [], top_k=1, k=1)
        assert small_k[0]["score"] > default_k[0]["score"]
        assert default_k[0]["score"] == pytest.approx(1.0 / 61)
        assert small_k[0]["score"] == pytest.approx(1.0 / 2)

    def test_payload_without_product_id_falls_back_to_id(self):
        """payload 无 product_id 时，使用 item["id"] 作为融合 key"""
        item = {"id": "fallback-id", "score": 0.9, "payload": {"title": "no pid"}}
        result = _rrf_fuse([item], [], top_k=10)
        assert len(result) == 1
        assert result[0]["id"] == "fallback-id"


class TestCategoryMatchValuesAliases:
    """_category_match_values 别名扩展 - 补充 test_retriever_pgvector.py"""

    def test_shoezi_alias_key_expands_to_multiple(self):
        """'鞋子' 键（区别于 '鞋'）扩展为多个值"""
        values = _category_match_values("鞋子")
        assert "运动鞋" in values
        assert "休闲鞋" in values
        assert len(values) > 3

    def test_fuzhuang_alias_includes_tshirt(self):
        """'服装' 键扩展包含 'T恤'"""
        values = _category_match_values("服装")
        assert "T恤" in values
        assert "外套" in values


Row = namedtuple(
    "Row",
    ["id", "title", "category", "brand", "price", "rating", "highlights",
     "scenarios", "attributes", "image_urls", "source_product_id"],
)


class TestRowToPayloadPreservation:
    """_row_to_payload 内容保留 - 补充 test_retriever_pgvector.py"""

    def test_attributes_dict_content_preserved(self):
        """attributes 字典内容应原样保留"""
        row = Row(
            id="u1", title="T", category="c", brand="b", price=1.0, rating=4.0,
            highlights=[], scenarios=[], attributes={"color": "黑", "size": "L"},
            image_urls=[], source_product_id="s1",
        )
        payload = _row_to_payload(row)
        assert payload["attributes"] == {"color": "黑", "size": "L"}

    def test_scenarios_list_content_preserved(self):
        """scenarios 列表内容应原样保留"""
        row = Row(
            id="u1", title="T", category="c", brand="b", price=1.0, rating=4.0,
            highlights=["h1"], scenarios=["通勤", "运动"], attributes={},
            image_urls=[], source_product_id="s1",
        )
        payload = _row_to_payload(row)
        assert payload["scenarios"] == ["通勤", "运动"]
