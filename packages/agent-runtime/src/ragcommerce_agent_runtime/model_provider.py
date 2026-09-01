"""Explicit model-provider boundary with OpenAI-compatible structured tool calls."""

from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Protocol

from .contracts import ToolCall, ToolResult, TurnCommand
from .tools import FROZEN_TOOL_TYPES

TOOL_DESCRIPTIONS = {
    "catalog.search": "按用户需求检索商品, 返回 product_id; 每轮最多调用一次。",
    "catalog.get_product_facts": "读取商品事实; ids 必须是 catalog.search 返回的 product_id。",
    "offer.find": "读取商品报价; ids 必须是 catalog.search 返回的 product_id。",
    "offer.requote": "刷新单个报价; offer_id 必须来自 offer.find 返回的 offer_id。",
    "comparison.build": "比较商品; ids 必须是 catalog.search 返回的 product_id。",
    "list.update": "修改清单; 属于可逆写操作, 未经审批不得调用。",
    "cart.update": "修改待购集合; 属于可逆写操作, 未经审批不得调用。",
    "link.resolve": "解析外跳链接; offer_id 必须来自 offer.find, 未经审批不得调用。",
    "vision.identify": "识别用户上传的媒体, 未经同意不得调用。",
    "merchant.get_policy": "读取商家政策; ids 必须是 catalog.search 返回的 product_id。",
}
MONEY_PATTERN = re.compile(
    r"(?:¥|￥|人民币)\s*[0-9]+(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?\s*元"
)


class ProviderError(RuntimeError):
    """Base class for model-provider failures that callers must surface."""


class ProviderRateLimited(ProviderError):
    pass


class ProviderInvalidResponse(ProviderError):
    pass


class ProviderUnsupportedAmount(ProviderInvalidResponse):
    pass


