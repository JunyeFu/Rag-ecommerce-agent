package com.ragcommerce.agent

import com.ragcommerce.agent.data.parseSsePayload
import com.ragcommerce.agent.data.remote.AgentEventStream
import com.ragcommerce.agent.ui.MediaAttachmentUi
import com.ragcommerce.agent.ui.ShoppingAction
import com.ragcommerce.agent.ui.ShoppingReducer
import com.ragcommerce.agent.ui.ShoppingUiState
import com.ragcommerce.agent.ui.isSafeMerchantUrl
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
    fun merchantLinksAreHttpsOnlyAndRequireAHost() {
        assertTrue(isSafeMerchantUrl("https://merchant.example/item/1"))
        assertFalse(isSafeMerchantUrl("http://merchant.example/item/1"))
        assertFalse(isSafeMerchantUrl("javascript:alert(1)"))
        assertFalse(isSafeMerchantUrl("https:///missing-host"))
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
