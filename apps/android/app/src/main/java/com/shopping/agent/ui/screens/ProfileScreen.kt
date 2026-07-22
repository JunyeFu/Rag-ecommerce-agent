package com.shopping.agent.ui.screens

import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.HeadsetMic
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.shopping.agent.data.local.UserRepository
import com.shopping.agent.data.model.CartItem
import com.shopping.agent.ui.theme.*
import com.shopping.agent.data.mock.MockProfile
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** 头像图片最大尺寸（像素），与 ProfileEditScreen 保持一致 */
private const val MAX_AVATAR_DIM = 480

/**
 * 计算 Bitmap 降采样比例因子，返回值总是 2 的幂。
 */
private fun calculateInSampleSize(options: BitmapFactory.Options, reqWidth: Int, reqHeight: Int): Int {
    val (height, width) = options.outHeight to options.outWidth
    var inSampleSize = 1
    if (height > reqHeight || width > reqWidth) {
        val halfHeight = height / 2
        val halfWidth = width / 2
        while (halfHeight / inSampleSize >= reqHeight && halfWidth / inSampleSize >= reqWidth) {
            inSampleSize *= 2
        }
    }
    return inSampleSize
}

// ===== ProfileHeader 背景色 =====
private val ProfileHeaderBg = Color(0xFFEBF3FC)

/**
 * 用户头部区域 — 蓝粉渐变 + 头像 + 用户名 + 官方客服 + 设置。
 *
 * 头像优先显示从 SQLite 加载的用户上传图片，无头像时展示"海"字默认占位符。
 *
 * @param onSettingsClick 设置按钮点击回调
 * @param avatarBitmap 用户头像 ImageBitmap，可为 null 以显示默认占位符
 * @param nickname 用户显示昵称，为空时回退默认值 "fujunye"
 */
