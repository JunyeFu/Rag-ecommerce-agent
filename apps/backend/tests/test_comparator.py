import pytest
from app.services.comparator import (
    _auto_dimensions,
    _dimension_value,
    _determine_winner,
    _extract_number,
    _build_comparison_table,
    _fallback_summary,
    CORE_DIMENSIONS,
)


@pytest.mark.unit
class TestAutoDimensions:
    def test_includes_core_dimensions(self):
        products = [{"attributes": {}}, {"attributes": {}}]
        dims = _auto_dimensions(products)
        assert "价格" in dims
        assert "评分" in dims
        assert "品牌" in dims

    def test_includes_common_attributes(self):
        products = [
            {"attributes": {"续航": "30h", "降噪": "是"}},
            {"attributes": {"续航": "40h", "降噪": "否"}},
        ]
        dims = _auto_dimensions(products)
        assert "续航" in dims
        assert "降噪" in dims

    def test_excludes_non_common_attributes(self):
        products = [
            {"attributes": {"续航": "30h", "unique1": "a"}},
            {"attributes": {"续航": "40h", "unique2": "b"}},
        ]
        dims = _auto_dimensions(products)
        assert "unique1" not in dims
        assert "unique2" not in dims

    def test_empty_products(self):
        dims = _auto_dimensions([])
        assert dims == CORE_DIMENSIONS

    def test_single_product_attributes_included(self):
        products = [{"attributes": {"续航": "30h", "降噪": "是"}}]
        dims = _auto_dimensions(products)
        assert "续航" in dims
        assert "降噪" in dims

    def test_priority_ordering(self):
        products = [
            {"attributes": {"续航": "30h", "降噪": "是"}},
            {"attributes": {"续航": "40h", "降噪": "否"}},
        ]
        dims = _auto_dimensions(products)
        assert dims.index("降噪") < dims.index("续航")

    def test_max_six_extra_attributes(self):
        products = [
            {"attributes": {f"attr{i}": str(i) for i in range(10)}},
            {"attributes": {f"attr{i}": str(i) for i in range(10)}},
        ]
        dims = _auto_dimensions(products)
        extra = [d for d in dims if d not in CORE_DIMENSIONS]
        assert len(extra) <= 6

    def test_no_attributes_still_has_core(self):
        products = [{"attributes": {}}, {"attributes": {}}]
        dims = _auto_dimensions(products)
        assert dims == CORE_DIMENSIONS


@pytest.mark.unit
class TestExtractNumber:
    def test_plain_number(self):
        assert _extract_number("30") == 30.0

    def test_with_unit(self):
        assert _extract_number("30小时") == 30.0

    def test_with_yen(self):
        assert _extract_number("¥2499") == 2499.0

    def test_with_comma(self):
        assert _extract_number("2,499") == 2499.0

    def test_with_chinese_comma(self):
        assert _extract_number("2，499") == 2499.0

    def test_decimal(self):
        assert _extract_number("3.5kg") == 3.5

    def test_no_number(self):
        assert _extract_number("无") is None

    def test_empty_string(self):
        assert _extract_number("") is None

    def test_extract_first_number(self):
        assert _extract_number("价格200元，原价300元") == 200.0

    def test_zero(self):
        assert _extract_number("0") == 0.0

    def test_large_number(self):
        assert _extract_number("99999") == 99999.0


