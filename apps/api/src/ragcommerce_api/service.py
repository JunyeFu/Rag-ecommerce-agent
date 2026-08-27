"""Thin API application service that delegates every turn to ShoppingAgent."""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from ragcommerce_agent_runtime import AgentEvent, EventType, MediaRef, TurnCommand

from .media import InMemoryMediaStore


class AgentPort(Protocol):
    def handle(self, command: TurnCommand) -> AsyncIterator[AgentEvent]: ...

    def replay(self, run_id: UUID) -> tuple[AgentEvent, ...]: ...


class OwnershipError(LookupError):
    pass


class IdempotencyConflict(ValueError):
    pass


class DecisionConflict(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ThreadRecord:
    id: UUID
    mission_id: UUID
    owner_id: UUID
    goal: str


@dataclass(slots=True)
class TurnRecord:
    owner_id: UUID
    thread_id: UUID
    run_id: UUID
    idempotency_key: str
    fingerprint: str
    command: TurnCommand
    execution_status: str = "RUNNING"
    events: list[AgentEvent] = field(default_factory=list)


class TurnIndex(Protocol):
    def create_thread(self, record: ThreadRecord) -> None: ...

    def get_thread(self, thread_id: UUID) -> ThreadRecord | None: ...

    def reserve(self, record: TurnRecord) -> tuple[TurnRecord, bool]: ...

    def get_run(self, run_id: UUID) -> TurnRecord | None: ...

    def update_status(self, run_id: UUID, value: str) -> None: ...

    def delete_user(self, user_id: UUID) -> int: ...


class InMemoryTurnIndex:
    def __init__(self) -> None:
        self.threads: dict[UUID, ThreadRecord] = {}
        self.turns: dict[tuple[UUID, UUID, str], TurnRecord] = {}
        self.runs: dict[UUID, TurnRecord] = {}

    def create_thread(self, record: ThreadRecord) -> None:
        self.threads[record.id] = record

    def get_thread(self, thread_id: UUID) -> ThreadRecord | None:
        return self.threads.get(thread_id)

    def reserve(self, record: TurnRecord) -> tuple[TurnRecord, bool]:
        key = (record.owner_id, record.thread_id, record.idempotency_key)
        existing = self.turns.get(key)
        if existing is not None:
            return existing, False
        self.turns[key] = record
        self.runs[record.run_id] = record
        return record, True

    def get_run(self, run_id: UUID) -> TurnRecord | None:
        return self.runs.get(run_id)

    def update_status(self, run_id: UUID, value: str) -> None:
        self.runs[run_id].execution_status = value

    def delete_user(self, user_id: UUID) -> int:
        thread_ids = {
            thread_id for thread_id, record in self.threads.items() if record.owner_id == user_id
        }
        turn_keys = [key for key, record in self.turns.items() if record.owner_id == user_id]
        run_ids = [run_id for run_id, record in self.runs.items() if record.owner_id == user_id]
        for thread_id in thread_ids:
            del self.threads[thread_id]
        for key in turn_keys:
            del self.turns[key]
        for run_id in run_ids:
            del self.runs[run_id]
        return len(thread_ids) + len(turn_keys) + len(run_ids)


def terminal_status(events: list[AgentEvent]) -> str:
    types = {event.type for event in events}
    if EventType.COMPLETED in types:
        return "COMPLETED"
    if EventType.FAILED in types:
        return "FAILED"
    if EventType.APPROVAL_REQUIRED in types:
        return "WAITING_APPROVAL"
    return "RUNNING"


class TurnService:
    def __init__(
        self,
        agent: AgentPort,
        media: InMemoryMediaStore,
        index: TurnIndex | None = None,
    ) -> None:
        self.agent = agent
        self.media = media
        self.index = index or InMemoryTurnIndex()

    def create_thread(self, owner_id: UUID, goal: str) -> ThreadRecord:
        normalized = goal.strip()
        if not normalized or len(normalized) > 500:
            raise ValueError("goal must contain 1..500 characters")
        record = ThreadRecord(uuid4(), uuid4(), owner_id, normalized)
        self.index.create_thread(record)
        return record

    def require_thread(self, owner_id: UUID, thread_id: UUID) -> ThreadRecord:
        record = self.index.get_thread(thread_id)
        if record is None or record.owner_id != owner_id:
            raise OwnershipError("thread not found")
        return record

    async def submit(
        self,
        owner_id: UUID,
        thread_id: UUID,
        idempotency_key: str,
        text: str,
        media_ids: tuple[UUID, ...],
    ) -> tuple[TurnRecord, bool]:
        self.require_thread(owner_id, thread_id)
        if not idempotency_key.strip() or len(idempotency_key) > 128:
            raise ValueError("Idempotency-Key must contain 1..128 characters")
        if len(media_ids) != len(set(media_ids)) or len(media_ids) > 8:
            raise ValueError("media references must be unique and contain at most 8 items")
        media = self.media.require_owned(owner_id, media_ids)
        fingerprint = hashlib.sha256(
            json.dumps(
                {"text": text, "media_ids": sorted(str(value) for value in media_ids)},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        run_id = uuid5(NAMESPACE_URL, f"urn:rag-commerce:{owner_id}:{thread_id}:{idempotency_key}")
        command = TurnCommand(
            owner_id,
            thread_id,
            run_id,
            idempotency_key,
            text,
            tuple(MediaRef(item.id, item.kind) for item in media),
        )
        candidate = TurnRecord(owner_id, thread_id, run_id, idempotency_key, fingerprint, command)
        record, created = self.index.reserve(candidate)
        if record.fingerprint != fingerprint:
            raise IdempotencyConflict("Idempotency-Key is bound to a different request")
        if not created:
            record.events = list(self.agent.replay(record.run_id))
            return record, True
        record.events = [event async for event in self.agent.handle(command)]
        record.execution_status = terminal_status(record.events)
        self.index.update_status(record.run_id, record.execution_status)
        return record, False

    def require_run(self, owner_id: UUID, run_id: UUID) -> TurnRecord:
        record = self.index.get_run(run_id)
        if record is None or record.owner_id != owner_id:
            raise OwnershipError("Agent run not found")
        record.events = list(self.agent.replay(run_id))
        return record

    async def decide(
        self, owner_id: UUID, run_id: UUID, tool_name: str, approved: bool
    ) -> TurnRecord:
        record = self.require_run(owner_id, run_id)
        pending = next(
            (
                event
                for event in reversed(record.events)
                if event.type is EventType.APPROVAL_REQUIRED
            ),
            None,
        )
        if pending is None or pending.data.get("tool") != tool_name:
            raise DecisionConflict("run does not have a matching pending approval")
        if not approved:
            return record
        command = TurnCommand(
            record.command.user_id,
            record.command.thread_id,
            record.command.run_id,
            record.command.idempotency_key,
            record.command.text,
            record.command.media,
            frozenset({tool_name}),
            allow_reversible_writes=True,
            consent_preference_memory=record.command.consent_preference_memory,
        )
        record.command = command
        record.events = [event async for event in self.agent.handle(command)]
        record.execution_status = terminal_status(record.events)
        self.index.update_status(record.run_id, record.execution_status)
        return record


def public_event(event: AgentEvent) -> tuple[str, dict[str, object]]:
    data = event.data
    if event.type in {
        EventType.RUN_STARTED,
        EventType.TOOL_STARTED,
        EventType.TOOL_COMPLETED,
        EventType.TOOL_FAILED,
    }:
        payload: dict[str, object] = {"stage": event.type.value}
        if isinstance(data.get("tool"), str):
            payload["tool"] = data["tool"]
        return "status", payload
    if event.type is EventType.MESSAGE:
        return "message_delta", {"text": str(data.get("text", ""))}
    if event.type is EventType.EVIDENCE:
        return "evidence", {
            "ref": str(data["ref"]),
            "sha256": str(data["sha256"]),
            "fields": list(data["fields"]),
        }
    if event.type is EventType.APPROVAL_REQUIRED:
        return "approval_required", {
            "tool": str(data["tool"]),
            "reason": str(data["reason"]),
        }
    if event.type is EventType.COMPLETED:
        return "completed", {"reason": str(data["reason"])}
    return "failed", {
        "reason": str(data.get("reason", "TOOL_FAILURE")),
        "summary": str(data.get("summary", data.get("error_type", "failed"))),
    }
