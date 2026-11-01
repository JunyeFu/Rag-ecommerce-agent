"""Frozen typed tool registry and risk policy."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .contracts import ToolCall, ToolExecutionContext, ToolResult, TurnCommand

ToolHandler = Callable[[ToolExecutionContext, BaseModel], ToolResult | Awaitable[ToolResult]]


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueryArgs(StrictArgs):
    query: str = Field(min_length=1, max_length=500)


class IdsArgs(StrictArgs):
    ids: list[str] = Field(min_length=1, max_length=20)


class OfferArgs(StrictArgs):
    offer_id: str
    quote_id: str | None = None


class ListUpdateArgs(StrictArgs):
    operation: Literal["add", "remove"]
    list_id: UUID
    variant_id: UUID


class CartUpdateArgs(StrictArgs):
    operation: Literal["add", "set", "remove"]
    offer_id: UUID
    quantity: int = Field(default=1, ge=1, le=99)


class MediaArgs(StrictArgs):
    media_ref: str


class Risk(StrEnum):
    READ = "READ"
    REVERSIBLE = "REVERSIBLE"
    CONSENT = "CONSENT"
    EXTERNAL_NAVIGATION = "EXTERNAL_NAVIGATION"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    args_type: type[BaseModel]
    risk: Risk
    handler: ToolHandler


class ToolDenied(RuntimeError):
    pass


FROZEN_TOOL_TYPES: Mapping[str, tuple[type[BaseModel], Risk]] = {
    "catalog.search": (QueryArgs, Risk.READ),
    "catalog.get_product_facts": (IdsArgs, Risk.READ),
    "offer.find": (IdsArgs, Risk.READ),
    "offer.requote": (OfferArgs, Risk.READ),
    "comparison.build": (IdsArgs, Risk.READ),
    "list.update": (ListUpdateArgs, Risk.REVERSIBLE),
    "cart.update": (CartUpdateArgs, Risk.REVERSIBLE),
    "link.resolve": (OfferArgs, Risk.EXTERNAL_NAVIGATION),
    "vision.identify": (MediaArgs, Risk.CONSENT),
    "audio.transcribe": (MediaArgs, Risk.CONSENT),
    "merchant.get_policy": (IdsArgs, Risk.READ),
}


class ToolRegistry:
    def __init__(self, handlers: Mapping[str, ToolHandler]) -> None:
        if set(handlers) != set(FROZEN_TOOL_TYPES):
            raise ValueError("handlers must implement exactly the registered tools")
        self.specs = {
            name: ToolSpec(name, values[0], values[1], handlers[name])
            for name, values in FROZEN_TOOL_TYPES.items()
        }

    def execute(
        self, command: TurnCommand, call: ToolCall, context: ToolExecutionContext
    ) -> ToolResult:
        spec, arguments = self._validated(command, call, context)
        result = spec.handler(context, arguments)
        if inspect.isawaitable(result):
            raise RuntimeError("async tool handler requires execute_async")
        return result

    async def execute_async(
        self, command: TurnCommand, call: ToolCall, context: ToolExecutionContext
    ) -> ToolResult:
        spec, arguments = self._validated(command, call, context)
        result = spec.handler(context, arguments)
        return await result if inspect.isawaitable(result) else result

    def _validated(
        self, command: TurnCommand, call: ToolCall, context: ToolExecutionContext
    ) -> tuple[ToolSpec, BaseModel]:
        spec = self.specs.get(call.name)
        if spec is None:
            raise ValueError("tool is not registered")
        arguments = spec.args_type.model_validate(dict(call.arguments))
        if spec.risk is Risk.REVERSIBLE and (
            not command.allow_reversible_writes or call.name not in command.approved_tools
        ):
            raise ToolDenied("reversible write was not authorized")
        if (
            spec.risk in {Risk.CONSENT, Risk.EXTERNAL_NAVIGATION}
            and call.name not in command.approved_tools
        ):
            raise ToolDenied("explicit approval is required")
        if (
            spec.risk in {Risk.REVERSIBLE, Risk.EXTERNAL_NAVIGATION}
            and command.approved_invocations is not None
            and str(context.invocation_id) not in command.approved_invocations
        ):
            raise ToolDenied("approval does not cover this invocation")
        if spec.risk is Risk.CONSENT:
            expected_kind = "image" if call.name == "vision.identify" else "audio"
            if not any(
                str(ref.id) == arguments.media_ref and ref.kind == expected_kind
                for ref in command.media
            ):
                raise ToolDenied("media was not authorized for this Turn")
        return spec, arguments
