package com.ragcommerce.agent.ui

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.ragcommerce.agent.data.AgentPublicEvent
import com.ragcommerce.agent.data.MediaAttachmentInput
import com.ragcommerce.agent.data.ShoppingRepository
import com.ragcommerce.agent.data.parseBusinessFacts
import com.ragcommerce.agent.data.parseRecommendationRoutes
import com.ragcommerce.agent.data.parseShoppingMission
import com.ragcommerce.agent.data.parseExploration
import com.ragcommerce.agent.data.parseMediaEvent
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
import java.io.IOException
import retrofit2.HttpException
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
            selectedTab = PrimaryTab.TASK,
        ),
    )
    val state: StateFlow<ShoppingUiState> = mutableState.asStateFlow()
    private val mutableMerchantLinks = MutableSharedFlow<String>(extraBufferCapacity = 1)
    val merchantLinks: SharedFlow<String> = mutableMerchantLinks.asSharedFlow()
    private val activeRuns = mutableSetOf<String>()
    private val completedWriteKeys = mutableSetOf<String>()
    private var currentRunId: String? = null
    private var currentCursor = 0L
    private var submittingTurn = false
    private var resolvingApproval = false
    private var identityGeneration = 0L
    private var deletingData = false
    private var restoringThread = false

    init {
        viewModelScope.launch {
            val online = repository.probeConnection()
            if (online) {
                restoreCompletedThread()
                try {
                    repository.refreshSavedCandidates()
                    restoreSavedComparison()
                } catch (_: IOException) {
                    mutableState.update { it.copy(statusMessage = "保存列表暂未同步，请检查连接", decisionError = "保存列表或比较暂未同步，请检查连接后重新打开应用") }
                } catch (_: HttpException) {
                    mutableState.update { it.copy(statusMessage = "保存列表读取失败，未清除本地记录", decisionError = "保存列表或比较读取失败，未清除本地记录") }
                } catch (error: SavedComparisonSelectionException) {
                    mutableState.update { it.copy(decisionError = error.message) }
                }
                if (mutableState.value.connection == ConnectionState.CHECKING) {
                    dispatch(ShoppingAction.SetConnection(ConnectionState.ONLINE))
                }
            } else {
                dispatch(ShoppingAction.SetConnection(ConnectionState.OFFLINE))
            }
            var localNavigationRestored = false
            repository.observeLocal().collect { snapshot ->
                val tab = PrimaryTab.valueOf(snapshot.selectedTab)
                mutableState.update { current ->
                    current.copy(
                        selectedTab = if (localNavigationRestored) current.selectedTab
                            else ShoppingReducer.reduce(current, ShoppingAction.SelectTab(tab)).selectedTab,
                        missionGoal = snapshot.mission?.goal ?: current.missionGoal,
                        savedProducts = snapshot.items
                            .filter { it.kind == "LIST" }
                            .map { SavedProductUi(it.externalId, it.title, it.sourceRef) },
                        qualityDataConsent = snapshot.qualityDataConsent,
                    )
                }
                localNavigationRestored = true
                // An explicitly submitted stream owns run/cursor/approval state.
                // Local snapshots only claim recovery when no stream owns it.
                if (restoringThread || resolvingApproval || submittingTurn || activeRuns.isNotEmpty() ||
                    mutableState.value.connection == ConnectionState.OFFLINE) return@collect
                mutableState.update { it.copy(pendingApprovalTool = snapshot.pendingApprovalTool) }
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
                        !resolvingApproval &&
                        !deletingData &&
                        mutableState.value.connection != ConnectionState.OFFLINE &&
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

    private suspend fun restoreCompletedThread(): Boolean {
        restoringThread = true
        return try {
            restoreThreadState()
            true
        } catch (_: IOException) {
            mutableState.update {
                ShoppingReducer.reduce(
                    ShoppingReducer.reduce(it, ShoppingAction.TurnFailed("恢复连接失败，请重连后继续")),
                    ShoppingAction.SetConnection(ConnectionState.OFFLINE),
                )
            }
            false
        } catch (error: HttpException) {
            mutableState.update {
                ShoppingReducer.reduce(
                    ShoppingReducer.reduce(it, ShoppingAction.TurnFailed("恢复请求失败（${error.code()}），请重连")),
                    ShoppingAction.SetConnection(ConnectionState.OFFLINE),
                )
            }
            false
        } finally {
            restoringThread = false
        }
    }

    private suspend fun restoreThreadState() {
        val quantities = repository.waitingCart()
        mutableState.update { ShoppingReducer.reduce(it, ShoppingAction.WaitingCartUpdated(quantities)) }
        val snapshot = repository.restoreThread() ?: return
        currentRunId = snapshot.resumableRunId
        currentCursor = if (currentRunId == null) 0L else snapshot.lastEventId
        mutableState.update {
            it.copy(pendingApprovalTool = null, isLoading = snapshot.status == "RUNNING",
                feedback = snapshot.experience.feedback,
                pendingApprovalArguments = snapshot.pendingActionArguments,
                pendingMediaInterpretations = snapshot.pendingMediaInterpretations,
                mediaSourceRunId = if (snapshot.pendingMediaInterpretations.isEmpty()) null else snapshot.activeRunId,
                draft = if (snapshot.pendingMediaInterpretations.isEmpty()) it.draft
                    else (listOf(snapshot.goal) + snapshot.pendingMediaInterpretations.map { media -> media.recognized_text })
                        .filter(String::isNotBlank).joinToString("；").take(500),
                mode = snapshot.mode, exploration = snapshot.exploration,
                explorationNeedsRefresh = false,
                products = emptyList(), recommendationRoutes = emptyList(), comparison = null,
                showConversation = snapshot.mode == "DISCOVERY" || snapshot.pendingMediaInterpretations.isNotEmpty(),
                clarificationQuestion = if (snapshot.status == "WAITING_CLARIFICATION" &&
                    snapshot.exploration?.selected_direction_id != null) "你的预算上限是多少？" else null)
        }
        if (snapshot.products.isNotEmpty()) {
            mutableState.update { state ->
                ShoppingReducer.reduce(
                    state.copy(
                        missionGoal = snapshot.goal,
                        mission = snapshot.mission,
                        comparedProductIds = snapshot.selectedProductIds,
                        watchers = snapshot.watchers,
                    ),
                    ShoppingAction.TurnProducts(snapshot.products, snapshot.recommendationRoutes),
                )
            }
        } else {
            mutableState.update {
                it.copy(
                    missionGoal = snapshot.goal,
                    mission = snapshot.mission,
                    comparedProductIds = snapshot.selectedProductIds,
                    watchers = snapshot.watchers,
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
                    ShoppingReducer.reduce(state, ShoppingAction.ApprovalRequired(tool, snapshot.pendingActionArguments))
                }
            }
            "FAILED" -> mutableState.update { state ->
                ShoppingReducer.reduce(
                    state.copy(connection = ConnectionState.ONLINE, showConversation = true),
                    ShoppingAction.TurnFailed("本次导购未完成，请调整需求或新建任务"),
                )
            }
        }
    }

    fun dispatch(action: ShoppingAction) {
        when (action) {
            ShoppingAction.LoadHistory -> decisionRequest { val history = repository.history(); mutableState.update { it.copy(history = history, historyVisible = true) } }
            is ShoppingAction.OrganizeHistory -> decisionRequest {
                repository.organizeThread(action.threadId, action.title, action.archived)
                val history = repository.history()
                mutableState.update { it.copy(history = history) }
            }
            is ShoppingAction.OpenHistory -> decisionRequest {
                currentRunId = null
                repository.activateThread(action.threadId)
                mutableState.update { ShoppingReducer.reduce(it, ShoppingAction.StartNewMission).copy(connection = ConnectionState.ONLINE) }
                restoreCompletedThread()
            }
            ShoppingAction.LoadConversation -> loadConversation(false)
            ShoppingAction.MoreConversation -> loadConversation(true)
            is ShoppingAction.ExcludeCandidate -> decisionRequest {
                val snapshot = repository.candidateFeedback(action, mutableState.value.mission?.version ?: error("Task version missing"))
                mutableState.update { it.copy(feedback = snapshot.experience.feedback, mission = snapshot.mission,
                    products = emptyList(), comparedProductIds = emptySet(), comparison = null, showConversation = true,
                    pendingMissionRecalculation = true, pendingApprovalTool = null, pendingApprovalArguments = emptyMap(),
                    statusMessage = if (action.undo) "已撤销排除；确认重新推荐后生效" else "已记下排除范围；确认重新推荐后生效") }
            }
            is ShoppingAction.UndoCandidateFeedback -> decisionRequest {
                val snapshot = repository.undoCandidateFeedback(action.key, mutableState.value.mission?.version ?: error("Task version missing"))
                mutableState.update { it.copy(feedback = snapshot.experience.feedback, mission = snapshot.mission,
                    products = emptyList(), comparedProductIds = emptySet(), comparison = null, pendingMissionRecalculation = true,
                    statusMessage = "已撤销排除；确认重新推荐后生效") }
            }
            is ShoppingAction.OpenSaved -> decisionRequest {
                val product = repository.productFacts(action.productId)
                val offers = repository.productOffers(product)
                mutableState.update { it.copy(savedDetail = product, savedDetailOffers = offers) }
            }
            is ShoppingAction.RemoveSaved -> decisionRequest {
                repository.removeSavedCandidate(action.productId)
                mutableState.update { it.copy(savedDetail = null, savedDetailOffers = emptyList(),
                    savedComparisonIds = it.savedComparisonIds - action.productId,
                    savedComparison = if (action.productId in it.savedComparisonIds) null else it.savedComparison,
                    statusMessage = "候选已从保存列表移除") }
            }
            is ShoppingAction.ToggleSavedComparison -> decisionRequest {
                repository.clearSavedComparison()
                mutableState.update { ShoppingReducer.reduce(it, action) }
            }
            ShoppingAction.CompareSavedSelection -> decisionRequest {
                val comparison = repository.compareSavedProducts(mutableState.value.savedComparisonIds)
                mutableState.update { it.copy(savedComparison = comparison) }
            }
            ShoppingAction.ClearSavedComparison -> decisionRequest {
                repository.clearSavedComparison()
                mutableState.update { ShoppingReducer.reduce(it, action) }
            }
            is ShoppingAction.ContinueSaved -> decisionRequest {
                currentRunId = null
                repository.startNewMission()
                mutableState.update { ShoppingReducer.reduce(it, ShoppingAction.StartNewMission).copy(connection = ConnectionState.ONLINE,
                    draft = "想进一步比较和选购【${action.product.title}】，用途是：", statusMessage = "已开启独立任务，请补充用途并发送，不继承原任务约束") }
            }
            ShoppingAction.ConfirmMedia -> confirmMedia()
            is ShoppingAction.Explore -> explore(action)
            ShoppingAction.SubmitMission -> submitCurrentTurn()
            ShoppingAction.RecalculateMission -> recalculateMission()
            ShoppingAction.StartNewMission -> startNewMission()
            is ShoppingAction.ToggleCompare -> toggleComparison(action)
            is ShoppingAction.SetWaitingQuantity -> updateWaitingOffer(action.offer, action.quantity)
              is ShoppingAction.RequoteOffer -> requoteOffer(action.offer)
            is ShoppingAction.PrepareMerchant -> prepareMerchant(action.offer)
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

    private fun decisionRequest(block: suspend () -> Unit) {
        if (deletingData || mutableState.value.decisionBusy || submittingTurn) return
        viewModelScope.launch {
            mutableState.update { it.copy(decisionBusy = true, decisionError = null) }
            try { block() }
            catch (_: IOException) { mutableState.update { it.copy(statusMessage = "连接中断，操作结果尚未确认，请重新读取任务", decisionError = "连接中断，未显示为完成；请检查网络后再操作") } }
            catch (error: HttpException) { mutableState.update { it.copy(statusMessage = if (error.code() == 409) "任务状态已变化，请重新打开后继续" else "请求未成功（${error.code()}），未显示为完成", decisionError = "请求未成功，请重新打开后核对，不会改写为成功") } }
            catch (error: SavedComparisonSelectionException) { mutableState.update { it.copy(decisionError = error.message) } }
            catch (error: org.json.JSONException) { failEventContract(error) }
            finally { mutableState.update { it.copy(decisionBusy = false) } }
        }
    }

    private suspend fun restoreSavedComparison() {
        val comparison = repository.restoreSavedComparison() ?: return
        mutableState.update { it.copy(savedComparison = comparison, savedComparisonIds = comparison.products.map { product -> product.id }.toSet()) }
    }

    private fun loadConversation(more: Boolean) = decisionRequest {
        val before = if (more) mutableState.value.conversationMessages else emptyList()
        val page = repository.messages(before.size)
        mutableState.update { it.copy(conversationMessages = before + page, conversationVisible = true, conversationHasMore = page.size == 50) }
    }

    private fun explore(action: ShoppingAction.Explore) {
        if (submittingTurn || mutableState.value.isLoading || mutableState.value.explorationNeedsRefresh) return
        submittingTurn = true
        val version = mutableState.value.mission?.version ?: 1
        mutableState.update { it.copy(isLoading = true, statusMessage = "正在更新探索方向") }
        viewModelScope.launch {
            try {
                val accepted = repository.explore(action, version)
                currentRunId = accepted.runId
                currentCursor = 0L
                mutableState.update { it.copy(agentMessages = emptyList(), evidenceRefs = emptyList(), pendingApprovalTool = null) }
                val ownsConsumption = activeRuns.add(accepted.runId)
                submittingTurn = false
                if (ownsConsumption) consumeRun(accepted.runId, 0L, processResume = false)
            } catch (_: IOException) {
                mutableState.update { it.copy(isLoading = false, connection = ConnectionState.OFFLINE,
                    statusMessage = "探索请求未确认，请重连查看状态") }
            } catch (error: HttpException) {
                mutableState.update { it.copy(isLoading = false, explorationNeedsRefresh = error.code() == 409,
                    statusMessage = if (error.code() == 409) "任务已变化，请刷新后继续" else "探索请求失败（${error.code()}）") }
            } finally {
                submittingTurn = false
            }
        }
    }

    private fun prepareMerchant(offer: OfferUi) {
        val generation = identityGeneration
        mutableState.update { it.copy(preparedMerchantOfferId = null, preparedMerchantHost = null) }
        viewModelScope.launch {
            try {
                val resolved = repository.resolveOffer(offer.id, offer.confirmedChange)
                if (generation != identityGeneration) return@launch
                val url = resolved.url
                if (!resolved.quoteChanged && !resolved.requiresConfirmation && url != null && isFreshMerchantResolution(url, resolved.expiresAt)) {
                    mutableState.update { it.copy(preparedMerchantOfferId = offer.id, preparedMerchantHost = URI(url).host) }
                } else mutableState.update { it.copy(statusMessage = "来源不可用或报价已变化，请重新询价") }
            } catch (_: IOException) {
                mutableState.update { it.copy(statusMessage = "连接中断，尚未核验外部来源") }
            } catch (_: HttpException) {
                mutableState.update { it.copy(statusMessage = "外部来源核验未通过") }
            }
        }
    }

    fun openMerchant(offer: OfferUi) {
        val confirmedHost = mutableState.value.preparedMerchantHost
        if (mutableState.value.preparedMerchantOfferId != offer.id || confirmedHost == null) return
        if (!offer.mayResolve || !Instant.parse(offer.expiresAt).isAfter(Instant.now())) {
            mutableState.update { ShoppingReducer.reduce(it, ShoppingAction.TurnStatus("报价已过期或不可用，请先重新询价")) }
            return
        }
        val generation = identityGeneration
        mutableState.update {
            ShoppingReducer.reduce(it, ShoppingAction.TurnStatus("正在重新验证商家报价"))
        }
        viewModelScope.launch {
            try {
                val resolved = repository.resolveOffer(offer.id, offer.confirmedChange)
                if (generation != identityGeneration) return@launch
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
                if (URI(url).host != confirmedHost) {
                    mutableState.update { it.copy(preparedMerchantOfferId = null, preparedMerchantHost = null, statusMessage = "目标网站已变化，请重新查看并确认") }
                    return@launch
                }
                mutableMerchantLinks.emit(url)
                mutableState.update {
                    ShoppingReducer.reduce(it, ShoppingAction.TurnStatus(resolved.disclosure))
                }
            } catch (_: IOException) {
                if (generation != identityGeneration) return@launch
                mutableState.update {
                    ShoppingReducer.reduce(it, ShoppingAction.TurnStatus("重新询价失败，已阻断商家跳转"))
                }
            } catch (error: HttpException) {
                if (generation != identityGeneration) return@launch
                mutableState.update { ShoppingReducer.reduce(it, ShoppingAction.TurnStatus("来源验证未通过，请重新询价")) }
            }
        }
    }

    private fun requoteOffer(offer: OfferUi) {
        val generation = identityGeneration
        mutableState.update { it.copy(statusMessage = "正在重新询价") }
        viewModelScope.launch {
            try {
                val offers = repository.requoteOffer(offer)
                if (generation != identityGeneration) return@launch
                mutableState.update { ShoppingReducer.reduce(it, ShoppingAction.OfferRequoted(offer.productId, offers)) }
            } catch (_: IOException) {
                if (generation != identityGeneration) return@launch
                mutableState.update { it.copy(statusMessage = "重新询价未完成，请恢复连接后再试") }
            } catch (error: HttpException) {
                if (generation != identityGeneration) return@launch
                mutableState.update { it.copy(statusMessage = "报价请求未通过，请稍后重新询价") }
            }
        }
    }

    fun saveProduct(product: EvidenceProductUi) {
        val writeKey = "candidate:${product.id}"
        if (!completedWriteKeys.add(writeKey)) return
        viewModelScope.launch {
            runCatching { repository.saveProduct(product) }
                .onSuccess { mutableState.update { it.copy(statusMessage = "已保存候选方案") } }
                .onFailure {
                    completedWriteKeys.remove(writeKey)
                    mutableState.update { it.copy(statusMessage = "保存失败，远端状态未改变") }
                }
        }
    }

    private fun startNewMission() {
        viewModelScope.launch {
            repository.startNewMission()
            activeRuns.clear()
            currentRunId = null
            currentCursor = 0L
            mutableState.update { current ->
                ShoppingReducer.reduce(current, ShoppingAction.StartNewMission).copy(selectedTab = current.selectedTab)
            }
        }
    }

    fun addOffer(offer: OfferUi) {
        updateWaitingOffer(offer, 1)
    }

    private fun updateWaitingOffer(offer: OfferUi, quantity: Int) {
        if (mutableState.value.waitingCartBusy || deletingData) return
        val generation = identityGeneration
        mutableState.update { it.copy(waitingCartBusy = true, statusMessage = "正在保存待购计划") }
        viewModelScope.launch {
            try {
                val quantities = repository.updateOfferQuantity(offer, quantity)
                if (generation != identityGeneration) return@launch
                mutableState.update { state ->
                    ShoppingReducer.reduce(state, ShoppingAction.WaitingCartUpdated(quantities))
                        .copy(statusMessage = if (quantity == 0) "已移出待购计划" else "待购计划已保存")
                }
            } catch (_: IOException) {
                if (generation == identityGeneration) mutableState.update {
                    it.copy(statusMessage = "未能确认待购结果，请重连核对", connection = ConnectionState.OFFLINE)
                }
            } catch (error: HttpException) {
                if (generation == identityGeneration) mutableState.update {
                    it.copy(statusMessage = "待购请求未完成（${error.code()}），请核对后再操作")
                }
            } finally {
                if (generation == identityGeneration) mutableState.update { it.copy(waitingCartBusy = false) }
            }
        }
    }

    fun createWatcher(offer: OfferUi, kind: String) {
        val threshold = if (kind == "PRICE_BELOW") offer.priceMinor?.times(9)?.div(10) else null
        viewModelScope.launch {
            runCatching { repository.createWatcher(offer, kind, threshold) }
                .onSuccess { watcher ->
                    mutableState.update { state ->
                        ShoppingReducer.reduce(state, ShoppingAction.WatcherCreated(watcher)).copy(
                            statusMessage = "已保存演示观察草稿；不会后台提醒",
                        )
                    }
                }
                .onFailure {
                    mutableState.update { it.copy(statusMessage = "观察草稿保存失败") }
                }
        }
    }

    fun deleteMyData() {
        identityGeneration += 1
        deletingData = true
        viewModelScope.launch {
            runCatching { repository.deleteMyData() }
                .onSuccess {
                    activeRuns.clear()
                    completedWriteKeys.clear()
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
            if (!restoreCompletedThread()) return@launch
            val runId = currentRunId
            if (runId != null && activeRuns.add(runId)) {
                consumeRun(runId, currentCursor, processResume = true)
            } else {
                mutableState.update {
                    ShoppingReducer.reduce(it, ShoppingAction.SetConnection(ConnectionState.ONLINE))
                }
            }
        }
    }

    private fun confirmMedia() {
        val before = mutableState.value
        val source = before.mediaSourceRunId ?: return
        if (before.isLoading || before.draft.isBlank()) return
        mutableState.update { ShoppingReducer.reduce(it, ShoppingAction.ConfirmMedia) }
        viewModelScope.launch {
            submittingTurn = true
            try {
                val accepted = repository.confirmMedia(source, before.draft.trim().take(500), before.mission?.version ?: 1)
                currentRunId = accepted.runId
                currentCursor = 0L
                mutableState.update { it.copy(pendingMediaInterpretations = emptyList(), mediaSourceRunId = null) }
                submittingTurn = false
                val ownsConsumption = activeRuns.add(accepted.runId)
                if (ownsConsumption) consumeRun(accepted.runId, 0L, processResume = false)
            } catch (failure: HttpException) {
                submittingTurn = false
                if (failure.code() == 409) restoreThreadState()
                mutableState.update { ShoppingReducer.reduce(it, ShoppingAction.TurnFailed("确认未完成，请核对当前任务后再操作")) }
            } catch (failure: IOException) {
                submittingTurn = false
                mutableState.update { ShoppingReducer.reduce(it, ShoppingAction.TurnFailed("连接中断，识别内容已保留")) }
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
            if (text.isNotBlank()) repository.saveMission(before.missionGoal.ifBlank { text })
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
            } catch (_: IOException) {
                mutableState.update {
                    ShoppingReducer.reduce(
                        ShoppingReducer.reduce(it, ShoppingAction.SetConnection(ConnectionState.OFFLINE)),
                        ShoppingAction.TurnFailed("提交失败；Mission 已保留，请检查连接后重试"),
                    )
                }
            } catch (_: HttpException) {
                mutableState.update {
                    ShoppingReducer.reduce(it, ShoppingAction.TurnFailed("请求未成功，请检查任务和授权后重试"))
                }
            } finally {
                submittingTurn = false
            }
        }
    }

    private fun recalculateMission() {
        val before = mutableState.value
        if (!before.pendingMissionRecalculation || before.missionGoal.isBlank()) return
        mutableState.update {
            it.copy(isLoading = true, statusMessage = "正在保存约束版本")
        }
        viewModelScope.launch {
            runCatching { repository.updateMissionConstraints(before.missionGoal) }
                .onSuccess { mission ->
                    mutableState.update {
                        ShoppingReducer.reduce(
                            it.copy(
                                draft = mission.goal,
                                products = emptyList(),
                                comparison = null,
                                comparedProductIds = emptySet(),
                                isLoading = false,
                            ),
                            ShoppingAction.MissionUpdated(mission),
                        )
                    }
                    submitCurrentTurn()
                }
                .onFailure {
                    mutableState.update {
                        it.copy(
                            isLoading = false,
                            statusMessage = "约束保存失败，原推荐未被覆盖",
                        )
                    }
                }
        }
    }

    private fun toggleComparison(action: ShoppingAction.ToggleCompare) {
        val before = mutableState.value
        val optimistic = ShoppingReducer.reduce(before, action)
        mutableState.value = optimistic
        viewModelScope.launch {
            runCatching {
                repository.updateComparisonSelection(optimistic.comparedProductIds)
            }.onSuccess { persisted ->
                mutableState.update {
                    it.copy(
                        comparedProductIds = persisted,
                        statusMessage = if (persisted.size >= 2) {
                            "已保存 ${persisted.size} 项比较候选"
                        } else {
                            "比较选择已保存"
                        },
                    )
                }
            }.onFailure {
                mutableState.update {
                    it.copy(
                        comparedProductIds = before.comparedProductIds,
                        statusMessage = "比较选择保存失败，已恢复原状态",
                    )
                }
            }
        }
    }

    private fun resolveApproval(approved: Boolean) {
        if (resolvingApproval) return
        val runId = currentRunId ?: return
        val tool = mutableState.value.pendingApprovalTool ?: return
        val generation = identityGeneration
        resolvingApproval = true
        mutableState.update { ShoppingReducer.reduce(it, ShoppingAction.ResolveApproval(approved)) }
        viewModelScope.launch {
            try {
                repository.decide(runId, tool, approved)
                if (generation != identityGeneration) return@launch
                if (activeRuns.add(runId)) consumeRun(runId, currentCursor, processResume = false)
                if (approved && tool == "cart.update") {
                    if (generation != identityGeneration || mutableState.value.connection == ConnectionState.OFFLINE) return@launch
                    val quantities = repository.waitingCart()
                    if (generation != identityGeneration) return@launch
                    mutableState.update { ShoppingReducer.reduce(it, ShoppingAction.WaitingCartUpdated(quantities)) }
                }
            } catch (failure: IOException) {
                android.util.Log.w("ApprovalBoundary", "network_failure=${failure.javaClass.simpleName}")
                if (generation == identityGeneration) mutableState.update {
                    ShoppingReducer.reduce(
                        ShoppingReducer.reduce(it.copy(showConversation = true), ShoppingAction.SetConnection(ConnectionState.OFFLINE)),
                        ShoppingAction.TurnFailed("确认结果未核实，请恢复连接后核对待购"),
                    )
                }
            } catch (_: HttpException) {
                if (generation == identityGeneration) mutableState.update {
                    ShoppingReducer.reduce(
                        ShoppingReducer.reduce(it.copy(showConversation = true), ShoppingAction.SetConnection(ConnectionState.OFFLINE)),
                        ShoppingAction.TurnFailed("确认请求未被接受，请恢复连接后核对任务状态"),
                    )
                }
            } finally {
                resolvingApproval = false
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
            repository.observeEvents(runId, cursor).collect { event ->
                if (generation == identityGeneration && currentRunId == runId) {
                    mutableState.update {
                        ShoppingReducer.reduce(it, ShoppingAction.SetConnection(
                            if (recovered) ConnectionState.RECOVERED else ConnectionState.ONLINE))
                    }
                    applyEvent(event)
                }
            }
        } catch (_: IOException) {
            if (generation != identityGeneration || currentRunId != runId) return
            mutableState.update {
                ShoppingReducer.reduce(
                    ShoppingReducer.reduce(it, ShoppingAction.SetConnection(ConnectionState.OFFLINE)),
                    ShoppingAction.TurnFailed("事件流中断；游标已保留，可在恢复连接后继续"),
                )
            }
        } catch (error: IllegalStateException) {
            if (generation == identityGeneration && currentRunId == runId) failEventContract(error)
        } catch (error: IllegalArgumentException) {
            if (generation == identityGeneration && currentRunId == runId) failEventContract(error)
        } catch (error: org.json.JSONException) {
            if (generation == identityGeneration && currentRunId == runId) failEventContract(error)
        } finally {
            activeRuns.remove(runId)
        }
    }

    private fun failEventContract(error: Exception) {
        android.util.Log.e("AgentEvents", "Event contract failure: ${error.javaClass.simpleName}")
        mutableState.update { ShoppingReducer.reduce(it, ShoppingAction.TurnFailed("服务数据格式错误，任务未完成")) }
    }

    private fun applyEvent(event: AgentPublicEvent) {
        currentCursor = maxOf(currentCursor, event.id)
        val action = when (event.name) {
            "media_interpreted" -> ShoppingAction.MediaInterpreted(
                parseMediaEvent(event.data), requireNotNull(currentRunId),
            )
            "exploration_updated" -> ShoppingAction.ExplorationUpdated(
                event.data.getValue("mode"), parseExploration(JSONObject(event.data.getValue("exploration"))),
            )
            "status", "progress" -> ShoppingAction.TurnStatus(statusText(event.data["stage"]))
            "mission_updated" -> ShoppingAction.MissionUpdated(
                parseShoppingMission(JSONObject(event.data.getValue("mission"))),
            )
            "message_delta" -> ShoppingAction.TurnMessage(event.data["text"].orEmpty())
            "evidence" -> ShoppingAction.TurnEvidence(event.data["ref"].orEmpty())
            "products" -> ShoppingAction.TurnProducts(
                parseProducts(event.data["products"]),
                parseRecommendationRoutes(
                    event.data["recommendation_routes"]?.let(::JSONArray),
                ),
            )
            "offers" -> ShoppingAction.TurnOffers(parseOffers(event.data["offers"]))
            "comparison" -> ShoppingAction.TurnComparison(parseComparison(event.data["comparison"]))
            "approval_required" -> ShoppingAction.ApprovalRequired(event.data.getValue("tool"),
                JSONObject(event.data.getValue("arguments")).let { obj -> obj.keys().asSequence().associateWith { obj.get(it).toString() } })
            "clarification_required" -> ShoppingAction.ClarificationRequired(
                event.data["question"].orEmpty(),
            )
            "completed" -> ShoppingAction.TurnCompleted()
            "failed" -> ShoppingAction.TurnFailed(
                "Agent 未完成：" + when (event.data["summary"]) {
                    "ProviderTimeout" -> "分析服务超时，请稍后重新发起任务"
                    "ProviderRateLimited" -> "分析服务当前繁忙，请稍后重新发起任务"
                    "ProviderInvalidResponse" -> "分析结果格式错误，未执行后续操作"
                    "ProviderBudgetExceeded" -> "本次分析用量已达上限，任务已停止"
                    "ProviderUnsupportedAmount" -> "结果中存在无法核实的金额，已阻止展示"
                    else -> "本次任务未能完成，请查看任务详情或联系演示维护者"
                },
            )
            else -> throw IllegalArgumentException("unknown Agent event: ${event.name}")
        }
        if (action is ShoppingAction.TurnMessage && action.text.isBlank()) return
        if (action is ShoppingAction.TurnEvidence && action.ref.isBlank()) return
        mutableState.update { ShoppingReducer.reduce(it, action) }
        if (action is ShoppingAction.TurnProducts) {
            val generation = identityGeneration
            val missionVersion = mutableState.value.mission?.version
            decisionRequest {
                val facts = action.products.associate { product -> product.id to repository.productFacts(product.id) }
                if (generation == identityGeneration && mutableState.value.mission?.version == missionVersion) mutableState.update { state ->
                    state.copy(products = state.products.map { product -> facts[product.id]?.let { fact -> product.copy(attributes = fact.attributes, category = fact.category, imageRef = fact.imageRef) } ?: product })
                }
            }
        }
    }

    private fun statusText(stage: String?): String = when (stage) {
        "queued" -> "任务已接收，排队处理中"
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
            recommendationType = RecommendationType.valueOf(
                item.optString("recommendation_type", "STRICT"),
            ),
            relaxedConstraints = item.stringList("relaxed_constraints"),
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
            quoteState = when {
                item.getString("availability") != "AVAILABLE" -> QuoteState.UNAVAILABLE
                !Instant.parse(item.getString("expires_at")).isAfter(Instant.now()) -> QuoteState.EXPIRED
                else -> QuoteState.CURRENT
            },
            disclosure = "演示报价仅用于本地导购流程，不代表真实市场供应",
            priceMinor = item.optLongOrNull("price_minor"),
            businessFacts = parseBusinessFacts(item),
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