@pytest.mark.unit
class TestDetermineWinner:
    def test_price_lowest_wins(self):
        products_map = {
            "p1": {"price": 100},
            "p2": {"price": 200},
        }
        values = {"p1": "¥100", "p2": "¥200"}
        winner = _determine_winner("价格", values, products_map)
        assert winner == "p1"

    def test_rating_highest_wins(self):
        products_map = {
            "p1": {"rating": 4.5},
            "p2": {"rating": 4.8},
        }
        values = {"p1": "4.5★ (0评价)", "p2": "4.8★ (10评价)"}
        winner = _determine_winner("评分", values, products_map)
        assert winner == "p2"

    def test_brand_no_winner(self):
        products_map = {"p1": {"brand": "Sony"}, "p2": {"brand": "Bose"}}
        values = {"p1": "Sony", "p2": "Bose"}
        winner = _determine_winner("品牌", values, products_map)
        assert winner is None

    def test_attribute_numeric_higher_wins(self):
        products_map = {"p1": {}, "p2": {}}
        values = {"p1": "30小时", "p2": "40小时"}
        winner = _determine_winner("续航", values, products_map)
        assert winner == "p2"

    def test_weight_lower_is_better(self):
        products_map = {"p1": {}, "p2": {}}
        values = {"p1": "200g", "p2": "150g"}
        winner = _determine_winner("重量", values, products_map)
        assert winner == "p2"

    def test_single_value_returns_none(self):
        products_map = {"p1": {"price": 100}}
        values = {"p1": "¥100"}
        winner = _determine_winner("价格", values, products_map)
        assert winner is None

    def test_non_numeric_attribute_returns_none(self):
        products_map = {"p1": {}, "p2": {}}
        values = {"p1": "是", "p2": "否"}
        winner = _determine_winner("降噪", values, products_map)
        assert winner is None

    def test_one_numeric_one_non_numeric_returns_none(self):
        products_map = {"p1": {}, "p2": {}}
        values = {"p1": "30小时", "p2": "无数据"}
        winner = _determine_winner("续航", values, products_map)
        assert winner is None

    def test_response_time_lower_is_better(self):
        products_map = {"p1": {}, "p2": {}}
        values = {"p1": "5ms", "p2": "1ms"}
        winner = _determine_winner("响应时间", values, products_map)
        assert winner == "p2"

    def test_latency_lower_is_better(self):
        products_map = {"p1": {}, "p2": {}}
        values = {"p1": "50ms", "p2": "20ms"}
        winner = _determine_winner("延迟", values, products_map)
        assert winner == "p2"

    def test_three_products_price(self):
        products_map = {
            "p1": {"price": 300},
            "p2": {"price": 100},
            "p3": {"price": 200},
        }
        values = {"p1": "¥300", "p2": "¥100", "p3": "¥200"}
        winner = _determine_winner("价格", values, products_map)
        assert winner == "p2"


@pytest.mark.unit
class TestDimensionValue:
    def test_price_value(self):
        product = {"price": 199.0}
        assert _dimension_value(product, "价格") == "¥199.0"

    def test_price_default_zero(self):
        product = {}
        assert _dimension_value(product, "价格") == "¥0"

    def test_rating_value(self):
        product = {"rating": 4.5, "rating_count": 10}
        val = _dimension_value(product, "评分")
        assert "4.5" in val
        assert "10" in val

    def test_rating_default_zero(self):
        product = {}
        val = _dimension_value(product, "评分")
        assert "0" in val

    def test_brand_value(self):
        product = {"brand": "Sony"}
        assert _dimension_value(product, "品牌") == "Sony"

    def test_brand_default_unknown(self):
        product = {}
        assert _dimension_value(product, "品牌") == "未知"

    def test_attribute_value(self):
        product = {"attributes": {"续航": "30h"}}
        assert _dimension_value(product, "续航") == "30h"

    def test_missing_attribute_returns_dash(self):
        product = {"attributes": {}}
        result = _dimension_value(product, "续航")
        assert result == "\u2014"

    def test_no_attributes_key_returns_dash(self):
        product = {}
        result = _dimension_value(product, "续航")
        assert result == "\u2014"


