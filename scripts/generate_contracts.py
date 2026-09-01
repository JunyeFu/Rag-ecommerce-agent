#!/usr/bin/env python3
"""Generate deterministic Python, Kotlin and TypeScript API contract types."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENAPI = ROOT / "packages/contracts/openapi.json"
HEALTH_SCHEMA = ROOT / "packages/contracts/schemas/health-response.schema.json"
GENERATOR_VERSION = "3"
EXPECTED_OPERATIONS = {
    "createAgentRunDecision",
    "createCartMutation",
    "createList",
    "createMedia",
    "createThread",
    "createTurn",
    "deleteMedia",
    "deleteMyData",
    "getCart",
    "getAgentRunEvents",
    "getHealth",
    "getLists",
    "getOpsAudit",
    "getOpsConnectors",
    "getOpsEntityConflicts",
    "getOpsEvaluationRuns",
    "getOpsPolicy",
    "getOpsReleaseGates",
    "getOpsTraces",
    "getProduct",
    "getProductOffers",
    "getThread",
    "patchCart",
    "patchList",
    "resolveOffer",
    "resolveOpsEntityConflict",
    "startOpsEvaluationRun",
}
EXPECTED_MODELS = {
    "AgentDecision",
    "CartItemView",
    "CartMutation",
    "CartView",
    "CreateListRequest",
    "CreateThreadRequest",
    "DecisionAccepted",
    "DeletionResult",
    "HealthResponse",
    "MediaCreated",
    "OfferCollection",
    "OfferView",
    "PatchListRequest",
    "ProductCandidateView",
    "ProductView",
    "ResolveOfferRequest",
    "ResolvedOffer",
    "ShoppingListView",
    "ShoppingListsResponse",
    "ThreadCreated",
    "ThreadSnapshot",
    "TurnAccepted",
    "TurnRequest",
}


def canonical_bytes(path: Path) -> bytes:
    value = json.loads(path.read_text(encoding="utf-8"))
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def source_hash() -> str:
    digest = hashlib.sha256()
    for source in (OPENAPI, HEALTH_SCHEMA):
        digest.update(source.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(canonical_bytes(source))
        digest.update(b"\0")
    return digest.hexdigest()


def validate_source(openapi: dict, schema: dict) -> None:
    operations = {
        operation["operationId"]
        for path in openapi["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    models = set(openapi["components"]["schemas"])
    if operations != EXPECTED_OPERATIONS:
        raise ValueError(f"unexpected API operations: {sorted(operations)}")
    if not models >= EXPECTED_MODELS:
        raise ValueError(f"missing API models: {sorted(EXPECTED_MODELS - models)}")
    if schema["title"] != "HealthResponse" or schema["required"] != [
        "status",
        "contract_version",
    ]:
        raise ValueError("health schema changed; update generator deliberately")


def render() -> dict[Path, str]:
    openapi = json.loads(OPENAPI.read_text(encoding="utf-8"))
    schema = json.loads(HEALTH_SCHEMA.read_text(encoding="utf-8"))
    validate_source(openapi, schema)
    version = openapi["info"]["version"]
    digest = source_hash()
    banner = f"generator={GENERATOR_VERSION} source_sha256={digest}"

    python = f'''"""Generated file; do not edit. {banner}"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "{version}"
CONTRACT_SOURCE_SHA256 = "{digest}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictModel):
    status: Literal["ok"]
    contract_version: str


class CreateThreadRequest(StrictModel):
    goal: str = Field(min_length=1, max_length=500)


class ThreadCreated(StrictModel):
    thread_id: UUID
    mission_id: UUID


class ProductCandidateView(StrictModel):
    product_id: UUID
    variant_id: UUID
    title: str
    fit_summary: str = ""
    matched_constraints: list[str] = Field(default_factory=list)
    unmet_constraints: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class ThreadSnapshot(StrictModel):
    thread_id: UUID
    mission_id: UUID
    goal: str
    status: Literal[
        "IDLE", "RUNNING", "WAITING_APPROVAL", "WAITING_CLARIFICATION", "COMPLETED", "FAILED"
    ]
    last_event_id: int = Field(ge=0)
    pending_action: str | None = None
    candidates: list[ProductCandidateView] = Field(default_factory=list)


class ProductView(StrictModel):
    product_id: UUID
    variant_id: UUID
    title: str
    category: str
    brand: str
    attributes: dict[str, str]
    image_ref: str | None = None
    evidence_refs: list[str]


