package com.shopping.agent.ui.screens

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import com.shopping.agent.data.model.*
import com.shopping.agent.ui.theme.*
import com.shopping.agent.viewmodel.ProductDetailUiState
import com.shopping.agent.viewmodel.ProductDetailViewModel

// Brand colors
private val CoralRed = Color(0xFFFF5C5C)
private val CoralRedLight = Color(0xFFFFF0F0)
private val PinkAccent = Color(0xFFFF6B8A)
private val BlueAccent = Color(0xFF4A90D9)
private val BlueLight = Color(0xFFF0F4FF)
private val WarmBg = Color(0xFFFFF8F0)
private val GreenCheck = Color(0xFF2ECC71)
private val TagBlue = Color(0xFFEBF3FC)
private val TagBlueText = Color(0xFF4A90D9)
private val CouponRed = Color(0xFFFFF0ED)
private val CouponRedBorder = Color(0xFFFFD4CC)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProductDetailScreen(
    productId: String,
    onBack: () -> Unit,
    onAddToCart: (String) -> Unit = {},
    onBuyNow: (String) -> Unit = {},
    onCustomerServiceClick: () -> Unit = {},
    viewModel: ProductDetailViewModel,
) {
    val uiState by viewModel.uiState.collectAsState()

    LaunchedEffect(productId) {
        viewModel.loadProduct(productId)
    }

    val snackbarHostState = remember { SnackbarHostState() }
    LaunchedEffect(uiState.addToCartResult) {
        uiState.addToCartResult?.let {
            snackbarHostState.showSnackbar(it)
            viewModel.dismissResult()
        }
    }
    LaunchedEffect(uiState.favoriteResult) {
        uiState.favoriteResult?.let {
            snackbarHostState.showSnackbar(it)
            viewModel.dismissFavoriteResult()
        }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        bottomBar = {
            ProductBottomActionBar(
                isFavorited = uiState.isFavorited,
                isFollowingShop = uiState.isFollowingShop,
                onToggleFavorite = { viewModel.toggleFavorite() },
                onToggleFollowShop = { viewModel.toggleFollowShop() },
                onCustomerServiceClick = onCustomerServiceClick,
                onAddToCart = {
                    viewModel.addToCart()
                    onAddToCart(productId)
                },
                onBuyNow = {
                    onBuyNow(productId)
                },
            )
        },
        containerColor = Color.Transparent,
    ) { innerPadding ->
        if (uiState.isLoading) {
            Box(Modifier.fillMaxSize().padding(innerPadding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = CoralRed)
            }
        } else if (uiState.product == null) {
            Box(Modifier.fillMaxSize().padding(innerPadding), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("商品加载失败", color = Color.Gray)
                    Spacer(Modifier.height(12.dp))
                    OutlinedButton(onClick = { viewModel.loadProduct(productId) }) {
                        Text("重试", color = CoralRed)
                    }
                }
            }
        } else {
            val product = uiState.product ?: return@Scaffold
            // 底部内边距由 Scaffold 处理，顶部不留间距（图片贴顶）
            val contentPadding = PaddingValues(
                start = innerPadding.calculateStartPadding(LayoutDirection.Ltr),
                end = innerPadding.calculateEndPadding(LayoutDirection.Ltr),
                top = 0.dp,
                bottom = innerPadding.calculateBottomPadding(),
            )
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(contentPadding)
                    .verticalScroll(rememberScrollState())
                    .background(Neutral50),
            ) {
                // 图片贴顶 + 浮层控制栏
                ProductHeroGallery(
                    images = product.images,
                    campaign = product.campaign,
                    onBack = onBack,
                )
                ProductInfoCard(product = product)
                CouponBenefitCard(coupons = product.coupons, savedAmount = product.price.savedAmount)
                LogisticsGuaranteeCard(delivery = product.delivery, guarantee = product.guarantee)
                ProductSpecGrid(specs = product.specs)
                ReviewSummarySection(reviews = product.reviews)
                ShopInfoCard(
                    shop = product.shop,
                    isFollowing = uiState.isFollowingShop,
                    onToggleFollow = { viewModel.toggleFollowShop() },
                )
                Spacer(Modifier.height(100.dp))
            }
        }
    }
}

