// Generated file; do not edit. generator=3 source_sha256=08fa7e7cb7446628bc1407cedc5bffb4a5bbfb0914ed1bca8c91216a5799d076
export const CONTRACT_VERSION = "0.2.0" as const;
export const CONTRACT_SOURCE_SHA256 = "08fa7e7cb7446628bc1407cedc5bffb4a5bbfb0914ed1bca8c91216a5799d076" as const;

export type HealthResponse = { status: "ok"; contract_version: string };
export type CreateThreadRequest = { goal: string };
export type ThreadCreated = { thread_id: string; mission_id: string };
export type ProductCandidateView = {
  product_id: string;
  variant_id: string;
  title: string;
  fit_summary?: string;
  matched_constraints?: string[];
  unmet_constraints?: string[];
  risks?: string[];
  evidence_refs?: string[];
};
export type ThreadSnapshot = {
  thread_id: string;
  mission_id: string;
  goal: string;
  status: "IDLE" | "RUNNING" | "WAITING_APPROVAL" | "WAITING_CLARIFICATION" | "COMPLETED" | "FAILED";
  last_event_id: number;
  pending_action?: string | null;
  candidates?: ProductCandidateView[];
};
export type ProductView = {
  product_id: string;
  variant_id: string;
  title: string;
  category: string;
  brand: string;
  attributes: Record<string, string>;
  image_ref?: string | null;
  evidence_refs: string[];
};
export type MediaCreated = {
  media_id: string;
  kind: "image" | "audio";
  content_type: string;
  size_bytes: number;
  sha256: string;
  expires_at: string;
};
export type TurnRequest = { text?: string; media_ids?: string[] };
export type TurnAccepted = { run_id: string; replayed: boolean; event_count: number };
export type AgentDecision = { tool_name: string; approved: boolean };
export type DecisionAccepted = { run_id: string; approved: boolean; event_count: number };
export type DeletionResult = { deleted: boolean };
export type OfferView = {
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
};
export type OfferCollection = { product_id: string; offers: OfferView[] };
export type ResolveOfferRequest = { quote_id?: string | null; confirmed_quote_change?: boolean };
export type ResolvedOffer = {
  offer_id: string;
  link_url?: string | null;
  disclosure: string;
  expires_at?: string | null;
  quote_changed: boolean;
  requires_confirmation: boolean;
};
export type ShoppingListView = { list_id: string; name: string; variant_ids: string[] };
export type ShoppingListsResponse = { lists: ShoppingListView[] };
export type CreateListRequest = { name: string };
export type PatchListRequest = {
  name?: string | null;
  add_variant_id?: string | null;
  remove_variant_id?: string | null;
};
export type CartItemView = { offer_id: string; quantity: number };
export type CartView = { items: CartItemView[] };
export type CartMutation = { operation: "add" | "set" | "remove"; offer_id: string; quantity?: number };
export type EvidenceBoundary = { local_evidence: string; external_gate?: string | null };
export type ConnectorStatus = {
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
};
export type EntityConflict = {
  conflict_id: string;
  left_entity_ref: string;
  right_entity_ref: string;
  conflict_fields: string[];
  confidence: number;
  status: "PENDING" | "MERGED" | "KEPT_SEPARATE";
  source_refs: string[];
  observed_at: string;
};
export type ResolveConflictRequest = { decision: "MERGE" | "KEEP_SEPARATE"; reason: string };
export type ToolInvocationSummary = {
  tool: string;
  status: "COMPLETED" | "FAILED" | "APPROVAL_REQUIRED";
  arguments_sha256: string;
  evidence_refs: string[];
  duration_ms: number;
};
export type AgentTraceSummary = {
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
};
export type EvaluationRun = {
  run_id: string;
  dataset_version: string;
  runner_version: string;
  status: "PASSED" | "FAILED" | "BLOCKED" | "QUEUED";
  case_count: number;
  metrics: Record<string, number>;
  evidence: EvidenceBoundary;
  created_at: string;
};
export type StartEvaluationRequest = { dataset_version: string; runner_version: string };
export type ReleaseGate = {
  gate_id: string;
  title: string;
  evidence_level: "LOCAL" | "INTEGRATION" | "LIVE" | "HUMAN" | "RELEASE";
  status: "PASSED" | "FAILED" | "BLOCKED" | "NOT_RUN";
  evidence_ref?: string | null;
  blocker?: string | null;
};
export type AuditEvent = {
  sequence: number;
  event_id: string;
  actor_ref: string;
  action: string;
  object_ref: string;
  payload_sha256: string;
  occurred_at: string;
};
export type OpsPolicy = {
  auth_mode: "development_headers";
  visible_fields: string[];
  prohibited_fields: string[];
  export_enabled: boolean;
  audit_append_only: boolean;
};
