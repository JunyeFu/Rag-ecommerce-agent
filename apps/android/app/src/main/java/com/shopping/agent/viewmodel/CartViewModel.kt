package com.shopping.agent.viewmodel

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.shopping.agent.core.network.NetworkConfig
import com.shopping.agent.data.local.CartEvents
import com.shopping.agent.data.local.CartSessionManager
import com.shopping.agent.data.local.UserRepository
import com.shopping.agent.data.model.CartItem
import com.shopping.agent.data.model.Product
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

/** 购物车 UI 状态 */
data class CartUiState(
    /** 购物车全部商品列表 */
    val items: List<CartItem> = emptyList(),
    /** 是否处于管理模式 */
    val isManageMode: Boolean = false,
    /** 当前选中的商品 productId 集合（仅当前缓存生效） */
    val selectedProductIds: Set<String> = emptySet(),
    /** 选中商品总价（两位小数） */
    val selectedTotalPrice: Double = 0.0,
    /** 全部商品总价 */
    val totalPrice: Double = 0.0,
    /** 是否正在加载 */
    val isLoading: Boolean = false,
    /** 加载错误信息 */
    val error: String? = null,
    /** 下单结果信息 */
    val orderResult: String? = null,
    /** 快速清理面板是否可见 */
    val showQuickClean: Boolean = false,
    /** 快速清理中选中的商品 productId 集合 */
    val quickCleanSelectedIds: Set<String> = emptySet(),
)

/** 购物车商品数量 */
val CartUiState.itemCount: Int get() = items.size

