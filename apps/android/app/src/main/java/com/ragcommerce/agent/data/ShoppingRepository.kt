package com.ragcommerce.agent.data

import android.content.Context
import android.net.Uri
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.MutablePreferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import com.ragcommerce.agent.BuildConfig
import com.ragcommerce.agent.data.local.MissionEntity
import com.ragcommerce.agent.data.local.SavedItemEntity
import com.ragcommerce.agent.data.local.ShoppingDao
import com.ragcommerce.agent.data.remote.AgentEventStream
import com.ragcommerce.agent.data.remote.CommerceApi
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.toList
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.security.MessageDigest
import java.time.Instant
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

data class LocalShoppingSnapshot(
    val mission: MissionEntity?,
    val items: List<SavedItemEntity>,
    val selectedTab: String,
    val pendingRunId: String?,
    val pendingApprovalTool: String?,
    val lastEventId: Long,
    val qualityDataConsent: Boolean,
)

data class MediaAttachmentInput(
    val uri: String,
    val kind: String,
)

data class TurnAcceptedRemote(
    val runId: String,
    val replayed: Boolean,
)

data class MerchantResolution(
    val url: String?,
    val expiresAt: String?,
    val quoteChanged: Boolean,
    val requiresConfirmation: Boolean,
    val disclosure: String,
)

data class RemoteThreadSnapshot(
    val experience: com.ragcommerce.agent.generated.ThreadExperience = com.ragcommerce.agent.generated.ThreadExperience(),
    val pendingMediaInterpretations: List<com.ragcommerce.agent.generated.MediaInterpretation> = emptyList(),
    val mode: String = "PURCHASE",
    val exploration: com.ragcommerce.agent.generated.ExplorationState? = null,
    val activeRunId: String? = null,
    val goal: String,
    val status: String,
    val lastEventId: Long,
    val pendingAction: String?,
    val pendingActionArguments: Map<String, String> = emptyMap(),
    val products: List<com.ragcommerce.agent.ui.EvidenceProductUi>,
    val recommendationRoutes: List<com.ragcommerce.agent.ui.RecommendationRouteUi> = emptyList(),
    val mission: com.ragcommerce.agent.ui.ShoppingMissionUi,
    val selectedProductIds: Set<String>,
    val offers: List<com.ragcommerce.agent.ui.OfferUi> = emptyList(),
    val watchers: List<com.ragcommerce.agent.ui.WatcherUi> = emptyList(),
) {
    val resumableRunId: String?
        get() = activeRunId.takeIf { status in setOf("RUNNING", "WAITING_APPROVAL") }
}

private val pendingRunIdKey = stringPreferencesKey("pending_run_id")
private val pendingApprovalToolKey = stringPreferencesKey("pending_approval_tool")
private val lastEventIdKey = longPreferencesKey("last_event_id")

internal fun restoreRunPreferences(preferences: MutablePreferences, snapshot: RemoteThreadSnapshot) {
    val runId = snapshot.resumableRunId
    if (runId == null) {
        preferences.remove(pendingRunIdKey)
        preferences.remove(lastEventIdKey)
    } else {
        preferences[pendingRunIdKey] = runId
        preferences[lastEventIdKey] = snapshot.lastEventId
    }
    if (snapshot.status == "WAITING_APPROVAL" && runId != null && snapshot.pendingAction != null) {
        preferences[pendingApprovalToolKey] = snapshot.pendingAction
    } else {
        preferences.remove(pendingApprovalToolKey)
    }
}

internal fun parseOfferCollection(
    productId: String,
    variantId: String,
    payload: String,
): List<com.ragcommerce.agent.ui.OfferUi> {
    val values = JSONObject(payload).getJSONArray("offers")
    return (0 until values.length()).map { index ->
        values.getJSONObject(index).let { item ->
            com.ragcommerce.agent.ui.OfferUi(
                id = item.getString("offer_id"),
                productId = productId,
                variantId = variantId,
                merchantName = item.getString("merchant_name"),
                priceText = item.longValueOrNull("price_minor")?.let { "¥%.2f".format(it / 100.0) },
                shippingText = item.longValueOrNull("shipping_minor")?.let { "¥%.2f".format(it / 100.0) },
                verification = item.getString("verification"),
                collectedAt = item.getString("collected_at"),
                expiresAt = item.getString("expires_at"),
                sourceRef = item.getString("source_ref"),
                quoteState = when {
                    item.getString("availability") != "AVAILABLE" -> com.ragcommerce.agent.ui.QuoteState.UNAVAILABLE
                    !Instant.parse(item.getString("expires_at")).isAfter(Instant.now()) -> com.ragcommerce.agent.ui.QuoteState.EXPIRED
                    else -> com.ragcommerce.agent.ui.QuoteState.CURRENT
                },
                disclosure = "演示报价仅用于本地导购流程，不代表真实市场供应",
                priceMinor = item.longValueOrNull("price_minor"),
                businessFacts = parseBusinessFacts(item),
            )
        }
    }
}

internal fun parseWaitingCart(payload: String): com.ragcommerce.agent.ui.WaitingCartUi {
    val items = JSONObject(payload).getJSONArray("items")
    val quantities = (0 until items.length()).associate { index ->
        val item = items.getJSONObject(index)
        item.getString("offer_id") to item.getInt("quantity")
    }
    val offers = (0 until items.length()).map { index ->
        val item = items.getJSONObject(index)
        val product = item.getJSONObject("product")
        parseOfferCollection(product.getString("product_id"), product.getString("variant_id"),
            JSONObject().put("offers", JSONArray().put(item.getJSONObject("quote"))).toString())
            .single().copy(productTitle = product.getString("title"))
    }
    return com.ragcommerce.agent.ui.WaitingCartUi(quantities, offers)
}