class MediaCreated(StrictModel):
    media_id: UUID
    kind: Literal["image", "audio"]
    content_type: str
    size_bytes: int
    sha256: str
    expires_at: datetime


class TurnRequest(StrictModel):
    text: str = Field(default="", max_length=10000)
    media_ids: tuple[UUID, ...] = Field(default=(), max_length=8)


class TurnAccepted(StrictModel):
    run_id: UUID
    replayed: bool
    event_count: int


class AgentDecision(StrictModel):
    tool_name: str = Field(min_length=1, max_length=100)
    approved: bool


class DecisionAccepted(StrictModel):
    run_id: UUID
    approved: bool
    event_count: int


class DeletionResult(StrictModel):
    deleted: bool


class OfferView(StrictModel):
    offer_id: UUID
    merchant_name: str
    verification: Literal["LIVE_AUTHORIZED", "FEED_VERIFIED", "DISCOVERY_ONLY", "DEMO_FIXTURE"]
    availability: Literal["AVAILABLE", "UNAVAILABLE", "UNKNOWN"]
    price_minor: int | None = None
    shipping_minor: int | None = None
    currency: Literal["CNY"] | None = None
    collected_at: datetime
    expires_at: datetime
    source_ref: str


class OfferCollection(StrictModel):
    product_id: UUID
    offers: list[OfferView]


class ResolveOfferRequest(StrictModel):
    quote_id: UUID | None = None
    confirmed_quote_change: bool = False


class ResolvedOffer(StrictModel):
    offer_id: UUID
    link_url: str | None = None
    disclosure: str
    expires_at: datetime | None = None
    quote_changed: bool
    requires_confirmation: bool


class ShoppingListView(StrictModel):
    list_id: UUID
    name: str
    variant_ids: list[UUID]


class ShoppingListsResponse(StrictModel):
    lists: list[ShoppingListView]


class CreateListRequest(StrictModel):
    name: str = Field(min_length=1, max_length=120)


