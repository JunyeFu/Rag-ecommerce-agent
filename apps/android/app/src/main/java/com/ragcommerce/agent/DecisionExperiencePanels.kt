package com.ragcommerce.agent

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.ragcommerce.agent.generated.ThreadHistoryEntry
import com.ragcommerce.agent.ui.*

@Composable
internal fun DecisionExperienceDialogs(state: ShoppingUiState, onAction: (ShoppingAction) -> Unit, onAddOffer: (OfferUi) -> Unit) {
    if (state.historyVisible) {
        var showArchived by remember { mutableStateOf(false) }
        var editing by remember { mutableStateOf<ThreadHistoryEntry?>(null) }
        var title by remember { mutableStateOf("") }
        var archive by remember { mutableStateOf<Boolean?>(null) }
        AlertDialog(onDismissRequest = { onAction(ShoppingAction.CloseHistory) }, title = { Text("最近任务") }, text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("任务分别保留约束、推荐和审批，不自动继承偏好。")
                Row { Checkbox(showArchived, { showArchived = it }, modifier = Modifier.testTag("history_archived").semantics { contentDescription = "查看已归档任务" }); Text("查看已归档任务") }
                editing?.let { item ->
                    Text(item.experience.title ?: item.goal, fontWeight = FontWeight.Bold)
                    if (archive == null) OutlinedTextField(title, { title = it.take(80) }, label = { Text("任务名称") }, modifier = Modifier.testTag("history_title_input"))
                    else Text(if (archive == true) "归档只整理列表，不删除任务和业务数据。" else "恢复到最近任务列表。")
                    Button(onClick = { onAction(ShoppingAction.OrganizeHistory(item.thread_id, title.takeIf { archive == null }, archive)); editing = null },
                        enabled = !state.decisionBusy && (archive != null || title.isNotBlank())) { Text("确认保存") }
                    TextButton(onClick = { editing = null }) { Text("取消修改") }
                } ?: LazyColumn(Modifier.heightIn(max = 420.dp).testTag("task_history_list"), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    val visible = state.history.filter { it.experience.archived == showArchived }
                    if (visible.isEmpty()) item { Text("这里还没有任务。") }
                    items(visible, key = { it.thread_id }) { item ->
                        Column(Modifier.fillMaxWidth().background(DesignTokens.Bone).padding(12.dp).testTag("history_${item.thread_id}")) {
                            Text(item.experience.title ?: item.goal, fontWeight = FontWeight.Bold)
                            Text(if (item.mode == "DISCOVERY") "探索任务" else "选购任务")
                            Button(onClick = { onAction(ShoppingAction.OpenHistory(item.thread_id)) }, enabled = !state.decisionBusy) { Text("继续任务") }
                            Row {
                                TextButton(onClick = { editing = item; title = item.experience.title ?: item.goal.take(80); archive = null }) { Text("命名") }
                                TextButton(onClick = { editing = item; archive = !item.experience.archived }) { Text(if (item.experience.archived) "移回最近" else "归档") }
                            }
                        }
                    }
                }
            }
        }, confirmButton = { TextButton(onClick = { onAction(ShoppingAction.CloseHistory) }) { Text("关闭") } })
    }
    if (state.conversationVisible) AlertDialog(onDismissRequest = { onAction(ShoppingAction.CloseConversation) }, title = { Text("本次完整对话") }, text = {
        LazyColumn(Modifier.heightIn(max = 480.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (state.conversationMessages.isEmpty()) item { Text("本次还没有已保存的公开对话。") }
            items(state.conversationMessages) { message ->
                Column { Text(when (message.role) { "user" -> "你"; "assistant" -> "导购助手"; else -> "操作记录" }, fontWeight = FontWeight.Bold); Text(message.text) }
            }
            if (state.conversationHasMore) item { TextButton(onClick = { onAction(ShoppingAction.MoreConversation) }, enabled = !state.decisionBusy) { Text("继续加载对话") } }
        }
    }, confirmButton = { TextButton(onClick = { onAction(ShoppingAction.CloseConversation) }) { Text("返回任务") } })
    state.savedDetail?.let { product ->
        var removing by remember(product.id) { mutableStateOf(false) }
        AlertDialog(onDismissRequest = { onAction(ShoppingAction.CloseSaved) }, title = { Text(product.title) }, text = {
            LazyColumn(Modifier.heightIn(max = 430.dp).testTag("saved_detail_list"), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item { Text("目录商品 · 演示报价，非实时商家信息") }
                items(product.attributes.entries.toList()) { (key, value) -> Text("$key · $value") }
                item { Text("来源依据 · ${product.evidenceRefs.joinToString("、")}") }
                if (removing) item {
                    Text("确认将这款商品移出保存？不影响待购或其他任务。")
                    Button(onClick = { onAction(ShoppingAction.RemoveSaved(product.id)) }, enabled = !state.decisionBusy) { Text("确认移出保存") }
                    TextButton(onClick = { removing = false }) { Text("暂不移除") }
                } else {
                    item { Button(onClick = { onAction(ShoppingAction.ContinueSaved(product)) }) { Text("新建任务继续选购") } }
                    items(state.savedDetailOffers) { offer ->
                        Text("${offer.priceText ?: "价格未知"} · 演示报价 · ${if (offer.quoteState == QuoteState.EXPIRED) "已过期" else "有效至 ${offer.expiresAt}"}")
                        Button(onClick = { onAction(ShoppingAction.CloseSaved); onAddOffer(offer) }, enabled = offer.quoteState == QuoteState.CURRENT) { Text("加入待购") }
                    }
                    item { TextButton(onClick = { removing = true }) { Text("移出保存") } }
                }
            }
        }, confirmButton = { TextButton(onClick = { onAction(ShoppingAction.CloseSaved) }) { Text("关闭") } })
    }
}

