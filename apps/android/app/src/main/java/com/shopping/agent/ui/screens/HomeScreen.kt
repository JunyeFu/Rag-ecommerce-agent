package com.shopping.agent.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.VolumeOff
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.shopping.agent.ui.components.*
import com.shopping.agent.ui.navigation.LocalOnMenuClick
import com.shopping.agent.ui.theme.*
import com.shopping.agent.viewmodel.ChatViewModel
import com.shopping.agent.viewmodel.GuideUiState
import com.shopping.agent.viewmodel.ScreenState

@Composable
fun HomeScreen(
    chatViewModel: ChatViewModel,
    onProductTap: (String) -> Unit = {},
    onCheckoutRequested: () -> Unit = {},
) {
    val uiState by chatViewModel.uiState.collectAsState()

    // 首次进入时尝试发送问候（ViewModel 内部保证有历史消息时不覆盖）
    LaunchedEffect(Unit) {
        chatViewModel.sendDailyGreeting()
    }

    LaunchedEffect(uiState.checkoutNavigationRequest) {
        if (uiState.checkoutNavigationRequest > 0) {
            onCheckoutRequested()
            chatViewModel.consumeCheckoutNavigation()
        }
    }

    // ── 统一 Column 布局（与比价页一致）──
    Column(modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        // ===== 渐变条 (与比价页位置一致) =====
        GradientTopBar(icons = {
            IconButton(onClick = LocalOnMenuClick.current, modifier = Modifier.size(34.dp)) {
                Icon(Icons.Default.Menu, "菜单", tint = MaterialTheme.colorScheme.onSurface, modifier = Modifier.size(26.dp))
            }
            Row {
                IconButton(
                    onClick = { chatViewModel.toggleTts() },
                    modifier = Modifier.size(34.dp)
                ) {
                    Icon(
                        imageVector = if (uiState.ttsEnabled) Icons.AutoMirrored.Filled.VolumeUp else Icons.AutoMirrored.Filled.VolumeOff,
                        contentDescription = "语音播报",
                        tint = if (uiState.ttsEnabled) Primary else MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.size(26.dp)
                    )
                }
            }
        })

        // ===== 演示模式横幅 =====
        val themeState = LocalThemeState.current
        if (themeState.isDemoMode.value) {
            Surface(
                color = Warning,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(
                    "演示模式",
                    color = OnPrimary,
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 4.dp),
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                )
            }
        }

        // ===== 内容区 (占满剩余空间) =====
        if (uiState.screenState is ScreenState.Error && uiState.messages.isEmpty()) {
            // 错误态：无历史消息时，居中展示错误信息和重试按钮
            Box(
                modifier = Modifier.weight(1f).fillMaxWidth(),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    val errorMsg = (uiState.screenState as ScreenState.Error).message
                    Text(
                        errorMsg,
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                        modifier = Modifier.padding(horizontal = 32.dp),
                    )
                    Spacer(Modifier.height(16.dp))
                    OutlinedButton(onClick = { chatViewModel.retryLastMessage() }) {
                        Text("重试", color = Primary)
                    }
                }
            }
        } else if (uiState.messages.isEmpty() && !uiState.isStreaming) {
            // 空态 — 在渐变条和搜索栏之间居中
            Box(
                modifier = Modifier.weight(1f).fillMaxWidth(),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("输入商品需求",
                        style = MaterialTheme.typography.headlineMedium,
                        color = MaterialTheme.colorScheme.onSurface)
                    Spacer(Modifier.height(8.dp))
                    Text("AI 为你精准推荐",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(32.dp))
                    Surface(
                        onClick = {
                            chatViewModel.onInputChange("推荐一款降噪耳机")
                            chatViewModel.sendMessage()
                        },
                        shape = RadiusLg,
                        color = PrimaryLight,
                        modifier = Modifier.padding(horizontal = 32.dp),
                    ) {
                        Text(
                            "试试：推荐一款降噪耳机",
                            style = MaterialTheme.typography.bodyMedium,
                            color = Primary,
                            modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
                        )
                    }
                }
            }
        } else {
            ChatMessageList(uiState = uiState, chatViewModel = chatViewModel,
                onProductTap = onProductTap, modifier = Modifier.weight(1f))
        }

        // ===== 底部搜索栏 (与比价页位置一致) =====
        ChatInputBar(
            chatViewModel = chatViewModel,
            placeholder = "输入商品需求…",
            showIcons = true,
        )
    }
}

