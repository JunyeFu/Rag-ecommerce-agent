package com.ragcommerce.agent

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
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
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
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
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.ragcommerce.agent.generated.CONTRACT_VERSION
import com.ragcommerce.agent.ui.CartGroupUi
import com.ragcommerce.agent.ui.ConnectionState
import com.ragcommerce.agent.ui.DesignTokens
import com.ragcommerce.agent.ui.EvidenceProductUi
import com.ragcommerce.agent.ui.OfferUi
import com.ragcommerce.agent.ui.PrimaryTab
import com.ragcommerce.agent.ui.QuoteState
import com.ragcommerce.agent.ui.ShoppingAction
import com.ragcommerce.agent.ui.ShoppingUiState

@Composable
fun EditorialShoppingApp(
    state: ShoppingUiState,
    onAction: (ShoppingAction) -> Unit,
    onOpenMerchant: (OfferUi) -> Unit,
    onSaveProduct: (EvidenceProductUi) -> Unit,
    onAddOffer: (OfferUi) -> Unit,
    onDeleteMyData: () -> Unit,
    onQualityDataConsentChanged: (Boolean) -> Unit,
    onPickImage: () -> Unit,
    onPickAudio: () -> Unit,
) {
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
            onSurface = DesignTokens.Ink,
            error = DesignTokens.Danger,
        ),
    ) {
        Scaffold(
            containerColor = DesignTokens.Bone,
            bottomBar = {
                if (!(state.selectedTab == PrimaryTab.TASK && state.products.isNotEmpty())) {
                    EditorialBottomBar(state.selectedTab, onAction)
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
                        onSaveProduct = onSaveProduct,
                        onAddOffer = onAddOffer,
                        onPickImage = onPickImage,
                        onPickAudio = onPickAudio,
                    )
                    PrimaryTab.DECISIONS -> EditorialDecisionScreen(
                        state = state,
                        onAction = onAction,
                        onOpenMerchant = onOpenMerchant,
                    )
                    PrimaryTab.PROFILE -> EditorialProfileScreen(state, onDeleteMyData, onQualityDataConsentChanged)
                }
            }
        }

        state.pendingApprovalTool?.let { tool ->
            ApprovalSheet(
                tool = tool,
                onCancel = { onAction(ShoppingAction.ResolveApproval(false)) },
                onConfirm = { onAction(ShoppingAction.ResolveApproval(true)) },
            )
        }
    }
}

@Composable
private fun EditorialBottomBar(
    selectedTab: PrimaryTab,
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
                    .testTag("tab_${tab.name}"),
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
        } else if (state.products.isNotEmpty()) {
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
                    state.missionGoal.ifBlank { "当前 Shopping Mission" },
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
                Text("上次进度：核验证据", color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                Text("任务已安全保存，事件从最后游标续接", color = Color.White.copy(alpha = 0.78f))
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
                Text("恢复凭证", color = DesignTokens.Emerald, fontSize = 18.sp, fontWeight = FontWeight.Black)
                Text("快照已校验", fontWeight = FontWeight.SemiBold)
                Text("事件已续接", fontWeight = FontWeight.SemiBold)
                Text("重复终态 0", fontWeight = FontWeight.SemiBold)
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
                if (state.missionGoal.isNotBlank()) {
                    EditorialPanel("当前 Mission", state.missionGoal, DesignTokens.Lime)
                }
                state.agentMessages.takeLast(3).forEach { message ->
                    EditorialPanel("Agent", message, DesignTokens.Surface)
                }
                state.evidenceRefs.takeLast(2).forEach { evidence ->
                    EditorialPanel("证据引用", evidence, DesignTokens.Surface)
                }
            }
        }
        if (state.isLoading) {
            item { AgentProgress() }
        }
        item {
            MissionComposer(state, onAction, onPickImage, onPickAudio)
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
                modifier = Modifier
                    .heightIn(min = DesignTokens.TouchTarget)
                    .semantics { contentDescription = "添加商品图片" },
            ) { Text("图片") }
            OutlinedButton(
                onClick = onPickAudio,
                modifier = Modifier
                    .heightIn(min = DesignTokens.TouchTarget)
                    .semantics { contentDescription = "添加语音" },
            ) { Text("语音") }
            Button(
                onClick = { onAction(ShoppingAction.SubmitMission) },
                enabled = state.draft.isNotBlank() || state.attachments.isNotEmpty(),
                colors = ButtonDefaults.buttonColors(
                    containerColor = DesignTokens.Emerald,
                    contentColor = Color.White,
                ),
                modifier = Modifier.heightIn(min = DesignTokens.TouchTarget).testTag("send_turn"),
            ) { Text("发送", fontWeight = FontWeight.Black) }
        }
        if (state.attachments.isNotEmpty()) {
            Text(
                "附件提交后由服务端生成短期引用，客户端不持久化原始媒体",
                color = DesignTokens.TextSecondary,
                fontSize = 12.sp,
            )
        }
    }
}

