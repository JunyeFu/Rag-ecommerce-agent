package com.shopping.agent.data.local

import android.content.ContentValues
import android.util.Log
import com.shopping.agent.core.network.NetworkConfig
import com.shopping.agent.data.local.UserRepository.FootprintRecord
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody

// ═══════════════════════════════════════════════════════
// 商品足迹记录（浏览历史）
// ═══════════════════════════════════════════════════════

/**
 * 获取当天0点的时间戳（仅保留年月日）。
 */
private fun getTodayTimestamp(): Long {
    val cal = java.util.Calendar.getInstance()
    cal.set(java.util.Calendar.HOUR_OF_DAY, 0)
    cal.set(java.util.Calendar.MINUTE, 0)
    cal.set(java.util.Calendar.SECOND, 0)
    cal.set(java.util.Calendar.MILLISECOND, 0)
    return cal.timeInMillis
}

/**
 * 记录商品浏览足迹。
 *
 * 逻辑：
 * - 库中不存在该商品的足迹 -> 新增记录
 * - 库中已存在该商品的足迹 -> 更新浏览日期
 *
 * @param productId 商品 ID
 */
suspend fun UserRepository.recordFootprint(productId: String) = withContext(Dispatchers.IO) {
    val userId = getUserId()
    if (userId.isEmpty()) return@withContext
    val today = getTodayTimestamp()
    val writableDb = db.writableDatabase

    // 检查是否已存在该商品足迹
    val cursor = writableDb.query(
        LocalDatabase.TABLE_FOOTPRINTS,
        arrayOf("user_id"),
        "user_id=? AND product_id=?",
        arrayOf(userId, productId),
        null, null, null, "1"
    )
    val exists = cursor.moveToFirst()
    cursor.close()

    if (exists) {
        // 已存在 -> 更新浏览日期
        val cv = ContentValues().apply {
            put("browse_date", today)
        }
        writableDb.update(
            LocalDatabase.TABLE_FOOTPRINTS, cv,
            "user_id=? AND product_id=?",
            arrayOf(userId, productId)
        )
    } else {
        // 不存在 -> 新增足迹记录
        val cv = ContentValues().apply {
            put("user_id", userId)
            put("product_id", productId)
            put("browse_date", today)
            put("created_at", System.currentTimeMillis())
        }
        writableDb.insertWithOnConflict(
            LocalDatabase.TABLE_FOOTPRINTS, null, cv,
            android.database.sqlite.SQLiteDatabase.CONFLICT_REPLACE
        )
    }
}

/**
 * 获取当前用户的足迹记录列表，按浏览日期降序排列。
 *
 * @param startDate 筛选起始日期（毫秒时间戳，0点），0 表示不限
 * @param endDate 筛选结束日期（毫秒时间戳，次日0点前），0 表示不限
 * @param limit 最大返回条数
 */
suspend fun UserRepository.getFootprints(
    startDate: Long = 0,
    endDate: Long = 0,
    limit: Int = 0,
): List<FootprintRecord> = withContext(Dispatchers.IO) {
    val userId = getUserId()
    if (userId.isEmpty()) return@withContext emptyList()

    val whereClause = buildString {
        append("user_id=?")
        if (startDate > 0) append(" AND browse_date>=?")
        if (endDate > 0) append(" AND browse_date<=?")
    }
    val whereArgs = buildList {
        add(userId)
        if (startDate > 0) add(startDate.toString())
        if (endDate > 0) add(endDate.toString())
    }.toTypedArray()

    val limitStr = if (limit > 0) limit.toString() else null
    val cursor = db.readableDatabase.query(
        LocalDatabase.TABLE_FOOTPRINTS, null,
        whereClause, whereArgs,
        null, null,
        "browse_date DESC, created_at DESC",
        limitStr
    )
    val list = mutableListOf<FootprintRecord>()
    while (cursor.moveToNext()) {
        list.add(FootprintRecord(
            userId = cursor.getString(cursor.getColumnIndexOrThrow("user_id")) ?: "",
            productId = cursor.getString(cursor.getColumnIndexOrThrow("product_id")) ?: "",
            browseDate = cursor.getLong(cursor.getColumnIndexOrThrow("browse_date")),
            createdAt = cursor.getLong(cursor.getColumnIndexOrThrow("created_at")),
        ))
    }
    cursor.close()
    list
}

/**
 * 获取当前用户的足迹总数（可按日期范围筛选）。
 */
suspend fun UserRepository.getFootprintCount(
    startDate: Long = 0,
    endDate: Long = 0,
): Int = withContext(Dispatchers.IO) {
    val userId = getUserId()
    if (userId.isEmpty()) return@withContext 0

    val whereClause = buildString {
        append("user_id=?")
        if (startDate > 0) append(" AND browse_date>=?")
        if (endDate > 0) append(" AND browse_date<=?")
    }
    val whereArgs = buildList {
        add(userId)
        if (startDate > 0) add(startDate.toString())
        if (endDate > 0) add(endDate.toString())
    }.toTypedArray()

    val cursor = db.readableDatabase.rawQuery(
        "SELECT COUNT(*) FROM ${LocalDatabase.TABLE_FOOTPRINTS} WHERE $whereClause",
        whereArgs
    )
    val count = if (cursor.moveToFirst()) cursor.getInt(0) else 0
    cursor.close()
    count
}

/**
 * 同步足迹记录到后端 PostgreSQL。
 *
 * @param productId 商品 ID
 */
suspend fun UserRepository.syncFootprintToBackend(productId: String) = withContext(Dispatchers.IO) {
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
            .url("$baseUrl/api/v1/footprints/record")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()
        val response = client.newCall(request).execute()
        if (!response.isSuccessful) {
            Log.w("UserRepository", "syncFootprintToBackend: 后端返回 ${response.code}")
        }
    } catch (e: Exception) {
        Log.e("UserRepository", "syncFootprintToBackend: 同步失败", e)
    }
}
