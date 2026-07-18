package com.shopping.agent.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.shopping.agent.data.model.CartItem
import com.shopping.agent.ui.components.GradientTopBar
import com.shopping.agent.ui.theme.*
import com.shopping.agent.viewmodel.CartViewModel

// ═══════════════════════════════════════════════════════════════
// 常量定义
// ═══════════════════════════════════════════════════════════════

/** 快速清理面板占屏幕高度比例 */
private const val QUICK_CLEAN_HEIGHT_FRACTION = 0.7f

/** 商品图片占卡片宽度比例 */
private const val PRODUCT_IMAGE_WIDTH_FRACTION = 0.32f

/** 快速清理每行商品数 */
private const val QUICK_CLEAN_COLUMNS = 4

/** 数量输入范围 */
private const val QUANTITY_MIN = 1
private const val QUANTITY_MAX = 1000

/** 选中的圆圈按钮颜色 */
private val CheckedColor = Color(0xFF4A90D9)

/** 未选中的圆圈按钮颜色 */
private val UncheckedColor = Color(0xFFCCCCCC)

// ═══════════════════════════════════════════════════════════════
// 主页面
// ═══════════════════════════════════════════════════════════════

/**
 * 购物车页面 — 底部导航 Tab 页。
 *
 * 支持两种模式：
 * - 普通模式：商品列表（按商家分组）、底部结算栏
 * - 管理模式：商品多选、批量删除、快速清理面板
 *
 * @param viewModel 购物车 ViewModel
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CartScreen(
    viewModel: CartViewModel = viewModel(),
    onCheckout: () -> Unit = { viewModel.placeOrder() },
    onNavigateToHome: () -> Unit = {},
) {
    val uiState by viewModel.uiState.collectAsState()

    LaunchedEffect(Unit) { viewModel.loadCart() }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
    ) {
        // ── 顶栏 ──
        CartTopBar(
            isManageMode = uiState.isManageMode,
            hasItems = uiState.items.isNotEmpty(),
            onToggleManageMode = { viewModel.toggleManageMode() },
        )

        // ── 主体内容 ──
        when {
            uiState.isLoading -> {
                Box(Modifier.weight(1f), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Primary)
                }
            }
            uiState.error != null && uiState.items.isEmpty() -> {
                CartErrorState(
                    message = uiState.error ?: "加载失败",
                    onRetry = { viewModel.loadCart() },
                )
            }
            uiState.items.isEmpty() -> {
                CartEmptyState(onNavigateToHome = onNavigateToHome)
            }
            else -> {
                CartItemList(
                    items = uiState.items,
                    selectedProductIds = uiState.selectedProductIds,
                    isManageMode = uiState.isManageMode,
                    onToggleSelect = { viewModel.toggleItemSelection(it) },
                    onToggleBrandSelect = { viewModel.toggleBrandSelection(it) },
                    isBrandFullySelected = { viewModel.isBrandFullySelected(it) },
                    onIncrease = { viewModel.increaseQuantity(it) },
                    onDecrease = { viewModel.decreaseQuantity(it) },
                    onUpdateQuantity = { productId, quantity -> viewModel.updateQuantity(productId, quantity) },
                )
            }
        }

        // ── 底部栏 ──
        if (uiState.items.isNotEmpty()) {
            if (uiState.isManageMode) {
                // 管理模式底部操作栏
                ManageBottomBar(
                    selectedCount = uiState.selectedProductIds.size,
                    totalCount = uiState.items.size,
                    onSelectAll = { viewModel.toggleSelectAll() },
                    onQuickClean = { viewModel.openQuickClean() },
                    onDeleteSelected = { viewModel.performDeleteSelected() },
                )
            } else {
                // 普通模式底部结算栏
                CartBottomBar(
                    selectedCount = uiState.selectedProductIds.size,
                    totalCount = uiState.items.size,
                    selectedTotalPrice = uiState.selectedTotalPrice,
                    onSelectAll = { viewModel.toggleSelectAll() },
                    onCheckout = onCheckout,
                )
            }
        }
    }

    // ── 快速清理面板 ──
    if (uiState.showQuickClean) {
        QuickCleanSheet(
            items = uiState.items,
            selectedIds = uiState.quickCleanSelectedIds,
            onDismiss = { viewModel.closeQuickClean() },
            onToggleSelect = { viewModel.toggleQuickCleanSelection(it) },
            onSelectAll = { viewModel.toggleQuickCleanSelectAll() },
            onDelete = { viewModel.performQuickCleanDelete() },
        )
    }

    // ── 下单成功弹窗 ──
    if (uiState.orderResult != null) {
        OrderSuccessDialog(
            message = uiState.orderResult!!,
            onDismiss = { viewModel.dismissOrderResult() },
        )
    }
}

// ═══════════════════════════════════════════════════════════════
// 顶栏
// ═══════════════════════════════════════════════════════════════

@Composable
private fun CartTopBar(
    isManageMode: Boolean,
    hasItems: Boolean,
    onToggleManageMode: () -> Unit,
) {
    GradientTopBar {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // 标题
            Text(
                text = "购物车",
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onSurface,
                fontWeight = FontWeight.Bold,
            )

            // 右侧：管理/完成按钮（仅在有商品时显示）
            if (hasItems) {
                TextButton(onClick = onToggleManageMode) {
                    Text(
                        text = if (isManageMode) "完成" else "管理",
                        color = MaterialTheme.colorScheme.onSurface,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════
// 管理模式底部操作栏
// ═══════════════════════════════════════════════════════════════

@Composable
private fun ManageBottomBar(
    selectedCount: Int,
    totalCount: Int,
    onSelectAll: () -> Unit,
    onQuickClean: () -> Unit,
    onDeleteSelected: () -> Unit,
) {
    val isAllSelected = selectedCount == totalCount && totalCount > 0

    Surface(
        shadowElevation = 8.dp,
        color = MaterialTheme.colorScheme.surface,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .padding(horizontal = 16.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // 左侧：全选按钮（带真实选中状态）
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.clickable { onSelectAll() },
            ) {
                SelectCircle(isSelected = isAllSelected, modifier = Modifier.size(24.dp))
                Spacer(Modifier.width(8.dp))
                Text(
                    text = "全选",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurface,
                )
            }

            // 右侧操作按钮
            Row(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                // 快速清理
                TextButton(onClick = onQuickClean) {
                    Text(
                        "🗑️ 快速清理",
                        color = Primary,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
                // 删除
                TextButton(
                    onClick = onDeleteSelected,
                    enabled = selectedCount > 0,
                ) {
                    Text(
                        text = "删除${if (selectedCount > 0) "（$selectedCount）" else ""}",
                        color = if (selectedCount > 0) ErrorColor else MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════
// 空购物车
// ═══════════════════════════════════════════════════════════════

@Composable
private fun ColumnScope.CartEmptyState(onNavigateToHome: () -> Unit = {}) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .weight(1f),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(
                Icons.Default.ShoppingCart,
                contentDescription = "空购物车",
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.size(64.dp),
            )
            Spacer(Modifier.height(12.dp))
            Text(
                text = "购物车为空",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodyLarge,
            )
            Text(
                text = "去首页逛逛 AI 导购推荐吧",
                color = Primary,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier
                    .clickable { onNavigateToHome() }
                    .padding(vertical = 4.dp),
            )
        }
    }
}

/** 购物车加载失败时的错误页，提供重试入口 */
@Composable
private fun ColumnScope.CartErrorState(
    message: String,
    onRetry: () -> Unit,
) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .weight(1f),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(
                Icons.Default.Close,
                contentDescription = "加载失败",
                tint = ErrorColor,
                modifier = Modifier.size(48.dp),
            )
            Spacer(Modifier.height(12.dp))
            Text(
                text = "购物车加载失败",
                color = MaterialTheme.colorScheme.onSurface,
                style = MaterialTheme.typography.bodyLarge,
            )
            Text(
                text = message,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodySmall,
            )
            Spacer(Modifier.height(16.dp))
            OutlinedButton(onClick = onRetry) {
                Text("重试", color = Primary)
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════
// 商品列表（按商家分组）
// ═══════════════════════════════════════════════════════════════

@Composable
private fun ColumnScope.CartItemList(
    items: List<CartItem>,
    selectedProductIds: Set<String>,
    isManageMode: Boolean,
    onToggleSelect: (String) -> Unit,
    onToggleBrandSelect: (String) -> Unit,
    isBrandFullySelected: (String) -> Boolean,
    onIncrease: (String) -> Unit,
    onDecrease: (String) -> Unit,
    onUpdateQuantity: (String, Int) -> Unit,
) {
    // 按商家分组
    val groupedItems = remember(items) {
        items.groupBy { it.product.brand ?: "其他" }
    }

    LazyColumn(
        modifier = Modifier
            .fillMaxWidth()
            .weight(1f),
        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        groupedItems.forEach { (brand, brandItems) ->
            item(key = "brand_$brand") {
                BrandGroupCard(
                    brand = brand,
                    items = brandItems,
                    isBrandSelected = isBrandFullySelected(brand),
                    selectedProductIds = selectedProductIds,
                    isManageMode = isManageMode,
                    onToggleBrandSelect = { onToggleBrandSelect(brand) },
                    onToggleSelect = onToggleSelect,
                    onIncrease = onIncrease,
                    onDecrease = onDecrease,
                    onUpdateQuantity = onUpdateQuantity,
                )
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════
// 商家分组卡片
// ═══════════════════════════════════════════════════════════════

@Composable
private fun BrandGroupCard(
    brand: String,
    items: List<CartItem>,
    isBrandSelected: Boolean,
    selectedProductIds: Set<String>,
    isManageMode: Boolean,
    onToggleBrandSelect: () -> Unit,
    onToggleSelect: (String) -> Unit,
    onIncrease: (String) -> Unit,
    onDecrease: (String) -> Unit,
    onUpdateQuantity: (String, Int) -> Unit,
) {
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.surface,
        shadowElevation = 1.dp,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column {
            // 商家头部：全选 + 商家名
            BrandHeader(
                brand = brand,
                isSelected = isBrandSelected,
                onToggleSelect = onToggleBrandSelect,
            )

            // 商品列表
            items.forEach { item ->
                CartProductRow(
                    item = item,
                    isSelected = selectedProductIds.contains(item.product.productId),
                    isManageMode = isManageMode,
                    onToggleSelect = { onToggleSelect(item.product.productId) },
                    onIncrease = { onIncrease(item.product.productId) },
                    onDecrease = { onDecrease(item.product.productId) },
                    onUpdateQuantity = { qty -> onUpdateQuantity(item.product.productId, qty) },
                )
            }
        }
    }
}

@Composable
private fun BrandHeader(
    brand: String,
    isSelected: Boolean,
    onToggleSelect: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onToggleSelect() }
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        SelectCircle(isSelected = isSelected, modifier = Modifier.size(22.dp))
        Spacer(Modifier.width(10.dp))
        Text(
            text = brand,
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurface,
            fontWeight = FontWeight.Medium,
        )
    }
}

// ═══════════════════════════════════════════════════════════════
// 单个商品行
// ═══════════════════════════════════════════════════════════════

@Composable
private fun CartProductRow(
    item: CartItem,
    isSelected: Boolean,
    isManageMode: Boolean,
    onToggleSelect: () -> Unit,
    onIncrease: () -> Unit,
    onDecrease: () -> Unit,
    onUpdateQuantity: (Int) -> Unit,
) {
    // 数量编辑弹窗状态
    var showQuantityDialog by remember { mutableStateOf(false) }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // 第一列：选中圆圈按钮
        SelectCircle(
            isSelected = isSelected,
            modifier = Modifier
                .size(22.dp)
                .clickable { onToggleSelect() },
        )

        Spacer(Modifier.width(10.dp))

        // 第二列：商品图片
        AsyncImage(
            model = item.product.imageUrl ?: "",
            contentDescription = item.product.title,
            modifier = Modifier
                .fillMaxWidth(PRODUCT_IMAGE_WIDTH_FRACTION)
                .aspectRatio(1f)
                .clip(RoundedCornerShape(8.dp)),
            contentScale = ContentScale.Crop,
        )

        Spacer(Modifier.width(10.dp))

        // 第三列：商品信息
        Column(modifier = Modifier.weight(1f)) {
            // 商品名称（单行省略）
            Text(
                text = item.product.title,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )

            Spacer(Modifier.height(6.dp))

            // 价格 + 数量控制
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                // 价格
                Text(
                    text = "¥${item.product.price}",
                    style = MaterialTheme.typography.titleMedium,
                    color = Primary,
                    fontWeight = FontWeight.Bold,
                )

                // 数量控制
                QuantityControl(
                    quantity = item.quantity,
                    onIncrease = onIncrease,
                    onDecrease = onDecrease,
                    onQuantityClick = { showQuantityDialog = true },
                )
            }
        }
    }

    // 数量编辑弹窗
    if (showQuantityDialog) {
        QuantityEditDialog(
            currentQuantity = item.quantity,
            onConfirm = { newQty ->
                onUpdateQuantity(newQty)
                showQuantityDialog = false
            },
            onDismiss = { showQuantityDialog = false },
        )
    }
}

