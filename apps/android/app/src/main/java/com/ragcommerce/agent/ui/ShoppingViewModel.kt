package com.ragcommerce.agent.ui

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.ragcommerce.agent.data.AgentPublicEvent
import com.ragcommerce.agent.data.MediaAttachmentInput
import com.ragcommerce.agent.data.ShoppingRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import javax.inject.Inject
import java.net.URI
import java.time.Instant

internal fun isSafeMerchantUrl(value: String): Boolean = runCatching {
    val uri = URI(value)
    uri.scheme.equals("https", ignoreCase = true) && !uri.host.isNullOrBlank()
}.getOrDefault(false)

internal fun isFreshMerchantResolution(
    url: String,
    expiresAt: String?,
    now: Instant = Instant.now(),
): Boolean = isSafeMerchantUrl(url) && runCatching {
    expiresAt != null && Instant.parse(expiresAt).isAfter(now)
}.getOrDefault(false)

@HiltViewModel
class ShoppingViewModel @Inject constructor(
    private val savedStateHandle: SavedStateHandle,
    private val repository: ShoppingRepository,
) : ViewModel() {
    private val mutableState = MutableStateFlow(
        ShoppingUiState(
            selectedTab = savedStateHandle.get<String>("selected_tab")
                ?.let(PrimaryTab::valueOf)
                ?: PrimaryTab.TASK,
        ),
    )
    val state: StateFlow<ShoppingUiState> = mutableState.asStateFlow()
    private val mutableMerchantLinks = MutableSharedFlow<String>(extraBufferCapacity = 1)
    val merchantLinks: SharedFlow<String> = mutableMerchantLinks.asSharedFlow()
    private val activeRuns = mutableSetOf<String>()
    private var currentRunId: String? = null
    private var currentCursor = 0L
    private var submittingTurn = false
    private var identityGeneration = 0L
    private var deletingData = false

    init {
        viewModelScope.launch {
            val online = repository.probeConnection()
            if (online) {
                restoreCompletedThread()
                if (mutableState.value.connection == ConnectionState.CHECKING) {
                    dispatch(ShoppingAction.SetConnection(ConnectionState.ONLINE))
                }
            } else {
                dispatch(ShoppingAction.SetConnection(ConnectionState.OFFLINE))
            }
        }
        viewModelScope.launch {
            repository.observeLocal().collect { snapshot ->
                val tab = PrimaryTab.valueOf(snapshot.selectedTab)
                mutableState.update { current ->
                    current.copy(
                        selectedTab = tab,
                        missionGoal = snapshot.mission?.goal ?: current.missionGoal,
                        savedProducts = snapshot.items
                            .filter { it.kind == "LIST" }
                            .map { SavedProductUi(it.externalId, it.title, it.sourceRef) },
                        qualityDataConsent = snapshot.qualityDataConsent,
                    )
                }
                snapshot.pendingApprovalTool?.let {
                    mutableState.update { state ->
                        ShoppingReducer.reduce(state, ShoppingAction.ApprovalRequired(it))
                    }
                }
                snapshot.pendingRunId?.let { runId ->
                    currentRunId = runId
                    currentCursor = snapshot.lastEventId
                    if (
                        !submittingTurn &&
                        !deletingData &&
                        snapshot.pendingApprovalTool == null &&
                        activeRuns.add(runId)
                    ) {
                        mutableState.update { it.copy(isLoading = true) }
                        viewModelScope.launch { consumeRun(runId, snapshot.lastEventId, processResume = true) }
                    }
                }
            }
        }
    }

    private suspend fun restoreCompletedThread() {
        val snapshot = repository.restoreThread() ?: return
        if (snapshot.products.isNotEmpty()) {
            mutableState.update { state ->
                ShoppingReducer.reduce(
                    state.copy(missionGoal = snapshot.goal),
                    ShoppingAction.TurnProducts(snapshot.products),
                )
            }
        }
        if (snapshot.offers.isNotEmpty()) {
            mutableState.update { state ->
                ShoppingReducer.reduce(state, ShoppingAction.TurnOffers(snapshot.offers))
            }
        }
        when (snapshot.status) {
            "COMPLETED" -> mutableState.update { state ->
                ShoppingReducer.reduce(
                    ShoppingReducer.reduce(state, ShoppingAction.TurnCompleted()),
                    ShoppingAction.SetConnection(ConnectionState.RECOVERED),
                )
            }
            "WAITING_APPROVAL" -> snapshot.pendingAction?.let { tool ->
                mutableState.update { state ->
                    ShoppingReducer.reduce(state, ShoppingAction.ApprovalRequired(tool))
                }
            }
        }
        currentCursor = maxOf(currentCursor, snapshot.lastEventId)
    }

    fun dispatch(action: ShoppingAction) {
        when (action) {
            ShoppingAction.SubmitMission -> submitCurrentTurn()
            ShoppingAction.RetryConnection -> retryConnection()
            is ShoppingAction.ResolveApproval -> resolveApproval(action.approved)
            else -> {
                mutableState.update { ShoppingReducer.reduce(it, action) }
                when (action) {
                    is ShoppingAction.SelectTab -> {
                        savedStateHandle["selected_tab"] = action.tab.name
                        viewModelScope.launch { repository.saveSelectedTab(action.tab.name) }
                    }
                    else -> Unit
                }
            }
        }
    }

    fun openMerchant(offer: OfferUi) {
        mutableState.update {
            ShoppingReducer.reduce(it, ShoppingAction.TurnStatus("正在重新验证商家报价"))
        }
        viewModelScope.launch {
            try {
                val resolved = repository.resolveOffer(offer.id, offer.confirmedChange)
                if (resolved.quoteChanged || resolved.requiresConfirmation) {
                    mutableState.update {
                        ShoppingReducer.reduce(it, ShoppingAction.QuoteRefreshRequired(offer.id))
                    }
                    return@launch
                }
                val url = resolved.url
                if (url == null || !isFreshMerchantResolution(url, resolved.expiresAt)) {
                    mutableState.update {
                        ShoppingReducer.reduce(it, ShoppingAction.TurnStatus("商家链接不可用、已过期或未通过安全校验"))
                    }
                    return@launch
                }
                mutableMerchantLinks.emit(url)
                mutableState.update {
                    ShoppingReducer.reduce(it, ShoppingAction.TurnStatus(resolved.disclosure))
                }
            } catch (_: Exception) {
                mutableState.update {
                    ShoppingReducer.reduce(it, ShoppingAction.TurnStatus("重新询价失败，已阻断商家跳转"))
                }
            }
        }
    }

    fun saveProduct(product: EvidenceProductUi) {
        viewModelScope.launch {
            runCatching { repository.saveProduct(product) }
                .onSuccess { mutableState.update { it.copy(statusMessage = "已保存到 Agent 候选清单") } }
                .onFailure { mutableState.update { it.copy(statusMessage = "保存失败，远端状态未改变") } }
        }
    }

    fun addOffer(offer: OfferUi) {
        viewModelScope.launch {
            runCatching { repository.addOffer(offer) }
                .onSuccess {
                    mutableState.update { state ->
                        val offers = state.cartGroups.flatMap { it.offers }
                        ShoppingReducer.reduce(state, ShoppingAction.TurnOffers((offers + offer).distinctBy { it.id }))
                            .copy(statusMessage = "已加入 API 驱动的待购集合")
                    }
                }
                .onFailure { mutableState.update { it.copy(statusMessage = "加入待购失败，远端状态未改变") } }
        }
    }

    fun deleteMyData() {
        identityGeneration += 1
        deletingData = true
        viewModelScope.launch {
            runCatching { repository.deleteMyData() }
                .onSuccess {
                    activeRuns.clear()
                    currentRunId = null
                    currentCursor = 0L
                    mutableState.value = ShoppingUiState(
                        selectedTab = PrimaryTab.PROFILE,
                        connection = ConnectionState.ONLINE,
                        statusMessage = "数据已删除；已创建新的本地开发身份",
                    )
                    deletingData = false
                }
                .onFailure {
                    deletingData = false
                    mutableState.update { it.copy(statusMessage = "删除失败；本地状态未清除") }
                }
        }
    }

    fun setQualityDataConsent(granted: Boolean) {
        viewModelScope.launch {
            runCatching { repository.setQualityDataConsent(granted) }
                .onSuccess {
                    mutableState.update {
                        it.copy(
                            qualityDataConsent = granted,
                            statusMessage = if (granted) "已同意使用匿名质量数据" else "已停止使用匿名质量数据",
                        )
                    }
                }
                .onFailure { mutableState.update { it.copy(statusMessage = "授权状态保存失败") } }
        }
    }

    fun reportMerchantLaunchFailure() {
        mutableState.update {
            ShoppingReducer.reduce(it, ShoppingAction.TurnStatus("设备上没有可安全处理该商家链接的应用"))
        }
    }

    private fun retryConnection() {
        mutableState.update { ShoppingReducer.reduce(it, ShoppingAction.RetryConnection) }
        viewModelScope.launch {
            if (!repository.probeConnection()) {
                mutableState.update {
                    ShoppingReducer.reduce(it, ShoppingAction.SetConnection(ConnectionState.OFFLINE))
                }
                return@launch
            }
            val runId = currentRunId
            if (runId != null && activeRuns.add(runId)) {
                consumeRun(runId, currentCursor, processResume = true)
            } else {
                restoreCompletedThread()
                mutableState.update {
                    ShoppingReducer.reduce(it, ShoppingAction.SetConnection(ConnectionState.ONLINE))
                }
            }
        }
    }

    private fun submitCurrentTurn() {
        val before = mutableState.value
        if (before.draft.isBlank() && before.attachments.isEmpty()) return
        val text = before.draft.trim()
        val media = before.attachments.map { MediaAttachmentInput(it.uri, it.kind) }
        mutableState.update { ShoppingReducer.reduce(it, ShoppingAction.SubmitMission) }
        viewModelScope.launch {
            submittingTurn = true
            if (text.isNotBlank()) repository.saveMission(text)
            try {
                val accepted = repository.submitTurn(text, media)
                currentRunId = accepted.runId
                currentCursor = 0L
                val ownsConsumption = activeRuns.add(accepted.runId)
                submittingTurn = false
                mutableState.update {
                    ShoppingReducer.reduce(it, ShoppingAction.SetConnection(ConnectionState.ONLINE))
                }
                if (ownsConsumption) consumeRun(accepted.runId, 0L, processResume = false)
            } catch (_: Exception) {
                submittingTurn = false
                mutableState.update {
                    ShoppingReducer.reduce(
                        ShoppingReducer.reduce(it, ShoppingAction.SetConnection(ConnectionState.OFFLINE)),
                        ShoppingAction.TurnFailed("提交失败；Mission 已保留，请检查连接后重试"),
                    )
                }
            }
        }
    }

    private fun resolveApproval(approved: Boolean) {
        val runId = currentRunId ?: return
        val tool = mutableState.value.pendingApprovalTool ?: return
        mutableState.update { ShoppingReducer.reduce(it, ShoppingAction.ResolveApproval(approved)) }
        viewModelScope.launch {
            try {
                repository.decide(runId, tool, approved)
                if (activeRuns.add(runId)) consumeRun(runId, currentCursor, processResume = false)
            } catch (_: Exception) {
                mutableState.update {
                    ShoppingReducer.reduce(it, ShoppingAction.TurnFailed("确认操作未送达，请重试"))
                }
            }
        }
    }

    private suspend fun consumeRun(runId: String, cursor: Long, processResume: Boolean) {
        val generation = identityGeneration
        var recovered = processResume
        if (processResume) {
            mutableState.update {
                ShoppingReducer.reduce(it, ShoppingAction.SetConnection(ConnectionState.RECONNECTING))
            }
        }
        try {
            val events = try {
                repository.readEvents(runId, cursor)
            } catch (first: Exception) {
                if (generation != identityGeneration) return
                recovered = true
                mutableState.update {
                    ShoppingReducer.reduce(it, ShoppingAction.SetConnection(ConnectionState.RECONNECTING))
                }
                delay(500)
                repository.readEvents(runId, currentCursor)
            }
            if (generation != identityGeneration) return
            mutableState.update {
                ShoppingReducer.reduce(
                    it,
                    ShoppingAction.SetConnection(
                        if (recovered) ConnectionState.RECOVERED else ConnectionState.ONLINE,
                    ),
                )
            }
            events.forEach(::applyEvent)
        } catch (_: Exception) {
            if (generation != identityGeneration) return
            mutableState.update {
                ShoppingReducer.reduce(
                    ShoppingReducer.reduce(it, ShoppingAction.SetConnection(ConnectionState.OFFLINE)),
                    ShoppingAction.TurnFailed("事件流中断；游标已保留，可在恢复连接后继续"),
                )
            }
        } finally {
            activeRuns.remove(runId)
        }
    }

    private fun applyEvent(event: AgentPublicEvent) {
        currentCursor = maxOf(currentCursor, event.id)
        val action = when (event.name) {
            "status", "progress" -> ShoppingAction.TurnStatus(statusText(event.data["stage"]))
            "mission_updated" -> ShoppingAction.MissionUpdated(event.data["goal"].orEmpty())
            "message_delta" -> ShoppingAction.TurnMessage(event.data["text"].orEmpty())
            "evidence" -> ShoppingAction.TurnEvidence(event.data["ref"].orEmpty())
            "products" -> ShoppingAction.TurnProducts(parseProducts(event.data["products"]))
            "offers" -> ShoppingAction.TurnOffers(parseOffers(event.data["offers"]))
            "comparison" -> ShoppingAction.TurnComparison(parseComparison(event.data["comparison"]))
            "approval_required" -> ShoppingAction.ApprovalRequired(event.data["tool"].orEmpty())
            "clarification_required" -> ShoppingAction.ClarificationRequired(
                event.data["question"].orEmpty(),
            )
            "completed" -> ShoppingAction.TurnCompleted()
            "failed" -> ShoppingAction.TurnFailed(
                "Agent 未完成：${event.data["summary"].orEmpty().ifBlank { "未知错误" }}",
            )
            else -> throw IllegalArgumentException("unknown Agent event: ${event.name}")
        }
        if (action is ShoppingAction.TurnMessage && action.text.isBlank()) return
        if (action is ShoppingAction.TurnEvidence && action.ref.isBlank()) return
        mutableState.update { ShoppingReducer.reduce(it, action) }
    }

    private fun statusText(stage: String?): String = when (stage) {
        "run_started" -> "Agent 已开始"
        "tool_started" -> "正在调用受控工具"
        "tool_completed" -> "工具完成，正在核验证据"
        "tool_failed" -> "工具失败，Agent 正在受限重规划"
        else -> "Agent 正在处理"
    }

    private fun parseProducts(value: String?): List<EvidenceProductUi> = jsonArray(value).map { item ->
        EvidenceProductUi(
            id = item.getString("product_id"),
            variantId = item.getString("variant_id"),
            title = item.getString("title"),
            fitSummary = item.optString("fit_summary"),
            matchedConstraints = item.stringList("matched_constraints"),
            unmetConstraints = item.stringList("unmet_constraints"),
            risks = item.stringList("risks"),
            evidenceRefs = item.stringList("evidence_refs"),
        )
    }

    private fun parseOffers(value: String?): List<OfferUi> = jsonArray(value).map { item ->
        OfferUi(
            id = item.getString("offer_id"),
            productId = item.optString("product_id"),
            variantId = item.optString("variant_id"),
            merchantName = item.getString("merchant_name"),
            priceText = item.optLongOrNull("price_minor")?.let { "¥%.2f".format(it / 100.0) },
            shippingText = item.optLongOrNull("shipping_minor")?.let { "¥%.2f".format(it / 100.0) },
            verification = item.getString("verification"),
            collectedAt = item.getString("collected_at"),
            expiresAt = item.getString("expires_at"),
            sourceRef = item.getString("source_ref"),
            quoteState = if (item.optString("availability") in setOf("AVAILABLE", "IN_STOCK")) {
                QuoteState.CURRENT
            } else {
                QuoteState.UNAVAILABLE
            },
            disclosure = "演示报价仅用于本地导购流程，不代表真实市场供应",
        )
    }

    private fun parseComparison(value: String?): ComparisonUi {
        val item = JSONObject(requireNotNull(value) { "comparison payload is missing" })
        return ComparisonUi(
            items = item.stringList("items"),
            dimensions = item.stringList("dimensions"),
            missingFields = item.stringList("missing_fields"),
            evidenceRefs = item.stringList("evidence_refs"),
        )
    }

    private fun jsonArray(value: String?): List<JSONObject> {
        val array = JSONArray(requireNotNull(value) { "event array payload is missing" })
        return (0 until array.length()).mapNotNull { array.optJSONObject(it) }
    }

    private fun JSONObject.stringList(key: String): List<String> {
        val array = optJSONArray(key) ?: return emptyList()
        return (0 until array.length()).mapNotNull { array.optString(it).takeIf(String::isNotBlank) }
    }

    private fun JSONObject.optLongOrNull(key: String): Long? =
        if (has(key) && !isNull(key)) optLong(key) else null

}