internal fun parseExploration(root: JSONObject): com.ragcommerce.agent.generated.ExplorationState {
    fun strings(item: JSONObject, name: String): List<String> = item.getJSONArray(name).let { array ->
        (0 until array.length()).map { array.getString(it) }
    }
    val directions = root.getJSONArray("directions")
    val feedback = root.getJSONObject("feedback")
    return com.ragcommerce.agent.generated.ExplorationState(
        directions = (0 until directions.length()).map { i ->
            val d = directions.getJSONObject(i)
            com.ragcommerce.agent.generated.ExplorationDirection(
                d.getString("direction_id"), d.getString("title"), d.getString("category"),
                strings(d, "experience_tags"), strings(d, "evidence_refs"), strings(d, "supporting_product_ids"),
                d.optString("scenario_hint"), d.optString("try_first"), d.optString("to_confirm"),
            )
        },
        feedback = feedback.keys().asSequence().associateWith { feedback.getString(it) },
        shown_direction_ids = strings(root, "shown_direction_ids"),
        shown_product_ids = strings(root, "shown_product_ids"),
        experience_tags = strings(root, "experience_tags"),
        selected_direction_id = if (root.isNull("selected_direction_id")) null else root.getString("selected_direction_id"),
        exhausted = root.getBoolean("exhausted"), ended = root.getBoolean("ended"),
        outcome = if (root.isNull("outcome")) null else root.getString("outcome"),
    )
}

internal fun parseMediaInterpretation(root: JSONObject): com.ragcommerce.agent.generated.MediaInterpretation =
    com.ragcommerce.agent.generated.MediaInterpretation(
        media_id = root.getString("media_id"), kind = root.getString("kind"),
        recognized_text = root.getString("recognized_text"),
        category = if (root.isNull("category")) null else root.getString("category"),
        visible_attributes = root.stringValues("visible_attributes"),
        uncertainties = root.stringValues("uncertainties"), supported = root.getBoolean("supported"),
    )

internal fun parseMediaEvent(data: Map<String, String>): com.ragcommerce.agent.generated.MediaInterpretation =
    parseMediaInterpretation(JSONObject(data).apply {
        put("category", data.getValue("category").let { if (it == "null") JSONObject.NULL else it })
        put("visible_attributes", JSONArray(data.getValue("visible_attributes")))
        put("uncertainties", JSONArray(data.getValue("uncertainties")))
    })

internal fun parseThreadSnapshot(payload: String): RemoteThreadSnapshot {
    val root = JSONObject(payload)
    val candidates = root.optJSONArray("candidates") ?: JSONArray()
    val products = (0 until candidates.length()).mapNotNull { index ->
        candidates.optJSONObject(index)?.let { item ->
            com.ragcommerce.agent.ui.EvidenceProductUi(
                id = item.getString("product_id"),
                variantId = item.getString("variant_id"),
                title = item.getString("title"),
                fitSummary = item.optString("fit_summary"),
                matchedConstraints = item.stringValues("matched_constraints"),
                unmetConstraints = item.stringValues("unmet_constraints"),
                risks = item.stringValues("risks"),
                evidenceRefs = item.stringValues("evidence_refs"),
                recommendationType = com.ragcommerce.agent.ui.RecommendationType.valueOf(
                    item.optString("recommendation_type", "STRICT"),
                ),
                relaxedConstraints = item.stringValues("relaxed_constraints"),
            )
        }
    }
    return RemoteThreadSnapshot(
        experience = root.optJSONObject("experience")?.let { obj ->
            com.ragcommerce.agent.generated.ThreadExperience(
                if (obj.isNull("title")) null else obj.getString("title"), obj.getBoolean("archived"),
                obj.getJSONObject("feedback").let { values -> values.keys().asSequence().associateWith { values.getString(it) } },
            )
        } ?: com.ragcommerce.agent.generated.ThreadExperience(),
        pendingMediaInterpretations = root.optJSONArray("pending_media_interpretations")?.let { values ->
            (0 until values.length()).map { parseMediaInterpretation(values.getJSONObject(it)) }
        } ?: emptyList(),
        mode = root.optString("mode", "PURCHASE"),
        exploration = if (root.isNull("exploration")) null else parseExploration(root.getJSONObject("exploration")),
        activeRunId = if (root.isNull("active_run_id")) null else root.getString("active_run_id"),
        goal = root.getString("goal"),
        status = root.getString("status"),
        lastEventId = root.getLong("last_event_id"),
        pendingAction = if (root.isNull("pending_action")) null else root.getString("pending_action"),
        pendingActionArguments = root.optJSONObject("pending_action_arguments")?.let { obj -> obj.keys().asSequence().associateWith { obj.get(it).toString() } } ?: emptyMap(),
        products = products,
        recommendationRoutes = parseRecommendationRoutes(root.optJSONArray("recommendation_routes")),
        mission = parseShoppingMission(root.getJSONObject("mission")),
        selectedProductIds = root.stringValues("selected_product_ids").toSet(),
    )
}

