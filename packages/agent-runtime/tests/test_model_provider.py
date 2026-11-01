import asyncio
import json
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


def test_explicit_quote_write_can_request_approval_in_a_followup_turn():
    offer = uuid4()
    turn = TurnCommand(
        uuid4(), uuid4(), uuid4(), "explicit-quote", f"请把报价 {offer} 以数量2加入待购, 等待审批"
    )
    assert OpenAICompatibleProvider._explicit_write_target(turn, ()) == "cart.update"
    assert not turn.allow_reversible_writes and not turn.approved_tools
    vague = TurnCommand(uuid4(), uuid4(), uuid4(), "vague-quote", "请把报价最便宜的加入待购")
    assert OpenAICompatibleProvider._explicit_write_target(vague, ()) is None


def test_media_prompt_has_a_literal_structure_and_user_instruction():
    from ragcommerce_agent_runtime import ToolExecutionContext

    payload = {
        "recognized_text": "手机",
        "category": "手机",
        "visible_attributes": ["屏幕"],
        "uncertainties": [],
        "supported": True,
    }
    transport = BoundaryTransport(
        200,
        {"choices": [{"message": {"content": json.dumps(payload)}}], "usage": {"total_tokens": 50}},
    )
    provider = OpenAICompatibleProvider(
        "https://fixture.example/v1", "test-only", "fixture", transport=transport
    )
    context = ToolExecutionContext(uuid4(), uuid4(), uuid4(), uuid4(), "fixture-digest")
    assert (
        asyncio.run(provider.interpret_media(context, "image", "image/png", b"fixture")) == payload
    )
    request = transport.requests[0]
    assert request["response_format"] == {"type": "json_object"}
    parts = request["messages"][1]["content"]
    assert parts[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert parts[1]["type"] == "text" and '"recognized_text"' in parts[1]["text"]


def test_completed_phase_response_uses_observed_stages_not_purchase_goal():
    transport = BoundaryTransport(
        200,
        {
            "choices": [{"message": {"content": "已完成检索, 请查看证据卡片。"}}],
            "usage": {"total_tokens": 50},
        },
    )
    provider = OpenAICompatibleProvider(
        "https://fixture.example/v1", "test-only", "fixture", transport=transport
    )
    asyncio.run(provider.respond(command(), (ToolResult({"products": []}),)))
    payload = transport.requests[0]
    context = json.loads(payload["messages"][1]["content"])
    assert "goal" not in context and context["completed_stages"] == ["products"]
    assert payload["thinking"] == {"type": "disabled"} and payload["max_completion_tokens"] == 512


def test_completed_explicit_cart_is_not_forced_to_plan_the_same_write_again():
    transport = BoundaryTransport(200, {})
    provider = OpenAICompatibleProvider(
        "https://fixture.example/v1", "test-only", "fixture", transport=transport
    )
    turn = TurnCommand(uuid4(), uuid4(), uuid4(), "completed-cart", f"报价 {uuid4()} 加入待购")
    assert asyncio.run(provider.plan(turn, (ToolResult({"cart": {"items": []}}),), 0)) == ()
    assert not transport.requests


def test_reused_provider_has_a_separate_budget_for_each_run():
    provider = OpenAICompatibleProvider(
        "https://model.example/v1",
        "test-only",
        "test-model",
        max_total_tokens=10,
        transport=BoundaryTransport(
            200,
            {
                "choices": [{"message": {"content": "请补充用途"}}],
                "usage": {"total_tokens": 7},
            },
        ),
    )

    async def run():
        for _ in range(2):
            await provider.respond(command(), ())
            assert provider.usage()["total_tokens"] == 7
        same_run = command()
        await provider.respond(same_run, ())
        with pytest.raises(ProviderBudgetExceeded):
            await provider.respond(same_run, ())

    asyncio.run(run())


def test_shared_provider_isolates_concurrent_run_usage():
    class YieldingTransport(BoundaryTransport):
        async def post_json(self, *args):
            await asyncio.sleep(0)
            return await super().post_json(*args)

    provider = OpenAICompatibleProvider(
        "https://model.example/v1",
        "test-only",
        "test-model",
        max_total_tokens=10,
        transport=YieldingTransport(
            200,
            {
                "choices": [{"message": {"content": "请补充用途"}}],
                "usage": {"total_tokens": 7},
            },
        ),
    )

    async def run():
        async def one():
            await provider.respond(command(), ())
            return provider.usage()["total_tokens"]

        assert await asyncio.gather(one(), one()) == [7, 7]

    asyncio.run(run())


def test_blocked_amount_diagnostic_does_not_include_model_text():
    provider = OpenAICompatibleProvider(
        "https://model.example/v1",
        "test-only",
        "test-model",
        transport=BoundaryTransport(
            200,
            {
                "choices": [{"message": {"content": "售价999元 私密原文不进入异常"}}],
            },
        ),
    )
    with pytest.raises(ProviderUnsupportedAmount) as caught:
        asyncio.run(provider.respond(command(), ()))
    assert caught.value.amounts_minor == (99900,)
    assert "私密原文" not in str(caught.value)


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
    assert "品类和用途都不明确" in request["messages"][0]["content"]
    assert len(request["tools"]) == 11
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


def test_known_demo_sku_is_retrieved_even_without_optional_use_case() -> None:
    provider = OpenAICompatibleProvider(
        "https://model.example/v1", "secret", "demo-model", transport=BoundaryTransport(200, {})
    )
    request = TurnCommand(
        uuid4(), uuid4(), uuid4(), "provider-test-known", "Arc Compute Forge 03 演示电脑"
    )

    assert asyncio.run(provider.plan(request, (), 0)) == (
        ToolCall("catalog.search", {"query": request.text}),
    )
    assert provider.usage()["planning_path"] == "known_catalog_entity"


def test_explicit_cart_intent_rejects_invalid_json_proposal_without_retry() -> None:
    transport = BoundaryTransport(200, {"choices": [{"message": {"content": "无法处理"}}]})
    provider = OpenAICompatibleProvider(
        "https://model.example/v1", "secret", "demo-model", transport=transport
    )
    request = TurnCommand(
        uuid4(),
        uuid4(),
        uuid4(),
        "provider-test-cart",
        "请把报价 abc 以数量 2 加入待购, 等待我审批",
    )
    prior = (ToolResult({"offers": [{"offer_id": "abc"}]}),)

    with pytest.raises(ProviderInvalidResponse, match=r"cart\.update"):
        asyncio.run(provider.plan(request, prior, 0))
    assert len(transport.requests) == 1
    assert "tool_choice" not in transport.requests[0]
    assert transport.requests[0]["response_format"] == {"type": "json_object"}


def test_explicit_cart_proposal_is_typed_but_not_preapproved() -> None:
    offer_id = str(uuid4())
    arguments = {"operation": "add", "offer_id": offer_id, "quantity": 2}
    transport = BoundaryTransport(
        200, {"choices": [{"message": {"content": json.dumps(arguments)}}]}
    )
    provider = OpenAICompatibleProvider(
        "https://model.example/v1", "test-only", "demo-model", transport=transport
    )
    request = TurnCommand(uuid4(), uuid4(), uuid4(), "typed-cart", f"报价 {offer_id} 数量2加入待购")
    assert asyncio.run(provider.plan(request, (), 0)) == (ToolCall("cart.update", arguments),)
    assert not request.allow_reversible_writes and not request.approved_tools
    assert len(transport.requests) == 1 and "tools" not in transport.requests[0]
    assert provider.usage()["planning_path"] == "structured_write_proposal"


@pytest.mark.parametrize(
    "proposal",
    [
        {"operation": "add"},
        {"operation": "add", "quantity": 1},
    ],
)
def test_cart_proposal_must_not_drop_or_change_the_explicit_quantity(proposal):
    offer_id = str(uuid4())
    transport = BoundaryTransport(
        200, {"choices": [{"message": {"content": json.dumps({**proposal, "offer_id": offer_id})}}]}
    )
    provider = OpenAICompatibleProvider(
        "https://fixture.example/v1", "test-only", "fixture", transport=transport
    )
    request = TurnCommand(uuid4(), uuid4(), uuid4(), "quantity", f"报价 {offer_id} 数量2加入待购")
    with pytest.raises(ProviderInvalidResponse, match="quantity"):
        asyncio.run(provider.plan(request, (), 0))
    assert len(transport.requests) == 1


def test_cart_proposal_cannot_substitute_another_valid_quote():
    requested, substituted = str(uuid4()), str(uuid4())
    transport = BoundaryTransport(
        200,
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "operation": "add",
                                "offer_id": substituted,
                                "quantity": 2,
                            }
                        )
                    }
                }
            ]
        },
    )
    provider = OpenAICompatibleProvider(
        "https://fixture.example/v1", "test-only", "fixture", transport=transport
    )
    request = TurnCommand(uuid4(), uuid4(), uuid4(), "quote", f"报价 {requested} 数量2加入待购")
    with pytest.raises(ProviderInvalidResponse, match="offer_id"):
        asyncio.run(provider.plan(request, (), 0))
    assert len(transport.requests) == 1


