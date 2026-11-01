package com.ragcommerce.agent

import android.net.Uri
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.pager.VerticalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.ShoppingCart
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.TextButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.snapshotFlow
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.ragcommerce.agent.ui.BusinessFactUi
import com.ragcommerce.agent.ui.CartGroupUi
import com.ragcommerce.agent.ui.ComparisonSort
import com.ragcommerce.agent.ui.ConnectionState
import com.ragcommerce.agent.ui.DesignTokens
import com.ragcommerce.agent.ui.EvidenceProductUi
import com.ragcommerce.agent.ui.OfferUi
import com.ragcommerce.agent.ui.PrimaryTab
import com.ragcommerce.agent.ui.QuoteState
import com.ragcommerce.agent.ui.ShoppingAction
import com.ragcommerce.agent.ui.ShoppingUiState
import com.ragcommerce.agent.ui.constraintVerdict
import com.ragcommerce.agent.ui.approvalTargetSummary

private sealed interface PendingUserAction {
    data class Save(val product: EvidenceProductUi) : PendingUserAction
    data class AddToPlan(val offer: OfferUi) : PendingUserAction
    data class ChangeWaitingQuantity(val offer: OfferUi, val quantity: Int) : PendingUserAction
    data class OpenSource(val offer: OfferUi) : PendingUserAction
}

@Composable
fun EditorialShoppingApp(
    state: ShoppingUiState,
    onAction: (ShoppingAction) -> Unit,
    onOpenMerchant: (OfferUi) -> Unit,
    onSaveProduct: (EvidenceProductUi) -> Unit,
    onAddOffer: (OfferUi) -> Unit,
    onCreateWatcher: (OfferUi, String) -> Unit,
    onDeleteMyData: () -> Unit,
    onQualityDataConsentChanged: (Boolean) -> Unit,
    onPickImage: () -> Unit,
    onPickAudio: () -> Unit,
) {
    var pendingUserAction by remember { mutableStateOf<PendingUserAction?>(null) }
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = DesignTokens.Emerald,
            onPrimary = Color.White,
            primaryContainer = DesignTokens.Lime,
            onPrimaryContainer = DesignTokens.Ink,
            secondary = DesignTokens.Coral,
            background = DesignTokens.Bone,
            onBackground = DesignTokens.Ink,
            surface = DesignTokens.Surface,
            surfaceContainer = DesignTokens.Surface,
            surfaceContainerHigh = DesignTokens.Surface,
            surfaceContainerHighest = DesignTokens.Bone,
            surfaceContainerLow = DesignTokens.Bone,
            surfaceContainerLowest = DesignTokens.Surface,
            onSurface = DesignTokens.Ink,
            error = DesignTokens.Danger,
        ),
    ) {
        val navigationLocked = state.connection in setOf(
            ConnectionState.CHECKING,
            ConnectionState.RECONNECTING,
            ConnectionState.RECOVERED,
        )
        Scaffold(
            containerColor = DesignTokens.Bone,
            bottomBar = {
                if (navigationLocked || !(state.selectedTab == PrimaryTab.TASK && state.products.isNotEmpty() && !state.showConversation)) {
                    EditorialBottomBar(
                        selectedTab = state.selectedTab,
                        enabled = !navigationLocked,
                        onAction = onAction,
                    )
                }
            },
        ) { padding ->
            Surface(
                color = DesignTokens.Bone,
                modifier = Modifier.fillMaxSize().padding(padding),
            ) {
                when (state.selectedTab) {
                    PrimaryTab.TASK -> EditorialTaskScreen(
                        state = state,
                        onAction = onAction,
                        onSaveProduct = { pendingUserAction = PendingUserAction.Save(it) },
                        onAddOffer = { pendingUserAction = PendingUserAction.AddToPlan(it) },
                        onPickImage = onPickImage,
                        onPickAudio = onPickAudio,
                    )
                    PrimaryTab.DECISIONS -> EditorialDecisionScreen(
                        state = state,
                        onAction = { action ->
                            if (action is ShoppingAction.SetWaitingQuantity) {
                                pendingUserAction = PendingUserAction.ChangeWaitingQuantity(action.offer, action.quantity)
                            } else onAction(action)
                        },
                        onOpenMerchant = { pendingUserAction = PendingUserAction.OpenSource(it); onAction(ShoppingAction.PrepareMerchant(it)) },
                        onCreateWatcher = onCreateWatcher,
                    )
                    PrimaryTab.PROFILE -> EditorialProfileScreen(state, onDeleteMyData, onQualityDataConsentChanged)
                }
            }
        }

        state.pendingApprovalTool?.let { tool ->
            ApprovalSheet(
                tool = tool,
                targetSummary = approvalTargetSummary(tool, state.pendingApprovalArguments, state),
                onCancel = { onAction(ShoppingAction.ResolveApproval(false)) },
                onConfirm = { onAction(ShoppingAction.ResolveApproval(true)) },
            )
        }
        pendingUserAction?.let { action ->
            ActionConfirmationSheet(
                action = action,
                merchantHost = state.preparedMerchantHost.takeIf { action is PendingUserAction.OpenSource && state.preparedMerchantOfferId == action.offer.id },
                onCancel = { pendingUserAction = null },
                onConfirm = {
                    when (action) {
                        is PendingUserAction.Save -> onSaveProduct(action.product)
                        is PendingUserAction.AddToPlan -> onAddOffer(action.offer)
                        is PendingUserAction.ChangeWaitingQuantity -> onAction(ShoppingAction.SetWaitingQuantity(action.offer, action.quantity))
                        is PendingUserAction.OpenSource -> onOpenMerchant(action.offer)
                    }
                    pendingUserAction = null
                },
            )
        }
        state.missionEditDraft?.let { draft ->
            MissionEditDialog(draft = draft, onAction = onAction)
        }
        DecisionExperienceDialogs(state, onAction, onAddOffer = { pendingUserAction = PendingUserAction.AddToPlan(it) })
    }
}

@Composable
private fun EditorialBottomBar(
    selectedTab: PrimaryTab,
    enabled: Boolean,
    onAction: (ShoppingAction) -> Unit,
) {
    NavigationBar(
        containerColor = DesignTokens.Ink,
        contentColor = Color.White,
        modifier = Modifier.navigationBarsPadding(),
    ) {
        PrimaryTab.entries.forEach { tab ->
            NavigationBarItem(
                selected = selectedTab == tab,
                enabled = enabled,
                onClick = { onAction(ShoppingAction.SelectTab(tab)) },
                icon = {
                    Icon(
                        imageVector = when (tab) {
                            PrimaryTab.TASK -> Icons.Outlined.Search
                            PrimaryTab.DECISIONS -> Icons.Outlined.ShoppingCart
                            PrimaryTab.PROFILE -> Icons.Outlined.Person
                        },
                        contentDescription = null,
                    )
                },
                label = { Text(tab.label, fontWeight = FontWeight.Bold) },
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = DesignTokens.Ink,
                    selectedTextColor = DesignTokens.Lime,
                    indicatorColor = DesignTokens.Lime,
                    unselectedIconColor = Color.White.copy(alpha = 0.72f),
                    unselectedTextColor = Color.White.copy(alpha = 0.72f),
                ),
                modifier = Modifier
                    .heightIn(min = DesignTokens.TouchTarget)
                    .testTag("tab_${tab.name}")
                    .semantics { contentDescription = tab.label },
            )
        }
    }
}

@Composable
private fun EditorialTaskScreen(
    state: ShoppingUiState,
    onAction: (ShoppingAction) -> Unit,
    onSaveProduct: (EvidenceProductUi) -> Unit,
    onAddOffer: (OfferUi) -> Unit,
    onPickImage: () -> Unit,
    onPickAudio: () -> Unit,
) {
    Box(modifier = Modifier.fillMaxSize().testTag("screen_任务")) {
        if (state.connection == ConnectionState.RECOVERED) {
            RecoveryExperience(state, onAction)
        } else if (state.products.isNotEmpty() && !state.showConversation) {
            RecommendationResult(
                state = state,
                onAction = onAction,
                onSaveProduct = onSaveProduct,
                onAddOffer = onAddOffer,
            )
        } else {
            MissionConversation(
                state = state,
                onAction = onAction,
                onPickImage = onPickImage,
                onPickAudio = onPickAudio,
            )
        }
    }
}

