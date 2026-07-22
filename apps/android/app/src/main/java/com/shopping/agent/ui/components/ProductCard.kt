package com.shopping.agent.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.shopping.agent.data.model.Citation
import com.shopping.agent.data.model.Product
import com.shopping.agent.ui.theme.*

@Composable
fun ProductCard(
    product: Product,
    onTap: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(onClick = onTap, shape = RadiusLg,
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        modifier = modifier.fillMaxWidth()) {
        Column {
            Box {
                AsyncImage(model = product.imageUrl, contentDescription = product.title,
                    modifier = Modifier.fillMaxWidth().aspectRatio(1f),
                    contentScale = ContentScale.Crop)
                Surface(Modifier.align(Alignment.BottomEnd).padding(8.dp),
                    shape = CircleShape, color = MaterialTheme.colorScheme.surface.copy(alpha = 0.9f)) {
                    Icon(Icons.Default.ChevronRight, "详情",
                        tint = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.size(24.dp))
                }
            }
            Column(modifier = Modifier.padding(Dimens.cardPadding)) {
                if (product.attributes.isNotEmpty()) {
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        product.attributes.values.take(3).forEach { tag ->
                            Surface(shape = RadiusSm, color = MaterialTheme.colorScheme.outlineVariant) {
                                Text(tag, Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                    Spacer(Modifier.height(Dimens.space1))
                }
                Text(product.title, style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurface, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Spacer(Modifier.height(Dimens.space1))
                Row(verticalAlignment = Alignment.Bottom) {
                    Text("到手价", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.width(4.dp))
                    Text("¥${product.price}", style = PriceMedium.copy(fontWeight = FontWeight.Bold),
                        color = TextPrice)
                }
                Spacer(Modifier.height(Dimens.space1))
                Row(verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    Surface(shape = RadiusSm, color = Color(0xFFEBF3FC)) {
                        Text(product.source, Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                            style = MaterialTheme.typography.bodySmall, color = Info)
                    }
                    if (product.ratingCount > 0) {
                        Text(formatSalesCount(product.ratingCount),
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                CitationSection(citations = product.citation)
            }
        }
    }
}

fun formatSalesCount(count: Int): String = when {
    count >= 10000 -> "${count / 10000}.${(count % 10000) / 1000}万人付款"
    else -> "${count}人付款"
}

/**
 * F7 引用来源展示区 - 商品卡片底部的检索溯源信息。
 *
 * 当后端 ProductCardEvent.citation 非空时渲染：以小号弱化文本列出每条引用的描述，
 * 不喧宾夺主，保持卡片主体内容的视觉优先级。
 */
@Composable
fun CitationSection(
    citations: List<Citation>,
    modifier: Modifier = Modifier,
) {
    if (citations.isEmpty()) return
    Column(modifier = modifier.fillMaxWidth().padding(top = Dimens.space2)) {
        HorizontalDivider(
            color = MaterialTheme.colorScheme.outlineVariant,
            thickness = 0.5.dp,
        )
        Spacer(Modifier.height(Dimens.space1))
        Text(
            text = "引用来源",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontWeight = FontWeight.Medium,
        )
        citations.forEach { citation ->
            Row(
                modifier = Modifier.padding(top = 2.dp).fillMaxWidth(),
                verticalAlignment = Alignment.Top,
            ) {
                Text(
                    text = "·",
                    style = MaterialTheme.typography.labelSmall,
                    color = Neutral400,
                )
                Spacer(Modifier.width(Dimens.space1))
                Text(
                    text = citation.description.ifBlank { citation.sourceType },
                    style = MaterialTheme.typography.labelSmall,
                    color = Neutral500,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}