internal fun parseRecommendationRoutes(
    values: JSONArray?,
): List<com.ragcommerce.agent.ui.RecommendationRouteUi> {
    val routes = values ?: JSONArray()
    return (0 until routes.length()).mapNotNull { index ->
        routes.optJSONObject(index)?.let { item ->
            com.ragcommerce.agent.ui.RecommendationRouteUi(
                type = com.ragcommerce.agent.ui.RecommendationType.valueOf(item.getString("route_type")),
                available = item.getString("status") == "AVAILABLE",
                summary = item.getString("summary"),
                relaxedConstraints = item.stringValues("relaxed_constraints"),
                productIds = item.stringValues("product_ids"),
            )
        }
    }
}

internal fun parseBusinessFacts(item: JSONObject): List<com.ragcommerce.agent.ui.BusinessFactUi> {
    val values = item.optJSONArray("business_facts") ?: JSONArray()
    return (0 until values.length()).mapNotNull { index ->
        values.optJSONObject(index)?.let { fact ->
            com.ragcommerce.agent.ui.BusinessFactUi(
                type = fact.getString("fact_type"),
                summary = fact.getString("summary"),
                verificationLevel = fact.getString("verification_level"),
                observedAt = fact.getString("observed_at"),
                expiresAt = if (fact.isNull("expires_at")) null else fact.getString("expires_at"),
                evidenceRef = fact.getString("evidence_ref"),
            )
        }
    }
}

internal fun parseShoppingMission(item: JSONObject): com.ragcommerce.agent.ui.ShoppingMissionUi {
    val values = item.optJSONArray("items") ?: JSONArray()
    return com.ragcommerce.agent.ui.ShoppingMissionUi(
        goal = item.getString("goal"),
        version = item.getInt("version"),
        items = (0 until values.length()).map { index ->
            val value = values.getJSONObject(index)
            com.ragcommerce.agent.ui.MissionItemUi(
                category = value.getString("category"),
                quantity = value.getInt("quantity"),
            )
        },
        hardConstraints = item.stringValues("hard_constraints"),
        softPreferences = item.stringValues("soft_preferences"),
        unknowns = item.stringValues("unknowns"),
        budgetTotalMinor = item.longValueOrNull("budget_total_minor"),
    )
}

internal fun parseWatcher(item: JSONObject): com.ragcommerce.agent.ui.WatcherUi =
    com.ragcommerce.agent.ui.WatcherUi(
        id = item.getString("watcher_id"),
        offerId = item.getString("offer_id"),
        kind = item.getString("kind"),
        thresholdMinor = item.longValueOrNull("threshold_minor"),
        disclosure = item.getString("disclosure"),
    )

private fun JSONObject.stringValues(key: String): List<String> {
    val values = optJSONArray(key) ?: return emptyList()
    return (0 until values.length()).mapNotNull { values.optString(it).takeIf(String::isNotBlank) }
}

private fun JSONObject.longValueOrNull(key: String): Long? =
    if (has(key) && !isNull(key)) getLong(key) else null

data class AgentPublicEvent(
    val id: Long,
    val name: String,
    val data: Map<String, String>,
)

internal fun parseSsePayload(payload: String): List<AgentPublicEvent> = payload
    .split(Regex("\\r?\\n\\r?\\n"))
    .mapNotNull { block ->
        val lines = block.lines()
        val name = lines.firstOrNull { it.startsWith("event:") }
            ?.substringAfter(':')?.trim() ?: return@mapNotNull null
        val idLine = lines.firstOrNull { it.startsWith("id:") }
        val id = if (idLine != null) idLine.substringAfter(':').trim().toLong()
            else if (name == "progress") 0L else throw IllegalArgumentException("SSE event ID missing")
        val dataText = lines.filter { it.startsWith("data:") }
            .joinToString("\n") { it.substringAfter(':').trimStart() }
        val dataObject = JSONObject(dataText)
        val data = dataObject.keys().asSequence().associateWith { key ->
            dataObject.opt(key)?.toString().orEmpty()
        }
        AgentPublicEvent(id, name, data)
    }

interface ShoppingRepository {
    suspend fun history(): List<com.ragcommerce.agent.generated.ThreadHistoryEntry>
    suspend fun organizeThread(threadId: String, title: String?, archived: Boolean?)
    suspend fun activateThread(threadId: String)
    suspend fun messages(offset: Int): List<com.ragcommerce.agent.generated.ConversationMessage>
    suspend fun candidateFeedback(action: com.ragcommerce.agent.ui.ShoppingAction.ExcludeCandidate, version: Int): RemoteThreadSnapshot
    suspend fun undoCandidateFeedback(key: String, version: Int): RemoteThreadSnapshot
    suspend fun productFacts(productId: String): com.ragcommerce.agent.ui.EvidenceProductUi
    suspend fun productOffers(product: com.ragcommerce.agent.ui.EvidenceProductUi): List<com.ragcommerce.agent.ui.OfferUi>
    suspend fun refreshSavedCandidates()
    suspend fun removeSavedCandidate(productId: String)
    suspend fun compareSavedProducts(productIds: Set<String>): com.ragcommerce.agent.ui.SavedComparisonUi
    suspend fun restoreSavedComparison(): com.ragcommerce.agent.ui.SavedComparisonUi?
    suspend fun clearSavedComparison()
    fun observeLocal(): Flow<LocalShoppingSnapshot>

    suspend fun saveMission(goal: String)

    suspend fun saveSelectedTab(value: String)

    suspend fun setQualityDataConsent(granted: Boolean)

    suspend fun probeConnection(): Boolean

