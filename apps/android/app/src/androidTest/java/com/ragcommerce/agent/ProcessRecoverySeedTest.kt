package com.ragcommerce.agent

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToIndex
import androidx.compose.ui.test.performTextInput
import org.junit.Rule
import org.junit.Test

class ProcessRecoverySeedTest {
    @get:Rule
    val compose = createAndroidComposeRule<MainActivity>()

    @Test
    fun persistMissionForExternalProcessRestartVerification() {
        ensureConversation()
        compose.onNodeWithTag("mission_input").performTextInput(EXPECTED_MISSION)
        compose.onNodeWithTag("send_turn").performScrollTo().performClick()
        compose.onNodeWithText(EXPECTED_MISSION).assertExists()
        compose.waitUntil(timeoutMillis = 15_000) {
            compose.onAllNodesWithText("Agent 需要补充一个条件").fetchSemanticsNodes().isNotEmpty()
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
        if (compose.onAllNodesWithTag("tab_TASK").fetchSemanticsNodes().isNotEmpty()) {
            compose.onNodeWithTag("tab_TASK").performClick()
        }
        compose.onNodeWithTag("mission_conversation").performScrollToIndex(2)
        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithTag("mission_input").fetchSemanticsNodes().isNotEmpty()
        }
    }

    companion object {
        const val EXPECTED_MISSION = "processrecoverymission"
    }
}
