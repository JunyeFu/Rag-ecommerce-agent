package com.shopping.agent.data.local

import android.content.ContentValues
import android.util.Log
import com.shopping.agent.core.network.NetworkConfig
import com.shopping.agent.data.model.CartItem
import com.shopping.agent.data.model.Product
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

// ═══════════════════════════════════════════════════════
// 购物车 (本地缓存)
// ═══════════════════════════════════════════════════════

suspend fun UserRepository.saveCartItem(product: Product, sessionId: String, quantity: Int = 1) = withContext(Dispatchers.IO) {
    val cv = ContentValues().apply {
        put("product_id", product.productId)
        put("session_id", sessionId)
        put("title", product.title)
        put("price", product.price)
        put("brand", product.brand ?: "")
        put("category", product.category)
        put("image_url", product.imageUrl ?: "")
        put("rating", product.rating.toDouble())
        put("quantity", quantity)
        put("is_selected", 1)
        put("added_at", System.currentTimeMillis())
    }
    db.writableDatabase.insertWithOnConflict(
        LocalDatabase.TABLE_CART, null, cv,
        android.database.sqlite.SQLiteDatabase.CONFLICT_REPLACE
    )
}

suspend fun UserRepository.getCartItems(sessionId: String): List<CartItem> = withContext(Dispatchers.IO) {
    val cursor = db.readableDatabase.query(
        LocalDatabase.TABLE_CART, null,
        "session_id=?", arrayOf(sessionId),
        null, null, "added_at DESC"
    )
    val list = mutableListOf<CartItem>()
    while (cursor.moveToNext()) {
        val product = Product(
            productId = cursor.getString(cursor.getColumnIndexOrThrow("product_id")),
            title = cursor.getString(cursor.getColumnIndexOrThrow("title")),
            price = cursor.getDouble(cursor.getColumnIndexOrThrow("price")),
            brand = cursor.getString(cursor.getColumnIndexOrThrow("brand")).takeIf { it.isNotEmpty() },
            category = cursor.getString(cursor.getColumnIndexOrThrow("category")),
            imageUrl = NetworkConfig.resolveImageUrl(cursor.getString(cursor.getColumnIndexOrThrow("image_url")).takeIf { it.isNotEmpty() }),
            rating = cursor.getDouble(cursor.getColumnIndexOrThrow("rating")).toFloat(),
        )
        // 安全读取 is_selected 列，防止 v8 迁移未运行时闪退
        val isSelectedCol = cursor.getColumnIndex("is_selected")
        val isSelected = isSelectedCol >= 0 && cursor.getInt(isSelectedCol) == 1
        list.add(CartItem(
            product,
            cursor.getInt(cursor.getColumnIndexOrThrow("quantity")),
            isSelected,
        ))
    }
    cursor.close()
    list
}

suspend fun UserRepository.removeCartItem(productId: String) = withContext(Dispatchers.IO) {
    db.writableDatabase.delete(LocalDatabase.TABLE_CART, "product_id=?", arrayOf(productId))
}

suspend fun UserRepository.clearCart(sessionId: String) = withContext(Dispatchers.IO) {
    db.writableDatabase.delete(LocalDatabase.TABLE_CART, "session_id=?", arrayOf(sessionId))
}

// ═══════════════════════════════════════════════════════
// 购物车 (扩展：支持 user_id 关联)
// ═══════════════════════════════════════════════════════

/**
 * 获取当前用户的购物车商品（优先按 user_id 查询，兼容旧 session_id 模式）。
 * 若 user_id 未关联到用户画像或用户为游客状态，回退到 session_id 查询。
 */
