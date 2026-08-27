"""Frozen typed tool registry and risk policy."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .contracts import ToolCall, ToolExecutionContext, ToolResult, TurnCommand

ToolHandler = Callable[[ToolExecutionContext, BaseModel], ToolResult]


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueryArgs(StrictArgs):
    query: str = Field(min_length=1, max_length=500)


class IdsArgs(StrictArgs):
    ids: list[str] = Field(min_length=1, max_length=20)


class OfferArgs(StrictArgs):
    offer_id: str
    quote_id: str | None = None


class UpdateArgs(StrictArgs):
    operation: str
    item_id: str
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
    "list.update": (UpdateArgs, Risk.REVERSIBLE),
    "cart.update": (UpdateArgs, Risk.REVERSIBLE),
    "link.resolve": (OfferArgs, Risk.EXTERNAL_NAVIGATION),
    "vision.identify": (MediaArgs, Risk.CONSENT),
    "merchant.get_policy": (IdsArgs, Risk.READ),
}


class ToolRegistry:
    def __init__(self, handlers: Mapping[str, ToolHandler]) -> None:
        if set(handlers) != set(FROZEN_TOOL_TYPES):
            raise ValueError("handlers must implement exactly the ten frozen tools")
        self.specs = {
            name: ToolSpec(name, values[0], values[1], handlers[name])
            for name, values in FROZEN_TOOL_TYPES.items()
        }

    def execute(
        self, command: TurnCommand, call: ToolCall, context: ToolExecutionContext
    ) -> ToolResult:
        spec = self.specs.get(call.name)
        if spec is None:
            raise ValueError("tool is not registered")
        if spec.risk is Risk.REVERSIBLE and (
            not command.allow_reversible_writes or call.name not in command.approved_tools
        ):
            raise ToolDenied("reversible write was not authorized")
        if (
            spec.risk in {Risk.CONSENT, Risk.EXTERNAL_NAVIGATION}
            and call.name not in command.approved_tools
        ):
            raise ToolDenied("explicit approval is required")
        arguments = spec.args_type.model_validate(dict(call.arguments))
        return spec.handler(context, arguments)
