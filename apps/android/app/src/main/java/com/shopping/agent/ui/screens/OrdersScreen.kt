package com.shopping.agent.ui.screens

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.shopping.agent.core.network.NetworkConfig
import com.shopping.agent.data.local.UserRepository
import com.shopping.agent.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

/* ═══════════════════════════════════════════════════════════ */
/*         订单展示数据结构                                      */
/* ═══════════════════════════════════════════════════════════ */

/** 订单中单个商品的数据快照 — 从 order_body JSON 解析得到 */
private data class OrderItemSnapshot(
    val productId: String = "",
    val title: String = "",
    val price: Double = 0.0,
    val quantity: Int = 1,
    val imageUrl: String = "",
)

/** 订单列表展示数据 — 从 order_body JSON 解析得到 */
private data class OrderDisplayData(
    val orderId: Long,
    val backendOrderNo: String,
    val totalPrice: Double,
    val totalCount: Int,
    val firstProductId: String,
    val firstProductImage: String,
    val firstProductTitle: String,
    val hasMoreItems: Boolean,
    val status: String,
    val rawOrderBody: String = "",  // 原始 order_body JSON，用于再次购买时解析所有商品
)

/* ═══════════════════════════════════════════════════════════ */
/*         状态筛选配置                                          */
/* ═══════════════════════════════════════════════════════════ */

/** 订单筛选选项卡配置 */
private data class OrderFilterTab(
    val label: String,
    val statusKey: String,
    val statusFilters: List<String>,  // 对应的 OrderStatus 值列表
)

/** 五个筛选选项卡 — 与 AGENTS.md 规格一致 */
private val FILTER_TABS = listOf(
    OrderFilterTab("待付款", "unpaid", listOf(UserRepository.OrderStatus.PENDING_PAYMENT)),
    OrderFilterTab("待发货", "shipping", listOf(UserRepository.OrderStatus.PENDING_SHIPPING)),
    OrderFilterTab("待收货", "receiving", listOf(UserRepository.OrderStatus.PENDING_RECEIPT)),
    OrderFilterTab("待评价", "comment", listOf(UserRepository.OrderStatus.PENDING_REVIEW)),
    OrderFilterTab("退款/售后", "refund", listOf(UserRepository.OrderStatus.COMPLETED, UserRepository.OrderStatus.CANCELLED)),
)

/* ═══════════════════════════════════════════════════════════ */
/*         主 Composable                                         */
/* ═══════════════════════════════════════════════════════════ */