suspend fun UserRepository.getCartItemsForCurrentUser(sessionId: String): List<CartItem> = withContext(Dispatchers.IO) {
    val userId = getUserId()
    if (userId.isNotEmpty()) {
        // 尝试按 user_id 查询
        val cursor = db.readableDatabase.query(
            LocalDatabase.TABLE_CART, null,
            "user_id=?", arrayOf(userId),
            null, null, "added_at DESC"
        )
        if (cursor.count > 0) {
            val list = mutableListOf<CartItem>()
            while (cursor.moveToNext()) {
                list.add(buildCartItemFromCursor(cursor))
            }
            cursor.close()
            return@withContext list
        }
        cursor.close()
    }
    // 回退到 session_id
    getCartItems(sessionId)
}

/**
 * 为当前用户保存购物车商品（同时写入 user_id）。
 */
suspend fun UserRepository.saveCartItemForCurrentUser(product: Product, sessionId: String, quantity: Int = 1) = withContext(Dispatchers.IO) {
    val userId = getUserId()
    val cv = ContentValues().apply {
        put("product_id", product.productId)
        put("session_id", sessionId)
        put("user_id", userId)
        put("title", product.title)
        put("price", product.price)
        put("brand", product.brand ?: "")
        put("category", product.category)
        put("image_url", product.imageUrl ?: "")
        put("rating", product.rating.toDouble())
        put("quantity", quantity)
        put("is_selected", 1)
        put("added_at", System.currentTimeMillis())
    }
    db.writableDatabase.insertWithOnConflict(
        LocalDatabase.TABLE_CART, null, cv,
        android.database.sqlite.SQLiteDatabase.CONFLICT_REPLACE
    )
}

/** 从 Cursor 构建 CartItem */
private fun buildCartItemFromCursor(cursor: android.database.Cursor): CartItem {
    val product = Product(
        productId = cursor.getString(cursor.getColumnIndexOrThrow("product_id")),
        title = cursor.getString(cursor.getColumnIndexOrThrow("title")),
        price = cursor.getDouble(cursor.getColumnIndexOrThrow("price")),
        brand = cursor.getString(cursor.getColumnIndexOrThrow("brand")).takeIf { it.isNotEmpty() },
        category = cursor.getString(cursor.getColumnIndexOrThrow("category")),
        imageUrl = NetworkConfig.resolveImageUrl(cursor.getString(cursor.getColumnIndexOrThrow("image_url")).takeIf { it.isNotEmpty() }),
        rating = cursor.getDouble(cursor.getColumnIndexOrThrow("rating")).toFloat(),
    )
    // 安全读取 is_selected 列，防止 v8 迁移未运行时闪退
    val isSelectedCol = cursor.getColumnIndex("is_selected")
    val isSelected = isSelectedCol >= 0 && cursor.getInt(isSelectedCol) == 1
    return CartItem(
        product,
        cursor.getInt(cursor.getColumnIndexOrThrow("quantity")),
        isSelected,
    )
}

/** 更新购物车商品的选中状态 */
suspend fun UserRepository.updateCartItemSelection(productId: String, isSelected: Boolean) = withContext(Dispatchers.IO) {
    val cv = ContentValues().apply {
        put("is_selected", if (isSelected) 1 else 0)
    }
    db.writableDatabase.update(LocalDatabase.TABLE_CART, cv, "product_id=?", arrayOf(productId))
}

/** 批量更新购物车商品的选中状态 */
suspend fun UserRepository.updateCartItemsSelection(productIds: List<String>, isSelected: Boolean) = withContext(Dispatchers.IO) {
    val cv = ContentValues().apply {
        put("is_selected", if (isSelected) 1 else 0)
    }
    val writableDb = db.writableDatabase
    productIds.forEach { productId ->
        writableDb.update(LocalDatabase.TABLE_CART, cv, "product_id=?", arrayOf(productId))
    }
}

/** 更新购物车商品数量 */
suspend fun UserRepository.updateCartItemQuantity(productId: String, quantity: Int) = withContext(Dispatchers.IO) {
    val cv = ContentValues().apply {
        put("quantity", quantity)
    }
    db.writableDatabase.update(LocalDatabase.TABLE_CART, cv, "product_id=?", arrayOf(productId))
}

