package com.ragcommerce.agent

import android.os.Bundle
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.List
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.ShoppingCart
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
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
import com.ragcommerce.agent.ui.ShoppingViewModel
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { ShoppingRoute() }
    }
}

@Composable
private fun ShoppingRoute(viewModel: ShoppingViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    LaunchedEffect(viewModel) {
        viewModel.merchantLinks.collect { link ->
            try {
                context.startActivity(
                    Intent(Intent.ACTION_VIEW, Uri.parse(link))
                        .addCategory(Intent.CATEGORY_BROWSABLE),
                )
            } catch (_: ActivityNotFoundException) {
                viewModel.reportMerchantLaunchFailure()
            }
        }
    }
    val imagePicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        uri?.let {
            viewModel.dispatch(
                ShoppingAction.AddAttachment(
                    com.ragcommerce.agent.ui.MediaAttachmentUi(
                        uri = it.toString(),
                        kind = "image",
                        displayName = it.lastPathSegment ?: "已选图片",
                    ),
                ),
            )
        }
    }
    val audioPicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        uri?.let {
            viewModel.dispatch(
                ShoppingAction.AddAttachment(
                    com.ragcommerce.agent.ui.MediaAttachmentUi(
                        uri = it.toString(),
                        kind = "audio",
                        displayName = it.lastPathSegment ?: "已选音频",
                    ),
                ),
            )
        }
    }
    ShoppingApp(
        state = state,
        onAction = viewModel::dispatch,
        onOpenMerchant = viewModel::openMerchant,
        onPickImage = { imagePicker.launch("image/*") },
        onPickAudio = { audioPicker.launch("audio/*") },
    )
}

@Composable
fun ShoppingApp(
    state: ShoppingUiState,
    onAction: (ShoppingAction) -> Unit,
    onOpenMerchant: (OfferUi) -> Unit = {},
    onPickImage: () -> Unit = {},
    onPickAudio: () -> Unit = {},
) {
    MaterialTheme(
        colorScheme = MaterialTheme.colorScheme.copy(
            primary = DesignTokens.Brand,
            primaryContainer = DesignTokens.BrandContainer,
            background = DesignTokens.Background,
            surface = DesignTokens.Surface,
            onBackground = DesignTokens.TextPrimary,
            onSurface = DesignTokens.TextPrimary,
        ),
    ) {
        Scaffold(
            containerColor = DesignTokens.Background,
            bottomBar = {
                NavigationBar(containerColor = DesignTokens.Surface) {
                    PrimaryTab.entries.forEach { tab ->
                        NavigationBarItem(
                            selected = state.selectedTab == tab,
                            onClick = { onAction(ShoppingAction.SelectTab(tab)) },
                            icon = {
                                Icon(
                                    imageVector = when (tab) {
                                        PrimaryTab.GUIDE -> Icons.Outlined.Search
                                        PrimaryTab.LISTS -> Icons.AutoMirrored.Outlined.List
                                        PrimaryTab.CART -> Icons.Outlined.ShoppingCart
                                        PrimaryTab.PROFILE -> Icons.Outlined.Person
                                    },
                                    contentDescription = null,
                                )
                            },
                            label = { Text(tab.label) },
                            modifier = Modifier
                                .heightIn(min = DesignTokens.TouchTarget)
                                .testTag("tab_${tab.name}"),
                        )
                    }
                }
            },
        ) { padding ->
            Surface(
                modifier = Modifier.fillMaxSize().padding(padding),
                color = DesignTokens.Background,
            ) {
                when (state.selectedTab) {
                    PrimaryTab.GUIDE -> GuideScreen(state, onAction, onPickImage, onPickAudio)
                    PrimaryTab.LISTS -> ListsScreen(state)
                    PrimaryTab.CART -> CartScreen(state, onAction, onOpenMerchant)
                    PrimaryTab.PROFILE -> ProfileScreen(state)
                }
            }
        }
    }
}

@Composable
private fun ScreenColumn(
    title: String,
    subtitle: String,
    content: @Composable () -> Unit,
) {
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = DesignTokens.ScreenPadding)
            .testTag("screen_$title"),
        verticalArrangement = Arrangement.spacedBy(DesignTokens.CardSpacing),
    ) {
        item {
            Column(modifier = Modifier.padding(top = 20.dp)) {
                Text(title, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
                Text(
                    subtitle,
                    style = MaterialTheme.typography.bodyMedium,
                    color = DesignTokens.TextSecondary,
                )
            }
        }
        item { content() }
        item { Box(modifier = Modifier.padding(bottom = 20.dp)) }
    }
}