@Composable
private fun RecoveryExperience(
    state: ShoppingUiState,
    onAction: (ShoppingAction) -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize().testTag("connection_RECOVERED"),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Column(
                modifier = Modifier.fillMaxWidth().padding(horizontal = DesignTokens.ScreenPadding, vertical = 18.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Text("任务 01", color = DesignTokens.Emerald, fontWeight = FontWeight.Black)
                Text("已恢复", fontSize = 62.sp, lineHeight = 64.sp, fontWeight = FontWeight.Black)
                Box(modifier = Modifier.fillMaxWidth().height(6.dp).background(DesignTokens.Lime))
                Text("已从上次进度继续", fontSize = 23.sp, fontWeight = FontWeight.Black)
                Text(state.statusMessage, color = DesignTokens.TextSecondary)
            }
        }
        item {
            Column(
                modifier = Modifier
                    .padding(horizontal = DesignTokens.ScreenPadding)
                    .fillMaxWidth()
                    .background(DesignTokens.Surface)
                    .border(1.dp, DesignTokens.Ink)
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text("任务约束", color = DesignTokens.Emerald, fontSize = 16.sp, fontWeight = FontWeight.Black)
                Text(
                    displayMissionGoal(state.missionGoal).ifBlank { "当前 Shopping Mission" },
                    fontSize = 20.sp,
                    lineHeight = 24.sp,
                    fontWeight = FontWeight.Black,
                )
            }
        }
        item {
            Column(
                modifier = Modifier
                    .padding(horizontal = DesignTokens.ScreenPadding)
                    .fillMaxWidth()
                    .background(DesignTokens.Emerald)
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text("安全恢复点", color = DesignTokens.Lime, fontSize = 20.sp, fontWeight = FontWeight.Black)
                Text(if (state.pendingApprovalTool != null) "有操作等待你确认" else if (state.isLoading) "任务仍在处理中" else "上次任务已载入", color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                Text("继续后查看结果或处理待确认操作", color = Color.White.copy(alpha = 0.78f))
            }
        }
        item {
            Column(
                modifier = Modifier
                    .padding(horizontal = DesignTokens.ScreenPadding)
                    .fillMaxWidth()
                    .background(DesignTokens.Surface)
                    .border(1.dp, DesignTokens.Ink)
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Text("恢复说明", color = DesignTokens.Emerald, fontSize = 18.sp, fontWeight = FontWeight.Black)
                Text("已从服务端载入任务状态", fontWeight = FontWeight.SemiBold)
                Text("待确认操作仍需你批准", fontWeight = FontWeight.SemiBold)
                Text("离线期间未生成新报价或新证据", color = DesignTokens.TextSecondary)
            }
        }
        item {
            Button(
                onClick = { onAction(ShoppingAction.ContinueRecoveredMission) },
                colors = ButtonDefaults.buttonColors(containerColor = DesignTokens.Lime, contentColor = DesignTokens.Ink),
                modifier = Modifier
                    .padding(horizontal = DesignTokens.ScreenPadding)
                    .fillMaxWidth()
                    .heightIn(min = 58.dp)
                    .testTag("continue_recovered"),
            ) { Text("继续任务", fontSize = 18.sp, fontWeight = FontWeight.Black) }
        }
        item { Spacer(Modifier.height(20.dp)) }
    }
}

@Composable
private fun MissionConversation(
    state: ShoppingUiState,
    onAction: (ShoppingAction) -> Unit,
    onPickImage: () -> Unit,
    onPickAudio: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize().testTag("mission_conversation"),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            EditorialHeader(
                eyebrow = "SHOPPING MISSION",
                title = "把需求交给\nAgent 决策",
                accent = DesignTokens.Coral,
            )
        }
        item {
            Column(
                modifier = Modifier.padding(horizontal = DesignTokens.ScreenPadding),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                ConnectionReceipt(state.connection, state.statusMessage, onAction)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = { onAction(ShoppingAction.LoadHistory) }, enabled = !state.decisionBusy && !state.isLoading,
                        modifier = Modifier.testTag("task_history")) { Text("最近任务") }
                    if (state.missionGoal.isNotBlank()) TextButton(onClick = { onAction(ShoppingAction.LoadConversation) }, enabled = !state.decisionBusy,
                        modifier = Modifier.testTag("conversation_history")) { Text("完整对话") }
                }
                NoMatchGuidance(state, onAction)
                state.feedback.forEach { (key, reason) ->
                    Column {
                        Text("${if (key.startsWith("CATEGORY:")) "类别排除" else "单品排除"} · $reason")
                        TextButton(onClick = { onAction(ShoppingAction.UndoCandidateFeedback(key)) }, enabled = !state.decisionBusy) { Text("撤销排除") }
                    }
                }
                if (state.explorationNeedsRefresh) {
                    OutlinedButton(onClick = { onAction(ShoppingAction.RetryConnection) },
                        modifier = Modifier.testTag("explore_refresh")) { Text("刷新当前任务") }
                }
                if (state.missionGoal.isNotBlank()) {
                    EditorialPanel("当前 Mission", displayMissionGoal(state.missionGoal), DesignTokens.Lime)
                }
                if (state.mode != "DISCOVERY") MissionConstraintStrip(state, onAction)
                if (state.missionGoal.isNotBlank()) {
                    OutlinedButton(
                        onClick = { onAction(ShoppingAction.StartNewMission) },
                        modifier = Modifier
                            .heightIn(min = DesignTokens.TouchTarget)
                            .testTag("new_mission"),
                    ) { Text("新建任务", fontWeight = FontWeight.Bold) }
                }
                if (state.products.isNotEmpty()) {
                    OutlinedButton(
                        onClick = { onAction(ShoppingAction.ShowCurrentRecommendations) },
                        modifier = Modifier
                            .heightIn(min = DesignTokens.TouchTarget)
                            .testTag("reopen_recommendations"),
                    ) { Text("查看当前推荐", fontWeight = FontWeight.Bold) }
                }
                state.agentMessages.takeLast(3).forEach { message ->
                    EditorialPanel("Agent", message, DesignTokens.Surface)
                }
                if (state.clarificationQuestion != null) {
                    ClarificationQuickReplies(onAction)
                }
            }
        }
        if (state.isLoading) {
            item {
                if (state.statusMessage == "正在更新探索方向") {
                    Text("正在读取目录方向", modifier = Modifier.padding(DesignTokens.ScreenPadding))
                } else AgentProgress(state.statusMessage)
            }
        }
        if (state.mode == "DISCOVERY") {
            item { ExplorationWorkbench(state, onAction) }
        } else if (state.pendingMediaInterpretations.isNotEmpty()) {
            item {
                Column(Modifier.fillMaxWidth().padding(DesignTokens.ScreenPadding), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("确认识别内容", fontSize = 24.sp, fontWeight = FontWeight.Black)
                    state.pendingMediaInterpretations.forEach { media ->
                        Text(if (media.kind == "audio") "语音转写" else "图片线索")
                        media.visible_attributes.forEach { Text(it) }
                        media.uncertainties.forEach { Text(it, color = DesignTokens.TextSecondary) }
                        if (!media.supported) Text("未能确定需求，你可以改用文字说明", color = DesignTokens.Warning)
                    }
                    Text("识别内容仅帮助理解需求，商品事实和报价仍以目录证据为准。", fontSize = 12.sp)
                    OutlinedTextField(value = state.draft, onValueChange = { onAction(ShoppingAction.UpdateDraft(it.take(500))) },
                        modifier = Modifier.fillMaxWidth().testTag("media_confirmation_input"), label = { Text("核对并修改需求") })
                    Button(onClick = { onAction(ShoppingAction.ConfirmMedia) }, enabled = state.draft.isNotBlank() && !state.isLoading,
                        modifier = Modifier.testTag("media_confirm")) { Text("确认并继续导购") }
                }
            }
        } else {
            item { MissionComposer(state, onAction, onPickImage, onPickAudio) }
            if (state.missionGoal.isBlank()) item { ExplorationEntry(state, onAction) }
        }
        items(state.attachments, key = { it.uri }) { attachment ->
            Card(
                colors = CardDefaults.cardColors(containerColor = DesignTokens.Surface),
                shape = androidx.compose.foundation.shape.CutCornerShape(0.dp),
                modifier = Modifier
                    .padding(horizontal = DesignTokens.ScreenPadding)
                    .fillMaxWidth()
                    .border(1.dp, DesignTokens.Ink)
                    .testTag("attachment_${attachment.kind}"),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(if (attachment.kind == "image") "图片附件" else "音频附件", fontWeight = FontWeight.Black)
                        Text(attachment.displayName.take(80), color = DesignTokens.TextSecondary)
                    }
                    OutlinedButton(
                        onClick = { onAction(ShoppingAction.RemoveAttachment(attachment.uri)) },
                        modifier = Modifier.heightIn(min = DesignTokens.TouchTarget),
                    ) { Text("移除") }
                }
            }
        }
        item { Spacer(Modifier.height(20.dp)) }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ExplorationEntry(state: ShoppingUiState, onAction: (ShoppingAction) -> Unit) {
    var life by remember { mutableStateOf(true) }
    var novelty by remember { mutableStateOf(true) }
    Column(Modifier.fillMaxWidth().padding(DesignTokens.ScreenPadding), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("还没想好买什么？", fontSize = 24.sp, fontWeight = FontWeight.Black)
        Text("从使用方向开始，不必先填预算。当前支持手机、电脑、耳机和相机。", color = DesignTokens.TextSecondary)
        FlowRow {
            Row(verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.heightIn(min = DesignTokens.TouchTarget)
                    .toggleable(value = life, role = Role.Checkbox, onValueChange = { life = it })
                    .semantics { contentDescription = "改善生活" }) {
                Checkbox(checked = life, onCheckedChange = null,
                    modifier = Modifier.size(DesignTokens.TouchTarget).clearAndSetSemantics {})
                Text("改善生活", modifier = Modifier.clearAndSetSemantics {})
            }
            Row(verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.heightIn(min = DesignTokens.TouchTarget)
                    .toggleable(value = novelty, role = Role.Checkbox, onValueChange = { novelty = it })
                    .semantics { contentDescription = "发现新玩法" }) {
                Checkbox(checked = novelty, onCheckedChange = null,
                    modifier = Modifier.size(DesignTokens.TouchTarget).clearAndSetSemantics {})
                Text("发现新玩法", modifier = Modifier.clearAndSetSemantics {})
            }
        }
        Button(onClick = { onAction(ShoppingAction.Explore("start", tags = buildList {
            if (life) add("life_improvement")
            if (novelty) add("novelty")
        })) }, enabled = !state.isLoading,
            colors = ButtonDefaults.buttonColors(containerColor = DesignTokens.Emerald),
            modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp).testTag("explore_start")) {
            Text("随便看看", fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun ExplorationWorkbench(state: ShoppingUiState, onAction: (ShoppingAction) -> Unit) {
    val exploration = state.exploration ?: return
    Column(Modifier.fillMaxWidth().padding(DesignTokens.ScreenPadding), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text(if (exploration.ended) "今天先看到这里" else "先发现方向，再决定要不要买",
            fontSize = 26.sp, fontWeight = FontWeight.Black)
        Text("方向来自项目演示目录，不代表市场新品或真实供货。", color = DesignTokens.TextSecondary)
        if (!exploration.ended) {
            exploration.directions.forEachIndexed { index, direction ->
                Column(Modifier.fillMaxWidth().background(DesignTokens.Surface).border(1.dp, DesignTokens.Ink)
                    .padding(16.dp).testTag("explore_direction_$index"), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("0${index + 1} / ${direction.category}", color = DesignTokens.Emerald, fontWeight = FontWeight.Bold)
                    Text(direction.title, fontSize = 25.sp, fontWeight = FontWeight.Black)
                    Text(direction.scenario_hint)
                    Text("先试一试 · ${direction.try_first}")
                    Text("决定前确认 · ${direction.to_confirm}", color = DesignTokens.TextSecondary)
                    Text("目录中有 ${direction.supporting_product_ids.size} 个示例支持这个使用方向；选定后再核对预算和规格。")
                    var showEvidence by remember(direction.direction_id) { mutableStateOf(false) }
                    TextButton(onClick = { showEvidence = !showEvidence }) { Text(if (showEvidence) "收起依据" else "查看目录依据") }
                    if (showEvidence) direction.evidence_refs.forEach { Text(it, fontSize = 12.sp) }
                    val feedback = exploration.feedback[direction.direction_id]
                    Text(when (feedback) { "interested" -> "已记下：感兴趣"; "not_interested" -> "已排除：不再主动推荐"; else -> "尚未选择偏好" }, color = DesignTokens.TextSecondary)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = { onAction(ShoppingAction.Explore("feedback", direction.direction_id, "interested")) }, enabled = !state.isLoading,
                            modifier = Modifier.testTag("explore_like_$index")) { Text("感兴趣") }
                        OutlinedButton(onClick = { onAction(ShoppingAction.Explore("feedback", direction.direction_id, "not_interested")) }, enabled = !state.isLoading,
                            modifier = Modifier.testTag("explore_dislike_$index")) { Text("不感兴趣") }
                    }
                    Button(onClick = { onAction(ShoppingAction.Explore("select_for_purchase", direction.direction_id)) },
                        enabled = !state.isLoading && feedback != "not_interested",
                        modifier = Modifier.fillMaxWidth().testTag("explore_select_$index"),
                        colors = ButtonDefaults.buttonColors(containerColor = DesignTokens.Emerald)) { Text("按这个方向选") }
                }
            }
            if (exploration.exhausted) Text("当前目录已看完，没有更多合适方向。可以撤销偏好，或结束后开始新任务。")
            exploration.feedback.forEach { (id, value) ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("${id.substringAfter(':')} · ${if (value == "interested") "感兴趣" else "已排除"}", modifier = Modifier.weight(1f))
                    TextButton(onClick = { onAction(ShoppingAction.Explore("feedback", id, "neutral")) }, enabled = !state.isLoading) { Text("撤销") }
                }
            }
            OutlinedButton(onClick = { onAction(ShoppingAction.Explore("next")) }, enabled = !state.isLoading,
                modifier = Modifier.fillMaxWidth().testTag("explore_next")) { Text("换个方向") }
            TextButton(onClick = { onAction(ShoppingAction.Explore("end")) }, enabled = !state.isLoading,
                modifier = Modifier.testTag("explore_end")) { Text("先结束") }
            OutlinedButton(onClick = { onAction(ShoppingAction.Explore("end", outcome = "USE_EXISTING")) }, enabled = !state.isLoading,
                modifier = Modifier.testTag("explore_use_existing")) { Text("先用现有设备试试") }
            TextButton(onClick = { onAction(ShoppingAction.Explore("end", outcome = "NOT_BUYING")) }, enabled = !state.isLoading,
                modifier = Modifier.testTag("explore_not_buying")) { Text("今天不买，保留结论") }
        } else {
            Text(when (exploration.outcome) { "USE_EXISTING" -> "本次结论：先用现有设备尝试"; "NOT_BUYING" -> "本次结论：暂不购买"; else -> "本次探索已结束" }, fontWeight = FontWeight.Bold)
            Text("没有新增待购，也没有跳转商家。探索记录已保留在本次会话。")
            OutlinedButton(onClick = { onAction(ShoppingAction.StartNewMission) }) { Text("开始新任务") }
        }
    }
}

