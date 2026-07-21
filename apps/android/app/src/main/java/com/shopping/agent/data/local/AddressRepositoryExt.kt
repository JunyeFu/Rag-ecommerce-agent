package com.shopping.agent.data.local

import android.content.ContentValues
import com.shopping.agent.data.local.UserRepository.PaymentSettings
import com.shopping.agent.data.local.UserRepository.ShippingAddress
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

// ═══════════════════════════════════════════════════════
// 收货地址
// ═══════════════════════════════════════════════════════

/**
 * 新增收货地址。
 * 若设为默认地址，则先将该用户其他地址的 is_default 置为 0（保证唯一默认）。
 */
suspend fun UserRepository.addShippingAddress(address: ShippingAddress): Long = withContext(Dispatchers.IO) {
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
suspend fun UserRepository.getShippingAddresses(): List<ShippingAddress> = withContext(Dispatchers.IO) {
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
suspend fun UserRepository.updateShippingAddress(address: ShippingAddress) = withContext(Dispatchers.IO) {
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
suspend fun UserRepository.setDefaultShippingAddress(addressId: Long) = withContext(Dispatchers.IO) {
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
suspend fun UserRepository.deleteShippingAddress(addressId: Long) = withContext(Dispatchers.IO) {
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

/**
 * 获取当前用户的支付设置。若未设置则返回默认值。
 */
suspend fun UserRepository.getPaymentSettings(): PaymentSettings = withContext(Dispatchers.IO) {
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
suspend fun UserRepository.savePaymentSettings(settings: PaymentSettings) = withContext(Dispatchers.IO) {
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
suspend fun UserRepository.getCountryRegion(): String = withContext(Dispatchers.IO) {
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
suspend fun UserRepository.saveCountryRegion(region: String) = withContext(Dispatchers.IO) {
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
