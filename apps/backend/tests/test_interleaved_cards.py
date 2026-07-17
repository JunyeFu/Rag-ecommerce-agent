import pytest
pytestmark = pytest.mark.unit

import json
from types import SimpleNamespace

import pytest

from app.services.agent import _emit_interleaved, _stream_interleaved


class _Chunk:
    def __init__(self, content: str):
        self.choices = [SimpleNamespace(delta=SimpleNamespace(content=content))]


async def _fake_stream(text: str, step: int = 7):
    for i in range(0, len(text), step):
        yield _Chunk(text[i : i + step])


async def _collect_card_positions(events):
    text = ""
    positions = []
    async for event in events:
        if event["event"] == "text_delta":
            text += json.loads(event["data"])["content"]
        elif event["event"] == "product_cards":
            positions.append((json.loads(event["data"])["index"], text))
    return positions


def _cards():
    return [
        {"id": "1", "title": "A", "price": 1, "rating": 5, "score": 0.9},
        {"id": "2", "title": "B", "price": 1, "rating": 5, "score": 0.8},
        {"id": "3", "title": "C", "price": 1, "rating": 5, "score": 0.7},
    ]


MARKED_TEXT = (
    "\u6458\u8981\u5217\u51faA\u3001B\u3001C\u3002\n"
    "\u300c\u5546\u54c11\u300d\n"
    "A\u6807\u9898\u3002\u2460 \u5339\u914d\u4f9d\u636e:\u4e00\u3002"
    "\u2461 \u54c1\u8d28\u4eae\u70b9:\u4e8c\u3002"
    "\u2462 \u9002\u7528\u573a\u666f:\u4e09\u3002\n"
    "\u300c\u5546\u54c12\u300d\n"
    "B\u6807\u9898\u3002\u2460 \u5339\u914d\u4f9d\u636e:\u4e00\u3002"
    "\u2461 \u54c1\u8d28\u4eae\u70b9:\u4e8c\u3002"
    "\u2462 \u9002\u7528\u573a\u666f:\u4e09\u3002\n"
    "\u300c\u5546\u54c13\u300d\n"
    "C\u6807\u9898\u3002\u2460 \u5339\u914d\u4f9d\u636e:\u4e00\u3002"
    "\u2461 \u54c1\u8d28\u4eae\u70b9:\u4e8c\u3002"
    "\u2462 \u9002\u7528\u573a\u666f:\u4e09\u3002\n"
    "\u300c\u7ed3\u8bed\u300d\u7ed3\u675f\u3002"
)

UNMARKED_TEXT = (
    "\u6458\u8981\u5217\u51faA\u3001B\u3001C\u3002\n"
    "A\u6807\u9898\u3002\u2460 \u5339\u914d\u4f9d\u636e:\u4e00\u3002"
    "\u2461 \u54c1\u8d28\u4eae\u70b9:\u4e8c\u3002"
    "\u2462 \u9002\u7528\u573a\u666f:\u4e09\u3002\n"
    "B\u6807\u9898\u3002\u2460 \u5339\u914d\u4f9d\u636e:\u4e00\u3002"
    "\u2461 \u54c1\u8d28\u4eae\u70b9:\u4e8c\u3002"
    "\u2462 \u9002\u7528\u573a\u666f:\u4e09\u3002\n"
    "C\u6807\u9898\u3002\u2460 \u5339\u914d\u4f9d\u636e:\u4e00\u3002"
    "\u2461 \u54c1\u8d28\u4eae\u70b9:\u4e8c\u3002"
    "\u2462 \u9002\u7528\u573a\u666f:\u4e09\u3002"
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "events",
    [
        _stream_interleaved(_fake_stream(MARKED_TEXT), _cards()),
        _emit_interleaved(MARKED_TEXT, _cards()),
    ],
)
async def test_product_markers_insert_previous_card_after_detail(events):
    positions = await _collect_card_positions(events)

    assert [index for index, _ in positions] == [1, 2, 3]
    assert "A\u6807\u9898" in positions[0][1]
    assert "B\u6807\u9898" not in positions[0][1]
    assert "B\u6807\u9898" in positions[1][1]
    assert "C\u6807\u9898" in positions[2][1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "events",
    [
        _stream_interleaved(_fake_stream(UNMARKED_TEXT), _cards()),
        _emit_interleaved(UNMARKED_TEXT, _cards()),
    ],
)
async def test_feature_detection_inserts_each_card_after_usage_scene(events):
    positions = await _collect_card_positions(events)

    assert [index for index, _ in positions] == [1, 2, 3]
    for expected_index, (_, emitted_text) in enumerate(positions, start=1):
        assert emitted_text.count("\u9002\u7528\u573a\u666f") == expected_index