/**
 * 我的订单页面。
 *
 * 布局结构：
 * - 顶部栏第一行：< 返回 + "我的订单"标题
 * - 顶部栏第二行：5个状态筛选选项卡（等宽排列）
 * - 主体：订单卡片列表（按时间倒序）
 * - 空状态："您还没有相关订单"
 *
 * @param statusFilter 初始筛选状态键（从导航参数传入），空字符串表示全部
 * @param onBack 返回回调
 * @param onProductClick 点击商品回调，传入商品 ID
 * @param onBuyAgain 再次购买回调（加入购物车后跳转至购物车页面）
 * @param onReview 评价晒单回调，传入订单数据
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun OrdersScreen(
    statusFilter: String = "",
    onBack: () -> Unit = {},
    onProductClick: (String) -> Unit = {},
    onBuyAgain: () -> Unit = {},
    onReview: (orderId: Long, backendOrderNo: String, productId: String, productTitle: String, productImage: String) -> Unit = { _, _, _, _, _ -> },
) {
    val context = LocalContext.current
    val repository = remember { UserRepository(context) }
    val scope = rememberCoroutineScope()

    // 当前选中的筛选 tab 状态键，null 表示显示全部
    var selectedTab by remember { mutableStateOf<String?>(statusFilter.takeIf { it.isNotEmpty() }) }
    var displayOrders by remember { mutableStateOf<List<OrderDisplayData>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }

    // 取消订单弹窗状态
    var cancelDialogOrder by remember { mutableStateOf<OrderDisplayData?>(null) }

    /** 从 SQLite 加载订单并解析展示数据 */
    fun loadOrders(filterKey: String?) {
        scope.launch {
            isLoading = true
            try {
                val records = withContext(Dispatchers.IO) {
                    // 根据筛选键获取对应的状态列表
                    val statusFilterList = if (filterKey != null) {
                        FILTER_TABS.find { it.statusKey == filterKey }?.statusFilters ?: emptyList()
                    } else {
                        emptyList()
                    }
                    // 逐个状态查询，合并结果（按 created_at DESC 排序）
                    if (statusFilterList.isNotEmpty()) {
                        val allRecords = mutableListOf<UserRepository.OrderRecord>()
                        statusFilterList.forEach { status ->
                            allRecords.addAll(repository.getOrderRecords(statusFilter = status))
                        }
                        allRecords.sortedByDescending { it.createdAt }
                    } else {
                        repository.getOrderRecords(statusFilter = null)
                    }
                }
                // 解析 order_body JSON 为展示数据
                val parsed = records.mapNotNull { record -> parseOrderBody(record) }
                displayOrders = parsed
            } catch (_: Exception) {
                displayOrders = emptyList()
            }
            isLoading = false
        }
    }

    // 初始加载
    LaunchedEffect(Unit) {
        loadOrders(selectedTab)
    }

    // 监听 selectedTab 变化，重新加载
    LaunchedEffect(selectedTab) {
        loadOrders(selectedTab)
    }

    // 取消订单确认弹窗
    if (cancelDialogOrder != null) {
        AlertDialog(
            onDismissRequest = { cancelDialogOrder = null },
            title = { Text("真的要取消订单吗？") },
            confirmButton = {
                TextButton(
                    onClick = {
                        val order = cancelDialogOrder ?: return@TextButton
                        scope.launch {
                            try {
                                withContext(Dispatchers.IO) {
                                    // 1. 先调后端 API 取消订单
                                    repository.cancelOrderOnBackend(order.backendOrderNo)
                                    // 2. 更新前端 SQLite 状态为已取消
                                    repository.updateOrderStatus(
                                        order.orderId,
                                        UserRepository.OrderStatus.CANCELLED,
                                    )
                                }
                                Toast.makeText(context, "订单已取消", Toast.LENGTH_SHORT).show()
                                loadOrders(selectedTab)
                            } catch (_: Exception) {
                                Toast.makeText(context, "取消订单失败", Toast.LENGTH_SHORT).show()
                            }
                        }
                        cancelDialogOrder = null
                    },
                ) {
                    Text("确认取消", color = Primary)
                }
            },
            dismissButton = {
                TextButton(onClick = { cancelDialogOrder = null }) {
                    Text("取消")
                }
            },
        )
    }

    Scaffold(
        topBar = {
            Column(
                modifier = Modifier
                    .background(MaterialTheme.colorScheme.surface)
                    .padding(top = 8.dp, bottom = 4.dp),
            ) {
                // 第一行：返回 + 标题
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(48.dp)
                        .padding(horizontal = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    IconButton(onClick = onBack, modifier = Modifier.size(40.dp)) {
                        Icon(
                            Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "返回",
                            tint = MaterialTheme.colorScheme.onSurface,
                        )
                    }
                    Text(
                        "我的订单",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurface,
                    )
                }
                // 第二行：筛选选项卡（等宽排列，间距约 3%-5%）
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp, vertical = 4.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    FILTER_TABS.forEach { tab ->
                        val isSelected = selectedTab == tab.statusKey
                        Button(
                            onClick = {
                                selectedTab = if (isSelected) null else tab.statusKey
                            },
                            colors = ButtonDefaults.buttonColors(
                                containerColor = if (isSelected) Primary else MaterialTheme.colorScheme.surfaceVariant,
                                contentColor = if (isSelected) OnPrimary else MaterialTheme.colorScheme.onSurface,
                            ),
                            shape = RoundedCornerShape(20.dp),
                            modifier = Modifier
                                .weight(1f)
                                .height(34.dp),
                            contentPadding = PaddingValues(horizontal = 4.dp, vertical = 0.dp),
                        ) {
                            Text(
                                tab.label,
                                style = MaterialTheme.typography.bodySmall,
                                maxLines = 1,
                            )
                        }
                    }
                }
            }
        },
    ) { padding ->
        when {
            isLoading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator(color = Primary)
                }
            }
            displayOrders.isEmpty() -> {
                // 空状态
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        "您还没有相关订单",
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            else -> {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(MaterialTheme.colorScheme.background)
                        .padding(padding),
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    items(displayOrders, key = { it.orderId }) { order ->
                        OrderCard(
                            order = order,
                            onProductClick = {
                                // 点击商品跳转至商品详情页（取第一个商品的 productId）
                                onProductClick(order.firstProductId)
                            },
                            onConfirmReceipt = {
                                scope.launch {
                                    try {
                                        withContext(Dispatchers.IO) {
                                            repository.updateOrderStatusOnBackend(
                                                order.backendOrderNo,
                                                UserRepository.OrderStatus.PENDING_REVIEW,
                                            )
                                            repository.updateOrderStatus(
                                                order.orderId,
                                                UserRepository.OrderStatus.PENDING_REVIEW,
                                            )
                                        }
                                        // 刷新列表
                                        loadOrders(selectedTab)
                                    } catch (_: Exception) {
                                        Toast.makeText(context, "操作失败", Toast.LENGTH_SHORT).show()
                                    }
                                }
                            },
                            onUrgeShipping = {
                                scope.launch {
                                    try {
                                        withContext(Dispatchers.IO) {
                                            repository.updateOrderStatusOnBackend(
                                                order.backendOrderNo,
                                                UserRepository.OrderStatus.PENDING_RECEIPT,
                                            )
                                            repository.updateOrderStatus(
                                                order.orderId,
                                                UserRepository.OrderStatus.PENDING_RECEIPT,
                                            )
                                        }
                                        Toast.makeText(context, "催发货成功", Toast.LENGTH_SHORT).show()
                                        // 刷新列表
                                        loadOrders(selectedTab)
                                    } catch (_: Exception) {
                                        Toast.makeText(context, "操作失败", Toast.LENGTH_SHORT).show()
                                    }
                                }
                            },
                            onCancelOrder = {
                                // 弹出取消订单确认弹窗
                                cancelDialogOrder = order
                            },
                            onBuyAgain = {
                                // 将订单中所有商品加入购物车：先 POST 后端 API，成功后同步前端 SQLite
                                scope.launch {
                                    try {
                                        val allSuccess = withContext(Dispatchers.IO) {
                                            val json = JSONObject(order.rawOrderBody)
                                            val itemsArray = json.optJSONArray("items") ?: return@withContext false
                                            val sessionId = com.shopping.agent.data.local.CartSessionManager.getOrCreate(context)
                                            val userId = repository.getUserId()
                                            val client = NetworkConfig.httpClient
                                            val baseUrl = NetworkConfig.BASE_URL

                                            var anyFailed = false
                                            for (i in 0 until itemsArray.length()) {
                                                val item = itemsArray.getJSONObject(i)
                                                val pid = item.optString("product_id", "")
                                                val title = item.optString("title", "")
                                                val price = item.optDouble("price", 0.0)
                                                val imageUrl = item.optString("image_url", "")

                                                // 1. POST 后端 API 加入购物车
                                                val apiSuccess = try {
                                                    val body = org.json.JSONObject().apply {
                                                        put("session_id", sessionId)
                                                        put("product_id", pid)
                                                        put("title", title)
                                                        put("price", price)
                                                        put("user_id", userId)
                                                    }
                                                    val request = okhttp3.Request.Builder()
                                                        .url("$baseUrl/api/v1/cart/add")
                                                        .post(body.toString().toRequestBody("application/json".toMediaType()))
                                                        .build()
                                                    client.newCall(request).execute().isSuccessful
                                                } catch (_: Exception) {
                                                    false
                                                }
                                                if (!apiSuccess) {
                                                    anyFailed = true
                                                    continue
                                                }

                                                // 2. 后端成功后同步前端 SQLite
                                                val product = com.shopping.agent.data.model.Product(
                                                productId = pid,
                                                title = title,
                                                price = price,
                                                brand = null,
                                                imageUrl = imageUrl,
                                                category = "",
                                            )
                                            repository.saveCartItemForCurrentUser(product, sessionId, 1)
                                        }
                                        !anyFailed
                                        }
                                        if (allSuccess) {
                                            Toast.makeText(context, "已加入购物车", Toast.LENGTH_SHORT).show()
                                        } else {
                                            Toast.makeText(context, "部分商品加购失败", Toast.LENGTH_SHORT).show()
                                        }
                                        onBuyAgain()
                                    } catch (_: Exception) {
                                        Toast.makeText(context, "操作失败", Toast.LENGTH_SHORT).show()
                                    }
                                }
                            },
                            onReview = {
                                onReview(
                                    order.orderId,
                                    order.backendOrderNo,
                                    order.firstProductId,
                                    order.firstProductTitle,
                                    order.firstProductImage,
                                )
                            },
                            onPlaceholderAction = {
                                Toast.makeText(context, "该功能暂未开放", Toast.LENGTH_SHORT).show()
                            },
                        )
                    }
                }
            }
        }
    }
}