@Composable
private fun GuideScreen(
    state: ShoppingUiState,
    onAction: (ShoppingAction) -> Unit,
    onPickImage: () -> Unit,
    onPickAudio: () -> Unit,
) {
    ScreenColumn(title = "导购", subtitle = "说清预算与用途，所有商业事实都带来源") {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            ConnectionBanner(state.connection, state.statusMessage)
            if (state.missionGoal.isNotBlank()) {
                EvidencePanel("当前 Mission", state.missionGoal)
            }
            state.agentMessages.forEach { EvidencePanel("Agent", it) }
            state.evidenceRefs.forEach { EvidencePanel("证据引用", it) }
            OutlinedTextField(
                value = state.draft,
                onValueChange = { onAction(ShoppingAction.UpdateDraft(it)) },
                label = { Text("预算、用途、硬约束") },
                minLines = 2,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 64.dp)
                    .testTag("mission_input"),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(
                    onClick = onPickImage,
                    modifier = Modifier.heightIn(min = DesignTokens.TouchTarget)
                        .semantics { contentDescription = "添加商品图片" },
                ) { Text("图片") }
                OutlinedButton(
                    onClick = onPickAudio,
                    modifier = Modifier.heightIn(min = DesignTokens.TouchTarget)
                        .semantics { contentDescription = "添加语音" },
                ) { Text("语音") }
                Button(
                    onClick = { onAction(ShoppingAction.SubmitMission) },
                    enabled = state.draft.isNotBlank() || state.attachments.isNotEmpty(),
                    modifier = Modifier.heightIn(min = DesignTokens.TouchTarget).testTag("send_turn"),
                ) { Text("发送") }
            }
            state.attachments.forEach { attachment ->
                Card(
                    modifier = Modifier.fillMaxWidth().testTag("attachment_${attachment.kind}"),
                    colors = CardDefaults.cardColors(containerColor = DesignTokens.Surface),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Column(modifier = Modifier.fillMaxWidth(0.68f)) {
                            Text(if (attachment.kind == "image") "图片附件" else "音频附件")
                            Text(
                                attachment.displayName.take(80),
                                style = MaterialTheme.typography.labelMedium,
                                color = DesignTokens.TextSecondary,
                            )
                        }
                        OutlinedButton(
                            onClick = { onAction(ShoppingAction.RemoveAttachment(attachment.uri)) },
                            modifier = Modifier.heightIn(min = DesignTokens.TouchTarget),
                        ) { Text("移除") }
                    }
                }
            }
            if (state.attachments.isNotEmpty()) {
                Text(
                    "附件提交后由服务端生成短期引用，客户端不持久化原始媒体",
                    style = MaterialTheme.typography.labelMedium,
                    color = DesignTokens.TextSecondary,
                )
            }
            state.pendingApprovalTool?.let { tool ->
                EvidencePanel("需要明确确认", "受控工具 $tool 将修改可逆状态")
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(
                        onClick = { onAction(ShoppingAction.ResolveApproval(false)) },
                        modifier = Modifier.heightIn(min = DesignTokens.TouchTarget),
                    ) { Text("拒绝") }
                    Button(
                        onClick = { onAction(ShoppingAction.ResolveApproval(true)) },
                        modifier = Modifier.heightIn(min = DesignTokens.TouchTarget),
                    ) { Text("确认执行") }
                }
            }
            if (state.isLoading) EvidencePanel("正在检索", "保持硬约束，等待证据结果")
            if (!state.isLoading && state.products.isEmpty()) {
                EvidencePanel("还没有推荐", "输入任务后，Agent 会返回可核验商品与来源")
            }
            state.products.forEach { product ->
                ProductEvidenceCard(
                    product = product,
                    selected = product.id in state.comparedProductIds,
                    onToggle = { onAction(ShoppingAction.ToggleCompare(product.id)) },
                )
            }
            if (state.comparedProductIds.size >= 2) {
                EvidencePanel("比较工作台", "只比较工具返回的规格与证据，不补全缺失字段")
            }
        }
    }
}

@Composable
private fun ConnectionBanner(connection: ConnectionState, message: String) {
    val warning = connection != ConnectionState.ONLINE && connection != ConnectionState.RECOVERED
    Card(
        modifier = Modifier.fillMaxWidth().testTag("connection_${connection.name}"),
        colors = CardDefaults.cardColors(containerColor = DesignTokens.Surface),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(if (warning) DesignTokens.WarningContainer else DesignTokens.BrandContainer)
                .padding(16.dp),
        ) {
            Text(connection.name, style = MaterialTheme.typography.labelLarge)
            Text(message, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun EvidencePanel(title: String, body: String) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = DesignTokens.Surface),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, fontWeight = FontWeight.SemiBold)
            Text(body, color = DesignTokens.TextSecondary)
        }
    }
}

