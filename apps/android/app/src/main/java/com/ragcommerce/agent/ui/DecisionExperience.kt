package com.ragcommerce.agent.ui

fun constraintVerdict(product: EvidenceProductUi, mission: ShoppingMissionUi?): String {
    if (product.unmetConstraints.isNotEmpty()) return "${product.unmetConstraints.size} 项未满足"
    val required = mission?.hardConstraints.orEmpty()
    if (required.isEmpty()) return "未设置硬约束"
    val unknown = required.count { it !in product.matchedConstraints }
    return if (unknown > 0) "$unknown 项待核实" else "${required.size} 项已核实满足"
}

fun approvalTargetSummary(tool: String, arguments: Map<String, String>, state: ShoppingUiState): String? {
    val products = state.products
    return when (tool) {
        "cart.update", "link.resolve" -> {
            val offer = state.cartGroups.flatMap { it.offers }.firstOrNull { it.id == arguments["offer_id"] } ?: return null
            val product = products.firstOrNull { it.id == offer.productId } ?: return null
            if (tool == "link.resolve") "${product.title} · ${offer.merchantName}"
            else "${product.title} · ${when (arguments["operation"]) { "remove" -> "移除"; "add" -> "增加"; "set" -> "数量改为"; else -> return null }} ${arguments["quantity"] ?: return null} 件"
        }
        "list.update" -> {
            val product = products.firstOrNull { it.variantId == arguments["variant_id"] } ?: return null
            "${product.title} · ${when (arguments["operation"]) { "add" -> "加入保存"; "remove" -> "移出保存"; else -> return null }}"
        }
        "vision.identify" -> "读取本次发送的图片"
        "audio.transcribe" -> "转写本次发送的录音"
        else -> null
    }
}
