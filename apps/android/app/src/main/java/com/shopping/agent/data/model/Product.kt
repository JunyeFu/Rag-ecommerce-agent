package com.shopping.agent.data.model

/**
 * 统一商品模型 - 对齐 DATA-CONTRACT.md v1.0 §1.2
 *
 * 与后端 ProductRecord 一一映射。字段命名 camelCase (Kotlin 规范)。
 */
data class Product(
    // 标识
    val productId: String,              // -> product_id

    // 基本信息
    val title: String,                  // -> title
    val brand: String?,                 // -> brand
    val category: String = "",          // -> category

    // 价格
    val price: Double,                  // -> price

    // 评价
    val rating: Float = 3.0f,           // -> rating
    val ratingCount: Int = 0,           // -> rating_count

    // 描述
    val highlights: List<String> = emptyList(),  // -> highlights
    val attributes: Map<String, String> = emptyMap(), // -> attributes
    val scenarios: List<String> = emptyList(),  // -> scenarios

    // 多媒体
    val imageUrl: String? = null,       // -> image_url
    val imageUrls: List<String> = emptyList(),  // -> image_urls

    // 来源
    val source: String = "",            // -> source

    // 检索元数据
    val matchScore: Double = 0.0,       // -> match_score
    val rankReason: String = "",        // -> rank_reason

    // F7 引用标注 - 后端 ProductCardEvent.citation
    val citation: List<Citation> = emptyList(),
)

/**
 * F7 引用来源 - 对齐后端 ProductCardEvent.citation[]。
 *
 * source_type: semantic_retrieval | product_highlights | keyword_match | ...
 * description: 人类可读的引用说明，如"向量检索匹配度 85%"
 */
data class Citation(
    val sourceType: String = "",
    val description: String = "",
)
