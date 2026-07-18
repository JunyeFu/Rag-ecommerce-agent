"""Safety service unit tests."""
import pytest
from app.services.safety_service import check_input_safety, check_output_safety, _doubao_moderation


@pytest.mark.unit
class TestInputSafety:
    @pytest.mark.asyncio
    async def test_safe_input(self):
        is_safe, reason = await check_input_safety("推荐一款降噪耳机")
        assert is_safe is True
        assert reason == ""

    @pytest.mark.asyncio
    async def test_unsafe_keyword_color(self):
        is_safe, reason = await check_input_safety("色情内容")
        assert is_safe is False
        assert "色情" in reason

    @pytest.mark.asyncio
    async def test_unsafe_keyword_violence(self):
        is_safe, reason = await check_input_safety("暴力描写")
        assert is_safe is False

    @pytest.mark.asyncio
    async def test_unsafe_keyword_gambling(self):
        is_safe, reason = await check_input_safety("赌博网站")
        assert is_safe is False

    @pytest.mark.asyncio
    async def test_unsafe_keyword_drugs(self):
        is_safe, reason = await check_input_safety("毒品交易")
        assert is_safe is False

    @pytest.mark.asyncio
    async def test_empty_input(self):
        is_safe, reason = await check_input_safety("")
        assert is_safe is True

    @pytest.mark.asyncio
    async def test_safe_chinese_query(self):
        is_safe, reason = await check_input_safety("帮我找一双适合跑步的运动鞋")
        assert is_safe is True


@pytest.mark.unit
class TestOutputSafety:
    @pytest.mark.asyncio
    async def test_safe_output(self):
        is_safe, reason = await check_output_safety("为您推荐3款降噪耳机：索尼、Bose、AirPods")
        assert is_safe is True

    @pytest.mark.asyncio
    async def test_unsafe_output_color(self):
        is_safe, reason = await check_output_safety("这里有色情内容")
        assert is_safe is False

    @pytest.mark.asyncio
    async def test_unsafe_output_violence(self):
        is_safe, reason = await check_output_safety("暴力描写片段")
        assert is_safe is False

    @pytest.mark.asyncio
    async def test_empty_output(self):
        is_safe, reason = await check_output_safety("")
        assert is_safe is True


@pytest.mark.unit
class TestDoubaoModeration:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_none(self, monkeypatch):
        monkeypatch.setattr("app.services.safety_service.settings.DOUBAO_API_KEY", "")
        result = await _doubao_moderation("test text")
        assert result is None
