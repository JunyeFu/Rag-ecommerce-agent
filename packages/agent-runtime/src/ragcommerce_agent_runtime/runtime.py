"""Single LangGraph-backed shopping runtime with bounded typed tools."""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, TypedDict
from uuid import NAMESPACE_URL, UUID, uuid5

from langgraph.graph import END, START, StateGraph

from .contracts import (
    AgentEvent,
    EventType,
    RuntimeIdentity,
    StopReason,
    ToolCall,
    ToolExecutionContext,
    ToolResult,
    TurnCommand,
)
from .mission import parse_shopping_mission
from .model_provider import (
    ModelProvider,
    ProviderError,
    ProviderInvalidResponse,
    ProviderUnsupportedAmount,
)
from .store import CheckpointStore, RunCheckpoint
from .tools import Risk, ToolDenied, ToolRegistry


class AgentState(TypedDict):
    command: TurnCommand
    calls: tuple[ToolCall, ...]
    results: tuple[ToolResult, ...]
    checkpoint: RunCheckpoint
    stop_reason: StopReason | None
    replans: int


OFFER_FACT_FIELDS = frozenset(
    {
        "price_minor",
        "shipping_minor",
        "availability",
        "merchant_name",
        "source_ref",
        "verification",
    }
)


def _offer_evidence_error(result: ToolResult) -> str | None:
    offers = result.public_data.get("offers")
    if offers is None:
        return None
    if not isinstance(offers, list):
        return "offers payload is not a list"
    if not result.commercial_fact_fields >= OFFER_FACT_FIELDS:
        return "offer commercial facts were not declared"
    for offer in offers:
        if not isinstance(offer, dict):
            return "offer payload is not an object"
        source_ref = offer.get("source_ref")
        evidence = next((item for item in result.evidence if item.ref == source_ref), None)
        if evidence is None or not set(evidence.fields) >= OFFER_FACT_FIELDS:
            return "offer commercial fact lacks matching source evidence"
        expires_at = offer.get("expires_at")
        if not isinstance(expires_at, str):
            return "offer expiry is missing"
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            return "offer expiry is invalid"
        if expiry <= datetime.now(UTC):
            return "offer is expired"
    return None


