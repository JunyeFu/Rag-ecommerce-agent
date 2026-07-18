"""
前端契约回归测试 - 验证 API 响应和 SSE 事件结构与 Android 客户端期望一致。

覆盖：
- ApiResponse 信封: code/data/message 字段
- PaginatedResponse: items/total/page/size 字段
- SSE 事件类型字段契约 (TextDelta/ProductCard/Done/Error/Progress/Clarify/Compare/Scenario)
- SSEEvent 联合类型包含所有事件
- 序列化 (model_dump) 与 SSEMixin.to_sse() 格式
"""
import json
import pytest

from app.schemas.common import ApiResponse, PaginatedResponse
from app.schemas.sse_events import (
    SSEMixin,
    TextDeltaEvent,
    ProductCardEvent,
    DoneEvent,
    ErrorEvent,
    ProgressEvent,
    ClarifyEvent,
    CompareEvent,
    ScenarioEvent,
    SSEEvent,
)

pytestmark = pytest.mark.unit


class TestApiResponseEnvelope:
    """ApiResponse 信封结构 - Android ApiClient 依赖此固定结构"""

    def test_envelope_has_all_three_fields(self):
        resp = ApiResponse(data={"id": 1})
        dumped = resp.model_dump()
        assert set(dumped.keys()) == {"code", "data", "message"}

    def test_envelope_default_values(self):
        resp = ApiResponse()
        assert resp.code == 0
        assert resp.data is None
        assert resp.message == "ok"

    def test_envelope_with_dict_data(self):
        resp = ApiResponse(data={"product_id": "p1", "price": 9.9})
        assert resp.data["product_id"] == "p1"
        assert resp.data["price"] == 9.9

    def test_envelope_with_list_data(self):
        resp = ApiResponse(data=[1, 2, 3])
        assert resp.data == [1, 2, 3]

    def test_envelope_with_string_data(self):
        resp = ApiResponse(data="hello", message="ok")
        assert resp.data == "hello"

    def test_envelope_serialization_roundtrip(self):
        resp = ApiResponse(code=200, data={"k": "v"}, message="success")
        dumped = resp.model_dump()
        assert dumped == {"code": 200, "data": {"k": "v"}, "message": "success"}
        rebuilt = ApiResponse(**dumped)
        assert rebuilt.code == 200
        assert rebuilt.data == {"k": "v"}


class TestPaginatedResponse:
    """PaginatedResponse 字段 - 前端分页列表依赖"""

    def test_paginated_fields_present(self):
        page = PaginatedResponse(items=["a", "b"], total=2, page=1, size=10)
        dumped = page.model_dump()
        assert set(dumped.keys()) == {"items", "total", "page", "size"}

    def test_paginated_defaults(self):
        page = PaginatedResponse()
        assert page.items == []
        assert page.total == 0
        assert page.page == 1
        assert page.size == 20


class TestProductCardEvent:
    """ProductCardEvent - 前端商品卡片渲染契约 (DATA-CONTRACT.md §2.2)"""

    def test_product_card_all_fields_present_and_typed(self):
        card = ProductCardEvent(
            product_id="p1",
            title="无线耳机",
            price=299.0,
            rating=4.5,
            match_score=0.9,
            highlights=["降噪"],
            image_url="http://x.jpg",
            brand="Sony",
            category="耳机",
            index=0,
            total=5,
            citation=[{"source": "web"}],
        )
        dumped = card.model_dump()
        assert dumped["type"] == "product_cards"
        assert dumped["product_id"] == "p1"
        assert dumped["price"] == 299.0
        assert isinstance(dumped["rating"], float)
        assert isinstance(dumped["highlights"], list)
        assert isinstance(dumped["image_urls"], list)

    def test_product_card_citation_is_list(self):
        card = ProductCardEvent(product_id="p1", title="T")
        assert card.citation == []
        assert isinstance(card.citation, list)
        card2 = ProductCardEvent(
            product_id="p2", title="T2", citation=[{"text": "c1"}]
        )
        assert len(card2.citation) == 1


class TestSSEEventContracts:
    """SSE 事件 type 字段契约 - 前端通过 type 分发"""

    def test_text_delta_event(self):
        e = TextDeltaEvent(content="hello")
        assert e.type == "text_delta"
        assert e.content == "hello"

    def test_done_event_fields(self):
        e = DoneEvent(total_cards=3, latency_ms=120)
        assert e.type == "done"
        assert e.total_cards == 3
        assert e.latency_ms == 120

    def test_error_event_requires_code(self):
        e = ErrorEvent(message="boom", code="5001")
        assert e.type == "error"
        assert e.message == "boom"
        assert e.code == "5001"

    def test_progress_event(self):
        e = ProgressEvent(message="retrieving")
        assert e.type == "progress"
        assert e.message == "retrieving"

    def test_clarify_event(self):
        e = ClarifyEvent(
            question="需要什么价位?",
            missing_slots=["price"],
            options=["0-100", "100-500"],
        )
        assert e.type == "clarify"
        assert e.question == "需要什么价位?"
        assert e.missing_slots == ["price"]
        assert e.options == ["0-100", "100-500"]

    def test_compare_event(self):
        e = CompareEvent(dimensions=[{"name": "price"}])
        assert e.type == "compare"
        assert isinstance(e.dimensions, list)

    def test_scenario_event(self):
        e = ScenarioEvent(scenario="送礼", sub_queries=["耳机", "手表"])
        assert e.type == "scenario"
        assert e.scenario == "送礼"
        assert e.sub_queries == ["耳机", "手表"]


class TestSSEUnionAndSerialization:
    """SSEEvent 联合类型与序列化格式"""

    def test_sse_event_union_includes_all_events(self):
        import typing

        args = set(typing.get_args(SSEEvent))
        assert TextDeltaEvent in args
        assert ProductCardEvent in args
        assert DoneEvent in args
        assert ErrorEvent in args
        assert ProgressEvent in args
        assert ClarifyEvent in args
        assert CompareEvent in args
        assert ScenarioEvent in args

    def test_sse_mixin_to_sse_format(self):
        e = TextDeltaEvent(content="hi")
        sse = e.to_sse()
        assert sse.startswith("data: ")
        assert sse.endswith("\n\n")
        payload = json.loads(sse[len("data: "):].strip())
        assert payload["type"] == "text_delta"
        assert payload["content"] == "hi"
