"""Single LangGraph-backed shopping runtime with bounded typed tools."""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from time import perf_counter
from typing import Any, Protocol, TypedDict
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
from .store import CheckpointStore, RunCheckpoint
from .tools import ToolDenied, ToolRegistry


class Planner(Protocol):
    def plan(
        self, command: TurnCommand, prior_results: tuple[ToolResult, ...], replan: int
    ) -> tuple[ToolCall, ...]: ...

    def respond(self, command: TurnCommand, results: tuple[ToolResult, ...]) -> str: ...


class AgentState(TypedDict):
    command: TurnCommand
    calls: tuple[ToolCall, ...]
    results: tuple[ToolResult, ...]
    checkpoint: RunCheckpoint
    stop_reason: StopReason | None
    replans: int


class ShoppingAgent:
    MAX_TOOLS = 8
    MAX_REPLANS = 2

    def __init__(
        self,
        planner: Planner,
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
        graph.add_edge("plan", "tools")
        graph.add_conditional_edges(
            "tools", lambda state: "respond" if state["stop_reason"] is None else END
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
                },
            )
            self.store.save(checkpoint)
        elif any(
            event.type in {EventType.COMPLETED, EventType.FAILED} for event in checkpoint.events
        ):
            for event in checkpoint.events:
                yield event
            return
        state: AgentState = {
            "command": command,
            "calls": (),
            "results": (),
            "checkpoint": checkpoint,
            "stop_reason": None,
            "replans": checkpoint.replans,
        }
        await self._graph.ainvoke(state)
        for event in checkpoint.events:
            yield event

    def _guard(self, state: AgentState) -> dict[str, Any]:
        command = state["command"]
        if not command.text.strip() and not command.media:
            return self._stop(state, StopReason.INVALID_INPUT, "turn requires text or media")
        return {}

    def _plan(self, state: AgentState) -> dict[str, Any]:
        if state["stop_reason"] is not None:
            return {"calls": ()}
        calls = self.planner.plan(state["command"], state["results"], state["replans"])
        if len(calls) + state["checkpoint"].tool_attempts > self.MAX_TOOLS:
            return {
                **self._stop(state, StopReason.TOOL_LIMIT, "tool budget exceeded"),
                "calls": (),
            }
        return {"calls": calls}

    def _tools(self, state: AgentState) -> dict[str, Any]:
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
            self.store.save(checkpoint)
            started = perf_counter()
            try:
                result = self.tools.execute(command, call, context)
            except ToolDenied as exc:
                self._emit(
                    checkpoint,
                    command,
                    EventType.APPROVAL_REQUIRED,
                    {
                        "tool": call.name,
                        "invocation_id": str(invocation_id),
                        "reason": str(exc),
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
                    },
                )
                self.store.save(checkpoint)
                if replans >= self.MAX_REPLANS:
                    return self._stop(state, StopReason.REPLAN_LIMIT, type(exc).__name__)
                replans += 1
                checkpoint.replans = replans
                pending = list(self.planner.plan(command, tuple(results), replans))
                continue
            supported = {field for evidence in result.evidence for field in evidence.fields}
            if not result.commercial_fact_fields <= supported:
                return self._stop(state, StopReason.TOOL_FAILURE, "commercial fact lacks evidence")
            checkpoint.completed_tools[key] = result
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
            self.store.save(checkpoint)
        return {"results": tuple(results), "replans": replans}

    def _respond(self, state: AgentState) -> dict[str, Any]:
        checkpoint, command = state["checkpoint"], state["command"]
        message = self.planner.respond(command, state["results"])
        self._emit(checkpoint, command, EventType.MESSAGE, {"text": message})
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
