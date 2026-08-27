package com.ragcommerce.agent

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import java.net.HttpURLConnection
import java.net.URL

class FixtureApiFlowTest {
    @get:Rule
    val compose = createAndroidComposeRule<MainActivity>()

    @Test
    fun textTurnTraversesApiAgentSseAndReturnsEvidence() {
        assumeTrue("fixture API is not running", fixtureApiAvailable())
        compose.onNodeWithTag("tab_GUIDE").performClick()
        compose.onNodeWithTag("mission_input").performTextInput("fixture shopping")
        compose.onNodeWithTag("send_turn").performClick()
        compose.waitUntil(timeoutMillis = 15_000) {
            compose.onAllNodesWithText("fixture response").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("fixture response").assertExists()
        compose.onNodeWithText("fixture:catalog-product-1").assertExists()
        compose.onNodeWithTag("connection_ONLINE").assertExists()
    }

    private fun fixtureApiAvailable(): Boolean = runCatching {
        val connection = URL("http://10.0.2.2:8080/health").openConnection() as HttpURLConnection
        connection.connectTimeout = 700
        connection.readTimeout = 700
        connection.requestMethod = "GET"
        try {
            connection.responseCode == 200
        } finally {
            connection.disconnect()
        }
    }.getOrDefault(false)
}
