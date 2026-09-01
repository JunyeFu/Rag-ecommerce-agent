package com.ragcommerce.agent

import com.ragcommerce.agent.data.parseSsePayload
import com.ragcommerce.agent.data.parseOfferCollection
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
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ShoppingProtocolTest {
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
            product,
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
                "source_ref":"demo:v3:product-1:offer"
              }]
            }
            """.trimIndent(),
        )

        assertEquals(product.id, offers.single().productId)
        assertEquals(product.variantId, offers.single().variantId)
        assertEquals("¥399.00", offers.single().priceText)
        assertEquals("DEMO_FIXTURE", offers.single().verification)
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
              "pending_action":null,
              "candidates":[{
                "product_id":"00000000-0000-5000-8000-000000000003",
                "variant_id":"00000000-0000-5000-8000-000000000004",
                "title":"Aural Audio Quiet 01 演示耳机",
                "fit_summary":"符合演示硬约束",
                "matched_constraints":["预算内"],
                "unmet_constraints":[],
                "risks":["DEMO_FIXTURE"],
                "evidence_refs":["demo:v3:product-1"]
              }]
            }
            """.trimIndent(),
        )

        assertEquals("COMPLETED", snapshot.status)
        assertEquals(19L, snapshot.lastEventId)
        assertEquals("Aural Audio Quiet 01 演示耳机", snapshot.products.single().title)
        assertEquals(listOf("demo:v3:product-1"), snapshot.products.single().evidenceRefs)
    }

    @Test
    fun merchantLinksAreHttpsOnlyAndRequireAHost() {
        assertTrue(isSafeMerchantUrl("https://merchant.example/item/1"))
        assertFalse(isSafeMerchantUrl("http://merchant.example/item/1"))
        assertFalse(isSafeMerchantUrl("javascript:alert(1)"))
        assertFalse(isSafeMerchantUrl("https:///missing-host"))
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
    fun eventStreamSendsOwnerAndLastEventCursorHeaders() = runTest {
        val server = MockWebServer()
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "text/event-stream")
                .setBody("id: 8\nevent: completed\ndata: {\"reason\":\"COMPLETED\"}\n\n"),
        )
        server.start()
        try {
            val payload = AgentEventStream(OkHttpClient()).read(
                server.url("/v1/agent-runs/run/events").toString(),
                "00000000-0000-5000-8000-000000000101",
                7,
            )
            val request = server.takeRequest()
            assertEquals("7", request.getHeader("Last-Event-ID"))
            assertEquals(
                "00000000-0000-5000-8000-000000000101",
                request.getHeader("X-User-ID"),
            )
            assertTrue(payload.contains("event: completed"))
        } finally {
            server.shutdown()
        }
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
