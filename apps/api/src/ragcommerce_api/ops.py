"""Governed operations API with redacted records and append-only local audit evidence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

ROLE_LEVEL = {"viewer": 0, "reviewer": 1, "admin": 2}
ACTOR_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,63}$")
FIXED_AT = datetime(2026, 8, 26, 9, 0, tzinfo=UTC)


class OpsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceBoundary(OpsModel):
    local_evidence: str
    external_gate: str | None = None


class ConnectorStatus(OpsModel):
    source_id: str
    display_name: str
    authorization: Literal["AUTHORIZED", "UNAUTHORIZED", "FIXTURE_ONLY"]
    health: Literal["HEALTHY", "DEGRADED", "BLOCKED"]
    error_rate_5m: float | None
    requests_used: int
    requests_limit: int
    freshness_p50_seconds: int | None
    last_observed_at: datetime
    evidence: EvidenceBoundary


class EntityConflict(OpsModel):
    conflict_id: str
    left_entity_ref: str
    right_entity_ref: str
    conflict_fields: list[str]
    confidence: float
    status: Literal["PENDING", "MERGED", "KEPT_SEPARATE"]
    source_refs: list[str]
    observed_at: datetime


class ResolveConflictRequest(OpsModel):
    decision: Literal["MERGE", "KEEP_SEPARATE"]
    reason: str = Field(min_length=12, max_length=500)


class ToolInvocationSummary(OpsModel):
    tool: str
    status: Literal["COMPLETED", "FAILED", "APPROVAL_REQUIRED"]
    arguments_sha256: str
    evidence_refs: list[str]
    duration_ms: int


class AgentTraceSummary(OpsModel):
    run_id: str
    status: Literal["COMPLETED", "FAILED", "WAITING_APPROVAL", "WAITING_CLARIFICATION"]
    prompt_version: str
    model_version: str
    duration_ms: int
    estimated_cost_microunits: int
    input_tokens: int
    output_tokens: int
    retrieval_hits: int
    last_event_id: int
    recovered: bool
    tools: list[ToolInvocationSummary]
    redaction_policy: str
    created_at: datetime


class EvaluationRun(OpsModel):
    run_id: str
    dataset_version: str
    runner_version: str
    status: Literal["PASSED", "FAILED", "BLOCKED", "QUEUED"]
    case_count: int
    metrics: dict[str, float]
    evidence: EvidenceBoundary
    created_at: datetime


class StartEvaluationRequest(OpsModel):
    dataset_version: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    runner_version: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")


class ReleaseGate(OpsModel):
    gate_id: str
    title: str
    evidence_level: Literal["LOCAL", "INTEGRATION", "LIVE", "HUMAN", "RELEASE"]
    status: Literal["PASSED", "FAILED", "BLOCKED", "NOT_RUN"]
    evidence_ref: str | None = None
    blocker: str | None = None


class AuditEvent(OpsModel):
    sequence: int
    event_id: str
    actor_ref: str
    action: str
    object_ref: str
    payload_sha256: str
    occurred_at: datetime


class OpsPolicy(OpsModel):
    auth_mode: Literal["development_headers"]
    visible_fields: list[str]
    prohibited_fields: list[str]
    export_enabled: bool
    audit_append_only: bool


@dataclass(frozen=True, slots=True)
class OpsActor:
    actor_id: str
    role: str

    @property
    def ref(self) -> str:
        return "actor:" + hashlib.sha256(self.actor_id.encode()).hexdigest()[:12]


class OpsConflict(RuntimeError):
    pass


class InMemoryOpsStore:
    """Deterministic fixture store; production persistence is configured separately."""

    def __init__(self) -> None:
        self.connectors = [
            ConnectorStatus(
                source_id="src_taobao_tmall",
                display_name="淘宝/天猫",
                authorization="FIXTURE_ONLY",
                health="DEGRADED",
                error_rate_5m=0.0312,
                requests_used=620,
                requests_limit=1000,
                freshness_p50_seconds=500,
                last_observed_at=FIXED_AT,
                evidence=EvidenceBoundary(
                    local_evidence="fixture:connector-taobao-v1",
                    external_gate="联盟主体授权与 live 凭据未提供",
                ),
            ),
            ConnectorStatus(
                source_id="src_jd",
                display_name="京东",
                authorization="FIXTURE_ONLY",
                health="HEALTHY",
                error_rate_5m=0.0041,
                requests_used=1420,
                requests_limit=2000,
                freshness_p50_seconds=135,
                last_observed_at=FIXED_AT,
                evidence=EvidenceBoundary(
                    local_evidence="fixture:connector-jd-v1",
                    external_gate="联盟主体授权与 live 凭据未提供",
                ),
            ),
            ConnectorStatus(
                source_id="src_pdd",
                display_name="拼多多",
                authorization="UNAUTHORIZED",
                health="BLOCKED",
                error_rate_5m=None,
                requests_used=0,
                requests_limit=500,
                freshness_p50_seconds=None,
                last_observed_at=FIXED_AT,
                evidence=EvidenceBoundary(
                    local_evidence="fixture:connector-pdd-v1",
                    external_gate="联盟主体授权与 live 凭据未提供",
                ),
            ),
        ]
        self.conflicts: dict[str, EntityConflict] = {
            "conflict-001": EntityConflict(
                conflict_id="conflict-001",
                left_entity_ref="entity:seed-0021",
                right_entity_ref="entity:seed-0198",
                conflict_fields=["brand", "model_number"],
                confidence=0.82,
                status="PENDING",
                source_refs=["seed:product-0021", "seed:product-0198"],
                observed_at=FIXED_AT,
            )
        }
        digest = hashlib.sha256(b'{"product_id":"fixture-001"}').hexdigest()
        self.traces = [
            AgentTraceSummary(
                run_id="run-fixture-001",
                status="COMPLETED",
                prompt_version="shopping-agent-v1",
                model_version="deterministic-planner-v1",
                duration_ms=284,
                estimated_cost_microunits=0,
                input_tokens=0,
                output_tokens=0,
                retrieval_hits=3,
                last_event_id=42,
                recovered=False,
                tools=[
                    ToolInvocationSummary(
                        tool="search_catalog",
                        status="COMPLETED",
                        arguments_sha256=digest,
                        evidence_refs=["fixture:catalog-product-1"],
                        duration_ms=31,
                    )
                ],
                redaction_policy="public_trace_v1:no_input_no_cot_no_raw_tool_arguments",
                created_at=FIXED_AT,
            )
        ]
        self.evaluations = [
            EvaluationRun(
                run_id="eval-local-smoke-001",
                dataset_version="v2-smoke-1",
                runner_version="deterministic-1",
                status="PASSED",
                case_count=12,
                metrics={"schema_valid": 1.0, "unsafe_tool_execution_rate": 0.0},
                evidence=EvidenceBoundary(
                    local_evidence="docs:evaluation/local-smoke",
                    external_gate="600-case frozen evaluation and held-out human review not complete",
                ),
                created_at=FIXED_AT,
            )
        ]
        self.release_gates = [
            ReleaseGate(
                gate_id="local-contract",
                title="本地契约与回归",
                evidence_level="LOCAL",
                status="PASSED",
                evidence_ref="docs/task-packages/manifest.json",
            ),
            ReleaseGate(
                gate_id="live-commerce",
                title="真实联盟报价",
                evidence_level="LIVE",
                status="BLOCKED",
                blocker="缺少 live 联盟授权与凭据",
            ),
            ReleaseGate(
                gate_id="human-acceptance",
                title="运营与无障碍人工验收",
                evidence_level="HUMAN",
                status="NOT_RUN",
                blocker="需指定人员在物理设备与生产预演环境执行",
            ),
        ]
        self.audit: list[AuditEvent] = []
        self.idempotency: dict[tuple[str, str], tuple[str, object]] = {}

    def _fingerprint(self, value: OpsModel) -> str:
        payload = json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def _append_audit(self, actor: OpsActor, action: str, object_ref: str, digest: str) -> None:
        sequence = len(self.audit) + 1
        self.audit.append(
            AuditEvent(
                sequence=sequence,
                event_id=f"audit-{sequence:06d}",
                actor_ref=actor.ref,
                action=action,
                object_ref=object_ref,
                payload_sha256=digest,
                occurred_at=FIXED_AT,
            )
        )

    def resolve_conflict(
        self, actor: OpsActor, conflict_id: str, request: ResolveConflictRequest, key: str
    ) -> EntityConflict:
        fingerprint = self._fingerprint(request)
        reservation = (actor.ref, key)
        existing = self.idempotency.get(reservation)
        if existing is not None:
            if existing[0] != fingerprint:
                raise OpsConflict("Idempotency-Key is bound to a different operation")
            return existing[1]  # type: ignore[return-value]
        conflict = self.conflicts.get(conflict_id)
        if conflict is None:
            raise KeyError(conflict_id)
        if conflict.status != "PENDING":
            raise OpsConflict("conflict is already resolved")
        resolved = conflict.model_copy(
            update={"status": "MERGED" if request.decision == "MERGE" else "KEPT_SEPARATE"}
        )
        self.conflicts[conflict_id] = resolved
        self.idempotency[reservation] = (fingerprint, resolved)
        self._append_audit(actor, "entity_conflict.resolve", conflict_id, fingerprint)
        return resolved

    def start_evaluation(
        self, actor: OpsActor, request: StartEvaluationRequest, key: str
    ) -> EvaluationRun:
        fingerprint = self._fingerprint(request)
        reservation = (actor.ref, key)
        existing = self.idempotency.get(reservation)
        if existing is not None:
            if existing[0] != fingerprint:
                raise OpsConflict("Idempotency-Key is bound to a different operation")
            return existing[1]  # type: ignore[return-value]
        run = EvaluationRun(
            run_id=f"eval-queued-{len(self.evaluations) + 1:03d}",
            dataset_version=request.dataset_version,
            runner_version=request.runner_version,
            status="QUEUED",
            case_count=0,
            metrics={},
            evidence=EvidenceBoundary(
                local_evidence="pending:runner",
                external_gate="真实模型预算和 held-out 人工双评未批准",
            ),
            created_at=FIXED_AT,
        )
        self.evaluations.append(run)
        self.idempotency[reservation] = (fingerprint, run)
        self._append_audit(actor, "evaluation.start", run.run_id, fingerprint)
        return run


def parse_actor(role_value: str | None, actor_value: str | None, minimum: str) -> OpsActor:
    role = (role_value or "").strip().lower()
    if role not in ROLE_LEVEL:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "valid X-Ops-Role is required")
    actor = (actor_value or "").strip()
    if not ACTOR_PATTERN.fullmatch(actor):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "valid X-Ops-Actor-ID is required")
    if ROLE_LEVEL[role] < ROLE_LEVEL[minimum]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "operation is not allowed for this role")
    return OpsActor(actor, role)


def require_key(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized or len(normalized) > 128:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Idempotency-Key is required")
    return normalized


def register_ops_routes(application: FastAPI) -> None:
    def store() -> InMemoryOpsStore:
        value = application.state.ops_store
        if value is None:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "operations persistence and production identity are not configured",
            )
        return value

    def actor(
        minimum: str,
        role: str | None,
        actor_id: str | None,
    ) -> OpsActor:
        return parse_actor(role, actor_id, minimum)

    async def connectors(
        response: Response,
        x_ops_role: Annotated[str | None, Header(alias="X-Ops-Role")] = None,
        x_ops_actor_id: Annotated[str | None, Header(alias="X-Ops-Actor-ID")] = None,
    ) -> list[ConnectorStatus]:
        actor("viewer", x_ops_role, x_ops_actor_id)
        response.headers["Cache-Control"] = "no-store"
        return store().connectors

    async def conflicts(
        response: Response,
        x_ops_role: Annotated[str | None, Header(alias="X-Ops-Role")] = None,
        x_ops_actor_id: Annotated[str | None, Header(alias="X-Ops-Actor-ID")] = None,
    ) -> list[EntityConflict]:
        actor("viewer", x_ops_role, x_ops_actor_id)
        response.headers["Cache-Control"] = "no-store"
        return list(store().conflicts.values())

    async def resolve(
        conflict_id: str,
        request: ResolveConflictRequest,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        x_ops_role: Annotated[str | None, Header(alias="X-Ops-Role")] = None,
        x_ops_actor_id: Annotated[str | None, Header(alias="X-Ops-Actor-ID")] = None,
    ) -> EntityConflict:
        principal = actor("reviewer", x_ops_role, x_ops_actor_id)
        try:
            return store().resolve_conflict(
                principal, conflict_id, request, require_key(idempotency_key)
            )
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "conflict not found") from exc
        except OpsConflict as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    async def traces(
        response: Response,
        x_ops_role: Annotated[str | None, Header(alias="X-Ops-Role")] = None,
        x_ops_actor_id: Annotated[str | None, Header(alias="X-Ops-Actor-ID")] = None,
    ) -> list[AgentTraceSummary]:
        actor("viewer", x_ops_role, x_ops_actor_id)
        response.headers["Cache-Control"] = "no-store"
        return store().traces

    async def evaluations(
        response: Response,
        x_ops_role: Annotated[str | None, Header(alias="X-Ops-Role")] = None,
        x_ops_actor_id: Annotated[str | None, Header(alias="X-Ops-Actor-ID")] = None,
    ) -> list[EvaluationRun]:
        actor("viewer", x_ops_role, x_ops_actor_id)
        response.headers["Cache-Control"] = "no-store"
        return store().evaluations

    async def start_evaluation(
        request: StartEvaluationRequest,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        x_ops_role: Annotated[str | None, Header(alias="X-Ops-Role")] = None,
        x_ops_actor_id: Annotated[str | None, Header(alias="X-Ops-Actor-ID")] = None,
    ) -> EvaluationRun:
        principal = actor("reviewer", x_ops_role, x_ops_actor_id)
        try:
            return store().start_evaluation(principal, request, require_key(idempotency_key))
        except OpsConflict as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    async def release_gates(
        response: Response,
        x_ops_role: Annotated[str | None, Header(alias="X-Ops-Role")] = None,
        x_ops_actor_id: Annotated[str | None, Header(alias="X-Ops-Actor-ID")] = None,
    ) -> list[ReleaseGate]:
        actor("viewer", x_ops_role, x_ops_actor_id)
        response.headers["Cache-Control"] = "no-store"
        return store().release_gates

    async def audit(
        response: Response,
        x_ops_role: Annotated[str | None, Header(alias="X-Ops-Role")] = None,
        x_ops_actor_id: Annotated[str | None, Header(alias="X-Ops-Actor-ID")] = None,
    ) -> list[AuditEvent]:
        actor("reviewer", x_ops_role, x_ops_actor_id)
        response.headers["Cache-Control"] = "no-store"
        return tuple(store().audit)

    async def policy(
        response: Response,
        x_ops_role: Annotated[str | None, Header(alias="X-Ops-Role")] = None,
        x_ops_actor_id: Annotated[str | None, Header(alias="X-Ops-Actor-ID")] = None,
    ) -> OpsPolicy:
        actor("viewer", x_ops_role, x_ops_actor_id)
        response.headers["Cache-Control"] = "no-store"
        return OpsPolicy(
            auth_mode="development_headers",
            visible_fields=[
                "source health and freshness",
                "hashed tool arguments",
                "evidence references",
                "versioned evaluation metrics",
                "local and external gate status",
            ],
            prohibited_fields=[
                "chain of thought",
                "raw user input",
                "raw tool arguments",
                "connector secrets",
                "raw authorization responses",
            ],
            export_enabled=False,
            audit_append_only=True,
        )

    application.get(
        "/v1/ops/connectors",
        response_model=list[ConnectorStatus],
        tags=["operations"],
        operation_id="getOpsConnectors",
    )(connectors)
    application.get(
        "/v1/ops/entity-conflicts",
        response_model=list[EntityConflict],
        tags=["operations"],
        operation_id="getOpsEntityConflicts",
    )(conflicts)
    application.post(
        "/v1/ops/entity-conflicts/{conflict_id}/resolution",
        response_model=EntityConflict,
        tags=["operations"],
        operation_id="resolveOpsEntityConflict",
    )(resolve)
    application.get(
        "/v1/ops/traces",
        response_model=list[AgentTraceSummary],
        tags=["operations"],
        operation_id="getOpsTraces",
    )(traces)
    application.get(
        "/v1/ops/evaluation-runs",
        response_model=list[EvaluationRun],
        tags=["operations"],
        operation_id="getOpsEvaluationRuns",
    )(evaluations)
    application.post(
        "/v1/ops/evaluation-runs",
        response_model=EvaluationRun,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["operations"],
        operation_id="startOpsEvaluationRun",
    )(start_evaluation)
    application.get(
        "/v1/ops/release-gates",
        response_model=list[ReleaseGate],
        tags=["operations"],
        operation_id="getOpsReleaseGates",
    )(release_gates)
    application.get(
        "/v1/ops/audit",
        response_model=list[AuditEvent],
        tags=["operations"],
        operation_id="getOpsAudit",
    )(audit)
    application.get(
        "/v1/ops/policy",
        response_model=OpsPolicy,
        tags=["operations"],
        operation_id="getOpsPolicy",
    )(policy)
