package com.shopping.agent.data.local

import android.content.ContentValues
import android.content.Context
import android.util.Log
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.shopping.agent.core.network.NetworkConfig
import com.shopping.agent.data.model.CartItem
import com.shopping.agent.data.model.ChatMessage
import com.shopping.agent.data.model.MessageRole
import com.shopping.agent.data.model.Product
import com.shopping.agent.data.model.WebSearchItem
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody

/**
 * 用户数据仓库 — 封装 LocalDatabase 的 CRUD 操作。
 *
 * 对标:
 *   微信 WCDB → 消息/联系人本地缓存
 *   豆包 Room → 对话历史/用户偏好持久化
 */
class UserRepository(context: Context) {

    private val db = LocalDatabase(context)
    private val gson = Gson()

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
     * 查询当前用户画像 — 返回文本列的键值对 Map（不包含 avatar BLOB）。
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
    // 购物车 (本地缓存)
    // ═══════════════════════════════════════════════════════

    suspend fun saveCartItem(product: Product, sessionId: String, quantity: Int = 1) = withContext(Dispatchers.IO) {
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

    suspend fun getCartItems(sessionId: String): List<CartItem> = withContext(Dispatchers.IO) {
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

    suspend fun removeCartItem(productId: String) = withContext(Dispatchers.IO) {
        db.writableDatabase.delete(LocalDatabase.TABLE_CART, "product_id=?", arrayOf(productId))
    }

    suspend fun clearCart(sessionId: String) = withContext(Dispatchers.IO) {
        db.writableDatabase.delete(LocalDatabase.TABLE_CART, "session_id=?", arrayOf(sessionId))
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
    // 登录凭证
    // ═══════════════════════════════════════════════════════

    /**
     * 保存或更新用户登录凭证。
     * 密码在存入前已由调用方使用 [CryptoUtil.encrypt] 加密。
     * @param loginMethod 登录方式："phone" 或 "email"
     * @param encryptedPassword AES 加密后的密码
     */
    suspend fun saveCredentials(loginMethod: String, encryptedPassword: String) = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext
        val cv = ContentValues().apply {
            put("user_id", userId)
            put("login_method", loginMethod)
            put("password", encryptedPassword)
        }
        db.writableDatabase.insertWithOnConflict(
            LocalDatabase.TABLE_CREDENTIALS, null, cv,
            android.database.sqlite.SQLiteDatabase.CONFLICT_REPLACE
        )
    }

    /**
     * 获取当前用户的登录凭证。
     * @return Map 包含 login_method 和 password，若未设置则返回 null
     */
    suspend fun getCredentials(): Map<String, String>? = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext null
        val cursor = db.readableDatabase.query(
            LocalDatabase.TABLE_CREDENTIALS, arrayOf("login_method", "password"),
            "user_id=?", arrayOf(userId), null, null, null
        )
        val result = if (cursor.moveToFirst()) {
            mapOf(
                "login_method" to (cursor.getString(0) ?: ""),
                "password" to (cursor.getString(1) ?: ""),
            )
        } else null
        cursor.close()
        result
    }

    /** 检查当前用户是否为游客登录（无保存的登录凭证） */
    suspend fun isGuestLogin(): Boolean = withContext(Dispatchers.IO) {
        getCredentials() == null
    }

    /**
     * 删除当前用户的登录凭证（游客登出时调用）。
     * 清除凭证后，将用户标记回游客状态（is_guest=1），但不删除 user_profile 记录。
     * 调用方如需删除 user_profile，应显式操作。
     */
    suspend fun deleteCredentials() = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext
        db.writableDatabase.delete(LocalDatabase.TABLE_CREDENTIALS, "user_id=?", arrayOf(userId))
        // 清除登录状态
        db.writableDatabase.delete(LocalDatabase.TABLE_LOGIN_STATE, "user_id=?", arrayOf(userId))
        // 标记回游客状态
        val cv = ContentValues().apply { put("is_guest", 1) }
        db.writableDatabase.update(LocalDatabase.TABLE_USER, cv, "id=?", arrayOf(userId))
    }

