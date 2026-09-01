package com.ragcommerce.agent.data

import android.content.Context
import android.net.Uri
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
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
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.security.MessageDigest
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
    val goal: String,
    val status: String,
    val lastEventId: Long,
    val pendingAction: String?,
    val products: List<com.ragcommerce.agent.ui.EvidenceProductUi>,
    val offers: List<com.ragcommerce.agent.ui.OfferUi> = emptyList(),
)

internal fun parseOfferCollection(
    product: com.ragcommerce.agent.ui.EvidenceProductUi,
    payload: String,
): List<com.ragcommerce.agent.ui.OfferUi> {
    val values = JSONObject(payload).optJSONArray("offers") ?: JSONArray()
    return (0 until values.length()).mapNotNull { index ->
        values.optJSONObject(index)?.let { item ->
            com.ragcommerce.agent.ui.OfferUi(
                id = item.getString("offer_id"),
                productId = product.id,
                variantId = product.variantId,
                merchantName = item.getString("merchant_name"),
                priceText = item.longValueOrNull("price_minor")?.let { "¥%.2f".format(it / 100.0) },
                shippingText = item.longValueOrNull("shipping_minor")?.let { "¥%.2f".format(it / 100.0) },
                verification = item.getString("verification"),
                collectedAt = item.getString("collected_at"),
                expiresAt = item.getString("expires_at"),
                sourceRef = item.getString("source_ref"),
                quoteState = if (item.optString("availability") == "AVAILABLE") {
                    com.ragcommerce.agent.ui.QuoteState.CURRENT
                } else {
                    com.ragcommerce.agent.ui.QuoteState.UNAVAILABLE
                },
                disclosure = "演示报价仅用于本地导购流程，不代表真实市场供应",
            )
        }
    }
}

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
            )
        }
    }
    return RemoteThreadSnapshot(
        goal = root.getString("goal"),
        status = root.getString("status"),
        lastEventId = root.getLong("last_event_id"),
        pendingAction = root.optString("pending_action").takeIf(String::isNotBlank),
        products = products,
    )
}

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
        val id = lines.firstOrNull { it.startsWith("id:") }
            ?.substringAfter(':')
            ?.trim()
            ?.toLongOrNull()
            ?: return@mapNotNull null
        val name = lines.firstOrNull { it.startsWith("event:") }
            ?.substringAfter(':')
            ?.trim()
            ?: return@mapNotNull null
        val dataText = lines.filter { it.startsWith("data:") }
            .joinToString("\n") { it.substringAfter(':').trimStart() }
        val dataObject = JSONObject(dataText)
        val data = dataObject.keys().asSequence().associateWith { key ->
            dataObject.opt(key)?.toString().orEmpty()
        }
        AgentPublicEvent(id, name, data)
    }

interface ShoppingRepository {
    fun observeLocal(): Flow<LocalShoppingSnapshot>

    suspend fun saveMission(goal: String)

    suspend fun saveSelectedTab(value: String)

    suspend fun setQualityDataConsent(granted: Boolean)

    suspend fun probeConnection(): Boolean

    suspend fun submitTurn(text: String, media: List<MediaAttachmentInput>): TurnAcceptedRemote

    suspend fun readEvents(runId: String, lastEventId: Long): List<AgentPublicEvent>

    suspend fun restoreThread(): RemoteThreadSnapshot?

    suspend fun decide(runId: String, tool: String, approved: Boolean)

    suspend fun resolveOffer(offerId: String, confirmedQuoteChange: Boolean): MerchantResolution

    suspend fun saveProduct(product: com.ragcommerce.agent.ui.EvidenceProductUi)

    suspend fun addOffer(offer: com.ragcommerce.agent.ui.OfferUi)

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
    private val pendingRunIdKey = stringPreferencesKey("pending_run_id")
    private val pendingApprovalToolKey = stringPreferencesKey("pending_approval_tool")
    private val lastEventIdKey = longPreferencesKey("last_event_id")
    private val pendingFingerprintKey = stringPreferencesKey("pending_turn_fingerprint")
    private val pendingIdempotencyKey = stringPreferencesKey("pending_turn_idempotency")
    private val pendingMediaIdsKey = stringPreferencesKey("pending_turn_media_ids")
    private val qualityDataConsentKey = booleanPreferencesKey("quality_data_consent")

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

    override suspend fun readEvents(runId: String, lastEventId: Long): List<AgentPublicEvent> {
        val userId = requireUserId()
        val url = BuildConfig.API_BASE_URL.toHttpUrl().newBuilder()
            .addPathSegments("v1/agent-runs/$runId/events")
            .build()
            .toString()
        val events = parseSsePayload(eventStream.read(url, userId, lastEventId))
        val cursor = events.maxOfOrNull(AgentPublicEvent::id) ?: lastEventId
        val terminal = events.lastOrNull()?.name in setOf("completed", "failed")
        val approvalTool = events.lastOrNull { it.name == "approval_required" }?.data?.get("tool")
        settings.edit { preferences ->
            preferences[lastEventIdKey] = cursor
            if (approvalTool != null) preferences[pendingApprovalToolKey] = approvalTool
            if (terminal) {
                preferences.remove(pendingRunIdKey)
                preferences.remove(pendingApprovalToolKey)
            }
        }
        return events
    }

    override suspend fun restoreThread(): RemoteThreadSnapshot? {
        val preferences = settings.data.first()
        val threadId = preferences[threadIdKey] ?: return null
        val userId = preferences[userIdKey] ?: return null
        val snapshot = api.thread(userId, threadId).use { parseThreadSnapshot(it.string()) }
        val offers = snapshot.products.flatMap { product ->
            api.offers(userId, product.id, false).use { response ->
                parseOfferCollection(product, response.string())
            }
        }
        return snapshot.copy(offers = offers)
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
            url = resolved.optString("link_url").takeIf(String::isNotBlank),
            expiresAt = resolved.optString("expires_at").takeIf(String::isNotBlank),
            quoteChanged = resolved.optBoolean("quote_changed", false),
            requiresConfirmation = resolved.optBoolean("requires_confirmation", false),
            disclosure = resolved.optString("disclosure"),
        )
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

    override suspend fun addOffer(offer: com.ragcommerce.agent.ui.OfferUi) {
        val request = JSONObject()
            .put("operation", "add")
            .put("offer_id", offer.id)
            .put("quantity", 1)
            .toString()
            .toRequestBody(JSON_MEDIA_TYPE)
        api.mutateCart(requireUserId(), request).use { }
        dao.saveItem(
            SavedItemEntity(
                itemKey = "CART:${offer.id}",
                kind = "CART",
                externalId = offer.id,
                title = offer.merchantName,
                sourceRef = offer.sourceRef,
                quantity = 1,
            ),
        )
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
            ?: throw IllegalArgumentException("media content type is unavailable")
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
