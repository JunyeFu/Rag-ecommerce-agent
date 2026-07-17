package com.shopping.agent.data.mock

import com.shopping.agent.data.model.SSEEvent
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

/**
 * 演示模式 SSE 事件流提供者。
 *
 * 断网或无需后端时，从本地 MockProducts 中关键词匹配商品，
 * 模拟真实 SSE 时序：progress → text_delta → product_cards → done。
 */
object DemoStreamProvider {

    fun mockStream(query: String, conversationId: String): Flow<SSEEvent> = flow {
        // 1. 流水线进度
        emit(SSEEvent.Progress("[演示模式] 正在分析您的需求..."))
        delay(300)

        // 2. 意图理解完成
        emit(SSEEvent.TextDelta("收到，我马上帮您找找。\n\n"))
        delay(200)

        // 3. 检索中
        emit(SSEEvent.Progress("[演示模式] 已理解需求，正在检索商品..."))
        delay(400)

        // 4. 关键词匹配 MockProducts
        val matched = matchProducts(query)
        if (matched.isNotEmpty()) {
            emit(SSEEvent.TextDelta("[演示模式] 为您找到 ${matched.size} 款相关商品：\n\n"))
            delay(200)

            matched.forEachIndexed { index, product ->
                emit(
                    SSEEvent.ProductCard(
                        productId = product.productId,
                        title = product.title,
                        price = product.price,
                        rating = product.rating.toDouble(),
                        matchScore = 0.85 - index * 0.05,
                        highlights = product.highlights.take(3),
                        imageUrl = product.imageUrl,
                        imageUrls = product.imageUrls,
                        brand = product.brand,
                        category = product.category,
                        index = index + 1,
                        total = matched.size,
                    )
                )
                delay(300)
            }
        } else {
            emit(SSEEvent.TextDelta("[演示模式] 没有找到完全匹配的商品，试试\"推荐手机\"或\"降噪耳机\"？\n"))
        }

        // 5. 结束
        emit(
            SSEEvent.Done(
                sessionId = conversationId,
                totalCards = matched.size,
                latencyMs = 0,
            )
        )
    }

    private fun matchProducts(query: String): List<com.shopping.agent.data.model.Product> {
        val q = query.lowercase()
        // 提取查询中的关键词：品类、品牌、属性
        return mockProducts.filter { product ->
            val haystack = buildString {
                append(product.title.lowercase())
                append(" ")
                append(product.category.lowercase())
                append(" ")
                append((product.brand ?: "").lowercase())
                append(" ")
                append(product.highlights.joinToString(" ").lowercase())
                append(" ")
                append(product.rankReason.lowercase())
            }
            // 分词匹配：至少匹配一个关键词
            q.split(" ", "，", "、", "的", "了", "吗", "吧", "推荐", "一款", "哪些", "有没有")
                .filter { it.length >= 2 }
                .any { keyword -> keyword in haystack }
        }.take(5)
    }
}