@Composable
private fun ClarificationQuickReplies(onAction: (ShoppingAction) -> Unit) {
    val prompts = listOf(
        "budget" to "我的预算是：",
        "usage" to "主要用途是：",
        "hard_constraint" to "不能妥协：",
        "alternative" to "可以接受相近替代",
    )
    Column(
        modifier = Modifier.fillMaxWidth().testTag("clarification_quick_replies"),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text("快速补充（点击后仍可编辑）", fontWeight = FontWeight.Black)
        prompts.chunked(2).forEach { rowPrompts ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                rowPrompts.forEach { (id, prompt) ->
                    OutlinedButton(
                        onClick = { onAction(ShoppingAction.UseClarificationPrompt(prompt)) },
                        modifier = Modifier
                            .weight(1f)
                            .heightIn(min = DesignTokens.TouchTarget)
                            .testTag("clarification_$id"),
                    ) {
                        Text(prompt.removeSuffix("："), maxLines = 1)
                    }
                }
            }
        }
    }
}

@Composable
private fun EditorialHeader(eyebrow: String, title: String, accent: Color) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(DesignTokens.Ink)
            .padding(horizontal = DesignTokens.ScreenPadding, vertical = 22.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(eyebrow, color = accent, fontSize = 12.sp, fontWeight = FontWeight.Black, letterSpacing = 2.sp)
        Text(
            title,
            color = Color.White,
            fontSize = 38.sp,
            lineHeight = 39.sp,
            fontWeight = FontWeight.Black,
            modifier = Modifier.semantics { heading() },
        )
    }
}

@Composable
private fun MissionComposer(
    state: ShoppingUiState,
    onAction: (ShoppingAction) -> Unit,
    onPickImage: () -> Unit,
    onPickAudio: () -> Unit,
) {
    Column(
        modifier = Modifier.padding(horizontal = DesignTokens.ScreenPadding),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text("告诉我预算、用途与不能妥协的条件", fontSize = 18.sp, fontWeight = FontWeight.Black)
        OutlinedTextField(
            value = state.draft,
            onValueChange = { onAction(ShoppingAction.UpdateDraft(it)) },
            label = { Text("例如：1000 元内，通勤降噪，不要入耳式") },
            minLines = 3,
            modifier = Modifier.fillMaxWidth().testTag("mission_input"),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(
                onClick = onPickImage,
                enabled = !state.isLoading,
                modifier = Modifier
                    .heightIn(min = DesignTokens.TouchTarget)
                    .semantics { contentDescription = "添加商品图片" },
            ) { Text("图片") }
            OutlinedButton(
                onClick = onPickAudio,
                enabled = !state.isLoading,
                modifier = Modifier
                    .heightIn(min = DesignTokens.TouchTarget)
                    .semantics { contentDescription = "添加语音" },
            ) { Text("语音") }
            Button(
                onClick = { onAction(ShoppingAction.SubmitMission) },
                enabled = !state.isLoading && (state.draft.isNotBlank() || state.attachments.isNotEmpty()),
                colors = ButtonDefaults.buttonColors(
                    containerColor = DesignTokens.Emerald,
                    contentColor = Color.White,
                ),
                modifier = Modifier.heightIn(min = DesignTokens.TouchTarget).testTag("send_turn"),
            ) { Text("发送", fontWeight = FontWeight.Black) }
        }
        if (state.attachments.isNotEmpty()) {
            Text(
                "附件仅用于理解本次需求，识别结果由你确认后再继续",
                color = DesignTokens.TextSecondary,
                fontSize = 12.sp,
            )
        }
    }
}

@Composable
private fun AgentProgress(stage: String) {
    Column(
        modifier = Modifier
            .padding(horizontal = DesignTokens.ScreenPadding)
            .fillMaxWidth()
            .background(DesignTokens.Emerald)
            .semantics { liveRegion = LiveRegionMode.Polite }
            .padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Agent 分析中", color = DesignTokens.Lime, fontSize = 24.sp, fontWeight = FontWeight.Black)
        Text(stage, color = Color.White, fontWeight = FontWeight.SemiBold)
        Text("正在核对你的需求、商品信息与推荐依据", color = Color.White.copy(alpha = 0.68f), fontSize = 12.sp)
    }
}