    /**
     * 清除当前用户的所有本地数据（购物车、收藏、足迹、搜索历史）。
     *
     * 用于"退出登录"场景：与"切换账号"不同，退出登录会清空本地业务数据，
     * 但保留 user_profile 记录本身（供下一次登录或游客使用）。
     * 调用此方法后应再调用 [deleteCredentials] 以清除登录态。
     */
    suspend fun clearAllLocalData() = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext
        val writableDb = db.writableDatabase
        writableDb.delete(LocalDatabase.TABLE_CART, "user_id=?", arrayOf(userId))
        writableDb.delete(LocalDatabase.TABLE_FAVORITES, "user_id=?", arrayOf(userId))
        writableDb.delete(LocalDatabase.TABLE_FOOTPRINTS, "user_id=?", arrayOf(userId))
        writableDb.delete(LocalDatabase.TABLE_SEARCH, null, null)
        writableDb.delete(LocalDatabase.TABLE_CUSTOMER_SERVICE, "user_id=?", arrayOf(userId))
    }

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

    /**
     * 创建新的用户画像（注册时使用），返回新用户的 sw UUID。
     * 若当前存在游客用户（is_guest=1），则先删除旧的游客画像再创建新画像。
     * 非游客用户 is_guest 设为 0。
     */
    suspend fun createUserProfile(): String = withContext(Dispatchers.IO) {
        // 删除已有的游客画像（避免 getUserId() 一直返回旧 guest ID）
        val oldUserId = try {
            val cursor = db.readableDatabase.query(
                LocalDatabase.TABLE_USER, arrayOf("id"), "is_guest=1", null, null, null, null, "1"
            )
            val id = if (cursor.moveToFirst()) cursor.getString(0) else null
            cursor.close()
            id
        } catch (_: Exception) { null }

        if (oldUserId != null) {
            db.writableDatabase.delete(LocalDatabase.TABLE_USER, "id=?", arrayOf(oldUserId))
        }

        val newId = "sw" + java.util.UUID.randomUUID().toString()
        val now = System.currentTimeMillis()
        val cv = ContentValues().apply {
            put("id", newId)
            put("is_guest", 0)
            put("created_at", now)
            put("updated_at", now)
        }
        db.writableDatabase.insert(LocalDatabase.TABLE_USER, null, cv)
        newId
    }

    // ═══════════════════════════════════════════════════════
    // 收货地址
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

    /**
     * 新增收货地址。
     * 若设为默认地址，则先将该用户其他地址的 is_default 置为 0（保证唯一默认）。
     */
    suspend fun addShippingAddress(address: ShippingAddress): Long = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext -1L

        val writableDb = db.writableDatabase
        // 唯一默认地址约束：先将其他地址设为非默认
        if (address.isDefault) {
            clearDefaultAddress(writableDb, userId)
        }

        val cv = ContentValues().apply {
            put("user_id", userId)
            put("is_default", if (address.isDefault) 1 else 0)
            put("phone", address.phone)
            put("recipient_name", address.recipientName)
            put("address_detail", address.addressDetail)
            put("address_type", address.addressType)
        }
        writableDb.insert(LocalDatabase.TABLE_SHIPPING_ADDRESSES, null, cv)
    }

    /** 清除指定用户所有地址的 is_default 标记 */
    private fun clearDefaultAddress(db: android.database.sqlite.SQLiteDatabase, userId: String) {
        val cv = ContentValues().apply { put("is_default", 0) }
        db.update(LocalDatabase.TABLE_SHIPPING_ADDRESSES, cv, "user_id=? AND is_default=1", arrayOf(userId))
    }

    /**
     * 获取当前用户所有收货地址，默认地址排在前面。
     * @return 地址列表，按 is_default DESC + address_id ASC 排序
     */
    suspend fun getShippingAddresses(): List<ShippingAddress> = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext emptyList()
        val cursor = db.readableDatabase.query(
            LocalDatabase.TABLE_SHIPPING_ADDRESSES, null,
            "user_id=?", arrayOf(userId),
            null, null, "is_default DESC, address_id ASC"
        )
        val list = mutableListOf<ShippingAddress>()
        while (cursor.moveToNext()) {
            list.add(ShippingAddress(
                addressId = cursor.getLong(cursor.getColumnIndexOrThrow("address_id")),
                userId = cursor.getString(cursor.getColumnIndexOrThrow("user_id")) ?: "",
                isDefault = cursor.getInt(cursor.getColumnIndexOrThrow("is_default")) == 1,
                phone = cursor.getString(cursor.getColumnIndexOrThrow("phone")) ?: "",
                recipientName = cursor.getString(cursor.getColumnIndexOrThrow("recipient_name")) ?: "",
                addressDetail = cursor.getString(cursor.getColumnIndexOrThrow("address_detail")) ?: "",
                addressType = cursor.getString(cursor.getColumnIndexOrThrow("address_type")) ?: "",
            ))
        }
        cursor.close()
        list
    }

    /**
     * 更新收货地址信息。
     * 若设为默认地址，则先将该用户其他地址的 is_default 置为 0。
     */
    suspend fun updateShippingAddress(address: ShippingAddress) = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext
        val writableDb = db.writableDatabase
        if (address.isDefault) {
            clearDefaultAddress(writableDb, userId)
        }
        val cv = ContentValues().apply {
            put("is_default", if (address.isDefault) 1 else 0)
            put("phone", address.phone)
            put("recipient_name", address.recipientName)
            put("address_detail", address.addressDetail)
            put("address_type", address.addressType)
        }
        writableDb.update(
            LocalDatabase.TABLE_SHIPPING_ADDRESSES, cv,
            "address_id=? AND user_id=?", arrayOf(address.addressId.toString(), userId)
        )
    }

    /**
     * 设置指定地址为默认地址（清除其他默认标记）。
     * @param addressId 要设为默认的地址 ID
     */
    suspend fun setDefaultShippingAddress(addressId: Long) = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext
        val writableDb = db.writableDatabase
        clearDefaultAddress(writableDb, userId)
        val cv = ContentValues().apply { put("is_default", 1) }
        writableDb.update(
            LocalDatabase.TABLE_SHIPPING_ADDRESSES, cv,
            "address_id=? AND user_id=?", arrayOf(addressId.toString(), userId)
        )
    }

    /** 删除收货地址 */
    suspend fun deleteShippingAddress(addressId: Long) = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext
        db.writableDatabase.delete(
            LocalDatabase.TABLE_SHIPPING_ADDRESSES,
            "address_id=? AND user_id=?", arrayOf(addressId.toString(), userId)
        )
    }

    // ═══════════════════════════════════════════════════════
    // 支付设置
    // ═══════════════════════════════════════════════════════

    /** 支付设置数据类 */
    data class PaymentSettings(
        val userId: String = "",
        val defaultPaymentMethod: String = "支付宝",  // "支付宝" / "微信"
        val paymentPassword: String = "",              // AES 加密存储
        val smallAmountPasswordFree: Boolean = false,
        val smallAmountLimit: String = "",             // 小额免密额度
    )

    /**
     * 获取当前用户的支付设置。若未设置则返回默认值。
     */
    suspend fun getPaymentSettings(): PaymentSettings = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext PaymentSettings()
        val cursor = db.readableDatabase.query(
            LocalDatabase.TABLE_PAYMENT_SETTINGS, null,
            "user_id=?", arrayOf(userId), null, null, null
        )
        val settings = if (cursor.moveToFirst()) {
            PaymentSettings(
                userId = cursor.getString(cursor.getColumnIndexOrThrow("user_id")) ?: "",
                defaultPaymentMethod = cursor.getString(cursor.getColumnIndexOrThrow("default_payment_method")) ?: "支付宝",
                paymentPassword = cursor.getString(cursor.getColumnIndexOrThrow("payment_password")) ?: "",
                smallAmountPasswordFree = cursor.getInt(cursor.getColumnIndexOrThrow("small_amount_password_free")) == 1,
                smallAmountLimit = cursor.getString(cursor.getColumnIndexOrThrow("small_amount_limit")) ?: "",
            )
        } else PaymentSettings()
        cursor.close()
        settings
    }

    /**
     * 保存或更新支付设置。
     * 支付密码在存入前已由调用方使用 [CryptoUtil.encrypt] 加密。
     */
    suspend fun savePaymentSettings(settings: PaymentSettings) = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext
        val cv = ContentValues().apply {
            put("user_id", userId)
            put("default_payment_method", settings.defaultPaymentMethod)
            put("payment_password", settings.paymentPassword)
            put("small_amount_password_free", if (settings.smallAmountPasswordFree) 1 else 0)
            put("small_amount_limit", settings.smallAmountLimit)
        }
        db.writableDatabase.insertWithOnConflict(
            LocalDatabase.TABLE_PAYMENT_SETTINGS, null, cv,
            android.database.sqlite.SQLiteDatabase.CONFLICT_REPLACE
        )
    }

    // ═══════════════════════════════════════════════════════
    // 国家与地区
    // ═══════════════════════════════════════════════════════

    /**
     * 获取当前用户的国家与地区设置，默认返回 "中国"。
     */
    suspend fun getCountryRegion(): String = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext "中国"
        val cursor = db.readableDatabase.query(
            LocalDatabase.TABLE_COUNTRY_REGION, arrayOf("country_region"),
            "user_id=?", arrayOf(userId), null, null, null
        )
        val value = if (cursor.moveToFirst()) cursor.getString(0) ?: "中国" else "中国"
        cursor.close()
        value
    }

    /**
     * 保存或更新国家与地区设置。
     */
    suspend fun saveCountryRegion(region: String) = withContext(Dispatchers.IO) {
        val userId = getUserId()
        if (userId.isEmpty()) return@withContext
        val cv = ContentValues().apply {
            put("user_id", userId)
            put("country_region", region)
        }
        db.writableDatabase.insertWithOnConflict(
            LocalDatabase.TABLE_COUNTRY_REGION, null, cv,
            android.database.sqlite.SQLiteDatabase.CONFLICT_REPLACE
        )
    }

    // ═══════════════════════════════════════════════════════
    // 订单记录
    // ═══════════════════════════════════════════════════════

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

    /**
     * 新增一条订单记录。
     * @param orderBody 订单体 JSON（含商品快照、总价等）
     * @param status 订单状态，默认待付款
     * @param backendOrderNo 后端订单号，前后端订单关联字段
     * @return 新订单的 orderId，失败返回 -1
     */
    suspend fun addOrderRecord(
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
    suspend fun getOrderRecords(statusFilter: String? = null, limit: Int = 50): List<OrderRecord> = withContext(Dispatchers.IO) {
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
    suspend fun updateOrderStatus(orderId: Long, newStatus: String) = withContext(Dispatchers.IO) {
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
    suspend fun getOrderCountByStatus(statuses: List<String>): Map<String, Int> = withContext(Dispatchers.IO) {
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
    // 购物车 (扩展：支持 user_id 关联)
    // ═══════════════════════════════════════════════════════

    /**
     * 获取当前用户的购物车商品（优先按 user_id 查询，兼容旧 session_id 模式）。
     * 若 user_id 未关联到用户画像或用户为游客状态，回退到 session_id 查询。
     */
    suspend fun getCartItemsForCurrentUser(sessionId: String): List<CartItem> = withContext(Dispatchers.IO) {
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
    suspend fun saveCartItemForCurrentUser(product: Product, sessionId: String, quantity: Int = 1) = withContext(Dispatchers.IO) {
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
    suspend fun updateCartItemSelection(productId: String, isSelected: Boolean) = withContext(Dispatchers.IO) {
        val cv = ContentValues().apply {
            put("is_selected", if (isSelected) 1 else 0)
        }
        db.writableDatabase.update(LocalDatabase.TABLE_CART, cv, "product_id=?", arrayOf(productId))
    }

    /** 批量更新购物车商品的选中状态 */
    suspend fun updateCartItemsSelection(productIds: List<String>, isSelected: Boolean) = withContext(Dispatchers.IO) {
        val cv = ContentValues().apply {
            put("is_selected", if (isSelected) 1 else 0)
        }
        val writableDb = db.writableDatabase
        productIds.forEach { productId ->
            writableDb.update(LocalDatabase.TABLE_CART, cv, "product_id=?", arrayOf(productId))
        }
    }

    /** 更新购物车商品数量 */
    suspend fun updateCartItemQuantity(productId: String, quantity: Int) = withContext(Dispatchers.IO) {
        val cv = ContentValues().apply {
            put("quantity", quantity)
        }
        db.writableDatabase.update(LocalDatabase.TABLE_CART, cv, "product_id=?", arrayOf(productId))
    }

    /** 删除购物车中指定商品 */
    suspend fun deleteCartItems(productIds: List<String>) = withContext(Dispatchers.IO) {
        val writableDb = db.writableDatabase
        productIds.forEach { productId ->
            writableDb.delete(LocalDatabase.TABLE_CART, "product_id=?", arrayOf(productId))
        }
    }

    /** 获取购物车商品总数 */
    suspend fun getCartItemCount(): Int = withContext(Dispatchers.IO) {
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
    suspend fun syncCartFromBackend(sessionId: String) = withContext(Dispatchers.IO) {
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

    // ═══════════════════════════════════════════════════════
    // 商品收藏记录
    // ═══════════════════════════════════════════════════════

    /** 收藏记录数据类 */
    data class FavoriteRecord(
        val userId: String = "",
        val productId: String = "",
        val createdAt: Long = 0,
    )

    /**
     * 检查用户是否已收藏指定商品。
     * @param productId 商品 ID
     * @return true 表示已收藏
     */
    suspend fun isFavorited(productId: String): Boolean = withContext(Dispatchers.IO) {
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
    suspend fun toggleFavorite(productId: String): Boolean = withContext(Dispatchers.IO) {
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
            // 已收藏 → 取消收藏
            writableDb.delete(
                LocalDatabase.TABLE_FAVORITES,
                "user_id=? AND product_id=?",
                arrayOf(userId, productId)
            )
            false
        } else {
            // 未收藏 → 添加收藏
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
    suspend fun getFavorites(limit: Int = 0): List<FavoriteRecord> = withContext(Dispatchers.IO) {
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
    suspend fun getFavoriteCount(): Int = withContext(Dispatchers.IO) {
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
    suspend fun removeFavorites(productIds: List<String>): Int = withContext(Dispatchers.IO) {
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
    // 商品足迹记录（浏览历史）
    // ═══════════════════════════════════════════════════════

    /** 足迹记录数据类 */
    data class FootprintRecord(
        val userId: String = "",
        val productId: String = "",
        /** 浏览日期（毫秒时间戳），读写时转为年月日（当天0点） */
        val browseDate: Long = 0,
        val createdAt: Long = 0,
    )

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
     * - 库中不存在该商品的足迹 → 新增记录
     * - 库中已存在该商品的足迹 → 更新浏览日期
     *
     * @param productId 商品 ID
     */
    suspend fun recordFootprint(productId: String) = withContext(Dispatchers.IO) {
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
            // 已存在 → 更新浏览日期
            val cv = ContentValues().apply {
                put("browse_date", today)
            }
            writableDb.update(
                LocalDatabase.TABLE_FOOTPRINTS, cv,
                "user_id=? AND product_id=?",
                arrayOf(userId, productId)
            )
        } else {
            // 不存在 → 新增足迹记录
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
    suspend fun getFootprints(
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
    suspend fun getFootprintCount(
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

    // ═══════════════════════════════════════════════════════
    // 收藏 + 足迹 后端同步
    // ═══════════════════════════════════════════════════════

    /**
     * 同步收藏状态到后端 PostgreSQL。
     *
     * @param productId 商品 ID
     * @param isFavorited true=添加收藏, false=取消收藏
     */
    suspend fun syncFavoriteToBackend(productId: String, isFavorited: Boolean) = withContext(Dispatchers.IO) {
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
    suspend fun syncFavoritesFromBackend() = withContext(Dispatchers.IO) {
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
     * 同步足迹记录到后端 PostgreSQL。
     *
     * @param productId 商品 ID
     */
    suspend fun syncFootprintToBackend(productId: String) = withContext(Dispatchers.IO) {
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

    /**
     * 批量同步收藏移除到后端。
     * @param productIds 要移除收藏的商品 ID 列表
     */
    suspend fun syncFavoriteRemoveToBackend(productIds: List<String>) = withContext(Dispatchers.IO) {
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

    // ═══════════════════════════════════════════════════════
    // 订单操作 — 后端同步
    // ═══════════════════════════════════════════════════════

    /**
     * 调用后端 API 取消订单。
     *
     * @param backendOrderNo 后端订单号（ORD 开头）
     */
    suspend fun cancelOrderOnBackend(backendOrderNo: String) = withContext(Dispatchers.IO) {
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
    suspend fun updateOrderStatusOnBackend(backendOrderNo: String, newStatus: String) = withContext(Dispatchers.IO) {
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
    suspend fun submitReviewToBackend(
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
}
