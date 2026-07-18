package com.shopping.agent.data.remote

import com.google.gson.Gson
import com.shopping.agent.core.network.NetworkConfig
import com.shopping.agent.data.model.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.FlowCollector
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * 真实 SSE 客户端。
 *
 * connect(): POST /api/v1/chat (JSON → SSE 流)
 * connectVision(): POST /api/v1/upload/vision-search (multipart → SSE 流)
 */
class SseClient(
    private val baseUrl: String = NetworkConfig.BASE_URL
) {
    private val client = NetworkConfig.sseClient
    private val gson = Gson()

    // ── 文本聊天 ──────────────────────────────────────────

    fun connect(
        message: String,
        conversationId: String? = null,
        cartSessionId: String? = null,
        userId: String = "",
    ): Flow<SSEEvent> = flow {
        val json = JSONObject().apply {
            put("message", message)
            conversationId?.let { put("conversation_id", it) }
            cartSessionId?.takeIf { it.isNotBlank() }?.let { put("cart_session_id", it) }
            if (userId.isNotBlank()) put("user_id", userId)
        }

        val requestBody = json.toString()
            .toRequestBody("application/json".toMediaType())

        val request = Request.Builder()
            .url("$baseUrl/api/v1/chat")
            .post(requestBody)
            .header("Accept", "text/event-stream")
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                emit(SSEEvent.Error("HTTP ${response.code}: ${response.message}"))
                return@flow
            }
            parseStream(response, conversationId)
        }
    }.flowOn(Dispatchers.IO)

    // ── 拍照找货 ──────────────────────────────────────────

    /**
     * 上传图片进行视觉搜索。
     * @param imageFile 图片文件（JPEG/PNG）
     * @return SSE 事件流: vision_parsed → product_cards → done
     */
    fun connectVision(imageFile: File): Flow<SSEEvent> = flow {
        val requestBody = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart(
                "file", imageFile.name,
                imageFile.asRequestBody("image/*".toMediaType())
            )
            .build()

        val request = Request.Builder()
            .url("$baseUrl/api/v1/upload/vision-search")
            .post(requestBody)
            .header("Accept", "text/event-stream")
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                emit(SSEEvent.Error("HTTP ${response.code}: ${response.message}"))
                return@flow
            }
            parseStream(response = response, convId = null, isVision = true)
        }
    }.flowOn(Dispatchers.IO)

    fun connectVoice(
        audioFile: File,
        conversationId: String? = null,
        cartSessionId: String? = null,
        userId: String = "",
    ): Flow<SSEEvent> = flow {
        val builder = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart(
                "file",
                audioFile.name,
                audioFile.asRequestBody("audio/mp4".toMediaType()),
            )
        conversationId?.let { builder.addFormDataPart("conversation_id", it) }
        cartSessionId?.takeIf { it.isNotBlank() }?.let { builder.addFormDataPart("cart_session_id", it) }
        if (userId.isNotBlank()) builder.addFormDataPart("user_id", userId)

        val request = Request.Builder()
            .url("$baseUrl/api/v1/voice/chat")
            .post(builder.build())
            .header("Accept", "text/event-stream")
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                emit(SSEEvent.Error("HTTP ${response.code}: ${response.message}"))
                return@flow
            }
            parseStream(response = response, convId = conversationId)
        }
    }.flowOn(Dispatchers.IO)

    // ── SSE 流解析 ────────────────────────────────────────

    private suspend fun FlowCollector<SSEEvent>.parseStream(
        response: okhttp3.Response,
        convId: String?,
        isVision: Boolean = false
    ) {
        val source = response.body!!.source()
        var eventType = ""
        val dataBuilder = StringBuilder()

        try {
            while (!source.exhausted()) {
                val line = source.readUtf8Line() ?: break

                when {
                    line.startsWith("event: ") ->
                        eventType = line.removePrefix("event: ").trim()

                    line.startsWith("data: ") ->
                        dataBuilder.append(line.removePrefix("data: "))

                    line.isEmpty() && dataBuilder.isNotEmpty() -> {
                        val jsonStr = dataBuilder.toString()
                        dataBuilder.clear()

                        // vision-search 用 data-only 格式，从 JSON type 推断事件类型
                        val effectiveType = if (isVision && eventType.isEmpty()) {
                            inferVisionEventType(jsonStr)
                        } else {
                            eventType
                        }

                        val event = parseSseEvent(effectiveType, jsonStr, convId)
                        if (event != null) emit(event)

                        if (eventType == "error" || eventType == "done") break
                    }
                }
            }
        } finally {
            response.close()
        }
    }

    private fun inferVisionEventType(json: String): String {
        return try {
            val node = gson.fromJson(json, com.google.gson.JsonObject::class.java)
            val type = node.get("type")?.asString ?: ""
            when {
                type == "vision_parsed" -> "progress"  // 映射为 progress 在 UI 显示
                type == "product_cards" -> "product_cards"
                type == "done" -> "done"
                type == "error" -> "error"
                else -> "unknown"
            }
        } catch (e: Exception) {
            "unknown"
        }
    }

    private fun parseSseEvent(type: String, json: String, convId: String?): SSEEvent? {
        return try {
            when (type) {
                "text_delta" -> {
                    val d = gson.fromJson(json, TextDeltaPayload::class.java)
                    SSEEvent.TextDelta(delta = d.content, content = d.content)
                }
                "product_cards" -> {
                    val d = gson.fromJson(json, ProductCardPayload::class.java)
                    SSEEvent.ProductCard(
                        productId = d.product_id,
                        title = d.title,
                        price = d.price,
                        rating = d.rating,
                        matchScore = d.match_score,
                        highlights = d.highlights ?: emptyList(),
                        imageUrl = NetworkConfig.resolveImageUrl(d.image_url),
                        imageUrls = NetworkConfig.resolveImageUrls(d.image_urls ?: emptyList()),
                        brand = d.brand,
                        category = d.category ?: "",
                        index = d.index,
                        total = d.total,
                        citation = d.citation?.map { Citation(it.source_type, it.description) } ?: emptyList()
                    )
                }
                "progress" -> {
                    val node = gson.fromJson(json, com.google.gson.JsonObject::class.java)
                    val msg = if (node.has("product_info")) {
                        // vision-search 的 vision_parsed 事件
                        val pi = node.getAsJsonObject("product_info")
                        val name = pi?.get("product_name")?.asString ?: ""
                        val desc = pi?.get("description")?.asString ?: ""
                        if (name.isNotEmpty()) "图片识别: $name"
                        else if (desc.isNotEmpty()) "图片识别: $desc"
                        else "图片已识别，正在检索..."
                    } else {
                        // text chat progress — 直接取 message 字段
                        node.get("message")?.asString ?: ""
                    }
                    SSEEvent.Progress(msg)
                }
                "voice_recognized" -> {
                    val node = gson.fromJson(json, com.google.gson.JsonObject::class.java)
                    SSEEvent.VoiceRecognized(
                        text = node.get("text")?.asString ?: "",
                        provider = node.get("provider")?.asString ?: "",
                    )
                }
                "done" -> {
                    val d = gson.fromJson(json, DonePayload::class.java)
                    SSEEvent.Done(
                        sessionId = convId ?: "",
                        totalCards = d.total_cards,
                        latencyMs = d.latency_ms,
                        slots = d.slots ?: emptyMap()
                    )
                }
                "clarify" -> {
                    val d = gson.fromJson(json, ClarifyPayload::class.java)
                    SSEEvent.Clarify(
                        question = d.question,
                        missingSlots = d.missing_slots ?: emptyList(),
                        options = d.options ?: emptyList()
                    )
                }
                "web_search_result" -> {
                    val d = gson.fromJson(json, WebSearchResultPayload::class.java)
                    SSEEvent.WebSearchResult(
                        title = d.title,
                        url = d.url,
                        snippet = d.snippet,
                        index = d.index,
                        total = d.total
                    )
                }
                "compare" -> {
                    val node = gson.fromJson(json, com.google.gson.JsonObject::class.java)
                    val dims = node.getAsJsonArray("dimensions")
                    @Suppress("UNCHECKED_CAST")
                    val dimList = if (dims != null) {
                        gson.fromJson(dims, List::class.java) as List<Map<String, Any?>>
                    } else emptyList()
                    SSEEvent.Compare(dimensions = dimList)
                }
                "scenario" -> {
                    val d = gson.fromJson(json, ScenarioPayload::class.java)
                    SSEEvent.Scenario(
                        scenario = d.scenario,
                        subQueries = d.sub_queries ?: emptyList(),
                        categoryGroups = d.category_groups ?: emptyList(),
                        totalProducts = d.total_products
                    )
                }
                "error" -> {
                    val d = gson.fromJson(json, ErrorPayload::class.java)
                    SSEEvent.Error(d.message)
                }
                else -> null  // 忽略未知事件
            }
        } catch (e: Exception) {
            SSEEvent.Error("SSE parse error [${type}]: ${e.message}")
        }
    }
}

// vision-search 特殊载荷
data class VisionParsedPayload(
    val type: String?,
    val product_info: Map<String, Any?>?
)
