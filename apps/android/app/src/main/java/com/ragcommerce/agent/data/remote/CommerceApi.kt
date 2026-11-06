package com.ragcommerce.agent.data.remote

import okhttp3.Call
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.Response
import okhttp3.ResponseBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.Header
import retrofit2.http.Path
import retrofit2.http.POST
import retrofit2.http.Query
import retrofit2.http.PUT
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.channels.trySendBlocking
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import java.io.IOException
import java.util.concurrent.TimeUnit

interface CommerceApi {
    @POST("v1/installations")
    suspend fun install(): ResponseBody

    @GET("v1/threads")
    suspend fun threads(@Header("Authorization") userId: String): ResponseBody

    @PATCH("v1/threads/{threadId}")
    suspend fun organizeThread(@Header("Authorization") userId: String, @Path("threadId") threadId: String, @Body request: RequestBody): ResponseBody

    @GET("v1/threads/{threadId}/messages")
    suspend fun messages(@Header("Authorization") userId: String, @Path("threadId") threadId: String, @Query("offset") offset: Int): ResponseBody

    @PATCH("v1/threads/{threadId}/feedback")
    suspend fun feedback(@Header("Authorization") userId: String, @Path("threadId") threadId: String, @Body request: RequestBody): ResponseBody

    @DELETE("v1/threads/{threadId}/feedback/{key}")
    suspend fun undoFeedback(@Header("Authorization") userId: String, @Path("threadId") threadId: String, @Path("key") key: String, @Query("version") version: Int): ResponseBody

    @GET("v1/products/{productId}")
    suspend fun product(@Header("Authorization") userId: String, @Path("productId") productId: String): ResponseBody

    @GET("v1/variants/{variantId}")
    suspend fun variant(@Header("Authorization") userId: String, @Path("variantId") variantId: String): ResponseBody
    @GET("health")
    suspend fun health(): ResponseBody

    @POST("v1/media")
    suspend fun uploadMedia(
        @Header("Authorization") userId: String,
        @Header("Content-Type") contentType: String,
        @Body content: RequestBody,
    ): ResponseBody

    @POST("v1/threads")
    suspend fun createThread(
        @Header("Authorization") userId: String,
        @Body request: RequestBody,
    ): ResponseBody

    @GET("v1/threads/{threadId}")
    suspend fun thread(
        @Header("Authorization") userId: String,
        @Path("threadId") threadId: String,
    ): ResponseBody

    @PATCH("v1/threads/{threadId}/constraints")
    suspend fun updateThreadConstraints(
        @Header("Authorization") userId: String,
        @Path("threadId") threadId: String,
        @Body request: RequestBody,
    ): ResponseBody

    @PUT("v1/threads/{threadId}/comparison")
    suspend fun updateComparisonSelection(
        @Header("Authorization") userId: String,
        @Path("threadId") threadId: String,
        @Body request: RequestBody,
    ): ResponseBody

    @POST("v1/threads/{threadId}/turns")
    suspend fun createTurn(
        @Header("Authorization") userId: String,
        @Header("Idempotency-Key") idempotencyKey: String,
        @Path("threadId") threadId: String,
        @Body request: RequestBody,
    ): ResponseBody

    @POST("v1/agent-runs/{runId}/decisions")
    suspend fun decide(
        @Header("Authorization") userId: String,
        @Path("runId") runId: String,
        @Body request: RequestBody,
    ): ResponseBody

    @POST("v1/offers/{offerId}/resolve")
    suspend fun resolveOffer(
        @Header("Authorization") userId: String,
        @Path("offerId") offerId: String,
        @Body request: RequestBody,
    ): ResponseBody

    @GET("v1/products/{productId}/offers")
    suspend fun offers(
        @Header("Authorization") userId: String,
        @Path("productId") productId: String,
        @Query("fresh") fresh: Boolean,
    ): ResponseBody

    @GET("v1/lists")
    suspend fun lists(@Header("Authorization") userId: String): ResponseBody

    @POST("v1/lists")
    suspend fun createList(
        @Header("Authorization") userId: String,
        @Body request: RequestBody,
    ): ResponseBody

    @PATCH("v1/lists/{listId}")
    suspend fun patchList(
        @Header("Authorization") userId: String,
        @Path("listId") listId: String,
        @Body request: RequestBody,
    ): ResponseBody

    @POST("v1/cart")
    suspend fun mutateCart(
        @Header("Authorization") userId: String,
        @Body request: RequestBody,
    ): ResponseBody

    @GET("v1/cart")
    suspend fun cart(@Header("Authorization") userId: String): ResponseBody

    @GET("v1/threads/{threadId}/watchers")
    suspend fun watchers(
        @Header("Authorization") userId: String,
        @Path("threadId") threadId: String,
    ): ResponseBody

    @POST("v1/threads/{threadId}/watchers")
    suspend fun createWatcher(
        @Header("Authorization") userId: String,
        @Path("threadId") threadId: String,
        @Body request: RequestBody,
    ): ResponseBody

    @DELETE("v1/users/me/data")
    suspend fun deleteMyData(
        @Header("Authorization") userId: String,
        @Header("X-Deletion-Confirmation") confirmation: String,
    ): ResponseBody
}

class AgentEventStream(
    client: OkHttpClient,
) {
    // SSE is a long-lived subscription, not a 35-second REST request.
    // The inherited idle read timeout still detects a missing heartbeat.
    private val client = client.newBuilder().callTimeout(0, TimeUnit.MILLISECONDS).build()

    fun frames(
        url: String,
        userId: String,
        lastEventId: Long?,
    ): Flow<String> = callbackFlow {
        val request = Request.Builder()
            .url(url)
            .header("Accept", "text/event-stream")
            .header("Authorization", userId)
            .apply { lastEventId?.let { header("Last-Event-ID", it.toString()) } }
            .build()
        val call = client.newCall(request).also { call ->
            call.enqueue(
                object : okhttp3.Callback {
                    override fun onFailure(call: Call, error: java.io.IOException) {
                        close(error)
                    }

                    override fun onResponse(call: Call, response: Response) {
                        try {
                            response.use {
                                check(it.isSuccessful) { "SSE HTTP ${it.code}" }
                                val source = requireNotNull(it.body) { "SSE body missing" }.source()
                                val frame = StringBuilder()
                                while (!source.exhausted()) {
                                    val line = source.readUtf8Line() ?: break
                                    if (line.isEmpty()) {
                                        if (frame.isNotEmpty() && trySendBlocking(frame.toString()).isFailure) break
                                        frame.clear()
                                    } else if (!line.startsWith(":")) {
                                        frame.append(line).append('\n')
                                    }
                                }
                            }
                            close()
                        } catch (error: IOException) {
                            close(error)
                        } catch (error: IllegalStateException) {
                            close(error)
                        } catch (error: IllegalArgumentException) {
                            close(error)
                        }
                    }
                },
            )
        }
        awaitClose { call.cancel() }
    }
}
