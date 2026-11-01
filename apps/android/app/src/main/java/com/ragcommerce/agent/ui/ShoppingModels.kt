package com.ragcommerce.agent.ui

enum class PrimaryTab(val label: String) {
    TASK("任务"),
    DECISIONS("决策"),
    PROFILE("我的"),
}

enum class ConnectionState {
    CHECKING,
    ONLINE,
    OFFLINE,
    RECONNECTING,
    RECOVERED,
}

enum class QuoteState {
    CURRENT,
    CHANGED,
    EXPIRED,
    UNAVAILABLE,
}

enum class ComparisonSort(val label: String) {
    BUDGET("按预算"),
    HARD_CONSTRAINTS("按硬约束"),
    PREFERENCE("按偏好"),
}

enum class RecommendationType(val label: String) {
    STRICT("严格方案"),
    BUDGET("预算方案"),
    ALTERNATIVE("替代方案"),
}

data class EvidenceProductUi(
    val id: String,
    val variantId: String,
    val title: String,
    val fitSummary: String,
    val matchedConstraints: List<String>,
    val unmetConstraints: List<String>,
    val risks: List<String>,
    val evidenceRefs: List<String>,
    val recommendationType: RecommendationType = RecommendationType.STRICT,
    val relaxedConstraints: List<String> = emptyList(),
    val attributes: Map<String, String> = emptyMap(),
    val category: String = "",
    val imageRef: String? = null,
)

data class RecommendationRouteUi(
    val type: RecommendationType,
    val available: Boolean,
    val summary: String,
    val relaxedConstraints: List<String>,
    val productIds: List<String>,
)

data class BusinessFactUi(
    val type: String,
    val summary: String,
    val verificationLevel: String,
    val observedAt: String,
    val expiresAt: String?,
    val evidenceRef: String,
)

data class OfferUi(
    val id: String,
    val productId: String = "",
    val variantId: String = "",
    val merchantName: String,
    val priceText: String?,
    val shippingText: String?,
    val verification: String,
    val collectedAt: String,
    val expiresAt: String,
    val sourceRef: String,
    val quoteState: QuoteState,
    val disclosure: String,
    val confirmedChange: Boolean = false,
    val priceMinor: Long? = null,
    val businessFacts: List<BusinessFactUi> = emptyList(),
    val productTitle: String = "",
) {
    val mayResolve: Boolean
        get() = quoteState == QuoteState.CURRENT || (quoteState == QuoteState.CHANGED && confirmedChange)
}

data class SavedProductUi(
    val id: String,
    val title: String,
    val sourceRef: String,
)

class SavedComparisonSelectionException(message: String) : IllegalArgumentException(message)

data class SavedComparisonUi(val products: List<EvidenceProductUi>, val offers: List<OfferUi>) {
    companion object {
        fun create(products: List<EvidenceProductUi>, offers: List<OfferUi>): SavedComparisonUi {
            if (products.size !in 2..4 || products.map { it.id }.distinct().size != products.size)
                throw SavedComparisonSelectionException("请选择2–4款不同的已保存商品")
            if (products.any { it.category.isBlank() } || products.map { it.category }.distinct().size != 1)
                throw SavedComparisonSelectionException("请选同一品类比较；不同品类请分开选择")
            return SavedComparisonUi(products, offers)
        }
    }
}

data class CartGroupUi(
    val merchantName: String,
    val offers: List<OfferUi>,
)

data class WaitingCartUi(val quantities: Map<String, Int>, val offers: List<OfferUi>)

data class ComparisonUi(
    val items: List<String>,
    val dimensions: List<String>,
    val missingFields: List<String>,
    val evidenceRefs: List<String>,
)

data class MediaAttachmentUi(
    val uri: String,
    val kind: String,
    val displayName: String,
)

data class WatcherUi(
    val id: String,
    val offerId: String,
    val kind: String,
    val thresholdMinor: Long?,
    val disclosure: String,
)

data class MissionItemUi(
    val category: String,
    val quantity: Int,
)

data class ShoppingMissionUi(
    val goal: String,
    val version: Int,
    val items: List<MissionItemUi>,
    val hardConstraints: List<String>,
    val softPreferences: List<String>,
    val unknowns: List<String>,
    val budgetTotalMinor: Long?,
)

