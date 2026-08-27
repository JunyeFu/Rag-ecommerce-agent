"""Stable persistence metadata entrypoint; applications compose the engine."""

from .schema_v1 import FORBIDDEN_TRANSACTION_TABLES, metadata

__all__ = ["FORBIDDEN_TRANSACTION_TABLES", "metadata"]