@Composable
private fun RecommendationResult(
    state: ShoppingUiState,
    onAction: (ShoppingAction) -> Unit,
    onSaveProduct: (EvidenceProductUi) -> Unit,
    onAddOffer: (OfferUi) -> Unit,
) {
    val rankedProducts = state.products.take(3)
    val pagerState = rememberPagerState(
        initialPage = state.recommendationIndex.coerceIn(0, (rankedProducts.size - 1).coerceAtLeast(0)),
        pageCount = { rankedProducts.size },
    )
    LaunchedEffect(pagerState) {
        snapshotFlow { pagerState.settledPage }.collect { onAction(ShoppingAction.RecommendationPageChanged(it)) }
    }
    Column(modifier = Modifier.fillMaxSize()) {
        Column(
            // Keep navigation visible while long constraints scroll within the same height budget.
            modifier = Modifier.fillMaxWidth().heightIn(max = 240.dp)
                .padding(horizontal = DesignTokens.ScreenPadding, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                IconButton(
                    onClick = { onAction(ShoppingAction.ReturnToMissionConversation) },
                    modifier = Modifier.testTag("back_to_mission"),
                ) {
                    Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "返回 Mission 对话")
                }
                Text("Agent 推荐", fontSize = 22.sp, fontWeight = FontWeight.Black)
                Spacer(Modifier.weight(1f))
                ConnectionPill(state.connection)
            }
            Column(
                modifier = Modifier.fillMaxWidth().weight(1f, fill = false)
                    .verticalScroll(rememberScrollState()).testTag("recommendation_controls"),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    displayMissionGoal(state.missionGoal).ifBlank { "本次导购任务" },
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    color = DesignTokens.TextSecondary,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(state.statusMessage, color = DesignTokens.TextSecondary, fontSize = 12.sp)
                MissionConstraintStrip(state, onAction)
                OutlinedButton(
                    onClick = { onAction(ShoppingAction.StartNewMission) },
                    modifier = Modifier
                        .heightIn(min = DesignTokens.TouchTarget)
                        .testTag("new_mission"),
                ) { Text("新建任务", fontWeight = FontWeight.Bold) }
                ConstraintSummary(state.products)
                RecommendationRouteStrip(state)
                NoMatchGuidance(state, onAction)
                if (state.connection == ConnectionState.RECOVERED) RecoveryReceipt()
            }
        }
        if (state.connection == ConnectionState.OFFLINE) {
            OutlinedButton(
                onClick = { onAction(ShoppingAction.RetryConnection) },
                modifier = Modifier.padding(horizontal = DesignTokens.ScreenPadding)
                    .heightIn(min = DesignTokens.TouchTarget).testTag("retry_connection"),
            ) { Text("重试连接") }
        }
        if (state.comparedProductIds.isNotEmpty()) {
            Text(
                if (LocalDensity.current.fontScale > 1f) "已选 ${state.comparedProductIds.size} 项"
                else if (state.comparedProductIds.size == 1) "已选 1 项，再选 1 项进入比较"
                else "已选 ${state.comparedProductIds.size} 项，可前往决策比较",
                color = DesignTokens.Emerald,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(horizontal = DesignTokens.ScreenPadding)
                    .testTag("compare_selection_hint"),
            )
        }
        VerticalPager(
            state = pagerState,
            modifier = Modifier.fillMaxSize().testTag("recommendation_pager"),
            pageSpacing = 8.dp,
        ) { page ->
            val product = rankedProducts[page]
            val offers = state.cartGroups.flatMap { it.offers }
            val offer = offers.firstOrNull { it.productId == product.id }
                ?: offers.singleOrNull().takeIf { rankedProducts.size == 1 }
            RecommendationPage(
                product = product,
                offer = offer,
                rank = page,
                total = rankedProducts.size,
                selected = product.id in state.comparedProductIds,
                onToggle = { onAction(ShoppingAction.ToggleCompare(product.id)) },
                onSave = { onSaveProduct(product) },
                onAddOffer = { offer?.let(onAddOffer) },
                onAction = onAction,
            )
        }
    }
}

private fun displayMissionGoal(value: String): String =
    if ('%' in value) Uri.decode(value) else value

@Composable
private fun MissionConstraintStrip(
    state: ShoppingUiState,
    onAction: (ShoppingAction) -> Unit,
) {
    val mission = state.mission ?: return
    val labels = buildList {
        mission.budgetTotalMinor?.let { add("总预算 ¥${it / 100}") }
        addAll(mission.items.map { "${it.category} ×${it.quantity}" })
        addAll(mission.hardConstraints.map { "硬约束 · $it" })
        addAll(mission.softPreferences.map { "偏好 · $it" })
        addAll(mission.unknowns.map { "待确认 · $it" })
    }.take(8)
    if (labels.isEmpty()) return
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .testTag("mission_constraints"),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            labels.forEach { label ->
                OutlinedButton(
                    onClick = { onAction(ShoppingAction.BeginMissionEdit) },
                    modifier = Modifier.heightIn(min = DesignTokens.TouchTarget),
                ) {
                    Text(label, maxLines = 1, fontWeight = FontWeight.Bold)
                }
            }
        }
        if (state.pendingMissionRecalculation) {
            Button(
                onClick = { onAction(ShoppingAction.RecalculateMission) },
                colors = ButtonDefaults.buttonColors(
                    containerColor = DesignTokens.Coral,
                    contentColor = Color.White,
                ),
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = DesignTokens.TouchTarget)
                    .testTag("recalculate_mission"),
            ) {
                Text("重新计算推荐", fontWeight = FontWeight.Black)
            }
        }
    }
}

@Composable
private fun MissionEditDialog(
    draft: String,
    onAction: (ShoppingAction) -> Unit,
) {
    AlertDialog(
        onDismissRequest = { onAction(ShoppingAction.CancelMissionEdit) },
        title = { Text("编辑任务约束", fontWeight = FontWeight.Black) },
        text = {
            OutlinedTextField(
                value = draft,
                onValueChange = { onAction(ShoppingAction.UpdateMissionEdit(it)) },
                label = { Text("用一句话调整预算、硬约束或偏好") },
                minLines = 3,
                modifier = Modifier.fillMaxWidth().testTag("mission_edit_input"),
            )
        },
        dismissButton = {
            OutlinedButton(onClick = { onAction(ShoppingAction.CancelMissionEdit) }) {
                Text("取消")
            }
        },
        confirmButton = {
            Button(
                onClick = { onAction(ShoppingAction.ApplyMissionEdit) },
                enabled = draft.isNotBlank(),
            ) {
                Text("保存修改")
            }
        },
    )
}