def test_invalid_proposal_reports_only_safe_schema_locations():
    supplied_secret = "private-model-value"
    transport = BoundaryTransport(
        200,
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "operation": "add",
                                "offer_id": supplied_secret,
                                "quantity": 0,
                                supplied_secret: supplied_secret,
                            }
                        )
                    }
                }
            ]
        },
    )
    provider = OpenAICompatibleProvider(
        "https://fixture.example/v1", "test-only", "fixture", transport=transport
    )
    request = TurnCommand(uuid4(), uuid4(), uuid4(), "diagnostic", f"报价 {uuid4()} 数量2加入待购")
    with pytest.raises(ProviderInvalidResponse) as caught:
        asyncio.run(provider.plan(request, (), 0))
    detail = str(caught.value)
    assert "offer_id:uuid_parsing" in detail
    assert "quantity:greater_than_equal" in detail
    assert "[extra]:extra_forbidden" in detail
    assert supplied_secret not in detail
    assert len(transport.requests) == 1


def test_requote_is_not_replanned_after_two_offer_results() -> None:
    provider = OpenAICompatibleProvider(
        "https://model.example/v1", "secret", "demo-model", transport=BoundaryTransport(200, {})
    )
    request = TurnCommand(
        uuid4(), uuid4(), uuid4(), "provider-test-requote", "请重新核验并刷新报价"
    )
    prior = (
        ToolResult({"offers": [{"offer_id": "a"}]}),
        ToolResult({"offers": [{"offer_id": "a"}]}),
    )

    assert asyncio.run(provider.plan(request, prior, 1)) == ()
    assert provider.usage()["planning_path"] == "requote_completed"


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        (
            "cart__update",
            {
                "operation": "add",
                "offer_id": "00000000-0000-5000-8000-000000000103",
                "quantity": 1,
            },
        ),
        (
            "list__update",
            {
                "operation": "add",
                "list_id": "00000000-0000-5000-8000-000000000101",
                "variant_id": "00000000-0000-5000-8000-000000000102",
            },
        ),
        (
            "offer__requote",
            {"offer_id": "00000000-0000-5000-8000-000000000103"},
        ),
    ],
)
def test_provider_can_plan_requote_and_typed_reversible_actions(
    tool_name: str, arguments: dict[str, object]
) -> None:
    transport = BoundaryTransport(
        200,
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": tool_name,
                                    "arguments": json.dumps(arguments),
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

    calls = asyncio.run(provider.plan(command(), (), 0))

    assert calls == (ToolCall(tool_name.replace("__", "."), arguments),)


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