@Composable
private fun ProductEvidenceCard(
    product: EvidenceProductUi,
    selected: Boolean,
    onToggle: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth().testTag("product_${product.id}"),
        colors = CardDefaults.cardColors(containerColor = DesignTokens.Surface),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(product.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            product.reasons.forEach { Text("• $it", style = MaterialTheme.typography.bodyMedium) }
            Text("来源 ${product.sourceRef}", style = MaterialTheme.typography.labelMedium)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = selected, onCheckedChange = { onToggle() })
                Text("加入比较（最多 4 项）")
            }
        }
    }
}

@Composable
private fun ListsScreen(state: ShoppingUiState) {
    ScreenColumn(title = "清单", subtitle = "跨平台候选，不等于已下单") {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (state.savedProducts.isEmpty()) {
                EvidencePanel("清单为空", "从有证据的商品卡加入，来源会随条目保存")
            }
            state.savedProducts.forEach { item ->
                Card(
                    modifier = Modifier.fillMaxWidth().testTag("saved_${item.id}"),
                    colors = CardDefaults.cardColors(containerColor = DesignTokens.Surface),
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(item.title, fontWeight = FontWeight.SemiBold)
                        Text("来源 ${item.sourceRef}", style = MaterialTheme.typography.labelMedium)
                    }
                }
            }
        }
    }
}

@Composable
private fun CartScreen(
    state: ShoppingUiState,
    onAction: (ShoppingAction) -> Unit,
    onOpenMerchant: (OfferUi) -> Unit,
) {
    ScreenColumn(title = "购物车", subtitle = "按商家分组的跨站待购集合，跳转前重新询价") {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (state.cartGroups.isEmpty()) {
                EvidencePanel("待购集合为空", "此处不创建订单，不保存支付信息")
            }
            state.cartGroups.forEach { group ->
                CartGroup(group, onAction, onOpenMerchant)
            }
        }
    }
}

@Composable
private fun CartGroup(
    group: CartGroupUi,
    onAction: (ShoppingAction) -> Unit,
    onOpenMerchant: (OfferUi) -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth().testTag("merchant_${group.merchantName}"),
        colors = CardDefaults.cardColors(containerColor = DesignTokens.Surface),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(group.merchantName, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            group.offers.forEachIndexed { index, offer ->
                if (index > 0) HorizontalDivider()
                OfferCard(offer, onAction, onOpenMerchant)
            }
        }
    }
}

@Composable
private fun OfferCard(
    offer: OfferUi,
    onAction: (ShoppingAction) -> Unit,
    onOpenMerchant: (OfferUi) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.testTag("offer_${offer.id}")) {
        Text(offer.priceText ?: "价格待商家确认", style = MaterialTheme.typography.titleLarge)
        offer.shippingText?.let { Text("运费 $it") }
        Text("${offer.verification} · 采集 ${offer.collectedAt}")
        Text("有效至 ${offer.expiresAt}")
        Text("来源 ${offer.sourceRef}", style = MaterialTheme.typography.labelMedium)
        if (offer.quoteState == QuoteState.CHANGED && !offer.confirmedChange) {
            Text("价格或库存已变化，已阻断跳转", color = DesignTokens.Warning)
            Button(
                onClick = { onAction(ShoppingAction.ConfirmQuoteChange(offer.id)) },
                modifier = Modifier.heightIn(min = DesignTokens.TouchTarget)
                    .testTag("confirm_quote_${offer.id}"),
            ) { Text("确认价格变化") }
        }
        if (offer.quoteState in setOf(QuoteState.EXPIRED, QuoteState.UNAVAILABLE)) {
            Text("报价已失效或不可用，请重新询价", color = DesignTokens.Danger)
        }
        Button(
            onClick = { onOpenMerchant(offer) },
            enabled = offer.mayResolve,
            modifier = Modifier.heightIn(min = DesignTokens.TouchTarget).testTag("open_${offer.id}"),
        ) { Text("前往商家") }
        Text(offer.disclosure, style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
private fun ProfileScreen(state: ShoppingUiState) {
    ScreenColumn(title = "我的", subtitle = "隐私、来源和连接设置") {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            EvidencePanel("长期偏好", "仅在明确同意后保存，可请求删除")
            EvidencePanel("商业来源", "价格、库存、物流、保障和店铺身份不由客户端推导")
            EvidencePanel("本地恢复", "Mission、清单、待购集合与最后事件游标可恢复")
            EvidencePanel("连接状态", state.connection.name)
            Text("Contract $CONTRACT_VERSION", style = MaterialTheme.typography.labelMedium)
        }
    }
}