class PatchListRequest(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    add_variant_id: UUID | None = None
    remove_variant_id: UUID | None = None


class CartItemView(StrictModel):
    offer_id: UUID
    quantity: int = Field(ge=1, le=99)


class CartView(StrictModel):
    items: list[CartItemView]


class CartMutation(StrictModel):
    operation: Literal["add", "set", "remove"]
    offer_id: UUID
    quantity: int = Field(default=1, ge=1, le=99)


__all__ = [
    "CONTRACT_SOURCE_SHA256",
    "CONTRACT_VERSION",
    "AgentDecision",
    "CartItemView",
    "CartMutation",
    "CartView",
    "CreateListRequest",
    "CreateThreadRequest",
    "DecisionAccepted",
    "DeletionResult",
    "HealthResponse",
    "MediaCreated",
    "OfferCollection",
    "OfferView",
    "PatchListRequest",
    "ProductCandidateView",
    "ProductView",
    "ResolveOfferRequest",
    "ResolvedOffer",
    "ShoppingListView",
    "ShoppingListsResponse",
    "ThreadCreated",
    "ThreadSnapshot",
    "TurnAccepted",
    "TurnRequest",
]
'''
    kotlin = f'''// Generated file; do not edit. {banner}
package com.ragcommerce.agent.generated

const val CONTRACT_VERSION: String = "{version}"
const val CONTRACT_SOURCE_SHA256: String = "{digest}"

data class HealthResponse(val status: String, val contract_version: String)
data class CreateThreadRequest(val goal: String)
data class ThreadCreated(val thread_id: String, val mission_id: String)
data class ProductCandidateView(
    val product_id: String,
    val variant_id: String,
    val title: String,
    val fit_summary: String = "",
    val matched_constraints: List<String> = emptyList(),
    val unmet_constraints: List<String> = emptyList(),
    val risks: List<String> = emptyList(),
    val evidence_refs: List<String> = emptyList(),
)
data class ThreadSnapshot(
    val thread_id: String,
    val mission_id: String,
    val goal: String,
    val status: String,
    val last_event_id: Long,
    val pending_action: String? = null,
    val candidates: List<ProductCandidateView> = emptyList(),
)
data class ProductView(
    val product_id: String,
    val variant_id: String,
    val title: String,
    val category: String,
    val brand: String,
    val attributes: Map<String, String>,
    val image_ref: String? = null,
    val evidence_refs: List<String>,
)
data class MediaCreated(
    val media_id: String,
    val kind: String,
    val content_type: String,
    val size_bytes: Long,
    val sha256: String,
    val expires_at: String,
)
data class TurnRequest(val text: String = "", val media_ids: List<String> = emptyList())
data class TurnAccepted(val run_id: String, val replayed: Boolean, val event_count: Int)
data class AgentDecision(val tool_name: String, val approved: Boolean)
data class DecisionAccepted(val run_id: String, val approved: Boolean, val event_count: Int)
data class DeletionResult(val deleted: Boolean)
data class OfferView(
    val offer_id: String,
    val merchant_name: String,
    val verification: String,
    val availability: String,
    val price_minor: Long?,
    val shipping_minor: Long?,
    val currency: String?,
    val collected_at: String,
    val expires_at: String,
    val source_ref: String,
)
data class OfferCollection(val product_id: String, val offers: List<OfferView>)
data class ResolveOfferRequest(val quote_id: String? = null, val confirmed_quote_change: Boolean = false)
data class ResolvedOffer(
    val offer_id: String,
    val link_url: String?,
    val disclosure: String,
    val expires_at: String?,
    val quote_changed: Boolean,
    val requires_confirmation: Boolean,
)
data class ShoppingListView(val list_id: String, val name: String, val variant_ids: List<String>)
data class ShoppingListsResponse(val lists: List<ShoppingListView>)
data class CreateListRequest(val name: String)
data class PatchListRequest(
    val name: String? = null,
    val add_variant_id: String? = null,
    val remove_variant_id: String? = null,
)
data class CartItemView(val offer_id: String, val quantity: Int)
data class CartView(val items: List<CartItemView>)
data class CartMutation(val operation: String, val offer_id: String, val quantity: Int = 1)
'''
    typescript = f'''// Generated file; do not edit. {banner}
export const CONTRACT_VERSION = "{version}" as const;
export const CONTRACT_SOURCE_SHA256 = "{digest}" as const;

export type HealthResponse = {{ status: "ok"; contract_version: string }};
export type CreateThreadRequest = {{ goal: string }};
export type ThreadCreated = {{ thread_id: string; mission_id: string }};
export type ProductCandidateView = {{
  product_id: string;
  variant_id: string;
  title: string;
  fit_summary?: string;
  matched_constraints?: string[];
  unmet_constraints?: string[];
  risks?: string[];
  evidence_refs?: string[];
}};
export type ThreadSnapshot = {{
  thread_id: string;
  mission_id: string;
  goal: string;
  status: "IDLE" | "RUNNING" | "WAITING_APPROVAL" | "WAITING_CLARIFICATION" | "COMPLETED" | "FAILED";
  last_event_id: number;
  pending_action?: string | null;
  candidates?: ProductCandidateView[];
}};
export type ProductView = {{
  product_id: string;
  variant_id: string;
  title: string;
  category: string;
  brand: string;
  attributes: Record<string, string>;
  image_ref?: string | null;
  evidence_refs: string[];
}};
export type MediaCreated = {{
  media_id: string;
  kind: "image" | "audio";
  content_type: string;
  size_bytes: number;
  sha256: string;
  expires_at: string;
}};
export type TurnRequest = {{ text?: string; media_ids?: string[] }};
export type TurnAccepted = {{ run_id: string; replayed: boolean; event_count: number }};
export type AgentDecision = {{ tool_name: string; approved: boolean }};
export type DecisionAccepted = {{ run_id: string; approved: boolean; event_count: number }};
export type DeletionResult = {{ deleted: boolean }};
export type OfferView = {{
  offer_id: string;
  merchant_name: string;
  verification: "LIVE_AUTHORIZED" | "FEED_VERIFIED" | "DISCOVERY_ONLY" | "DEMO_FIXTURE";
  availability: "AVAILABLE" | "UNAVAILABLE" | "UNKNOWN";
  price_minor?: number | null;
  shipping_minor?: number | null;
  currency?: "CNY" | null;
  collected_at: string;
  expires_at: string;
  source_ref: string;
}};
export type OfferCollection = {{ product_id: string; offers: OfferView[] }};
export type ResolveOfferRequest = {{ quote_id?: string | null; confirmed_quote_change?: boolean }};
export type ResolvedOffer = {{
  offer_id: string;
  link_url?: string | null;
  disclosure: string;
  expires_at?: string | null;
  quote_changed: boolean;
  requires_confirmation: boolean;
}};
export type ShoppingListView = {{ list_id: string; name: string; variant_ids: string[] }};
export type ShoppingListsResponse = {{ lists: ShoppingListView[] }};
export type CreateListRequest = {{ name: string }};
export type PatchListRequest = {{
  name?: string | null;
  add_variant_id?: string | null;
  remove_variant_id?: string | null;
}};
export type CartItemView = {{ offer_id: string; quantity: number }};
export type CartView = {{ items: CartItemView[] }};
export type CartMutation = {{ operation: "add" | "set" | "remove"; offer_id: string; quantity?: number }};
export type EvidenceBoundary = {{ local_evidence: string; external_gate?: string | null }};
export type ConnectorStatus = {{
  source_id: string;
  display_name: string;
  authorization: "AUTHORIZED" | "UNAUTHORIZED" | "FIXTURE_ONLY";
  health: "HEALTHY" | "DEGRADED" | "BLOCKED";
  error_rate_5m?: number | null;
  requests_used: number;
  requests_limit: number;
  freshness_p50_seconds?: number | null;
  last_observed_at: string;
  evidence: EvidenceBoundary;
}};
export type EntityConflict = {{
  conflict_id: string;
  left_entity_ref: string;
  right_entity_ref: string;
  conflict_fields: string[];
  confidence: number;
  status: "PENDING" | "MERGED" | "KEPT_SEPARATE";
  source_refs: string[];
  observed_at: string;
}};
export type ResolveConflictRequest = {{ decision: "MERGE" | "KEEP_SEPARATE"; reason: string }};
export type ToolInvocationSummary = {{
  tool: string;
  status: "COMPLETED" | "FAILED" | "APPROVAL_REQUIRED";
  arguments_sha256: string;
  evidence_refs: string[];
  duration_ms: number;
}};
export type AgentTraceSummary = {{
  run_id: string;
  status: "COMPLETED" | "FAILED" | "WAITING_APPROVAL" | "WAITING_CLARIFICATION";
  prompt_version: string;
  model_version: string;
  duration_ms: number;
  estimated_cost_microunits: number;
  input_tokens: number;
  output_tokens: number;
  retrieval_hits: number;
  last_event_id: number;
  recovered: boolean;
  tools: ToolInvocationSummary[];
  redaction_policy: string;
  created_at: string;
}};
export type EvaluationRun = {{
  run_id: string;
  dataset_version: string;
  runner_version: string;
  status: "PASSED" | "FAILED" | "BLOCKED" | "QUEUED";
  case_count: number;
  metrics: Record<string, number>;
  evidence: EvidenceBoundary;
  created_at: string;
}};
export type StartEvaluationRequest = {{ dataset_version: string; runner_version: string }};
export type ReleaseGate = {{
  gate_id: string;
  title: string;
  evidence_level: "LOCAL" | "INTEGRATION" | "LIVE" | "HUMAN" | "RELEASE";
  status: "PASSED" | "FAILED" | "BLOCKED" | "NOT_RUN";
  evidence_ref?: string | null;
  blocker?: string | null;
}};
export type AuditEvent = {{
  sequence: number;
  event_id: string;
  actor_ref: string;
  action: string;
  object_ref: string;
  payload_sha256: string;
  occurred_at: string;
}};
export type OpsPolicy = {{
  auth_mode: "development_headers";
  visible_fields: string[];
  prohibited_fields: string[];
  export_enabled: boolean;
  audit_append_only: boolean;
}};
'''
    return {
        ROOT / "packages/contracts/generated/python/ragcommerce_contracts/__init__.py": python,
        ROOT
        / "apps/android/app/src/main/java/com/ragcommerce/agent/generated/ApiContracts.kt": kotlin,
        ROOT / "apps/ops-web/src/generated/api-contracts.ts": typescript,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if generated files drift")
    args = parser.parse_args()
    drift: list[str] = []
    outputs = render()
    for path, expected in outputs.items():
        relative = path.relative_to(ROOT).as_posix()
        if args.check:
            actual = path.read_text(encoding="utf-8") if path.exists() else None
            if actual != expected:
                drift.append(relative)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8", newline="\n")
            print(f"generated {relative}")
    if drift:
        print("contract drift:")
        for item in drift:
            print(f"- {item}")
        return 1
    if args.check:
        print(f"contract generation is deterministic ({len(outputs)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
