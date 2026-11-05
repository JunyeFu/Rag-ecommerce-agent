// Generated file; do not edit. generator=4 source_sha256=174853fd5afac40fa49aeb1516c200f0ea2f4f7602603befea83a1988a031c91
package com.ragcommerce.agent.generated

const val CONTRACT_VERSION: String = "0.2.0"
const val CONTRACT_SOURCE_SHA256: String = "174853fd5afac40fa49aeb1516c200f0ea2f4f7602603befea83a1988a031c91"

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
