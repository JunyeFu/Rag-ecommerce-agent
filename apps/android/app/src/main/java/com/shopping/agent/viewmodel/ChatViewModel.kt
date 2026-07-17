package com.shopping.agent.viewmodel

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.shopping.agent.data.local.CartEvents
import com.shopping.agent.data.local.CartSessionManager
import com.shopping.agent.data.local.UserRepository
import com.shopping.agent.data.mock.mockProducts
import com.shopping.agent.data.model.*
import com.shopping.agent.data.remote.SseClient
import com.shopping.agent.data.repository.ChatRepository
import com.shopping.agent.data.tts.TtsManager
import com.shopping.agent.data.voice.AudioCompressor
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import java.io.File
import java.util.UUID
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

data class GuideUiState(
    val messages: List<ChatMessage> = emptyList(),
    val conversations: List<ConversationMeta> = emptyList(),
    val currentConversationId: String = UUID.randomUUID().toString(),
    val inputText: String = "",
    val isRecording: Boolean = false,
    val selectedImageUri: Uri? = null,

    val isStreaming: Boolean = false,
    val streamingText: String = "",
    val streamingCards: List<Product> = emptyList(),
    val searchStatus: String = "",

    val clarifyChips: List<String> = emptyList(),
    val clarifyQuestion: String = "",       // Agent 反问的问题文本

    val ttsEnabled: Boolean = false,

    val screenState: ScreenState = ScreenState.Idle,
    val sessionId: String = UUID.randomUUID().toString(),
    val checkoutNavigationRequest: Int = 0,
)

sealed class ScreenState {
    data object Idle : ScreenState()
    data object Loading : ScreenState()
    data class Streaming(val partialText: String = "") : ScreenState()
    data class Content(val hasProducts: Boolean = false) : ScreenState()
    data class Error(val message: String) : ScreenState()
}

