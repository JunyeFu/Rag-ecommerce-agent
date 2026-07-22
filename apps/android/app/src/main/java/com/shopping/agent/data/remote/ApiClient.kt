package com.shopping.agent.data.remote

import com.shopping.agent.core.network.NetworkConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

object ApiClient {
    private val baseUrl = "${NetworkConfig.BASE_URL}/api/v1"

    private val client: OkHttpClient = NetworkConfig.httpClient

    suspend fun get(path: String, params: Map<String, String> = emptyMap()): JSONObject = withContext(Dispatchers.IO) {
        val url = buildUrl(path, params)
        val request = Request.Builder().url(url).get().build()
        val response = client.newCall(request).execute()
        JSONObject(response.body?.string() ?: "{}")
    }

    suspend fun post(path: String, body: String): JSONObject = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$baseUrl$path")
            .post(body.toRequestBody("application/json".toMediaType()))
            .build()
        val response = client.newCall(request).execute()
        JSONObject(response.body?.string() ?: "{}")
    }

    suspend fun put(path: String, body: String): JSONObject = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$baseUrl$path")
            .put(body.toRequestBody("application/json".toMediaType()))
            .build()
        val response = client.newCall(request).execute()
        JSONObject(response.body?.string() ?: "{}")
    }

    suspend fun delete(path: String, params: Map<String, String> = emptyMap()): JSONObject = withContext(Dispatchers.IO) {
        val url = buildUrl(path, params)
        val request = Request.Builder().url(url).delete().build()
        val response = client.newCall(request).execute()
        JSONObject(response.body?.string() ?: "{}")
    }

    private fun buildUrl(path: String, params: Map<String, String>): String {
        val fullUrl = "$baseUrl$path"
        return if (params.isEmpty()) fullUrl
        else {
            val query = params.entries.joinToString("&") { "${it.key}=${it.value}" }
            "$fullUrl?$query"
        }
    }
}
