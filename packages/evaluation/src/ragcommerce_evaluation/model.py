"""Frozen evaluation case and result contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Family = Literal["shopping", "multi_turn", "multimodal", "quote_failure", "security"]
Split = Literal["dev", "test", "heldout"]


@dataclass(frozen=True, slots=True)
class ExpectedBehavior:
    outcome: str
    allowed_tools: tuple[str, ...]
    forbidden_tools: tuple[str, ...]
    requires_approval: bool
    minimum_evidence_refs: int
    commercial_facts_allowed: bool
    https_links_only: bool

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ExpectedBehavior:
        return cls(
            outcome=str(value["outcome"]),
            allowed_tools=tuple(value["allowed_tools"]),
            forbidden_tools=tuple(value["forbidden_tools"]),
            requires_approval=bool(value["requires_approval"]),
            minimum_evidence_refs=int(value["minimum_evidence_refs"]),
            commercial_facts_allowed=bool(value["commercial_facts_allowed"]),
            https_links_only=bool(value["https_links_only"]),
        )


@dataclass(frozen=True, slots=True)
class EvalCase:
    case_id: str
    family: Family
    split: Split
    turns: tuple[str, ...]
    media: tuple[dict[str, str], ...]
    injected_faults: tuple[str, ...]
    risk_tags: tuple[str, ...]
    expected: ExpectedBehavior

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> EvalCase:
        if value.get("schema_version") != 1:
            raise ValueError("unsupported case schema")
        if value.get("split") == "heldout" or "expected" not in value:
            raise ValueError("blinded held-out cases cannot be executed by the local runner")
        turns = tuple(str(item) for item in value["turns"])
        if not turns or any(not item.strip() for item in turns):
            raise ValueError("case turns must be non-empty")
        return cls(
            case_id=str(value["case_id"]),
            family=value["family"],
            split=value["split"],
            turns=turns,
            media=tuple(value.get("media", [])),
            injected_faults=tuple(value.get("injected_faults", [])),
            risk_tags=tuple(value.get("risk_tags", [])),
            expected=ExpectedBehavior.from_dict(value["expected"]),
        )


@dataclass(frozen=True, slots=True)
class EvalResult:
    case_id: str
    outcome: str
    tool_calls: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    commercial_facts: tuple[dict[str, Any], ...]
    approval_requested: bool
    deep_links: tuple[str, ...]
    exposed_sensitive_fields: tuple[str, ...]
    latency_ms: int
    estimated_cost_microunits: int
    error: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> EvalResult:
        return cls(
            case_id=str(value["case_id"]),
            outcome=str(value["outcome"]),
            tool_calls=tuple(value.get("tool_calls", [])),
            evidence_refs=tuple(value.get("evidence_refs", [])),
            commercial_facts=tuple(value.get("commercial_facts", [])),
            approval_requested=bool(value.get("approval_requested", False)),
            deep_links=tuple(value.get("deep_links", [])),
            exposed_sensitive_fields=tuple(value.get("exposed_sensitive_fields", [])),
            latency_ms=int(value.get("latency_ms", 0)),
            estimated_cost_microunits=int(value.get("estimated_cost_microunits", 0)),
            error=value.get("error"),
        )
