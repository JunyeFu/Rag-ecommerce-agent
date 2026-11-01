package com.ragcommerce.agent

import com.ragcommerce.agent.data.parseMediaEvent
import com.ragcommerce.agent.data.parseSsePayload
import com.ragcommerce.agent.ui.ShoppingAction
import com.ragcommerce.agent.ui.ShoppingReducer
import com.ragcommerce.agent.ui.ShoppingUiState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

class MediaProtocolTest {
    @Test fun mediaSsePreservesAttributesAndUncertainty() {
        val event = parseSsePayload("""
            id: 2
            event: media_interpreted
            data: {"media_id":"media-1","kind":"image","recognized_text":"通勤耳机","category":null,"visible_attributes":["头戴式"],"uncertainties":["无法判断型号"],"supported":true}


        """.trimIndent()).single()
        val value = parseMediaEvent(event.data)
        assertEquals(listOf("头戴式"), value.visible_attributes)
        assertEquals(listOf("无法判断型号"), value.uncertainties)
        val pending = ShoppingReducer.reduce(ShoppingUiState(), ShoppingAction.MediaInterpreted(value, "run-1"))
        assertTrue(pending.showConversation)
        assertFalse(pending.isLoading)
        assertEquals("run-1", pending.mediaSourceRunId)
        assertEquals("通勤耳机", pending.draft)
        assertTrue(ShoppingReducer.reduce(pending, ShoppingAction.ConfirmMedia).isLoading)
    }

    @Test fun nativeVoiceHeaderIsMono16kPcm16() {
        val bytes = VoiceCapture.wavHeader(32000)
        val header = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals("RIFF", String(bytes.copyOfRange(0, 4)))
        assertEquals(32036, header.getInt(4))
        assertEquals(1, header.getShort(22).toInt())
        assertEquals(16000, header.getInt(24))
        assertEquals(16, header.getShort(34).toInt())
        assertEquals(32000, header.getInt(40))
    }
}
