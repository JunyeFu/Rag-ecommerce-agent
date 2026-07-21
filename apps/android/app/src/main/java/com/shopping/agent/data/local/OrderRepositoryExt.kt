package com.shopping.agent.data.local

import android.content.ContentValues
import android.util.Log
import com.shopping.agent.core.network.NetworkConfig
import com.shopping.agent.data.local.UserRepository.OrderRecord
import com.shopping.agent.data.local.UserRepository.OrderStatus
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody

// ═══════════════════════════════════════════════════════
// 订单记录
// ═══════════════════════════════════════════════════════

/**
 * 新增一条订单记录。
 * @param orderBody 订单体 JSON（含商品快照、总价等）
 * @param status 订单状态，默认待付款
 * @param backendOrderNo 后端订单号，前后端订单关联字段
 * @return 新订单的 orderId，失败返回 -1
 */
suspend fun UserRepository.addOrderRecord(
    orderBody: String,
    status: String = OrderStatus.PENDING_PAYMENT,
    backendOrderNo: String = "",
): Long = withContext(Dispatchers.IO) {
    val userId = getUserId()
    if (userId.isEmpty()) return@withContext -1L
    val now = System.currentTimeMillis()
    val cv = ContentValues().apply {
        put("user_id", userId)
        put("backend_order_no", backendOrderNo)
        put("order_body", orderBody)
        put("created_at", now)
        put("updated_at", now)
        put("status", status)
    }
    db.writableDatabase.insert(LocalDatabase.TABLE_ORDER_RECORDS, null, cv)
}

/**
 * 获取当前用户所有订单记录，按时间倒序排列。
 * @param statusFilter 可选的状态过滤，为空则返回全部
 * @param limit 最大返回条数
 */
suspend fun UserRepository.getOrderRecords(statusFilter: String? = null, limit: Int = 50): List<OrderRecord> = withContext(Dispatchers.IO) {
    val userId = getUserId()
    if (userId.isEmpty()) return@withContext emptyList()
    val (where, args) = if (!statusFilter.isNullOrEmpty()) {
        "user_id=? AND status=?" to arrayOf(userId, statusFilter)
    } else {
        "user_id=?" to arrayOf(userId)
    }
    val cursor = db.readableDatabase.query(
        LocalDatabase.TABLE_ORDER_RECORDS, null,
        where, args, null, null, "created_at DESC", limit.toString()
    )
    val list = mutableListOf<OrderRecord>()
    while (cursor.moveToNext()) {
        list.add(OrderRecord(
            orderId = cursor.getLong(cursor.getColumnIndexOrThrow("order_id")),
            userId = cursor.getString(cursor.getColumnIndexOrThrow("user_id")) ?: "",
            backendOrderNo = cursor.getString(cursor.getColumnIndexOrThrow("backend_order_no")) ?: "",
            orderBody = cursor.getString(cursor.getColumnIndexOrThrow("order_body")) ?: "",
            createdAt = cursor.getLong(cursor.getColumnIndexOrThrow("created_at")),
            updatedAt = cursor.getLong(cursor.getColumnIndexOrThrow("updated_at")),
            status = cursor.getString(cursor.getColumnIndexOrThrow("status")) ?: OrderStatus.PENDING_PAYMENT,
        ))
    }
    cursor.close()
    list
}

/**
 * 更新订单状态，同时更新 updated_at 时间戳。
 */
suspend fun UserRepository.updateOrderStatus(orderId: Long, newStatus: String) = withContext(Dispatchers.IO) {
    val userId = getUserId()
    if (userId.isEmpty()) return@withContext
    val cv = ContentValues().apply {
        put("status", newStatus)
        put("updated_at", System.currentTimeMillis())
    }
    db.writableDatabase.update(
        LocalDatabase.TABLE_ORDER_RECORDS, cv,
        "order_id=? AND user_id=?", arrayOf(orderId.toString(), userId)
    )
}

/**
 * 按状态列表统计当前用户订单数量。
 * 用于个人页面展示各状态订单数量。
 * @param statuses 要统计的状态列表
 * @return Map<状态, 数量>
 */
