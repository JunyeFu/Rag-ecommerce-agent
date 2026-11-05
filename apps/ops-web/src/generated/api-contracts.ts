// Generated file; do not edit. generator=4 source_sha256=174853fd5afac40fa49aeb1516c200f0ea2f4f7602603befea83a1988a031c91
export const CONTRACT_VERSION = "0.2.0" as const;
export const CONTRACT_SOURCE_SHA256 = "174853fd5afac40fa49aeb1516c200f0ea2f4f7602603befea83a1988a031c91" as const;

export type HealthResponse = { status: "ok"; contract_version: string };
export type CreateThreadRequest = { goal: string };
export type ThreadCreated = { thread_id: string; mission_id: string };
export type MissionItemView = { category: string; quantity: number };
export type ShoppingMissionView = {
  goal: string;
  version: number;
  items?: MissionItemView[];
  hard_constraints?: string[];
  soft_preferences?: string[];
  unknowns?: string[];
  budget_total_minor?: number | null;
  currency: "CNY";
};
export type ProductCandidateView = {
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
};
export type RecommendationRouteView = {
  route_type: "STRICT" | "BUDGET" | "ALTERNATIVE";
  status: "AVAILABLE" | "UNAVAILABLE";
  summary: string;
  relaxed_constraints?: string[];
  product_ids?: string[];
};
export type ComparisonSelection = { product_ids?: string[] };
export type ThreadExperience = { title?: string | null; archived?: boolean; feedback?: Record<string, string> };
export type CandidateFeedback = { product_id: string; expected_mission_version: number; scope?: "PRODUCT" | "CATEGORY"; reason: string; undo?: boolean };
export type ThreadHistoryPatch = { title?: string | null; archived?: boolean | null };
export type ThreadHistoryEntry = { thread_id: string; goal: string; experience: ThreadExperience; mode: "PURCHASE" | "DISCOVERY" };
export type ConversationMessage = { run_id: string; role: "user" | "assistant" | "system"; text: string };
export type ThreadSnapshot = {
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
export type MediaInterpretation = {
  media_id: string; kind: "image" | "audio"; recognized_text: string;
  category?: "手机" | "电脑" | "耳机" | "相机" | null;
  visible_attributes: string[]; uncertainties: string[]; supported: boolean;
};
export type MediaConfirmation = { source_run_id: string; text: string };
export type MediaCreated = {
  media_id: string;
  kind: "image" | "audio";
  content_type: string;
  size_bytes: number;
  sha256: string;
  expires_at: string;
};
export type ExplorationDirection = {
  direction_id: string; title: string; category: string; experience_tags: string[];
  evidence_refs: string[]; supporting_product_ids: string[];
  scenario_hint?: string; try_first?: string; to_confirm?: string;
};
export type ExplorationState = {
  directions: ExplorationDirection[]; feedback: Record<string, "interested" | "not_interested">;
  shown_direction_ids: string[]; shown_product_ids: string[]; experience_tags: string[];
  selected_direction_id: string | null; exhausted: boolean; ended: boolean;
  outcome?: "UNDECIDED" | "USE_EXISTING" | "NOT_BUYING" | null;
};
export type ExplorationAction = {
  kind: "start" | "feedback" | "next" | "select_for_purchase" | "end";
  experience_tags?: ("life_improvement" | "novelty")[];
  direction_id?: string | null; value?: "interested" | "not_interested" | "neutral" | null;
  outcome?: "UNDECIDED" | "USE_EXISTING" | "NOT_BUYING" | null;
};
export type TurnRequest = { text?: string; media_ids?: string[];
  exploration_action?: ExplorationAction | null; expected_mission_version?: number | null;
  media_confirmation?: MediaConfirmation | null;
};
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
  business_facts?: BusinessFactView[];
};
export type BusinessFactView = {
  fact_type: "price" | "inventory" | "delivery" | "merchant" | "after_sales";
  summary: string;
  verification_level: "LIVE_AUTHORIZED" | "FEED_VERIFIED" | "DISCOVERY_ONLY" | "DEMO_FIXTURE";
  observed_at: string;
  expires_at?: string | null;
  evidence_ref: string;
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
export type CartItemView = { offer_id: string; quantity: number; product: ProductView; quote: OfferView };
export type CartView = { items: CartItemView[] };
export type CartMutation = { operation: "add" | "set" | "remove"; offer_id: string; quantity?: number };
export type CreateWatcherRequest = { kind: "PRICE_BELOW" | "RESTOCK"; offer_id: string; threshold_minor?: number | null };
export type WatcherView = {
  watcher_id: string;
  thread_id: string;
  offer_id: string;
  kind: "PRICE_BELOW" | "RESTOCK";
  threshold_minor?: number | null;
  status: "DEMO_DRAFT";
  scheduler_active: false;
  disclosure: string;
  created_at: string;
};
export type WatcherCollection = { watchers: WatcherView[] };
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
  evidence_level: "LOCAL" | "INTEGRATION" | "CHALLENGE" | "LIVE" | "RELEASE";
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
  auth_mode: "development_headers" | "server_bearer";
  visible_fields: string[];
  prohibited_fields: string[];
  export_enabled: boolean;
  audit_append_only: boolean;
};