/** 删除购物车中指定商品 */
suspend fun UserRepository.deleteCartItems(productIds: List<String>) = withContext(Dispatchers.IO) {
    val writableDb = db.writableDatabase
    productIds.forEach { productId ->
        writableDb.delete(LocalDatabase.TABLE_CART, "product_id=?", arrayOf(productId))
    }
}

/** 获取购物车商品总数 */
suspend fun UserRepository.getCartItemCount(): Int = withContext(Dispatchers.IO) {
    val userId = getUserId()
    if (userId.isEmpty()) return@withContext 0
    val cursor = db.readableDatabase.rawQuery(
        "SELECT COUNT(*) FROM ${LocalDatabase.TABLE_CART} WHERE user_id=?",
        arrayOf(userId)
    )
    val count = if (cursor.moveToFirst()) cursor.getInt(0) else 0
    cursor.close()
    count
}

/**
 * 从后端同步购物车数据到本地 SQLite。
 *
 * 触发时机：App 启动 & 登录成功。
 * 前置条件：当前用户 user_id 必须在本地 user_profile 表中存在（否则跳过同步）。
 *
 * @param sessionId 本地持久化的 session_id，用于后端查询购物车
 */
suspend fun UserRepository.syncCartFromBackend(sessionId: String) = withContext(Dispatchers.IO) {
    val userId = getUserId()
    val client = NetworkConfig.httpClient
    val baseUrl = NetworkConfig.BASE_URL

    try {
        val cartUrl = if (userId.isNotEmpty()) {
            "$baseUrl/api/v1/cart?session_id=$sessionId&user_id=$userId"
        } else {
            "$baseUrl/api/v1/cart?session_id=$sessionId"
        }
        val request = okhttp3.Request.Builder()
            .url(cartUrl)
            .get()
            .build()
        val response = client.newCall(request).execute()
        if (!response.isSuccessful) {
            Log.w("UserRepository", "syncCartFromBackend: 后端返回 ${response.code}")
            return@withContext
        }

        val body = response.body?.string() ?: return@withContext
        val json = org.json.JSONObject(body)
        val data = json.optJSONObject("data") ?: org.json.JSONObject()
        val itemsArray = data.optJSONArray("items") ?: org.json.JSONArray()

        val writableDb = db.writableDatabase
        if (userId.isNotEmpty()) {
            writableDb.delete(LocalDatabase.TABLE_CART, "user_id=?", arrayOf(userId))
        } else {
            writableDb.delete(LocalDatabase.TABLE_CART, "session_id=?", arrayOf(sessionId))
        }
        var syncedCount = 0
        for (i in 0 until itemsArray.length()) {
            val item = itemsArray.getJSONObject(i)
            val productId = item.optString("product_id", "")
            val title = item.optString("title", "")
            val price = item.optDouble("price", 0.0)
            val quantity = item.optInt("quantity", 1)
            val imageUrl = item.optString("image_url", "")
                .takeIf { it.isNotEmpty() && it != "null" }
            val brand = item.optString("brand", "")
                .takeIf { it.isNotEmpty() && it != "null" }
            val category = item.optString("category", "")

            val cv = ContentValues().apply {
                put("product_id", productId)
                put("session_id", sessionId)
                put("user_id", userId)
                put("title", title)
                put("price", price)
                put("brand", brand ?: "")
                put("category", category)
                put("image_url", imageUrl ?: "")
                put("quantity", quantity)
                put("is_selected", 1)
                put("added_at", System.currentTimeMillis())
            }
            writableDb.insertWithOnConflict(
                LocalDatabase.TABLE_CART, null, cv,
                android.database.sqlite.SQLiteDatabase.CONFLICT_REPLACE
            )
            syncedCount++
        }
        Log.i("UserRepository", "syncCartFromBackend: 同步完成，共 $syncedCount 件商品")
    } catch (e: Exception) {
        Log.e("UserRepository", "syncCartFromBackend: 同步失败", e)
    }
}