// ─── 1. Hero Gallery ────────────────────────────────────

@Composable
private fun ProductHeroGallery(
    images: List<String>,
    campaign: CampaignInfo?,
    onBack: () -> Unit = {},
) {
    Box(modifier = Modifier.fillMaxWidth()) {
        if (images.isEmpty()) {
            Box(
                Modifier.fillMaxWidth().height(320.dp).background(BlueLight),
                contentAlignment = Alignment.Center,
            ) {
                Icon(Icons.Default.Image, "无图片", tint = Color.Gray, modifier = Modifier.size(48.dp))
            }
        } else {
            val pagerState = rememberPagerState(pageCount = { images.size })
            Column {
                HorizontalPager(
                    state = pagerState,
                    modifier = Modifier.fillMaxWidth().height(400.dp),
                ) { page ->
                    AsyncImage(
                        model = images[page],
                        contentDescription = "商品图片 ${page + 1}",
                        modifier = Modifier.fillMaxSize(),
                        contentScale = ContentScale.Crop,
                    )
                }
                // Dot indicators
                if (images.size > 1) {
                    Row(
                        Modifier.fillMaxWidth().padding(vertical = 8.dp),
                        horizontalArrangement = Arrangement.Center,
                    ) {
                        repeat(images.size) { idx ->
                            val isSelected = pagerState.currentPage == idx
                            Box(
                                Modifier
                                    .padding(horizontal = 4.dp)
                                    .size(if (isSelected) 8.dp else 6.dp)
                                    .clip(CircleShape)
                                    .background(if (isSelected) CoralRed else Color.Gray.copy(alpha = 0.3f)),
                            )
                        }
                    }
                }
            }
        }

        // ── Overlaid controls ──
        // 顶部渐变遮罩
        Box(
            Modifier
                .fillMaxWidth()
                .height(80.dp)
                .align(Alignment.TopCenter)
                .background(
                    Brush.verticalGradient(
                        colors = listOf(Color.Black.copy(alpha = 0.35f), Color.Transparent)
                    )
                ),
        )

        // 返回按钮
        IconButton(
            onClick = onBack,
            modifier = Modifier
                .align(Alignment.TopStart)
                .padding(top = 4.dp, start = 4.dp)
                .size(40.dp),
        ) {
            Icon(
                Icons.AutoMirrored.Filled.ArrowBack,
                "返回",
                tint = Color.White,
                modifier = Modifier.size(24.dp),
            )
        }

        // 右侧操作按钮
        Row(
            Modifier
                .align(Alignment.TopEnd)
                .padding(top = 8.dp, end = 8.dp),
        ) {
            IconButton(onClick = {}, modifier = Modifier.size(40.dp)) {
                Icon(Icons.Default.Share, "分享", tint = Color.White, modifier = Modifier.size(22.dp))
            }
            IconButton(onClick = {}, modifier = Modifier.size(40.dp)) {
                Icon(Icons.Default.MoreHoriz, "更多", tint = Color.White, modifier = Modifier.size(22.dp))
            }
        }

        // Campaign overlay badges
        if (campaign != null) {
            Column(
                Modifier.align(Alignment.TopStart).padding(top = 48.dp, start = 12.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                // Campaign title badge
                Surface(
                    shape = RoundedCornerShape(4.dp),
                    color = CoralRed,
                ) {
                    Text(
                        campaign.title,
                        Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
                        color = Color.White,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }
                // Subsidy badge
                if (campaign.subsidyText.isNotBlank()) {
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = CoralRedLight,
                    ) {
                        Text(
                            campaign.subsidyText,
                            Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
                            color = CoralRed,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Medium,
                        )
                    }
                }
            }
        }

        // Spec bubble on bottom-right
        if (campaign != null && campaign.specBubble.isNotBlank()) {
            Surface(
                Modifier.align(Alignment.BottomEnd).padding(12.dp),
                shape = RoundedCornerShape(12.dp),
                color = Color.Black.copy(alpha = 0.55f),
            ) {
                Text(
                    campaign.specBubble,
                    Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
                    color = Color.White,
                    fontSize = 12.sp,
                )
            }
        }
    }
}

// ─── 2. Price & Title Card ──────────────────────────────

@Composable
private fun ProductInfoCard(product: ProductDetailData) {
    Surface(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 6.dp),
        shape = RoundedCornerShape(12.dp),
        color = Color.White,
        shadowElevation = 0.dp,
        border = BorderStroke(1.dp, Neutral100),
    ) {
        Column(Modifier.padding(14.dp)) {
            // Price row
            Row(verticalAlignment = Alignment.Bottom) {
                Text("¥", fontSize = 14.sp, color = CoralRed, fontWeight = FontWeight.Bold)
                Text(
                    product.price.current.toString(),
                    fontSize = 28.sp,
                    color = CoralRed,
                    fontWeight = FontWeight.Bold,
                )
                if (product.price.couponPrice != null) {
                    Spacer(Modifier.width(8.dp))
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = CoralRedLight,
                    ) {
                        Text(
                            "券后 ¥${product.price.couponPrice}",
                            Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                            fontSize = 13.sp,
                            color = CoralRed,
                            fontWeight = FontWeight.Medium,
                        )
                    }
                }
                if (product.price.origin != null) {
                    Spacer(Modifier.width(8.dp))
                    Text(
                        "¥${product.price.origin}",
                        fontSize = 13.sp,
                        color = Color.Gray,
                        textDecoration = TextDecoration.LineThrough,
                    )
                }
                Spacer(Modifier.weight(1f))
                if (product.price.salesText.isNotBlank()) {
                    Text(product.price.salesText, fontSize = 12.sp, color = Color.Gray)
                }
            }

            Spacer(Modifier.height(10.dp))

            // Title
            Text(
                product.title,
                fontSize = 15.sp,
                fontWeight = FontWeight.Medium,
                color = MaterialTheme.colorScheme.onSurface,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                lineHeight = 21.sp,
            )

            // Tags
            if (product.tags.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    product.tags.forEach { tag ->
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = TagBlue,
                        ) {
                            Text(
                                tag,
                                Modifier.padding(horizontal = 6.dp, vertical = 3.dp),
                                fontSize = 11.sp,
                                color = TagBlueText,
                            )
                        }
                    }
                }
            }
        }
    }
}