/* ═══════════════════════════════════════════════════════════ */
/*         订单卡片                                               */
/* ═══════════════════════════════════════════════════════════ */

/**
 * 订单卡片组件。
 *
 * 布局：
 * - 顶部：订单状态（灰色文本，右对齐）
 * - 中间：商品缩略图 + 商品名称 + 总价 + 件数
 * - 底部：操作按钮（右对齐，根据状态显示不同按钮）
 */
@Composable
private fun OrderCard(
    order: OrderDisplayData,
    onProductClick: () -> Unit,
    onConfirmReceipt: () -> Unit,
    onUrgeShipping: () -> Unit,  // 催发货：状态改为待收货 + 刷新
    onCancelOrder: () -> Unit,   // 取消订单：弹窗确认后状态改为已取消
    onBuyAgain: () -> Unit,      // 再次购买：加入购物车 + 跳转至购物车页面
    onReview: () -> Unit,        // 评价晒单：跳转至评价页面
    onPlaceholderAction: () -> Unit,
) {
    Card(
        shape = RadiusLg,
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            // 顶部：订单状态（右对齐，灰色文本）
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End,
            ) {
                Text(
                    order.status,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall,
                )
            }

            Spacer(Modifier.height(8.dp))

            // 中间：商品信息行（缩略图 + 名称 + 价格）
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { onProductClick() },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                // 商品缩略图（72dp 圆角方形）
                AsyncImage(
                    model = NetworkConfig.resolveImageUrl(order.firstProductImage),
                    contentDescription = order.firstProductTitle,
                    modifier = Modifier
                        .size(72.dp)
                        .clip(RoundedCornerShape(8.dp)),
                    contentScale = ContentScale.Crop,
                )
                Spacer(Modifier.width(12.dp))
                // 商品名称（加粗，多商品时加"等"后缀）
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = if (order.hasMoreItems) "${order.firstProductTitle}等" else order.firstProductTitle,
                        style = MaterialTheme.typography.bodyLarge,
                        fontWeight = FontWeight.Bold,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                        color = MaterialTheme.colorScheme.onSurface,
                    )
                }
                Spacer(Modifier.width(8.dp))
                // 总价 + 件数
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        "¥${"%.2f".format(order.totalPrice)}",
                        color = TextPrice,
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        "共${order.totalCount}件",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            Spacer(Modifier.height(8.dp))

            // 底部：操作按钮（右对齐）
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End,
            ) {
                OrderActionButtons(
                    status = order.status,
                    onCancelOrder = onCancelOrder,
                    onPayNow = onPlaceholderAction,
                    onUrgeShipping = onUrgeShipping,
                    onViewLogistics = onPlaceholderAction,
                    onConfirmReceipt = onConfirmReceipt,
                    onBuyAgain = onBuyAgain,
                    onReview = onReview,
                )
            }
        }
    }
}