data class ShoppingUiState(
    val history: List<com.ragcommerce.agent.generated.ThreadHistoryEntry> = emptyList(),
    val historyVisible: Boolean = false,
    val conversationMessages: List<com.ragcommerce.agent.generated.ConversationMessage> = emptyList(),
    val conversationVisible: Boolean = false,
    val conversationHasMore: Boolean = false,
    val feedback: Map<String, String> = emptyMap(),
    val savedDetail: EvidenceProductUi? = null,
    val savedDetailOffers: List<OfferUi> = emptyList(),
    val savedComparisonIds: Set<String> = emptySet(),
    val savedComparison: SavedComparisonUi? = null,
    val decisionError: String? = null,
    val decisionBusy: Boolean = false,
    val pendingMediaInterpretations: List<com.ragcommerce.agent.generated.MediaInterpretation> = emptyList(),
    val mediaSourceRunId: String? = null,
    val mode: String = "PURCHASE",
    val exploration: com.ragcommerce.agent.generated.ExplorationState? = null,
    val explorationNeedsRefresh: Boolean = false,
    val selectedTab: PrimaryTab = PrimaryTab.TASK,
    val missionGoal: String = "",
    val mission: ShoppingMissionUi? = null,
    val missionEditDraft: String? = null,
    val pendingMissionRecalculation: Boolean = false,
    val draft: String = "",
    val isLoading: Boolean = false,
    val connection: ConnectionState = ConnectionState.CHECKING,
    val statusMessage: String = "正在确认服务连接",
    val products: List<EvidenceProductUi> = emptyList(),
    val showConversation: Boolean = false,
    val recommendationIndex: Int = 0,
    val recommendationRoutes: List<RecommendationRouteUi> = emptyList(),
    val comparedProductIds: Set<String> = emptySet(),
    val savedProducts: List<SavedProductUi> = emptyList(),
    val cartGroups: List<CartGroupUi> = emptyList(),
    val waitingOfferIds: Set<String> = emptySet(),
    val waitingQuantities: Map<String, Int> = emptyMap(),
    val waitingOffers: List<OfferUi> = emptyList(),
    val waitingCartBusy: Boolean = false,
    val watchers: List<WatcherUi> = emptyList(),
    val comparison: ComparisonUi? = null,
    val comparisonSort: ComparisonSort = ComparisonSort.HARD_CONSTRAINTS,
    val attachments: List<MediaAttachmentUi> = emptyList(),
    val agentMessages: List<String> = emptyList(),
    val clarificationQuestion: String? = null,
    val evidenceRefs: List<String> = emptyList(),
    val pendingApprovalTool: String? = null,
    val pendingApprovalArguments: Map<String, String> = emptyMap(),
    val preparedMerchantOfferId: String? = null,
    val preparedMerchantHost: String? = null,
    val qualityDataConsent: Boolean = false,
)

sealed interface ShoppingAction {
    data object LoadHistory : ShoppingAction
    data object CloseHistory : ShoppingAction
    data class OpenHistory(val threadId: String) : ShoppingAction
    data class OrganizeHistory(val threadId: String, val title: String?, val archived: Boolean?) : ShoppingAction
    data object LoadConversation : ShoppingAction
    data object MoreConversation : ShoppingAction
    data object CloseConversation : ShoppingAction
    data class AskCandidate(val productId: String) : ShoppingAction
    data class ExcludeCandidate(val productId: String, val reason: String, val scope: String = "PRODUCT", val undo: Boolean = false) : ShoppingAction
    data class UndoCandidateFeedback(val key: String) : ShoppingAction
    data class OpenSaved(val productId: String) : ShoppingAction
    data class RemoveSaved(val productId: String) : ShoppingAction
    data class ContinueSaved(val product: EvidenceProductUi) : ShoppingAction
    data object CloseSaved : ShoppingAction
    data class ToggleSavedComparison(val productId: String) : ShoppingAction
    data object CompareSavedSelection : ShoppingAction
    data object ClearSavedComparison : ShoppingAction
    data class MediaInterpreted(val value: com.ragcommerce.agent.generated.MediaInterpretation, val runId: String) : ShoppingAction
    data object ConfirmMedia : ShoppingAction
    data class Explore(val kind: String, val directionId: String? = null, val value: String? = null,
                       val tags: List<String> = emptyList(), val outcome: String? = null) : ShoppingAction
    data class ExplorationUpdated(val mode: String,
        val exploration: com.ragcommerce.agent.generated.ExplorationState) : ShoppingAction
    data class SelectTab(val tab: PrimaryTab) : ShoppingAction

