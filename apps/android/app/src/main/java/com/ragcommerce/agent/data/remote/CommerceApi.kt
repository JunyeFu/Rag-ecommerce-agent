package com.ragcommerce.agent.data.remote

import okhttp3.Call
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.Response
import okhttp3.ResponseBody
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.Path
import retrofit2.http.POST
import retrofit2.http.Query
import kotlinx.coroutines.suspendCancellableCoroutine

interface CommerceApi {
    @GET("health")
    suspend fun health(): ResponseBody

    @POST("v1/media")
    suspend fun uploadMedia(
        @Header("X-User-ID") userId: String,
        @Header("Content-Type") contentType: String,
        @Body content: RequestBody,
    ): ResponseBody

    @POST("v1/threads")
    suspend fun createThread(
        @Header("X-User-ID") userId: String,
        @Body request: RequestBody,
    ): ResponseBody

    @POST("v1/threads/{threadId}/turns")
    suspend fun createTurn(
        @Header("X-User-ID") userId: String,
        @Header("Idempotency-Key") idempotencyKey: String,
        @Path("threadId") threadId: String,
        @Body request: RequestBody,
    ): ResponseBody

    @POST("v1/agent-runs/{runId}/decisions")
    suspend fun decide(
        @Header("X-User-ID") userId: String,
        @Path("runId") runId: String,
        @Body request: RequestBody,
    ): ResponseBody

    @POST("v1/offers/{offerId}/resolve")
    suspend fun resolveOffer(
        @Header("X-User-ID") userId: String,
        @Path("offerId") offerId: String,
        @Body request: RequestBody,
    ): ResponseBody

    @GET("v1/products/{productId}/offers")
    suspend fun offers(
        @Header("X-User-ID") userId: String,
        @Path("productId") productId: String,
        @Query("fresh") fresh: Boolean,
    ): ResponseBody
}

class AgentEventStream(
    private val client: OkHttpClient,
) {
    suspend fun read(
        url: String,
        userId: String,
        lastEventId: Long?,
    ): String = suspendCancellableCoroutine { continuation ->
        val call = open(url, userId, lastEventId) { result ->
            if (continuation.isActive) continuation.resumeWith(result)
        }
        continuation.invokeOnCancellation { call.cancel() }
    }

    fun open(
        url: String,
        userId: String,
        lastEventId: Long?,
        callback: (Result<String>) -> Unit,
    ): Call {
        val request = Request.Builder()
            .url(url)
            .header("Accept", "text/event-stream")
            .header("X-User-ID", userId)
            .apply { lastEventId?.let { header("Last-Event-ID", it.toString()) } }
            .build()
        return client.newCall(request).also { call ->
            call.enqueue(
                object : okhttp3.Callback {
                    override fun onFailure(call: Call, error: java.io.IOException) {
                        callback(Result.failure(error))
                    }

                    override fun onResponse(call: Call, response: Response) {
                        response.use {
                            if (!it.isSuccessful) {
                                callback(Result.failure(IllegalStateException("SSE HTTP ${it.code}")))
                            } else {
                                val body = it.body
                                if (body == null) {
                                    callback(Result.failure(IllegalStateException("SSE body missing")))
                                } else {
                                    callback(Result.success(body.string()))
                                }
                            }
                        }
                    }
                },
            )
        }
    }
}
