"""Thin API application service that delegates every turn to ShoppingAgent."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from threading import Lock
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from ragcommerce_agent_runtime import (
    AgentEvent,
    EventType,
    MediaRef,
    TurnCommand,
    parse_shopping_mission,
)
from ragcommerce_contracts import (
    ComparisonSelection,
    ConversationMessage,
    ProductCandidateView,
    RecommendationRouteView,
    ShoppingMissionView,
    ThreadHistoryEntry,
    ThreadSnapshot,
)

from .media import InMemoryMediaStore


class AgentPort(Protocol):
    def handle(self, command: TurnCommand) -> AsyncIterator[AgentEvent]: ...

    def replay(self, run_id: UUID) -> tuple[AgentEvent, ...]: ...

    def reject_approval(self, command: TurnCommand, tool_name: str) -> tuple[AgentEvent, ...]: ...


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
    mission_version: int = 1
    selected_product_ids: tuple[UUID, ...] = ()
    mode: str = "PURCHASE"
    exploration: dict | None = None
    experience: dict = field(default_factory=dict)


@dataclass(slots=True)
class TurnRecord:
    owner_id: UUID
    thread_id: UUID
    run_id: UUID
    idempotency_key: str
    fingerprint: str
    command: TurnCommand
    execution_status: str = "PENDING"
    events: list[AgentEvent] = field(default_factory=list)


class TurnIndex(Protocol):
    def list_threads(self, owner_id: UUID) -> list[ThreadRecord]: ...

    def turns_for_thread(self, owner_id: UUID, thread_id: UUID) -> list[TurnRecord]: ...

    def update_experience(
        self, owner_id: UUID, thread_id: UUID, change: Callable
    ) -> ThreadRecord: ...

    def owner_guard(self, owner_id: UUID, blocking: bool = True) -> AbstractContextManager: ...

    def has_active(self, owner_id: UUID) -> bool: ...

    def execution_guard(self, run_id: UUID) -> AbstractContextManager: ...

    def mission_guard(self, thread_id: UUID) -> AbstractContextManager[None]: ...

    def create_thread(self, record: ThreadRecord) -> None: ...

    def get_thread(self, thread_id: UUID) -> ThreadRecord | None: ...

    def reserve(
        self, record: TurnRecord, transition: Callable | None = None
    ) -> tuple[TurnRecord, bool]: ...

    def get_run(self, run_id: UUID) -> TurnRecord | None: ...

    def latest_for_thread(self, owner_id: UUID, thread_id: UUID) -> TurnRecord | None: ...

    def run_ids_for_mission(
        self, owner_id: UUID, thread_id: UUID, version: int
    ) -> tuple[UUID, ...]: ...

    def update_status(self, run_id: UUID, value: str) -> None: ...

    def enqueue_approval(self, command: TurnCommand) -> None: ...

    def update_goal(self, owner_id: UUID, thread_id: UUID, goal: str) -> ThreadRecord: ...

    def update_comparison(
        self,
        owner_id: UUID,
        thread_id: UUID,
        product_ids: tuple[UUID, ...],
    ) -> ThreadRecord: ...

    def claim(self, run_id: UUID) -> TurnRecord | None: ...

    def delete_user(self, user_id: UUID) -> int: ...


class InMemoryTurnIndex:
    def __init__(self) -> None:
        self.threads: dict[UUID, ThreadRecord] = {}
        self.turns: dict[tuple[UUID, UUID, str], TurnRecord] = {}
        self.runs: dict[UUID, TurnRecord] = {}
        self.mission_locks: dict[UUID, Lock] = {}
        self.owner_locks: dict[UUID, Lock] = {}
        self.execution_locks: dict[UUID, Lock] = {}
        self.held_owners = ContextVar("held_owners", default=frozenset())

    @contextmanager
    def owner_guard(self, owner_id, blocking=True):
        if owner_id in self.held_owners.get():
            yield
            return
        lock = self.owner_locks.setdefault(owner_id, Lock())
        if not lock.acquire(blocking=blocking):
            raise DecisionConflict("user data operation in progress")
        token = self.held_owners.set(self.held_owners.get() | {owner_id})
        try:
            yield
        finally:
            self.held_owners.reset(token)
            lock.release()

    @contextmanager
    def execution_guard(self, run_id):
        lock = self.execution_locks.setdefault(run_id, Lock())
        if not lock.acquire(blocking=False):
            raise DecisionConflict("run is already executing")
        try:
            yield
        finally:
            lock.release()

    def has_active(self, owner_id):
        return any(
            r.owner_id == owner_id and r.execution_status in {"PENDING", "RETRY", "RUNNING"}
            for r in self.runs.values()
        )

    @contextmanager
    def mission_guard(self, thread_id: UUID) -> Iterator[None]:
        lock = self.mission_locks.setdefault(thread_id, Lock())
        if not lock.acquire(blocking=False):
            raise DecisionConflict("Mission update or approval is already in progress")
        try:
            yield
        finally:
            lock.release()

    def create_thread(self, record: ThreadRecord) -> None:
        with self.owner_guard(record.owner_id):
            self.threads[record.id] = record

    def list_threads(self, owner_id: UUID) -> list[ThreadRecord]:
        return [
            record
            for record in reversed(tuple(self.threads.values()))
            if record.owner_id == owner_id
        ]

    def turns_for_thread(self, owner_id: UUID, thread_id: UUID) -> list[TurnRecord]:
        return [
            record
            for record in self.runs.values()
            if record.owner_id == owner_id and record.thread_id == thread_id
        ]

    def update_experience(self, owner_id: UUID, thread_id: UUID, change: Callable) -> ThreadRecord:
        with self.owner_guard(owner_id), self.mission_guard(thread_id):
            record = self.threads.get(thread_id)
            if record is None or record.owner_id != owner_id:
                raise OwnershipError("thread not found")
            self._require_no_approved_job(owner_id, thread_id)
            updated = change(record)
            self.threads[thread_id] = updated
            return updated

    def get_thread(self, thread_id: UUID) -> ThreadRecord | None:
        return self.threads.get(thread_id)

    def reserve(
        self, record: TurnRecord, transition: Callable | None = None
    ) -> tuple[TurnRecord, bool]:
        with self.owner_guard(record.owner_id):
            if transition is not None:
                with self.mission_guard(record.thread_id):
                    return self._reserve(record, transition)
            return self._reserve(record)

    def _reserve(
        self, record: TurnRecord, transition: Callable | None = None
    ) -> tuple[TurnRecord, bool]:
        key = (record.owner_id, record.thread_id, record.idempotency_key)
        existing = self.turns.get(key)
        if existing is not None:
            return existing, False
        self._require_no_approved_job(record.owner_id, record.thread_id)
        thread = self.threads.get(record.thread_id)
        if thread is None or thread.owner_id != record.owner_id:
            raise OwnershipError("thread not found")
        if transition is not None:
            from .exploration import result_for

            thread = transition(thread)
            self.threads[thread.id] = thread
            record.command = replace(
                record.command,
                text=thread.goal,
                exploration_result=None
                if record.command.media_confirmation
                else result_for(thread),
            )
        elif thread.mode == "DISCOVERY":
            raise ValueError("Select a direction or start a new shopping task before sending text")
        previous = self.latest_for_thread(record.owner_id, record.thread_id)
        if (
            transition is None
            and previous is not None
            and previous.execution_status == "WAITING_CLARIFICATION"
            and previous.command.mission_version == thread.mission_version
        ):
            thread = self.update_goal(
                record.owner_id,
                record.thread_id,
                f"{thread.goal}; {record.command.text.strip()}"[:500],
            )
            record.command = replace(record.command, text=thread.goal)
        record.command = replace(
            record.command,
            mission_version=thread.mission_version,
            mission_goal=thread.goal,
            recommendation_feedback=dict(thread.experience.get("feedback", {})),
            excluded_product_ids=tuple(
                key.removeprefix("PRODUCT:")
                for key in thread.experience.get("feedback", {})
                if key.startswith("PRODUCT:")
            ),
            excluded_categories=tuple(
                key.removeprefix("CATEGORY:")
                for key in thread.experience.get("feedback", {})
                if key.startswith("CATEGORY:")
            ),
        )
        self.turns[key] = record
        self.runs[record.run_id] = record
        return record, True

    def get_run(self, run_id: UUID) -> TurnRecord | None:
        return self.runs.get(run_id)

    def latest_for_thread(self, owner_id: UUID, thread_id: UUID) -> TurnRecord | None:
        values = [
            record
            for record in self.runs.values()
            if record.owner_id == owner_id and record.thread_id == thread_id
        ]
        return values[-1] if values else None

    def run_ids_for_mission(
        self, owner_id: UUID, thread_id: UUID, version: int
    ) -> tuple[UUID, ...]:
        return tuple(
            record.run_id
            for record in reversed(tuple(self.runs.values()))
            if record.owner_id == owner_id
            and record.thread_id == thread_id
            and record.command.mission_version == version
        )

    def update_status(self, run_id: UUID, value: str) -> None:
        self.runs[run_id].execution_status = value

    def enqueue_approval(self, command: TurnCommand) -> None:
        with self.owner_guard(command.user_id):
            record = self.runs[command.run_id]
            if record.execution_status != "WAITING_APPROVAL":
                raise DecisionConflict("approval is no longer pending")
            record.command = command
            record.execution_status = "PENDING"

    def _require_no_approved_job(self, owner_id: UUID, thread_id: UUID) -> None:
        if any(
            run.owner_id == owner_id
            and run.thread_id == thread_id
            and run.command.approved_tools
            and run.execution_status in {"PENDING", "RETRY", "RUNNING"}
            for run in self.runs.values()
        ):
            raise DecisionConflict("an approved operation is still executing")

    def update_goal(self, owner_id: UUID, thread_id: UUID, goal: str) -> ThreadRecord:
        with self.owner_guard(owner_id), self.mission_guard(thread_id):
            return self._update_goal(owner_id, thread_id, goal)

    def _update_goal(self, owner_id: UUID, thread_id: UUID, goal: str) -> ThreadRecord:
        record = self.threads.get(thread_id)
        if record is None or record.owner_id != owner_id:
            raise OwnershipError("thread not found")
        self._require_no_approved_job(owner_id, thread_id)
        updated = replace(
            record,
            goal=goal,
            mission_version=record.mission_version + 1,
            selected_product_ids=(),
            mode="PURCHASE",
        )
        self.threads[thread_id] = updated
        return updated

    def update_comparison(
        self,
        owner_id: UUID,
        thread_id: UUID,
        product_ids: tuple[UUID, ...],
    ) -> ThreadRecord:
        with self.owner_guard(owner_id):
            record = self.threads.get(thread_id)
            if record is None or record.owner_id != owner_id:
                raise OwnershipError("thread not found")
            updated = replace(record, selected_product_ids=product_ids)
            self.threads[thread_id] = updated
            return updated

    def claim(self, run_id: UUID) -> TurnRecord | None:
        record = self.runs.get(run_id)
        if record is None or record.execution_status not in {"PENDING", "RETRY"}:
            return None
        record.execution_status = "RUNNING"
        return record

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
    if EventType.CLARIFICATION_REQUIRED in types:
        return "WAITING_CLARIFICATION"
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

    def snapshot(self, owner_id: UUID, thread_id: UUID) -> ThreadSnapshot:
        thread = self.require_thread(owner_id, thread_id)
        turn = self.index.latest_for_thread(owner_id, thread_id)
        if turn is None or turn.command.mission_version != thread.mission_version:
            return ThreadSnapshot(
                experience=thread.experience,
                mode=thread.mode,
                exploration=thread.exploration,
                thread_id=thread.id,
                mission_id=thread.mission_id,
                goal=thread.goal,
                status="IDLE",
                last_event_id=0,
                candidates=[],
                recommendation_routes=[],
                selected_product_ids=list(thread.selected_product_ids),
                mission=ShoppingMissionView.model_validate(
                    parse_shopping_mission(thread.goal, version=thread.mission_version)
                ),
            )
        events = list(self.agent.replay(turn.run_id))
        candidates: list[ProductCandidateView] = []
        routes: list[RecommendationRouteView] = []
        for run_id in self.index.run_ids_for_mission(owner_id, thread_id, thread.mission_version):
            run_events = events if run_id == turn.run_id else self.agent.replay(run_id)
            product_event = next(
                (event for event in reversed(run_events) if event.type is EventType.PRODUCTS), None
            )
            if product_event is None:
                continue
            candidates = [
                ProductCandidateView.model_validate(value)
                for value in product_event.data.get("products", [])
                if isinstance(value, dict)
            ]
            routes = [
                RecommendationRouteView.model_validate(value)
                for value in product_event.data.get("recommendation_routes", [])
                if isinstance(value, dict)
            ]
            break
        pending = next(
            (
                str(event.data.get("tool"))
                for event in reversed(events)
                if event.type is EventType.APPROVAL_REQUIRED
            ),
            None,
        )
        pending_arguments = next(
            (
                dict(event.data.get("arguments", {}))
                for event in reversed(events)
                if event.type is EventType.APPROVAL_REQUIRED
            ),
            {},
        )
        # The persisted Thread owns the shopping goal. A cart/list action is
        # a Turn request, not an implicit replacement of that goal.
        mission_data = parse_shopping_mission(thread.goal, version=thread.mission_version)
        active_status = terminal_status(events)
        if pending in turn.command.approved_tools and turn.execution_status in {
            "PENDING",
            "RETRY",
            "RUNNING",
        }:
            active_status = "RUNNING"
        return ThreadSnapshot(
            experience=thread.experience,
            mode=thread.mode,
            exploration=thread.exploration,
            pending_media_interpretations=[
                dict(event.data) for event in events if event.type is EventType.MEDIA_INTERPRETED
            ]
            if terminal_status(events) == "WAITING_CLARIFICATION"
            else [],
            thread_id=thread.id,
            mission_id=thread.mission_id,
            goal=thread.goal,
            status=active_status,
            last_event_id=events[-1].id if events else 0,
            active_run_id=turn.run_id,
            pending_action=pending if active_status == "WAITING_APPROVAL" else None,
            pending_action_arguments=pending_arguments
            if active_status == "WAITING_APPROVAL"
            else {},
            candidates=candidates,
            recommendation_routes=routes,
            selected_product_ids=list(thread.selected_product_ids),
            mission=ShoppingMissionView.model_validate(mission_data),
        )

    def history(self, owner_id: UUID):
        return [
            ThreadHistoryEntry(
                thread_id=record.id,
                goal=record.goal,
                experience=record.experience,
                mode=record.mode,
            )
            for record in self.index.list_threads(owner_id)
        ]

    def organize(self, owner_id: UUID, thread_id: UUID, request):
        self.require_thread(owner_id, thread_id)
        values = request.model_dump(exclude_none=True)
        if not values:
            raise ValueError("Choose a title or archive state")
        if "title" in values:
            values["title"] = values["title"].strip()
            if not values["title"]:
                raise ValueError("Title cannot be blank")
        self.index.update_experience(
            owner_id,
            thread_id,
            lambda record: replace(record, experience={**record.experience, **values}),
        )
        return self.snapshot(owner_id, thread_id)

    def feedback(self, owner_id: UUID, thread_id: UUID, request, category: str):
        thread = self.require_thread(owner_id, thread_id)
        key = (
            f"PRODUCT:{request.product_id}"
            if request.scope == "PRODUCT"
            else f"CATEGORY:{category}"
        )
        if not request.undo and request.product_id not in {
            p.product_id for p in self.snapshot(owner_id, thread_id).candidates
        }:
            raise ValueError("Feedback target was not offered in this task")
        if request.undo and key not in thread.experience.get("feedback", {}):
            raise ValueError("Feedback is not active")

        def change(current):
            if current.mission_version != request.expected_mission_version:
                raise DecisionConflict("Feedback belongs to an earlier task version")
            feedback = dict(current.experience.get("feedback", {}))
            if request.undo:
                feedback.pop(key)
            else:
                feedback[key] = request.reason
            return replace(
                current,
                experience={**current.experience, "feedback": feedback},
                mission_version=current.mission_version + 1,
                selected_product_ids=(),
            )

        self.index.update_experience(owner_id, thread_id, change)
        return self.snapshot(owner_id, thread_id)

    def messages(self, owner_id: UUID, thread_id: UUID, offset: int = 0, limit: int = 50):
        self.require_thread(owner_id, thread_id)
        result = []
        for turn in self.index.turns_for_thread(owner_id, thread_id):
            text = (
                turn.command.submitted_text
                if turn.command.submitted_text is not None
                else turn.command.text
            )
            if text:
                result.append(ConversationMessage(run_id=turn.run_id, role="user", text=text))
            if turn.command.approved_tools - {"vision.identify", "audio.transcribe"}:
                result.append(
                    ConversationMessage(
                        run_id=turn.run_id, role="system", text="用户已确认本轮指定操作"
                    )
                )
            for event in self.agent.replay(turn.run_id):
                if event.type is EventType.MESSAGE and event.data.get("text"):
                    result.append(
                        ConversationMessage(
                            run_id=turn.run_id, role="assistant", text=str(event.data["text"])
                        )
                    )
                elif event.type is EventType.CLARIFICATION_REQUIRED and event.data.get("question"):
                    result.append(
                        ConversationMessage(
                            run_id=turn.run_id, role="assistant", text=str(event.data["question"])
                        )
                    )
                elif (
                    event.type is EventType.COMPLETED
                    and event.data.get("reason") == "approval_rejected"
                ):
                    result.append(
                        ConversationMessage(
                            run_id=turn.run_id,
                            role="system",
                            text="用户拒绝了操作，未执行写入",  # noqa: RUF001
                        )
                    )
        return result[offset : offset + limit]

    def undo_feedback(self, owner_id: UUID, thread_id: UUID, key: str, version: int):
        self.require_thread(owner_id, thread_id)

        def change(current):
            if current.mission_version != version:
                raise DecisionConflict("Feedback belongs to an earlier task version")
            feedback = dict(current.experience.get("feedback", {}))
            if key not in feedback:
                raise ValueError("Feedback is not active")
            del feedback[key]
            return replace(
                current,
                experience={**current.experience, "feedback": feedback},
                mission_version=current.mission_version + 1,
                selected_product_ids=(),
            )

        self.index.update_experience(owner_id, thread_id, change)
        return self.snapshot(owner_id, thread_id)

    def update_mission(
        self,
        owner_id: UUID,
        thread_id: UUID,
        goal: str,
    ) -> ShoppingMissionView:
        normalized = goal.strip()
        if not normalized or len(normalized) > 500:
            raise ValueError("goal must contain 1..500 characters")
        thread = self.require_thread(owner_id, thread_id)
        if normalized == thread.goal:
            return ShoppingMissionView.model_validate(
                parse_shopping_mission(normalized, version=thread.mission_version)
            )
        updated = self.index.update_goal(owner_id, thread_id, normalized)
        return ShoppingMissionView.model_validate(
            parse_shopping_mission(normalized, version=updated.mission_version)
        )

    def comparison_selection(
        self,
        owner_id: UUID,
        thread_id: UUID,
    ) -> ComparisonSelection:
        thread = self.require_thread(owner_id, thread_id)
        return ComparisonSelection(product_ids=list(thread.selected_product_ids))

    def update_comparison_selection(
        self,
        owner_id: UUID,
        thread_id: UUID,
        product_ids: list[UUID],
    ) -> ComparisonSelection:
        if len(product_ids) != len(set(product_ids)) or len(product_ids) > 4:
            raise ValueError("comparison requires at most four unique products")
        thread = self.require_thread(owner_id, thread_id)
        candidates = {value.product_id for value in self.snapshot(owner_id, thread_id).candidates}
        if not set(product_ids).issubset(candidates):
            raise ValueError("comparison selection contains a product outside this Mission")
        if tuple(product_ids) != thread.selected_product_ids:
            thread = self.index.update_comparison(
                owner_id,
                thread_id,
                tuple(product_ids),
            )
        return ComparisonSelection(product_ids=list(thread.selected_product_ids))

    async def submit(
        self,
        owner_id: UUID,
        thread_id: UUID,
        idempotency_key: str,
        text: str,
        media_ids: tuple[UUID, ...],
        exploration_action=None,
        expected_mission_version: int | None = None,
        directions=(),
        media_confirmation=None,
    ) -> tuple[TurnRecord, bool]:
        return await asyncio.to_thread(
            self._submit,
            owner_id,
            thread_id,
            idempotency_key,
            text,
            media_ids,
            exploration_action,
            expected_mission_version,
            directions,
            media_confirmation,
        )

    def _submit(
        self,
        owner_id,
        thread_id,
        idempotency_key,
        text,
        media_ids,
        exploration_action,
        expected_mission_version,
        directions,
        media_confirmation,
    ) -> tuple[TurnRecord, bool]:
        thread = self.require_thread(owner_id, thread_id)
        if exploration_action is not None and (
            text or media_ids or expected_mission_version is None
        ):
            raise ValueError("Exploration requires a version and no text/media")
        if (
            exploration_action is None
            and media_confirmation is None
            and expected_mission_version is not None
        ):
            raise ValueError("expected_mission_version requires a versioned action")
        if media_confirmation is not None and (
            exploration_action or text or media_ids or expected_mission_version is None
        ):
            raise ValueError("Media confirmation requires a version and no text/media/exploration")
        if not idempotency_key.strip() or len(idempotency_key) > 128:
            raise ValueError("Idempotency-Key must contain 1..128 characters")
        if len(media_ids) != len(set(media_ids)) or len(media_ids) > 8:
            raise ValueError("media references must be unique and contain at most 8 items")
        media = self.media.require_owned(owner_id, media_ids)
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "text": text,
                    "media_ids": sorted(str(value) for value in media_ids),
                    **(
                        {
                            "exploration_action": exploration_action.model_dump(mode="json"),
                            "expected_mission_version": expected_mission_version,
                        }
                        if exploration_action is not None
                        else {}
                    ),
                    **(
                        {
                            "media_confirmation": media_confirmation.model_dump(mode="json"),
                            "expected_mission_version": expected_mission_version,
                        }
                        if media_confirmation is not None
                        else {}
                    ),
                },
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
            approved_invocations=frozenset(),
            approved_tools=frozenset(
                "vision.identify" if item.kind == "image" else "audio.transcribe" for item in media
            ),
            mission_version=thread.mission_version,
            media_confirmation=media_confirmation is not None,
            submitted_text=text,
        )
        candidate = TurnRecord(owner_id, thread_id, run_id, idempotency_key, fingerprint, command)
        if media_confirmation is not None:

            def confirm(current):
                source = self.require_run(owner_id, media_confirmation.source_run_id)
                latest = self.index.latest_for_thread(owner_id, thread_id)
                if (
                    current.mission_version != expected_mission_version
                    or source.thread_id != thread_id
                    or latest is None
                    or latest.run_id != source.run_id
                    or source.command.mission_version != current.mission_version
                    or source.execution_status != "WAITING_CLARIFICATION"
                    or not any(event.type is EventType.MEDIA_INTERPRETED for event in source.events)
                ):
                    raise DecisionConflict("media confirmation is stale or not pending")
                return replace(
                    current,
                    goal=media_confirmation.text.strip(),
                    mission_version=current.mission_version + 1,
                    selected_product_ids=(),
                    mode="PURCHASE",
                )

            record, created = self.index.reserve(candidate, confirm)
        elif exploration_action is not None:
            from .exploration import transition

            record, created = self.index.reserve(
                candidate,
                lambda current: transition(
                    current, exploration_action, expected_mission_version, directions
                ),
            )
        else:
            record, created = self.index.reserve(candidate)
        if record.fingerprint != fingerprint:
            raise IdempotencyConflict("Idempotency-Key is bound to a different request")
        if not created:
            record.events = list(self.agent.replay(record.run_id))
            return record, True
        return record, False

    async def execute(self, run_id: UUID) -> TurnRecord:
        record = self.index.claim(run_id)
        if record is None:
            existing = self.index.get_run(run_id)
            if existing is None:
                raise OwnershipError("Agent run not found")
            existing.events = list(self.agent.replay(existing.run_id))
            return existing
        return await self.execute_claimed(record)

    async def execute_claimed(self, record: TurnRecord) -> TurnRecord:
        with self.index.execution_guard(record.run_id):
            record.events = [event async for event in self.agent.handle(record.command)]
            record.execution_status = terminal_status(record.events)
            self.index.update_status(record.run_id, record.execution_status)
        return record

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
        with self.index.owner_guard(owner_id), self.index.mission_guard(record.thread_id):
            return await self._decide(owner_id, run_id, tool_name, approved)

    async def _decide(
        self, owner_id: UUID, run_id: UUID, tool_name: str, approved: bool
    ) -> TurnRecord:
        record = self.require_run(owner_id, run_id)
        thread = self.require_thread(owner_id, record.thread_id)
        if (
            record.execution_status != "COMPLETED"
            and record.command.mission_version != thread.mission_version
        ):
            raise DecisionConflict("approval belongs to an earlier Mission version")
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
        if tool_name in record.command.approved_tools and record.execution_status in {
            "PENDING",
            "RETRY",
            "RUNNING",
        }:
            if approved:
                return record
            raise DecisionConflict("approval is already accepted")
        terminal = next(
            (
                event
                for event in reversed(record.events)
                if event.type in {EventType.COMPLETED, EventType.FAILED}
            ),
            None,
        )
        if terminal is not None:
            rejected = terminal.data.get("reason") == "approval_rejected"
            if terminal.type is EventType.COMPLETED and approved != rejected:
                return record
            raise DecisionConflict("approval is already closed")
        if not approved:
            record.events = list(self.agent.reject_approval(record.command, tool_name))
            record.execution_status = terminal_status(record.events)
            self.index.update_status(record.run_id, record.execution_status)
            return record
        command = replace(
            record.command,
            mission_goal=thread.goal,
            approved_tools=record.command.approved_tools | {tool_name},
            allow_reversible_writes=True,
            approved_invocations=(record.command.approved_invocations or frozenset())
            | {str(pending.data["invocation_id"])},
        )
        self.index.enqueue_approval(command)
        record.command = command
        record.execution_status = "PENDING"
        return record


def public_event(event: AgentEvent) -> tuple[str, dict[str, object]]:
    data = event.data
    if event.type is EventType.MEDIA_INTERPRETED:
        return "media_interpreted", dict(data)
    if event.type is EventType.EXPLORATION_UPDATED:
        return "exploration_updated", dict(data)
    if event.type is EventType.MISSION_UPDATED:
        return "mission_updated", {
            "goal": str(data["goal"]),
            "status": str(data["status"]),
            "mission": ShoppingMissionView.model_validate(data["mission"]).model_dump(mode="json"),
        }
    if event.type in {
        EventType.RUN_STARTED,
        EventType.RUN_RESUMED,
        EventType.TOOL_STARTED,
        EventType.TOOL_COMPLETED,
        EventType.TOOL_FAILED,
    }:
        payload: dict[str, object] = {"stage": event.type.value}
        if isinstance(data.get("tool"), str):
            payload["tool"] = data["tool"]
        return "progress", payload
    if event.type in {EventType.PRODUCTS, EventType.OFFERS, EventType.COMPARISON}:
        return event.type.value, dict(data)
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
            "arguments": dict(data.get("arguments", {})),
        }
    if event.type is EventType.CLARIFICATION_REQUIRED:
        return "clarification_required", {"question": str(data["question"])}
    if event.type is EventType.COMPLETED:
        return "completed", {"reason": str(data["reason"])}
    return "failed", {
        "reason": str(data.get("reason", "TOOL_FAILURE")),
        "summary": str(data.get("summary", data.get("error_type", "failed"))),
    }
