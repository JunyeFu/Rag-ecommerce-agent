import asyncio
from uuid import uuid4

import pytest
from ragcommerce_agent_runtime import (
    OpenAICompatibleProvider,
    ProviderBudgetExceeded,
    ProviderInvalidResponse,
    ProviderRateLimited,
    ProviderUnsupportedAmount,
    ToolCall,
    ToolResult,
    TurnCommand,
)


class BoundaryTransport:
    def __init__(self, status: int, payload: dict[str, object]) -> None:
        self.status = status
        self.payload = payload
        self.requests: list[dict[str, object]] = []

    async def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> tuple[int, dict[str, object]]:
        self.requests.append(payload)
        return self.status, self.payload


def command() -> TurnCommand:
    return TurnCommand(uuid4(), uuid4(), uuid4(), "provider-test-1", "推荐通勤耳机")


def test_openai_compatible_provider_returns_typed_tool_calls() -> None:
    transport = BoundaryTransport(
        200,
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "catalog__search",
                                    "arguments": '{"query":"通勤耳机"}',
                                }
                            }
                        ]
                    }
                }
            ],
            "usage": {"prompt_tokens": 21, "completion_tokens": 7, "total_tokens": 28},
        },
    )
    provider = OpenAICompatibleProvider(
        "https://model.example/v1", "secret", "demo-model", transport=transport
    )

    calls = asyncio.run(provider.plan(command(), (), 0))

    assert calls == (ToolCall("catalog.search", {"query": "通勤耳机"}),)
    request = transport.requests[0]
    assert request["model"] == "demo-model"
    assert "调用一次比较" in request["messages"][0]["content"]
    assert len(request["tools"]) == 10
    assert request["tools"][0]["function"]["name"].count(".") == 0
    assert "product_id" in request["tools"][1]["function"]["description"]
    assert provider.usage()["total_tokens"] == 28


def test_provider_accepts_a_valid_plan_without_tool_calls() -> None:
    provider = OpenAICompatibleProvider(
        "https://model.example/v1",
        "secret",
        "demo-model",
        transport=BoundaryTransport(
            200,
            {"choices": [{"message": {"content": "已有信息足够"}}]},
        ),
    )

    assert asyncio.run(provider.plan(command(), (), 0)) == ()


def test_provider_requires_the_missing_read_stage() -> None:
    transport = BoundaryTransport(
        200,
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "catalog__get_product_facts",
                                    "arguments": '{"ids":["p1","p2"]}',
                                }
                            }
                        ]
                    }
                }
            ]
        },
    )
    provider = OpenAICompatibleProvider(
        "https://model.example/v1", "secret", "demo-model", transport=transport
    )

    calls = asyncio.run(
        provider.plan(
            command(),
            (ToolResult({"products": [{"product_id": "p1"}, {"product_id": "p2"}]}),),
            0,
        )
    )

    assert calls[0].name == "catalog.get_product_facts"
    assert calls[0].arguments == {"ids": ["p1", "p2"]}
    assert transport.requests == []


@pytest.mark.parametrize(
    ("results", "expected"),
    [
        (
            (ToolResult({"products": [{"product_id": "p1"}, {"product_id": "p2"}]}),),
            "catalog.get_product_facts",
        ),
        (
            (
                ToolResult({"products": [{"product_id": "p1"}, {"product_id": "p2"}]}),
                ToolResult({"product_facts": []}),
            ),
            "offer.find",
        ),
        (
            (
                ToolResult({"products": [{"product_id": "p1"}, {"product_id": "p2"}]}),
                ToolResult({"product_facts": []}),
                ToolResult({"offers": []}),
            ),
            "comparison.build",
        ),
        (
            (
                ToolResult({"products": [{"product_id": "p1"}, {"product_id": "p2"}]}),
                ToolResult({"product_facts": []}),
                ToolResult({"offers": []}),
                ToolResult({"comparison": {}}),
            ),
            None,
        ),
    ],
)
def test_required_read_stage_table(results: tuple[ToolResult, ...], expected: str | None) -> None:
    call = OpenAICompatibleProvider._required_read_call(results)
    assert (call.name if call else None) == expected


def test_provider_rejects_monetary_amounts_in_free_text() -> None:
    provider = OpenAICompatibleProvider(
        "https://model.example/v1",
        "secret",
        "demo-model",
        transport=BoundaryTransport(
            200,
            {"choices": [{"message": {"content": "推荐商品售价 1999 元"}}]},
        ),
    )

    with pytest.raises(ProviderUnsupportedAmount, match="unsupported amount"):
        asyncio.run(provider.respond(command(), (ToolResult({"offers": []}),)))


def test_provider_accepts_an_amount_supported_by_an_offer() -> None:
    provider = OpenAICompatibleProvider(
        "https://model.example/v1",
        "secret",
        "demo-model",
        transport=BoundaryTransport(
            200,
            {"choices": [{"message": {"content": "工具报价为 1999 元"}}]},
        ),
    )
    results = (ToolResult({"offers": [{"price_minor": 199900, "shipping_minor": 0}]}),)

    assert asyncio.run(provider.respond(command(), results)) == "工具报价为 1999 元"


def test_provider_errors_are_explicit_and_never_fall_back_to_fake() -> None:
    limited = OpenAICompatibleProvider(
        "https://model.example/v1",
        "secret",
        "demo-model",
        transport=BoundaryTransport(429, {"error": {"message": "rate limited"}}),
    )
    with pytest.raises(ProviderRateLimited):
        asyncio.run(limited.plan(command(), (), 0))

    invalid = OpenAICompatibleProvider(
        "https://model.example/v1",
        "secret",
        "demo-model",
        transport=BoundaryTransport(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "catalog.search",
                                        "arguments": "not-json",
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
        ),
    )
    with pytest.raises(ProviderInvalidResponse):
        asyncio.run(invalid.plan(command(), (), 0))

    over_budget = OpenAICompatibleProvider(
        "https://model.example/v1",
        "secret",
        "demo-model",
        max_total_tokens=10,
        transport=BoundaryTransport(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "catalog.search",
                                        "arguments": '{"query":"耳机"}',
                                    }
                                }
                            ]
                        }
                    }
                ],
                "usage": {"total_tokens": 11},
            },
        ),
    )
    with pytest.raises(ProviderBudgetExceeded):
        asyncio.run(over_budget.plan(command(), (), 0))