@Composable
private fun ConstraintSummary(products: List<EvidenceProductUi>) {
    val matched = products.flatMap { it.matchedConstraints }.distinct().take(4)
    val unmet = products.flatMap { it.unmetConstraints }.distinct().take(4)
    if (matched.isEmpty() && unmet.isEmpty()) return
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(DesignTokens.Surface)
            .border(1.dp, DesignTokens.Ink)
            .padding(10.dp)
            .testTag("constraint_summary"),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text("约束摘要", fontWeight = FontWeight.Black)
        matched.forEach { Text("满足 · $it", color = DesignTokens.Emerald, fontSize = 12.sp) }
        unmet.forEach { Text("未满足 · $it", color = DesignTokens.Warning, fontSize = 12.sp) }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun RecommendationPage(
    product: EvidenceProductUi,
    offer: OfferUi?,
    rank: Int,
    total: Int,
    selected: Boolean,
    onToggle: () -> Unit,
    onSave: () -> Unit,
    onAddOffer: () -> Unit,
    onAction: (ShoppingAction) -> Unit,
) {
    var discussionVisible by remember(product.id) { mutableStateOf(false) }
    if (discussionVisible) CandidateDiscussionDialog(product, onAction, onClose = { discussionVisible = false })
    val compact = LocalDensity.current.fontScale > 1f
    val rankLabel = when (rank) {
        0 -> "主推荐"
        1 -> "次推荐"
        else -> "再次推荐"
    }
    val pagingHint = when (rank) {
        0 -> "下滑查看次推荐"
        1 -> if (compact) "上滑主推荐 · 下滑再次推荐" else "上滑返回主推荐 · 下滑查看再次推荐"
        else -> "上滑返回次推荐"
    }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = DesignTokens.ScreenPadding, vertical = 4.dp)
            .background(DesignTokens.Surface)
            .border(1.dp, DesignTokens.Ink)
            .padding(14.dp)
            .testTag("product_${product.id}"),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        val summary: @Composable ColumnScope.() -> Unit = {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(
                if (compact) "$rankLabel · ${product.recommendationType.label}" else "${product.recommendationType.label} · $rankLabel",
                fontSize = 24.sp,
                fontWeight = FontWeight.Black,
                modifier = Modifier.weight(1f).testTag("recommendation_rank_$rank"),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                "%02d / %02d".format(rank + 1, total),
                color = DesignTokens.Emerald,
                fontWeight = FontWeight.Black,
                maxLines = 1,
            )
        }
        Text(
            product.title,
            fontSize = 25.sp,
            lineHeight = 27.sp,
            fontWeight = FontWeight.Black,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        if (!compact && (product.title.contains("耳机") || product.title.contains("headphone", ignoreCase = true) || product.title.contains("earbud", ignoreCase = true))) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(0.48f)
                    .background(DesignTokens.Lime)
                    .clipToBounds(),
                contentAlignment = Alignment.Center,
            ) {
                Image(
                    painter = painterResource(R.drawable.product_earbuds_editorial_v1),
                    contentDescription = "耳机概念插画，非该商品实拍",
                    contentScale = ContentScale.Fit,
                    modifier = Modifier
                        .fillMaxSize()
                        .graphicsLayer(scaleX = 1.15f, scaleY = 1.15f)
                        .padding(4.dp),
                )
                Text(
                    "%02d".format(rank + 1),
                    color = DesignTokens.Emerald,
                    fontSize = 54.sp,
                    lineHeight = 54.sp,
                    fontWeight = FontWeight.Black,
                    modifier = Modifier.align(Alignment.TopStart).padding(10.dp),
                )
                Text("概念插画 · 非商品实拍", color = DesignTokens.Ink, fontSize = 11.sp,
                    modifier = Modifier.align(Alignment.BottomEnd).background(DesignTokens.Lime).padding(6.dp))
            }
        }
        if (!compact) {
            Text(product.fitSummary, color = DesignTokens.TextSecondary, lineHeight = 20.sp,
                maxLines = 1, overflow = TextOverflow.Ellipsis)
            product.matchedConstraints.take(1).forEach { constraint ->
                Text("满足 · $constraint", color = DesignTokens.Emerald, fontWeight = FontWeight.SemiBold)
            }
            product.unmetConstraints.take(1).forEach { constraint ->
                Text("未满足 · $constraint", color = DesignTokens.Warning, fontWeight = FontWeight.SemiBold)
            }
            product.relaxedConstraints.take(1).forEach { constraint ->
                Text("明确放宽 · $constraint", color = DesignTokens.Warning, fontWeight = FontWeight.SemiBold)
            }
            product.risks.take(1).forEach { risk ->
                Text("提示 · ${displayProductRisk(risk)}", color = DesignTokens.Warning, fontWeight = FontWeight.SemiBold)
            }
        }
        }
        if (compact) {
            Column(Modifier.weight(1f).clipToBounds(),
                verticalArrangement = Arrangement.spacedBy(8.dp), content = summary)
        } else summary()
        // Actions stay outside the clipped editorial summary at large font sizes.
        // Detailed reasons and risks remain available in the evidence dialog.
        Button(
            onClick = { discussionVisible = true },
            colors = ButtonDefaults.buttonColors(containerColor = DesignTokens.Lime, contentColor = DesignTokens.Ink),
            modifier = Modifier.fillMaxWidth().heightIn(min = DesignTokens.TouchTarget).testTag("discuss_${product.id}"),
        ) { Text("问这款 / 调整推荐", fontWeight = FontWeight.Bold) }
        if (product.evidenceRefs.isNotEmpty()) {
            EvidenceDisclosure("product_${product.id}", product.evidenceRefs,
                buildList {
                    add(product.title)
                    add(product.fitSummary)
                    addAll(product.matchedConstraints.map { "满足 · $it" })
                    addAll(product.unmetConstraints.map { "未满足 · $it" })
                    addAll(product.relaxedConstraints.map { "明确放宽 · $it" })
                    addAll(product.risks.map { "提示 · ${displayProductRisk(it)}" })
                    offer?.let { quote ->
                        add("${quote.priceText ?: "价格待确认"} · ${quoteLabel(quote)}")
                        addAll(quote.businessFacts.map(::displayBusinessFact))
                    }
                })
        }
        offer?.let {
            if (compact) {
                Column {
                    Text(it.priceText ?: "价格待确认", fontSize = 26.sp, fontWeight = FontWeight.Black, color = DesignTokens.Emerald)
                    Text(quoteLabel(it), fontSize = 12.sp, lineHeight = 16.sp, fontWeight = FontWeight.Black)
                }
            } else {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(it.priceText ?: "价格待确认", fontSize = 26.sp, fontWeight = FontWeight.Black, color = DesignTokens.Emerald)
                Text(quoteLabel(it), fontSize = 12.sp, lineHeight = 16.sp, fontWeight = FontWeight.Black,
                    modifier = Modifier.weight(1f).padding(start = 8.dp))
            }
            }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = selected, onCheckedChange = { onToggle() },
                    modifier = Modifier.size(DesignTokens.TouchTarget).testTag("compare_${product.id}")
                        .semantics { contentDescription = "加入比较 · ${product.title}" })
                Text(if (selected) { if (compact) "已选" else "已加入比较" } else "加入比较", fontWeight = FontWeight.Bold)
            }
            OutlinedButton(
                onClick = onSave,
                modifier = Modifier.heightIn(min = DesignTokens.TouchTarget).testTag("save_${product.id}"),
            ) { Text("保存候选") }
            if (offer != null) {
                Button(
                    onClick = onAddOffer,
                    enabled = offer.quoteState == QuoteState.CURRENT,
                    colors = ButtonDefaults.buttonColors(containerColor = DesignTokens.Ink, contentColor = DesignTokens.Lime),
                    modifier = Modifier
                        .heightIn(min = DesignTokens.TouchTarget)
                        .testTag("add_plan_${product.id}"),
                ) { Text("加入待购", fontWeight = FontWeight.Black) }
            }
        }
        if (!compact) offer?.let { BusinessFactsCard(it.businessFacts) }
        Text(pagingHint, color = DesignTokens.TextSecondary, fontSize = 11.sp, lineHeight = 14.sp,
            maxLines = if (compact) 1 else 2, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun EvidenceDisclosure(id: String, refs: List<String>, details: List<String>) {
    var expanded by remember { mutableStateOf(false) }
    TextButton(onClick = { expanded = true }, modifier = Modifier.heightIn(min = DesignTokens.TouchTarget).testTag("evidence_$id")) {
        Text("查看来源与依据", fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
    }
    if (expanded) {
        AlertDialog(
            onDismissRequest = { expanded = false },
            title = { Text("证据来源") },
            text = {
                Column(Modifier.heightIn(max = 420.dp).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("当前内容来自项目自有演示目录，不是电商平台实时报价。")
                    details.forEach { Text(it) }
                    refs.distinct().forEach { Text("证据记录 · $it", fontSize = 12.sp) }
                }
            },
            confirmButton = { TextButton(onClick = { expanded = false }, modifier = Modifier.testTag("evidence_close")) { Text("关闭依据") } },
        )
    }
}

@Composable
private fun RecommendationRouteStrip(state: ShoppingUiState) {
    if (state.recommendationRoutes.isEmpty()) return
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .testTag("recommendation_routes"),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        state.recommendationRoutes.forEach { route ->
            Surface(
                color = if (route.available) DesignTokens.Lime else DesignTokens.Background,
                modifier = Modifier
                    .width(190.dp)
                    .border(1.dp, DesignTokens.Ink)
                    .testTag("route_${route.type.name}"),
            ) {
                Column(
                    modifier = Modifier.padding(8.dp),
                    verticalArrangement = Arrangement.spacedBy(2.dp),
                ) {
                    Text(route.type.label, fontWeight = FontWeight.Black)
                    Text(
                        if (route.available) route.summary else "暂不可用 · ${route.summary}",
                        fontSize = 10.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
    }
}

@Composable
private fun BusinessFactsCard(facts: List<BusinessFactUi>) {
    if (facts.isEmpty()) return
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(DesignTokens.Background)
            .border(1.dp, DesignTokens.Ink)
            .padding(horizontal = 8.dp, vertical = 6.dp)
            .testTag("business_facts"),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        facts.forEach { fact ->
            Text(displayBusinessFact(fact), fontSize = 10.sp, maxLines = 1,
                overflow = TextOverflow.Ellipsis)
        }
    }
}

private fun displayBusinessFact(fact: BusinessFactUi): String {
    val label = when (fact.type) {
        "price" -> "价格"
        "inventory" -> "库存"
        "delivery" -> "配送"
        "merchant" -> "商家"
        "after_sales" -> "售后"
        else -> fact.type
    }
    val level = when (fact.verificationLevel) {
        "LIVE_AUTHORIZED" -> "已授权核验"
        "FEED_VERIFIED" -> "第三方核验"
        "DISCOVERY_ONLY" -> "发现线索"
        else -> "演示数据"
    }
    return "$label · ${fact.summary} · $level"
}

@Composable
private fun EditorialDecisionScreen(
    state: ShoppingUiState,
    onAction: (ShoppingAction) -> Unit,
    onOpenMerchant: (OfferUi) -> Unit,
    onCreateWatcher: (OfferUi, String) -> Unit,
) {
    val waitingGroups = state.waitingOffers.groupBy(OfferUi::merchantName)
        .map { (merchant, offers) -> CartGroupUi(merchant, offers) }
    LazyColumn(
        modifier = Modifier.fillMaxSize().testTag("screen_决策"),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            EditorialHeader(
                eyebrow = "决策工作台",
                title = "比较之后\n再行动",
                accent = DesignTokens.Lime,
            )
        }
        item {
            Text(
                "比较、已保存方案与待购集合，不创建订单",
                modifier = Modifier.padding(horizontal = DesignTokens.ScreenPadding),
                color = DesignTokens.TextSecondary,
            )
        }
        if (state.comparedProductIds.size >= 2) {
            item {
                Column(
                    modifier = Modifier
                        .padding(horizontal = DesignTokens.ScreenPadding)
                        .fillMaxWidth()
                        .background(DesignTokens.Lime)
                        .border(1.dp, DesignTokens.Ink)
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Text("比较工作台", fontSize = 24.sp, fontWeight = FontWeight.Black)
                    Text("${state.comparedProductIds.size} 个候选")
                    state.comparison?.let { comparison ->
                        Text("比较维度：${comparison.dimensions.joinToString("、").ifBlank { "暂无统一维度" }}")
                        Text("缺失字段 ${comparison.missingFields.size} 项；只比较已返回事实")
                    }
                    Row(
                        modifier = Modifier.horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        ComparisonSort.entries.forEach { sort ->
                            val selected = state.comparisonSort == sort
                            if (selected) {
                                Button(
                                    onClick = { onAction(ShoppingAction.SetComparisonSort(sort)) },
                                    modifier = Modifier.testTag("comparison_sort_${sort.name}"),
                                ) { Text(sort.label) }
                            } else {
                                OutlinedButton(
                                    onClick = { onAction(ShoppingAction.SetComparisonSort(sort)) },
                                    modifier = Modifier.testTag("comparison_sort_${sort.name}"),
                                ) { Text(sort.label) }
                            }
                        }
                    }
                    MobileComparisonTable(state)
                    ComparisonFacts(state)
                    TextButton(onClick = {
                        onAction(ShoppingAction.ReturnToMissionConversation)
                        onAction(ShoppingAction.SelectTab(PrimaryTab.TASK))
                        onAction(ShoppingAction.UpdateDraft("结合本次用途比较这些候选，解释已核实差异和取舍：" + state.products.filter { it.id in state.comparedProductIds }.joinToString("、") { it.title }))
                    }) { Text("结合我的用途继续问") }
                }
            }
        }
        item { EditorialSectionTitle("已保存方案", "已保存") }
        item {
            Column(Modifier.padding(horizontal = DesignTokens.ScreenPadding).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("跨任务选2–4款同品类商品，直接比较目录事实；不会改动当前任务。", color = DesignTokens.TextSecondary)
                Text("已选 ${state.savedComparisonIds.size}/4", fontWeight = FontWeight.Bold, modifier = Modifier.testTag("saved_compare_count"))
                Button(onClick = { onAction(ShoppingAction.CompareSavedSelection) },
                    enabled = !state.decisionBusy && state.savedComparisonIds.size in 2..4,
                    modifier = Modifier.fillMaxWidth().testTag("saved_compare_start")) { Text(if (state.decisionBusy) "正在读取事实" else "比较已选商品") }
                if (state.savedComparisonIds.isNotEmpty() || state.decisionError != null) {
                    OutlinedButton(onClick = { onAction(ShoppingAction.ClearSavedComparison) }, enabled = !state.decisionBusy,
                        modifier = Modifier.fillMaxWidth().testTag("saved_compare_clear")) { Text("清空比较选择") }
                }
                state.decisionError?.let { Text(it, color = DesignTokens.Danger, modifier = Modifier.testTag("decision_error").semantics { liveRegion = LiveRegionMode.Polite }) }
            }
        }
        state.savedComparison?.let { comparison ->
            item {
                Column(Modifier.padding(horizontal = DesignTokens.ScreenPadding).fillMaxWidth().background(DesignTokens.Lime)
                    .border(1.dp, DesignTokens.Ink).padding(16.dp).testTag("saved_compare_result"), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("已保存商品比较", fontSize = 24.sp, fontWeight = FontWeight.Black)
                    Text("${comparison.products.size}款 · ${comparison.products.first().category} · 目录事实对照")
                    Text("演示报价不代表成交价。这里对照已核实规格，不改变当前任务的用途和预算。")
                    comparison.products.forEach { product ->
                        Column(Modifier.fillMaxWidth().background(DesignTokens.Surface).padding(12.dp).testTag("saved_compare_product_${product.id}"), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text(product.title, fontWeight = FontWeight.Black)
                            val offers = comparison.offers.filter { it.productId == product.id }
                            if (offers.isEmpty()) Text("尚无可核实报价")
                            offers.forEach { offer ->
                                Text("${offer.merchantName} · ${offer.priceText ?: "价格未知"}")
                                Text(quoteLabel(offer))
                            }
                            EvidenceDisclosure("saved_compare_${product.id}", product.evidenceRefs + offers.map { it.sourceRef },
                                offers.flatMap { listOf("${it.merchantName} · 采集于 ${it.collectedAt}", "有效至 ${it.expiresAt} · ${quoteLabel(it)}") })
                        }
                    }
                    ProductComparisonFacts(comparison.products)
                }
            }
        }
        if (state.savedProducts.isEmpty()) {
            item { PaddedPanel("清单为空", "从有证据的商品卡加入，来源会随条目保存") }
        }
        items(state.savedProducts, key = { it.id }) { item ->
            Card(
                colors = CardDefaults.cardColors(containerColor = DesignTokens.Surface),
                shape = androidx.compose.foundation.shape.CutCornerShape(0.dp),
                modifier = Modifier
                    .padding(horizontal = DesignTokens.ScreenPadding)
                    .fillMaxWidth()
                    .border(1.dp, DesignTokens.Ink)
                    .testTag("saved_${item.id}"),
            ) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(item.title, fontSize = 18.sp, fontWeight = FontWeight.Black)
                    Text("来源与依据 · 已保存", color = DesignTokens.TextSecondary, fontSize = 12.sp)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = item.id in state.savedComparisonIds,
                            onCheckedChange = { onAction(ShoppingAction.ToggleSavedComparison(item.id)) },
                            enabled = !state.decisionBusy && (item.id in state.savedComparisonIds || state.savedComparisonIds.size < 4),
                            modifier = Modifier.size(DesignTokens.TouchTarget).testTag("saved_compare_pick_${item.id}")
                                .semantics { contentDescription = "加入比较 · ${item.title}" })
                        Text("加入比较", modifier = Modifier.weight(1f))
                    }
                    OutlinedButton(onClick = { onAction(ShoppingAction.OpenSaved(item.id)) }, enabled = !state.decisionBusy,
                        modifier = Modifier.fillMaxWidth().testTag("open_saved_${item.id}")) { Text("查看或管理商品") }
                }
            }
        }
        item { EditorialSectionTitle("待购计划", "待购") }
        if (waitingGroups.isEmpty()) {
            item { PaddedPanel("待购计划为空", "此处不创建订单，不保存支付信息") }
        }
        items(waitingGroups, key = { it.merchantName }) { group ->
            EditorialCartGroup(group, state.waitingQuantities, state.waitingCartBusy, state.watchers, onAction, onOpenMerchant, onCreateWatcher)
        }
        item { Spacer(Modifier.height(20.dp)) }
    }
}