// ─── 3. Coupon / Benefit Card ───────────────────────────

@Composable
private fun CouponBenefitCard(coupons: List<CouponInfo>, savedAmount: Int) {
    if (coupons.isEmpty() && savedAmount == 0) return

    Surface(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 4.dp),
        shape = RoundedCornerShape(12.dp),
        color = Color.White,
        shadowElevation = 0.dp,
        border = BorderStroke(1.dp, Neutral100),
    ) {
        Column(Modifier.padding(14.dp)) {
            Text("优惠", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.onSurface)
            Spacer(Modifier.height(8.dp))
            coupons.forEach { coupon ->
                val (bg, border, textColor) = when (coupon.type) {
                    "subsidy" -> Triple(CoralRedLight, CoralRed, CoralRed)
                    else -> Triple(CouponRed, CouponRedBorder, CoralRed)
                }
                Surface(
                    Modifier.fillMaxWidth().padding(vertical = 3.dp),
                    shape = RoundedCornerShape(6.dp),
                    color = bg,
                    border = ButtonDefaults.outlinedButtonBorder(enabled = true).copy(
                        brush = Brush.horizontalGradient(listOf(border, border))
                    ).let { null },
                ) {
                    Row(
                        Modifier.padding(horizontal = 10.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            if (coupon.type == "subsidy") "礼金" else "券",
                            fontSize = 11.sp,
                            color = textColor,
                            fontWeight = FontWeight.Bold,
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(coupon.text, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurface)
                        Spacer(Modifier.weight(1f))
                        Icon(Icons.Default.ChevronRight, "展开", tint = Color.Gray, modifier = Modifier.size(16.dp))
                    }
                }
            }
            if (savedAmount > 0) {
                Spacer(Modifier.height(6.dp))
                Text(
                    "预计节省 ¥$savedAmount",
                    fontSize = 12.sp,
                    color = CoralRed,
                    fontWeight = FontWeight.Medium,
                )
            }
        }
    }
}

// ─── 4. Logistics & Guarantee Card ──────────────────────