    data class UpdateDraft(val value: String) : ShoppingAction

    data class UseClarificationPrompt(val value: String) : ShoppingAction

    data object BeginMissionEdit : ShoppingAction

    data class UpdateMissionEdit(val value: String) : ShoppingAction

    data object ApplyMissionEdit : ShoppingAction

    data object CancelMissionEdit : ShoppingAction

    data object RecalculateMission : ShoppingAction

    data object SubmitMission : ShoppingAction

    data class ToggleCompare(val productId: String) : ShoppingAction

    data class SetComparisonSort(val value: ComparisonSort) : ShoppingAction

    data class ConfirmQuoteChange(val offerId: String) : ShoppingAction
    data class RequoteOffer(val offer: OfferUi) : ShoppingAction
    data class PrepareMerchant(val offer: OfferUi) : ShoppingAction
    data class OfferRequoted(val productId: String, val offers: List<OfferUi>) : ShoppingAction

    data class SetConnection(val value: ConnectionState) : ShoppingAction

    data object RetryConnection : ShoppingAction

    data object ContinueRecoveredMission : ShoppingAction

    data object ReturnToMissionConversation : ShoppingAction

    data object ShowCurrentRecommendations : ShoppingAction
    data class RecommendationPageChanged(val page: Int) : ShoppingAction

    data object StartNewMission : ShoppingAction

    data class AddAttachment(val value: MediaAttachmentUi) : ShoppingAction

    data class RemoveAttachment(val uri: String) : ShoppingAction

    data class TurnStatus(val message: String) : ShoppingAction

    data class MissionUpdated(val mission: ShoppingMissionUi) : ShoppingAction

    data class TurnMessage(val text: String) : ShoppingAction

    data class TurnEvidence(val ref: String) : ShoppingAction

    data class TurnProducts(
        val products: List<EvidenceProductUi>,
        val routes: List<RecommendationRouteUi> = emptyList(),
    ) : ShoppingAction

    data class TurnOffers(val offers: List<OfferUi>) : ShoppingAction

    data class SetWaitingQuantity(val offer: OfferUi, val quantity: Int) : ShoppingAction
    data class WaitingCartUpdated(val cart: WaitingCartUi) : ShoppingAction

    data class WatcherCreated(val watcher: WatcherUi) : ShoppingAction

    data class TurnComparison(val comparison: ComparisonUi) : ShoppingAction

    data class ApprovalRequired(val tool: String, val arguments: Map<String, String> = emptyMap()) : ShoppingAction

    data class ClarificationRequired(val question: String) : ShoppingAction

    data class ResolveApproval(val approved: Boolean) : ShoppingAction

    data class TurnCompleted(val message: String = "Agent 已完成") : ShoppingAction

    data class TurnFailed(val message: String) : ShoppingAction

    data class QuoteRefreshRequired(val offerId: String) : ShoppingAction
}