@Composable
private fun MobileComparisonTable(state: ShoppingUiState) {
    val offers = state.cartGroups.flatMap(CartGroupUi::offers)
    val selected = state.products.filter { it.id in state.comparedProductIds }
    val sorted = when (state.comparisonSort) {
        ComparisonSort.BUDGET -> selected.sortedBy { product ->
            offers.firstOrNull { it.productId == product.id }?.priceMinor ?: Long.MAX_VALUE
        }
        ComparisonSort.HARD_CONSTRAINTS -> selected.sortedBy { it.unmetConstraints.size }
        ComparisonSort.PREFERENCE -> selected.sortedByDescending { it.matchedConstraints.size }
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .testTag("comparison_table"),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        sorted.forEach { product ->
            val offer = offers.firstOrNull { it.productId == product.id }
            Column(
                modifier = Modifier
                    .width(230.dp)
                    .background(DesignTokens.Surface)
                    .border(1.dp, DesignTokens.Ink)
                    .padding(12.dp)
                    .testTag("comparison_${product.id}"),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Text(product.title, fontWeight = FontWeight.Black, maxLines = 2)
                Text("预算 · ${offer?.priceText ?: "价格待确认"}", fontWeight = FontWeight.Bold)
                Text(
                    "硬约束 · ${constraintVerdict(product, state.mission)}",
                    color = if (product.unmetConstraints.isEmpty()) DesignTokens.Emerald else DesignTokens.Warning,
                )
                Text(
                    "偏好 · ${product.matchedConstraints.take(2).joinToString("、").ifBlank { "未返回" }}",
                    fontSize = 12.sp,
                )
                Text(
                    "提示 · ${product.risks.firstOrNull()?.let(::displayProductRisk) ?: "暂无补充提示"}",
                    color = DesignTokens.Warning,
                    fontSize = 12.sp,
                )
                Text(
                    "证据 · ${if (product.evidenceRefs.isEmpty()) "缺失" else "已保存"}",
                    color = DesignTokens.TextSecondary,
                    fontSize = 12.sp,
                )
            }
        }
    }
}

@Composable
private fun EditorialSectionTitle(title: String, eyebrow: String) {
    Column(modifier = Modifier.padding(horizontal = DesignTokens.ScreenPadding)) {
        Text(eyebrow, color = DesignTokens.Warning, fontSize = 11.sp, fontWeight = FontWeight.Black, letterSpacing = 1.4.sp)
        Text(title, fontSize = 28.sp, fontWeight = FontWeight.Black, modifier = Modifier.semantics { heading() })
    }
}

