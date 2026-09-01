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

data class EvidenceProductUi(
    val id: String,
    val variantId: String,
    val title: String,
    val fitSummary: String,
    val matchedConstraints: List<String>,
    val unmetConstraints: List<String>,
    val risks: List<String>,
    val evidenceRefs: List<String>,
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
) {
    val mayResolve: Boolean
        get() = quoteState == QuoteState.CURRENT || (quoteState == QuoteState.CHANGED && confirmedChange)
}

data class SavedProductUi(
    val id: String,
    val title: String,
    val sourceRef: String,
)

data class CartGroupUi(
    val merchantName: String,
    val offers: List<OfferUi>,
)

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

data class ShoppingUiState(
    val selectedTab: PrimaryTab = PrimaryTab.TASK,
    val missionGoal: String = "",
    val draft: String = "",
    val isLoading: Boolean = false,
    val connection: ConnectionState = ConnectionState.CHECKING,
    val statusMessage: String = "正在确认服务连接",
    val products: List<EvidenceProductUi> = emptyList(),
    val comparedProductIds: Set<String> = emptySet(),
    val savedProducts: List<SavedProductUi> = emptyList(),
    val cartGroups: List<CartGroupUi> = emptyList(),
    val comparison: ComparisonUi? = null,
    val attachments: List<MediaAttachmentUi> = emptyList(),
    val agentMessages: List<String> = emptyList(),
    val evidenceRefs: List<String> = emptyList(),
    val pendingApprovalTool: String? = null,
    val qualityDataConsent: Boolean = false,
)

sealed interface ShoppingAction {
    data class SelectTab(val tab: PrimaryTab) : ShoppingAction

    data class UpdateDraft(val value: String) : ShoppingAction

    data object SubmitMission : ShoppingAction

    data class ToggleCompare(val productId: String) : ShoppingAction

    data class ConfirmQuoteChange(val offerId: String) : ShoppingAction

    data class SetConnection(val value: ConnectionState) : ShoppingAction

    data object RetryConnection : ShoppingAction

    data object ContinueRecoveredMission : ShoppingAction

    data object ReturnToMissionConversation : ShoppingAction

    data class AddAttachment(val value: MediaAttachmentUi) : ShoppingAction

    data class RemoveAttachment(val uri: String) : ShoppingAction

    data class TurnStatus(val message: String) : ShoppingAction

    data class MissionUpdated(val goal: String) : ShoppingAction

    data class TurnMessage(val text: String) : ShoppingAction

    data class TurnEvidence(val ref: String) : ShoppingAction

    data class TurnProducts(val products: List<EvidenceProductUi>) : ShoppingAction

    data class TurnOffers(val offers: List<OfferUi>) : ShoppingAction

    data class TurnComparison(val comparison: ComparisonUi) : ShoppingAction

    data class ApprovalRequired(val tool: String) : ShoppingAction

    data class ClarificationRequired(val question: String) : ShoppingAction

    data class ResolveApproval(val approved: Boolean) : ShoppingAction

    data class TurnCompleted(val message: String = "Agent 已完成") : ShoppingAction

    data class TurnFailed(val message: String) : ShoppingAction

    data class QuoteRefreshRequired(val offerId: String) : ShoppingAction
}

object ShoppingReducer {
    fun reduce(state: ShoppingUiState, action: ShoppingAction): ShoppingUiState =
        when (action) {
            is ShoppingAction.SelectTab -> state.copy(selectedTab = action.tab)
            is ShoppingAction.UpdateDraft -> state.copy(draft = action.value.take(10_000))
            ShoppingAction.SubmitMission -> {
                if (state.draft.isBlank() && state.attachments.isEmpty()) state
                else state.copy(
                    missionGoal = state.draft.trim().ifBlank { state.missionGoal },
                    draft = "",
                    isLoading = true,
                    pendingApprovalTool = null,
                    statusMessage = "正在通过统一 Agent 检索证据",
                )
            }
            is ShoppingAction.ToggleCompare -> {
                val values = state.comparedProductIds.toMutableSet()
                if (!values.add(action.productId)) values.remove(action.productId)
                state.copy(comparedProductIds = values.take(4).toSet())
            }
            is ShoppingAction.ConfirmQuoteChange -> state.copy(
                cartGroups = state.cartGroups.map { group ->
                    group.copy(
                        offers = group.offers.map { offer ->
                            if (offer.id == action.offerId) offer.copy(confirmedChange = true) else offer
                        },
                    )
                },
            )
            is ShoppingAction.SetConnection -> state.copy(
                connection = action.value,
                statusMessage = when (action.value) {
                    ConnectionState.CHECKING -> "正在确认服务连接"
                    ConnectionState.ONLINE -> "已连接"
                    ConnectionState.OFFLINE -> "当前离线，保留 Mission 与待购状态"
                    ConnectionState.RECONNECTING -> "连接中断，正在从最后事件恢复"
                    ConnectionState.RECOVERED -> "已从最后事件恢复，无重复完成事件"
                },
            )
            ShoppingAction.RetryConnection -> state.copy(
                connection = ConnectionState.RECONNECTING,
                statusMessage = "正在重新连接，并从最后事件游标恢复",
            )
            ShoppingAction.ContinueRecoveredMission -> state.copy(
                connection = ConnectionState.ONLINE,
                statusMessage = "Agent 已完成",
            )
            ShoppingAction.ReturnToMissionConversation -> state.copy(
                products = emptyList(),
                isLoading = false,
                statusMessage = "继续当前 Mission",
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
                missionGoal = action.goal,
                statusMessage = "Mission 已更新",
            )
            is ShoppingAction.TurnMessage -> state.copy(
                agentMessages = (state.agentMessages + action.text).takeLast(100),
            )
            is ShoppingAction.TurnEvidence -> state.copy(
                evidenceRefs = (state.evidenceRefs + action.ref).distinct().takeLast(100),
            )
            is ShoppingAction.TurnProducts -> state.copy(
                products = action.products,
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
                comparedProductIds = action.comparison.items.toSet(),
                evidenceRefs = (state.evidenceRefs + action.comparison.evidenceRefs)
                    .distinct()
                    .takeLast(100),
            )
            is ShoppingAction.ApprovalRequired -> state.copy(
                isLoading = false,
                pendingApprovalTool = action.tool,
                statusMessage = "工具 ${action.tool} 需要明确确认",
            )
            is ShoppingAction.ClarificationRequired -> state.copy(
                isLoading = false,
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
        }
}
