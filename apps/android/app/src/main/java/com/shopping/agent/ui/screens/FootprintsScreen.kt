package com.shopping.agent.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
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
import com.shopping.agent.data.mock.mockProducts
import com.shopping.agent.data.model.Product
import com.shopping.agent.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.Request
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.*

/** 日期格式化器 — 用于显示分组日期 */
private val DATE_DISPLAY_FORMAT = SimpleDateFormat("yyyy年MM月dd日", Locale.CHINESE)
/** 日期格式化器 — 用于日期选择器参数转换 */
private val DATE_PARAM_FORMAT = SimpleDateFormat("yyyy-MM-dd", Locale.CHINESE)

/**
 * 筛选弹窗状态。
 * @param startDate 起始日期（毫秒时间戳，0点），0 表示不限
 * @param endDate 结束日期（毫秒时间戳，次日0点前），0 表示不限
 */
private data class FilterState(
    val startDate: Long = 0,
    val endDate: Long = 0,
)

/**
 * 足迹页面。
 *
 * 布局结构：
 * - 顶部栏：< 返回 + "足迹"文本 + "筛选"按钮
 * - 主体：按日期分组降序显示足迹商品卡片
 * - 筛选弹窗：标题"筛选足迹" + 日期范围选择 + "确定"和"重置"按钮
 *
 * @param onBack 返回个人页面回调
 * @param onProductClick 点击商品卡片回调，传入商品 ID
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FootprintsScreen(
    onBack: () -> Unit = {},
    onProductClick: (String) -> Unit = {},
) {
    val context = LocalContext.current
    val repository = remember { UserRepository(context) }
    val scope = rememberCoroutineScope()

    var footprintsByDate by remember { mutableStateOf<Map<String, List<Product>>>(emptyMap()) }
    var isLoading by remember { mutableStateOf(true) }
    var showFilterDialog by remember { mutableStateOf(false) }
    var filterState by remember { mutableStateOf(FilterState()) }
    /** 上一次加载的 Job，用于取消并发加载防止 LazyColumn key 重复 */
    var loadJob by remember { mutableStateOf<kotlinx.coroutines.Job?>(null) }

    /** 加载足迹商品列表 — mockProducts 优先，UUID 则调 API 获取完整信息并按日期分组 */
    fun loadFootprints(startDate: Long = 0, endDate: Long = 0) {
        // 取消前次加载，防止并发导致 LazyColumn key 冲突
        loadJob?.cancel()
        loadJob = scope.launch {
            isLoading = true
            try {
                val records = withContext(Dispatchers.IO) {
                    repository.getFootprints(startDate = startDate, endDate = endDate)
                }
                // 分离匹配和未匹配的记录，并行处理
                val (matched, unmatched) = records.partition { record ->
                    mockProducts.any { it.productId == record.productId }
                }
                // 构建 productId → Product 的映射
                val productMap = mutableMapOf<String, Product>()
                matched.forEach { record ->
                    mockProducts.find { it.productId == record.productId }?.let {
                        productMap[record.productId] = it
                    }
                }
                // UUID 记录：并行调 API 获取完整商品信息
                if (unmatched.isNotEmpty()) {
                    val apiResults = withContext(Dispatchers.IO) {
                        unmatched.map { record ->
                            async<Pair<String, Product?>> { record.productId to fetchFootprintProductFromApi(record.productId) }
                        }.awaitAll()
                    }
                    apiResults.forEach { (id, product) ->
                        if (product != null) productMap[id] = product
                    }
                }
                // 按日期分组（去重：同一日期组内相同 productId 只保留一条）
                val grouped = linkedMapOf<String, MutableList<Product>>()
                records.forEach { record ->
                    val product = productMap[record.productId] ?: return@forEach
                    val dateLabel = DATE_DISPLAY_FORMAT.format(Date(record.browseDate))
                    val list = grouped.getOrPut(dateLabel) { mutableListOf() }
                    // 防止同一 productId 被重复添加（兜底去重）
                    if (list.none { it.productId == product.productId }) {
                        list.add(product)
                    }
                }
                @Suppress("UNCHECKED_CAST")
                footprintsByDate = grouped as Map<String, List<Product>>
            } catch (_: Exception) {
                footprintsByDate = emptyMap()
            }
            isLoading = false
        }
    }

    // 初始加载
    LaunchedEffect(Unit) {
        loadFootprints()
    }

    // 筛选弹窗
    if (showFilterDialog) {
        FilterFootprintDialog(
            onDismiss = { showFilterDialog = false },
            onConfirm = { startDate, endDate ->
                filterState = FilterState(startDate, endDate)
                loadFootprints(startDate, endDate)
                showFilterDialog = false
            },
            onReset = {
                filterState = FilterState()
                loadFootprints(0, 0)
                showFilterDialog = false
            },
        )
    }

    Scaffold(
        topBar = {
            // 顶部栏
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(48.dp)
                    .padding(horizontal = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(onClick = onBack) {
                    Icon(
                        Icons.AutoMirrored.Filled.ArrowBack, "返回",
                        tint = MaterialTheme.colorScheme.onSurface,
                    )
                }
                Text(
                    "足迹",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurface,
                    fontWeight = FontWeight.Medium,
                )

                Spacer(Modifier.weight(1f))

                // 筛选按钮（屏幕右上角）
                TextButton(onClick = { showFilterDialog = true }) {
                    Text(
                        "筛选",
                        color = MaterialTheme.colorScheme.onSurface,
                    )
                }
            }
        },
    ) { innerPadding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .background(MaterialTheme.colorScheme.background),
        ) {
            if (isLoading) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Primary)
                }
            } else if (footprintsByDate.isEmpty()) {
                // 空足迹状态
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(
                        "暂无足迹",
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            } else {
                // 按日期分组降序显示足迹商品卡片
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    footprintsByDate.forEach { (dateLabel, products) ->
                        // 日期分组标题
                        item(key = "date_$dateLabel") {
                            Text(
                                text = dateLabel,
                                style = MaterialTheme.typography.titleSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontWeight = FontWeight.Medium,
                                modifier = Modifier.padding(vertical = 8.dp),
                            )
                        }
                        // 该日期下的商品卡片（key 含日期+productId+索引，三重防冲突）
                        itemsIndexed(products, key = { index, product -> "fp_${dateLabel}_${product.productId}_$index" }) { _, product ->
                            FootprintProductCard(
                                product = product,
                                onTap = { onProductClick(product.productId) },
                            )
                        }
                    }
                }
            }
        }
    }
}

