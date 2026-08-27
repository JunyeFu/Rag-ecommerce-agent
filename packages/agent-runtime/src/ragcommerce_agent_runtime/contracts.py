"""Stable Agent command, event, tool, and stop contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class EventType(StrEnum):
    RUN_STARTED = "run_started"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    EVIDENCE = "evidence"
    APPROVAL_REQUIRED = "approval_required"
    MESSAGE = "message"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class MediaRef:
    id: UUID
    kind: str


@dataclass(frozen=True, slots=True)
class TurnCommand:
    user_id: UUID
    thread_id: UUID
    run_id: UUID
    idempotency_key: str
    text: str = ""
    media: tuple[MediaRef, ...] = ()
    approved_tools: frozenset[str] = frozenset()
    allow_reversible_writes: bool = False
    consent_preference_memory: bool = False

    def __post_init__(self) -> None:
        if not self.idempotency_key.strip() or len(self.idempotency_key) > 128:
            raise ValueError("idempotency_key must contain 1..128 characters")
        if len(self.text) > 10_000:
            raise ValueError("turn text exceeds 10000 characters")
        if len(self.media) > 8:
            raise ValueError("a turn may reference at most 8 media objects")


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    agent_version: str
    model_version: str
    prompt_version: str
    policy_version: str
    contract_version: str

    def __post_init__(self) -> None:
        for name in (
            "agent_version",
            "model_version",
            "prompt_version",
            "policy_version",
            "contract_version",
        ):
            value = getattr(self, name)
            if not value.strip() or len(value) > 128:
                raise ValueError(f"{name} must contain 1..128 characters")


@dataclass(frozen=True, slots=True)
class AgentEvent:
    id: int
    type: EventType
    run_id: UUID
    data: Mapping[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ToolEvidence:
    ref: str
    sha256: str
    fields: tuple[str, ...]

    def __post_init__(self) -> None:
        normalized = self.sha256.lower()
        if not self.ref.strip() or len(self.ref) > 512:
            raise ValueError("evidence ref must contain 1..512 characters")
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("evidence sha256 must be a SHA-256 hex digest")
        if not self.fields or any(not field_name.strip() for field_name in self.fields):
            raise ValueError("evidence fields must be non-empty")
        object.__setattr__(self, "sha256", normalized)


@dataclass(frozen=True, slots=True)
class ToolResult:
    public_data: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[ToolEvidence, ...] = ()
    commercial_fact_fields: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    user_id: UUID
    thread_id: UUID
    run_id: UUID
    invocation_id: UUID
    idempotency_key: str


class StopReason(StrEnum):
    COMPLETED = "COMPLETED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    TOOL_LIMIT = "TOOL_LIMIT"
    REPLAN_LIMIT = "REPLAN_LIMIT"
    INVALID_INPUT = "INVALID_INPUT"
    TOOL_FAILURE = "TOOL_FAILURE"