@pytest.mark.unit
class TestBuildComparisonTable:
    def test_basic_structure(self):
        products_map = {
            "p1": {
                "title": "Product A",
                "brand": "BrandA",
                "price": 100,
                "rating": 4.5,
                "highlights": ["h1", "h2"],
            }
        }
        dimensions = [
            {"name": "价格", "values": {"p1": "¥100"}, "winner": "p1"},
        ]
        table = _build_comparison_table(dimensions, products_map)
        assert "商品对比表" in table
        assert "Product A" in table
        assert "BrandA" in table

    def test_winner_marker(self):
        products_map = {
            "p1": {"title": "A", "brand": "B", "price": 100, "rating": 4.5, "highlights": []},
            "p2": {"title": "C", "brand": "D", "price": 200, "rating": 4.0, "highlights": []},
        }
        dimensions = [
            {"name": "价格", "values": {"p1": "¥100", "p2": "¥200"}, "winner": "p1"},
        ]
        table = _build_comparison_table(dimensions, products_map)
        assert "最佳" in table

    def test_no_winner_no_marker(self):
        products_map = {
            "p1": {"title": "A", "brand": "B", "price": 100, "rating": 4.5, "highlights": []},
            "p2": {"title": "C", "brand": "D", "price": 200, "rating": 4.0, "highlights": []},
        }
        dimensions = [
            {"name": "品牌", "values": {"p1": "B", "p2": "D"}, "winner": None},
        ]
        table = _build_comparison_table(dimensions, products_map)
        assert "最佳" not in table

    def test_highlights_included(self):
        products_map = {
            "p1": {"title": "A", "brand": "B", "price": 100, "rating": 4.5,
                   "highlights": ["超长续航", "主动降噪"]},
        }
        dimensions = []
        table = _build_comparison_table(dimensions, products_map)
        assert "超长续航" in table
        assert "主动降噪" in table

    def test_long_title_truncated(self):
        long_title = "这是一个非常非常非常长的商品名称用来测试截断功能是否正常工作" * 2
        products_map = {
            "p1": {"title": long_title, "brand": "B", "price": 100, "rating": 4.5, "highlights": []},
        }
        dimensions = [
            {"name": "价格", "values": {"p1": "¥100"}, "winner": None},
        ]
        table = _build_comparison_table(dimensions, products_map)
        assert "…" in table


@pytest.mark.unit
class TestFallbackSummary:
    def test_empty_products(self):
        assert _fallback_summary([], {}) == "暂无商品数据"

    def test_basic_summary(self):
        dimensions = [
            {"name": "价格", "values": {"p1": "¥100", "p2": "¥200"}, "winner": "p1"},
        ]
        products_map = {
            "p1": {"title": "Product A", "price": 100, "rating": 4.5},
            "p2": {"title": "Product B", "price": 200, "rating": 4.8},
        }
        summary = _fallback_summary(dimensions, products_map)
        assert "Product A" in summary
        assert "Product B" in summary
        assert "¥100" in summary
        assert "4.8★" in summary
        assert "价格" in summary

    def test_cheapest_identified(self):
        dimensions = []
        products_map = {
            "p1": {"title": "Cheap", "price": 50, "rating": 3.0},
            "p2": {"title": "Expensive", "price": 500, "rating": 5.0},
        }
        summary = _fallback_summary(dimensions, products_map)
        assert "Cheap" in summary
        assert "¥50" in summary

    def test_highest_rated_identified(self):
        dimensions = []
        products_map = {
            "p1": {"title": "Low", "price": 50, "rating": 3.0},
            "p2": {"title": "High", "price": 500, "rating": 5.0},
        }
        summary = _fallback_summary(dimensions, products_map)
        assert "High" in summary
        assert "5.0★" in summary

    def test_winner_dimensions_mentioned(self):
        dimensions = [
            {"name": "价格", "values": {}, "winner": "p1"},
            {"name": "评分", "values": {}, "winner": "p2"},
        ]
        products_map = {
            "p1": {"title": "Alpha", "price": 100, "rating": 4.0},
            "p2": {"title": "Beta", "price": 200, "rating": 4.8},
        }
        summary = _fallback_summary(dimensions, products_map)
        assert "价格" in summary
        assert "评分" in summary

    def test_no_winners(self):
        dimensions = [
            {"name": "品牌", "values": {}, "winner": None},
        ]
        products_map = {
            "p1": {"title": "Alpha", "price": 100, "rating": 4.0},
            "p2": {"title": "Beta", "price": 200, "rating": 4.8},
        }
        summary = _fallback_summary(dimensions, products_map)
        assert "建议根据个人需求和预算选择" in summary

    def test_single_product(self):
        dimensions = []
        products_map = {
            "p1": {"title": "Solo", "price": 100, "rating": 4.5},
        }
        summary = _fallback_summary(dimensions, products_map)
        assert "Solo" in summary
        assert "¥100" in summary
