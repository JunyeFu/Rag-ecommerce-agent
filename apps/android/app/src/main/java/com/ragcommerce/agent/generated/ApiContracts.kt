// Generated file; do not edit. generator=2 source_sha256=267cb76a25754c1b81655dbd96c725e46520db160c05a6aea5febff81997350d
package com.ragcommerce.agent.generated

const val CONTRACT_VERSION: String = "0.1.0"
const val CONTRACT_SOURCE_SHA256: String = "267cb76a25754c1b81655dbd96c725e46520db160c05a6aea5febff81997350d"

data class HealthResponse(val status: String, val contract_version: String)
data class CreateThreadRequest(val goal: String)
data class ThreadCreated(val thread_id: String, val mission_id: String)
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
