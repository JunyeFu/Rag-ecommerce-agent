"""Explicit model-provider boundary with OpenAI-compatible structured tool calls."""

from __future__ import annotations

import asyncio
import base64
import json
import math
import re
import urllib.error
import urllib.request
import wave
from collections.abc import Mapping
from contextlib import suppress
from contextvars import ContextVar
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError

from .contracts import ToolCall, ToolExecutionContext, ToolResult, TurnCommand
from .token_budget import BudgetRefused, PostgresTokenBudget
from .tools import FROZEN_TOOL_TYPES

TOOL_DESCRIPTIONS = {
    "catalog.search": "按用户需求检索商品, 返回 product_id; 每轮最多调用一次。",
    "catalog.get_product_facts": "读取商品事实; ids 必须是 catalog.search 返回的 product_id。",
    "offer.find": "读取商品报价; ids 必须是 catalog.search 返回的 product_id。",
    "offer.requote": "刷新单个报价; offer_id 必须来自 offer.find 返回的 offer_id。",
    "comparison.build": "比较商品; ids 必须是 catalog.search 返回的 product_id。",
    "list.update": "提出清单变更及参数; 调用只产生待审批提案, 真正写入由执行器在审批后进行。",
    "cart.update": "提出待购变更及参数; 调用只产生待审批提案, 真正写入由执行器在审批后进行。",
    "link.resolve": "解析外跳链接; offer_id 必须来自 offer.find, 未经审批不得调用。",
    "vision.identify": "识别用户上传的媒体, 未经同意不得调用。",
    "audio.transcribe": "转写用户授权的语音, 不把音频内容作为商品事实。",
    "merchant.get_policy": "读取商家政策; ids 必须是 catalog.search 返回的 product_id。",
}
MONEY_PATTERN = re.compile(
    r"(?:¥|￥|人民币)\s*[0-9]+(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?\s*元"
)
EXPLICIT_QUOTE_PATTERN = re.compile(
    r"报价\s+([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})(?![0-9a-fA-F])"
)


class ProviderError(RuntimeError):
    """Base class for model-provider failures that callers must surface."""


class ProviderRateLimited(ProviderError):
    pass


class ProviderInvalidResponse(ProviderError):
    pass


class ProviderUnsupportedAmount(ProviderInvalidResponse):
    def __init__(self, amounts_minor: tuple[int, ...]) -> None:
        super().__init__("model response contained an unsupported amount")
        self.amounts_minor = amounts_minor


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