    suspend fun submitTurn(text: String, media: List<MediaAttachmentInput>): TurnAcceptedRemote
    suspend fun confirmMedia(sourceRunId: String, text: String, version: Int): TurnAcceptedRemote
    suspend fun explore(action: com.ragcommerce.agent.ui.ShoppingAction.Explore, version: Int): TurnAcceptedRemote

    suspend fun readEvents(runId: String, lastEventId: Long): List<AgentPublicEvent>
    fun observeEvents(runId: String, lastEventId: Long): Flow<AgentPublicEvent> = flow {
        readEvents(runId, lastEventId).forEach { emit(it) }
    }

    suspend fun restoreThread(): RemoteThreadSnapshot?

    suspend fun startNewMission()

    suspend fun updateMissionConstraints(goal: String): com.ragcommerce.agent.ui.ShoppingMissionUi

    suspend fun updateComparisonSelection(productIds: Set<String>): Set<String>

    suspend fun decide(runId: String, tool: String, approved: Boolean)

    suspend fun resolveOffer(offerId: String, confirmedQuoteChange: Boolean): MerchantResolution
    suspend fun requoteOffer(offer: com.ragcommerce.agent.ui.OfferUi): List<com.ragcommerce.agent.ui.OfferUi>

    suspend fun saveProduct(product: com.ragcommerce.agent.ui.EvidenceProductUi)

    suspend fun waitingCart(): com.ragcommerce.agent.ui.WaitingCartUi

    suspend fun updateOfferQuantity(offer: com.ragcommerce.agent.ui.OfferUi, quantity: Int): com.ragcommerce.agent.ui.WaitingCartUi

    suspend fun createWatcher(
        offer: com.ragcommerce.agent.ui.OfferUi,
        kind: String,
        thresholdMinor: Long?,
    ): com.ragcommerce.agent.ui.WatcherUi

    suspend fun deleteMyData()
}