@Composable
private fun AgentProgress() {
    Column(
        modifier = Modifier
            .padding(horizontal = DesignTokens.ScreenPadding)
            .fillMaxWidth()
            .background(DesignTokens.Emerald)
            .padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Agent 分析中", color = DesignTokens.Lime, fontSize = 24.sp, fontWeight = FontWeight.Black)
        listOf("理解需求", "混合检索", "核验证据", "比较候选").forEachIndexed { index, stage ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("0${index + 1}", color = DesignTokens.Coral, fontWeight = FontWeight.Black)
                Text(stage, color = Color.White, fontWeight = FontWeight.SemiBold)
            }
        }
        Text("只展示公开执行阶段，不展示模型思维链", color = Color.White.copy(alpha = 0.68f), fontSize = 12.sp)
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
    val pagerState = rememberPagerState(pageCount = { rankedProducts.size })
    Column(modifier = Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(horizontal = DesignTokens.ScreenPadding, vertical = 10.dp),
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
            Text(
                state.missionGoal.ifBlank { "本次导购任务" },
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                color = DesignTokens.TextSecondary,
                fontWeight = FontWeight.SemiBold,
            )
            Text(state.statusMessage, color = DesignTokens.TextSecondary, fontSize = 12.sp)
            if (state.connection == ConnectionState.OFFLINE) {
                OutlinedButton(
                    onClick = { onAction(ShoppingAction.RetryConnection) },
                    modifier = Modifier.heightIn(min = DesignTokens.TouchTarget).testTag("retry_connection"),
                ) { Text("重试连接") }
            }
            if (state.connection == ConnectionState.RECOVERED) RecoveryReceipt()
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
            )
        }
    }
}