@dataclass
class _ProviderRun:
    run_id: UUID | None
    usage: dict[str, int | str]
    diagnostic: dict[str, int | str | bool]


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
        token_budget: PostgresTokenBudget | None = None,
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
        self.token_budget = token_budget
        self._run_context: ContextVar[_ProviderRun | None] = ContextVar(
            "provider_run", default=None
        )
        self._latest_run = self._new_run(None)

    def _new_run(self, run_id: UUID | None) -> _ProviderRun:
        return _ProviderRun(
            run_id,
            {"provider": "openai_compatible", "model": self.model, "total_tokens": 0},
            {"tool_calls_present": False, "tool_call_count": 0},
        )

    def _begin_run(self, command: TurnCommand | ToolExecutionContext) -> None:
        current = self._run_context.get()
        if current is None or current.run_id != command.run_id:
            current = self._new_run(command.run_id)
            self._run_context.set(current)
        self._latest_run = current

    @property
    def _usage(self) -> dict[str, int | str]:
        return (self._run_context.get() or self._latest_run).usage

    @property
    def _last_plan_diagnostic(self) -> dict[str, int | str | bool]:
        return (self._run_context.get() or self._latest_run).diagnostic

    @_last_plan_diagnostic.setter
    def _last_plan_diagnostic(self, value: dict[str, int | str | bool]) -> None:
        (self._run_context.get() or self._latest_run).diagnostic = value

    async def plan(
        self, command: TurnCommand, prior_results: tuple[ToolResult, ...], replan: int
    ) -> tuple[ToolCall, ...]:
        self._begin_run(command)
        required_call = self._required_read_call(prior_results)
        if required_call is not None:
            self._last_plan_diagnostic = {
                "tool_calls_present": True,
                "tool_call_count": 1,
                "planning_path": "deterministic_read_stage",
            }
            return (required_call,)
        catalog_call = self._known_catalog_lookup(command)
        if catalog_call is not None and not prior_results:
            self._last_plan_diagnostic = {
                "tool_calls_present": True,
                "tool_call_count": 1,
                "planning_path": "known_catalog_entity",
            }
            return (catalog_call,)
        if self._requote_already_completed(command, prior_results):
            self._last_plan_diagnostic = {
                "tool_calls_present": False,
                "tool_call_count": 0,
                "planning_path": "requote_completed",
            }
            return ()
        forced_write = self._explicit_write_target(command, prior_results)
        if forced_write == "cart.update" and any(
            "cart" in result.public_data for result in prior_results
        ):
            self._last_plan_diagnostic = {
                "tool_calls_present": False,
                "tool_call_count": 0,
                "planning_path": "explicit_cart_write_completed",
            }
            return ()
        if forced_write is not None:
            return await self._write_proposal(command, prior_results, forced_write)
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是电商导购规划器。只通过注册工具获取商品和商业事实; "
                        "价格、库存、物流和商家信息不得自行生成。"
                        "若商品品类和用途都不明确, 必须不调用工具以进入澄清; "
                        "缺少继续检索所必需的一个条件时也不调用工具。"
                        "复用 prior_results 中已经返回的 ID, 不重复成功的工具调用。"
                        "标准只读链路为检索、商品事实、报价; 有两个以上候选时调用一次比较。"
                        "每次规划只调用一个工具。只读链路完成后, 若用户明确要求刷新已有报价, "
                        "可调用 offer.requote, 但同一轮最多一次; prior_results 已有两次报价结果时不要再次调用。"
                        "若用户明确给出目标清单与商品规格或报价并要求保存, "
                        "明确要求加入清单或待购时必须调用对应写工具, 审批由执行器处理。除此之外不再调用工具。"
                        "规划写工具仅提出待审批参数, 不表示已执行; 不要因为尚未审批而省略工具调用。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "goal": command.text,
                            "mission_goal": command.mission_goal,
                            "excluded_product_ids": command.excluded_product_ids,
                            "excluded_categories": command.excluded_categories,
                            "recommendation_feedback": dict(command.recommendation_feedback),
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
                self._last_plan_diagnostic = {
                    "tool_calls_present": False,
                    "tool_call_count": 0,
                    "planning_path": "empty_model_decision",
                    "forced_write": forced_write is not None,
                }
                if forced_write is not None:
                    raise ProviderInvalidResponse(
                        f"provider omitted required {forced_write} tool call"
                    )
                return ()
            self._last_plan_diagnostic = {
                "tool_calls_present": True,
                "tool_call_count": len(raw_calls),
                "planning_path": "model_tool_call",
                "forced_write": forced_write is not None,
            }
            return tuple(
                ToolCall(
                    str(item["function"]["name"]).replace("__", "."),
                    json.loads(str(item["function"]["arguments"])),
                )
                for item in raw_calls
            )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderInvalidResponse("provider did not return valid tool calls") from exc

    async def _write_proposal(self, command, prior_results, tool_name):
        """MiMo only supports auto tool choice; an explicit write uses JSON arguments."""
        args_type = FROZEN_TOOL_TYPES[tool_name][0]
        response = await self._request(
            {
                "model": self.model,
                "thinking": {"type": "disabled"},
                "max_completion_tokens": 1024,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            f"用户已明确请求 {tool_name}。仅生成待审批提案的工具参数JSON对象,"
                            "不执行操作、不回答用户、不添加外层arguments或tool字段。"
                            "只能使用用户或工具给出的真实ID,不生成价格或商业事实。"
                            + (
                                "顶层仅含operation、offer_id、quantity三个字段。结构示例: "
                                '{"operation":"add","offer_id":"用户指定的报价UUID","quantity":1}。'
                                "加入用add,调整数量用set,移除用remove; quantity必须是JSON整数。"
                                "样例不是待购目标,必须保留用户实际指定的报价和数量,不能省略明确数量。"
                                if tool_name == "cart.update"
                                else ""
                            )
                            + f"字段与类型必须符合此Schema: {json.dumps(args_type.model_json_schema(), ensure_ascii=False)}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "request": command.text,
                                "prior_results": [dict(item.public_data) for item in prior_results],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
            }
        )
        try:
            content = response["choices"][0]["message"]["content"]
            raw = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderInvalidResponse(
                f"provider returned invalid {tool_name} proposal: envelope:{type(exc).__name__}"
            ) from exc
        try:
            arguments = args_type.model_validate_json(content, strict=True).model_dump(mode="json")
        except ValidationError as exc:
            locations = ",".join(
                f"{error['loc'][0] if error['loc'] and error['loc'][0] in args_type.model_fields else '[extra]'}:{error['type']}"
                for error in exc.errors(include_input=False, include_context=False)
            )
            raise ProviderInvalidResponse(
                f"provider returned invalid {tool_name} proposal: schema:{locations}"
            ) from exc
        if tool_name == "cart.update":
            explicit_quote = EXPLICIT_QUOTE_PATTERN.search(command.text)
            if explicit_quote and arguments["offer_id"] != str(UUID(explicit_quote.group(1))):
                raise ProviderInvalidResponse(
                    "cart.update proposal offer_id differs from explicit request"
                )
            quantity = re.search(r"(?:数量|件数)\s*[:\uFF1A]?\s*([0-9]+)", command.text)
            if quantity and (
                "quantity" not in raw or arguments["quantity"] != int(quantity.group(1))
            ):
                raise ProviderInvalidResponse(
                    "cart.update proposal quantity differs from explicit request"
                )
        self._last_plan_diagnostic = {
            "tool_calls_present": True,
            "tool_call_count": 1,
            "planning_path": "structured_write_proposal",
        }
        return (ToolCall(tool_name, arguments),)

    async def respond(self, command: TurnCommand, results: tuple[ToolResult, ...]) -> str:
        self._begin_run(command)
        # Successful phase text needs observed stages, not the original purchase
        # request: that previously elicited fabricated prices despite the guard.
        context = {
            "task": "只总结实际工具阶段, 不给商品报价或新购买建议",
            "completed_stages": sorted({key for item in results for key in item.public_data}),
            "candidate_count": sum(len(item.public_data.get("products", [])) for item in results),
        }
        if not results:
            context = {"task": "只提出一个继续检索所必需的澄清问题", "goal": command.text}
        response = await self._request(
            {
                "model": self.model,
                "thinking": {"type": "disabled"},
                "max_completion_tokens": 512,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "只输出一句不含货币金额的简洁中文阶段总结。"
                            "只总结completed_stages中实际完成的步骤, 不得声称未完成的步骤。具体结论由结构化卡片展示。"
                            "不得补全工具结果中不存在的商业事实。"
                            "本阶段总结不复述报价或预算数字, 数字与商业结论只在带证据的结构化卡片展示。"
                            "工具结果为空时只提出一个继续检索所必需的澄清问题。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(context, ensure_ascii=False),
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
                raise ProviderUnsupportedAmount(
                    tuple(sorted(mentioned_amounts - supported_amounts))
                )
            return value
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderInvalidResponse("provider did not return a message") from exc

    async def interpret_media(
        self, context: ToolExecutionContext, kind: str, content_type: str, content: bytes
    ) -> dict[str, object]:
        self._begin_run(context)
        media_upper = 16_384  # twice the official maximum image-token estimate (8,388,608 / 32²).
        if kind == "audio":
            if content_type != "audio/wav":
                raise ProviderInvalidResponse("native voice understanding requires PCM WAV")
            try:
                with wave.open(BytesIO(content), "rb") as audio:
                    duration = audio.getnframes() / audio.getframerate()
                    if (
                        duration > 60
                        or audio.getframerate() != 16000
                        or audio.getnchannels() != 1
                        or audio.getsampwidth() != 2
                    ):
                        raise ProviderInvalidResponse(
                            "voice must be mono16k PCM16 WAV, at most60seconds"
                        )
                    media_upper = math.ceil(duration * 6.25 * 2) + 512
            except (wave.Error, EOFError) as exc:
                raise ProviderInvalidResponse("invalid WAV input") from exc
        data_url = f"data:{content_type};base64,{base64.b64encode(content).decode('ascii')}"
        part = (
            {"type": "image_url", "image_url": {"url": data_url}}
            if kind == "image"
            else {"type": "input_audio", "input_audio": {"data": data_url}}
        )
        instruction = (
            "只输出一个顶层JSON对象, 不加Markdown或result/data外层, 不添加字段。"
            '必须包含且仅包含这五个字段, 结构示例: {"recognized_text":"用户输入的线索",'
            '"category":"手机","visible_attributes":["可见外观"],"uncertainties":[],"supported":true}。'
            "recognized_text必须是字符串; category只能是手机/电脑/耳机/相机或JSON null; "
            "visible_attributes和uncertainties必须是字符串数组, 没有内容时用[]而不是null; "
            "supported必须是JSON true/false而非字符串。未知或不支持时category=null, supported=false, "
            "recognized_text可为空字符串, uncertainties说明原因。"
            "这是用户输入的解释, 不是商品事实。不要生成价格库存店铺或购买操作。"
            + (
                "识别图片可见的3C品类和外观线索, 不猜测型号、隐藏规格。非3C或无法辨认则supported=false并说明。"
                if kind == "image"
                else "逐字转写用户购买需求, 保留预算、单位和否定词; 不要替用户添加要求。无有效语音则supported=false。"
            )
        )
        response = await self._request(
            {
                "model": self.model,
                "response_format": {"type": "json_object"},
                "thinking": {"type": "disabled"},
                "max_completion_tokens": 2048,
                "messages": [
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": [part, {"type": "text", "text": instruction}]},
                ],
            },
            media_upper=media_upper,
        )
        try:
            value = json.loads(response["choices"][0]["message"]["content"])
            if not isinstance(value, dict):
                raise ValueError("not an object")
            return value
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderInvalidResponse("media understanding returned invalid JSON") from exc

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
    def _known_catalog_lookup(command: TurnCommand) -> ToolCall | None:
        """Known SKU-shaped queries retrieve before asking for optional context."""
        if "演示" not in command.text:
            return None
        if not re.search(r"\b[A-Z][A-Za-z]+\s+[A-Z][A-Za-z]+\s+\d{2}\b", command.text):
            return None
        return ToolCall("catalog.search", {"query": command.text.strip()})

    @staticmethod
    def _explicit_write_target(
        command: TurnCommand, prior_results: tuple[ToolResult, ...]
    ) -> str | None:
        text = command.text
        if not any(token in text for token in ("加入", "保存", "添加")):
            return None
        keys = {key for result in prior_results for key in result.public_data}
        explicit_quote = EXPLICIT_QUOTE_PATTERN.search(text)
        if "待购" in text and ("offers" in keys or explicit_quote is not None):
            return "cart.update"
        return None

    @staticmethod
    def _requote_already_completed(
        command: TurnCommand, prior_results: tuple[ToolResult, ...]
    ) -> bool:
        if not any(token in command.text for token in ("重新询价", "重新核验", "刷新报价")):
            return False
        return sum("offers" in result.public_data for result in prior_results) >= 2

    @staticmethod
    def _money_values(text: str) -> set[int]:
        values = set()
        for match in MONEY_PATTERN.finditer(text):
            number = re.search(r"[0-9]+(?:\.[0-9]{1,2})?", match.group())
            if number:
                values.add(round(float(number.group()) * 100))
        return values

    def usage(self) -> Mapping[str, int | str]:
        return {**self._usage, **self._last_plan_diagnostic}

    async def _request(
        self, payload: dict[str, object], *, media_upper: int = 0
    ) -> dict[str, object]:
        # Count text conservatively in UTF-8 bytes; Base64 is replaced only in
        # this estimate, never in the actual request. Media uses documented
        # estimates with 2x margin. Reserve the entire remaining run allowance.
        estimated = json.dumps(payload, ensure_ascii=False)
        estimated = re.sub(r"data:[^;\"]+;base64,[A-Za-z0-9+/=]+", "[media]", estimated)
        input_upper = len(estimated.encode("utf-8")) + media_upper + 1024
        output_limit = int(payload.get("max_completion_tokens", 8192))
        call_id = None
        if self.token_budget is not None:
            current = self._run_context.get()
            if current is None or current.run_id is None:
                raise ProviderBudgetExceeded("paid request has no run identity")
            try:
                call_id, output_limit = await asyncio.to_thread(
                    self.token_budget.reserve,
                    current.run_id,
                    self.max_total_tokens,
                    input_upper,
                    output_limit,
                    self.model,
                )
            except BudgetRefused as exc:
                raise ProviderBudgetExceeded(str(exc)) from exc
        elif isinstance(self.transport, UrllibJsonTransport):
            raise ProviderBudgetExceeded(
                "shared PostgreSQL token budget is required before a paid call"
            )
        payload["max_completion_tokens"] = output_limit
        try:
            status, response = await self.transport.post_json(
                self.url,
                {"Authorization": f"Bearer {self.api_key}"},
                payload,
                self.timeout_seconds,
            )
        except BaseException:
            # Cancellation/network failure can happen after the provider has
            # consumed tokens; retain the reservation, never refund as zero.
            if call_id is not None:
                with suppress(BudgetRefused):
                    await asyncio.shield(
                        asyncio.to_thread(
                            self.token_budget.settle, call_id, None, "transport_failed"
                        )
                    )
            raise
        response_usage = response.get("usage")
        total = response_usage.get("total_tokens") if isinstance(response_usage, dict) else None
        if call_id is not None:
            try:
                await asyncio.to_thread(
                    self.token_budget.settle,
                    call_id,
                    total if type(total) is int and total >= 0 else None,
                    f"http_{status}",
                )
            except BudgetRefused as exc:
                if status == 429:
                    raise ProviderRateLimited(
                        "model provider rate limited the request; budget remains held"
                    ) from exc
                if status < 200 or status >= 300:
                    raise ProviderUnavailable(
                        f"model provider returned HTTP {status}; budget remains held"
                    ) from exc
                raise ProviderBudgetExceeded(str(exc)) from exc
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
