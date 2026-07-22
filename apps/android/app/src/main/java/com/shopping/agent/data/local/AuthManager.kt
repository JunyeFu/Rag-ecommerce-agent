package com.shopping.agent.data.local

import android.content.Context
import com.shopping.agent.ShoppingApp
import com.shopping.agent.core.network.NetworkConfig
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

object AuthManager {
    private const val PREFS_NAME = "auth_prefs"
    private const val KEY_TOKEN = "auth_token"

    fun getToken(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getString(KEY_TOKEN, "") ?: ""
    }

    fun setToken(context: Context, token: String) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit().putString(KEY_TOKEN, token).apply()
    }

    fun clearToken(context: Context) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit().remove(KEY_TOKEN).apply()
    }

    @Synchronized
    fun ensureToken(context: Context): String {
        val existing = getToken(context)
        if (existing.isNotBlank()) return existing

        val client = OkHttpClient.Builder()
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(10, TimeUnit.SECONDS)
            .build()
        val url = "${NetworkConfig.BASE_URL}/api/v1/auth/login"
        val body = "{}".toRequestBody("application/json".toMediaType())
        val request = Request.Builder().url(url).post(body).build()
        try {
            val response = client.newCall(request).execute()
            val json = JSONObject(response.body?.string() ?: "{}")
            val token = json.optJSONObject("data")?.optString("token") ?: ""
            if (token.isNotBlank()) {
                setToken(context, token)
            }
            return token
        } catch (e: Exception) {
            return ""
        }
    }
}
