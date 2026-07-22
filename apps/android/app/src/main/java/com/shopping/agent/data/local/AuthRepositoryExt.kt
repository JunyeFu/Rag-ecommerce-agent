package com.shopping.agent.data.local

import android.content.ContentValues
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

// ═══════════════════════════════════════════════════════
// 登录凭证管理
// ═══════════════════════════════════════════════════════

/**
 * 保存或更新用户登录凭证。
 * 密码在存入前已由调用方使用 [CryptoUtil.encrypt] 加密。
 * @param loginMethod 登录方式："phone" 或 "email"
 * @param encryptedPassword AES 加密后的密码
 */
suspend fun UserRepository.saveCredentials(loginMethod: String, encryptedPassword: String) = withContext(Dispatchers.IO) {
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
suspend fun UserRepository.getCredentials(): Map<String, String>? = withContext(Dispatchers.IO) {
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
suspend fun UserRepository.isGuestLogin(): Boolean = withContext(Dispatchers.IO) {
    getCredentials() == null
}

/**
 * 删除当前用户的登录凭证（游客登出时调用）。
 * 清除凭证后，将用户标记回游客状态（is_guest=1），但不删除 user_profile 记录。
 * 调用方如需删除 user_profile，应显式操作。
 */
suspend fun UserRepository.deleteCredentials() = withContext(Dispatchers.IO) {
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
suspend fun UserRepository.clearAllLocalData() = withContext(Dispatchers.IO) {
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
 * 创建新的用户画像（注册时使用），返回新用户的 sw UUID。
 * 若当前存在游客用户（is_guest=1），则先删除旧的游客画像再创建新画像。
 * 非游客用户 is_guest 设为 0。
 */
suspend fun UserRepository.createUserProfile(): String = withContext(Dispatchers.IO) {
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