class ProviderBudgetExceeded(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    pass


class JsonTransport(Protocol):
    async def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> tuple[int, dict[str, object]]: ...


class UrllibJsonTransport:
    async def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> tuple[int, dict[str, object]]:
        return await asyncio.to_thread(self._post, url, headers, payload, timeout_seconds)

    @staticmethod
    def _post(
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> tuple[int, dict[str, object]]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {"error": {"message": "provider returned non-JSON error"}}
            return exc.code, parsed
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ProviderUnavailable(type(exc).__name__) from exc


class ModelProvider(Protocol):
    async def plan(
        self, command: TurnCommand, prior_results: tuple[ToolResult, ...], replan: int
    ) -> tuple[ToolCall, ...]: ...

    async def respond(self, command: TurnCommand, results: tuple[ToolResult, ...]) -> str: ...

    def usage(self) -> Mapping[str, int | str]: ...


class OpenAICompatibleProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout_seconds: float = 30.0,
        max_total_tokens: int = 12_000,
        transport: JsonTransport | None = None,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("model base_url must use HTTPS")
        if not api_key or not model:
            raise ValueError("model api_key and model are required")
        self.url = f"{base_url.rstrip('/')}/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_total_tokens = max_total_tokens
        self.transport = transport or UrllibJsonTransport()
        self._usage: dict[str, int | str] = {
            "provider": "openai_compatible",
            "model": model,
            "total_tokens": 0,
        }

    async def plan(
        self, command: TurnCommand, prior_results: tuple[ToolResult, ...], replan: int
    ) -> tuple[ToolCall, ...]:
        required_call = self._required_read_call(prior_results)
        if required_call is not None:
            return (required_call,)
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是电商导购规划器。只通过注册工具获取商品和商业事实; "
                        "价格、库存、物流和商家信息不得自行生成。"
                        "缺少继续检索所必需的一个条件时不调用工具。"
                        "复用 prior_results 中已经返回的 ID, 不重复成功的工具调用。"
                        "标准只读链路为检索、商品事实、报价; 有两个以上候选时调用一次比较。"
                        "每次规划只调用一个工具, 完成该链路后不再调用工具。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "goal": command.text,
                            "media_count": len(command.media),
                            "replan": replan,
                            "prior_results": [dict(item.public_data) for item in prior_results],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": name.replace(".", "__"),
                        "description": TOOL_DESCRIPTIONS[name],
                        "parameters": args_type.model_json_schema(),
                    },
                }
                for name, (args_type, _) in FROZEN_TOOL_TYPES.items()
            ],
            "tool_choice": "auto",
        }
        response = await self._request(payload)
        try:
            message = response["choices"][0]["message"]  # type: ignore[index]
            if not isinstance(message, dict):
                raise TypeError("message")
            raw_calls = message.get("tool_calls", [])
            if not raw_calls:
                return ()
            return tuple(
                ToolCall(
                    str(item["function"]["name"]).replace("__", "."),
                    json.loads(str(item["function"]["arguments"])),
                )
                for item in raw_calls
            )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderInvalidResponse("provider did not return valid tool calls") from exc

    async def respond(self, command: TurnCommand, results: tuple[ToolResult, ...]) -> str:
        response = await self._request(
            {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "只输出一句不含货币金额的简洁中文阶段总结。"
                            "说明已经完成检索、事实核验、报价与比较, 具体结论由结构化卡片展示。"
                            "不得补全工具结果中不存在的商业事实。"
                            "货币金额只能复述用户输入或工具结果中的精确价格、运费或合计; 不得估算。"
                            "工具结果为空时只提出一个继续检索所必需的澄清问题。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "goal": command.text,
                                "tool_results": [dict(item.public_data) for item in results],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
            }
        )
        try:
            content = response["choices"][0]["message"]["content"]  # type: ignore[index]
            if not isinstance(content, str) or not content.strip():
                raise KeyError("content")
            value = content.strip()
            mentioned_amounts = self._money_values(value)
            supported_amounts = self._money_values(command.text)
            for result in results:
                for offer in result.public_data.get("offers", []):
                    price = offer.get("price_minor")
                    shipping = offer.get("shipping_minor")
                    if isinstance(price, int):
                        supported_amounts.add(price)
                    if isinstance(shipping, int):
                        supported_amounts.add(shipping)
                    if isinstance(price, int) and isinstance(shipping, int):
                        supported_amounts.add(price + shipping)
            if mentioned_amounts - supported_amounts:
                raise ProviderUnsupportedAmount("model response contained an unsupported amount")
            return value
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderInvalidResponse("provider did not return a message") from exc

    @staticmethod
    def _required_read_call(prior_results: tuple[ToolResult, ...]) -> ToolCall | None:
        keys = {key for result in prior_results for key in result.public_data}
        products = next(
            (
                result.public_data["products"]
                for result in prior_results
                if "products" in result.public_data
            ),
            (),
        )
        ids = [str(product["product_id"]) for product in products[:3]]
        if ids and "product_facts" not in keys:
            return ToolCall("catalog.get_product_facts", {"ids": ids})
        if "product_facts" in keys and "offers" not in keys:
            return ToolCall("offer.find", {"ids": ids})
        if len(ids) >= 2 and "offers" in keys and "comparison" not in keys:
            return ToolCall("comparison.build", {"ids": ids})
        return None

    @staticmethod
    def _money_values(text: str) -> set[int]:
        values = set()
        for match in MONEY_PATTERN.finditer(text):
            number = re.search(r"[0-9]+(?:\.[0-9]{1,2})?", match.group())
            if number:
                values.add(round(float(number.group()) * 100))
        return values

    def usage(self) -> Mapping[str, int | str]:
        return dict(self._usage)

    async def _request(self, payload: dict[str, object]) -> dict[str, object]:
        status, response = await self.transport.post_json(
            self.url,
            {"Authorization": f"Bearer {self.api_key}"},
            payload,
            self.timeout_seconds,
        )
        if status == 429:
            raise ProviderRateLimited("model provider rate limited the request")
        if status < 200 or status >= 300:
            raise ProviderUnavailable(f"model provider returned HTTP {status}")
        usage = response.get("usage", {})
        if isinstance(usage, dict):
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                value = usage.get(key)
                if isinstance(value, int):
                    self._usage[key] = int(self._usage.get(key, 0)) + value
        if int(self._usage.get("total_tokens", 0)) > self.max_total_tokens:
            raise ProviderBudgetExceeded("model token budget exceeded")
        return response
