"""Explicit local provider selection; real mode never falls back to fake."""

from __future__ import annotations

import os

from ragcommerce_agent_runtime import ModelProvider, OpenAICompatibleProvider

from .demo import DemoProvider


def configured_provider() -> ModelProvider:
    mode = os.environ.get("MODEL_PROVIDER_MODE", "fake").strip().lower()
    if mode == "fake":
        return DemoProvider()
    if mode == "openai_compatible":
        return OpenAICompatibleProvider(
            os.environ.get("OPENAI_COMPATIBLE_BASE_URL", ""),
            os.environ.get("OPENAI_COMPATIBLE_API_KEY", ""),
            os.environ.get("OPENAI_COMPATIBLE_MODEL", ""),
        )
    raise RuntimeError("MODEL_PROVIDER_MODE must be fake or openai_compatible")


__all__ = ["configured_provider"]
