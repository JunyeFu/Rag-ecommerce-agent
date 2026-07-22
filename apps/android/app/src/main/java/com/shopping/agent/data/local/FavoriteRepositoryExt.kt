package com.shopping.agent.data.local

import android.content.ContentValues
import android.util.Log
import com.shopping.agent.core.network.NetworkConfig
import com.shopping.agent.data.local.UserRepository.FavoriteRecord
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody

// ═══════════════════════════════════════════════════════
// 商品收藏记录
// ═══════════════════════════════════════════════════════

/**
 * 检查用户是否已收藏指定商品。
 * @param productId 商品 ID
 * @return true 表示已收藏
 */
suspend fun UserRepository.isFavorited(productId: String): Boolean = withContext(Dispatchers.IO) {
    val userId = getUserId()
    if (userId.isEmpty()) return@withContext false
    val cursor = db.readableDatabase.query(
        LocalDatabase.TABLE_FAVORITES,
        arrayOf("user_id"),
        "user_id=? AND product_id=?",
        arrayOf(userId, productId),
        null, null, null, "1"
    )
    val exists = cursor.moveToFirst()
    cursor.close()
    exists
}

/**
 * 切换收藏状态：已收藏则取消，未收藏则添加。
 * @param productId 商品 ID（mock 格式，如 "p_clothes_021"，保证与 mockProducts 匹配）
 * @return 操作后的收藏状态（true=已收藏, false=未收藏）
 */
suspend fun UserRepository.toggleFavorite(productId: String): Boolean = withContext(Dispatchers.IO) {
    val userId = getUserId()
    if (userId.isEmpty()) return@withContext false
    val writableDb = db.writableDatabase

    // 检查是否已收藏
    val cursor = writableDb.query(
        LocalDatabase.TABLE_FAVORITES,
        arrayOf("user_id"),
        "user_id=? AND product_id=?",
        arrayOf(userId, productId),
        null, null, null, "1"
    )
    val exists = cursor.moveToFirst()
    cursor.close()

    if (exists) {
        // 已收藏 -> 取消收藏
        writableDb.delete(
            LocalDatabase.TABLE_FAVORITES,
            "user_id=? AND product_id=?",
            arrayOf(userId, productId)
        )
        false
    } else {
        // 未收藏 -> 添加收藏
        val cv = ContentValues().apply {
            put("user_id", userId)
            put("product_id", productId)
            put("created_at", System.currentTimeMillis())
        }
        writableDb.insertWithOnConflict(
            LocalDatabase.TABLE_FAVORITES, null, cv,
            android.database.sqlite.SQLiteDatabase.CONFLICT_REPLACE
        )
        true
    }
}

/**
 * 获取当前用户的收藏记录列表，按收藏时间降序排列。
 * @param limit 最大返回条数，默认全量
 */
suspend fun UserRepository.getFavorites(limit: Int = 0): List<FavoriteRecord> = withContext(Dispatchers.IO) {
    val userId = getUserId()
    if (userId.isEmpty()) return@withContext emptyList()
    val limitStr = if (limit > 0) limit.toString() else null
    val cursor = db.readableDatabase.query(
        LocalDatabase.TABLE_FAVORITES, null,
        "user_id=?", arrayOf(userId),
        null, null,
        "created_at DESC",
        limitStr
    )
    val list = mutableListOf<FavoriteRecord>()
    while (cursor.moveToNext()) {
        list.add(FavoriteRecord(
            userId = cursor.getString(cursor.getColumnIndexOrThrow("user_id")) ?: "",
            productId = cursor.getString(cursor.getColumnIndexOrThrow("product_id")) ?: "",
            createdAt = cursor.getLong(cursor.getColumnIndexOrThrow("created_at")),
        ))
    }
    cursor.close()
    list
}

/**
 * 获取当前用户的收藏商品总数。
 */
suspend fun UserRepository.getFavoriteCount(): Int = withContext(Dispatchers.IO) {
    val userId = getUserId()
    if (userId.isEmpty()) return@withContext 0
    val cursor = db.readableDatabase.rawQuery(
        "SELECT COUNT(*) FROM ${LocalDatabase.TABLE_FAVORITES} WHERE user_id=?",
        arrayOf(userId)
    )
    val count = if (cursor.moveToFirst()) cursor.getInt(0) else 0
    cursor.close()
    count
}

/**
 * 批量移除收藏商品。
 * @param productIds 要移除的商品 ID 列表
 * @return 实际删除的条数
 */