/* ═══════════════════════════════════════════════════════════ */
/*         订单操作按钮（根据状态显示不同按钮组合）                  */
/* ═══════════════════════════════════════════════════════════ */

/**
 * 根据订单状态渲染不同的操作按钮组。
 *
 * 按钮规则（AGENTS.md §订单页面功能完善）：
 * - 待付款：取消订单 + 去付款（蓝色）
 * - 待发货：取消订单 + 催发货
 * - 待收货：确认收货（蓝色）— 已移除查看物流按钮
 * - 待评价：再次购买 + 评价晒单（蓝色）
 * - 已完成/已取消：再次购买（蓝色）
 */
@Composable
private fun OrderActionButtons(
    status: String,
    onCancelOrder: () -> Unit,
    onPayNow: () -> Unit,
    onUrgeShipping: () -> Unit,
    onViewLogistics: () -> Unit,
    onConfirmReceipt: () -> Unit,
    onBuyAgain: () -> Unit,
    onReview: () -> Unit,
) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        when (status) {
            // 待付款：取消订单 + 去付款（蓝色）
            UserRepository.OrderStatus.PENDING_PAYMENT -> {
                OutlinedButton(onClick = onCancelOrder, shape = CircleShape) {
                    Text("取消订单", style = MaterialTheme.typography.bodySmall)
                }
                Button(
                    onClick = onPayNow,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.outlineVariant,
                        contentColor = MaterialTheme.colorScheme.onSurfaceVariant,
                    ),
                    shape = CircleShape,
                    enabled = false,
                ) {
                    Text("支付即将上线", style = MaterialTheme.typography.bodySmall)
                }
            }
            // 待发货：取消订单 + 催发货
            UserRepository.OrderStatus.PENDING_SHIPPING -> {
                OutlinedButton(onClick = onCancelOrder, shape = CircleShape) {
                    Text("取消订单", style = MaterialTheme.typography.bodySmall)
                }
                OutlinedButton(onClick = onUrgeShipping, shape = CircleShape) {
                    Text("催发货", style = MaterialTheme.typography.bodySmall)
                }
            }
            // 待收货：确认收货（蓝色）— 已移除查看物流按钮
            UserRepository.OrderStatus.PENDING_RECEIPT -> {
                OutlinedButton(
                    onClick = {},
                    shape = CircleShape,
                    enabled = false,
                ) {
                    Text(
                        "物流查询即将上线",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Button(
                    onClick = onConfirmReceipt,
                    colors = ButtonDefaults.buttonColors(containerColor = Primary),
                    shape = CircleShape,
                ) {
                    Text("确认收货", color = OnPrimary, style = MaterialTheme.typography.bodySmall)
                }
            }
            // 待评价：再次购买 + 评价晒单（蓝色）
            UserRepository.OrderStatus.PENDING_REVIEW -> {
                OutlinedButton(onClick = onBuyAgain, shape = CircleShape) {
                    Text("再次购买", style = MaterialTheme.typography.bodySmall)
                }
                Button(
                    onClick = onReview,
                    colors = ButtonDefaults.buttonColors(containerColor = Primary),
                    shape = CircleShape,
                ) {
                    Text("评价晒单", color = OnPrimary, style = MaterialTheme.typography.bodySmall)
                }
            }
            // 已完成 / 已取消：再次购买（蓝色）
            UserRepository.OrderStatus.COMPLETED, UserRepository.OrderStatus.CANCELLED -> {
                Button(
                    onClick = onBuyAgain,
                    colors = ButtonDefaults.buttonColors(containerColor = Primary),
                    shape = CircleShape,
                ) {
                    Text("再次购买", color = OnPrimary, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

/* ═══════════════════════════════════════════════════════════ */
/*         数据解析工具函数                                       */
/* ═══════════════════════════════════════════════════════════ */

/**
 * 从 SQLite order_body JSON 解析订单展示数据。
 *
 * order_body JSON 格式：
 * {
 *   "backend_order_no": "ORD...",
 *   "total": 299.00,
 *   "items": [
 *     {"product_id": "...", "title": "...", "price": 199.00, "quantity": 1, "image_url": "..."}
 *   ]
 * }
 *
 * @param record 从 SQLite 读取的订单记录
 * @return 解析后的展示数据，失败返回 null
 */
private fun parseOrderBody(record: UserRepository.OrderRecord): OrderDisplayData? {
    return try {
        val json = JSONObject(record.orderBody)
        val itemsArray = json.optJSONArray("items") ?: return null
        if (itemsArray.length() == 0) return null

        val firstItem = itemsArray.getJSONObject(0)
        var totalCount = 0
        var totalPrice = 0.0
        for (i in 0 until itemsArray.length()) {
            val item = itemsArray.getJSONObject(i)
            val qty = item.optInt("quantity", 1)
            val price = item.optDouble("price", 0.0)
            totalCount += qty
            totalPrice += price * qty
        }

        OrderDisplayData(
            orderId = record.orderId,
            backendOrderNo = record.backendOrderNo,
            totalPrice = if (totalPrice > 0) totalPrice else json.optDouble("total", 0.0),
            totalCount = totalCount,
            firstProductId = firstItem.optString("product_id", ""),
            firstProductImage = firstItem.optString("image_url", ""),
            firstProductTitle = firstItem.optString("title", "商品"),
            hasMoreItems = itemsArray.length() > 1,
            status = record.status,
            rawOrderBody = record.orderBody,
        )
    } catch (_: Exception) {
        null
    }
}
