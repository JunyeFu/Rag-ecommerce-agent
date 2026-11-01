"""Model budget metadata, isolated from historical V3 create_all migrations."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, MetaData, String, Table
from sqlalchemy.dialects.postgresql import UUID

metadata = MetaData()
model_budget_sessions = Table(
    "model_budget_sessions",
    metadata,
    Column("session_id", String(96), primary_key=True),
    Column("total_limit", Integer, nullable=False),
    Column("blocked", Boolean, nullable=False),
)
model_budget_calls = Table(
    "model_budget_calls",
    metadata,
    Column("call_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "session_id", String(96), ForeignKey("model_budget_sessions.session_id"), nullable=False
    ),
    Column("run_id", UUID(as_uuid=True), nullable=False),
    Column("reserved_tokens", Integer, nullable=False),
    Column("used_tokens", Integer),
    Column("model", String(120), nullable=False),
    Column("status", String(24), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("settled_at", DateTime(timezone=True)),
    Column("scenario_id", String(96)),
)
model_budget_scenarios = Table(
    "model_budget_scenarios",
    metadata,
    Column(
        "session_id", String(96), ForeignKey("model_budget_sessions.session_id"), primary_key=True
    ),
    Column("scenario_id", String(96), primary_key=True),
    Column("owner_id", UUID(as_uuid=True), nullable=False),
    Column("scenario_group", String(16), nullable=False),
    Column("phase", String(16), nullable=False),
    Column("root_cause_ref", String(240)),
    Column("active", Boolean, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("result", String(24)),
)