@Composable
private fun RecommendationPage(
    product: EvidenceProductUi,
    offer: OfferUi?,
    rank: Int,
    total: Int,
    selected: Boolean,
    onToggle: () -> Unit,
    onSave: () -> Unit,
    onAddOffer: () -> Unit,
) {
    val rankLabel = when (rank) {
        0 -> "主推荐"
        1 -> "次推荐"
        else -> "再次推荐"
    }
    val pagingHint = when (rank) {
        0 -> "下滑查看次推荐"
        1 -> "上滑返回主推荐 · 下滑查看再次推荐"
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
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(rankLabel, fontSize = 24.sp, fontWeight = FontWeight.Black)
            Text(
                "%02d / %02d".format(rank + 1, total),
                color = DesignTokens.Emerald,
                fontWeight = FontWeight.Black,
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
        if (product.title.contains("耳机") || product.title.contains("headphone", ignoreCase = true) || product.title.contains("earbud", ignoreCase = true)) {
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
                    contentDescription = product.title,
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
            }
        }
        Text(product.fitSummary, color = DesignTokens.TextSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
        product.matchedConstraints.take(1).forEach { constraint ->
            Text("满足 · $constraint", color = DesignTokens.Emerald, fontWeight = FontWeight.SemiBold)
        }
        product.unmetConstraints.take(1).forEach { constraint ->
            Text("未满足 · $constraint", color = DesignTokens.Warning, fontWeight = FontWeight.SemiBold)
        }
        product.risks.take(1).forEach { risk ->
            Text("风险 · $risk", color = DesignTokens.Coral, fontWeight = FontWeight.SemiBold)
        }
        product.evidenceRefs.take(2).forEach { ref ->
            Text("来源 $ref", fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
        }
        offer?.let {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(it.priceText ?: "价格待确认", fontSize = 26.sp, fontWeight = FontWeight.Black, color = DesignTokens.Emerald)
                Text(it.verification, fontSize = 12.sp, fontWeight = FontWeight.Black)
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(checked = selected, onCheckedChange = { onToggle() })
            Text("加入比较", fontWeight = FontWeight.Bold)
            Spacer(Modifier.weight(1f))
            OutlinedButton(
                onClick = onSave,
                modifier = Modifier.heightIn(min = DesignTokens.TouchTarget).testTag("save_${product.id}"),
            ) { Text("保存方案") }
        }
        if (offer != null) {
            Button(
                onClick = onAddOffer,
                enabled = offer.quoteState == QuoteState.CURRENT,
                colors = ButtonDefaults.buttonColors(containerColor = DesignTokens.Ink, contentColor = DesignTokens.Lime),
                modifier = Modifier.fillMaxWidth().heightIn(min = DesignTokens.TouchTarget).testTag("add_offer_${offer.id}"),
            ) { Text("加入待购集合", fontWeight = FontWeight.Black) }
        }
        Text(pagingHint, color = DesignTokens.TextSecondary, fontSize = 11.sp)
    }
}

@Composable
private fun EditorialDecisionScreen(
    state: ShoppingUiState,
    onAction: (ShoppingAction) -> Unit,
    onOpenMerchant: (OfferUi) -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize().testTag("screen_决策"),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            EditorialHeader(
                eyebrow = "DECISION WORKBENCH",
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
        if (state.comparedProductIds.size >= 2 || state.comparison != null) {
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
                    Text("${state.comparedProductIds.size.coerceAtLeast(state.comparison?.items?.size ?: 0)} 个候选")
                    state.comparison?.let { comparison ->
                        Text("缺失字段 ${comparison.missingFields.size} 项；只比较已返回事实")
                    }
                }
            }
        }
        item { EditorialSectionTitle("已保存方案", "SAVED") }
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
                    Text("来源 ${item.sourceRef}", color = DesignTokens.TextSecondary, fontSize = 12.sp)
                }
            }
        }
        item { EditorialSectionTitle("待购集合", "WAITING LIST") }
        if (state.cartGroups.isEmpty()) {
            item { PaddedPanel("待购集合为空", "此处不创建订单，不保存支付信息") }
        }
        items(state.cartGroups, key = { it.merchantName }) { group ->
            EditorialCartGroup(group, onAction, onOpenMerchant)
        }
        item { Spacer(Modifier.height(20.dp)) }
    }
}

@Composable
private fun EditorialSectionTitle(title: String, eyebrow: String) {
    Column(modifier = Modifier.padding(horizontal = DesignTokens.ScreenPadding)) {
        Text(eyebrow, color = DesignTokens.Coral, fontSize = 11.sp, fontWeight = FontWeight.Black, letterSpacing = 1.4.sp)
        Text(title, fontSize = 28.sp, fontWeight = FontWeight.Black)
    }
}

@Composable
private fun EditorialCartGroup(
    group: CartGroupUi,
    onAction: (ShoppingAction) -> Unit,
    onOpenMerchant: (OfferUi) -> Unit,
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
        Text(group.merchantName, fontSize = 20.sp, fontWeight = FontWeight.Black)
        group.offers.forEachIndexed { index, offer ->
            if (index > 0) HorizontalDivider(color = DesignTokens.Hairline)
            EditorialOfferCard(offer, onAction, onOpenMerchant)
        }
    }
}