@Composable
private fun LogisticsGuaranteeCard(delivery: DeliveryInfo, guarantee: List<String>) {
    Surface(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 4.dp),
        shape = RoundedCornerShape(12.dp),
        color = Color.White,
        shadowElevation = 0.dp,
        border = BorderStroke(1.dp, Neutral100),
    ) {
        Column(Modifier.padding(14.dp)) {
            // Delivery section
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.LocalShipping, "发货", tint = Color.Gray, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text(delivery.estimate, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurface)
                Spacer(Modifier.weight(1f))
                Text(delivery.shipping, fontSize = 12.sp, color = GreenCheck)
            }
            Spacer(Modifier.height(4.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.LocationOn, "发货地", tint = Color.Gray, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text(delivery.location, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurface)
            }

            // Guarantee badges
            if (guarantee.isNotEmpty()) {
                Spacer(Modifier.height(10.dp))
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    guarantee.forEach { item ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.CheckCircle, "保障", tint = GreenCheck, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text(item, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        }
    }
}

// ─── 5. Spec Grid ───────────────────────────────────────

@Composable
private fun ProductSpecGrid(specs: List<SpecItem>) {
    if (specs.isEmpty()) return

    Surface(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 4.dp),
        shape = RoundedCornerShape(12.dp),
        color = Color.White,
        shadowElevation = 0.dp,
        border = BorderStroke(1.dp, Neutral100),
    ) {
        Column(Modifier.padding(14.dp)) {
            Text("规格参数", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.onSurface)
            Spacer(Modifier.height(10.dp))
            val rows = specs.chunked(2)
            rows.forEach { row ->
                Row(Modifier.fillMaxWidth().padding(vertical = 5.dp)) {
                    row.forEach { spec ->
                        Row(
                            Modifier.weight(1f),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(spec.label, fontSize = 13.sp, color = Color.Gray)
                            Spacer(Modifier.width(6.dp))
                            Text(spec.value, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurface)
                        }
                    }
                    // Fill empty cell if odd count
                    if (row.size < 2) Spacer(Modifier.weight(1f))
                }
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            }
        }
    }
}

// ─── 6. Review Summary ──────────────────────────────────

@Composable
private fun ReviewSummarySection(reviews: ReviewSummary) {
    Surface(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 4.dp),
        shape = RoundedCornerShape(12.dp),
        color = Color.White,
        shadowElevation = 0.dp,
        border = BorderStroke(1.dp, Neutral100),
    ) {
        Column(Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("评价", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.onSurface)
                Spacer(Modifier.weight(1f))
                Text("${reviews.count}条评价", fontSize = 12.sp, color = Color.Gray)
                Icon(Icons.Default.ChevronRight, "查看全部", tint = Color.Gray, modifier = Modifier.size(16.dp))
            }

            // Good rate highlight
            Spacer(Modifier.height(8.dp))
            Surface(
                shape = RoundedCornerShape(8.dp),
                color = WarmBg,
            ) {
                Row(
                    Modifier.padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("好评率", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.width(8.dp))
                    Text(
                        reviews.goodRate,
                        fontSize = 20.sp,
                        color = CoralRed,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }

            // Keywords
            if (reviews.keywords.isNotEmpty()) {
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    reviews.keywords.take(4).forEach { kw ->
                        Surface(
                            shape = RoundedCornerShape(14.dp),
                            color = WarmBg,
                        ) {
                            Text(
                                kw,
                                Modifier.padding(horizontal = 12.dp, vertical = 5.dp),
                                fontSize = 12.sp,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }
    }
}

// ─── 7. Shop Info Card ──────────────────────────────────

@Composable
private fun ShopInfoCard(
    shop: ShopInfo,
    isFollowing: Boolean,
    onToggleFollow: () -> Unit,
) {
    Surface(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 4.dp),
        shape = RoundedCornerShape(12.dp),
        color = Color.White,
        shadowElevation = 0.dp,
        border = BorderStroke(1.dp, Neutral100),
    ) {
        Column(Modifier.padding(14.dp)) {
            // Shop header
            Row(verticalAlignment = Alignment.CenterVertically) {
                // Shop avatar placeholder
                Surface(
                    Modifier.size(44.dp),
                    shape = CircleShape,
                    color = BlueLight,
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(Icons.Default.Store, "店铺", tint = BlueAccent, modifier = Modifier.size(24.dp))
                    }
                }
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(shop.name, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.onSurface)
                        Spacer(Modifier.width(6.dp))
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = CoralRedLight,
                        ) {
                            Text(
                                shop.badge,
                                Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                                fontSize = 10.sp,
                                color = CoralRed,
                            )
                        }
                    }
                    Spacer(Modifier.height(3.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Star, "评分", tint = Color(0xFFFFB800), modifier = Modifier.size(14.dp))
                        Text(" ${shop.score}", fontSize = 12.sp, color = Color(0xFFFFB800), fontWeight = FontWeight.Bold)
                        if (shop.fans.isNotBlank()) {
                            Text("  ${shop.fans}", fontSize = 12.sp, color = Color.Gray)
                        }
                    }
                }
                // Follow button
                val followBg by animateColorAsState(
                    if (isFollowing) Color.Gray.copy(alpha = 0.15f) else CoralRed,
                )
                val followText by animateColorAsState(
                    if (isFollowing) Color.Gray else Color.White,
                )
                Button(
                    onClick = onToggleFollow,
                    colors = ButtonDefaults.buttonColors(containerColor = followBg),
                    shape = RoundedCornerShape(18.dp),
                    contentPadding = PaddingValues(horizontal = 18.dp, vertical = 6.dp),
                ) {
                    Text(
                        if (isFollowing) "已关注" else "+关注",
                        fontSize = 13.sp,
                        color = followText,
                    )
                }
            }

            Spacer(Modifier.height(10.dp))
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            Spacer(Modifier.height(10.dp))

            // Score row
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                ShopScoreItem("品质", shop.qualityScore)
                ShopScoreItem("发货", shop.deliveryScore)
                ShopScoreItem("服务", shop.serviceScore)
            }
        }
    }
}

