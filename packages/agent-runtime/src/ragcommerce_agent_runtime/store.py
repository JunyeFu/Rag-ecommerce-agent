"""Checkpoint contract with an in-memory deterministic implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from .contracts import AgentEvent, RuntimeIdentity, ToolResult, TurnCommand


@dataclass(slots=True)
class RunCheckpoint:
    run_id: UUID
    idempotency_key: str
    events: list[AgentEvent] = field(default_factory=list)
    completed_tools: dict[str, ToolResult] = field(default_factory=dict)
    preferences: dict[str, str] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    tool_attempts: int = 0
    replans: int = 0


class CheckpointStore(Protocol):
    def begin_run(
        self, command: TurnCommand, identity: RuntimeIdentity, created_at: datetime
    ) -> None: ...
    def load(self, run_id: UUID) -> RunCheckpoint | None: ...
    def save(self, checkpoint: RunCheckpoint) -> None: ...
    def save_preferences(self, user_id: UUID, values: dict[str, str], consent: bool) -> None: ...
    def load_preferences(self, user_id: UUID) -> dict[str, str]: ...
    def delete_user(self, user_id: UUID) -> int: ...


class InMemoryCheckpointStore:
    def __init__(self) -> None:
        self.runs: dict[UUID, RunCheckpoint] = {}
        self.user_preferences: dict[UUID, dict[str, str]] = {}
        self.run_metadata: dict[UUID, tuple[TurnCommand, RuntimeIdentity, datetime]] = {}

    def begin_run(
        self, command: TurnCommand, identity: RuntimeIdentity, created_at: datetime
    ) -> None:
        self.run_metadata.setdefault(command.run_id, (command, identity, created_at))

    def load(self, run_id: UUID) -> RunCheckpoint | None:
        return self.runs.get(run_id)

    def save(self, checkpoint: RunCheckpoint) -> None:
        self.runs[checkpoint.run_id] = checkpoint

    def save_preferences(self, user_id: UUID, values: dict[str, str], consent: bool) -> None:
        if consent:
            self.user_preferences[user_id] = dict(values)

    def load_preferences(self, user_id: UUID) -> dict[str, str]:
        return dict(self.user_preferences.get(user_id, {}))

    def delete_user(self, user_id: UUID) -> int:
        count = int(user_id in self.user_preferences)
        self.user_preferences.pop(user_id, None)
        run_ids = [
            run_id
            for run_id, (command, _, _) in self.run_metadata.items()
            if command.user_id == user_id
        ]
        for run_id in run_ids:
            count += int(run_id in self.runs)
            self.runs.pop(run_id, None)
            del self.run_metadata[run_id]
            count += 1
        return count
