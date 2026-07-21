package com.shopping.agent.data.local

import android.content.ContentValues
import android.content.Context
import android.util.Log
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.shopping.agent.data.model.ChatMessage
import com.shopping.agent.data.model.MessageRole
import com.shopping.agent.data.model.Product
import com.shopping.agent.data.model.WebSearchItem
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * 用户数据仓库 - 封装 LocalDatabase 的 CRUD 操作。
 *
 * 对标:
 *   微信 WCDB -> 消息/联系人本地缓存
 *   豆包 Room -> 对话历史/用户偏好持久化
 */
class UserRepository(context: Context) {

    internal val db = LocalDatabase(context)
    internal val gson = Gson()

    // ═══════════════════════════════════════════════════════
    // 用户画像
    // ═══════════════════════════════════════════════════════

    /** 用户画像查询列（排除 BLOB 列，避免 cursor.getString() 在二进制数据上行为未定义） */
    private val USER_PROFILE_COLUMNS = arrayOf(
        "id", "nickname", "gender", "age_range",
        "budget_min", "budget_max", "preferred_categories",
        "is_guest", "created_at", "updated_at",
    )

    /**
     * 从数据库查询当前用户 UUID（"sw" 前缀的 TEXT 主键）。
     * 若表为空则自动创建默认用户行，确保所有涉及 user_profile 的操作都能正常读写。
     */
    fun getUserId(): String {
        val db = this.db.readableDatabase
        val cursor = db.rawQuery(
            "SELECT id FROM ${LocalDatabase.TABLE_USER} LIMIT 1", null
        )
        val id = if (cursor.moveToFirst()) cursor.getString(0) ?: "" else ""
        cursor.close()
        if (id.isEmpty()) {
            // 表为空（安装后首次启动或 DB 被意外清空），立即创建默认用户
            try {
                val newId = "sw" + java.util.UUID.randomUUID().toString()
                val now = System.currentTimeMillis()
                val cv = android.content.ContentValues().apply {
                    put("id", newId)
                    put("created_at", now)
                    put("updated_at", now)
                }
                this.db.writableDatabase.insert(LocalDatabase.TABLE_USER, null, cv)
                return newId
            } catch (_: Exception) {
                return ""
            }
        }
        return id
    }