@Composable
private fun ShopScoreItem(label: String, score: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, fontSize = 12.sp, color = Color.Gray)
        Text(
            score.ifBlank { "-" },
            fontSize = 14.sp,
            fontWeight = FontWeight.SemiBold,
            color = if (score.contains("高")) GreenCheck else MaterialTheme.colorScheme.onSurface,
        )
    }
}

// ─── 8. Bottom Action Bar ───────────────────────────────

@Composable
private fun ProductBottomActionBar(
    isFavorited: Boolean,
    isFollowingShop: Boolean,
    onToggleFavorite: () -> Unit,
    onToggleFollowShop: () -> Unit,
    onCustomerServiceClick: () -> Unit = {},
    onAddToCart: () -> Unit,
    onBuyNow: () -> Unit,
) {
    Surface(
        shadowElevation = 8.dp,
        color = Color.White,
    ) {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 10.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // Left icon buttons
            BottomActionIcon(Icons.Default.Store, "店铺", isActive = false, onClick = onToggleFollowShop)
            BottomActionIcon(Icons.Default.HeadsetMic, "客服", isActive = false, onClick = onCustomerServiceClick)
            BottomActionIcon(
                if (isFavorited) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                "收藏",
                isActive = isFavorited,
                onClick = onToggleFavorite,
            )

            Spacer(Modifier.width(8.dp))

            // Add to cart button
            Button(
                onClick = onAddToCart,
                modifier = Modifier.weight(1f).height(44.dp),
                shape = RoundedCornerShape(22.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = PinkAccent.copy(alpha = 0.15f),
                ),
            ) {
                Text("加入购物车", fontSize = 15.sp, color = PinkAccent, fontWeight = FontWeight.SemiBold)
            }

            Spacer(Modifier.width(8.dp))

            // Buy now button
            Button(
                onClick = onBuyNow,
                modifier = Modifier.weight(1f).height(44.dp),
                shape = RoundedCornerShape(22.dp),
                colors = ButtonDefaults.buttonColors(containerColor = CoralRed),
            ) {
                Text("立即购买", fontSize = 15.sp, color = Color.White, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun BottomActionIcon(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    isActive: Boolean,
    onClick: () -> Unit,
) {
    val tint = if (isActive) CoralRed else Color.Gray
    Column(
        Modifier
            .clickable(onClick = onClick)
            .padding(horizontal = 6.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(icon, label, tint = tint, modifier = Modifier.size(22.dp))
        Text(label, fontSize = 10.sp, color = tint)
    }
}