suspend fun UserRepository.removeFavorites(productIds: List<String>): Int = withContext(Dispatchers.IO) {
    val userId = getUserId()
    if (userId.isEmpty() || productIds.isEmpty()) return@withContext 0
    var removedCount = 0
    val writableDb = db.writableDatabase
    productIds.forEach { pid ->
        removedCount += writableDb.delete(
            LocalDatabase.TABLE_FAVORITES,
            "user_id=? AND product_id=?",
            arrayOf(userId, pid)
        )
    }
    removedCount
}

// ═══════════════════════════════════════════════════════
// 收藏后端同步
// ═══════════════════════════════════════════════════════

/**
 * 同步收藏状态到后端 PostgreSQL。
 *
 * @param productId 商品 ID
 * @param isFavorited true=添加收藏, false=取消收藏
 */
suspend fun UserRepository.syncFavoriteToBackend(productId: String, isFavorited: Boolean) = withContext(Dispatchers.IO) {
    val userId = getUserId()
    if (userId.isEmpty()) return@withContext
    try {
        val baseUrl = NetworkConfig.BASE_URL
        val client = NetworkConfig.httpClient
        val body = org.json.JSONObject().apply {
            put("user_id", userId)
            put("product_id", productId)
        }
        val request = okhttp3.Request.Builder()
            .url("$baseUrl/api/v1/favorites/toggle")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()
        val response = client.newCall(request).execute()
        if (!response.isSuccessful) {
            Log.w("UserRepository", "syncFavoriteToBackend: 后端返回 ${response.code}")
        }
    } catch (e: Exception) {
        Log.e("UserRepository", "syncFavoriteToBackend: 同步失败", e)
    }
}

/**
 * 从后端同步收藏数据到本地 SQLite。
 */
suspend fun UserRepository.syncFavoritesFromBackend() = withContext(Dispatchers.IO) {
    val userId = getUserId()
    if (userId.isEmpty()) return@withContext
    try {
        val baseUrl = NetworkConfig.BASE_URL
        val client = NetworkConfig.httpClient
        val request = okhttp3.Request.Builder()
            .url("$baseUrl/api/v1/favorites?user_id=$userId&limit=100")
            .get()
            .build()
        val response = client.newCall(request).execute()
        if (!response.isSuccessful) {
            Log.w("UserRepository", "syncFavoritesFromBackend: 后端返回 ${response.code}")
            return@withContext
        }
        val body = response.body?.string() ?: return@withContext
        val json = org.json.JSONObject(body)
        val data = json.optJSONObject("data") ?: org.json.JSONObject()
        val itemsArray = data.optJSONArray("items") ?: org.json.JSONArray()

        val writableDb = db.writableDatabase
        for (i in 0 until itemsArray.length()) {
            val item = itemsArray.getJSONObject(i)
            val productId = item.optString("product_id", "")
            val cv = ContentValues().apply {
                put("user_id", userId)
                put("product_id", productId)
                put("created_at", System.currentTimeMillis())
            }
            writableDb.insertWithOnConflict(
                LocalDatabase.TABLE_FAVORITES, null, cv,
                android.database.sqlite.SQLiteDatabase.CONFLICT_IGNORE
            )
        }
        Log.i("UserRepository", "syncFavoritesFromBackend: 同步完成")
    } catch (e: Exception) {
        Log.e("UserRepository", "syncFavoritesFromBackend: 同步失败", e)
    }
}

/**
 * 批量同步收藏移除到后端。
 * @param productIds 要移除收藏的商品 ID 列表
 */
suspend fun UserRepository.syncFavoriteRemoveToBackend(productIds: List<String>) = withContext(Dispatchers.IO) {
    val userId = getUserId()
    if (userId.isEmpty() || productIds.isEmpty()) return@withContext
    try {
        val baseUrl = NetworkConfig.BASE_URL
        val client = NetworkConfig.httpClient
        val idsArray = org.json.JSONArray(productIds)
        val body = org.json.JSONObject().apply {
            put("user_id", userId)
            put("product_ids", idsArray)
        }
        val request = okhttp3.Request.Builder()
            .url("$baseUrl/api/v1/favorites/remove")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()
        val response = client.newCall(request).execute()
        if (!response.isSuccessful) {
            Log.w("UserRepository", "syncFavoriteRemoveToBackend: 后端返回 ${response.code}")
        }
    } catch (e: Exception) {
        Log.e("UserRepository", "syncFavoriteRemoveToBackend: 同步失败", e)
    }
}