    /**
     * 查询当前用户画像 - 返回文本列的键值对 Map（不包含 avatar BLOB）。
     * 通过 [getUserId] 动态获取用户 ID，不再硬编码 id=1。
     */
    suspend fun getUserProfile(): Map<String, String> = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext emptyMap()
        val cursor = db.readableDatabase.query(
            LocalDatabase.TABLE_USER, USER_PROFILE_COLUMNS, "id=?", arrayOf(userId), null, null, null
        )
        val result = mutableMapOf<String, String>()
        if (cursor.moveToFirst()) {
            for (i in 0 until cursor.columnCount) {
                val key = cursor.getColumnName(i)
                val value = cursor.getString(i) ?: ""
                result[key] = value
            }
        }
        cursor.close()
        result
    }

    /**
     * 更新用户画像字段，只更新传入的键值对，自动刷新 updated_at。
     * 通过 [getUserId] 动态获取用户 ID。
     */
    suspend fun updateUserProfile(fields: Map<String, String>) = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext
        val cv = ContentValues().apply {
            for ((k, v) in fields) put(k, v)
            put("updated_at", System.currentTimeMillis())
        }
        db.writableDatabase.update(LocalDatabase.TABLE_USER, cv, "id=?", arrayOf(userId))
    }

    /**
     * 读取用户头像 BLOB 数据，返回 JPEG 字节数组。
     * 若用户不存在或未设置头像则返回 null。
     */
    suspend fun getUserAvatar(): ByteArray? = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext null
        val cursor = db.readableDatabase.query(
            LocalDatabase.TABLE_USER, arrayOf("avatar"), "id=?", arrayOf(userId), null, null, null
        )
        val avatar = if (cursor.moveToFirst()) cursor.getBlob(0) else null
        cursor.close()
        avatar
    }

    /**
     * 写入用户头像 BLOB 数据到数据库，同步更新 updated_at 时间戳。
     * 调用方应确保传入的 ByteArray 已经过分辨率压缩（建议 ≤ 480px）。
     */
    suspend fun updateUserAvatar(avatarBytes: ByteArray) = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext
        val cv = ContentValues().apply {
            put("avatar", avatarBytes)
            put("updated_at", System.currentTimeMillis())
        }
        db.writableDatabase.update(LocalDatabase.TABLE_USER, cv, "id=?", arrayOf(userId))
    }

    // ═══════════════════════════════════════════════════════
    // 对话会话
    // ═══════════════════════════════════════════════════════

    suspend fun createConversation(id: String, title: String = "") = withContext(Dispatchers.IO) {
        val now = System.currentTimeMillis()
        val cv = ContentValues().apply {
            put("id", id)
            put("title", title)
            put("created_at", now)
            put("updated_at", now)
        }
        // INSERT OR IGNORE preserves existing rows (and their created_at)
        db.writableDatabase.insertWithOnConflict(
            LocalDatabase.TABLE_CONVERSATIONS, null, cv,
            android.database.sqlite.SQLiteDatabase.CONFLICT_IGNORE
        )
        // Always refresh updated_at so the conversation moves to top of list
        val updateCv = ContentValues().apply {
            put("updated_at", now)
        }
        db.writableDatabase.update(LocalDatabase.TABLE_CONVERSATIONS, updateCv, "id=?", arrayOf(id))
    }

    suspend fun getConversations(limit: Int = 20): List<Map<String, String>> = withContext(Dispatchers.IO) {
        val cursor = db.readableDatabase.query(
            LocalDatabase.TABLE_CONVERSATIONS, null, null, null, null, null,
            "updated_at DESC", limit.toString()
        )
        val list = mutableListOf<Map<String, String>>()
        while (cursor.moveToNext()) {
            val row = mutableMapOf<String, String>()
            for (i in 0 until cursor.columnCount) {
                row[cursor.getColumnName(i)] = cursor.getString(i) ?: ""
            }
            list.add(row)
        }
        cursor.close()
        list
    }

    suspend fun getConversationMetas(limit: Int = 50): List<com.shopping.agent.data.model.ConversationMeta> = withContext(Dispatchers.IO) {
        val cursor = db.readableDatabase.query(
            LocalDatabase.TABLE_CONVERSATIONS, null, null, null, null, null,
            "updated_at DESC", limit.toString()
        )
        val list = mutableListOf<com.shopping.agent.data.model.ConversationMeta>()
        while (cursor.moveToNext()) {
            list.add(com.shopping.agent.data.model.ConversationMeta(
                id = cursor.getString(cursor.getColumnIndexOrThrow("id")),
                title = cursor.getString(cursor.getColumnIndexOrThrow("title")) ?: "",
                messageCount = cursor.getInt(cursor.getColumnIndexOrThrow("message_count")),
                lastMessage = cursor.getString(cursor.getColumnIndexOrThrow("last_message")) ?: "",
                createdAt = cursor.getLong(cursor.getColumnIndexOrThrow("created_at")),
                updatedAt = cursor.getLong(cursor.getColumnIndexOrThrow("updated_at")),
            ))
        }
        cursor.close()
        list
    }

    suspend fun updateConversationTitle(convId: String, title: String) = withContext(Dispatchers.IO) {
        val cv = ContentValues().apply {
            put("title", title)
            put("updated_at", System.currentTimeMillis())
        }
        db.writableDatabase.update(LocalDatabase.TABLE_CONVERSATIONS, cv, "id=?", arrayOf(convId))
    }

    suspend fun deleteConversation(convId: String) = withContext(Dispatchers.IO) {
        db.writableDatabase.delete(LocalDatabase.TABLE_MESSAGES, "conversation_id=?", arrayOf(convId))
        db.writableDatabase.delete(LocalDatabase.TABLE_CONVERSATIONS, "id=?", arrayOf(convId))
    }

    // ═══════════════════════════════════════════════════════
    // 聊天消息
    // ═══════════════════════════════════════════════════════

    suspend fun saveMessage(message: ChatMessage, conversationId: String) = withContext(Dispatchers.IO) {
        val cv = ContentValues().apply {
            put("id", message.id)
            put("conversation_id", conversationId)
            put("role", message.role.name)
            put("content", message.content)
            put("product_cards", gson.toJson(message.productCards))
            put("web_search_results", gson.toJson(message.webSearchResults))
            put("compare_dimensions", gson.toJson(message.compareDimensions))
            put("audio_uri", message.audioUri ?: "")
            put("audio_duration_sec", message.audioDurationSec)
            put("status", message.status.name)
            put("created_at", System.currentTimeMillis())
        }
        db.writableDatabase.insertWithOnConflict(
            LocalDatabase.TABLE_MESSAGES, null, cv,
            android.database.sqlite.SQLiteDatabase.CONFLICT_REPLACE
        )

        // 更新会话元数据 (COUNT(*) 已含本消息，不再 +1)
        val convCv = ContentValues().apply {
            put("message_count", getMessageCount(conversationId))
            put("last_message", message.content.take(100))
            put("updated_at", System.currentTimeMillis())
        }
        db.writableDatabase.update(
            LocalDatabase.TABLE_CONVERSATIONS, convCv, "id=?", arrayOf(conversationId)
        )
    }

    suspend fun getMessages(conversationId: String, limit: Int = 50): List<ChatMessage> = withContext(Dispatchers.IO) {
        val cursor = db.readableDatabase.query(
            LocalDatabase.TABLE_MESSAGES, null,
            "conversation_id=?", arrayOf(conversationId),
            null, null, "created_at ASC", limit.toString()
        )
        val list = mutableListOf<ChatMessage>()
        while (cursor.moveToNext()) {
            val cardsJson = cursor.getString(cursor.getColumnIndexOrThrow("product_cards")) ?: "[]"
            val cards: List<Product> = try {
                gson.fromJson(cardsJson, object : TypeToken<List<Product>>() {}.type)
            } catch (e: Exception) {
                Log.e("UserRepository", "Failed to deserialize product cards", e)
                emptyList()
            }

            val webJson = cursor.getString(cursor.getColumnIndexOrThrow("web_search_results")) ?: "[]"
            val webResults: List<WebSearchItem> = try {
                gson.fromJson(webJson, object : TypeToken<List<WebSearchItem>>() {}.type)
            } catch (e: Exception) {
                Log.e("UserRepository", "Failed to deserialize web search results", e)
                emptyList()
            }

            val compareJson = cursor.getColumnIndex("compare_dimensions")
                .takeIf { it >= 0 }
                ?.let { cursor.getString(it) }
                ?: "[]"
            val compareDimensions: List<Map<String, Any?>> = try {
                gson.fromJson(compareJson, object : TypeToken<List<Map<String, Any?>>>() {}.type)
                    ?: emptyList()
            } catch (e: Exception) {
                Log.e("UserRepository", "Failed to deserialize compare dimensions", e)
                emptyList()
            }

            list.add(ChatMessage(
                id = cursor.getString(cursor.getColumnIndexOrThrow("id")),
                role = MessageRole.valueOf(cursor.getString(cursor.getColumnIndexOrThrow("role"))),
                content = cursor.getString(cursor.getColumnIndexOrThrow("content")) ?: "",
                productCards = cards,
                webSearchResults = webResults,
                compareDimensions = compareDimensions,
                status = com.shopping.agent.data.model.MessageStatus.valueOf(
                    cursor.getString(cursor.getColumnIndexOrThrow("status")) ?: "Sent"
                ),
                audioUri = cursor.getColumnIndex("audio_uri")
                    .takeIf { it >= 0 }
                    ?.let { cursor.getString(it) }
                    ?.takeIf { it.isNotBlank() },
                audioDurationSec = cursor.getColumnIndex("audio_duration_sec")
                    .takeIf { it >= 0 }
                    ?.let { cursor.getInt(it) }
                    ?: 0,
            ))
        }
        cursor.close()
        list
    }

    suspend fun getMessageCount(conversationId: String): Int = withContext(Dispatchers.IO) {
        val cursor = db.readableDatabase.rawQuery(
            "SELECT COUNT(*) FROM ${LocalDatabase.TABLE_MESSAGES} WHERE conversation_id=?",
            arrayOf(conversationId)
        )
        val count = if (cursor.moveToFirst()) cursor.getInt(0) else 0
        cursor.close()
        count
    }

    // ═══════════════════════════════════════════════════════
    // 设置
    // ═══════════════════════════════════════════════════════

    suspend fun getSetting(key: String, default: String = ""): String = withContext(Dispatchers.IO) {
        getSettingSync(key, default)
    }

    fun getSettingSync(key: String, default: String = ""): String {
        val cursor = db.readableDatabase.query(
            LocalDatabase.TABLE_SETTINGS, arrayOf("value"),
            "key=?", arrayOf(key), null, null, null
        )
        val value = if (cursor.moveToFirst()) cursor.getString(0) ?: default else default
        cursor.close()
        return value
    }

    suspend fun setSetting(key: String, value: String) = withContext(Dispatchers.IO) {
        setSettingSync(key, value)
    }

    fun setSettingSync(key: String, value: String) {
        val cv = ContentValues().apply {
            put("key", key)
            put("value", value)
        }
        db.writableDatabase.insertWithOnConflict(
            LocalDatabase.TABLE_SETTINGS, null, cv,
            android.database.sqlite.SQLiteDatabase.CONFLICT_REPLACE
        )
    }

    // ═══════════════════════════════════════════════════════
    // 搜索历史
    // ═══════════════════════════════════════════════════════

    suspend fun addSearchHistory(query: String) = withContext(Dispatchers.IO) {
        val cv = ContentValues().apply {
            put("query", query)
            put("created_at", System.currentTimeMillis())
        }
        db.writableDatabase.insert(LocalDatabase.TABLE_SEARCH, null, cv)
        // 只保留最近 50 条
        db.writableDatabase.execSQL(
            "DELETE FROM ${LocalDatabase.TABLE_SEARCH} WHERE id NOT IN (SELECT id FROM ${LocalDatabase.TABLE_SEARCH} ORDER BY created_at DESC LIMIT 50)"
        )
    }

    suspend fun getSearchHistory(limit: Int = 20): List<String> = withContext(Dispatchers.IO) {
        val cursor = db.readableDatabase.query(
            LocalDatabase.TABLE_SEARCH, arrayOf("query"),
            null, null, null, null, "created_at DESC", limit.toString()
        )
        val list = mutableListOf<String>()
        while (cursor.moveToNext()) list.add(cursor.getString(0))
        cursor.close()
        list
    }

    // ═══════════════════════════════════════════════════════
    // 客服对话记录
    // ═══════════════════════════════════════════════════════

    /** 客服消息数据类 */
    data class CustomerServiceMessage(
        val id: Long = 0,
        val role: String,
        val content: String,
        val createdAt: Long,
    )

    /** 保存一条客服对话消息 */
    suspend fun saveCustomerServiceMessage(role: String, content: String) = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext
        val cv = ContentValues().apply {
            put("user_id", userId)
            put("role", role)
            put("content", content)
            put("created_at", System.currentTimeMillis())
        }
        db.writableDatabase.insert(LocalDatabase.TABLE_CUSTOMER_SERVICE, null, cv)
    }

    /** 读取当前用户所有客服对话消息，按时间升序排列 */
    suspend fun getCustomerServiceMessages(): List<CustomerServiceMessage> = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext emptyList()
        val cursor = db.readableDatabase.query(
            LocalDatabase.TABLE_CUSTOMER_SERVICE, null,
            "user_id=?", arrayOf(userId),
            null, null, "created_at ASC"
        )
        val list = mutableListOf<CustomerServiceMessage>()
        while (cursor.moveToNext()) {
            list.add(CustomerServiceMessage(
                id = cursor.getLong(cursor.getColumnIndexOrThrow("id")),
                role = cursor.getString(cursor.getColumnIndexOrThrow("role")) ?: "",
                content = cursor.getString(cursor.getColumnIndexOrThrow("content")) ?: "",
                createdAt = cursor.getLong(cursor.getColumnIndexOrThrow("created_at")),
            ))
        }
        cursor.close()
        list
    }

    /** 获取最后一条客服消息的 id，用于判断新消息分隔符 */
    suspend fun getLastCustomerServiceMessageId(): Long = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext 0L
        val cursor = db.readableDatabase.query(
            LocalDatabase.TABLE_CUSTOMER_SERVICE, arrayOf("id"),
            "user_id=?", arrayOf(userId),
            null, null, "id DESC", "1"
        )
        val id = if (cursor.moveToFirst()) cursor.getLong(0) else 0L
        cursor.close()
        id
    }

    // ═══════════════════════════════════════════════════════
    // 登录状态检查
    // ═══════════════════════════════════════════════════════

    /**
     * 检查当前用户是否为游客（is_guest = 1）。
     * @return true 表示游客登录，false 表示非游客（已通过手机号/邮箱登录）
     */
    suspend fun isGuestUser(): Boolean = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext true
        val cursor = db.readableDatabase.query(
            LocalDatabase.TABLE_USER, arrayOf("is_guest"),
            "id=?", arrayOf(userId), null, null, null
        )
        val isGuest = if (cursor.moveToFirst()) cursor.getInt(0) == 1 else true
        cursor.close()
        isGuest
    }

    /**
     * 标记当前用户为非游客登录（登录/注册成功后调用）。
     */
    suspend fun markAsLoggedIn() = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext
        val cv = ContentValues().apply {
            put("is_guest", 0)
            put("updated_at", System.currentTimeMillis())
        }
        db.writableDatabase.update(LocalDatabase.TABLE_USER, cv, "id=?", arrayOf(userId))
    }

    // ═══════════════════════════════════════════════════════
    // 登录状态
    // ═══════════════════════════════════════════════════════

    /** 登录状态数据类 */
    data class LoginState(
        val userId: String = "",
        val loginStatus: Boolean = false,  // true=已登录, false=未登录
        val loginType: String = "",        // "" / "guest" / "non_guest"
    )

    /**
     * 保存当前用户的登录状态（登录/注册/游客成功后调用）。
     * @param loginType 登录类型："guest" 或 "non_guest"
     */
    suspend fun saveLoginState(loginType: String) = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext
        val cv = ContentValues().apply {
            put("user_id", userId)
            put("login_status", 1)
            put("login_type", loginType)
        }
        db.writableDatabase.insertWithOnConflict(
            LocalDatabase.TABLE_LOGIN_STATE, null, cv,
            android.database.sqlite.SQLiteDatabase.CONFLICT_REPLACE
        )
    }

    /**
     * 获取当前用户的登录状态。
     * @return LoginState，若未记录则返回默认值（loginStatus=false）
     */
    suspend fun getLoginState(): LoginState = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext LoginState()
        val cursor = db.readableDatabase.query(
            LocalDatabase.TABLE_LOGIN_STATE, null,
            "user_id=?", arrayOf(userId), null, null, null
        )
        val state = if (cursor.moveToFirst()) {
            LoginState(
                userId = cursor.getString(cursor.getColumnIndexOrThrow("user_id")) ?: "",
                loginStatus = cursor.getInt(cursor.getColumnIndexOrThrow("login_status")) == 1,
                loginType = cursor.getString(cursor.getColumnIndexOrThrow("login_type")) ?: "",
            )
        } else LoginState()
        cursor.close()
        state
    }

    /**
     * 检查当前用户是否已完成登录（含游客登录确认）。
     * 仅在 login_state 表中存在 login_status=1 的记录时返回 true。
     * 用于启动时判断是否需要展示登录页面。
     */
    suspend fun isLoggedIn(): Boolean = withContext(Dispatchers.IO) {
        getLoginState().loginStatus
    }

    /**
     * 清除登录状态（退出登录时调用）。
     */
    suspend fun clearLoginState() = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext
        db.writableDatabase.delete(LocalDatabase.TABLE_LOGIN_STATE, "user_id=?", arrayOf(userId))
    }

    // ═══════════════════════════════════════════════════════
    // 嵌套数据类（供扩展函数使用）
    // ═══════════════════════════════════════════════════════

    /** 收货地址数据类 */
    data class ShippingAddress(
        val addressId: Long = 0,
        val userId: String = "",
        val isDefault: Boolean = false,
        val phone: String = "",
        val recipientName: String = "",
        val addressDetail: String = "",
        val addressType: String = "",  // "" / "家" / "公司" / "学校"
    )

    /** 支付设置数据类 */
    data class PaymentSettings(
        val userId: String = "",
        val defaultPaymentMethod: String = "支付宝",  // "支付宝" / "微信"
        val paymentPassword: String = "",              // AES 加密存储
        val smallAmountPasswordFree: Boolean = false,
        val smallAmountLimit: String = "",             // 小额免密额度
    )

    /** 订单状态枚举值 */
    object OrderStatus {
        const val PENDING_PAYMENT = "待付款"
        const val PENDING_SHIPPING = "待发货"
        const val PENDING_RECEIPT = "待收货"
        const val PENDING_REVIEW = "待评价"
        const val COMPLETED = "已完成"
        const val CANCELLED = "已取消"

        val ALL = listOf(PENDING_PAYMENT, PENDING_SHIPPING, PENDING_RECEIPT, PENDING_REVIEW, COMPLETED, CANCELLED)
    }

    /** 订单记录数据类 */
    data class OrderRecord(
        val orderId: Long = 0,
        val userId: String = "",
        val backendOrderNo: String = "",  // 后端订单号 ORD 开头，前后端订单关联字段
        val orderBody: String = "",
        val createdAt: Long = 0,
        val updatedAt: Long = 0,  // 订单更新时间戳
        val status: String = OrderStatus.PENDING_PAYMENT,
    )

    /** 收藏记录数据类 */
    data class FavoriteRecord(
        val userId: String = "",
        val productId: String = "",
        val createdAt: Long = 0,
    )

    /** 足迹记录数据类 */
    data class FootprintRecord(
        val userId: String = "",
        val productId: String = "",
        /** 浏览日期（毫秒时间戳），读写时转为年月日（当天0点） */
        val browseDate: Long = 0,
        val createdAt: Long = 0,
    )
}