/** 从后端 API 获取商品信息并转为 Product 对象（用于 UUID 等 mockProducts 无法匹配的 ID） */
private suspend fun fetchFootprintProductFromApi(productId: String): Product? {
    return try {
        val request = Request.Builder()
            .url("${NetworkConfig.BASE_URL}/api/v1/products/$productId")
            .get()
            .build()
        val response = NetworkConfig.httpClient.newCall(request).execute()
        if (!response.isSuccessful) return null
        val body = response.body?.string() ?: return null
        val data = JSONObject(body).optJSONObject("data") ?: return null
        val imageUrls = data.optJSONArray("image_urls")
        val firstImage = if (imageUrls != null && imageUrls.length() > 0) {
            NetworkConfig.resolveImageUrl(imageUrls.optString(0))
        } else {
            NetworkConfig.resolveImageUrl(data.optString("image_url").takeIf { it.isNotBlank() })
        }
        Product(
            productId = productId,
            title = data.optString("title", ""),
            price = data.optDouble("price", 0.0),
            brand = data.optString("brand").takeIf { it.isNotBlank() },
            category = data.optString("category", ""),
            imageUrl = firstImage,
            rating = data.optDouble("rating", 3.0).toFloat(),
        )
    } catch (_: Exception) {
        null
    }
}