class ShoppingAgent:
    MAX_TOOLS = 8
    MAX_REPLANS = 2

    def __init__(
        self,
        planner: ModelProvider,
        tools: ToolRegistry,
        store: CheckpointStore,
        identity: RuntimeIdentity,
    ) -> None:
        self.planner = planner
        self.tools = tools
        self.store = store
        self.identity = identity
        graph = StateGraph(AgentState)
        graph.add_node("guard", self._guard)
        graph.add_node("plan", self._plan)
        graph.add_node("tools", self._tools)
        graph.add_node("respond", self._respond)
        graph.add_edge(START, "guard")
        graph.add_edge("guard", "plan")
        graph.add_conditional_edges(
            "plan",
            lambda state: (
                END
                if state["stop_reason"] is not None
                else ("respond" if not state["calls"] else "tools")
            ),
        )
        graph.add_conditional_edges(
            "tools", lambda state: "plan" if state["stop_reason"] is None else END
        )
        graph.add_edge("respond", END)
        self._graph = graph.compile()

    async def handle(self, command: TurnCommand) -> AsyncIterator[AgentEvent]:
        checkpoint = self.store.load(command.run_id)
        if checkpoint is not None and checkpoint.idempotency_key != command.idempotency_key:
            raise ValueError("run_id is already bound to a different idempotency key")
        if checkpoint is None:
            checkpoint = RunCheckpoint(command.run_id, command.idempotency_key)
            self.store.begin_run(command, self.identity, checkpoint.started_at)
            self._emit(
                checkpoint,
                command,
                EventType.RUN_STARTED,
                {
                    "thread_id": str(command.thread_id),
                    "agent_version": self.identity.agent_version,
                    "model_version": self.identity.model_version,
                    "prompt_version": self.identity.prompt_version,
                    "policy_version": self.identity.policy_version,
                    "contract_version": self.identity.contract_version,
                    "retrieval_mode": self.identity.retrieval_mode,
                },
            )
            self._emit(
                checkpoint,
                command,
                EventType.MISSION_UPDATED,
                {
                    "goal": command.mission_goal
                    if command.mission_goal is not None
                    else command.text,
                    "status": "IN_PROGRESS",
                    "mission": parse_shopping_mission(
                        command.mission_goal if command.mission_goal is not None else command.text,
                        version=command.mission_version,
                    ),
                },
            )
            self.store.save(checkpoint)
        elif any(
            event.type in {EventType.COMPLETED, EventType.FAILED} for event in checkpoint.events
        ):
            for event in checkpoint.events:
                yield event
            return
        elif checkpoint.events and checkpoint.events[-1].type is not EventType.APPROVAL_REQUIRED:
            self._emit(
                checkpoint,
                command,
                EventType.RUN_RESUMED,
                {"reason": "nonterminal_checkpoint_loaded"},
            )
            self.store.save(checkpoint)
        if command.exploration_result is not None:
            if any(event.type is EventType.EXPLORATION_UPDATED for event in checkpoint.events):
                for event in checkpoint.events:
                    yield event
                return
            result = command.exploration_result
            self._emit(checkpoint, command, EventType.EXPLORATION_UPDATED, result)
            if result["mode"] == "PURCHASE":
                self._emit(
                    checkpoint,
                    command,
                    EventType.CLARIFICATION_REQUIRED,
                    {"question": "这个方向已记下, 你的预算上限是多少? 也可以补充不能妥协的条件。"},
                )
            else:
                exploration = result["exploration"]
                message = (
                    "本次探索已结束, 没有加入待购或前往商家。"
                    if exploration["ended"]
                    else "当前演示目录没有更多未展示的合适方向, 可撤销反馈或新建任务。"
                    if exploration["exhausted"]
                    else "看看这些使用方向, 感兴趣后再挑选商品。"
                )
                self._emit(checkpoint, command, EventType.MESSAGE, {"text": message})
                self._emit(
                    checkpoint, command, EventType.COMPLETED, {"reason": "exploration_updated"}
                )
            self.store.save(checkpoint)
            for event in checkpoint.events:
                yield event
            return
        state: AgentState = {
            "command": command,
            "calls": (),
            "results": tuple(checkpoint.completed_tools.values()),
            "checkpoint": checkpoint,
            "stop_reason": None,
            "replans": checkpoint.replans,
        }
        try:
            await self._graph.ainvoke(state)
        except ProviderError as exc:
            self._emit(
                checkpoint,
                command,
                EventType.FAILED,
                {
                    "reason": StopReason.PROVIDER_FAILURE,
                    "summary": type(exc).__name__,
                    **(
                        {"provider_detail": str(exc)}
                        if isinstance(exc, ProviderInvalidResponse)
                        else {}
                    ),
                    **(
                        {"blocked_amounts_minor": list(exc.amounts_minor)}
                        if isinstance(exc, ProviderUnsupportedAmount)
                        else {}
                    ),
                },
            )
            self.store.save(checkpoint)
        for event in checkpoint.events:
            yield event

    def reject_approval(self, command: TurnCommand, tool_name: str) -> tuple[AgentEvent, ...]:
        checkpoint = self.store.load(command.run_id)
        if checkpoint is None:
            raise ValueError("approval run does not exist")
        self._emit(
            checkpoint,
            command,
            EventType.COMPLETED,
            {"reason": "approval_rejected", "tool": tool_name},
        )
        self.store.save(checkpoint)
        return tuple(checkpoint.events)

    def _guard(self, state: AgentState) -> dict[str, Any]:
        command = state["command"]
        if not command.text.strip() and not command.media:
            return self._stop(state, StopReason.INVALID_INPUT, "turn requires text or media")
        return {}

    async def _plan(self, state: AgentState) -> dict[str, Any]:
        if state["stop_reason"] is not None:
            return {"calls": ()}
        checkpoint = state["checkpoint"]
        if checkpoint.pending_calls:
            return {"calls": checkpoint.pending_calls}
        if checkpoint.events and checkpoint.events[-1].type is EventType.APPROVAL_REQUIRED:
            return {
                **self._stop(
                    state,
                    StopReason.INVALID_INPUT,
                    "approval proposal was not persisted; start a new task",
                ),
                "calls": (),
            }
        if state["command"].media:
            if state["results"]:
                self._emit(
                    state["checkpoint"],
                    state["command"],
                    EventType.CLARIFICATION_REQUIRED,
                    {
                        "question": "请核对识别内容, 可以修改后确认继续; 图片线索不代表商品规格或报价。"
                    },
                )
                self.store.save(state["checkpoint"])
                return {"calls": (), "stop_reason": StopReason.CLARIFICATION_REQUIRED}
            return {
                "calls": tuple(
                    ToolCall(
                        "vision.identify" if ref.kind == "image" else "audio.transcribe",
                        {"media_ref": str(ref.id)},
                    )
                    for ref in state["command"].media
                )
            }
        calls = await self.planner.plan(state["command"], state["results"], state["replans"])
        if calls and all(self._call_digest(call) in checkpoint.completed_tools for call in calls):
            return {
                **self._stop(
                    state, StopReason.REPLAN_LIMIT, "planner repeated only completed tools"
                ),
                "calls": (),
            }
        if len(calls) + state["checkpoint"].tool_attempts > self.MAX_TOOLS:
            return {
                **self._stop(state, StopReason.TOOL_LIMIT, "tool budget exceeded"),
                "calls": (),
            }
        return {"calls": calls}

    async def _tools(self, state: AgentState) -> dict[str, Any]:
        checkpoint, command = state["checkpoint"], state["command"]
        results = list(state["results"])
        pending = list(state["calls"])
        replans = state["replans"]
        while pending:
            call = pending.pop(0)
            key = self._call_digest(call)
            if key in checkpoint.completed_tools:
                results.append(checkpoint.completed_tools[key])
                continue
            if checkpoint.tool_attempts >= self.MAX_TOOLS:
                return self._stop(state, StopReason.TOOL_LIMIT, "tool budget exceeded")
            checkpoint.tool_attempts += 1
            invocation_id = uuid5(NAMESPACE_URL, f"urn:rag-commerce:{command.run_id}:{key}")
            context = ToolExecutionContext(
                command.user_id,
                command.thread_id,
                command.run_id,
                invocation_id,
                hashlib.sha256(f"{command.idempotency_key}:{key}".encode()).hexdigest(),
                command.excluded_product_ids,
                command.excluded_categories,
            )
            spec = self.tools.specs.get(call.name)
            self._emit(
                checkpoint,
                command,
                EventType.TOOL_STARTED,
                {
                    "tool": call.name,
                    "invocation_id": str(invocation_id),
                    "idempotency_digest": key,
                    "arguments_sha256": key,
                    "argument_names": sorted(call.arguments),
                    "risk": spec.risk if spec else "UNREGISTERED",
                },
            )
            checkpoint.pending_calls = (call, *pending)
            self.store.save(checkpoint)
            started = perf_counter()
            try:
                result = await self.tools.execute_async(command, call, context)
            except ToolDenied as exc:
                if (
                    spec is not None
                    and spec.risk in {Risk.REVERSIBLE, Risk.EXTERNAL_NAVIGATION}
                    and call.name in command.approved_tools
                    and command.approved_invocations is not None
                    and str(invocation_id) not in command.approved_invocations
                ):
                    return self._stop(
                        state,
                        StopReason.TOOL_FAILURE,
                        "approved invocation changed; start a new Turn",
                    )
                self._emit(
                    checkpoint,
                    command,
                    EventType.APPROVAL_REQUIRED,
                    {
                        "tool": call.name,
                        "invocation_id": str(invocation_id),
                        "reason": str(exc),
                        "arguments": spec.args_type.model_validate(dict(call.arguments)).model_dump(
                            mode="json"
                        ),
                    },
                )
                self.store.save(checkpoint)
                return {
                    "results": tuple(results),
                    "stop_reason": StopReason.APPROVAL_REQUIRED,
                }
            except Exception as exc:
                self._emit(
                    checkpoint,
                    command,
                    EventType.TOOL_FAILED,
                    {
                        "tool": call.name,
                        "invocation_id": str(invocation_id),
                        "error_type": type(exc).__name__,
                        **(
                            {"error_summary": str(exc)}
                            if call.name in {"vision.identify", "audio.transcribe"}
                            and isinstance(exc, ProviderInvalidResponse)
                            else {}
                        ),
                    },
                )
                self.store.save(checkpoint)
                if call.name in {"vision.identify", "audio.transcribe"}:
                    return self._stop(
                        state,
                        StopReason.PROVIDER_FAILURE
                        if isinstance(exc, ProviderError)
                        else StopReason.TOOL_FAILURE,
                        type(exc).__name__,
                    )
                if replans >= self.MAX_REPLANS:
                    return self._stop(state, StopReason.REPLAN_LIMIT, type(exc).__name__)
                replans += 1
                checkpoint.replans = replans
                pending = list(await self.planner.plan(command, tuple(results), replans))
                continue
            supported = {field for evidence in result.evidence for field in evidence.fields}
            if not result.commercial_fact_fields <= supported:
                return self._stop(state, StopReason.TOOL_FAILURE, "commercial fact lacks evidence")
            offer_error = _offer_evidence_error(result)
            if offer_error is not None:
                return self._stop(state, StopReason.TOOL_FAILURE, offer_error)
            checkpoint.completed_tools[key] = result
            checkpoint.pending_calls = tuple(pending)
            results.append(result)
            self._emit(
                checkpoint,
                command,
                EventType.TOOL_COMPLETED,
                {
                    "tool": call.name,
                    "invocation_id": str(invocation_id),
                    "idempotency_digest": key,
                    "duration_ms": round((perf_counter() - started) * 1000, 3),
                },
            )
            for evidence in result.evidence:
                self._emit(
                    checkpoint,
                    command,
                    EventType.EVIDENCE,
                    {
                        "invocation_id": str(invocation_id),
                        "ref": evidence.ref,
                        "sha256": evidence.sha256,
                        "fields": evidence.fields,
                    },
                )
            public_event_type = {
                "catalog.search": EventType.PRODUCTS,
                "offer.find": EventType.OFFERS,
                "offer.requote": EventType.OFFERS,
                "comparison.build": EventType.COMPARISON,
            }.get(call.name)
            if public_event_type is not None and result.public_data:
                self._emit(
                    checkpoint,
                    command,
                    public_event_type,
                    dict(result.public_data),
                )
            if "media_interpretation" in result.public_data:
                self._emit(
                    checkpoint,
                    command,
                    EventType.MEDIA_INTERPRETED,
                    dict(result.public_data["media_interpretation"]),
                )
            self.store.save(checkpoint)
        return {"calls": (), "results": tuple(results), "replans": replans}

    async def _respond(self, state: AgentState) -> dict[str, Any]:
        checkpoint, command = state["checkpoint"], state["command"]
        message = await self.planner.respond(command, state["results"])
        self._emit(checkpoint, command, EventType.MESSAGE, {"text": message})
        if not state["results"] and checkpoint.tool_attempts == 0:
            self._emit(
                checkpoint,
                command,
                EventType.CLARIFICATION_REQUIRED,
                {"question": message},
            )
            self.store.save(checkpoint)
            return {"stop_reason": StopReason.CLARIFICATION_REQUIRED}
        usage = getattr(self.planner, "usage", lambda: {"provider": "unreported"})()
        self._emit(
            checkpoint,
            command,
            EventType.COMPLETED,
            {
                "reason": StopReason.COMPLETED,
                "tool_attempts": checkpoint.tool_attempts,
                "replans": checkpoint.replans,
                "usage": usage,
            },
        )
        self.store.save(checkpoint)
        return {"stop_reason": StopReason.COMPLETED}

    def _stop(self, state: AgentState, reason: StopReason, summary: str) -> dict[str, Any]:
        self._emit(
            state["checkpoint"],
            state["command"],
            EventType.FAILED,
            {"reason": reason, "summary": summary},
        )
        self.store.save(state["checkpoint"])
        return {"stop_reason": reason}

    def remember_preferences(self, command: TurnCommand, values: dict[str, str]) -> bool:
        if not command.consent_preference_memory:
            return False
        if any(
            not key.strip() or len(key) > 96 or not value.strip() or len(value) > 500
            for key, value in values.items()
        ):
            raise ValueError("preference keys and values exceed the persistence contract")
        self.store.save_preferences(command.user_id, values, True)
        return True

    def load_preferences(self, user_id: UUID) -> dict[str, str]:
        return self.store.load_preferences(user_id)

    def replay(self, run_id: UUID) -> tuple[AgentEvent, ...]:
        checkpoint = self.store.load(run_id)
        return tuple(checkpoint.events) if checkpoint is not None else ()

    @staticmethod
    def _call_digest(call: ToolCall) -> str:
        return hashlib.sha256(
            (call.name + json.dumps(call.arguments, sort_keys=True, separators=(",", ":"))).encode()
        ).hexdigest()

    @staticmethod
    def _emit(
        checkpoint: RunCheckpoint,
        command: TurnCommand,
        event_type: EventType,
        data: dict[str, Any],
    ) -> None:
        checkpoint.events.append(
            AgentEvent(len(checkpoint.events) + 1, event_type, command.run_id, data)
        )