class CartViewModel(application: Application) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow(CartUiState())
    val uiState: StateFlow<CartUiState> = _uiState.asStateFlow()

    private val repository = UserRepository(application)

    /** 会话 ID，用于兼容旧数据 */
    private val sessionId: String by lazy {
        CartSessionManager.getOrCreate(application)
    }

    init {
        viewModelScope.launch {
            CartEvents.changes.collect {
                loadCart()
            }
        }
    }

    // ═══════════════════════════════════════════════════════════
    // 后端同步辅助方法
    // ═══════════════════════════════════════════════════════════

    /** 获取当前用户 ID（用于后端 user_id 参数） */
    private fun getUserId(): String = repository.getUserId()

    /** 计算购物车总价和选中总价 */
    private fun calcTotals(items: List<CartItem>, selectedIds: Set<String>): Pair<Double, Double> {
        val total = items.sumOf { it.product.price * it.quantity }
        val selectedTotal = items.filter { it.product.productId in selectedIds }.sumOf { it.product.price * it.quantity }
        return total to selectedTotal
    }

    /** 调用后端 API：添加商品到购物车 */
    private suspend fun syncAddToBackend(product: Product, quantity: Int = 1): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val userId = getUserId()
                val baseUrl = NetworkConfig.BASE_URL
                val body = JSONObject().apply {
                    put("session_id", sessionId)
                    put("product_id", product.productId)
                    put("title", product.title)
                    put("price", product.price)
                    put("quantity", quantity)
                    put("user_id", userId)
                }
                val request = Request.Builder()
                    .url("$baseUrl/api/v1/cart/add")
                    .post(body.toString().toRequestBody("application/json".toMediaType()))
                    .build()
                val response = NetworkConfig.httpClient.newCall(request).execute()
                if (response.isSuccessful) {
                    Log.d("CartVM", "后端同步：添加 ${product.title.take(20)} 成功")
                    true
                } else {
                    Log.w("CartVM", "后端同步：添加失败 ${response.code}")
                    false
                }
            } catch (e: Exception) {
                Log.e("CartVM", "后端同步：添加异常 ${e.message}", e)
                false
            }
        }
    }

    /** 调用后端 API：从购物车删除商品 */
    private suspend fun syncRemoveFromBackend(productId: String): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val userId = getUserId()
                val baseUrl = NetworkConfig.BASE_URL
                val body = JSONObject().apply {
                    put("session_id", sessionId)
                    put("product_id", productId)
                    put("user_id", userId)
                }
                val request = Request.Builder()
                    .url("$baseUrl/api/v1/cart/remove")
                    .post(body.toString().toRequestBody("application/json".toMediaType()))
                    .build()
                val response = NetworkConfig.httpClient.newCall(request).execute()
                response.isSuccessful.also {
                    if (!it) Log.w("CartVM", "后端同步：删除失败 ${response.code}")
                }
            } catch (e: Exception) {
                Log.e("CartVM", "后端同步：删除异常 ${e.message}", e)
                false
            }
        }
    }

    /** 调用后端 API：更新商品数量 */
    private suspend fun syncUpdateQuantityToBackend(productId: String, quantity: Int): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val userId = getUserId()
                val baseUrl = NetworkConfig.BASE_URL
                val body = JSONObject().apply {
                    put("session_id", sessionId)
                    put("product_id", productId)
                    put("quantity", quantity)
                    put("user_id", userId)
                }
                val request = Request.Builder()
                    .url("$baseUrl/api/v1/cart/quantity")
                    .put(body.toString().toRequestBody("application/json".toMediaType()))
                    .build()
                val response = NetworkConfig.httpClient.newCall(request).execute()
                response.isSuccessful.also {
                    if (!it) Log.w("CartVM", "后端同步：修改数量失败 ${response.code}")
                }
            } catch (e: Exception) {
                Log.e("CartVM", "后端同步：修改数量异常 ${e.message}", e)
                false
            }
        }
    }

    /** 调用后端 API：清空购物车 */
    private suspend fun syncClearBackend(): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val userId = getUserId()
                val baseUrl = NetworkConfig.BASE_URL
                val body = JSONObject().apply {
                    put("session_id", sessionId)
                    put("user_id", userId)
                }
                val request = Request.Builder()
                    .url("$baseUrl/api/v1/cart/clear")
                    .post(body.toString().toRequestBody("application/json".toMediaType()))
                    .build()
                val response = NetworkConfig.httpClient.newCall(request).execute()
                response.isSuccessful.also {
                    if (!it) Log.w("CartVM", "后端同步：清空失败 ${response.code}")
                }
            } catch (e: Exception) {
                Log.e("CartVM", "后端同步：清空异常 ${e.message}", e)
                false
            }
        }
    }

    /** 从后端拉取最新购物车数据并刷新本地 SQLite */
    private suspend fun syncFromBackend(): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                repository.syncCartFromBackend(sessionId)
                true
            } catch (e: Exception) {
                Log.e("CartVM", "从后端同步购物车失败", e)
                false
            }
        }
    }

    /** 加载购物车数据（先从后端同步 → 再从本地加载） */
    fun loadCart() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            try {
                // 先从后端拉取最新数据刷新本地数据库
                withContext(Dispatchers.IO) {
                    repository.syncCartFromBackend(sessionId)
                }
                // 再从本地加载显示
                val items = withContext(Dispatchers.IO) {
                    repository.getCartItemsForCurrentUser(sessionId)
                }
                val selectedIds = items.filter { it.isSelected }.map { it.product.productId }.toSet()
                val (total, selectedTotal) = calcTotals(items, selectedIds)
                _uiState.update {
                    it.copy(
                        items = items,
                        totalPrice = total,
                        selectedProductIds = selectedIds,
                        selectedTotalPrice = selectedTotal,
                        isLoading = false,
                    )
                }
            } catch (e: Exception) {
                // 后端同步失败时，回退到仅从本地加载
                try {
                    val items = withContext(Dispatchers.IO) {
                        repository.getCartItemsForCurrentUser(sessionId)
                    }
                    val selectedIds = items.filter { it.isSelected }.map { it.product.productId }.toSet()
                    val (total, selectedTotal) = calcTotals(items, selectedIds)
                    _uiState.update {
                        it.copy(
                            items = items,
                            totalPrice = total,
                            selectedProductIds = selectedIds,
                            selectedTotalPrice = selectedTotal,
                            isLoading = false,
                        )
                    }
                } catch (e2: Exception) {
                    _uiState.update { it.copy(isLoading = false, error = e2.message) }
                }
            }
        }
    }

    /** 切换管理模式 */
    fun toggleManageMode() {
        val currentState = _uiState.value
        if (currentState.isManageMode) {
            // 退出管理模式：从数据库重新加载选中状态
            viewModelScope.launch {
                try {
                    val items = withContext(Dispatchers.IO) {
                        repository.getCartItemsForCurrentUser(sessionId)
                    }
                    val selectedIds = items.filter { it.isSelected }.map { it.product.productId }.toSet()
                    val (_, selectedTotal) = calcTotals(items, selectedIds)
                    _uiState.update {
                        it.copy(
                            isManageMode = false,
                            items = items,
                            selectedProductIds = selectedIds,
                            selectedTotalPrice = selectedTotal,
                        )
                    }
                } catch (_: Exception) {
                    _uiState.update { it.copy(isManageMode = false) }
                }
            }
        } else {
            // 进入管理模式：清空选中缓存，不从数据库读取
            _uiState.update {
                it.copy(isManageMode = true, selectedProductIds = emptySet(), selectedTotalPrice = 0.0)
            }
        }
    }

    /** 切换单个商品选中状态 */
    fun toggleItemSelection(productId: String) {
        _uiState.update { state ->
            val newSelected = state.selectedProductIds.toMutableSet()
            if (newSelected.contains(productId)) {
                newSelected.remove(productId)
            } else {
                newSelected.add(productId)
            }
            val selectedTotal = calcTotals(state.items, newSelected.toSet()).second
            state.copy(
                selectedProductIds = newSelected,
                selectedTotalPrice = selectedTotal,
            )
        }
    }

    /** 全选 / 取消全选所有商品 */
    fun toggleSelectAll() {
        _uiState.update { state ->
            val allIds = state.items.map { it.product.productId }.toSet()
            val allSelected = allIds.all { state.selectedProductIds.contains(it) }
            val newSelected = if (allSelected) {
                emptySet<String>()
            } else {
                allIds
            }
            val (_, selectedTotal) = calcTotals(state.items, newSelected)
            state.copy(
                selectedProductIds = newSelected,
                selectedTotalPrice = selectedTotal,
            )
        }
    }

    /** 全选 / 取消全选指定商家的商品 */
    fun toggleBrandSelection(brand: String) {
        _uiState.update { state ->
            val brandProductIds = state.items
                .filter { it.product.brand == brand }
                .map { it.product.productId }
                .toSet()
            val allBrandSelected = brandProductIds.all { state.selectedProductIds.contains(it) }
            val newSelected = state.selectedProductIds.toMutableSet()
            if (allBrandSelected) {
                newSelected.removeAll(brandProductIds)
            } else {
                newSelected.addAll(brandProductIds)
            }
            val (total, selectedTotal) = calcTotals(updated, newSelected.toSet())
            state.copy(
                selectedProductIds = newSelected,
                selectedTotalPrice = selectedTotal,
            )
        }
    }

    /** 检查指定商家商品是否全部选中 */
    fun isBrandFullySelected(brand: String): Boolean {
        val state = _uiState.value
        val brandProductIds = state.items
            .filter { it.product.brand == brand }
            .map { it.product.productId }
            .toSet()
        if (brandProductIds.isEmpty()) return false
        return brandProductIds.all { state.selectedProductIds.contains(it) }
    }

    /** 增加商品数量（先调后端，成功后写本地） */
    fun increaseQuantity(productId: String) {
        _uiState.update { state ->
            val updated = state.items.map { item ->
                if (item.product.productId == productId && item.quantity < MAX_QUANTITY) {
                    item.copy(quantity = item.quantity + 1)
                } else item
            }
            val (total, selectedTotal) = calcTotals(updated, state.selectedProductIds)
            state.copy(items = updated, totalPrice = total, selectedTotalPrice = selectedTotal)
        }
        viewModelScope.launch {
            val item = _uiState.value.items.find { it.product.productId == productId } ?: return@launch
            // 先调后端
            if (!syncUpdateQuantityToBackend(productId, item.quantity)) {
                loadCart()
                return@launch
            }
            withContext(Dispatchers.IO) {
                repository.updateCartItemQuantity(productId, item.quantity)
            }
        }
    }

    /** 减少商品数量，减至 0 则删除（先调后端，成功后写本地） */
    fun decreaseQuantity(productId: String) {
        val item = _uiState.value.items.find { it.product.productId == productId } ?: return
        if (item.quantity <= 1) {
            removeFromCart(productId)
            return
        }
        _uiState.update { state ->
            val updated = state.items.map { item ->
                if (item.product.productId == productId) {
                    item.copy(quantity = item.quantity - 1)
                } else item
            }
            val (total, selectedTotal) = calcTotals(updated, state.selectedProductIds)
            state.copy(items = updated, totalPrice = total, selectedTotalPrice = selectedTotal)
        }
        viewModelScope.launch {
            val updatedItem = _uiState.value.items.find { it.product.productId == productId } ?: return@launch
            if (!syncUpdateQuantityToBackend(productId, updatedItem.quantity)) {
                loadCart()
                return@launch
            }
            withContext(Dispatchers.IO) {
                repository.updateCartItemQuantity(productId, updatedItem.quantity)
            }
        }
    }

    /** 更新商品数量，用户手动输入（先调后端，成功后写本地） */
    fun updateQuantity(productId: String, quantity: Int) {
        val clamped = quantity.coerceIn(1, MAX_QUANTITY)
        _uiState.update { state ->
            val updated = state.items.map { item ->
                if (item.product.productId == productId) {
                    item.copy(quantity = clamped)
                } else item
            }
            val (total, selectedTotal) = calcTotals(updated, state.selectedProductIds)
            state.copy(items = updated, totalPrice = total, selectedTotalPrice = selectedTotal)
        }
        viewModelScope.launch {
            if (!syncUpdateQuantityToBackend(productId, clamped)) {
                loadCart()
                return@launch
            }
            withContext(Dispatchers.IO) {
                repository.updateCartItemQuantity(productId, clamped)
            }
        }
    }

    /** 从购物车移除单件商品（先调后端 API，成功后删本地） */
    fun removeFromCart(productId: String) {
        // 乐观更新 UI
        _uiState.update { state ->
            val updated = state.items.filter { it.product.productId != productId }
            val newSelected = state.selectedProductIds - productId
            val (total, selectedTotal) = calcTotals(updated, newSelected)
            state.copy(
                items = updated,
                totalPrice = total,
                selectedProductIds = newSelected,
                selectedTotalPrice = selectedTotal,
            )
        }
        viewModelScope.launch {
            // 先调后端删除
            val backendOk = syncRemoveFromBackend(productId)
            if (!backendOk) {
                // 后端失败，从本地重新加载恢复状态
                loadCart()
                return@launch
            }
            // 后端成功，删除本地
            withContext(Dispatchers.IO) {
                repository.removeCartItem(productId)
            }
        }
    }

    /** 执行删除选中商品（先调后端，成功后删本地） */
    fun performDeleteSelected() {
        val idsToDelete = _uiState.value.selectedProductIds.toList()
        if (idsToDelete.isEmpty()) return
        // 乐观更新 UI
        _uiState.update { state ->
            val updated = state.items.filter { it.product.productId !in idsToDelete }
            val total = updated.sumOf { it.product.price * it.quantity }
            state.copy(
                items = updated,
                totalPrice = total,
                selectedProductIds = emptySet(),
                selectedTotalPrice = 0.0,
            )
        }
        viewModelScope.launch {
            // 逐个调后端删除
            var allOk = true
            for (pid in idsToDelete) {
                if (!syncRemoveFromBackend(pid)) { allOk = false }
            }
            if (!allOk) {
                loadCart()
                return@launch
            }
            withContext(Dispatchers.IO) {
                repository.deleteCartItems(idsToDelete)
            }
        }
    }

    /** 添加商品到购物车（先调后端 API，成功后写本地） */
    fun addToCart(product: Product) {
        viewModelScope.launch {
            val existing = _uiState.value.items.find { it.product.productId == product.productId }
            if (existing != null) {
                updateQuantity(product.productId, existing.quantity + 1)
            } else {
                // 1. 先调后端 API 入库
                val backendOk = syncAddToBackend(product, 1)
                if (!backendOk) {
                    _uiState.update { it.copy(error = "加购失败：后端同步异常") }
                    return@launch
                }
                // 2. 后端成功后写本地 SQLite
                val newItem = CartItem(product, 1, isSelected = true)
                _uiState.update { state ->
                    val updated = state.items + newItem
                    val newSelected = state.selectedProductIds + product.productId
                    val (total, selectedTotal) = calcTotals(updated, newSelected)
                    state.copy(
                        items = updated,
                        totalPrice = total,
                        selectedProductIds = newSelected,
                        selectedTotalPrice = selectedTotal,
                    )
                }
                withContext(Dispatchers.IO) {
                    repository.saveCartItemForCurrentUser(product, sessionId, 1)
                }
            }
        }
    }

    /** 清空购物车（先调后端，成功后清本地） */
    fun clearCart() {
        _uiState.update { it.copy(items = emptyList(), totalPrice = 0.0, selectedProductIds = emptySet(), selectedTotalPrice = 0.0) }
        viewModelScope.launch {
            if (!syncClearBackend()) {
                loadCart()
                return@launch
            }
            withContext(Dispatchers.IO) {
                repository.clearCart(sessionId)
            }
        }
    }

    /** 下单（先调后端清除已下单商品，成功后删本地） */
    fun placeOrder() {
        if (_uiState.value.items.isEmpty()) return
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            try {
                // 使用选中的商品下单，若未选中任何商品则用全部商品
                val selectedItems = _uiState.value.items.filter {
                    _uiState.value.selectedProductIds.contains(it.product.productId)
                }.ifEmpty { _uiState.value.items }
                val orderedIds = selectedItems.map { it.product.productId }
                val userId = getUserId()
                val address = withContext(Dispatchers.IO) {
                    repository.getShippingAddresses().firstOrNull()
                }?.let { addr ->
                    listOf(addr.recipientName, addr.phone, addr.addressDetail)
                        .filter { it.isNotBlank() }
                        .joinToString(" ")
                }.takeUnless { it.isNullOrBlank() } ?: "默认地址"

                val orderJson = withContext(Dispatchers.IO) {
                    val baseUrl = NetworkConfig.BASE_URL
                    val body = JSONObject().apply {
                        put("session_id", sessionId)
                        put("user_id", userId)
                        put("address", address)
                        put("product_ids", org.json.JSONArray(orderedIds))
                    }
                    val request = Request.Builder()
                        .url("$baseUrl/api/v1/orders")
                        .post(body.toString().toRequestBody("application/json".toMediaType()))
                        .build()
                    NetworkConfig.httpClient.newCall(request).execute().use { response ->
                        if (!response.isSuccessful) {
                            throw IllegalStateException("后端返回 ${response.code}")
                        }
                        JSONObject(response.body?.string().orEmpty())
                    }
                }
                val orderNo = orderJson.optJSONObject("data")?.optString("order_no", "ORD${System.currentTimeMillis()}")
                    ?: "ORD${System.currentTimeMillis()}"
                val total = orderJson.optJSONObject("data")?.optDouble(
                    "total",
                    selectedItems.sumOf { it.product.price * it.quantity }
                ) ?: selectedItems.sumOf { it.product.price * it.quantity }

                // 后端成功后，删除本地数据库中的已下单商品
                withContext(Dispatchers.IO) {
                    repository.deleteCartItems(orderedIds)
                }

                // 仅移除已下单的商品，保留未选中的商品
                val remainingItems = _uiState.value.items.filter {
                    it.product.productId !in orderedIds
                }
                val remainingTotal = remainingItems.sumOf { it.product.price * it.quantity }
                val remainingSelectedIds = _uiState.value.selectedProductIds - orderedIds.toSet()
                val remainingSelectedTotal = remainingItems
                    .filter { remainingSelectedIds.contains(it.product.productId) }
                    .sumOf { it.product.price * it.quantity }
                _uiState.update {
                    it.copy(
                        items = remainingItems,
                        totalPrice = remainingTotal,
                        selectedProductIds = remainingSelectedIds,
                        selectedTotalPrice = remainingSelectedTotal,
                        isLoading = false,
                        orderResult = "下单成功！\n订单号：$orderNo\n收货地址：$address\n实付：¥${"%.2f".format(total)}"
                    )
                }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoading = false, error = "网络错误：${e.message}") }
            }
        }
    }

    /** 关闭下单成功弹窗 */
    fun dismissOrderResult() {
        _uiState.update { it.copy(orderResult = null) }
    }

    // ═══════════════════════════════════════════════════════
    // 快速清理面板
    // ═══════════════════════════════════════════════════════

    /** 打开快速清理面板 */
    fun openQuickClean() {
        _uiState.update { it.copy(showQuickClean = true, quickCleanSelectedIds = emptySet()) }
    }

    /** 关闭快速清理面板 */
    fun closeQuickClean() {
        _uiState.update { it.copy(showQuickClean = false, quickCleanSelectedIds = emptySet()) }
    }

    /** 切换快速清理中商品的选中状态 */
    fun toggleQuickCleanSelection(productId: String) {
        _uiState.update { state ->
            val newSet = state.quickCleanSelectedIds.toMutableSet()
            if (newSet.contains(productId)) {
                newSet.remove(productId)
            } else {
                newSet.add(productId)
            }
            state.copy(quickCleanSelectedIds = newSet)
        }
    }

    /** 快速清理中全选/取消全选 */
    fun toggleQuickCleanSelectAll() {
        _uiState.update { state ->
            val allIds = state.items.map { it.product.productId }.toSet()
            val allSelected = allIds.all { state.quickCleanSelectedIds.contains(it) }
            state.copy(
                quickCleanSelectedIds = if (allSelected) emptySet() else allIds
            )
        }
    }

    /** 快速清理 — 删除选中的商品（先调后端，成功后删本地） */
    fun performQuickCleanDelete() {
        val idsToDelete = _uiState.value.quickCleanSelectedIds.toList()
        if (idsToDelete.isEmpty()) return
        // 乐观更新 UI
        _uiState.update { state ->
            val updated = state.items.filter { it.product.productId !in idsToDelete }
            val newSelected = state.selectedProductIds - idsToDelete.toSet()
            val (total, selectedTotal) = calcTotals(updated, newSelected)
            state.copy(
                items = updated,
                totalPrice = total,
                selectedProductIds = newSelected,
                selectedTotalPrice = selectedTotal,
                showQuickClean = false,
                quickCleanSelectedIds = emptySet(),
            )
        }
        viewModelScope.launch {
            var allOk = true
            for (pid in idsToDelete) {
                if (!syncRemoveFromBackend(pid)) { allOk = false }
            }
            if (!allOk) {
                loadCart()
                return@launch
            }
            withContext(Dispatchers.IO) {
                repository.deleteCartItems(idsToDelete)
            }
        }
    }

    companion object {
        /** 商品数量最大值 */
        const val MAX_QUANTITY = 1000
    }
}
