// Generated file; do not edit. generator=3 source_sha256=08fa7e7cb7446628bc1407cedc5bffb4a5bbfb0914ed1bca8c91216a5799d076
package com.ragcommerce.agent.generated

const val CONTRACT_VERSION: String = "0.2.0"
const val CONTRACT_SOURCE_SHA256: String = "08fa7e7cb7446628bc1407cedc5bffb4a5bbfb0914ed1bca8c91216a5799d076"

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