@Composable
internal fun CandidateDiscussionDialog(product: EvidenceProductUi, onAction: (ShoppingAction) -> Unit, onClose: () -> Unit) {
    var excluding by remember { mutableStateOf(false) }
    var wholeCategory by remember { mutableStateOf(false) }
    var text by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = onClose, title = { Text("继续聊这款") }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(product.title, fontWeight = FontWeight.Bold)
            Row { Checkbox(excluding, { excluding = it }, modifier = Modifier.testTag("candidate_exclude").semantics { contentDescription = "暂时不推荐这款，记录原因" }); Text("暂时不推荐，记录原因") }
            OutlinedTextField(text, { text = it.take(200) }, label = { Text(if (excluding) "例如：太重，但仍需要长续航" else "想问它是否适合什么用途？") }, modifier = Modifier.fillMaxWidth().testTag("candidate_feedback_input"))
            if (excluding) {
                Text("默认只排除这款，不会自动改动你的预算和硬约束。")
                if (product.category.isNotBlank()) Row { Checkbox(wholeCategory, { wholeCategory = it }, modifier = Modifier.testTag("candidate_category_scope").semantics { contentDescription = "明确排除整个${product.category}类别" }); Text("明确排除整个${product.category}类别") }
                Text("可以在任务页撤销。排除后由你确认重新推荐。")
            } else Text("返回对话后可继续修改，再发送给助手。")
        }
    }, confirmButton = {
        Button(onClick = {
            if (excluding) onAction(ShoppingAction.ExcludeCandidate(product.id, text.trim(), if (wholeCategory) "CATEGORY" else "PRODUCT"))
            else { onAction(ShoppingAction.AskCandidate(product.id)); onAction(ShoppingAction.UpdateDraft("针对【${product.title}】：${text.trim()}")) }
            onClose()
        }, enabled = text.isNotBlank()) { Text(if (excluding) "确认排除" else "准备追问") }
    }, dismissButton = { TextButton(onClick = onClose) { Text("取消") } })
}

@Composable
internal fun NoMatchGuidance(state: ShoppingUiState, onAction: (ShoppingAction) -> Unit) {
    val strictUnavailable = state.recommendationRoutes.any { it.type == RecommendationType.STRICT && !it.available }
    if (!strictUnavailable || state.isLoading) return
    Column(Modifier.fillMaxWidth().background(DesignTokens.WarningContainer).padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("没有完全符合当前条件的结果", fontWeight = FontWeight.Bold)
        state.recommendationRoutes.filter { !it.available }.map { it.summary }.distinct().forEach { Text(it) }
        Text("替代项不算满足硬约束。你可以保留条件不选，也可以明确修改后再计算。")
        Text("编辑时可以保留预算、调整功能要求，或保留要求、自己修改预算。")
        OutlinedButton(onClick = { onAction(ShoppingAction.BeginMissionEdit) }) { Text("编辑要求，再次检索") }
    }
}

@Composable
internal fun ComparisonFacts(state: ShoppingUiState) {
    val selected = state.products.filter { it.id in state.comparedProductIds }
    ProductComparisonFacts(selected)
}

@Composable
internal fun ProductComparisonFacts(selected: List<EvidenceProductUi>) {
    val dimensions = selected.flatMap { it.attributes.keys }.distinct().sorted()
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("同口径规格与取舍", fontWeight = FontWeight.Bold)
        if (dimensions.isEmpty()) Text("尚未取得商品规格，不能据此判断性能。")
        dimensions.forEach { dimension ->
            Text(dimension, fontWeight = FontWeight.Bold)
            selected.forEach { product -> Text("${product.title}：${product.attributes[dimension] ?: "尚未核实"}") }
        }
        Text("规格差异不自动等于体验优劣；应结合用途。没有证据的效果不作肯定判断。")
    }
}
