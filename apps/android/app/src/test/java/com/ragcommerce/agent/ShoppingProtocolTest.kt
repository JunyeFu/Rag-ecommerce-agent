package com.ragcommerce.agent

import androidx.datastore.preferences.core.mutablePreferencesOf
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.core.longPreferencesKey
import com.ragcommerce.agent.data.RemoteThreadSnapshot
import com.ragcommerce.agent.data.restoreRunPreferences
import com.ragcommerce.agent.ui.ShoppingMissionUi
import com.ragcommerce.agent.data.parseSsePayload
import com.ragcommerce.agent.data.parseOfferCollection
import com.ragcommerce.agent.data.parseWaitingCart
import com.ragcommerce.agent.data.parseThreadSnapshot
import com.ragcommerce.agent.data.remote.AgentEventStream
import com.ragcommerce.agent.ui.MediaAttachmentUi
import com.ragcommerce.agent.ui.ShoppingAction
import com.ragcommerce.agent.ui.ShoppingReducer
import com.ragcommerce.agent.ui.ShoppingUiState
import com.ragcommerce.agent.ui.isSafeMerchantUrl
import com.ragcommerce.agent.ui.isFreshMerchantResolution
import java.time.Instant
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.flow.toList
import java.util.concurrent.TimeUnit
import java.io.IOException
import okhttp3.mockwebserver.SocketPolicy
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ShoppingProtocolTest {
    @Test fun cartResponseKeepsQuantityAndRejectsMissingContractFields() {
        assertEquals(emptyMap<String, Int>(), parseWaitingCart("""{"items":[]}""").quantities)
        org.junit.Assert.assertThrows(org.json.JSONException::class.java) { parseWaitingCart("{}") }
        org.junit.Assert.assertThrows(org.json.JSONException::class.java) { parseWaitingCart("""{"items":[{"offer_id":"offer-1","quantity":3}]}""") }
    }

    @Test fun globalWaitingCartHasItsOwnProductAndKeepsExpiredQuote() {
        val cart = parseWaitingCart("""{"items":[{"offer_id":"offer-1","quantity":3,
            "product":{"product_id":"p1","variant_id":"v1","title":"原任务演示耳机"},
            "quote":{"offer_id":"offer-1","merchant_name":"演示商家","price_minor":29900,
            "shipping_minor":0,"verification":"DEMO_FIXTURE","collected_at":"2020-01-01T00:00:00Z",
            "expires_at":"2020-01-01T00:15:00Z","source_ref":"demo:quote","availability":"AVAILABLE"}}]}""")
        assertEquals(mapOf("offer-1" to 3), cart.quantities)
        assertEquals("p1", cart.offers.single().productId)
        assertEquals("原任务演示耳机", cart.offers.single().productTitle)
        assertEquals(com.ragcommerce.agent.ui.QuoteState.EXPIRED, cart.offers.single().quoteState)
        assertEquals("2020-01-01T00:15:00Z", cart.offers.single().expiresAt)
    }
    @Test
    fun offerCollectionRestoreKeepsProductIdentityAndDemoBoundary() {
        val product = com.ragcommerce.agent.ui.EvidenceProductUi(
            id = "00000000-0000-5000-8000-000000000003",
            variantId = "00000000-0000-5000-8000-000000000004",
            title = "Aural Audio Quiet 01 演示耳机",
            fitSummary = "符合演示硬约束",
            matchedConstraints = emptyList(),
            unmetConstraints = emptyList(),
            risks = emptyList(),
            evidenceRefs = listOf("demo:v3:product-1"),
        )
        val offers = parseOfferCollection(
            product.id, product.variantId,
            """
            {
              "product_id":"00000000-0000-5000-8000-000000000003",
              "offers":[{
                "offer_id":"00000000-0000-5000-8000-000000000005",
                "merchant_name":"RAG Commerce Demo Store",
                "verification":"DEMO_FIXTURE",
                "availability":"AVAILABLE",
                "price_minor":39900,
                "shipping_minor":0,
                "currency":"CNY",
                "collected_at":"2026-08-31T00:00:00Z",
                "expires_at":"2026-08-31T00:15:00Z",
                "source_ref":"demo:v3:product-1:offer",
                "business_facts":[
                  {"fact_type":"price","summary":"演示报价 ¥399.00; 不可作为成交价","verification_level":"DEMO_FIXTURE","observed_at":"2026-08-31T00:00:00Z","expires_at":"2026-08-31T00:15:00Z","evidence_ref":"demo:v3:product-1:offer"},
                  {"fact_type":"inventory","summary":"演示目录包含此报价; 不代表真实库存","verification_level":"DEMO_FIXTURE","observed_at":"2026-08-31T00:00:00Z","expires_at":"2026-08-31T00:15:00Z","evidence_ref":"demo:v3:product-1:offer"},
                  {"fact_type":"delivery","summary":"未接入真实配送承诺","verification_level":"DEMO_FIXTURE","observed_at":"2026-08-31T00:00:00Z","expires_at":null,"evidence_ref":"demo:v3:product-1:offer"},
                  {"fact_type":"merchant","summary":"演示商家","verification_level":"DEMO_FIXTURE","observed_at":"2026-08-31T00:00:00Z","expires_at":null,"evidence_ref":"demo:v3:product-1:offer"},
                  {"fact_type":"after_sales","summary":"未接入真实售后条款","verification_level":"DEMO_FIXTURE","observed_at":"2026-08-31T00:00:00Z","expires_at":null,"evidence_ref":"demo:v3:product-1:offer"}
                ]
              }]
            }
            """.trimIndent(),
        )

        assertEquals(product.id, offers.single().productId)
        assertEquals(product.variantId, offers.single().variantId)
        assertEquals("¥399.00", offers.single().priceText)
        assertEquals("DEMO_FIXTURE", offers.single().verification)
        assertEquals(com.ragcommerce.agent.ui.QuoteState.EXPIRED, offers.single().quoteState)
        assertFalse(offers.single().mayResolve)
        assertEquals(5, offers.single().businessFacts.size)
        assertNull(offers.single().businessFacts[2].expiresAt)
        assertEquals("演示目录包含此报价; 不代表真实库存", offers.single().businessFacts[1].summary)
    }

    @Test
    fun completedThreadSnapshotRestoresRankedCandidatesAndCursor() {
        val snapshot = parseThreadSnapshot(
            """
            {
              "thread_id":"00000000-0000-5000-8000-000000000001",
              "mission_id":"00000000-0000-5000-8000-000000000002",
              "goal":"预算 1000 元的通勤降噪耳机",
              "status":"COMPLETED",
              "last_event_id":19,
              "active_run_id":"00000000-0000-5000-8000-000000000099",
              "pending_action":null,
              "selected_product_ids":["00000000-0000-5000-8000-000000000003"],
              "mission":{
                "goal":"预算 1000 元的通勤降噪耳机",
                "version":2,
                "items":[{"category":"耳机","quantity":1}],
                "hard_constraints":["预算 1000 元"],
                "soft_preferences":["通勤降噪"],
                "unknowns":[],
                "budget_total_minor":100000,
                "currency":"CNY"
              },
              "recommendation_routes":[
                {"route_type":"STRICT","status":"AVAILABLE","summary":"满足全部可验证硬约束","relaxed_constraints":[],"product_ids":["00000000-0000-5000-8000-000000000003"]},
                {"route_type":"BUDGET","status":"AVAILABLE","summary":"满足硬约束和预算上限","relaxed_constraints":["外观优先"],"product_ids":["00000000-0000-5000-8000-000000000003"]},
                {"route_type":"ALTERNATIVE","status":"UNAVAILABLE","summary":"没有需要放宽的硬约束","relaxed_constraints":[],"product_ids":[]}
              ],
              "candidates":[{
                "product_id":"00000000-0000-5000-8000-000000000003",
                "variant_id":"00000000-0000-5000-8000-000000000004",
                "title":"Aural Audio Quiet 01 演示耳机",
                "fit_summary":"符合演示硬约束",
                "matched_constraints":["预算内"],
                "unmet_constraints":[],
                "risks":["DEMO_FIXTURE"],
                "evidence_refs":["demo:v3:product-1"],
                "recommendation_type":"STRICT",
                "relaxed_constraints":[]
              }]
            }
            """.trimIndent(),
        )

        assertEquals("COMPLETED", snapshot.status)
        assertNull(snapshot.pendingAction)
        assertEquals(19L, snapshot.lastEventId)
        assertEquals("00000000-0000-5000-8000-000000000099", snapshot.activeRunId)
        assertEquals(2, snapshot.mission.version)
        assertEquals("耳机", snapshot.mission.items.single().category)
        assertEquals(
            setOf("00000000-0000-5000-8000-000000000003"),
            snapshot.selectedProductIds,
        )
        assertEquals("Aural Audio Quiet 01 演示耳机", snapshot.products.single().title)
        assertEquals(listOf("demo:v3:product-1"), snapshot.products.single().evidenceRefs)
        assertEquals(3, snapshot.recommendationRoutes.size)
        assertEquals("满足硬约束和预算上限", snapshot.recommendationRoutes[1].summary)
    }

    @Test
    fun merchantLinksAreHttpsOnlyAndRequireAHost() {
        assertTrue(isSafeMerchantUrl("https://merchant.example/item/1"))
        assertFalse(isSafeMerchantUrl("http://merchant.example/item/1"))
        assertFalse(isSafeMerchantUrl("javascript:alert(1)"))
        assertFalse(isSafeMerchantUrl("https:///missing-host"))
    }

    private fun recoverySnapshot(status: String, run: String?, cursor: Long) = RemoteThreadSnapshot(
        activeRunId = run,
        goal = "通勤耳机",
        status = status,
        lastEventId = cursor,
        pendingAction = if (status == "WAITING_APPROVAL") "cart.update" else null,
        products = emptyList(),
        mission = ShoppingMissionUi("通勤耳机", 1, emptyList(), emptyList(), emptyList(), emptyList(), null),
        selectedProductIds = emptySet(),
    )

    @Test
    fun recoveryReplacesOldRunAndHigherCursorAsOnePair() {
        val preferences = mutablePreferencesOf(
            stringPreferencesKey("pending_run_id") to "old-run",
            longPreferencesKey("last_event_id") to 99L,
            stringPreferencesKey("pending_approval_tool") to "list.update",
        )
        restoreRunPreferences(preferences, recoverySnapshot("RUNNING", "new-run", 3L))
        assertEquals("new-run", preferences[stringPreferencesKey("pending_run_id")])
        assertEquals(3L, preferences[longPreferencesKey("last_event_id")])
        assertNull(preferences[stringPreferencesKey("pending_approval_tool")])
    }

    @Test
    fun closedOrEditedMissionClearsPersistedApprovalAndCursor() {
        for (status in listOf("COMPLETED", "FAILED", "IDLE", "WAITING_CLARIFICATION")) {
            val preferences = mutablePreferencesOf(
                stringPreferencesKey("pending_run_id") to "old-run",
                longPreferencesKey("last_event_id") to 99L,
                stringPreferencesKey("pending_approval_tool") to "cart.update",
            )
            restoreRunPreferences(preferences, recoverySnapshot(status, "old-run", 100L))
            assertNull(preferences[stringPreferencesKey("pending_run_id")])
            assertNull(preferences[longPreferencesKey("last_event_id")])
            assertNull(preferences[stringPreferencesKey("pending_approval_tool")])
        }
    }

    @Test
    fun pendingApprovalIsBoundToServerRunAndSurvivesPreferenceReload() {
        val preferences = mutablePreferencesOf()
        restoreRunPreferences(preferences, recoverySnapshot("WAITING_APPROVAL", "server-run", 8L))
        val reloaded = preferences.toPreferences()
        assertEquals("server-run", reloaded[stringPreferencesKey("pending_run_id")])
        assertEquals(8L, reloaded[longPreferencesKey("last_event_id")])
        assertEquals("cart.update", reloaded[stringPreferencesKey("pending_approval_tool")])
    }

    @Test
    fun resolvedMerchantLinkMustStillBeFresh() {
        val now = Instant.parse("2026-08-31T08:00:00Z")
        assertTrue(
            isFreshMerchantResolution(
                "https://merchant.example/item/1",
                "2026-08-31T08:05:00Z",
                now,
            ),
        )
        assertFalse(
            isFreshMerchantResolution(
                "https://merchant.example/item/1",
                "2026-08-31T07:59:59Z",
                now,
            ),
        )
        assertFalse(isFreshMerchantResolution("http://merchant.example/item/1", null, now))
    }

    @Test
    fun sseParserPreservesCursorEventNameAndPublicPayload() {
        val events = parseSsePayload(
            """
            id: 4
            event: message_delta
            data: {"text":"有证据的结果"}

            id: 5
            event: completed
            data: {"reason":"COMPLETED"}

            """.trimIndent(),
        )

        assertEquals(listOf(4L, 5L), events.map { it.id })
        assertEquals("有证据的结果", events.first().data["text"])
        assertEquals("completed", events.last().name)
    }

    @Test
    fun eventStreamSendsCredentialAndLastEventCursorHeaders() = runTest {
        val server = MockWebServer()
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "text/event-stream")
                .setBody("id: 8\nevent: completed\ndata: {\"reason\":\"COMPLETED\"}\n\n"),
        )
        server.start()
        try {
            val payload = AgentEventStream(OkHttpClient()).frames(
                server.url("/v1/agent-runs/run/events").toString(),
                "00000000-0000-5000-8000-000000000101",
                7,
            ).toList().joinToString("\n")
            val request = server.takeRequest()
            assertEquals("7", request.getHeader("Last-Event-ID"))
            assertEquals(
                "00000000-0000-5000-8000-000000000101",
                request.getHeader("Authorization"),
            )
            assertTrue(payload.contains("event: completed"))
        } finally {
            server.shutdown()
        }
    }

    @Test fun sseSubscriptionOutlivesTheRestCallTimeout() = runTest {
        val server = MockWebServer()
        server.enqueue(MockResponse().setBodyDelay(120, TimeUnit.MILLISECONDS)
            .setBody("event: progress\ndata: {\"stage\":\"queued\"}\n\nid: 1\nevent: completed\ndata: {}\n\n"))
        server.start()
        try {
            val client = OkHttpClient.Builder().callTimeout(25, TimeUnit.MILLISECONDS).build()
            val frames = AgentEventStream(client).frames(server.url("/events").toString(), "owner", 0).toList()
            assertEquals(listOf("progress", "completed"), frames.flatMap(::parseSsePayload).map { it.name })
            assertEquals(listOf(0L, 1L), frames.flatMap(::parseSsePayload).map { it.id })
            assertEquals(25, client.callTimeoutMillis)
        } finally { server.shutdown() }
    }

    @Test fun sseBodyDisconnectReportsIoFailureInsteadOfHanging() = runTest {
        val server = MockWebServer()
        server.enqueue(MockResponse().setBody("id: 1\nevent: progress\ndata: {\"stage\":\"" + "x".repeat(512) + "\"}\n\n")
            .setSocketPolicy(SocketPolicy.DISCONNECT_DURING_RESPONSE_BODY))
        server.start()
        try {
            var failure: IOException? = null
            try { AgentEventStream(OkHttpClient()).frames(server.url("/events").toString(), "owner", 0).toList() }
            catch (error: IOException) { failure = error }
            assertTrue(failure != null)
        } finally { server.shutdown() }
    }

    @Test
    fun mediaOnlyTurnIsAllowedAndAttachmentsAreClearedOnlyOnCompletion() {
        val attached = ShoppingReducer.reduce(
            ShoppingUiState(),
            ShoppingAction.AddAttachment(MediaAttachmentUi("content://fixture/1", "image", "one.png")),
        )
        val submitted = ShoppingReducer.reduce(attached, ShoppingAction.SubmitMission)
        val completed = ShoppingReducer.reduce(submitted, ShoppingAction.TurnCompleted())

        assertTrue(submitted.isLoading)
        assertEquals(1, submitted.attachments.size)
        assertFalse(completed.isLoading)
        assertTrue(completed.attachments.isEmpty())
    }

    @Test
    fun approvalRequiresExplicitResolutionState() {
        val pending = ShoppingReducer.reduce(
            ShoppingUiState(isLoading = true),
            ShoppingAction.ApprovalRequired("cart.update"),
        )
        val approved = ShoppingReducer.reduce(pending, ShoppingAction.ResolveApproval(true))

        assertEquals("cart.update", pending.pendingApprovalTool)
        assertFalse(pending.isLoading)
        assertTrue(approved.isLoading)
    }
}
