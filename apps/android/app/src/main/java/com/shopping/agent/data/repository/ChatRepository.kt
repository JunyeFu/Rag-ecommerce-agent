package com.shopping.agent.data.repository

import com.shopping.agent.data.model.ChatMessage
import com.shopping.agent.data.model.MessageRole
import com.shopping.agent.data.model.SSEEvent
import com.shopping.agent.data.mock.DemoStreamProvider
import com.shopping.agent.data.remote.SseClient
import kotlinx.coroutines.flow.Flow
import java.io.File
import java.util.UUID

class ChatRepository {
    private val sseClient = SseClient()
    private val _messages = mutableListOf<ChatMessage>()
    val messages: List<ChatMessage> get() = _messages.toList()

    fun sendMessage(
        text: String,
        conversationId: String? = null,
        cartSessionId: String? = null,
        userId: String = "",
        isDemoMode: Boolean = false,
    ): Flow<SSEEvent> {
        _messages.add(ChatMessage(
            id = UUID.randomUUID().toString(),
            role = MessageRole.User,
            content = text,
        ))
        return if (isDemoMode) {
            DemoStreamProvider.mockStream(text, conversationId ?: "demo")
        } else {
            sseClient.connect(text, conversationId, cartSessionId, userId)
        }
    }

    fun addAssistantMessage(content: String, products: List<com.shopping.agent.data.model.Product> = emptyList()) {
        _messages.add(ChatMessage(
            id = UUID.randomUUID().toString(),
            role = MessageRole.Assistant,
            content = content,
            productCards = products,
        ))
    }

    fun sendVoice(
        audioFile: File,
        conversationId: String? = null,
        cartSessionId: String? = null,
        userId: String = "",
    ): Flow<SSEEvent> = sseClient.connectVoice(audioFile, conversationId, cartSessionId, userId)

    fun clearMessages() {
        _messages.clear()
    }
}