@Composable
private fun EditorialCartGroup(
    group: CartGroupUi,
    quantities: Map<String, Int>,
    busy: Boolean,
    watchers: List<com.ragcommerce.agent.ui.WatcherUi>,
    onAction: (ShoppingAction) -> Unit,
    onOpenMerchant: (OfferUi) -> Unit,
    onCreateWatcher: (OfferUi, String) -> Unit,
) {
    Column(
        modifier = Modifier
            .padding(horizontal = DesignTokens.ScreenPadding)
            .fillMaxWidth()
            .background(DesignTokens.Surface)
            .border(1.dp, DesignTokens.Ink)
            .padding(16.dp)
            .testTag("merchant_${group.merchantName}"),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(merchantDisplayName(group), fontSize = 20.sp, fontWeight = FontWeight.Black)
        group.offers.forEachIndexed { index, offer ->
            if (index > 0) HorizontalDivider(color = DesignTokens.Hairline)
            Text(offer.productTitle, fontSize = 18.sp, fontWeight = FontWeight.Black,
                modifier = Modifier.testTag("waiting_product_${offer.id}"))
            EditorialOfferCard(offer, watchers, onAction, onOpenMerchant, onCreateWatcher)
            WaitingQuantityControls(offer, quantities.getValue(offer.id), busy, onAction)
        }
    }
}

@Composable
private fun WaitingQuantityControls(offer: OfferUi, quantity: Int, busy: Boolean, onAction: (ShoppingAction) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("计划数量 $quantity", fontWeight = FontWeight.Bold, modifier = Modifier.testTag("waiting_quantity_${offer.id}"))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { onAction(ShoppingAction.SetWaitingQuantity(offer, quantity - 1)) },
                enabled = !busy && quantity > 1,
                modifier = Modifier.heightIn(min = DesignTokens.TouchTarget).testTag("waiting_decrease_${offer.id}")) { Text("减少") }
            OutlinedButton(onClick = { onAction(ShoppingAction.SetWaitingQuantity(offer, quantity + 1)) },
                enabled = !busy && quantity < 99,
                modifier = Modifier.heightIn(min = DesignTokens.TouchTarget).testTag("waiting_increase_${offer.id}")) { Text("增加") }
            TextButton(onClick = { onAction(ShoppingAction.SetWaitingQuantity(offer, 0)) }, enabled = !busy,
                modifier = Modifier.heightIn(min = DesignTokens.TouchTarget).testTag("waiting_remove_${offer.id}")) { Text("移除", color = DesignTokens.Danger) }
        }
    }
}

@Composable
private fun EditorialOfferCard(
    offer: OfferUi,
    watchers: List<com.ragcommerce.agent.ui.WatcherUi>,
    onAction: (ShoppingAction) -> Unit,
    onOpenMerchant: (OfferUi) -> Unit,
    onCreateWatcher: (OfferUi, String) -> Unit,
) {
    Column(modifier = Modifier.testTag("offer_${offer.id}"), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (offer.verification == "DEMO_FIXTURE") {
            Text(
                "演示数据 · 不代表可购买",
                color = DesignTokens.Ink,
                fontWeight = FontWeight.Black,
                modifier = Modifier.background(DesignTokens.Coral).padding(horizontal = 10.dp, vertical = 6.dp),
            )
        }
        Text(offer.priceText ?: "价格待商家确认", fontSize = 28.sp, fontWeight = FontWeight.Black)
        offer.shippingText?.let { Text("运费 $it") }
        Text("${quoteLabel(offer)} · 采集 ${offer.collectedAt}", fontSize = 12.sp, modifier = Modifier.testTag("quote_time_${offer.id}"))
        Text("有效至 ${offer.expiresAt}", fontSize = 12.sp, modifier = Modifier.testTag("quote_expiry_${offer.id}"))
        EvidenceDisclosure("offer_${offer.id}", listOf(offer.sourceRef) + offer.businessFacts.map { it.evidenceRef },
            listOf(offer.merchantName, "采集 ${offer.collectedAt}", "有效至 ${offer.expiresAt}") + offer.businessFacts.map { it.summary })
        if (offer.quoteState == QuoteState.CHANGED && !offer.confirmedChange) {
            Text("价格或库存已变化，已阻断跳转", color = DesignTokens.Warning, fontWeight = FontWeight.Bold)
            Button(
                onClick = { onAction(ShoppingAction.ConfirmQuoteChange(offer.id)) },
                colors = ButtonDefaults.buttonColors(containerColor = DesignTokens.Coral, contentColor = DesignTokens.Ink),
                modifier = Modifier.heightIn(min = DesignTokens.TouchTarget).testTag("confirm_quote_${offer.id}"),
            ) { Text("确认价格变化", fontWeight = FontWeight.Black) }
        }
        if (offer.quoteState == QuoteState.EXPIRED || offer.quoteState == QuoteState.UNAVAILABLE) {
            Text("报价已失效或不可用，请重新询价", color = DesignTokens.Danger, fontWeight = FontWeight.Bold)
        }
        OutlinedButton(
            onClick = { onAction(ShoppingAction.RequoteOffer(offer)) },
            modifier = Modifier.heightIn(min = DesignTokens.TouchTarget).testTag("requote_${offer.id}"),
        ) { Text("重新询价", fontWeight = FontWeight.Black) }
        Button(
            onClick = { onOpenMerchant(offer) },
            enabled = offer.mayResolve,
            colors = ButtonDefaults.buttonColors(containerColor = DesignTokens.Emerald, contentColor = Color.White),
            modifier = Modifier.heightIn(min = DesignTokens.TouchTarget).testTag("open_${offer.id}"),
        ) { Text(merchantActionLabel(offer), fontWeight = FontWeight.Black) }
        Text(offer.disclosure, color = DesignTokens.TextSecondary, fontSize = 11.sp)
    }
}

private fun quoteLabel(offer: OfferUi): String = when (offer.quoteState) {
    QuoteState.CURRENT -> verificationLabel(offer)
    QuoteState.CHANGED -> "${verificationLabel(offer)} · 已变化"
    QuoteState.EXPIRED -> "${verificationLabel(offer)} · 已过期"
    QuoteState.UNAVAILABLE -> "${verificationLabel(offer)} · 不可用"
}

private fun verificationLabel(offer: OfferUi): String = when (offer.verification) {
    "LIVE_AUTHORIZED" -> "已授权实时报价"
    "FEED_VERIFIED" -> "第三方核验报价"
    "DISCOVERY_ONLY" -> "发现线索 · 未核价"
    "DEMO_FIXTURE" -> "演示报价 · 不可作为成交价"
    else -> "报价证据等级未知"
}

private fun merchantDisplayName(group: CartGroupUi): String =
    if (group.offers.all { it.verification == "DEMO_FIXTURE" }) "演示商家 · ${group.merchantName}"
    else group.merchantName

private fun merchantActionLabel(offer: OfferUi): String = when (offer.verification) {
    "DEMO_FIXTURE" -> "查看演示来源"
    "LIVE_AUTHORIZED" -> "前往商家"
    else -> "查看报价来源"
}

@Composable
private fun EditorialProfileScreen(
    state: ShoppingUiState,
    onDeleteMyData: () -> Unit,
    onQualityDataConsentChanged: (Boolean) -> Unit,
) {
    var deleteConfirmationVisible by remember { mutableStateOf(false) }
    LazyColumn(
        modifier = Modifier.fillMaxSize().testTag("screen_我的"),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            EditorialHeader(
                eyebrow = "TRUST CENTER",
                title = "知道 Agent\n如何工作",
                accent = DesignTokens.Coral,
            )
        }
        item { PaddedPanel("商业来源", "价格、库存、物流、保障和店铺身份不由客户端推导。") }
        item { PaddedPanel("当前操作", state.statusMessage) }
        item { PaddedPanel("模型与数据声明", "演示商品与报价，不代表真实市场信息") }
        item {
            OutlinedButton(
                onClick = { deleteConfirmationVisible = true },
                modifier = Modifier
                    .padding(horizontal = DesignTokens.ScreenPadding)
                    .fillMaxWidth()
                    .heightIn(min = 56.dp),
            ) { Text("删除我的数据", color = DesignTokens.Danger, fontWeight = FontWeight.Black) }
        }
        item { PaddedPanel("证据等级", "演示报价仅用于本地流程，不会升级为真实商业证据。") }
        item {
            Box(modifier = Modifier.padding(horizontal = DesignTokens.ScreenPadding)) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(DesignTokens.Surface)
                        .border(1.dp, DesignTokens.Ink)
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text("匿名质量数据", fontSize = 17.sp, fontWeight = FontWeight.Black)
                    Text(
                        "${if (state.qualityDataConsent) "已同意" else "未同意"}：仅用于改进本地演示质量，不包含商家交易数据。",
                        color = DesignTokens.TextSecondary,
                    )
                    OutlinedButton(
                        onClick = { onQualityDataConsentChanged(!state.qualityDataConsent) },
                        modifier = Modifier
                            .heightIn(min = DesignTokens.TouchTarget)
                            .testTag("quality_consent_${if (state.qualityDataConsent) "GRANTED" else "DENIED"}"),
                    ) { Text(if (state.qualityDataConsent) "撤回同意" else "同意使用") }
                }
            }
        }
        item { PaddedPanel("连接与恢复", "${connectionLabel(state.connection)} · 任务、清单与待购集合可恢复。") }
        item { Spacer(Modifier.height(20.dp)) }
    }
    if (deleteConfirmationVisible) {
        AlertDialog(
            onDismissRequest = { deleteConfirmationVisible = false },
            title = { Text("删除我的数据") },
            text = {
                Text("这会删除当前开发身份的 Mission、清单、待购、偏好和短期媒体引用。此操作不会下单或影响商家数据。")
            },
            confirmButton = {
                Button(onClick = { deleteConfirmationVisible = false; onDeleteMyData() }) {
                    Text("确认删除")
                }
            },
            dismissButton = {
                OutlinedButton(onClick = { deleteConfirmationVisible = false }) { Text("取消") }
            },
        )
    }
}

