package com.shopping.agent.data.model

/**
 * SSE 事件类型 — 与后端 /api/v1/chat SSE 协议对齐。
 *
 * 后端事件:
 *   text_delta   → 流式文本增量（逐 token）
 *   product_cards → 单张推荐商品卡片（逐张推送）
 *   progress     → 流水线进度提示
 *   done         → 流结束
 *   error        → 错误
 */
sealed class SSEEvent {
    data class TextDelta(val delta: String, val content: String = "") : SSEEvent()
    
    data class ProductCard(
        val productId: String,
        val title: String,
        val price: Double,
        val rating: Double,
        val matchScore: Double,
        val highlights: List<String>,
        val imageUrl: String?,
        val imageUrls: List<String>,
        val brand: String?,
        val category: String,
        val index: Int,
        val total: Int,
        val citation: List<Citation> = emptyList()
    ) : SSEEvent()
    
    data class Progress(val message: String) : SSEEvent()
    data class VoiceRecognized(val text: String, val provider: String = "") : SSEEvent()
    
    data class Done(
        val sessionId: String = "",
        val totalCards: Int = 0,
        val latencyMs: Int = 0,
        val slots: Map<String, Any> = emptyMap()
    ) : SSEEvent()
    
    data class Error(val message: String) : SSEEvent()

    data class Clarify(
        val question: String,
        val missingSlots: List<String>,
        val options: List<String>
    ) : SSEEvent()

    data class WebSearchResult(
        val title: String,
        val url: String,
        val snippet: String,
        val index: Int,
        val total: Int
    ) : SSEEvent()

    data class Compare(
        val dimensions: List<Map<String, Any?>>
    ) : SSEEvent()

    data class Scenario(
        val scenario: String,
        val subQueries: List<String>,
        val categoryGroups: List<String>,
        val totalProducts: Int
    ) : SSEEvent()
}

// ── JSON payload 映射（仅 SseClient 内部解析用） ──

data class TextDeltaPayload(val content: String)

data class ProductCardPayload(
    val product_id: String,
    val title: String,
    val price: Double,
    val rating: Double,
    val match_score: Double,
    val highlights: List<String>?,
    val image_url: String?,
    val image_urls: List<String>?,
    val brand: String?,
    val category: String?,
    val index: Int,
    val total: Int,
    val citation: List<CitationPayload>? = null
)

data class CitationPayload(
    val source_type: String = "",
    val description: String = ""
)

data class ProgressPayload(val message: String)

data class DonePayload(
    val total_cards: Int,
    val latency_ms: Int,
    val message: String?,
    val slots: Map<String, Any>?
)

data class ErrorPayload(val message: String, val code: String?)

data class ClarifyPayload(
    val question: String,
    val missing_slots: List<String>?,
    val options: List<String>?
)

data class WebSearchResultPayload(
    val title: String,
    val url: String,
    val snippet: String,
    val index: Int,
    val total: Int
)

data class ScenarioPayload(
    val scenario: String,
    val sub_queries: List<String>?,
    val category_groups: List<String>?,
    val total_products: Int
)
