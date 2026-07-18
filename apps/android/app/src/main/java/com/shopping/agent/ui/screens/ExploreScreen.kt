package com.shopping.agent.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.shopping.agent.data.mock.MockExplorePosts
import com.shopping.agent.ui.components.ChatInputBar
import com.shopping.agent.ui.components.GradientTopBar
import com.shopping.agent.ui.navigation.LocalOnMenuClick
import com.shopping.agent.ui.theme.*
import com.shopping.agent.viewmodel.ChatViewModel
import kotlin.random.Random

private val CARD = 110.dp
private val GAP = 8.dp
private val STEP = CARD + GAP
private const val COLS = 12
private val ROWS: Int get() = (100 + COLS - 1) / COLS  // ceil(100/12) = 9

/** 随机不重叠布局数据 */
data class CardPlacement(val row: Int, val col: Int, val postIndex: Int)

@Composable
fun ExploreScreen(
    chatViewModel: ChatViewModel,
    onChatSend: () -> Unit,
    onPostClick: (String) -> Unit = {},
) {
    // 使用固定种子生成可重复的随机布局
    val placements = remember {
        val rng = Random(42)
        val grid = Array(ROWS) { BooleanArray(COLS) }
        val result = mutableListOf<CardPlacement>()

        // 随机打乱帖子索引
        val indices = (0 until 100).toMutableList()
        indices.shuffle(rng)

        for (idx in indices.take(100)) {
            // 随机尝试放置
            var placed = false
            val attempts = (ROWS * COLS * 2).coerceAtMost(500)
            for (attempt in 0 until attempts) {
                val r = rng.nextInt(ROWS)
                val c = rng.nextInt(COLS)
                if (!grid[r][c]) {
                    grid[r][c] = true
                    result.add(CardPlacement(r, c, idx))
                    placed = true
                    break
                }
            }
        }
        result
    }

    val sh = rememberScrollState()
    val sv = rememberScrollState()
    val d = LocalDensity.current

    // 初始居中
    LaunchedEffect(Unit) {
        val gp = with(d) { STEP.roundToPx() }
        val midC = COLS / 2
        val midR = ROWS / 2
        sh.scrollTo((midC * gp).coerceAtLeast(0))
        sv.scrollTo((midR * gp).coerceAtLeast(0))
    }

    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        GradientTopBar(icons = {
            IconButton(onClick = LocalOnMenuClick.current, modifier = Modifier.size(34.dp)) {
                Icon(Icons.Default.Menu, "菜单", tint = MaterialTheme.colorScheme.onSurface, modifier = Modifier.size(26.dp))
            }
        })

        // 随机卡片网格
        Box(
            Modifier.weight(1f).horizontalScroll(sh).verticalScroll(sv)
                .background(MaterialTheme.colorScheme.outlineVariant)
        ) {
            val gridW = STEP * COLS
            val gridH = STEP * ROWS
            Box(Modifier.size(width = gridW, height = gridH)) {
                // 虚线连接
                Canvas(Modifier.fillMaxSize()) {
                    // 简化：不画连接线，专注卡片展示
                }

                placements.forEach { p ->
                    val post = MockExplorePosts.posts.getOrNull(p.postIndex) ?: return@forEach
                    val x = STEP * p.col + 4.dp
                    val y = STEP * p.row + 4.dp

                    Box(Modifier.offset(x, y).size(CARD)) {
                        Card(
                            onClick = { onPostClick(post.postId) },
                            shape = RadiusMd,
                            elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
                        ) {
                            Column {
                                // 商品图
                                AsyncImage(
                                    model = post.product.images.firstOrNull() ?: "",
                                    contentDescription = post.product.title,
                                    modifier = Modifier.fillMaxWidth().aspectRatio(1f),
                                    contentScale = ContentScale.Crop,
                                )
                                // 底部信息
                                Column(Modifier.padding(6.dp)) {
                                    // 作者行
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Surface(
                                            modifier = Modifier.size(16.dp),
                                            shape = CircleShape,
                                            color = PrimaryLight,
                                        ) {
                                            Box(contentAlignment = Alignment.Center) {
                                                Text(
                                                    post.author.name.take(1),
                                                    style = MaterialTheme.typography.labelSmall,
                                                    color = Primary,
                                                    fontWeight = FontWeight.Bold,
                                                )
                                            }
                                        }
                                        Spacer(Modifier.width(4.dp))
                                        Text(
                                            post.author.name,
                                            style = MaterialTheme.typography.labelSmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                                            maxLines = 1,
                                            overflow = TextOverflow.Ellipsis,
                                        )
                                    }
                                    Spacer(Modifier.height(2.dp))
                                    Text(
                                        post.product.title.take(8),
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurface,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }

        // 底部搜索栏
        ChatInputBar(
            chatViewModel = chatViewModel,
            onSendRequested = onChatSend,
            placeholder = "搜索想探索的好物…",
            showIcons = true,
        )
    }
}