@Composable
private fun PaddedPanel(title: String, body: String) {
    Box(modifier = Modifier.padding(horizontal = DesignTokens.ScreenPadding)) {
        EditorialPanel(title, body, DesignTokens.Surface)
    }
}

@Composable
private fun EditorialPanel(title: String, body: String, color: Color) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(color)
            .border(1.dp, DesignTokens.Ink)
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        Text(title, fontSize = 17.sp, fontWeight = FontWeight.Black)
        Text(body, color = DesignTokens.TextSecondary)
    }
}

@Composable
private fun ConnectionReceipt(
    connection: ConnectionState,
    message: String,
    onAction: (ShoppingAction) -> Unit,
) {
    val color = when (connection) {
        ConnectionState.ONLINE, ConnectionState.RECOVERED -> DesignTokens.Lime
        else -> DesignTokens.WarningContainer
    }
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(color)
            .border(1.dp, DesignTokens.Ink)
            .padding(12.dp)
            .testTag("connection_${connection.name}"),
    ) {
        Text(connectionLabel(connection), fontWeight = FontWeight.Black)
        Text(message, color = DesignTokens.TextSecondary)
        if (connection == ConnectionState.OFFLINE) {
            OutlinedButton(
                onClick = { onAction(ShoppingAction.RetryConnection) },
                modifier = Modifier.heightIn(min = DesignTokens.TouchTarget).testTag("retry_connection"),
            ) { Text("重试连接") }
        }
        if (connection == ConnectionState.RECOVERED) RecoveryReceipt()
    }
}

@Composable
private fun ConnectionPill(connection: ConnectionState) {
    Box(
        modifier = Modifier
            .background(if (connection == ConnectionState.ONLINE || connection == ConnectionState.RECOVERED) DesignTokens.Lime else DesignTokens.WarningContainer)
            .border(1.dp, DesignTokens.Ink)
            .padding(horizontal = 10.dp, vertical = 6.dp)
            .testTag("connection_${connection.name}"),
    ) {
        Text(connectionLabel(connection), fontSize = 11.sp, fontWeight = FontWeight.Black)
    }
}

private fun connectionLabel(connection: ConnectionState): String = when (connection) {
    ConnectionState.CHECKING -> "正在连接"
    ConnectionState.ONLINE -> "已连接"
    ConnectionState.OFFLINE -> "连接中断"
    ConnectionState.RECONNECTING -> "正在恢复连接"
    ConnectionState.RECOVERED -> "任务已恢复"
}

private fun displayProductRisk(value: String): String =
    if (value == "DEMO_FIXTURE") "演示商品与报价，不代表商家实时信息" else value

@Composable
private fun RecoveryReceipt() {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(DesignTokens.Lime)
            .border(1.dp, DesignTokens.Ink)
            .padding(8.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text("已恢复", fontWeight = FontWeight.Black)
        Text("任务状态已载入", fontWeight = FontWeight.SemiBold)
    }
}

@Composable
@OptIn(ExperimentalMaterial3Api::class)
private fun ActionConfirmationSheet(
    action: PendingUserAction,
    merchantHost: String?,
    onCancel: () -> Unit,
    onConfirm: () -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = onCancel,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = DesignTokens.Surface,
        tonalElevation = 0.dp,
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().verticalScroll(rememberScrollState())
                .padding(horizontal = 22.dp, vertical = 14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("确认下一步", color = DesignTokens.Warning, fontSize = 11.sp, fontWeight = FontWeight.Black, letterSpacing = 1.6.sp)
            when (action) {
                is PendingUserAction.Save -> {
                    Text("保存候选方案？", fontSize = 28.sp, fontWeight = FontWeight.Black)
                    Text(action.product.title, fontWeight = FontWeight.Bold)
                    Text("只保存到你的 Agent 候选清单，不会下单或支付。", color = DesignTokens.TextSecondary)
                }
                is PendingUserAction.AddToPlan -> {
                    Text("加入待购计划？", fontSize = 28.sp, fontWeight = FontWeight.Black)
                    Text(action.offer.merchantName, fontWeight = FontWeight.Bold)
                    Text("${action.offer.priceText ?: "价格待确认"} · 数量 1", fontWeight = FontWeight.Black)
                    Text("这是演示报价，仅保存计划，不会下单或支付。", color = DesignTokens.TextSecondary)
                }
                is PendingUserAction.ChangeWaitingQuantity -> {
                    Text(if (action.quantity == 0) "移出待购计划？" else "修改计划数量？", fontSize = 28.sp, fontWeight = FontWeight.Black)
                    Text(action.offer.merchantName, fontWeight = FontWeight.Bold)
                    Text(if (action.quantity == 0) "只移除这条待购记录，不影响已保存方案。" else "数量改为 ${action.quantity}，确认后保存；不会下单或支付。", color = DesignTokens.TextSecondary)
                }
                is PendingUserAction.OpenSource -> {
                    Text("打开外部来源？", fontSize = 28.sp, fontWeight = FontWeight.Black)
                    Text(action.offer.merchantName, fontWeight = FontWeight.Bold)
                    Text(merchantHost?.let { "目标网站 · $it" } ?: "尚未核验目标网站，请等待或返回重新询价", fontWeight = FontWeight.Bold)
                    Text("确认后会重新验证链接并打开浏览器。演示来源不支持下单或支付。", color = DesignTokens.TextSecondary)
                }
            }
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(onClick = onCancel, modifier = Modifier.weight(1f).heightIn(min = 52.dp).testTag("cancel_user_action")) {
                    Text("取消", fontWeight = FontWeight.Bold)
                }
                Button(
                    onClick = onConfirm,
                    enabled = action !is PendingUserAction.OpenSource || merchantHost != null,
                    colors = ButtonDefaults.buttonColors(containerColor = DesignTokens.Emerald, contentColor = Color.White),
                    modifier = Modifier.weight(1f).heightIn(min = 52.dp).testTag("confirm_user_action"),
                ) { Text(when (action) {
                    is PendingUserAction.Save -> "确认保存"
                    is PendingUserAction.AddToPlan -> "确认加入"
                    is PendingUserAction.ChangeWaitingQuantity -> if (action.quantity == 0) "确认移除" else "确认修改"
                    is PendingUserAction.OpenSource -> "确认并打开"
                }, fontWeight = FontWeight.Black) }
            }
            Spacer(Modifier.height(12.dp))
        }
    }
}

@Composable
@OptIn(ExperimentalMaterial3Api::class)
private fun ApprovalSheet(
    tool: String,
    targetSummary: String?,
    onCancel: () -> Unit,
    onConfirm: () -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = onCancel,
        containerColor = DesignTokens.Surface,
        tonalElevation = 0.dp,
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 22.dp, vertical = 14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("操作确认", color = DesignTokens.Warning, fontSize = 11.sp, fontWeight = FontWeight.Black, letterSpacing = 1.6.sp)
            Text("确认执行操作", fontSize = 30.sp, lineHeight = 32.sp, fontWeight = FontWeight.Black)
            Text(targetSummary ?: "尚未取得完整操作对象，请取消后重新打开任务", fontWeight = FontWeight.Bold)
            Text(when (tool) {
                "cart.update" -> "按本次需求修改待购商品与数量，确认前不会写入。"
                "list.update" -> "按本次需求修改已保存方案，确认前不会写入。"
                "link.resolve" -> "核对报价和链接后前往演示商家，不会支付或下单。"
                "vision.identify" -> "读取你选择的图片以理解需求，不把图片作为报价证据。"
                "audio.transcribe" -> "读取你发送的录音以转写需求，转写内容仍需你确认。"
                else -> error("Unsupported approval tool")
            }, color = DesignTokens.TextSecondary)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Box(modifier = Modifier.background(DesignTokens.Lime).padding(horizontal = 10.dp, vertical = 6.dp)) {
                    Text("演示数据", fontWeight = FontWeight.Black)
                }
                Box(modifier = Modifier.background(DesignTokens.WarningContainer).padding(horizontal = 10.dp, vertical = 6.dp)) {
                    Text("不会支付或下单", fontWeight = FontWeight.Black)
                }
            }
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    onClick = onCancel,
                    modifier = Modifier.weight(1f).heightIn(min = 52.dp).testTag("agent_approval_cancel"),
                ) { Text("取消", fontWeight = FontWeight.Bold) }
                Button(
                    onClick = onConfirm,
                    enabled = targetSummary != null,
                    colors = ButtonDefaults.buttonColors(containerColor = DesignTokens.Emerald, contentColor = Color.White),
                    modifier = Modifier.weight(1f).heightIn(min = 52.dp).testTag("agent_approval_confirm"),
                ) { Text("确认并继续", fontWeight = FontWeight.Black) }
            }
            Spacer(Modifier.height(12.dp))
        }
    }
}