class ChatViewModel(application: Application) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow(GuideUiState())
    val uiState: StateFlow<GuideUiState> = _uiState.asStateFlow()

    private val chatRepository = ChatRepository()
    private val visionClient = SseClient()
    private val userRepo = UserRepository(application)
    private val ttsManager = TtsManager(application)
    private val initComplete = CompletableDeferred<Unit>()
    private val cartSessionId = CartSessionManager.getOrCreate(application)

    init {
        viewModelScope.launch {
            // 恢复持久化的 sessionId（后端状态跟踪，跨会话复用）
            val savedId = userRepo.getSetting("chat_session_id")
            val sessionId = if (savedId.isNotEmpty()) savedId else _uiState.value.sessionId
            if (savedId.isEmpty()) {
                userRepo.setSetting("chat_session_id", sessionId)
            }

            // 加载最近使用的 conversationId
            val lastConvId = userRepo.getSetting("last_conversation_id")
            val convId = if (lastConvId.isNotEmpty()) lastConvId else _uiState.value.currentConversationId

            // 确保会话记录存在
            userRepo.createConversation(convId, "")
            val messages = userRepo.getMessages(convId)

            // 加载对话列表
            val metas = userRepo.getConversationMetas()

            // 恢复该对话的排除 chips（按对话独立存储）
            val savedChipsJson = userRepo.getSetting("clarify_chips_$convId")
            val savedChips: List<String> = if (savedChipsJson.isNotEmpty()) {
                try {
                    Gson().fromJson(savedChipsJson, object : TypeToken<List<String>>() {}.type)
                } catch (_: Exception) { emptyList() }
            } else emptyList()

            _uiState.update {
                it.copy(
                    sessionId = sessionId,
                    currentConversationId = convId,
                    messages = messages,
                    conversations = metas,
                    clarifyChips = savedChips,
                    screenState = if (messages.isNotEmpty()) ScreenState.Content(true) else ScreenState.Idle,
                )
            }
            initComplete.complete(Unit)
        }
    }

    fun onInputChange(text: String) {
        _uiState.update { it.copy(inputText = text) }
    }

    fun toggleTts() {
        val newState = ttsManager.toggleEnabled()
        _uiState.update { it.copy(ttsEnabled = newState) }
    }

    override fun onCleared() {
        super.onCleared()
        ttsManager.shutdown()
    }

    // ═══════════════════════════════════════════════════════
    // 每日问候（当日首次打开 App 时单开一个独立对话）
    // ═══════════════════════════════════════════════════════

    suspend fun sendDailyGreeting() {
        // 等待 init 协程完成，确保 currentConversationId 和 messages 已从 DB 恢复
        initComplete.await()

        val today = java.time.LocalDate.now().toString()
        val lastGreetingDate = userRepo.getSetting("last_greeting_date")
        if (lastGreetingDate == today) return

        // 有历史消息时不覆盖 — 用户可能在继续之前的对话
        if (_uiState.value.messages.isNotEmpty()) return

        userRepo.setSetting("last_greeting_date", today)

        // 从 settings 读取真正的 conversationId，不依赖可能未初始化的 _uiState
        val savedConvId = userRepo.getSetting("last_conversation_id")
        val convId = if (savedConvId.isNotEmpty()) savedConvId else _uiState.value.currentConversationId

        val greeting = ChatMessage(
            id = UUID.randomUUID().toString(),
            role = MessageRole.Assistant,
            content = "fujunye，早上好 ☀️\n\n以下是今日为你精选的推荐：",
            status = MessageStatus.Sent,
        )
        val products = mockProducts.take(3)
        val productMsg = ChatMessage(
            id = UUID.randomUUID().toString(),
            role = MessageRole.Assistant,
            content = "",
            productCards = products,
            status = MessageStatus.Sent,
        )

        userRepo.createConversation(convId, "每日推荐")
        userRepo.saveMessage(greeting, convId)
        userRepo.saveMessage(productMsg, convId)
        refreshConversationList()

        _uiState.update {
            it.copy(
                messages = it.messages + greeting + productMsg,
                screenState = ScreenState.Content(true),
            )
        }
    }

    // ═══════════════════════════════════════════════════════
    // 多对话管理
    // ═══════════════════════════════════════════════════════

    fun createNewConversation() {
        val newId = UUID.randomUUID().toString()
        viewModelScope.launch {
            userRepo.createConversation(newId, "")
            userRepo.setSetting("last_conversation_id", newId)
            refreshConversationList()
        }
        _uiState.update {
            it.copy(
                currentConversationId = newId,
                messages = emptyList(),
                streamingText = "",
                streamingCards = emptyList(),
                clarifyChips = emptyList(),
                clarifyQuestion = "",
                searchStatus = "",
                screenState = ScreenState.Idle,
                inputText = "",
            )
        }
    }

    fun loadConversation(convId: String) {
        if (convId == _uiState.value.currentConversationId) return
        viewModelScope.launch {
            userRepo.setSetting("last_conversation_id", convId)
            val messages = userRepo.getMessages(convId)
            // 恢复该对话的排除 chips
            val savedChipsJson = userRepo.getSetting("clarify_chips_$convId")
            val savedChips: List<String> = if (savedChipsJson.isNotEmpty()) {
                try {
                    Gson().fromJson(savedChipsJson, object : TypeToken<List<String>>() {}.type)
                } catch (_: Exception) { emptyList() }
            } else emptyList()
            _uiState.update {
                it.copy(
                    currentConversationId = convId,
                    messages = messages,
                    streamingText = "",
                    streamingCards = emptyList(),
                    clarifyChips = savedChips,
                    clarifyQuestion = "",
                    searchStatus = "",
                    screenState = if (messages.isNotEmpty()) ScreenState.Content(true) else ScreenState.Idle,
                )
            }
        }
    }

    fun deleteConversation(convId: String) {
        viewModelScope.launch {
            userRepo.deleteConversation(convId)
            val metas = userRepo.getConversationMetas()

            if (convId == _uiState.value.currentConversationId) {
                // 删除的是当前对话 → 切换到最近的对话或创建新对话
                val next = metas.firstOrNull()
                if (next != null) {
                    userRepo.setSetting("last_conversation_id", next.id)
                    val messages = userRepo.getMessages(next.id)
                    _uiState.update {
                        it.copy(
                            currentConversationId = next.id,
                            messages = messages,
                            conversations = metas,
                            streamingText = "",
                            streamingCards = emptyList(),
                            clarifyChips = emptyList(),
                            clarifyQuestion = "",
                            searchStatus = "",
                            screenState = if (messages.isNotEmpty()) ScreenState.Content(true) else ScreenState.Idle,
                        )
                    }
                } else {
                    // 没有其他对话了，创建新的
                    val newId = UUID.randomUUID().toString()
                    userRepo.createConversation(newId, "")
                    userRepo.setSetting("last_conversation_id", newId)
                    _uiState.update {
                        it.copy(
                            currentConversationId = newId,
                            messages = emptyList(),
                            conversations = emptyList(),
                            streamingText = "",
                            streamingCards = emptyList(),
                            clarifyChips = emptyList(),
                            clarifyQuestion = "",
                            searchStatus = "",
                            screenState = ScreenState.Idle,
                        )
                    }
                }
            } else {
                _uiState.update { it.copy(conversations = metas) }
            }
        }
    }

    private suspend fun refreshConversationList() {
        val metas = userRepo.getConversationMetas()
        _uiState.update { it.copy(conversations = metas) }
    }

    // ═══════════════════════════════════════════════════════
    // 发送消息
    // ═══════════════════════════════════════════════════════

    fun sendMessage() {
        if (_uiState.value.isStreaming) return
        val text = _uiState.value.inputText.trim()
        if (text.isEmpty()) return

        if (shouldOpenCheckout(text)) {
            val userMessage = ChatMessage(
                id = UUID.randomUUID().toString(),
                role = MessageRole.User,
                content = text,
                status = MessageStatus.Sent,
            )
            viewModelScope.launch {
                userRepo.saveMessage(userMessage, _uiState.value.currentConversationId)
                syncCartAfterChatIfNeeded(text)
            }
            // 检查购物车中是否有可下单的商品，避免空购物车跳转至确认订单页面
            val hasCartItems = runBlocking {
                try {
                    kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                        userRepo.getCartItemsForCurrentUser(cartSessionId).isNotEmpty()
                    }
                } catch (_: Exception) {
                    false
                }
            }
            if (!hasCartItems) {
                // 购物车为空，不跳转确认订单页面，走正常 SSE 对话流程让 RAG 链路处理
                _uiState.update {
                    it.copy(
                        messages = it.messages + userMessage,
                        inputText = "",
                        screenState = ScreenState.Streaming(""),
                        isStreaming = true,
                        streamingText = "",
                        streamingCards = emptyList(),
                        clarifyChips = emptyList(),
                        clarifyQuestion = "",
                        searchStatus = "AI 正在思考…",
                    )
                }
                ttsManager.stop()
                viewModelScope.launch {
                    streamWithRetry(text)
                }
                return
            }
            _uiState.update {
                it.copy(
                    messages = it.messages + userMessage,
                    inputText = "",
                    searchStatus = "",
                    screenState = ScreenState.Content(false),
                    checkoutNavigationRequest = it.checkoutNavigationRequest + 1,
                )
            }
            return
        }

        val userMessage = ChatMessage(
            id = UUID.randomUUID().toString(),
            role = MessageRole.User,
            content = text,
            status = MessageStatus.Sent,
        )

        _uiState.update {
            it.copy(
                messages = it.messages + userMessage,
                inputText = "",
                screenState = ScreenState.Streaming(""),
                isStreaming = true,
                streamingText = "",
                streamingCards = emptyList(),
                clarifyChips = emptyList(),
                clarifyQuestion = "",
                searchStatus = "AI 正在思考…",
            )
        }

        ttsManager.stop()

        viewModelScope.launch {
            userRepo.saveMessage(userMessage, _uiState.value.currentConversationId)
            streamWithRetry(text)
        }
    }

    private suspend fun streamWithRetry(text: String) {
        val maxRetries = 3
        var attempt = 0
        var lastException: Exception? = null

        while (attempt < maxRetries) {
            if (attempt > 0) {
                val delayMs = (1000L * (1 shl (attempt - 1))).coerceAtMost(8000L)
                delay(delayMs)
                _uiState.update { it.copy(searchStatus = "正在重新连接…（第${attempt}次）") }
            }
            attempt++

            try {
                performStream(text)
                return  // success
            } catch (e: java.io.IOException) {
                lastException = e
                // 已收数据 → 不重试，用 H4 的持久化逻辑
                if (_uiState.value.messages.any { it.role == MessageRole.Assistant }) {
                    return
                }
                continue
            } catch (e: Exception) {
                lastException = e
                break  // non-IO errors don't retry
            }
        }

        _uiState.update {
            it.copy(
                searchStatus = "",
                screenState = ScreenState.Error("连接失败，请检查网络后重试"),
                isStreaming = false,
            )
        }
    }

    private suspend fun performStream(text: String) {
        val accText = StringBuilder()
        var ttsLastLength = 0
        val accCards = mutableListOf<Product>()
        val accWebResults = mutableListOf<WebSearchItem>()
        var accCompareDims: List<Map<String, Any?>> = emptyList()
        var streamFailed = false
        val convId = _uiState.value.currentConversationId

        try {
                val isDemoMode = getApplication<Application>()
                    .getSharedPreferences("shopping_theme_prefs", android.content.Context.MODE_PRIVATE)
                    .getBoolean("demo_mode_enabled", false)
                chatRepository.sendMessage(
                    text = text,
                    conversationId = _uiState.value.currentConversationId,
                    cartSessionId = cartSessionId,
                    userId = userRepo.getUserId(),
                    isDemoMode = isDemoMode,
                )
                    .collect { event ->
                        when (event) {
                            is SSEEvent.Progress -> {
                                _uiState.update { it.copy(searchStatus = event.message) }
                            }
                            is SSEEvent.WebSearchResult -> {
                                accWebResults.add(WebSearchItem(
                                    title = event.title,
                                    url = event.url,
                                    snippet = event.snippet,
                                    index = event.index,
                                    total = event.total,
                                ))
                            }
                            is SSEEvent.Compare -> {
                                accCompareDims = event.dimensions
                            }
                            is SSEEvent.Scenario -> Unit  // 场景元数据 — UI 按 category 字段分组渲染
                            is SSEEvent.Clarify -> {
                                _uiState.update {
                                    it.copy(
                                        clarifyQuestion = event.question,
                                        clarifyChips = event.options.ifEmpty {
                                            event.missingSlots.map { s -> "补充$s" }
                                        },
                                        isStreaming = false,
                                        streamingText = "",
                                        searchStatus = "",
                                    )
                                }
                                // 播报反问问题
                                ttsManager.speakFull(event.question)
                            }
                            is SSEEvent.TextDelta -> {
                                accText.append(event.content)
                                val fullText = accText.toString()
                                _uiState.update { it.copy(streamingText = fullText) }
                                val delta = fullText.substring(ttsLastLength)
                                if (delta.isNotBlank()) ttsManager.speak(delta)
                                ttsLastLength = fullText.length
                            }
                            is SSEEvent.ProductCard -> {
                                val product = Product(
                                    productId = event.productId,
                                    title = event.title,
                                    price = event.price,
                                    rating = event.rating.toFloat(),
                                    highlights = event.highlights,
                                    imageUrl = event.imageUrl,
                                    imageUrls = event.imageUrls,
                                    brand = event.brand,
                                    category = event.category,
                                    matchScore = event.matchScore,
                                )
                                accCards.add(product)

                                // 提交当前累积文本 + 此卡片为独立消息（交错格式）
                                val textSoFar = accText.toString().trim()
                                if (textSoFar.isNotEmpty()) {
                                    val (summaryText, productText) = if (event.index == 1) {
                                        splitSummaryFromFirstProduct(textSoFar)
                                    } else {
                                        null to textSoFar
                                    }

                                    if (!summaryText.isNullOrBlank()) {
                                        val dimsForSummary = accCompareDims.toList()
                                        accCompareDims = emptyList()
                                        val summaryMsg = ChatMessage(
                                            id = UUID.randomUUID().toString(),
                                            role = MessageRole.Assistant,
                                            content = summaryText.trim(),
                                            productCards = emptyList(),
                                            compareDimensions = dimsForSummary,
                                            status = MessageStatus.Sent,
                                        )
                                        _uiState.update {
                                            it.copy(messages = it.messages + summaryMsg)
                                        }
                                        userRepo.saveMessage(summaryMsg, convId)
                                    }

                                    val partialMsg = ChatMessage(
                                        id = UUID.randomUUID().toString(),
                                        role = MessageRole.Assistant,
                                        content = productText.trim(),
                                        productCards = listOf(product),
                                        status = MessageStatus.Sent,
                                    )
                                    _uiState.update {
                                        it.copy(
                                            messages = it.messages + partialMsg,
                                            streamingText = "",
                                            streamingCards = emptyList(),
                                        )
                                    }
                                    userRepo.saveMessage(partialMsg, convId)
                                    accText.clear()
                                    ttsLastLength = 0
                                } else {
                                    // 无前置文本：卡片也要落成独立消息，兼容后端“先流文本、后发卡片”的真流式模式。
                                    val cardOnlyMsg = ChatMessage(
                                        id = UUID.randomUUID().toString(),
                                        role = MessageRole.Assistant,
                                        content = "",
                                        productCards = listOf(product),
                                        status = MessageStatus.Sent,
                                    )
                                    _uiState.update {
                                        it.copy(
                                            messages = it.messages + cardOnlyMsg,
                                            streamingCards = emptyList(),
                                        )
                                    }
                                    userRepo.saveMessage(cardOnlyMsg, convId)
                                }
                            }
                            is SSEEvent.Done -> {
                                if (streamFailed) {
                                    _uiState.update {
                                        it.copy(
                                            isStreaming = false,
                                            streamingText = "",
                                            streamingCards = emptyList(),
                                            searchStatus = "",
                                        )
                                    }
                                    return@collect
                                }
                                // 提交剩余文本（如结语），附联网搜索结果
                                val remainingText = accText.toString().trim()
                                val finalWebResults = accWebResults.toList()
                                val finalCompareDims = accCompareDims.toList()
                                if (remainingText.isNotEmpty() || finalWebResults.isNotEmpty() || finalCompareDims.isNotEmpty()) {
                                    val closingMsg = ChatMessage(
                                        id = UUID.randomUUID().toString(),
                                        role = MessageRole.Assistant,
                                        content = remainingText,
                                        productCards = emptyList(),
                                        webSearchResults = finalWebResults,
                                        compareDimensions = finalCompareDims,
                                        status = MessageStatus.Sent,
                                    )
                                    _uiState.update {
                                        it.copy(messages = it.messages + closingMsg)
                                    }
                                    userRepo.saveMessage(closingMsg, convId)
                                }

                                _uiState.update {
                                    it.copy(
                                        isStreaming = false,
                                        streamingText = "",
                                        streamingCards = emptyList(),
                                        searchStatus = "",
                                        screenState = ScreenState.Content(accCards.isNotEmpty()),
                                    )
                                }

                                // 自动设置对话标题（首条用户消息截取）
                                val currentTitle = userRepo.getConversationMetas()
                                    .find { it.id == convId }?.title ?: ""
                                if (currentTitle.isEmpty() || currentTitle == "每日推荐") {
                                    userRepo.updateConversationTitle(convId, text.take(30))
                                }

                                syncCartAfterChatIfNeeded(text)
                                refreshConversationList()

                                // 反选 chips
                                val finalCards = accCards.toList()
                                if (finalCards.isNotEmpty()) {
                                    val brands = finalCards
                                        .mapNotNull { it.brand }
                                        .filter { it.isNotBlank() }
                                        .distinct()
                                        .take(4)
                                    val excludeChips = brands.map { "排除 $it" }
                                    _uiState.update { it.copy(clarifyChips = excludeChips, clarifyQuestion = "") }
                                    // 持久化排除 chips，按对话独立存储
                                    userRepo.setSetting("clarify_chips_$convId", Gson().toJson(excludeChips))
                                } else {
                                    // 无商品返回时清除持久化 chips，避免旧品类排除条件残留
                                    userRepo.setSetting("clarify_chips_$convId", "")
                                }
                            }
                            is SSEEvent.Error -> {
                                streamFailed = true
                                android.util.Log.e("ChatViewModel", "SSE Error: ${event.message}")
                                _uiState.update {
                                    it.copy(
                                        searchStatus = "",
                                        screenState = ScreenState.Error(event.message),
                                        isStreaming = false,
                                    )
                                }
                            }
                            is SSEEvent.VoiceRecognized -> Unit
                        }
                    }
                } catch (e: java.io.IOException) {
                android.util.Log.e("ChatViewModel", "SSE IO error: ${e.message}")

                // 保存已累积但未落盘的数据
                val remainingText = accText.toString().trim()
                val remainingCards = accCards.toList()
                val remainingWebResults = accWebResults.toList()
                if (remainingText.isNotEmpty() || remainingCards.isNotEmpty()) {
                    val partialMsg = ChatMessage(
                        id = UUID.randomUUID().toString(),
                        role = MessageRole.Assistant,
                        content = remainingText,
                        productCards = remainingCards,
                        webSearchResults = remainingWebResults,
                        status = MessageStatus.Sent,
                    )
                    userRepo.saveMessage(partialMsg, convId)
                    _uiState.update { it.copy(messages = it.messages + partialMsg) }
                }
                throw e  // propagate to streamWithRetry for retry
            } catch (e: Exception) {
                android.util.Log.e("ChatViewModel", "SSE exception: ${e.message}", e)

                val remainingText = accText.toString().trim()
                val remainingCards = accCards.toList()
                val remainingWebResults = accWebResults.toList()
                if (remainingText.isNotEmpty() || remainingCards.isNotEmpty()) {
                    val partialMsg = ChatMessage(
                        id = UUID.randomUUID().toString(),
                        role = MessageRole.Assistant,
                        content = remainingText,
                        productCards = remainingCards,
                        webSearchResults = remainingWebResults,
                        status = MessageStatus.Sent,
                    )
                    userRepo.saveMessage(partialMsg, convId)
                    _uiState.update { it.copy(messages = it.messages + partialMsg) }
                }

                _uiState.update {
                    it.copy(
                        searchStatus = "",
                        screenState = ScreenState.Error("网络连接失败，请重试"),
                        isStreaming = false,
                        streamingText = "",
                        streamingCards = emptyList(),
                    )
                }
            }
    }

    private suspend fun syncCartAfterChatIfNeeded(text: String) {
        if (!isCartRelatedText(text)) return
        try {
            withContext(kotlinx.coroutines.Dispatchers.IO) {
                userRepo.syncCartFromBackend(cartSessionId)
            }
            CartEvents.notifyChanged()
        } catch (e: Exception) {
            android.util.Log.w("ChatViewModel", "Cart sync after chat failed: ${e.message}")
        }
    }

    private fun isCartRelatedText(text: String): Boolean {
        val keywords = listOf(
            "购物车", "加购", "加入", "加到", "添加", "放入",
            "删除", "移除", "清空", "数量", "改成", "改为",
            "设为", "设置为", "调整为", "调到", "改到", "加一件", "减一件",
            "下单", "结算", "确认下单"
        )
        return keywords.any { text.contains(it, ignoreCase = true) }
    }

    private fun shouldOpenCheckout(text: String): Boolean {
        val normalized = text.trim()
        val confirmKeywords = listOf("确认下单", "确认", "确定", "是的", "没错", "结算", "下单")
        if (confirmKeywords.none { normalized == it || normalized.contains(it) }) return false
        return _uiState.value.messages
            .asReversed()
            .take(6)
            .any { message ->
                message.role == MessageRole.Assistant &&
                    (message.content.contains("订单确认") ||
                        message.content.contains("输入「确认下单」") ||
                        message.content.contains("合计："))
            }
    }

    fun consumeCheckoutNavigation() {
        _uiState.update { it.copy(checkoutNavigationRequest = 0) }
    }

    fun onClarifyChipClick(chip: String) {
        _uiState.update { it.copy(inputText = chip, clarifyChips = emptyList(), clarifyQuestion = "") }
        viewModelScope.launch {
            delay(50)
            sendMessage()
        }
    }

    fun clearImage() {
        _uiState.update { it.copy(selectedImageUri = null) }
    }

    fun sendVoice(audioFile: File, durationSec: Int) {
        if (_uiState.value.isStreaming) return
        val uploadFile = try {
            AudioCompressor.prepareForUpload(audioFile)
        } catch (e: Exception) {
            _uiState.update { it.copy(screenState = ScreenState.Error(e.message ?: "录音文件不可用")) }
            return
        }

        val userMessage = ChatMessage(
            id = UUID.randomUUID().toString(),
            role = MessageRole.User,
            content = "语音输入",
            audioUri = uploadFile.absolutePath,
            audioDurationSec = durationSec,
            status = MessageStatus.Sent,
        )

        _uiState.update {
            it.copy(
                messages = it.messages + userMessage,
                screenState = ScreenState.Streaming(""),
                isStreaming = true,
                streamingText = "",
                streamingCards = emptyList(),
                clarifyChips = emptyList(),
                clarifyQuestion = "",
                searchStatus = "正在理解语音...",
            )
        }
        ttsManager.stop()

        viewModelScope.launch {
            val convId = _uiState.value.currentConversationId
            val accText = StringBuilder()
            var ttsLastLength = 0
            val accCards = mutableListOf<Product>()
            val accWebResults = mutableListOf<WebSearchItem>()
            var accCompareDims: List<Map<String, Any?>> = emptyList()
            var streamFailed = false
            var recognizedText = ""
            var persistedUserMessage = userMessage
            userRepo.saveMessage(persistedUserMessage, convId)

            try {
                chatRepository.sendVoice(
                    audioFile = uploadFile,
                    conversationId = convId,
                    cartSessionId = cartSessionId,
                    userId = userRepo.getUserId(),
                ).collect { event ->
                    when (event) {
                        is SSEEvent.Progress -> {
                            _uiState.update { it.copy(searchStatus = event.message) }
                        }
                        is SSEEvent.VoiceRecognized -> {
                            recognizedText = event.text
                            if (event.text.isNotBlank()) {
                                persistedUserMessage = persistedUserMessage.copy(content = event.text)
                                userRepo.saveMessage(persistedUserMessage, convId)
                            }
                            _uiState.update {
                                it.copy(
                                    searchStatus = if (event.text.isNotBlank()) "已识别：${event.text}" else "正在检索商品...",
                                    messages = it.messages.map { msg ->
                                        if (msg.id == userMessage.id && event.text.isNotBlank()) {
                                            msg.copy(content = event.text)
                                        } else {
                                            msg
                                        }
                                    },
                                )
                            }
                        }
                        is SSEEvent.TextDelta -> {
                            accText.append(event.content)
                            val fullText = accText.toString()
                            _uiState.update { it.copy(streamingText = fullText) }
                            val delta = fullText.substring(ttsLastLength)
                            if (delta.isNotBlank()) ttsManager.speak(delta)
                            ttsLastLength = fullText.length
                        }
                        is SSEEvent.ProductCard -> {
                            val product = Product(
                                productId = event.productId,
                                title = event.title,
                                price = event.price,
                                rating = event.rating.toFloat(),
                                highlights = event.highlights,
                                imageUrl = event.imageUrl,
                                imageUrls = event.imageUrls,
                                brand = event.brand,
                                category = event.category,
                                matchScore = event.matchScore,
                            )
                            accCards.add(product)
                            _uiState.update { it.copy(streamingCards = accCards.toList()) }
                        }
                        is SSEEvent.WebSearchResult -> {
                            accWebResults.add(
                                WebSearchItem(
                                    title = event.title,
                                    url = event.url,
                                    snippet = event.snippet,
                                    index = event.index,
                                    total = event.total,
                                )
                            )
                        }
                        is SSEEvent.Compare -> {
                            accCompareDims = event.dimensions
                        }
                        is SSEEvent.Scenario -> Unit  // 场景元数据
                        is SSEEvent.Clarify -> {
                            _uiState.update {
                                it.copy(
                                    clarifyQuestion = event.question,
                                    clarifyChips = event.options.ifEmpty {
                                        event.missingSlots.map { slot -> "补充$slot" }
                                    },
                                    isStreaming = false,
                                    streamingText = "",
                                    streamingCards = emptyList(),
                                    searchStatus = "",
                                )
                            }
                            ttsManager.speakFull(event.question)
                        }
                        is SSEEvent.Done -> {
                            if (streamFailed) {
                                _uiState.update {
                                    it.copy(
                                        isStreaming = false,
                                        streamingText = "",
                                        streamingCards = emptyList(),
                                        searchStatus = "",
                                    )
                                }
                                return@collect
                            }
                            val finalText = accText.toString().trim()
                            val finalCards = accCards.toList()
                            val finalWebResults = accWebResults.toList()
                            val finalCompareDims = accCompareDims.toList()
                            if (
                                finalText.isNotEmpty() ||
                                finalCards.isNotEmpty() ||
                                finalWebResults.isNotEmpty() ||
                                finalCompareDims.isNotEmpty()
                            ) {
                                val assistantMessage = ChatMessage(
                                    id = UUID.randomUUID().toString(),
                                    role = MessageRole.Assistant,
                                    content = finalText,
                                    productCards = finalCards,
                                    webSearchResults = finalWebResults,
                                    compareDimensions = finalCompareDims,
                                    status = MessageStatus.Sent,
                                )
                                userRepo.saveMessage(assistantMessage, convId)
                                _uiState.update { it.copy(messages = it.messages + assistantMessage) }
                            }
                            _uiState.update {
                                it.copy(
                                    isStreaming = false,
                                    streamingText = "",
                                    streamingCards = emptyList(),
                                    searchStatus = "",
                                    screenState = ScreenState.Content(
                                        finalCards.isNotEmpty() ||
                                            finalWebResults.isNotEmpty() ||
                                            finalCompareDims.isNotEmpty()
                                    ),
                                )
                            }
                            val titleText = recognizedText.ifBlank { "语音导购" }
                            val currentTitle = userRepo.getConversationMetas().find { it.id == convId }?.title ?: ""
                            if (currentTitle.isEmpty() || currentTitle == "每日推荐") {
                                userRepo.updateConversationTitle(convId, titleText.take(30))
                            }
                            syncCartAfterChatIfNeeded(recognizedText)
                            refreshConversationList()
                        }
                        is SSEEvent.Error -> {
                            streamFailed = true
                            _uiState.update {
                                it.copy(
                                    searchStatus = "",
                                    screenState = ScreenState.Error(event.message),
                                    isStreaming = false,
                                    streamingText = "",
                                    streamingCards = emptyList(),
                                )
                            }
                        }
                    }
                }
            } catch (e: Exception) {
                android.util.Log.e("ChatViewModel", "Voice SSE exception: ${e.message}", e)
                _uiState.update {
                    it.copy(
                        searchStatus = "",
                        screenState = ScreenState.Error("语音导购失败，请重试"),
                        isStreaming = false,
                        streamingText = "",
                        streamingCards = emptyList(),
                    )
                }
            }
        }
    }

    fun retryLastMessage() {
        val lastUserMsg = _uiState.value.messages.lastOrNull { it.role == MessageRole.User }
        if (lastUserMsg != null) {
            _uiState.update { it.copy(inputText = lastUserMsg.content) }
            sendMessage()
        }
    }

    // ── 拍照找货 ──────────────────────────────────────────

    fun sendImage(imageFile: File) {
        val userMessage = ChatMessage(
            id = UUID.randomUUID().toString(),
            role = MessageRole.User,
            content = "📷 拍照找货",
            status = MessageStatus.Sent,
        )

        _uiState.update {
            it.copy(
                messages = it.messages + userMessage,
                screenState = ScreenState.Streaming(""),
                isStreaming = true,
                streamingText = "",
                streamingCards = emptyList(),
                searchStatus = "📷 正在识别图片，请稍候…",
            )
        }

        ttsManager.stop()

        viewModelScope.launch {
            val accText = StringBuilder()
            var ttsLastLength = 0
            val accCards = mutableListOf<Product>()
            val convId = _uiState.value.currentConversationId

            // 持久化用户消息，避免异常中断时丢失
            userRepo.saveMessage(userMessage, convId)

            try {
                visionClient.connectVision(imageFile)
                    .collect { event ->
                        when (event) {
                            is SSEEvent.Progress -> {
                                accText.append(event.message).append("\n")
                                val fullText = accText.toString()
                                _uiState.update {
                                    it.copy(
                                        searchStatus = event.message,
                                        streamingText = fullText
                                    )
                                }
                                val delta = fullText.substring(ttsLastLength)
                                if (delta.isNotBlank()) ttsManager.speak(delta)
                                ttsLastLength = fullText.length
                            }
                            is SSEEvent.ProductCard -> {
                                val product = Product(
                                    productId = event.productId,
                                    title = event.title,
                                    price = event.price,
                                    rating = event.rating.toFloat(),
                                    highlights = event.highlights,
                                    imageUrl = event.imageUrl,
                                    imageUrls = event.imageUrls,
                                    brand = event.brand,
                                    category = event.category,
                                    matchScore = event.matchScore,
                                )
                                accCards.add(product)
                                _uiState.update { it.copy(streamingCards = accCards.toList()) }
                            }
                            is SSEEvent.Scenario -> Unit  // 场景元数据
                            is SSEEvent.Done -> {
                                val finalText = accText.toString().ifBlank {
                                    "根据图片找到 ${event.totalCards} 件相似商品"
                                }
                                val finalCards = accCards.toList()

                                val aiMessage = ChatMessage(
                                    id = UUID.randomUUID().toString(),
                                    role = MessageRole.Assistant,
                                    content = finalText,
                                    productCards = finalCards,
                                    status = MessageStatus.Sent,
                                )
                                _uiState.update {
                                    it.copy(
                                        messages = it.messages + aiMessage,
                                        isStreaming = false,
                                        streamingText = "",
                                        streamingCards = emptyList(),
                                        searchStatus = "",
                                        screenState = ScreenState.Content(finalCards.isNotEmpty()),
                                    )
                                }

                                // 持久化
                                userRepo.saveMessage(aiMessage, convId)
                                val currentTitle = userRepo.getConversationMetas()
                                    .find { it.id == convId }?.title ?: ""
                                if (currentTitle.isEmpty()) {
                                    userRepo.updateConversationTitle(convId, "拍照找货")
                                }
                                refreshConversationList()
                            }
                            is SSEEvent.Error -> {
                                android.util.Log.e("ChatViewModel", "SSE Error: ${event.message}")
                                _uiState.update {
                                    it.copy(
                                        searchStatus = "",
                                        screenState = ScreenState.Error(event.message),
                                        isStreaming = false,
                                    )
                                }
                            }
                            else -> {}
                        }
                    }
            } catch (e: Exception) {
                android.util.Log.e("ChatViewModel", "Vision SSE exception: ${e.message}", e)

                val remainingText = accText.toString().trim()
                val remainingCards = accCards.toList()
                if (remainingText.isNotEmpty() || remainingCards.isNotEmpty()) {
                    val partialMsg = ChatMessage(
                        id = UUID.randomUUID().toString(),
                        role = MessageRole.Assistant,
                        content = remainingText.ifEmpty { "图片识别中断" },
                        productCards = remainingCards,
                        status = MessageStatus.Sent,
                    )
                    userRepo.saveMessage(partialMsg, convId)
                    _uiState.update { it.copy(messages = it.messages + partialMsg) }
                }

                _uiState.update {
                    it.copy(
                        searchStatus = "",
                        screenState = ScreenState.Error("拍照找货失败，请重试"),
                        isStreaming = false,
                        streamingText = "",
                        streamingCards = emptyList(),
                    )
                }
            }
        }
    }
}

private fun splitSummaryFromFirstProduct(text: String): Pair<String?, String> {
    val trimmed = text.trim()
    val firstSentenceEnd = trimmed.indexOfFirst { it == '。' || it == '！' || it == '？' }
    if (firstSentenceEnd < 0 || firstSentenceEnd >= trimmed.lastIndex) {
        return null to trimmed
    }

    val summary = trimmed.substring(0, firstSentenceEnd + 1).trim()
    val productText = trimmed.substring(firstSentenceEnd + 1).trim()
    return if (summary.isBlank() || productText.isBlank()) {
        null to trimmed
    } else {
        summary to productText
    }
}
