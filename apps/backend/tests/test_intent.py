import pytest
pytestmark = pytest.mark.unit

"""
Intent classifier tests — 测试纯函数：_clean_json, _keyword_classify, _keyword_extract_negation
"""
import pytest
from app.services.intent import _clean_json, _keyword_classify, _keyword_extract_negation


class TestCleanJson:
    def test_clean_markdown_code_block(self):
        raw = '```json\n{"intent": "commodity_recommend", "confidence": 0.92}\n```'
        result = _clean_json(raw)
        assert '"intent"' in result
        assert 'commodity_recommend' in result

    def test_clean_with_extra_text_before_json(self):
        raw = '分析结果：\n{"intent": "chitchat", "confidence": 0.95}\n以上是分类结果'
        result = _clean_json(raw)
        assert result.startswith('{')
        assert result.endswith('}')
        assert 'chitchat' in result

    def test_clean_json_with_trailing_comma_in_object(self):
        raw = '{"intent": "commodity_compare", "confidence": 0.88,}'
        result = _clean_json(raw)
        assert '"confidence": 0.88' in result
        assert ',}' not in result

    def test_clean_json_with_trailing_comma_in_array(self):
        raw = '{"items": ["a", "b",],}'
        result = _clean_json(raw)
        assert ',]' not in result
        assert ',}' not in result

    def test_clean_already_valid_json(self):
        raw = '{"intent": "scenario_shopping", "confidence": 0.91}'
        result = _clean_json(raw)
        assert result == raw

    def test_clean_empty_string(self):
        raw = ''
        result = _clean_json(raw)
        assert result == ''

    def test_clean_plain_text(self):
        raw = '你好，请问有什么可以帮您的'
        result = _clean_json(raw)
        # No braces at all — returns empty
        assert '你好' in result or result == raw


class TestKeywordClassify:
    def test_compare_intent(self):
        assert _keyword_classify("XM5和QC45哪个好")["intent"] == "commodity_compare"
        assert _keyword_classify("怎么选手机")["intent"] == "commodity_compare"

    def test_after_sales_intent(self):
        assert _keyword_classify("这个保修多久")["intent"] == "after_sales"
        assert _keyword_classify("支持退货吗")["intent"] == "after_sales"

    def test_scenario_intent(self):
        assert _keyword_classify("送女朋友礼物")["intent"] == "scenario_shopping"
        assert _keyword_classify("生日送什么")["intent"] == "scenario_shopping"

    def test_detail_intent(self):
        assert _keyword_classify("续航多久")["intent"] == "commodity_detail"
        assert _keyword_classify("配置参数怎么样")["intent"] == "commodity_detail"

    def test_recommend_intent(self):
        assert _keyword_classify("推荐一款降噪耳机")["intent"] == "commodity_recommend"
        assert _keyword_classify("想买个蓝牙音箱")["intent"] == "commodity_recommend"

    def test_anti_selection_intent(self):
        assert _keyword_classify("不要入耳式的")["intent"] == "anti_selection"
        assert _keyword_classify("除了小米还有什么")["intent"] == "anti_selection"
        assert _keyword_classify("我讨厌苹果手机")["intent"] == "anti_selection"
        assert _keyword_classify("不喜欢入耳式耳机")["intent"] == "anti_selection"

    def test_cart_intent(self):
        assert _keyword_classify("加入购物车")["intent"] == "cart_operation"
        assert _keyword_classify("查看购物车")["intent"] == "cart_operation"
        assert _keyword_classify("清空购物车")["intent"] == "cart_operation"

    def test_chitchat_intent(self):
        assert _keyword_classify("你好")["intent"] == "chitchat"
        assert _keyword_classify("谢谢你的帮助")["intent"] == "chitchat"

    def test_unknown_query_defaults_to_recommend(self):
        result = _keyword_classify("平板")
        assert result["intent"] == "commodity_recommend"
        assert result["confidence"] == 0.45


class TestKeywordExtractNegation:
    def test_exclude_brand(self):
        result = _keyword_extract_negation("不要小米的耳机")
        exclude_brands = result.get("exclude_brands", [])
        assert "Xiaomi" in exclude_brands or "小米" in exclude_brands or result.get("exclude_text_terms") is not None

    def test_dislike_excludes_brand(self):
        result = _keyword_extract_negation("我讨厌苹果手机")
        assert "Apple" in result.get("exclude_brands", [])

    def test_exclude_attribute_type(self):
        result = _keyword_extract_negation("不要入耳式的")
        exclude_attrs = result.get("exclude_attributes", {})
        exclude_text = result.get("exclude_text_terms", [])
        assert exclude_attrs or exclude_text

    def test_no_negation_returns_empty(self):
        result = _keyword_extract_negation("推荐降噪耳机")
        exclude_brands = result.get("exclude_brands", [])
        exclude_cats = result.get("exclude_categories", [])
        exclude_attrs = result.get("exclude_attributes", {})
        assert len(exclude_brands) == 0
        assert len(exclude_cats) == 0
        assert len(exclude_attrs) == 0

    def test_positive_query_present(self):
        result = _keyword_extract_negation("不要小米的耳机，其他品牌有什么推荐")
        assert "positive_query" in result
