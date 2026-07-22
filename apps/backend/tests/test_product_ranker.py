import pytest
pytestmark = pytest.mark.unit

"""ProductRanker 单元测试"""
import pytest
from app.services.product_ranker import ProductRanker, Intent


@pytest.fixture
def ranker():
    return ProductRanker()


@pytest.fixture
def sample_products():
    return [
        {"title": "Sony XM5", "price": 2499, "rating": 4.7, "brand": "Sony",
         "attributes": {"降噪": "主动降噪", "续航": "30小时"}, "semantic_score": 0.92},
        {"title": "Bose QC45", "price": 2299, "rating": 4.5, "brand": "Bose",
         "attributes": {"降噪": "主动降噪", "续航": "24小时"}, "semantic_score": 0.88},
        {"title": "AirPods Pro", "price": 1899, "rating": 4.8, "brand": "Apple",
         "attributes": {"降噪": "主动降噪", "续航": "6小时"}, "semantic_score": 0.85},
        {"title": "小米 Buds 4", "price": 699, "rating": 4.2, "brand": "小米",
         "attributes": {"降噪": "主动降噪", "续航": "9小时"}, "semantic_score": 0.75},
        {"title": "JBL Flip6", "price": 899, "rating": 4.4, "brand": "JBL",
         "attributes": {"防水": "IP67", "续航": "12小时"}, "semantic_score": 0.45},
    ]


def test_rank_returns_top_k(ranker, sample_products):
    result = ranker.rank(sample_products, {}, top_k=3)
    assert len(result) == 3


def test_price_budget_prefers_in_range(ranker, sample_products):
    """预算 2000-3000 时，Sony(2499) 和 Bose(2299) 应排在前面"""
    prefs = {"price_min": 2000, "price_max": 3000}
    result = ranker.rank(sample_products, prefs, "commodity_recommend", top_k=3)
    top_titles = [r["title"] for r in result]
    assert "Sony XM5" in top_titles or "Bose QC45" in top_titles
    assert "小米 Buds 4" not in top_titles  # 699 超出预算


def test_brand_preference_boosts(ranker, sample_products):
    """品牌偏好 Sony 时，Sony 应排第一"""
    prefs = {"brand_preference": "Sony"}
    result = ranker.rank(sample_products, prefs, top_k=5)
    assert result[0]["title"] == "Sony XM5"


def test_attribute_match_boosts(ranker, sample_products):
    """属性匹配降噪=主动降噪时，JBL 音箱排最后"""
    prefs = {"attributes": {"降噪": "主动降噪"}}
    result = ranker.rank(sample_products, prefs, top_k=5)
    assert result[-1]["title"] == "JBL Flip6"


def test_adds_match_score_and_reason(ranker, sample_products):
    result = ranker.rank(sample_products, {}, top_k=3)
    for prod in result:
        assert "match_score" in prod
        assert "dimension_scores" in prod
        assert "rank_reason" in prod
        assert 0 <= prod["match_score"] <= 1


def test_different_intents_give_different_orders(ranker, sample_products):
    """不同意图权重不同，但都返回5条"""
    result_rec = ranker.rank(sample_products, {}, "commodity_recommend", top_k=5)
    result_detail = ranker.rank(sample_products, {}, "commodity_detail", top_k=5)
    assert len(result_rec) == 5
    assert len(result_detail) == 5


def test_anti_selection_excludes_brands(ranker, sample_products):
    """反选意图：排除品牌"""
    prefs = {"exclude_brands": ["Sony", "Bose"]}
    result = ranker.rank(sample_products, prefs, "anti_selection", top_k=5)
    titles = {r["title"] for r in result}
    assert "Sony XM5" not in titles
    assert "Bose QC45" not in titles
    assert result[0]["title"] == "AirPods Pro"


def test_exclude_brands_is_case_and_space_insensitive(ranker, sample_products):
    prefs = {"exclude_brands": [" apple "]}
    result = ranker.rank(sample_products, prefs, "anti_selection", top_k=5)
    titles = {r["title"] for r in result}
    assert "AirPods Pro" not in titles


def test_exclude_brand_matches_compound_brand_names(ranker):
    products = [
        {"title": "AirPods Pro", "price": 1899, "rating": 4.8, "brand": "Apple 苹果", "semantic_score": 0.9},
        {"title": "Huawei FreeBuds", "price": 999, "rating": 4.6, "brand": "华为", "semantic_score": 0.8},
    ]

    result = ranker.rank(products, {"exclude_brands": ["Apple"]}, "anti_selection", top_k=5)

    assert [r["title"] for r in result] == ["Huawei FreeBuds"]


def test_anti_selection_excludes_attributes(ranker, sample_products):
    """反选意图：排除属性"""
    prefs = {"exclude_attributes": {"防水": "IP67"}}
    result = ranker.rank(sample_products, prefs, top_k=5)
    titles = {r["title"] for r in result}
    assert "JBL Flip6" not in titles


def test_anti_selection_excludes_japanese_family_and_alcohol(ranker):
    products = [
        {
            "title": "资生堂安耐晒小金瓶防晒霜",
            "price": 168,
            "rating": 4.8,
            "brand": "资生堂",
            "attributes": {"成分": "含酒精"},
            "highlights": ["日系防晒"],
            "semantic_score": 0.95,
        },
        {
            "title": "理肤泉大哥大防晒乳",
            "price": 189,
            "rating": 4.7,
            "brand": "理肤泉",
            "attributes": {"成分": "无香精配方"},
            "highlights": ["敏感肌适用"],
            "semantic_score": 0.8,
        },
    ]

    result = ranker.rank(
        products,
        {"exclude_brands": ["日系"], "exclude_text_terms": ["酒精"]},
        "anti_selection",
        top_k=5,
    )

    assert [r["title"] for r in result] == ["理肤泉大哥大防晒乳"]