object ShoppingReducer {
    fun reduce(state: ShoppingUiState, action: ShoppingAction): ShoppingUiState =
        when (action) {
            ShoppingAction.CloseHistory -> state.copy(historyVisible = false)
            ShoppingAction.CloseConversation -> state.copy(conversationVisible = false)
            ShoppingAction.CloseSaved -> state.copy(savedDetail = null, savedDetailOffers = emptyList())
            is ShoppingAction.ToggleSavedComparison -> {
                val selected = state.savedComparisonIds
                if (action.productId !in selected && (selected.size >= 4 || state.savedProducts.none { it.id == action.productId })) state
                else state.copy(savedComparisonIds = if (action.productId in selected) selected - action.productId else selected + action.productId,
                    savedComparison = null, decisionError = null)
            }
            ShoppingAction.ClearSavedComparison -> state.copy(savedComparisonIds = emptySet(), savedComparison = null, decisionError = null)
            ShoppingAction.CompareSavedSelection -> state
            is ShoppingAction.AskCandidate -> state.products.firstOrNull { it.id == action.productId }?.let { product ->
                state.copy(showConversation = true, selectedTab = PrimaryTab.TASK, draft = "针对【${product.title}】，我想了解：", statusMessage = "已指定当前候选，你可以继续提问或补充取舍")
            } ?: state
            ShoppingAction.LoadHistory, is ShoppingAction.OpenHistory, is ShoppingAction.OrganizeHistory,
            ShoppingAction.LoadConversation, ShoppingAction.MoreConversation,
            is ShoppingAction.ExcludeCandidate, is ShoppingAction.OpenSaved, is ShoppingAction.RemoveSaved,
            is ShoppingAction.ContinueSaved, is ShoppingAction.UndoCandidateFeedback -> state
            is ShoppingAction.MediaInterpreted -> state.copy(
                pendingMediaInterpretations = (state.pendingMediaInterpretations + action.value).distinctBy { it.media_id },
                mediaSourceRunId = action.runId,
                draft = listOf(if (state.pendingMediaInterpretations.isEmpty()) state.missionGoal.trim() else state.draft.trim(), action.value.recognized_text)
                    .filter(String::isNotBlank).joinToString("；").take(500),
                products = emptyList(), recommendationRoutes = emptyList(), showConversation = true,
                statusMessage = "请核对识别内容，再确认继续",
            )
            ShoppingAction.ConfirmMedia -> state.copy(isLoading = true, statusMessage = "正在按确认后的需求检索")
            is ShoppingAction.Explore -> state
            is ShoppingAction.ExplorationUpdated -> state.copy(
                pendingMediaInterpretations = emptyList(), mediaSourceRunId = null,
                mode = action.mode, exploration = action.exploration,
                explorationNeedsRefresh = false,
                products = emptyList(), recommendationRoutes = emptyList(),
                comparedProductIds = emptySet(), comparison = null, cartGroups = emptyList(),
                pendingApprovalTool = null, clarificationQuestion = null,
                showConversation = true, draft = "", attachments = emptyList(),
                missionEditDraft = null, pendingMissionRecalculation = false,
            )
            is ShoppingAction.SelectTab -> if (state.connection in navigationLockedConnections) state
            else state.copy(selectedTab = action.tab)
            is ShoppingAction.UpdateDraft -> state.copy(draft = action.value.take(10_000))
            is ShoppingAction.UseClarificationPrompt -> state.copy(
                draft = listOf(state.draft.trim(), action.value)
                    .filter(String::isNotBlank)
                    .joinToString("；")
                    .take(10_000),
            )
            ShoppingAction.BeginMissionEdit -> state.copy(
                missionEditDraft = state.missionGoal,
            )
            is ShoppingAction.UpdateMissionEdit -> state.copy(
                missionEditDraft = action.value.take(500),
            )
            ShoppingAction.ApplyMissionEdit -> {
                val updated = state.missionEditDraft?.trim().orEmpty()
                if (updated.isBlank()) state else state.copy(
                    missionGoal = updated,
                    missionEditDraft = null,
                    pendingMissionRecalculation = updated != state.mission?.goal,
                    statusMessage = "约束已修改，重新计算后更新推荐",
                )
            }
            ShoppingAction.CancelMissionEdit -> state.copy(missionEditDraft = null)
            ShoppingAction.RecalculateMission -> state
            ShoppingAction.SubmitMission -> {
                if (state.draft.isBlank() && state.attachments.isEmpty()) state
                else state.copy(
                    missionGoal = state.missionGoal.ifBlank { state.draft.trim() },
                    draft = "",
                    isLoading = true,
                    clarificationQuestion = null,
                    pendingApprovalTool = null,
                    statusMessage = "正在通过统一 Agent 检索证据",
                )
            }
            is ShoppingAction.ToggleCompare -> {
                val values = state.comparedProductIds.toMutableSet()
                if (!values.add(action.productId)) values.remove(action.productId)
                state.copy(comparedProductIds = values.take(4).toSet())
            }
            is ShoppingAction.SetComparisonSort -> state.copy(comparisonSort = action.value)
            is ShoppingAction.ConfirmQuoteChange -> state.copy(
                waitingOffers = state.waitingOffers.map { if (it.id == action.offerId) it.copy(confirmedChange = true) else it },
                cartGroups = state.cartGroups.map { group ->
                    group.copy(
                        offers = group.offers.map { offer ->
                            if (offer.id == action.offerId) offer.copy(confirmedChange = true) else offer
                        },
                    )
                },
            )
            is ShoppingAction.RequoteOffer -> state
            is ShoppingAction.PrepareMerchant -> state
            is ShoppingAction.OfferRequoted -> {
                val offers = state.cartGroups.flatMap { it.offers }
                    .filterNot { it.productId == action.productId } + action.offers
                state.copy(
                    waitingOffers = state.waitingOffers.map { old ->
                        if (old.productId == action.productId) action.offers.firstOrNull { it.id == old.id }
                            ?.copy(productTitle = old.productTitle) ?: old.copy(quoteState = QuoteState.UNAVAILABLE)
                        else old
                    },
                    cartGroups = offers.groupBy(OfferUi::merchantName).map { (merchant, values) -> CartGroupUi(merchant, values) },
                    statusMessage = if (action.offers.isEmpty()) "当前没有可用报价" else "报价已更新 · 演示报价不是成交价",
                )
            }
            is ShoppingAction.SetConnection -> state.copy(
                connection = action.value,
                selectedTab = if (action.value in navigationLockedConnections) PrimaryTab.TASK else state.selectedTab,
                statusMessage = when (action.value) {
                    ConnectionState.CHECKING -> "正在确认服务连接"
                    ConnectionState.ONLINE -> "已连接"
                    ConnectionState.OFFLINE -> "当前离线，保留 Mission 与待购状态"
                    ConnectionState.RECONNECTING -> "连接中断，正在从最后事件恢复"
                    ConnectionState.RECOVERED -> "已从服务端恢复任务状态"
                },
            )
            ShoppingAction.RetryConnection -> state.copy(
                connection = ConnectionState.RECONNECTING,
                selectedTab = PrimaryTab.TASK,
                statusMessage = "正在重新连接，并从最后事件游标恢复",
            )
            ShoppingAction.ContinueRecoveredMission -> state.copy(
                connection = ConnectionState.ONLINE,
                statusMessage = "Agent 已完成",
            )
            ShoppingAction.ReturnToMissionConversation -> state.copy(
                selectedTab = PrimaryTab.TASK,
                showConversation = true,
                draft = state.missionGoal,
                statusMessage = "继续当前 Mission",
            )
            ShoppingAction.ShowCurrentRecommendations -> state.copy(
                selectedTab = PrimaryTab.TASK,
                showConversation = false,
            )
            is ShoppingAction.RecommendationPageChanged -> state.copy(recommendationIndex = action.page)
            ShoppingAction.StartNewMission -> state.copy(
                feedback = emptyMap(), historyVisible = false,
                conversationMessages = emptyList(), conversationVisible = false, conversationHasMore = false,
                savedDetail = null, savedDetailOffers = emptyList(), decisionBusy = false,
                recommendationIndex = 0,
                pendingApprovalArguments = emptyMap(),
                preparedMerchantHost = null, preparedMerchantOfferId = null,
                pendingMediaInterpretations = emptyList(), mediaSourceRunId = null,
                mode = "PURCHASE", exploration = null,
                explorationNeedsRefresh = false,
                selectedTab = PrimaryTab.TASK,
                missionGoal = "",
                mission = null,
                missionEditDraft = null,
                pendingMissionRecalculation = false,
                draft = "",
                isLoading = false,
                products = emptyList(),
                showConversation = true,
                cartGroups = emptyList(),
                recommendationRoutes = emptyList(),
                comparedProductIds = emptySet(),
                comparison = null,
                attachments = emptyList(),
                agentMessages = emptyList(),
                clarificationQuestion = null,
                evidenceRefs = emptyList(),
                pendingApprovalTool = null,
                statusMessage = "已新建购物任务",
            )
            is ShoppingAction.AddAttachment -> {
                if (state.attachments.any { it.uri == action.value.uri } || state.attachments.size >= 8) state
                else state.copy(attachments = state.attachments + action.value)
            }
            is ShoppingAction.RemoveAttachment -> state.copy(
                attachments = state.attachments.filterNot { it.uri == action.uri },
            )
            is ShoppingAction.TurnStatus -> state.copy(statusMessage = action.message)
            is ShoppingAction.MissionUpdated -> state.copy(
                missionGoal = action.mission.goal,
                mission = action.mission,
                pendingMissionRecalculation = false,
                statusMessage = "Mission 已更新",
            )
            is ShoppingAction.TurnMessage -> state.copy(
                agentMessages = (state.agentMessages + action.text).takeLast(100),
            )
            is ShoppingAction.TurnEvidence -> state.copy(
                evidenceRefs = (state.evidenceRefs + action.ref).distinct().takeLast(100),
            )
            is ShoppingAction.TurnProducts -> state.copy(
                recommendationIndex = if (state.products.map { it.id } == action.products.map { it.id }) state.recommendationIndex else 0,
                products = action.products,
                showConversation = false,
                recommendationRoutes = action.routes,
                evidenceRefs = (state.evidenceRefs + action.products.flatMap { it.evidenceRefs })
                    .distinct()
                    .takeLast(100),
            )
            is ShoppingAction.TurnOffers -> state.copy(
                cartGroups = action.offers.groupBy(OfferUi::merchantName).map { (merchant, offers) ->
                    CartGroupUi(merchant, offers)
                },
                evidenceRefs = (state.evidenceRefs + action.offers.map(OfferUi::sourceRef))
                    .distinct()
                    .takeLast(100),
            )
            is ShoppingAction.TurnComparison -> state.copy(
                comparison = action.comparison,
                evidenceRefs = (state.evidenceRefs + action.comparison.evidenceRefs)
                    .distinct()
                    .takeLast(100),
            )
            is ShoppingAction.ApprovalRequired -> state.copy(
                isLoading = false,
                pendingApprovalTool = action.tool,
                pendingApprovalArguments = if (action.arguments.isEmpty() && state.pendingApprovalTool == action.tool) state.pendingApprovalArguments else action.arguments,
                statusMessage = "有一项操作等待确认，确认前不会执行",
            )
            is ShoppingAction.ClarificationRequired -> state.copy(
                isLoading = false,
                clarificationQuestion = action.question,
                statusMessage = "Agent 需要补充一个条件",
                agentMessages = (state.agentMessages + action.question)
                    .distinct()
                    .takeLast(100),
            )
            is ShoppingAction.ResolveApproval -> state.copy(
                isLoading = true,
                statusMessage = if (action.approved) "正在执行已确认操作" else "正在拒绝操作",
            )
            is ShoppingAction.TurnCompleted -> state.copy(
                isLoading = false,
                attachments = emptyList(),
                pendingApprovalTool = null,
                statusMessage = action.message,
            )
            is ShoppingAction.TurnFailed -> state.copy(
                isLoading = false,
                pendingApprovalTool = null,
                statusMessage = action.message,
            )
            is ShoppingAction.QuoteRefreshRequired -> state.copy(
                waitingOffers = state.waitingOffers.map { if (it.id == action.offerId) it.copy(quoteState = QuoteState.CHANGED, confirmedChange = false) else it },
                cartGroups = state.cartGroups.map { group ->
                    group.copy(
                        offers = group.offers.map { offer ->
                            if (offer.id == action.offerId) {
                                offer.copy(quoteState = QuoteState.CHANGED, confirmedChange = false)
                            } else {
                                offer
                            }
                        },
                    )
                },
                statusMessage = "商家报价已变化，请重新确认",
            )
            is ShoppingAction.SetWaitingQuantity -> state
            is ShoppingAction.WaitingCartUpdated -> state.copy(
                waitingOfferIds = action.cart.quantities.keys,
                waitingQuantities = action.cart.quantities,
                waitingOffers = action.cart.offers,
            )
            is ShoppingAction.WatcherCreated -> state.copy(
                watchers = (state.watchers + action.watcher).distinctBy { it.id },
            )
        }

    private val navigationLockedConnections = setOf(
        ConnectionState.CHECKING,
        ConnectionState.RECONNECTING,
        ConnectionState.RECOVERED,
    )
}