@Singleton
class NetworkShoppingRepository @Inject constructor(
    @ApplicationContext private val context: Context,
    private val dao: ShoppingDao,
    private val settings: DataStore<Preferences>,
    private val api: CommerceApi,
    private val eventStream: AgentEventStream,
) : ShoppingRepository {
    private val selectedTabKey = stringPreferencesKey("selected_primary_tab")
    private val userIdKey = stringPreferencesKey("install_user_id")
    private val threadIdKey = stringPreferencesKey("active_thread_id")
    private val pendingFingerprintKey = stringPreferencesKey("pending_turn_fingerprint")
    private val pendingIdempotencyKey = stringPreferencesKey("pending_turn_idempotency")
    private val pendingMediaIdsKey = stringPreferencesKey("pending_turn_media_ids")
    private val qualityDataConsentKey = booleanPreferencesKey("quality_data_consent")
    private val savedComparisonKey = stringPreferencesKey("saved_comparison_ids")

    override suspend fun history(): List<com.ragcommerce.agent.generated.ThreadHistoryEntry> =
        api.threads(requireUserId()).use { response ->
            val values = JSONArray(response.string())
            (0 until values.length()).map { index ->
                val row = values.getJSONObject(index)
                val experience = row.getJSONObject("experience")
                com.ragcommerce.agent.generated.ThreadHistoryEntry(row.getString("thread_id"), row.getString("goal"),
                    com.ragcommerce.agent.generated.ThreadExperience(if (experience.isNull("title")) null else experience.getString("title"), experience.getBoolean("archived")), row.getString("mode"))
            }
        }

    override suspend fun organizeThread(threadId: String, title: String?, archived: Boolean?) {
        val body = JSONObject().apply { title?.let { put("title", it) }; archived?.let { put("archived", it) } }
        api.organizeThread(requireUserId(), threadId, body.toString().toRequestBody(JSON_MEDIA_TYPE)).use { }
    }

    override suspend fun activateThread(threadId: String) {
        val snapshot = api.thread(requireUserId(), threadId).use { parseThreadSnapshot(it.string()) }
        settings.edit {
            it[threadIdKey] = threadId
            it.remove(pendingFingerprintKey); it.remove(pendingIdempotencyKey); it.remove(pendingMediaIdsKey)
            restoreRunPreferences(it, snapshot)
        }
        saveMission(snapshot.goal)
    }

    override suspend fun messages(offset: Int): List<com.ragcommerce.agent.generated.ConversationMessage> {
        val threadId = settings.data.first()[threadIdKey] ?: return emptyList()
        return api.messages(requireUserId(), threadId, offset).use { response ->
            val values = JSONArray(response.string())
            (0 until values.length()).map { index -> values.getJSONObject(index).let { row ->
                com.ragcommerce.agent.generated.ConversationMessage(row.getString("run_id"), row.getString("role"), row.getString("text"))
            } }
        }
    }

    override suspend fun candidateFeedback(action: com.ragcommerce.agent.ui.ShoppingAction.ExcludeCandidate, version: Int): RemoteThreadSnapshot {
        val threadId = requireNotNull(settings.data.first()[threadIdKey])
        val body = JSONObject().put("product_id", action.productId).put("expected_mission_version", version)
            .put("scope", action.scope).put("reason", action.reason).put("undo", action.undo)
        return api.feedback(requireUserId(), threadId, body.toString().toRequestBody(JSON_MEDIA_TYPE)).use { parseThreadSnapshot(it.string()) }
    }

    override suspend fun undoCandidateFeedback(key: String, version: Int): RemoteThreadSnapshot =
        api.undoFeedback(requireUserId(), requireNotNull(settings.data.first()[threadIdKey]), key, version).use { parseThreadSnapshot(it.string()) }

    private fun productFromJson(row: JSONObject): com.ragcommerce.agent.ui.EvidenceProductUi =
        com.ragcommerce.agent.ui.EvidenceProductUi(row.getString("product_id"), row.getString("variant_id"), row.getString("title"),
            "已保存的目录商品；请重新核对本次用途和约束", emptyList(), emptyList(), emptyList(), row.stringValues("evidence_refs"),
            attributes = row.getJSONObject("attributes").let { a -> a.keys().asSequence().associateWith { a.getString(it) } },
            category = row.getString("category"), imageRef = if (row.isNull("image_ref")) null else row.getString("image_ref"))

    override suspend fun productFacts(productId: String): com.ragcommerce.agent.ui.EvidenceProductUi =
        api.product(requireUserId(), productId).use { productFromJson(JSONObject(it.string())) }

    override suspend fun productOffers(product: com.ragcommerce.agent.ui.EvidenceProductUi): List<com.ragcommerce.agent.ui.OfferUi> =
        api.offers(requireUserId(), product.id, false).use { parseOfferCollection(product.id, product.variantId, it.string()) }

    private suspend fun readSavedComparison(productIds: Set<String>): com.ragcommerce.agent.ui.SavedComparisonUi {
        if (productIds.size !in 2..4) throw com.ragcommerce.agent.ui.SavedComparisonSelectionException("请选择2–4款不同的已保存商品")
        val lists = api.lists(requireUserId()).use { JSONObject(it.string()).getJSONArray("lists") }
        val savedVariants = (0 until lists.length()).flatMap { lists.getJSONObject(it).stringValues("variant_ids") }.toSet()
        val products = productIds.map { productFacts(it) }
        if (products.any { it.variantId !in savedVariants })
            throw com.ragcommerce.agent.ui.SavedComparisonSelectionException("有商品已移出保存，请清空选择后重新选择")
        // Validate categories before reading quotes; comparison never creates an Agent run.
        com.ragcommerce.agent.ui.SavedComparisonUi.create(products, emptyList())
        return com.ragcommerce.agent.ui.SavedComparisonUi.create(products, products.flatMap { productOffers(it) })
    }

    override suspend fun compareSavedProducts(productIds: Set<String>): com.ragcommerce.agent.ui.SavedComparisonUi {
        val comparison = readSavedComparison(productIds)
        settings.edit { it[savedComparisonKey] = JSONArray(productIds.toList()).toString() }
        return comparison
    }

    override suspend fun restoreSavedComparison(): com.ragcommerce.agent.ui.SavedComparisonUi? {
        val stored = settings.data.first()[savedComparisonKey] ?: return null
        val ids = JSONArray(stored)
        return readSavedComparison((0 until ids.length()).map { ids.getString(it) }.toSet())
    }

    override suspend fun clearSavedComparison() { settings.edit { it.remove(savedComparisonKey) } }

    override suspend fun refreshSavedCandidates() {
        val userId = requireUserId()
        val lists = api.lists(userId).use { JSONObject(it.string()).getJSONArray("lists") }
        val variantIds = (0 until lists.length()).flatMap { index -> lists.getJSONObject(index).stringValues("variant_ids") }.distinct()
        val products = variantIds.map { id -> api.variant(userId, id).use { productFromJson(JSONObject(it.string())) } }
        dao.replaceCandidateCache(products.map { p -> SavedItemEntity("LIST:${p.id}", "LIST", p.id, p.title, p.evidenceRefs.firstOrNull().orEmpty(), 1) })
    }

    override suspend fun removeSavedCandidate(productId: String) {
        val userId = requireUserId()
        val product = productFacts(productId)
        val lists = api.lists(userId).use { JSONObject(it.string()).getJSONArray("lists") }
        (0 until lists.length()).map { lists.getJSONObject(it) }.filter { product.variantId in it.stringValues("variant_ids") }.forEach { list ->
            api.patchList(userId, list.getString("list_id"), JSONObject().put("remove_variant_id", product.variantId).toString().toRequestBody(JSON_MEDIA_TYPE)).use { }
        }
        refreshSavedCandidates()
        val stored = settings.data.first()[savedComparisonKey]
        if (stored != null && (0 until JSONArray(stored).length()).any { JSONArray(stored).getString(it) == productId }) clearSavedComparison()
    }

    override fun observeLocal(): Flow<LocalShoppingSnapshot> =
        combine(
            dao.observeMission(),
            dao.observeItems(),
            settings.data,
        ) { mission, items, preferences ->
            LocalShoppingSnapshot(
                mission = mission,
                items = items,
                selectedTab = preferences[selectedTabKey] ?: "TASK",
                pendingRunId = preferences[pendingRunIdKey],
                pendingApprovalTool = preferences[pendingApprovalToolKey],
                lastEventId = preferences[lastEventIdKey] ?: 0L,
                qualityDataConsent = preferences[qualityDataConsentKey] ?: false,
            )
        }

    override suspend fun saveMission(goal: String) {
        dao.saveMission(
            MissionEntity(
                id = "current-mission",
                goal = goal,
                updatedAtEpochMillis = System.currentTimeMillis(),
            ),
        )
    }

    override suspend fun saveSelectedTab(value: String) {
        settings.edit { it[selectedTabKey] = value }
    }

    override suspend fun setQualityDataConsent(granted: Boolean) {
        settings.edit { it[qualityDataConsentKey] = granted }
    }

    override suspend fun probeConnection(): Boolean = runCatching {
        api.health().use { }
        true
    }.getOrDefault(false)

    override suspend fun submitTurn(
        text: String,
        media: List<MediaAttachmentInput>,
    ): TurnAcceptedRemote {
        require(text.isNotBlank() || media.isNotEmpty()) { "turn requires text or media" }
        require(media.size <= 8) { "at most 8 media attachments are allowed" }
        val userId = requireUserId()
        val threadId = requireThread(userId, text.ifBlank { "多模态导购任务" })
        val fingerprint = sha256(
            buildString {
                append(text)
                media.forEach { append('\u0000').append(it.kind).append('\u0000').append(it.uri) }
            },
        )
        val before = settings.data.first()
        val reusePending = before[pendingFingerprintKey] == fingerprint &&
            !before[pendingIdempotencyKey].isNullOrBlank()
        val mediaIds = if (reusePending) {
            before[pendingMediaIdsKey].orEmpty().split(',').filter(String::isNotBlank)
        } else {
            media.map { uploadMedia(userId, it) }
        }
        val idempotencyKey = if (reusePending) {
            requireNotNull(before[pendingIdempotencyKey])
        } else {
            "android-${UUID.randomUUID()}"
        }
        settings.edit { preferences ->
            preferences[pendingFingerprintKey] = fingerprint
            preferences[pendingIdempotencyKey] = idempotencyKey
            preferences[pendingMediaIdsKey] = mediaIds.joinToString(",")
        }
        val payload = JSONObject()
            .put("text", text)
            .put("media_ids", JSONArray(mediaIds))
            .toString()
            .toRequestBody(JSON_MEDIA_TYPE)
        val accepted = api.createTurn(userId, idempotencyKey, threadId, payload).use { body ->
            JSONObject(body.string())
        }
        val runId = accepted.getString("run_id")
        settings.edit { preferences ->
            preferences[pendingRunIdKey] = runId
            preferences[lastEventIdKey] = 0L
            preferences.remove(pendingFingerprintKey)
            preferences.remove(pendingIdempotencyKey)
            preferences.remove(pendingMediaIdsKey)
        }
        return TurnAcceptedRemote(runId, accepted.optBoolean("replayed", false))
    }

    override suspend fun confirmMedia(sourceRunId: String, text: String, version: Int): TurnAcceptedRemote {
        val userId = requireUserId()
        val threadId = requireNotNull(settings.data.first()[threadIdKey])
        val body = JSONObject().put("media_confirmation", JSONObject().put("source_run_id", sourceRunId).put("text", text))
            .put("expected_mission_version", version).toString()
        val fingerprint = sha256(body)
        val before = settings.data.first()
        val key = if (before[pendingFingerprintKey] == fingerprint) requireNotNull(before[pendingIdempotencyKey])
            else "android-confirm-media-${UUID.randomUUID()}"
        settings.edit { it[pendingFingerprintKey] = fingerprint; it[pendingIdempotencyKey] = key }
        val accepted = api.createTurn(userId, key, threadId, body.toRequestBody(JSON_MEDIA_TYPE)).use { JSONObject(it.string()) }
        val runId = accepted.getString("run_id")
        settings.edit {
            it[pendingRunIdKey] = runId; it[lastEventIdKey] = 0L
            it.remove(pendingApprovalToolKey); it.remove(pendingFingerprintKey); it.remove(pendingIdempotencyKey)
        }
        return TurnAcceptedRemote(runId, accepted.getBoolean("replayed"))
    }

    override suspend fun explore(action: com.ragcommerce.agent.ui.ShoppingAction.Explore, version: Int): TurnAcceptedRemote {
        val userId = requireUserId()
        val threadId = requireThread(userId, "随便看看")
        val request = JSONObject().put("kind", action.kind)
        if (action.tags.isNotEmpty()) request.put("experience_tags", JSONArray(action.tags))
        action.directionId?.let { request.put("direction_id", it) }
        action.value?.let { request.put("value", it) }
        action.outcome?.let { request.put("outcome", it) }
        val body = JSONObject().put("exploration_action", request)
            .put("expected_mission_version", version).toString()
        val fingerprint = sha256(body)
        val before = settings.data.first()
        val key = if (before[pendingFingerprintKey] == fingerprint) {
            requireNotNull(before[pendingIdempotencyKey])
        } else "android-explore-${UUID.randomUUID()}"
        settings.edit {
            it[pendingFingerprintKey] = fingerprint
            it[pendingIdempotencyKey] = key
        }
        val accepted = api.createTurn(userId, key, threadId, body.toRequestBody(JSON_MEDIA_TYPE))
            .use { JSONObject(it.string()) }
        val runId = accepted.getString("run_id")
        settings.edit {
            it[pendingRunIdKey] = runId
            it[lastEventIdKey] = 0L
            it.remove(pendingApprovalToolKey)
            it.remove(pendingFingerprintKey)
            it.remove(pendingIdempotencyKey)
        }
        return TurnAcceptedRemote(runId, accepted.getBoolean("replayed"))
    }

    override suspend fun readEvents(runId: String, lastEventId: Long): List<AgentPublicEvent> =
        observeEvents(runId, lastEventId).toList()

    override fun observeEvents(runId: String, lastEventId: Long): Flow<AgentPublicEvent> = flow {
        val userId = requireUserId()
        val url = BuildConfig.API_BASE_URL.toHttpUrl().newBuilder()
            .addPathSegments("v1/agent-runs/$runId/events")
            .build()
            .toString()
        var reachedStop = false
        eventStream.frames(url, userId, lastEventId).collect { frame ->
            parseSsePayload(frame).forEach { event ->
                reachedStop = event.name in setOf("completed", "failed", "approval_required", "clarification_required")
                if (event.name == "mission_updated" && settings.data.first()[pendingRunIdKey] == runId) {
                    event.data["goal"]?.let { saveMission(it) }
                }
                emit(event)
                settings.edit { preferences ->
                    if (preferences[pendingRunIdKey] != runId) return@edit
                    if (event.id > 0L) preferences[lastEventIdKey] = event.id
                    if (event.name == "approval_required") preferences[pendingApprovalToolKey] = event.data.getValue("tool")
                    if (event.name in setOf("completed", "failed")) {
                        preferences.remove(pendingRunIdKey)
                        preferences.remove(pendingApprovalToolKey)
                        preferences.remove(lastEventIdKey)
                    }
                }
            }
        }
        if (!reachedStop) throw java.io.IOException("SSE ended before a stop event")
    }

    override suspend fun restoreThread(): RemoteThreadSnapshot? {
        val preferences = settings.data.first()
        val threadId = preferences[threadIdKey] ?: return null
        val userId = preferences[userIdKey] ?: return null
        val snapshot = api.thread(userId, threadId).use { parseThreadSnapshot(it.string()) }
        val products = snapshot.products.map { candidate ->
            val facts = productFacts(candidate.id)
            candidate.copy(attributes = facts.attributes, category = facts.category, imageRef = facts.imageRef)
        }
        val offers = snapshot.products.flatMap { product ->
            api.offers(userId, product.id, false).use { response ->
                parseOfferCollection(product.id, product.variantId, response.string())
            }
        }
        val watchers = api.watchers(userId, threadId).use { response ->
            val values = JSONObject(response.string()).optJSONArray("watchers") ?: JSONArray()
            (0 until values.length()).map { parseWatcher(values.getJSONObject(it)) }
        }
        saveMission(snapshot.goal)
        settings.edit { restoreRunPreferences(it, snapshot) }
        return snapshot.copy(
            products = products,
            offers = offers,
            watchers = watchers,
        )
    }

    override suspend fun startNewMission() {
        dao.clearMissions()
        settings.edit { preferences ->
            preferences.remove(threadIdKey)
            preferences.remove(pendingRunIdKey)
            preferences.remove(pendingApprovalToolKey)
            preferences.remove(lastEventIdKey)
            preferences.remove(pendingFingerprintKey)
            preferences.remove(pendingIdempotencyKey)
            preferences.remove(pendingMediaIdsKey)
        }
    }

    override suspend fun updateMissionConstraints(
        goal: String,
    ): com.ragcommerce.agent.ui.ShoppingMissionUi {
        val preferences = settings.data.first()
        val threadId = requireNotNull(preferences[threadIdKey])
        val payload = JSONObject()
            .put("goal", goal)
            .toString()
            .toRequestBody(JSON_MEDIA_TYPE)
        return api.updateThreadConstraints(requireUserId(), threadId, payload).use {
            parseShoppingMission(JSONObject(it.string()))
        }
    }

    override suspend fun updateComparisonSelection(productIds: Set<String>): Set<String> {
        val preferences = settings.data.first()
        val threadId = requireNotNull(preferences[threadIdKey])
        val payload = JSONObject()
            .put("product_ids", JSONArray(productIds.toList()))
            .toString()
            .toRequestBody(JSON_MEDIA_TYPE)
        val response = api.updateComparisonSelection(
            requireUserId(),
            threadId,
            payload,
        ).use { JSONObject(it.string()) }
        return response.stringValues("product_ids").toSet()
    }

    override suspend fun decide(runId: String, tool: String, approved: Boolean) {
        val userId = requireUserId()
        val payload = JSONObject()
            .put("tool_name", tool)
            .put("approved", approved)
            .toString()
            .toRequestBody(JSON_MEDIA_TYPE)
        api.decide(userId, runId, payload).use { }
        settings.edit { it.remove(pendingApprovalToolKey) }
    }

    override suspend fun resolveOffer(
        offerId: String,
        confirmedQuoteChange: Boolean,
    ): MerchantResolution {
        val payload = JSONObject()
            .put("confirmed_quote_change", confirmedQuoteChange)
            .toString()
            .toRequestBody(JSON_MEDIA_TYPE)
        val resolved = api.resolveOffer(requireUserId(), offerId, payload).use {
            JSONObject(it.string())
        }
        return MerchantResolution(
            url = if (resolved.isNull("link_url")) null else resolved.getString("link_url"),
            expiresAt = if (resolved.isNull("expires_at")) null else resolved.getString("expires_at"),
            quoteChanged = resolved.getBoolean("quote_changed"),
            requiresConfirmation = resolved.getBoolean("requires_confirmation"),
            disclosure = resolved.getString("disclosure"),
        )
    }

    override suspend fun requoteOffer(offer: com.ragcommerce.agent.ui.OfferUi): List<com.ragcommerce.agent.ui.OfferUi> =
        api.offers(requireUserId(), offer.productId, true).use {
            parseOfferCollection(offer.productId, offer.variantId, it.string())
        }

    override suspend fun saveProduct(product: com.ragcommerce.agent.ui.EvidenceProductUi) {
        val userId = requireUserId()
        val current = api.lists(userId).use { JSONObject(it.string()) }.getJSONArray("lists")
        val listId = if (current.length() > 0) {
            current.getJSONObject(0).getString("list_id")
        } else {
            val request = JSONObject().put("name", "Agent 候选").toString().toRequestBody(JSON_MEDIA_TYPE)
            api.createList(userId, request).use { JSONObject(it.string()).getString("list_id") }
        }
        val request = JSONObject()
            .put("add_variant_id", product.variantId)
            .toString()
            .toRequestBody(JSON_MEDIA_TYPE)
        api.patchList(userId, listId, request).use { }
        dao.saveItem(
            SavedItemEntity(
                itemKey = "LIST:${product.id}",
                kind = "LIST",
                externalId = product.id,
                title = product.title,
                sourceRef = product.evidenceRefs.firstOrNull().orEmpty(),
                quantity = 1,
            ),
        )
    }

    override suspend fun waitingCart(): com.ragcommerce.agent.ui.WaitingCartUi =
        api.cart(requireUserId()).use { parseWaitingCart(it.string()) }

    override suspend fun updateOfferQuantity(offer: com.ragcommerce.agent.ui.OfferUi, quantity: Int): com.ragcommerce.agent.ui.WaitingCartUi {
        val request = JSONObject()
            .put("operation", if (quantity == 0) "remove" else "set")
            .put("offer_id", offer.id)
            .apply { if (quantity > 0) put("quantity", quantity) }
            .toString()
            .toRequestBody(JSON_MEDIA_TYPE)
        return api.mutateCart(requireUserId(), request).use { parseWaitingCart(it.string()) }
    }

    override suspend fun createWatcher(
        offer: com.ragcommerce.agent.ui.OfferUi,
        kind: String,
        thresholdMinor: Long?,
    ): com.ragcommerce.agent.ui.WatcherUi {
        val preferences = settings.data.first()
        val threadId = requireNotNull(preferences[threadIdKey])
        val request = JSONObject()
            .put("kind", kind)
            .put("offer_id", offer.id)
            .apply { if (thresholdMinor != null) put("threshold_minor", thresholdMinor) }
            .toString()
            .toRequestBody(JSON_MEDIA_TYPE)
        return api.createWatcher(requireUserId(), threadId, request).use { response ->
            parseWatcher(JSONObject(response.string()))
        }
    }

    override suspend fun deleteMyData() {
        api.deleteMyData(requireUserId(), "delete-my-data").use { }
        dao.clearMissions()
        dao.clearSavedItems()
        settings.edit { preferences ->
            preferences.clear()
            preferences[userIdKey] = UUID.randomUUID().toString()
            preferences[selectedTabKey] = "PROFILE"
        }
    }

    private suspend fun requireUserId(): String {
        settings.data.first()[userIdKey]?.let { return it }
        val generated = UUID.randomUUID().toString()
        settings.edit { preferences ->
            if (preferences[userIdKey] == null) preferences[userIdKey] = generated
        }
        return requireNotNull(settings.data.first()[userIdKey])
    }

    private suspend fun requireThread(userId: String, goal: String): String {
        settings.data.first()[threadIdKey]?.let { return it }
        val payload = JSONObject()
            .put("goal", goal.take(10_000))
            .toString()
            .toRequestBody(JSON_MEDIA_TYPE)
        val created = api.createThread(userId, payload).use { JSONObject(it.string()) }
        val threadId = created.getString("thread_id")
        settings.edit { it[threadIdKey] = threadId }
        return threadId
    }

    private suspend fun uploadMedia(userId: String, attachment: MediaAttachmentInput): String {
        val uri = Uri.parse(attachment.uri)
        val contentType = context.contentResolver.getType(uri)?.lowercase()
            ?: if (uri.scheme == "file" && attachment.kind == "audio" &&
                java.io.File(requireNotNull(uri.path)).canonicalFile.parentFile == java.io.File(context.cacheDir, "voice-input").canonicalFile) "audio/wav"
            else throw IllegalArgumentException("media content type is unavailable")
        require(contentType in SUPPORTED_MEDIA_TYPES) { "unsupported media type" }
        require(contentType.startsWith("${attachment.kind}/")) { "media kind does not match type" }
        val limit = if (attachment.kind == "image") IMAGE_LIMIT else AUDIO_LIMIT
        val content = context.contentResolver.openInputStream(uri)?.use { input ->
            val output = ByteArrayOutputStream()
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            var total = 0
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                total += read
                require(total <= limit) { "media exceeds client size limit" }
                output.write(buffer, 0, read)
            }
            output.toByteArray()
        } ?: throw IllegalArgumentException("media cannot be opened")
        val created = api.uploadMedia(
            userId,
            contentType,
            content.toRequestBody(contentType.toMediaType()),
        ).use { JSONObject(it.string()) }
        return created.getString("media_id")
    }

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8))
        .joinToString("") { byte -> "%02x".format(byte) }

    private companion object {
        val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
        const val IMAGE_LIMIT = 8 * 1024 * 1024
        const val AUDIO_LIMIT = 25 * 1024 * 1024
        val SUPPORTED_MEDIA_TYPES = setOf(
            "image/jpeg",
            "image/png",
            "image/webp",
            "audio/wav",
            "audio/mpeg",
            "audio/ogg",
        )
    }
}