@Composable
private fun EditorialOfferCard(
    offer: OfferUi,
    onAction: (ShoppingAction) -> Unit,
    onOpenMerchant: (OfferUi) -> Unit,
) {
    Column(modifier = Modifier.testTag("offer_${offer.id}"), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(offer.priceText ?: "价格待商家确认", fontSize = 28.sp, fontWeight = FontWeight.Black)
        offer.shippingText?.let { Text("运费 $it") }
        Text("${offer.verification} · 采集 ${offer.collectedAt}", fontSize = 12.sp)
        Text("有效至 ${offer.expiresAt}", fontSize = 12.sp)
        Text("来源 ${offer.sourceRef}", fontSize = 12.sp, color = DesignTokens.TextSecondary)
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
        Button(
            onClick = { onOpenMerchant(offer) },
            enabled = offer.mayResolve,
            colors = ButtonDefaults.buttonColors(containerColor = DesignTokens.Emerald, contentColor = Color.White),
            modifier = Modifier.heightIn(min = DesignTokens.TouchTarget).testTag("open_${offer.id}"),
        ) { Text("前往商家", fontWeight = FontWeight.Black) }
        Text(offer.disclosure, color = DesignTokens.TextSecondary, fontSize = 11.sp)
    }
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
        item { PaddedPanel("模型与数据声明", "当前不是 LIVE 环境") }
        item {
            OutlinedButton(
                onClick = { deleteConfirmationVisible = true },
                modifier = Modifier
                    .padding(horizontal = DesignTokens.ScreenPadding)
                    .fillMaxWidth()
                    .heightIn(min = 56.dp),
            ) { Text("删除我的数据", color = DesignTokens.Danger, fontWeight = FontWeight.Black) }
        }
        item { PaddedPanel("证据等级", "演示报价标记为 DEMO_FIXTURE，不会升级为真实商业证据。") }
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
        item { PaddedPanel("连接与恢复", "${state.connection.name} · Mission、清单、待购集合与最后事件游标可恢复。") }
        item {
            Text(
                "Contract $CONTRACT_VERSION",
                modifier = Modifier.padding(horizontal = DesignTokens.ScreenPadding),
                color = DesignTokens.TextSecondary,
                fontSize = 12.sp,
            )
        }
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
        Text(connection.name, fontWeight = FontWeight.Black)
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
        Text(connection.name, fontSize = 11.sp, fontWeight = FontWeight.Black)
    }
}

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
        Text("恢复凭证", fontWeight = FontWeight.SemiBold)
        Text("重复终态 0", fontWeight = FontWeight.SemiBold)
    }
}

@Composable
@OptIn(ExperimentalMaterial3Api::class)
private fun ApprovalSheet(
    tool: String,
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
            Text("ACTION APPROVAL", color = DesignTokens.Coral, fontSize = 11.sp, fontWeight = FontWeight.Black, letterSpacing = 1.6.sp)
            Text("确认执行操作", fontSize = 30.sp, lineHeight = 32.sp, fontWeight = FontWeight.Black)
            Text("工具 $tool 将修改可逆的导购状态。", color = DesignTokens.TextSecondary)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Box(modifier = Modifier.background(DesignTokens.Lime).padding(horizontal = 10.dp, vertical = 6.dp)) {
                    Text("DEMO_FIXTURE", fontWeight = FontWeight.Black)
                }
                Box(modifier = Modifier.background(DesignTokens.WarningContainer).padding(horizontal = 10.dp, vertical = 6.dp)) {
                    Text("不会支付或下单", fontWeight = FontWeight.Black)
                }
            }
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    onClick = onCancel,
                    modifier = Modifier.weight(1f).heightIn(min = 52.dp),
                ) { Text("取消", fontWeight = FontWeight.Bold) }
                Button(
                    onClick = onConfirm,
                    colors = ButtonDefaults.buttonColors(containerColor = DesignTokens.Emerald, contentColor = Color.White),
                    modifier = Modifier.weight(1f).heightIn(min = 52.dp),
                ) { Text("确认并继续", fontWeight = FontWeight.Black) }
            }
            Spacer(Modifier.height(12.dp))
        }
    }
}
