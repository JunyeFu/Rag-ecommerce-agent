package com.shopping.agent.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ReceiptLong
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.ShoppingBag
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.shopping.agent.core.network.NetworkConfig
import com.shopping.agent.data.local.CartSessionManager
import com.shopping.agent.data.local.UserRepository
import com.shopping.agent.data.model.CartItem
import com.shopping.agent.data.model.Product
import com.shopping.agent.ui.components.GradientTopBar
import com.shopping.agent.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject

private data class CheckoutOrder(
    val orderId: String,
    val orderNo: String,
    val total: Double,
    val itemsSnapshot: String = "",  // 商品快照 JSON，用于写入本地数据库
)

@Composable
fun CheckoutScreen(
    source: String,
    productId: String?,
    onBack: () -> Unit,
    onAddAddress: () -> Unit,
    onOrderCreated: (String) -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val repository = remember { UserRepository(context) }
    val sessionId = remember { CartSessionManager.getOrCreate(context) }

    var isLoading by remember { mutableStateOf(true) }
    var isSubmitting by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var items by remember { mutableStateOf<List<CartItem>>(emptyList()) }
    var address by remember { mutableStateOf<UserRepository.ShippingAddress?>(null) }

    fun load() {
        scope.launch {
            isLoading = true
            error = null
            try {
                val loadedAddress = withContext(Dispatchers.IO) {
                    repository.getShippingAddresses().firstOrNull()
                }
                val loadedItems = withContext(Dispatchers.IO) {
                    if (source == "buy" && !productId.isNullOrBlank()) {
                        listOf(CartItem(fetchProduct(productId), 1, isSelected = true))
                    } else {
                        val cart = repository.getCartItemsForCurrentUser(sessionId)
                        cart.filter { it.isSelected }.ifEmpty { cart }
                    }
                }
                address = loadedAddress
                items = loadedItems
                if (loadedItems.isEmpty()) error = "暂无可结算商品"
            } catch (e: Exception) {
                error = e.message ?: "加载失败"
            } finally {
                isLoading = false
            }
        }
    }

    LaunchedEffect(source, productId) { load() }

    val total = items.sumOf { it.product.price * it.quantity }
    val addressText = address?.let {
        listOf(it.recipientName, it.phone, it.addressDetail).filter { part -> part.isNotBlank() }.joinToString(" ")
    }.orEmpty()

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
                    Text("确认订单", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                }
            }
        },
        bottomBar = {
            Surface(shadowElevation = 8.dp, color = MaterialTheme.colorScheme.surface) {
                Row(
                    modifier = Modifier.fillMaxWidth().navigationBarsPadding().padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text("实付", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("¥${"%.2f".format(total)}", style = MaterialTheme.typography.titleLarge, color = TextPrice, fontWeight = FontWeight.Bold)
                    }
                    Button(
                        onClick = {
                            scope.launch {
                                isSubmitting = true
                                error = null
                                try {
                                    val order = withContext(Dispatchers.IO) {
                                        submitOrder(
                                            sessionId = sessionId,
                                            userId = repository.getUserId(),
                                            address = addressText.ifBlank { "默认地址" },
                                            items = items,
                                            addBuyNowItem = source == "buy",
                                        )
                                    }
                                    // 同步写入本地 SQLite 订单记录（待发货状态，绑定后端订单号）
                                    withContext(Dispatchers.IO) {
                                        val orderBodyJson = JSONObject().apply {
                                            put("backend_order_no", order.orderNo)
                                            put("total", order.total)
                                            put("items", JSONArray(order.itemsSnapshot))
                                        }
                                        repository.addOrderRecord(
                                            orderBody = orderBodyJson.toString(),
                                            status = UserRepository.OrderStatus.PENDING_SHIPPING,
                                            backendOrderNo = order.orderNo,
                                        )
                                        // 删除已下单的购物车商品
                                        repository.deleteCartItems(items.map { it.product.productId })
                                    }
                                    onOrderCreated(order.orderId)
                                } catch (e: Exception) {
                                    error = e.message ?: "下单失败"
                                } finally {
                                    isSubmitting = false
                                }
                            }
                        },
                        enabled = items.isNotEmpty() && !isSubmitting,
                        shape = CircleShape,
                        colors = ButtonDefaults.buttonColors(containerColor = Primary),
                        modifier = Modifier.height(48.dp),
                    ) {
                        if (isSubmitting) {
                            CircularProgressIndicator(modifier = Modifier.size(18.dp), color = OnPrimary, strokeWidth = 2.dp)
                        } else {
                            Text("提交订单", color = OnPrimary)
                        }
                    }
                }
            }
        },
    ) { padding ->
        when {
            isLoading -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = Primary)
            }
            else -> LazyColumn(
                modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).padding(padding),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                item {
                    CheckoutAddressCard(
                        text = addressText,
                        onAddAddress = onAddAddress,
                    )
                }
                item {
                    Text("商品清单", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                }
                items(items, key = { it.product.productId }) { item ->
                    CheckoutItemCard(item)
                }
                item {
                    CheckoutSummaryCard(items.size, total)
                }
                if (error != null) {
                    item {
                        Text(error.orEmpty(), color = ErrorColor, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
        }
    }
}

@Composable
private fun CheckoutAddressCard(text: String, onAddAddress: () -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Default.LocationOn, null, tint = Primary)
            Spacer(Modifier.width(10.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text("收货地址", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                Text(
                    text.ifBlank { "暂无默认地址" },
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            TextButton(onClick = onAddAddress) {
                Text(if (text.isBlank()) "新增" else "更换")
            }
        }
    }
}

@Composable
private fun CheckoutItemCard(item: CartItem) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Row(modifier = Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            AsyncImage(
                model = item.product.imageUrl,
                contentDescription = item.product.title,
                contentScale = ContentScale.Crop,
                modifier = Modifier.size(72.dp),
            )
            Spacer(Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(item.product.title, style = MaterialTheme.typography.bodyMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Spacer(Modifier.height(4.dp))
                Text(item.product.brand ?: item.product.category, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.height(6.dp))
                Text("¥${"%.2f".format(item.product.price)}", color = TextPrice, fontWeight = FontWeight.Bold)
            }
            Text("x${item.quantity}", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun CheckoutSummaryCard(count: Int, total: Double) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(modifier = Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.AutoMirrored.Filled.ReceiptLong, null, tint = Primary)
                Spacer(Modifier.width(8.dp))
                Text("订单汇总", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("商品件数", color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text("${count} 件")
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("运费", color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text("免运费")
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("实付金额", fontWeight = FontWeight.SemiBold)
                Text("¥${"%.2f".format(total)}", color = TextPrice, fontWeight = FontWeight.Bold)
            }
        }
    }
}

private fun fetchProduct(productId: String): Product {
    val request = Request.Builder()
        .url("${NetworkConfig.BASE_URL}/api/v1/products/$productId")
        .get()
        .build()
    NetworkConfig.httpClient.newCall(request).execute().use { response ->
        if (!response.isSuccessful) throw IllegalStateException("商品加载失败 ${response.code}")
        val data = JSONObject(response.body?.string().orEmpty()).optJSONObject("data")
            ?: throw IllegalStateException("商品数据解析失败")
        val imageUrls = data.optJSONArray("image_urls")
        val images = (0 until (imageUrls?.length() ?: 0)).map { imageUrls!!.optString(it) }
        return Product(
            productId = data.optString("product_id", productId),
            title = data.optString("title"),
            brand = data.optString("brand").takeIf { it.isNotBlank() },
            category = data.optString("category"),
            price = data.optDouble("price"),
            rating = data.optDouble("rating", 3.0).toFloat(),
            imageUrl = NetworkConfig.resolveImageUrl(data.optString("image_url").takeIf { it.isNotBlank() } ?: images.firstOrNull()),
            imageUrls = images.mapNotNull { NetworkConfig.resolveImageUrl(it) },
        )
    }
}

private fun submitOrder(
    sessionId: String,
    userId: String,
    address: String,
    items: List<CartItem>,
    addBuyNowItem: Boolean,
): CheckoutOrder {
    if (addBuyNowItem) {
        val first = items.firstOrNull() ?: throw IllegalStateException("暂无可购买商品")
        val addBody = JSONObject().apply {
            put("session_id", sessionId)
            put("user_id", userId)
            put("product_id", first.product.productId)
            put("title", first.product.title)
            put("price", first.product.price)
        }
        val addReq = Request.Builder()
            .url("${NetworkConfig.BASE_URL}/api/v1/cart/add")
            .post(addBody.toString().toRequestBody("application/json".toMediaType()))
            .build()
        NetworkConfig.httpClient.newCall(addReq).execute().use { response ->
            if (!response.isSuccessful) throw IllegalStateException("立即购买加购失败 ${response.code}")
        }
    }

    val orderBody = JSONObject().apply {
        put("session_id", sessionId)
        put("user_id", userId)
        put("address", address)
        put("product_ids", JSONArray(items.map { it.product.productId }))
    }
    val orderReq = Request.Builder()
        .url("${NetworkConfig.BASE_URL}/api/v1/orders")
        .post(orderBody.toString().toRequestBody("application/json".toMediaType()))
        .build()
    // 构建商品快照 JSON（用于写入本地数据库）
    val snapshotJsonArray = JSONArray().apply {
        items.forEach { cartItem ->
            put(JSONObject().apply {
                put("product_id", cartItem.product.productId)
                put("title", cartItem.product.title)
                put("price", cartItem.product.price)
                put("quantity", cartItem.quantity)
                put("image_url", cartItem.product.imageUrl ?: "")
            })
        }
    }
    val itemsSnapshotJson = snapshotJsonArray.toString()

    NetworkConfig.httpClient.newCall(orderReq).execute().use { response ->
        if (!response.isSuccessful) throw IllegalStateException("下单失败 ${response.code}")
        val json = JSONObject(response.body?.string().orEmpty())
        val data = json.optJSONObject("data") ?: JSONObject()
        return CheckoutOrder(
            orderId = data.optString("order_id"),
            orderNo = data.optString("order_no"),
            total = data.optDouble("total"),
            itemsSnapshot = itemsSnapshotJson,
        )
    }
}