// ═══════════════════════════════════════════════════════════════
// 数量控制组件
// ═══════════════════════════════════════════════════════════════

@Composable
private fun QuantityControl(
    quantity: Int,
    onIncrease: () -> Unit,
    onDecrease: () -> Unit,
    onQuantityClick: () -> Unit,
) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        // 减少按钮
        IconButton(
            onClick = onDecrease,
            modifier = Modifier.size(28.dp),
        ) {
            Icon(
                Icons.Default.Remove,
                contentDescription = "减少",
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.size(16.dp),
            )
        }

        // 数量（可点击编辑）
        Box(
            modifier = Modifier
                .widthIn(min = 32.dp)
                .clickable { onQuantityClick() },
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = quantity.toString(),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface,
                textAlign = TextAlign.Center,
            )
        }

        // 增加按钮
        IconButton(
            onClick = onIncrease,
            modifier = Modifier.size(28.dp),
        ) {
            Icon(
                Icons.Default.Add,
                contentDescription = "增加",
                tint = Primary,
                modifier = Modifier.size(16.dp),
            )
        }
    }
}

// ═══════════════════════════════════════════════════════════════
// 数量编辑弹窗
// ═══════════════════════════════════════════════════════════════

@Composable
private fun QuantityEditDialog(
    currentQuantity: Int,
    onConfirm: (Int) -> Unit,
    onDismiss: () -> Unit,
) {
    var inputText by remember { mutableStateOf(currentQuantity.toString()) }
    var hasError by remember { mutableStateOf(false) }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false),
    ) {
        Surface(
            shape = RoundedCornerShape(16.dp),
            color = MaterialTheme.colorScheme.surface,
            modifier = Modifier
                .fillMaxWidth(0.8f)
                .padding(16.dp),
        ) {
            Column(
                modifier = Modifier.padding(20.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(
                    text = "修改数量",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurface,
                    fontWeight = FontWeight.Bold,
                )
                Spacer(Modifier.height(16.dp))

                OutlinedTextField(
                    value = inputText,
                    onValueChange = { newValue ->
                        // 仅允许数字输入
                        if (newValue.isEmpty() || newValue.all { it.isDigit() }) {
                            inputText = newValue
                            val num = newValue.toIntOrNull()
                            hasError = num == null || num < QUANTITY_MIN || num > QUANTITY_MAX
                        }
                    },
                    label = { Text("数量（$QUANTITY_MIN-$QUANTITY_MAX）") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    isError = hasError,
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                if (hasError) {
                    Text(
                        text = "请输入${QUANTITY_MIN}-${QUANTITY_MAX}之间的整数",
                        color = ErrorColor,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                Spacer(Modifier.height(16.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    OutlinedButton(
                        onClick = onDismiss,
                        modifier = Modifier.weight(1f),
                    ) {
                        Text("取消")
                    }
                    Button(
                        onClick = {
                            val num = inputText.toIntOrNull()
                            if (num != null && num in QUANTITY_MIN..QUANTITY_MAX) {
                                onConfirm(num)
                            }
                        },
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(containerColor = Primary),
                        enabled = !hasError && inputText.isNotEmpty(),
                    ) {
                        Text("确定", color = OnPrimary)
                    }
                }
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════
// 底部结算栏
// ═══════════════════════════════════════════════════════════════

@Composable
private fun CartBottomBar(
    selectedCount: Int,
    totalCount: Int,
    selectedTotalPrice: Double,
    onSelectAll: () -> Unit,
    onCheckout: () -> Unit,
) {
    Surface(
        shadowElevation = 8.dp,
        color = MaterialTheme.colorScheme.surface,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier
                .padding(horizontal = 16.dp, vertical = 12.dp)
                .fillMaxWidth()
                .navigationBarsPadding(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // 左侧：全选 + 合计
            Row(verticalAlignment = Alignment.CenterVertically) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.clickable { onSelectAll() },
                ) {
                    SelectCircle(
                        isSelected = selectedCount == totalCount && totalCount > 0,
                        modifier = Modifier.size(22.dp),
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        text = "全选",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Spacer(Modifier.width(16.dp))
                Column {
                    Text(
                        text = "合计",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Text(
                        text = "¥%.2f".format(selectedTotalPrice),
                        color = Primary,
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }

            // 右侧：去结算
            Button(
                onClick = onCheckout,
                shape = RadiusFull,
                colors = ButtonDefaults.buttonColors(containerColor = Primary),
                modifier = Modifier.height(44.dp),
                enabled = selectedCount > 0,
            ) {
                Text(
                    text = "去结算",
                    color = OnPrimary,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Bold,
                )
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════
// 选中圆圈组件
// ═══════════════════════════════════════════════════════════════

@Composable
private fun SelectCircle(
    isSelected: Boolean,
    modifier: Modifier = Modifier,
) {
    // 三层背景结构：外圈 (UncheckedColor) → 内圈填充 (CheckedColor) → 内容
    // 未选中：仅显示外圈灰色圆环效果（灰色实心圆）
    // 已选中：蓝色实心圆 + 白色对勾
    val backgroundColor = if (isSelected) CheckedColor else UncheckedColor
    Box(
        modifier = modifier
            .size(22.dp)
            .clip(CircleShape)
            .background(backgroundColor, CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        if (isSelected) {
            Icon(
                Icons.Default.Check,
                contentDescription = "已选中",
                tint = Color.White,
                modifier = Modifier.size(14.dp),
            )
        }
    }
}

// ═══════════════════════════════════════════════════════════════
// 下单成功弹窗
// ═══════════════════════════════════════════════════════════════

@Composable
private fun OrderSuccessDialog(
    message: String,
    onDismiss: () -> Unit,
) {
    Dialog(onDismissRequest = onDismiss) {
        Surface(
            shape = RoundedCornerShape(16.dp),
            color = MaterialTheme.colorScheme.surface,
        ) {
            Column(
                modifier = Modifier.padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Icon(
                    Icons.Default.Check,
                    contentDescription = null,
                    tint = Primary,
                    modifier = Modifier
                        .size(48.dp)
                        .clip(CircleShape)
                        .background(PrimaryLight),
                )
                Spacer(Modifier.height(12.dp))
                Text(
                    text = "下单成功！",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                Spacer(Modifier.height(8.dp))
                Text(
                    text = message,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    textAlign = TextAlign.Center,
                )
                Spacer(Modifier.height(16.dp))
                Button(
                    onClick = onDismiss,
                    shape = RadiusFull,
                    colors = ButtonDefaults.buttonColors(containerColor = Primary),
                ) {
                    Text("完成", color = OnPrimary)
                }
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════
// 快速清理面板
// ═══════════════════════════════════════════════════════════════

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun QuickCleanSheet(
    items: List<CartItem>,
    selectedIds: Set<String>,
    onDismiss: () -> Unit,
    onToggleSelect: (String) -> Unit,
    onSelectAll: () -> Unit,
    onDelete: () -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        modifier = Modifier.fillMaxHeight(QUICK_CLEAN_HEIGHT_FRACTION),
        containerColor = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(topStart = 16.dp, topEnd = 16.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 24.dp),
        ) {
            // 顶部栏
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = "快速清理",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurface,
                        fontWeight = FontWeight.Bold,
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        text = "共${items.size}件商品",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = onSelectAll) {
                        Text(
                            text = if (selectedIds.size == items.size) "取消全选" else "全选",
                            color = Primary,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    IconButton(onClick = onDismiss, modifier = Modifier.size(32.dp)) {
                        Icon(
                            Icons.Default.Close,
                            contentDescription = "关闭",
                            tint = MaterialTheme.colorScheme.onSurface,
                            modifier = Modifier.size(20.dp),
                        )
                    }
                }
            }

            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)

            // 主体：4 列网格
            LazyVerticalGrid(
                columns = GridCells.Fixed(QUICK_CLEAN_COLUMNS),
                modifier = Modifier
                    .weight(1f)
                    .padding(12.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(items, key = { it.product.productId }) { item ->
                    QuickCleanItemCard(
                        item = item,
                        isSelected = selectedIds.contains(item.product.productId),
                        onToggle = { onToggleSelect(item.product.productId) },
                    )
                }
            }

            // 底部删除按钮
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            Button(
                onClick = onDelete,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 12.dp)
                    .height(44.dp),
                shape = RoundedCornerShape(8.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (selectedIds.isNotEmpty()) ErrorColor else MaterialTheme.colorScheme.outlineVariant,
                ),
                enabled = selectedIds.isNotEmpty(),
            ) {
                Text(
                    text = "删除（${selectedIds.size}）",
                    color = if (selectedIds.isNotEmpty()) Color.White else MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

/** 快速清理中的单个商品卡片 */
@Composable
private fun QuickCleanItemCard(
    item: CartItem,
    isSelected: Boolean,
    onToggle: () -> Unit,
) {
    Box(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(8.dp))
                .background(MaterialTheme.colorScheme.background)
                .clickable { onToggle() }
                .padding(6.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            // 商品图片
            AsyncImage(
                model = item.product.imageUrl ?: "",
                contentDescription = item.product.title,
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(1f)
                    .clip(RoundedCornerShape(8.dp)),
                contentScale = ContentScale.Crop,
            )
        }

        // 右上角选中标记
        if (isSelected) {
            Box(
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(4.dp)
                    .size(20.dp)
                    .clip(CircleShape)
                    .background(Primary),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    Icons.Default.Check,
                    contentDescription = "已选中",
                    tint = Color.White,
                    modifier = Modifier.size(12.dp),
                )
            }
        }
    }
}
