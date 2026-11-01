package com.ragcommerce.agent

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.*
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Rule
import org.junit.Test

/** Host force-stops the isolated package between phases; no injected UI state. */
class EmulatorRecoveryApiTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    @Test fun phase() {
        val phase = InstrumentationRegistry.getArguments().getString("phase")!!
        if (phase.startsWith("seed")) {
            compose.waitUntil(20_000) {
                compose.onAllNodesWithTag("connection_ONLINE").fetchSemanticsNodes().isNotEmpty() ||
                    compose.onAllNodesWithTag("continue_recovered").fetchSemanticsNodes().isNotEmpty()
            }
            if (compose.onAllNodesWithTag("continue_recovered").fetchSemanticsNodes().isNotEmpty()) {
                compose.onNodeWithTag("continue_recovered").performClick()
            }
            if (compose.onAllNodesWithTag("new_mission").fetchSemanticsNodes().isNotEmpty()) {
                compose.onNodeWithTag("new_mission").performClick()
            }
            compose.onNodeWithTag("mission_conversation").performScrollToIndex(2)
            compose.onNodeWithTag("mission_input").performTextInput("recovery-$phase")
            compose.onNodeWithTag("send_turn").performScrollTo().performClick()
        }
        if (phase.startsWith("seed") || phase == "reject" || phase == "approve") {
            compose.waitUntil(20_000) {
                compose.onAllNodesWithText("确认执行操作").fetchSemanticsNodes().isNotEmpty()
            }
            if (phase == "reject" || phase == "approve") {
                compose.onNodeWithText(if (phase == "reject") "取消" else "确认并继续").performClick()
                compose.waitUntil(20_000) {
                    compose.onAllNodesWithText("Agent 已完成").fetchSemanticsNodes().isNotEmpty()
                }
            }
        } else {
            compose.waitUntil(20_000) {
                compose.onAllNodesWithTag("connection_RECOVERED").fetchSemanticsNodes().isNotEmpty()
            }
            compose.onNodeWithText("确认执行操作").assertDoesNotExist()
        }
    }
}