/**
 * 筛选足迹弹窗 — 日期范围筛选。
 *
 * 底部按钮：
 * - "确定"按钮（蓝色背景）：根据筛选日期刷新列表
 * - "重置"按钮（默认背景）：重置筛选（显示所有足迹）
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FilterFootprintDialog(
    onDismiss: () -> Unit,
    onConfirm: (Long, Long) -> Unit,
    onReset: () -> Unit,
) {
    var selectedStartDate by remember { mutableStateOf("") }
    var selectedEndDate by remember { mutableStateOf("") }
    val dateRegex = Regex("^\\d{4}-\\d{2}-\\d{2}$")
    val startError = selectedStartDate.isNotEmpty() && !dateRegex.matches(selectedStartDate)
    val endError = selectedEndDate.isNotEmpty() && !dateRegex.matches(selectedEndDate)
    val hasError = startError || endError

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text("筛选足迹", fontWeight = FontWeight.Bold)
        },
        text = {
            Column {
                Text(
                    "筛选足迹日期范围",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(bottom = 12.dp),
                )

                // 起始日期输入
                OutlinedTextField(
                    value = selectedStartDate,
                    onValueChange = { selectedStartDate = it },
                    label = { Text("起始日期 (YYYY-MM-DD)") },
                    placeholder = { Text("2026-01-01") },
                    singleLine = true,
                    isError = startError,
                    supportingText = {
                        if (startError) {
                            Text("日期格式不正确，请使用 YYYY-MM-DD", color = ErrorColor)
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                )

                Spacer(Modifier.height(8.dp))

                // 结束日期输入
                OutlinedTextField(
                    value = selectedEndDate,
                    onValueChange = { selectedEndDate = it },
                    label = { Text("结束日期 (YYYY-MM-DD)") },
                    placeholder = { Text("2026-12-31") },
                    singleLine = true,
                    isError = endError,
                    supportingText = {
                        if (endError) {
                            Text("日期格式不正确，请使用 YYYY-MM-DD", color = ErrorColor)
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    // 解析日期并转为毫秒时间戳
                    val startMs = parseDateToMidnight(selectedStartDate)
                    val endMs = parseDateToEndOfDay(selectedEndDate)
                    onConfirm(startMs, endMs)
                },
                colors = ButtonDefaults.buttonColors(containerColor = Primary),
                enabled = !hasError,
            ) {
                Text("确定", color = OnPrimary)
            }
        },
        dismissButton = {
            TextButton(onClick = onReset) {
                Text("重置", color = MaterialTheme.colorScheme.onSurface)
            }
        },
    )
}

/**
 * 将日期字符串解析为当日0点的时间戳。
 * @param dateStr 日期字符串，格式 YYYY-MM-DD
 * @return 毫秒时间戳（0点），解析失败返回 0
 */
private fun parseDateToMidnight(dateStr: String): Long {
    if (dateStr.isBlank()) return 0
    return try {
        val date = DATE_PARAM_FORMAT.parse(dateStr.trim())
        date?.time ?: 0
    } catch (_: Exception) {
        0
    }
}

/**
 * 将日期字符串解析为当日23:59:59的时间戳。
 * @param dateStr 日期字符串，格式 YYYY-MM-DD
 * @return 毫秒时间戳（当日结束），解析失败返回 0
 */
private fun parseDateToEndOfDay(dateStr: String): Long {
    if (dateStr.isBlank()) return 0
    return try {
        val cal = Calendar.getInstance()
        cal.time = DATE_PARAM_FORMAT.parse(dateStr.trim())!!
        cal.set(Calendar.HOUR_OF_DAY, 23)
        cal.set(Calendar.MINUTE, 59)
        cal.set(Calendar.SECOND, 59)
        cal.set(Calendar.MILLISECOND, 999)
        cal.timeInMillis
    } catch (_: Exception) {
        0
    }
}

/**
 * 足迹商品卡片 — 与主页商品卡片设计一致，占满一行。
 */
@Composable
private fun FootprintProductCard(
    product: Product,
    onTap: () -> Unit,
) {
    Card(
        onClick = onTap,
        shape = RadiusLg,
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // 商品图片
            AsyncImage(
                model = product.imageUrl,
                contentDescription = product.title,
                modifier = Modifier
                    .size(80.dp)
                    .clip(RoundedCornerShape(8.dp)),
                contentScale = ContentScale.Crop,
            )

            Spacer(Modifier.width(12.dp))

            // 商品信息
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    product.title,
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurface,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(4.dp))
                Row(verticalAlignment = Alignment.Bottom) {
                    Text(
                        "¥${product.price}",
                        style = MaterialTheme.typography.titleMedium,
                        color = TextPrice,
                        fontWeight = FontWeight.Bold,
                    )
                }
                if (product.brand != null) {
                    Spacer(Modifier.height(2.dp))
                    Text(
                        product.brand,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}