@Composable
private fun ChatMessageList(
    uiState: GuideUiState,
    chatViewModel: ChatViewModel,
    onProductTap: (String) -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val listState = rememberLazyListState()
    LaunchedEffect(uiState.messages.size, uiState.streamingText) {
        val c = listState.layoutInfo.totalItemsCount
        if (c > 0) listState.animateScrollToItem(c - 1)
    }
    LazyColumn(state = listState, modifier = modifier.fillMaxWidth(),
        contentPadding = PaddingValues(horizontal = Dimens.pageHorizontal, vertical = Dimens.space2),
        verticalArrangement = Arrangement.spacedBy(Dimens.space3)) {
        items(uiState.messages, key = { it.id }) { msg ->
            MessageBubble(message = msg, onProductTap = { onProductTap(it.productId) })
        }
        if (uiState.isStreaming) {
            item(key = "streaming") {
                StreamingBubble(text = uiState.streamingText, isActive = true,
                    searchStatus = uiState.searchStatus,
                    productCards = uiState.streamingCards, onProductTap = { onProductTap(it.productId) })
            }
        }
        if (uiState.clarifyChips.isNotEmpty() || uiState.clarifyQuestion.isNotEmpty()) {
            item(key = "clarify") {
                Column(modifier = Modifier.padding(horizontal = Dimens.space2)) {
                    if (uiState.clarifyQuestion.isNotEmpty()) {
                        Surface(
                            shape = AgentBubbleShape,
                            color = MaterialTheme.colorScheme.surface,
                            shadowElevation = 2.dp,
                            modifier = Modifier.widthIn(max = Dimens.messageBubbleMaxWidth)
                        ) {
                            Column(modifier = Modifier.padding(Dimens.space3)) {
                                Text(
                                    "🤔 ${uiState.clarifyQuestion}",
                                    style = MaterialTheme.typography.bodyLarge,
                                    color = MaterialTheme.colorScheme.onSurface,
                                    fontWeight = FontWeight.Medium,
                                )
                            }
                        }
                        Spacer(Modifier.height(Dimens.space2))
                    }
                    if (uiState.clarifyChips.isNotEmpty()) {
                        Row(
                            horizontalArrangement = Arrangement.spacedBy(Dimens.space2),
                            modifier = Modifier.padding(start = Dimens.space2)
                        ) {
                            uiState.clarifyChips.forEach { chip ->
                                AssistChip(
                                    onClick = { chatViewModel.onClarifyChipClick(chip) },
                                    label = { Text(chip) },
                                    shape = RadiusFull,
                                    colors = AssistChipDefaults.assistChipColors(
                                        containerColor = PrimaryLight,
                                        labelColor = Primary
                                    )
                                )
                            }
                        }
                    }
                }
            }
        }
        // 有历史消息时错误态展示为底部可重试提示
        if (uiState.screenState is ScreenState.Error && uiState.messages.isNotEmpty()) {
            item(key = "error_retry") {
                Surface(
                    shape = RadiusLg,
                    color = MaterialTheme.colorScheme.surface,
                    shadowElevation = 2.dp,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Row(
                        modifier = Modifier.padding(Dimens.space3),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            (uiState.screenState as ScreenState.Error).message,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.weight(1f),
                        )
                        Spacer(Modifier.width(12.dp))
                        OutlinedButton(onClick = { chatViewModel.retryLastMessage() }) {
                            Text("重试", color = Primary)
                        }
                    }
                }
            }
        }
    }
}
