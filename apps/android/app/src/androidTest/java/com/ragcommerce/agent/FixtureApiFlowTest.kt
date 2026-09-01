package com.ragcommerce.agent

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToIndex
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
        compose.onNodeWithTag("tab_TASK").performClick()
        ensureConversation()
        compose.onNodeWithTag("mission_input").performTextInput("预算 1000 元的通勤降噪耳机")
        compose.onNodeWithTag("send_turn").performScrollTo().performClick()
        compose.waitUntil(timeoutMillis = 15_000) {
            compose.onAllNodesWithText("Agent 已完成").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("Agent 已完成").assertExists()
        compose.onAllNodesWithText("Aural Audio", substring = true)
            .onFirst()
            .performScrollTo()
            .assertExists()
        compose.onNodeWithTag("connection_ONLINE").assertExists()

        compose.activityRule.scenario.recreate()
        compose.waitUntil(timeoutMillis = 10_000) {
            compose.onAllNodesWithText("Aural Audio", substring = true)
                .fetchSemanticsNodes()
                .isNotEmpty()
        }
    }

    private fun ensureConversation() {
        compose.waitUntil(timeoutMillis = 15_000) {
            compose.onAllNodesWithTag("connection_ONLINE").fetchSemanticsNodes().isNotEmpty() ||
                compose.onAllNodesWithTag("continue_recovered").fetchSemanticsNodes().isNotEmpty()
        }
        if (compose.onAllNodesWithTag("continue_recovered").fetchSemanticsNodes().isNotEmpty()) {
            compose.onNodeWithTag("continue_recovered").performClick()
        }
        if (compose.onAllNodesWithTag("back_to_mission").fetchSemanticsNodes().isNotEmpty()) {
            compose.onNodeWithTag("back_to_mission").performClick()
        }
        compose.onNodeWithTag("mission_conversation").performScrollToIndex(2)
        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithTag("mission_input").fetchSemanticsNodes().isNotEmpty()
        }
    }

    private fun fixtureApiAvailable(): Boolean = runCatching {
        val connection = URL("${BuildConfig.API_BASE_URL}health").openConnection() as HttpURLConnection
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