@Composable
private fun ProfileHeader(
    onSettingsClick: () -> Unit = {},
    onCustomerServiceClick: () -> Unit = {},
    avatarBitmap: ImageBitmap? = null,
    nickname: String = "fujunye",
) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(100.dp)
            .background(ProfileHeaderBg),
    ) {
        // 右侧: 客服 + 设置
        Row(
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(top = 12.dp, end = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            IconButton(onClick = onCustomerServiceClick, modifier = Modifier.size(40.dp)) {
                Icon(Icons.Default.HeadsetMic, "官方客服", tint = MaterialTheme.colorScheme.onSurface, modifier = Modifier.size(24.dp))
            }
            IconButton(onClick = onSettingsClick, modifier = Modifier.size(40.dp)) {
                Icon(Icons.Default.Settings, "设置", tint = MaterialTheme.colorScheme.onSurface, modifier = Modifier.size(24.dp))
            }
        }

        // 左侧: 头像 + 用户名（水平排列）
        Row(
            modifier = Modifier
                .align(Alignment.CenterStart)
                .padding(start = 20.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            // 圆形头像
            Surface(
                modifier = Modifier.size(56.dp),
                shape = CircleShape,
                color = MaterialTheme.colorScheme.outlineVariant,
                shadowElevation = 2.dp,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    val bmp = avatarBitmap
                    if (bmp != null) {
                        Image(
                            bitmap = bmp,
                            contentDescription = "头像",
                            modifier = Modifier.fillMaxSize().clip(CircleShape),
                            contentScale = ContentScale.Crop,
                        )
                    } else {
                        Text(
                            text = "海",
                            style = MaterialTheme.typography.headlineSmall,
                            color = Primary,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }
            }
            // 用户名
            Text(
                text = nickname,
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onSurface,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

/** 个人页面订单状态数量数据类 */
private data class OrderStatusCount(
    val label: String,  // 显示文本（如"待付款"）
    val count: Int,  // 该状态的订单数量
    val statusKey: String,  // 导航筛选 key（如"unpaid"）
    val statusFilters: List<String>,  // 对应的 OrderStatus 值列表
)

/**
 * 订单状态模块 — 5个状态入口
 * 设计规约: §5.3 OrderStatusSection
 */
@Composable
private fun OrderStatusSection(
    orderCounts: List<OrderStatusCount>,
    onOrdersClick: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(
        shape = RadiusLg,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        modifier = modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    "我的订单",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurface,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    "全部 >",
                    style = MaterialTheme.typography.bodySmall,
                    color = Primary,
                    modifier = Modifier.clickable { onOrdersClick("") },
                )
            }
            Spacer(Modifier.height(12.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly,
            ) {
                orderCounts.forEach { status ->
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        modifier = Modifier.clickable { onOrdersClick(status.statusKey) },
                    ) {
                        Text(
                            "${status.count}",
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.onSurface,
                            fontWeight = if (status.count != 0) FontWeight.Bold else FontWeight.Normal,
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(status.label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

/**
 * 常用功能 2×3 网格 — 使用 Material Icons 替代 Emoji。
 *
 * "收藏"和"足迹"显示从数据库加载的真实数量，点击可导航到对应页面。
 * 其他功能仍使用 Mock 占位数据。
 *
 * 设计规约: §5.4 ProfileFeatureGrid
 */
@Composable
private fun ProfileFeatureGrid(
    favoriteCount: Int = 0,
    footprintCount: Int = 0,
    onFavoritesClick: () -> Unit = {},
    onFootprintsClick: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier.fillMaxWidth()) {
        val features = MockProfile.features
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            // 快递（占位 - 即将开放）
            FeatureItem(features[0].title, "即将开放", Icons.Default.Settings, Modifier.weight(1f))
            // 收藏 — 显示真实数量
            FeatureItem(
                title = features[1].title,
                subtitle = if (favoriteCount > 0) "${favoriteCount}件收藏" else "暂无收藏",
                icon = Icons.Default.Favorite,
                modifier = Modifier.weight(1f),
                onClick = onFavoritesClick,
            )
            // 关注店铺（占位 - 即将开放）
            FeatureItem(features[2].title, "即将开放", Icons.Default.HeadsetMic, Modifier.weight(1f))
        }
        Spacer(Modifier.height(12.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            // 足迹 — 显示真实数量
            FeatureItem(
                title = features[3].title,
                subtitle = if (footprintCount > 0) "${footprintCount}件商品" else "暂无足迹",
                icon = Icons.Default.Star,
                modifier = Modifier.weight(1f),
                onClick = onFootprintsClick,
            )
            // 想要（占位 - 即将开放）
            FeatureItem(features[4].title, "即将开放", Icons.Default.Settings, Modifier.weight(1f))
            // 我有（占位 - 即将开放）
            FeatureItem(features[5].title, "即将开放", Icons.Default.HeadsetMic, Modifier.weight(1f))
        }
    }
}

@Composable
private fun FeatureItem(
    title: String,
    subtitle: String,
    icon: ImageVector,
    modifier: Modifier = Modifier,
    onClick: () -> Unit = {},
) {
    Card(
        modifier = modifier,
        shape = RadiusLg,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
        onClick = onClick,
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Icon(
                icon,
                contentDescription = title,
                tint = MaterialTheme.colorScheme.onSurface,
                modifier = Modifier.size(28.dp),
            )
            Spacer(Modifier.height(6.dp))
            Text(title, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurface)
            Text(subtitle, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

/**
 * 领券中心 — 浅粉券面 + 红色金额
 * 设计规约: §5.5 CouponCenterSection
 */
@Composable
private fun CouponCenterSection(modifier: Modifier = Modifier) {
    Card(
        shape = RadiusLg,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        modifier = modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "领券中心",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurface,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    "更多优惠 >",
                    style = MaterialTheme.typography.bodySmall,
                    color = Primary,
                )
            }
            Spacer(Modifier.height(12.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                MockProfile.coupons.forEach { coupon ->
                    CouponCard(coupon.amount, coupon.label, BrandPink.copy(alpha = 0.15f), Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun CouponCard(
    amount: String,
    label: String,
    bgColor: Color,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier,
        shape = RadiusMd,
        colors = CardDefaults.cardColors(containerColor = bgColor),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
    ) {
        Column(
            modifier = Modifier.padding(vertical = 10.dp, horizontal = 6.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                amount,
                style = MaterialTheme.typography.titleMedium,
                color = TextPrice,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(2.dp))
            Text(
                label,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * 购物车预览模块 — 横向商品卡片列表。
 *
 * 从数据库加载真实购物车数据，最多显示 4 件商品。
 * 购物车为空时显示"购物车空空如也~"提示。
 *
 * @param onCartClick 点击整个卡片时的回调，导航到购物车页面
 * @param cartItems 从数据库加载的购物车商品列表
 */
@Composable
private fun CartPreviewSection(
    onCartClick: () -> Unit,
    cartItems: List<CartItem>,
    modifier: Modifier = Modifier,
) {
    val displayItems = remember(cartItems) { cartItems.take(MAX_CART_PREVIEW_ITEMS) }
    val cartCount = cartItems.size
    val isEmpty = cartItems.isEmpty()

    Card(
        onClick = onCartClick,
        shape = RadiusLg,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        modifier = modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "购物车",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurface,
                    fontWeight = FontWeight.Bold,
                )
                if (!isEmpty) {
                    Text(
                        "${cartCount}件商品",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Spacer(Modifier.height(12.dp))

            if (isEmpty) {
                // 空购物车状态
                Text(
                    text = "购物车空空如也~",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(vertical = 8.dp),
                )
            } else {
                // 横向商品卡片列表
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    displayItems.forEach { item ->
                        CartProductMiniCard(
                            item = item,
                            modifier = Modifier.weight(1f),
                        )
                    }
                }
            }
        }
    }
}

/** 购物车预览区块最多显示的商品数量 */
private const val MAX_CART_PREVIEW_ITEMS = 4

/**
 * 购物车预览迷你商品卡片。
 * 显示商品图片 + 标题 + 价格。
 */
@Composable
private fun CartProductMiniCard(
    item: CartItem,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        // 商品图
        AsyncImage(
            model = item.product.imageUrl ?: "",
            contentDescription = item.product.title,
            modifier = Modifier
                .size(56.dp)
                .clip(RoundedCornerShape(8.dp)),
            contentScale = ContentScale.Crop,
        )
        Spacer(Modifier.height(6.dp))
        Text(
            item.product.title,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            "¥${item.product.price}",
            style = MaterialTheme.typography.labelMedium,
            color = TextPrice,
            fontWeight = FontWeight.Bold,
        )
    }
}

/**
 * 我的 — 完整页面。
 *
 * 启动时从 SQLite 加载用户头像、昵称和购物车数据。
 * 子模块：用户头部、购物车预览、我的订单、常用功能 2×3 网格、领券中心。
 *
 * @param onSettingsClick 设置图标点击回调，导航到设置页
 * @param onCustomerServiceClick 客服图标点击回调，导航到客服页面
 * @param onCartClick 购物车卡片点击回调，导航到购物车页面
 */
@Composable
fun ProfileScreen(
    onSettingsClick: () -> Unit = {},
    onCustomerServiceClick: () -> Unit = {},
    onCartClick: () -> Unit = {},
    onFavoritesClick: () -> Unit = {},
    onFootprintsClick: () -> Unit = {},
    onOrdersClick: (String) -> Unit = {},  // 订单状态筛选导航回调，空字符串表示全部
) {
    val context = LocalContext.current
    val repository = remember { UserRepository(context) }
    var avatarBitmap by remember { mutableStateOf<ImageBitmap?>(null) }
    var displayName by remember { mutableStateOf("fujunye") }
    var cartItems by remember { mutableStateOf<List<CartItem>>(emptyList()) }
    var favoriteCount by remember { mutableIntStateOf(0) }
    var footprintCount by remember { mutableIntStateOf(0) }

    // 懒加载用户头像和昵称：DB 读取均在 IO 线程异步执行
    LaunchedEffect(Unit) {
        try {
            val avatarBytes = withContext(Dispatchers.IO) { repository.getUserAvatar() }
            if (avatarBytes != null && avatarBytes.isNotEmpty()) {
                val androidBmp = withContext(Dispatchers.IO) {
                    val opts = BitmapFactory.Options().apply {
                        inJustDecodeBounds = true
                    }
                    BitmapFactory.decodeByteArray(avatarBytes, 0, avatarBytes.size, opts)
                    opts.inSampleSize = calculateInSampleSize(opts, MAX_AVATAR_DIM, MAX_AVATAR_DIM)
                    opts.inJustDecodeBounds = false
                    opts.inPreferredConfig = android.graphics.Bitmap.Config.ARGB_8888
                    BitmapFactory.decodeByteArray(avatarBytes, 0, avatarBytes.size, opts)
                }
                if (androidBmp != null) {
                    avatarBitmap = androidBmp.asImageBitmap()
                }
            }
        } catch (_: Exception) {
            avatarBitmap = null
        }
    }

    // 懒加载昵称：从 SQLite 读取，为空则回退默认值 "fujunye"
    LaunchedEffect(Unit) {
        try {
            val profile = withContext(Dispatchers.IO) { repository.getUserProfile() }
            val name = profile["nickname"]?.takeIf { it.isNotEmpty() } ?: "fujunye"
            displayName = name
        } catch (_: Exception) {
            displayName = "fujunye"
        }
    }

    // 懒加载购物车数据
    LaunchedEffect(Unit) {
        try {
            val prefs = context.getSharedPreferences("cart_prefs", android.content.Context.MODE_PRIVATE)
            val sessionId = prefs.getString("cart_session_id", "") ?: ""
            val items = withContext(Dispatchers.IO) { repository.getCartItemsForCurrentUser(sessionId) }
            cartItems = items
        } catch (_: Exception) {
            cartItems = emptyList()
        }
    }

    // 懒加载收藏数量 — 每次进入页面时刷新一次
    LaunchedEffect(Unit) {
        try {
            val count = withContext(Dispatchers.IO) { repository.getFavoriteCount() }
            favoriteCount = count
        } catch (_: Exception) {
            favoriteCount = 0
        }
    }

    // 懒加载足迹数量 — 每次进入页面时刷新一次
    LaunchedEffect(Unit) {
        try {
            val count = withContext(Dispatchers.IO) { repository.getFootprintCount() }
            footprintCount = count
        } catch (_: Exception) {
            footprintCount = 0
        }
    }

    // 懒加载订单状态数量 — 每次进入页面时刷新一次
    var orderCounts by remember { mutableStateOf<List<OrderStatusCount>>(emptyList()) }
    LaunchedEffect(Unit) {
        try {
            val counts = withContext(Dispatchers.IO) {
                repository.getOrderCountByStatus(UserRepository.OrderStatus.ALL)
            }
            orderCounts = listOf(
                OrderStatusCount("待付款", counts[UserRepository.OrderStatus.PENDING_PAYMENT] ?: 0, "unpaid", listOf(UserRepository.OrderStatus.PENDING_PAYMENT)),
                OrderStatusCount("待发货", counts[UserRepository.OrderStatus.PENDING_SHIPPING] ?: 0, "shipping", listOf(UserRepository.OrderStatus.PENDING_SHIPPING)),
                OrderStatusCount("待收货", counts[UserRepository.OrderStatus.PENDING_RECEIPT] ?: 0, "receiving", listOf(UserRepository.OrderStatus.PENDING_RECEIPT)),
                OrderStatusCount("待评价", counts[UserRepository.OrderStatus.PENDING_REVIEW] ?: 0, "comment", listOf(UserRepository.OrderStatus.PENDING_REVIEW)),
                OrderStatusCount("退款/售后", (counts[UserRepository.OrderStatus.COMPLETED] ?: 0) + (counts[UserRepository.OrderStatus.CANCELLED] ?: 0), "refund", listOf(UserRepository.OrderStatus.COMPLETED, UserRepository.OrderStatus.CANCELLED)),
            )
        } catch (_: Exception) {
            orderCounts = listOf(
                OrderStatusCount("待付款", 0, "unpaid", listOf(UserRepository.OrderStatus.PENDING_PAYMENT)),
                OrderStatusCount("待发货", 0, "shipping", listOf(UserRepository.OrderStatus.PENDING_SHIPPING)),
                OrderStatusCount("待收货", 0, "receiving", listOf(UserRepository.OrderStatus.PENDING_RECEIPT)),
                OrderStatusCount("待评价", 0, "comment", listOf(UserRepository.OrderStatus.PENDING_REVIEW)),
                OrderStatusCount("退款/售后", 0, "refund", listOf(UserRepository.OrderStatus.COMPLETED, UserRepository.OrderStatus.CANCELLED)),
            )
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
    ) {
        // ===== A01: 用户头部 =====
        ProfileHeader(onSettingsClick = onSettingsClick, onCustomerServiceClick = onCustomerServiceClick, avatarBitmap = avatarBitmap, nickname = displayName)

        // ===== 内容区 =====
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            // ===== A02: 购物车预览 =====
            CartPreviewSection(onCartClick = onCartClick, cartItems = cartItems)

            // ===== A03: 我的订单 =====
            OrderStatusSection(orderCounts = orderCounts, onOrdersClick = onOrdersClick)

            // ===== A04: 常用功能 =====
            ProfileFeatureGrid(
                favoriteCount = favoriteCount,
                footprintCount = footprintCount,
                onFavoritesClick = onFavoritesClick,
                onFootprintsClick = onFootprintsClick,
            )

            // ===== A05: 领券中心 =====
            CouponCenterSection()

            // 底部留白
            Spacer(Modifier.height(24.dp))
        }
    }
}
