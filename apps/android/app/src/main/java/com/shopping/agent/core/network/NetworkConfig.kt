package com.shopping.agent.core.network

import com.shopping.agent.BuildConfig
import com.shopping.agent.data.remote.AuthInterceptor
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

/**
 * Shared network configuration and HTTP client singleton.
 *
 * Android emulator: http://10.0.2.2:8080
 * Physical device over Wi-Fi: set API_BASE_URL to http://<LAN-IP>:8080
 * Physical device over adb reverse: set API_BASE_URL to http://127.0.0.1:8080
 */
object NetworkConfig {
    val BASE_URL: String = BuildConfig.API_BASE_URL

    /** Shared OkHttpClient - single connection pool, reused across all consumers */
    val httpClient: OkHttpClient = OkHttpClient.Builder()
        .addInterceptor(AuthInterceptor())
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    /** SSE client — readTimeout=0 (streaming), shares pool with httpClient */
    val sseClient: OkHttpClient = httpClient.newBuilder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()

    /** 解析图片 URL：相对路径自动拼接 BASE_URL，绝对路径/空值原样返回 */
    fun resolveImageUrl(url: String?): String? {
        if (url.isNullOrBlank()) return null
        return if (url.startsWith("/")) "$BASE_URL$url" else url
    }

    fun resolveImageUrls(urls: List<String>): List<String> {
        return urls.mapNotNull { resolveImageUrl(it) }
    }
}
