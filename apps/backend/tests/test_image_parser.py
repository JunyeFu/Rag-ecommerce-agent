import json

import pytest
from app.services.image_parser import _parse_vlm_output


@pytest.mark.unit
class TestParseVlmOutput:
    def test_valid_json_all_fields(self):
        text = json.dumps({
            "category": "耳机",
            "brand": "Sony",
            "color": "黑色",
            "material": "塑料",
            "style": "简约",
            "keywords": ["降噪", "蓝牙", "音乐"],
            "description": "索尼降噪耳机",
        }, ensure_ascii=False)
        result = _parse_vlm_output(text)
        assert result["category"] == "耳机"
        assert result["brand"] == "Sony"
        assert result["color"] == "黑色"
        assert result["material"] == "塑料"
        assert result["style"] == "简约"
        assert result["keywords"] == ["降噪", "蓝牙", "音乐"]
        assert result["description"] == "索尼降噪耳机"
        assert result["confidence"] == 1.0

    def test_markdown_json_code_block(self):
        text = '```json\n{"category": "手机", "brand": "Apple"}\n```'
        result = _parse_vlm_output(text)
        assert result["category"] == "手机"
        assert result["brand"] == "Apple"

    def test_markdown_plain_code_block(self):
        text = '```\n{"category": "手机", "brand": "Apple"}\n```'
        result = _parse_vlm_output(text)
        assert result["category"] == "手机"
        assert result["brand"] == "Apple"

    def test_json_embedded_in_text(self):
        text = '分析结果如下：{"category": "耳机"} 以上是结果'
        result = _parse_vlm_output(text)
        assert result["category"] == "耳机"

    def test_empty_string(self):
        result = _parse_vlm_output("")
        assert result["category"] is None
        assert result["brand"] is None
        assert result["color"] is None
        assert result["material"] is None
        assert result["style"] is None
        assert result["keywords"] == []
        assert result["description"] is None
        assert result["confidence"] == 0.0

    def test_whitespace_only(self):
        result = _parse_vlm_output("   \n\t  ")
        assert result["confidence"] == 0.0
        assert result["category"] is None

    def test_keywords_as_string_coerced_to_list(self):
        text = '{"category": "耳机", "keywords": "降噪耳机"}'
        result = _parse_vlm_output(text)
        assert result["keywords"] == ["降噪耳机"]

    def test_keywords_as_number_coerced_to_list(self):
        text = '{"keywords": 123}'
        result = _parse_vlm_output(text)
        assert result["keywords"] == ["123"]

    def test_null_values_filtered(self):
        text = '{"category": null, "brand": "Sony"}'
        result = _parse_vlm_output(text)
        assert result["category"] is None
        assert result["brand"] == "Sony"

    def test_null_string_filtered(self):
        text = '{"category": "null", "brand": "Sony"}'
        result = _parse_vlm_output(text)
        assert result["category"] is None
        assert result["brand"] == "Sony"

    def test_description_auto_filled_from_keywords(self):
        text = '{"category": "耳机", "keywords": ["降噪", "蓝牙", "音乐"]}'
        result = _parse_vlm_output(text)
        assert result["description"] == "降噪, 蓝牙, 音乐"

    def test_description_not_overwritten_when_present(self):
        text = '{"category": "耳机", "keywords": ["降噪"], "description": "好耳机"}'
        result = _parse_vlm_output(text)
        assert result["description"] == "好耳机"

    def test_confidence_partial_fields(self):
        text = '{"category": "耳机", "brand": "Sony"}'
        result = _parse_vlm_output(text)
        assert result["confidence"] == round(2 / 6, 2)

    def test_confidence_with_auto_description(self):
        text = '{"category": "耳机", "keywords": ["降噪"]}'
        result = _parse_vlm_output(text)
        assert result["description"] == "降噪"
        assert result["confidence"] == round(2 / 6, 2)

    def test_confidence_zero_when_no_identifiable_fields(self):
        text = '{"keywords": []}'
        result = _parse_vlm_output(text)
        assert result["confidence"] == 0.0

    def test_no_json_at_all(self):
        result = _parse_vlm_output("这是一段纯文本，没有JSON")
        assert result["category"] is None
        assert result["confidence"] == 0.0

    def test_malformed_json_no_braces(self):
        result = _parse_vlm_output("not json at all 12345")
        assert result["confidence"] == 0.0

    def test_only_some_fields(self):
        text = '{"category": "手机", "color": "白色"}'
        result = _parse_vlm_output(text)
        assert result["category"] == "手机"
        assert result["color"] == "白色"
        assert result["brand"] is None
        assert result["keywords"] == []

    def test_extra_unknown_fields_ignored(self):
        text = '{"category": "手机", "unknown_field": "ignored"}'
        result = _parse_vlm_output(text)
        assert result["category"] == "手机"
        assert "unknown_field" not in result

    def test_keywords_max_three_for_description(self):
        text = '{"keywords": ["a", "b", "c", "d", "e"]}'
        result = _parse_vlm_output(text)
        assert result["description"] == "a, b, c"
