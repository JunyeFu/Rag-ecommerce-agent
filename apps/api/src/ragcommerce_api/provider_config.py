"""Explicit local provider selection; real mode never falls back to fake."""

from __future__ import annotations

import os

from ragcommerce_agent_runtime import ModelProvider, OpenAICompatibleProvider
from ragcommerce_agent_runtime.token_budget import PostgresTokenBudget

from .demo import DemoProvider

REAL_PROVIDER_TIMEOUT_SECONDS = 180.0
REAL_PROVIDER_MAX_TOTAL_TOKENS = 48_000


def configured_provider() -> ModelProvider:
    mode = os.environ.get("MODEL_PROVIDER_MODE", "fake").strip().lower()
    if mode == "fake":
        return DemoProvider()
    if mode == "openai_compatible":
        dsn = os.environ.get("DATABASE_URL", "")
        session = os.environ.get("MODEL_BUDGET_SESSION", "")
        if not dsn or not session:
            raise RuntimeError(
                "real provider requires DATABASE_URL and explicit MODEL_BUDGET_SESSION"
            )
        return OpenAICompatibleProvider(
            os.environ.get("OPENAI_COMPATIBLE_BASE_URL", ""),
            os.environ.get("OPENAI_COMPATIBLE_API_KEY", ""),
            os.environ.get("OPENAI_COMPATIBLE_MODEL", ""),
            timeout_seconds=REAL_PROVIDER_TIMEOUT_SECONDS,
            max_total_tokens=REAL_PROVIDER_MAX_TOTAL_TOKENS,
            token_budget=PostgresTokenBudget(dsn, session, require_scenario=True),
        )
    raise RuntimeError("MODEL_PROVIDER_MODE must be fake or openai_compatible")


__all__ = ["configured_provider"]
