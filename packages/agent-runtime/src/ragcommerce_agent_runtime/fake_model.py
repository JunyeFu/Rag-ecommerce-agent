"""Deterministic planner for tests and offline traces."""

from dataclasses import dataclass

from .contracts import ToolCall, ToolResult, TurnCommand


@dataclass(slots=True)
class ScriptedPlanner:
    calls: tuple[ToolCall, ...]
    message: str = "已根据工具证据完成。"

    def plan(
        self, command: TurnCommand, prior_results: tuple[ToolResult, ...], replan: int
    ) -> tuple[ToolCall, ...]:
        return self.calls

    def respond(self, command: TurnCommand, results: tuple[ToolResult, ...]) -> str:
        return self.message

    def usage(self) -> dict[str, int | str]:
        return {
            "provider": "deterministic_fake",
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_minor": 0,
            "currency": "CNY",
        }
