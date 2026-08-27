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
import javax.inject.Inject
import java.net.URI

internal fun isSafeMerchantUrl(value: String): Boolean = runCatching {
    val uri = URI(value)
    uri.scheme.equals("https", ignoreCase = true) && !uri.host.isNullOrBlank()
}.getOrDefault(false)

@HiltViewModel
class ShoppingViewModel @Inject constructor(
    private val savedStateHandle: SavedStateHandle,
    private val repository: ShoppingRepository,
) : ViewModel() {
    private val mutableState = MutableStateFlow(
        ShoppingUiState(
            selectedTab = savedStateHandle.get<String>("selected_tab")
                ?.let { runCatching { PrimaryTab.valueOf(it) }.getOrNull() }
                ?: PrimaryTab.GUIDE,
        ),
    )
    val state: StateFlow<ShoppingUiState> = mutableState.asStateFlow()
    private val mutableMerchantLinks = MutableSharedFlow<String>(extraBufferCapacity = 1)
    val merchantLinks: SharedFlow<String> = mutableMerchantLinks.asSharedFlow()
    private val activeRuns = mutableSetOf<String>()
    private var currentRunId: String? = null
    private var currentCursor = 0L
    private var submittingTurn = false

    init {
        viewModelScope.launch {
            dispatch(
                ShoppingAction.SetConnection(
                    if (repository.probeConnection()) ConnectionState.ONLINE else ConnectionState.OFFLINE,
                ),
            )
        }
        viewModelScope.launch {
            repository.observeLocal().collect { snapshot ->
                val tab = runCatching { PrimaryTab.valueOf(snapshot.selectedTab) }
                    .getOrDefault(mutableState.value.selectedTab)
                mutableState.update { current ->
                    current.copy(
                        selectedTab = tab,
                        missionGoal = snapshot.mission?.goal ?: current.missionGoal,
                        savedProducts = snapshot.items
                            .filter { it.kind == "LIST" }
                            .map { SavedProductUi(it.externalId, it.title, it.sourceRef) },
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

    fun dispatch(action: ShoppingAction) {
        when (action) {
            ShoppingAction.SubmitMission -> submitCurrentTurn()
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
                if (url == null || !isSafeMerchantUrl(url)) {
                    mutableState.update {
                        ShoppingReducer.reduce(it, ShoppingAction.TurnStatus("商家链接不可用或未通过安全校验"))
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

    fun reportMerchantLaunchFailure() {
        mutableState.update {
            ShoppingReducer.reduce(it, ShoppingAction.TurnStatus("设备上没有可安全处理该商家链接的应用"))
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
                recovered = true
                mutableState.update {
                    ShoppingReducer.reduce(it, ShoppingAction.SetConnection(ConnectionState.RECONNECTING))
                }
                delay(500)
                repository.readEvents(runId, currentCursor)
            }
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
            "status" -> ShoppingAction.TurnStatus(statusText(event.data["stage"]))
            "message_delta" -> ShoppingAction.TurnMessage(event.data["text"].orEmpty())
            "evidence" -> ShoppingAction.TurnEvidence(event.data["ref"].orEmpty())
            "approval_required" -> ShoppingAction.ApprovalRequired(event.data["tool"].orEmpty())
            "completed" -> ShoppingAction.TurnCompleted()
            "failed" -> ShoppingAction.TurnFailed(
                "Agent 未完成：${event.data["summary"].orEmpty().ifBlank { "未知错误" }}",
            )
            else -> ShoppingAction.TurnStatus("收到未识别事件，已安全忽略")
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

}
