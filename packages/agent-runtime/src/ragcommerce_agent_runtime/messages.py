"""Public stage text never consumes model-generated commercial claims."""

from .contracts import ToolResult


def public_stage_message(results: tuple[ToolResult, ...]) -> str:
    if not results:
        return "请补充商品类别、预算或主要用途。"
    return "已完成本轮处理, 具体结果和证据请查看卡片。"
