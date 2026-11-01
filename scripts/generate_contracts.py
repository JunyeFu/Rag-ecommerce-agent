#!/usr/bin/env python3
"""Generate deterministic Python, Kotlin and TypeScript API contract types."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENAPI = ROOT / "packages/contracts/openapi.json"
HEALTH_SCHEMA = ROOT / "packages/contracts/schemas/health-response.schema.json"
GENERATOR_VERSION = "4"
EXPECTED_OPERATIONS = {
    "getThreads",
    "patchThread",
    "getThreadMessages",
    "updateCandidateFeedback",
    "getVariant",
    "undoCandidateFeedback",
    "createAgentRunDecision",
    "createCartMutation",
    "createList",
    "createMedia",
    "createThread",
    "createTurn",
    "createWatcher",
    "deleteMedia",
    "deleteMyData",
    "getCart",
    "getComparisonSelection",
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
    "getWatchers",
    "patchCart",
    "patchList",
    "parseMission",
    "resolveOffer",
    "resolveOpsEntityConflict",
    "startOpsEvaluationRun",
    "updateThreadConstraints",
    "updateComparisonSelection",
}
EXPECTED_MODELS = {
    "AgentDecision",
    "BusinessFactView",
    "CartItemView",
    "CartMutation",
    "CartView",
    "ComparisonSelection",
    "CreateListRequest",
    "CreateThreadRequest",
    "CreateWatcherRequest",
    "DecisionAccepted",
    "DeletionResult",
    "HealthResponse",
    "MediaCreated",
    "MediaInterpretation",
    "MediaConfirmation",
    "OfferCollection",
    "OfferView",
    "PatchListRequest",
    "ProductCandidateView",
    "ProductView",
    "RecommendationRouteView",
    "ResolveOfferRequest",
    "ResolvedOffer",
    "ShoppingListView",
    "ShoppingListsResponse",
    "MissionItemView",
    "ShoppingMissionView",
    "ThreadCreated",
    "ThreadSnapshot",
    "TurnAccepted",
    "TurnRequest",
    "WatcherCollection",
    "WatcherView",
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


class MissionItemView(StrictModel):
    category: str
    quantity: int = Field(ge=1, le=99)


class ShoppingMissionView(StrictModel):
    goal: str
    version: int = Field(ge=1)
    items: list[MissionItemView] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    soft_preferences: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    budget_total_minor: int | None = Field(default=None, ge=0)
    currency: Literal["CNY"] = "CNY"


class ProductCandidateView(StrictModel):
    product_id: UUID
    variant_id: UUID
    title: str
    fit_summary: str = ""
    matched_constraints: list[str] = Field(default_factory=list)
    unmet_constraints: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    recommendation_type: Literal["STRICT", "BUDGET", "ALTERNATIVE"] = "STRICT"
    relaxed_constraints: list[str] = Field(default_factory=list)


class RecommendationRouteView(StrictModel):
    route_type: Literal["STRICT", "BUDGET", "ALTERNATIVE"]
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    summary: str
    relaxed_constraints: list[str] = Field(default_factory=list)
    product_ids: list[UUID] = Field(default_factory=list)


class ComparisonSelection(StrictModel):
    product_ids: list[UUID] = Field(default_factory=list, max_length=4)


class ExplorationDirection(StrictModel):
    direction_id: str
    title: str
    category: str
    experience_tags: list[str]
    evidence_refs: list[str]
    supporting_product_ids: list[UUID]
    scenario_hint: str = ""
    try_first: str = ""
    to_confirm: str = ""


class ExplorationState(StrictModel):
    directions: list[ExplorationDirection] = Field(default_factory=list)
    feedback: dict[str, Literal["interested", "not_interested"]] = Field(default_factory=dict)
    shown_direction_ids: list[str] = Field(default_factory=list)
    shown_product_ids: list[UUID] = Field(default_factory=list)
    experience_tags: list[str] = Field(default_factory=list)
    selected_direction_id: str | None = None
    exhausted: bool = False
    ended: bool = False
    outcome: Literal["UNDECIDED", "USE_EXISTING", "NOT_BUYING"] | None = None


class MediaInterpretation(StrictModel):
    media_id: UUID
    kind: Literal["image", "audio"]
    recognized_text: str = Field(max_length=2000)
    category: Literal["手机", "电脑", "耳机", "相机"] | None = None
    visible_attributes: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    supported: bool


class MediaConfirmation(StrictModel):
    source_run_id: UUID
    text: str = Field(min_length=1, max_length=500)


class ThreadExperience(StrictModel):
    title: str | None = None
    archived: bool = False
    feedback: dict[str, str] = Field(default_factory=dict)


class CandidateFeedback(StrictModel):
    product_id: UUID
    expected_mission_version: int = Field(ge=1)
    scope: Literal["PRODUCT", "CATEGORY"] = "PRODUCT"
    reason: str = Field(min_length=1, max_length=200)
    undo: bool = False


class ThreadHistoryPatch(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=80)
    archived: bool | None = None


class ThreadHistoryEntry(StrictModel):
    thread_id: UUID
    goal: str
    experience: ThreadExperience
    mode: Literal["PURCHASE", "DISCOVERY"]


class ConversationMessage(StrictModel):
    run_id: UUID
    role: Literal["user", "assistant", "system"]
    text: str


class ThreadSnapshot(StrictModel):
    experience: ThreadExperience = Field(default_factory=ThreadExperience)
    mode: Literal["PURCHASE", "DISCOVERY"] = "PURCHASE"
    exploration: ExplorationState | None = None
    pending_media_interpretations: list[MediaInterpretation] = Field(default_factory=list)
    thread_id: UUID
    mission_id: UUID
    goal: str
    status: Literal[
        "IDLE", "RUNNING", "WAITING_APPROVAL", "WAITING_CLARIFICATION", "COMPLETED", "FAILED"
    ]
    last_event_id: int = Field(ge=0)
    pending_action: str | None = None
    pending_action_arguments: dict[str, str | int] = Field(default_factory=dict)
    active_run_id: UUID | None = None
    candidates: list[ProductCandidateView] = Field(default_factory=list)
    recommendation_routes: list[RecommendationRouteView] = Field(default_factory=list)
    mission: ShoppingMissionView
    selected_product_ids: list[UUID] = Field(default_factory=list, max_length=4)


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


class ExplorationAction(StrictModel):
    kind: Literal["start", "feedback", "next", "select_for_purchase", "end"]
    experience_tags: list[Literal["life_improvement", "novelty"]] = Field(default_factory=list, max_length=2)
    direction_id: str | None = Field(default=None, min_length=1, max_length=100)
    value: Literal["interested", "not_interested", "neutral"] | None = None
    outcome: Literal["UNDECIDED", "USE_EXISTING", "NOT_BUYING"] | None = None


class TurnRequest(StrictModel):
    text: str = Field(default="", max_length=10000)
    media_ids: tuple[UUID, ...] = Field(default=(), max_length=8)
    exploration_action: ExplorationAction | None = None
    expected_mission_version: int | None = Field(default=None, ge=1)
    media_confirmation: MediaConfirmation | None = None


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


class BusinessFactView(StrictModel):
    fact_type: Literal["price", "inventory", "delivery", "merchant", "after_sales"]
    summary: str
    verification_level: Literal[
        "LIVE_AUTHORIZED", "FEED_VERIFIED", "DISCOVERY_ONLY", "DEMO_FIXTURE"
    ]
    observed_at: datetime
    expires_at: datetime | None = None
    evidence_ref: str


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
    business_facts: list[BusinessFactView] = Field(default_factory=list)


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
    product: ProductView
    quote: OfferView


class CartView(StrictModel):
    items: list[CartItemView]


class CartMutation(StrictModel):
    operation: Literal["add", "set", "remove"]
    offer_id: UUID
    quantity: int = Field(default=1, ge=1, le=99)


class CreateWatcherRequest(StrictModel):
    kind: Literal["PRICE_BELOW", "RESTOCK"]
    offer_id: UUID
    threshold_minor: int | None = Field(default=None, ge=0)


class WatcherView(StrictModel):
    watcher_id: UUID
    thread_id: UUID
    offer_id: UUID
    kind: Literal["PRICE_BELOW", "RESTOCK"]
    threshold_minor: int | None = Field(default=None, ge=0)
    status: Literal["DEMO_DRAFT"] = "DEMO_DRAFT"
    scheduler_active: Literal[False] = False
    disclosure: str
    created_at: datetime


class WatcherCollection(StrictModel):
    watchers: list[WatcherView]


__all__ = [
    "CONTRACT_SOURCE_SHA256",
    "CONTRACT_VERSION",
    "AgentDecision",
    "BusinessFactView",
    "CartItemView",
    "CartMutation",
    "CartView",
    "ComparisonSelection",
    "CreateListRequest",
    "CreateThreadRequest",
    "CreateWatcherRequest",
    "DecisionAccepted",
    "DeletionResult",
    "HealthResponse",
    "MediaCreated",
    "MissionItemView",
    "OfferCollection",
    "OfferView",
    "PatchListRequest",
    "ProductCandidateView",
    "ProductView",
    "RecommendationRouteView",
    "ResolveOfferRequest",
    "ResolvedOffer",
    "ShoppingListView",
    "ShoppingListsResponse",
    "ShoppingMissionView",
    "ThreadCreated",
    "ThreadSnapshot",
    "TurnAccepted",
    "TurnRequest",
    "WatcherCollection",
    "WatcherView",
]
'''
    kotlin = f'''// Generated file; do not edit. {banner}
package com.ragcommerce.agent.generated

const val CONTRACT_VERSION: String = "{version}"
const val CONTRACT_SOURCE_SHA256: String = "{digest}"

data class HealthResponse(val status: String, val contract_version: String)
data class CreateThreadRequest(val goal: String)
data class ThreadCreated(val thread_id: String, val mission_id: String)
data class MissionItemView(val category: String, val quantity: Int)
data class ShoppingMissionView(
    val goal: String,
    val version: Int,
    val items: List<MissionItemView> = emptyList(),
    val hard_constraints: List<String> = emptyList(),
    val soft_preferences: List<String> = emptyList(),
    val unknowns: List<String> = emptyList(),
    val budget_total_minor: Long? = null,
    val currency: String = "CNY",
)
data class ProductCandidateView(
    val product_id: String,
    val variant_id: String,
    val title: String,
    val fit_summary: String = "",
    val matched_constraints: List<String> = emptyList(),
    val unmet_constraints: List<String> = emptyList(),
    val risks: List<String> = emptyList(),
    val evidence_refs: List<String> = emptyList(),
    val recommendation_type: String = "STRICT",
    val relaxed_constraints: List<String> = emptyList(),
)
data class RecommendationRouteView(
    val route_type: String,
    val status: String,
    val summary: String,
    val relaxed_constraints: List<String> = emptyList(),
    val product_ids: List<String> = emptyList(),
)
data class ComparisonSelection(val product_ids: List<String> = emptyList())
data class ThreadExperience(val title: String? = null, val archived: Boolean = false, val feedback: Map<String, String> = emptyMap())
data class CandidateFeedback(val product_id: String, val expected_mission_version: Int, val scope: String = "PRODUCT", val reason: String, val undo: Boolean = false)
data class ThreadHistoryPatch(val title: String? = null, val archived: Boolean? = null)
data class ThreadHistoryEntry(val thread_id: String, val goal: String, val experience: ThreadExperience, val mode: String)
data class ConversationMessage(val run_id: String, val role: String, val text: String)
data class ThreadSnapshot(
    val experience: ThreadExperience = ThreadExperience(),
    val mode: String = "PURCHASE",
    val exploration: ExplorationState? = null,
    val pending_media_interpretations: List<MediaInterpretation> = emptyList(),
    val thread_id: String,
    val mission_id: String,
    val goal: String,
    val status: String,
    val last_event_id: Long,
    val pending_action: String? = null,
    val pending_action_arguments: Map<String, Any> = emptyMap(),
    val active_run_id: String? = null,
    val candidates: List<ProductCandidateView> = emptyList(),
    val recommendation_routes: List<RecommendationRouteView> = emptyList(),
    val mission: ShoppingMissionView,
    val selected_product_ids: List<String> = emptyList(),
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
data class MediaInterpretation(
    val media_id: String, val kind: String, val recognized_text: String,
    val category: String? = null, val visible_attributes: List<String> = emptyList(),
    val uncertainties: List<String> = emptyList(), val supported: Boolean,
)
data class MediaConfirmation(val source_run_id: String, val text: String)

data class MediaCreated(
    val media_id: String,
    val kind: String,
    val content_type: String,
    val size_bytes: Long,
    val sha256: String,
    val expires_at: String,
)
data class ExplorationDirection(
    val direction_id: String, val title: String, val category: String,
    val experience_tags: List<String>, val evidence_refs: List<String>,
    val supporting_product_ids: List<String>,
    val scenario_hint: String = "", val try_first: String = "", val to_confirm: String = "",
)
data class ExplorationState(
    val directions: List<ExplorationDirection> = emptyList(),
    val feedback: Map<String, String> = emptyMap(),
    val shown_direction_ids: List<String> = emptyList(),
    val shown_product_ids: List<String> = emptyList(),
    val experience_tags: List<String> = emptyList(),
    val selected_direction_id: String? = null,
    val exhausted: Boolean = false, val ended: Boolean = false,
    val outcome: String? = null,
)
data class ExplorationAction(
    val kind: String, val experience_tags: List<String> = emptyList(),
    val direction_id: String? = null, val value: String? = null,
    val outcome: String? = null,
)
data class TurnRequest(
    val text: String = "", val media_ids: List<String> = emptyList(),
    val exploration_action: ExplorationAction? = null, val expected_mission_version: Int? = null,
    val media_confirmation: MediaConfirmation? = null,
)
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
    val business_facts: List<BusinessFactView> = emptyList(),
)
data class BusinessFactView(
    val fact_type: String,
    val summary: String,
    val verification_level: String,
    val observed_at: String,
    val expires_at: String? = null,
    val evidence_ref: String,
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
data class CartItemView(val offer_id: String, val quantity: Int, val product: ProductView, val quote: OfferView)
data class CartView(val items: List<CartItemView>)
data class CartMutation(val operation: String, val offer_id: String, val quantity: Int = 1)
data class CreateWatcherRequest(val kind: String, val offer_id: String, val threshold_minor: Long? = null)
data class WatcherView(
    val watcher_id: String,
    val thread_id: String,
    val offer_id: String,
    val kind: String,
    val threshold_minor: Long? = null,
    val status: String = "DEMO_DRAFT",
    val scheduler_active: Boolean = false,
    val disclosure: String,
    val created_at: String,
)
data class WatcherCollection(val watchers: List<WatcherView>)
'''
    typescript = f'''// Generated file; do not edit. {banner}
export const CONTRACT_VERSION = "{version}" as const;
export const CONTRACT_SOURCE_SHA256 = "{digest}" as const;

export type HealthResponse = {{ status: "ok"; contract_version: string }};
export type CreateThreadRequest = {{ goal: string }};
export type ThreadCreated = {{ thread_id: string; mission_id: string }};
export type MissionItemView = {{ category: string; quantity: number }};
export type ShoppingMissionView = {{
  goal: string;
  version: number;
  items?: MissionItemView[];
  hard_constraints?: string[];
  soft_preferences?: string[];
  unknowns?: string[];
  budget_total_minor?: number | null;
  currency: "CNY";
}};
export type ProductCandidateView = {{
  product_id: string;
  variant_id: string;
  title: string;
  fit_summary?: string;
  matched_constraints?: string[];
  unmet_constraints?: string[];
  risks?: string[];
  evidence_refs?: string[];
  recommendation_type?: "STRICT" | "BUDGET" | "ALTERNATIVE";
  relaxed_constraints?: string[];
}};
export type RecommendationRouteView = {{
  route_type: "STRICT" | "BUDGET" | "ALTERNATIVE";
  status: "AVAILABLE" | "UNAVAILABLE";
  summary: string;
  relaxed_constraints?: string[];
  product_ids?: string[];
}};
export type ComparisonSelection = {{ product_ids?: string[] }};
export type ThreadExperience = {{ title?: string | null; archived?: boolean; feedback?: Record<string, string> }};
export type CandidateFeedback = {{ product_id: string; expected_mission_version: number; scope?: "PRODUCT" | "CATEGORY"; reason: string; undo?: boolean }};
export type ThreadHistoryPatch = {{ title?: string | null; archived?: boolean | null }};
export type ThreadHistoryEntry = {{ thread_id: string; goal: string; experience: ThreadExperience; mode: "PURCHASE" | "DISCOVERY" }};
export type ConversationMessage = {{ run_id: string; role: "user" | "assistant" | "system"; text: string }};
export type ThreadSnapshot = {{
  experience?: ThreadExperience;
  mode?: "PURCHASE" | "DISCOVERY";
  exploration?: ExplorationState | null;
  pending_media_interpretations: MediaInterpretation[];
  thread_id: string;
  mission_id: string;
  goal: string;
  status: "IDLE" | "RUNNING" | "WAITING_APPROVAL" | "WAITING_CLARIFICATION" | "COMPLETED" | "FAILED";
  last_event_id: number;
  pending_action?: string | null;
  pending_action_arguments?: Record<string, string | number>;
  active_run_id?: string | null;
  candidates?: ProductCandidateView[];
  recommendation_routes?: RecommendationRouteView[];
  mission: ShoppingMissionView;
  selected_product_ids?: string[];
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
export type MediaInterpretation = {{
  media_id: string; kind: "image" | "audio"; recognized_text: string;
  category?: "手机" | "电脑" | "耳机" | "相机" | null;
  visible_attributes: string[]; uncertainties: string[]; supported: boolean;
}};
export type MediaConfirmation = {{ source_run_id: string; text: string }};
export type MediaCreated = {{
  media_id: string;
  kind: "image" | "audio";
  content_type: string;
  size_bytes: number;
  sha256: string;
  expires_at: string;
}};
export type ExplorationDirection = {{
  direction_id: string; title: string; category: string; experience_tags: string[];
  evidence_refs: string[]; supporting_product_ids: string[];
  scenario_hint?: string; try_first?: string; to_confirm?: string;
}};
export type ExplorationState = {{
  directions: ExplorationDirection[]; feedback: Record<string, "interested" | "not_interested">;
  shown_direction_ids: string[]; shown_product_ids: string[]; experience_tags: string[];
  selected_direction_id: string | null; exhausted: boolean; ended: boolean;
  outcome?: "UNDECIDED" | "USE_EXISTING" | "NOT_BUYING" | null;
}};
export type ExplorationAction = {{
  kind: "start" | "feedback" | "next" | "select_for_purchase" | "end";
  experience_tags?: ("life_improvement" | "novelty")[];
  direction_id?: string | null; value?: "interested" | "not_interested" | "neutral" | null;
  outcome?: "UNDECIDED" | "USE_EXISTING" | "NOT_BUYING" | null;
}};
export type TurnRequest = {{ text?: string; media_ids?: string[];
  exploration_action?: ExplorationAction | null; expected_mission_version?: number | null;
  media_confirmation?: MediaConfirmation | null;
}};
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
  business_facts?: BusinessFactView[];
}};
export type BusinessFactView = {{
  fact_type: "price" | "inventory" | "delivery" | "merchant" | "after_sales";
  summary: string;
  verification_level: "LIVE_AUTHORIZED" | "FEED_VERIFIED" | "DISCOVERY_ONLY" | "DEMO_FIXTURE";
  observed_at: string;
  expires_at?: string | null;
  evidence_ref: string;
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
export type CartItemView = {{ offer_id: string; quantity: number; product: ProductView; quote: OfferView }};
export type CartView = {{ items: CartItemView[] }};
export type CartMutation = {{ operation: "add" | "set" | "remove"; offer_id: string; quantity?: number }};
export type CreateWatcherRequest = {{ kind: "PRICE_BELOW" | "RESTOCK"; offer_id: string; threshold_minor?: number | null }};
export type WatcherView = {{
  watcher_id: string;
  thread_id: string;
  offer_id: string;
  kind: "PRICE_BELOW" | "RESTOCK";
  threshold_minor?: number | null;
  status: "DEMO_DRAFT";
  scheduler_active: false;
  disclosure: string;
  created_at: string;
}};
export type WatcherCollection = {{ watchers: WatcherView[] }};
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
  status: "RUNNING" | "COMPLETED" | "FAILED" | "WAITING_APPROVAL" | "WAITING_CLARIFICATION";
  prompt_version: string;
  model_version: string;
  retrieval_mode: string;
  duration_ms: number;
  estimated_cost_microunits: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
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
  evidence_level: "LOCAL" | "INTEGRATION" | "CHALLENGE" | "LIVE" | "RELEASE";
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
    # Generated Python participates in the same pinned formatter gate as source.
    # Format before comparison so codegen and ruff cannot invalidate each other.
    python = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--stdin-filename", "generated.py", "-"],
        input=python,
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
        encoding="utf-8",
    ).stdout
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
