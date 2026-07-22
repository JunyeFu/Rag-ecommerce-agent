package com.shopping.agent.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ReceiptLong
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.shopping.agent.core.network.NetworkConfig
import com.shopping.agent.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Request
import org.json.JSONObject
import com.shopping.agent.ui.components.GradientTopBar

private data class OrderLine(
    val productId: String,
    val title: String,
    val price: Double,
    val quantity: Int,
)

private data class OrderDetail(
    val orderNo: String,
    val status: String,
    val total: Double,
    val address: String,
    val createdAt: String,
    val items: List<OrderLine>,
)

@Composable
fun OrderDetailScreen(
    orderId: String,
    onBack: () -> Unit,
) {
    var isLoading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var order by remember { mutableStateOf<OrderDetail?>(null) }

    LaunchedEffect(orderId) {
        isLoading = true
        error = null
        try {
            order = withContext(Dispatchers.IO) { fetchOrderDetail(orderId) }
        } catch (e: Exception) {
            error = e.message ?: "订单加载失败"
        } finally {
            isLoading = false
        }
    }

    Scaffold(
        topBar = {
            GradientTopBar {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    IconButton(onClick = onBack, modifier = Modifier.size(36.dp)) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "返回", tint = MaterialTheme.colorScheme.onSurface)
                    }
                    Text("订单详情", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                }
            }
        },
    ) { padding ->
        when {
            isLoading -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = Primary)
            }
            error != null -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Text(error.orEmpty(), color = ErrorColor)
            }
            order != null -> {
                val detail = order!!
                LazyColumn(
                    modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).padding(padding),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    item {
                        Card(colors = CardDefaults.cardColors(containerColor = PrimaryLight)) {
                            Row(modifier = Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.CheckCircle, null, tint = Primary, modifier = Modifier.size(36.dp))
                                Spacer(Modifier.width(12.dp))
                                Column {
                                    Text("下单成功", style = MaterialTheme.typography.titleMedium, color = Primary, fontWeight = FontWeight.Bold)
                                    Text("订单号：${detail.orderNo}", style = MaterialTheme.typography.bodyMedium, color = Primary)
                                }
                            }
                        }
                    }
                    item {
                        OrderInfoCard(detail)
                    }
                    item {
                        Text("商品快照", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    }
                    items(detail.items, key = { it.productId }) { line ->
                        OrderLineCard(line)
                    }
                }
            }
        }
    }
}

@Composable
private fun OrderInfoCard(detail: OrderDetail) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(modifier = Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.AutoMirrored.Filled.ReceiptLong, null, tint = Primary)
                Spacer(Modifier.width(8.dp))
                Text("订单信息", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
            }
            InfoRow("状态", detail.status)
            InfoRow("收货地址", detail.address.ifBlank { "默认地址" })
            InfoRow("创建时间", detail.createdAt)
            InfoRow("实付金额", "¥${"%.2f".format(detail.total)}", valueColor = TextPrice)
        }
    }
}

@Composable
private fun InfoRow(label: String, value: String, valueColor: androidx.compose.ui.graphics.Color = MaterialTheme.colorScheme.onSurface) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.width(12.dp))
        Text(value, color = valueColor, maxLines = 2, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun OrderLineCard(line: OrderLine) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Row(modifier = Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text(line.title, style = MaterialTheme.typography.bodyMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Spacer(Modifier.height(6.dp))
                Text("¥${"%.2f".format(line.price)}", color = TextPrice, fontWeight = FontWeight.Bold)
            }
            Text("x${line.quantity}", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

private fun fetchOrderDetail(orderId: String): OrderDetail {
    val request = Request.Builder()
        .url("${NetworkConfig.BASE_URL}/api/v1/orders/$orderId")
        .get()
        .build()
    NetworkConfig.httpClient.newCall(request).execute().use { response ->
        if (!response.isSuccessful) throw IllegalStateException("订单加载失败 ${response.code}")
        val json = JSONObject(response.body?.string().orEmpty())
        val data = json.optJSONObject("data") ?: JSONObject()
        val rawItems = data.optJSONArray("items") ?: org.json.JSONArray()
        val lines = (0 until rawItems.length()).map { idx ->
            val item = rawItems.getJSONObject(idx)
            OrderLine(
                productId = item.optString("product_id"),
                title = item.optString("title"),
                price = item.optDouble("price"),
                quantity = item.optInt("quantity", 1),
            )
        }
        return OrderDetail(
            orderNo = data.optString("order_no"),
            status = data.optString("status"),
            total = data.optDouble("total"),
            address = data.optString("address"),
            createdAt = data.optString("created_at"),
            items = lines,
        )
    }
}
