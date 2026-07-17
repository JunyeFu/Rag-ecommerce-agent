import pytest
pytestmark = pytest.mark.unit

from app.services.intent import _keyword_extract_negation


def test_brand_negation_does_not_generate_ascii_prefix_filters():
    result = _keyword_extract_negation("排除 vivo")

    assert "vivo" in {b.lower() for b in result["exclude_brands"]}
    assert "vivo" in {t.lower() for t in result["exclude_text_terms"]}
    assert "vi" not in {t.lower() for t in result["exclude_text_terms"]}
    assert "viv" not in {t.lower() for t in result["exclude_text_terms"]}


def test_chinese_brand_alias_goes_to_exclude_brands():
    result = _keyword_extract_negation("不要苹果")

    assert "Apple" in result["exclude_brands"]
    assert "brand" not in result["exclude_attributes"]


def test_dislike_marker_goes_to_exclude_brands():
    result = _keyword_extract_negation("我不喜欢苹果手机")

    assert "Apple" in result["exclude_brands"]


def test_japanese_brand_family_expands_to_specific_brands():
    result = _keyword_extract_negation("推荐防晒霜，不要日系品牌")

    brands = set(result["exclude_brands"])
    text_terms = {t.lower() for t in result["exclude_text_terms"]}
    assert "日系" in brands
    assert "资生堂" in brands
    assert "安热沙" in brands
    assert "sk-ii" in text_terms


def test_alcohol_negation_goes_to_text_terms():
    result = _keyword_extract_negation("推荐防晒霜，不要含酒精的")

    terms = {t.lower() for t in result["exclude_text_terms"]}
    assert "酒精" in terms
    assert "乙醇" in terms
    assert "alcohol" in terms