suspend fun UserRepository.getOrderCountByStatus(statuses: List<String>): Map<String, Int> = withContext(Dispatchers.IO) {
    val userId = getUserId()
    if (userId.isEmpty() || statuses.isEmpty()) return@withContext emptyMap()
    val result = mutableMapOf<String, Int>()
    statuses.forEach { status ->
        val cursor = db.readableDatabase.rawQuery(
            "SELECT COUNT(*) FROM ${LocalDatabase.TABLE_ORDER_RECORDS} WHERE user_id=? AND status=?",
            arrayOf(userId, status)
        )
        result[status] = if (cursor.moveToFirst()) cursor.getInt(0) else 0
        cursor.close()
    }
    result
}

// ═══════════════════════════════════════════════════════
// 订单操作 - 后端同步
// ═══════════════════════════════════════════════════════

/**
 * 调用后端 API 取消订单。
 *
 * @param backendOrderNo 后端订单号（ORD 开头）
 */
suspend fun UserRepository.cancelOrderOnBackend(backendOrderNo: String) = withContext(Dispatchers.IO) {
    if (backendOrderNo.isEmpty()) return@withContext
    try {
        val baseUrl = NetworkConfig.BASE_URL
        val client = NetworkConfig.httpClient
        val request = okhttp3.Request.Builder()
            .url("$baseUrl/api/v1/orders/$backendOrderNo/cancel")
            .post("{}".toRequestBody("application/json".toMediaType()))
            .build()
        val response = client.newCall(request).execute()
        if (!response.isSuccessful) {
            Log.w("UserRepository", "cancelOrderOnBackend: 后端返回 ${response.code}")
        }
    } catch (e: Exception) {
        Log.e("UserRepository", "cancelOrderOnBackend: 同步失败", e)
    }
}

/**
 * 调用后端 API 更新订单状态。
 *
 * 用于"催发货"、"确认收货"等本地状态流转时与后端同步。
 * 后端无对应端点时静默失败（仅记日志），不影响本地状态。
 *
 * @param backendOrderNo 后端订单号（ORD 开头）
 * @param newStatus 目标状态值（见 [OrderStatus]）
 */
suspend fun UserRepository.updateOrderStatusOnBackend(backendOrderNo: String, newStatus: String) = withContext(Dispatchers.IO) {
    if (backendOrderNo.isEmpty()) return@withContext
    try {
        val baseUrl = NetworkConfig.BASE_URL
        val client = NetworkConfig.httpClient
        val body = org.json.JSONObject().apply { put("status", newStatus) }
        val request = okhttp3.Request.Builder()
            .url("$baseUrl/api/v1/orders/$backendOrderNo/status")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()
        val response = client.newCall(request).execute()
        if (!response.isSuccessful) {
            Log.w("UserRepository", "updateOrderStatusOnBackend: 后端返回 ${response.code}")
        }
    } catch (e: Exception) {
        Log.e("UserRepository", "updateOrderStatusOnBackend: 同步失败", e)
    }
}

/**
 * 提交商品评价到后端。
 *
 * @param productId 商品 ID
 * @param nickname 用户昵称
 * @param rating 评分（1-5）
 * @param content 评价内容
 * @param isAnonymous 是否匿名评价
 * @return 评价是否提交成功
 */
suspend fun UserRepository.submitReviewToBackend(
    productId: String,
    nickname: String,
    rating: Int,
    content: String,
    isAnonymous: Boolean = false,
): Boolean = withContext(Dispatchers.IO) {
    val userId = getUserId()
    if (userId.isEmpty()) return@withContext false
    try {
        val baseUrl = NetworkConfig.BASE_URL
        val client = NetworkConfig.httpClient
        val body = okhttp3.MultipartBody.Builder()
            .setType(okhttp3.MultipartBody.FORM)
            .addFormDataPart("product_id", productId)
            .addFormDataPart("user_id", userId)
            .addFormDataPart("nickname", nickname)
            .addFormDataPart("rating", rating.toString())
            .addFormDataPart("content", content)
            .addFormDataPart("is_anonymous", isAnonymous.toString())
            .build()
        val request = okhttp3.Request.Builder()
            .url("$baseUrl/api/v1/reviews")
            .post(body)
            .build()
        val response = client.newCall(request).execute()
        response.isSuccessful
    } catch (e: Exception) {
        Log.e("UserRepository", "submitReviewToBackend: 同步失败", e)
        false
    }
}
