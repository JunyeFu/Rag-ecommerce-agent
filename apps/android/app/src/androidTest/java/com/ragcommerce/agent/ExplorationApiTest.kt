package com.ragcommerce.agent

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Rule
import org.junit.Test

/** UI generates every transition; host force-stops between discover and purchase. */
class ExplorationApiTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    private fun click(tag: String) {
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag(tag))
        compose.onNodeWithTag(tag).performScrollTo().performClick()
    }

    @Test fun phase() {
        val phase = InstrumentationRegistry.getArguments().getString("phase") ?: "discover"
        compose.waitUntil(30_000) {
            compose.onAllNodesWithTag("connection_ONLINE").fetchSemanticsNodes().isNotEmpty() ||
                compose.onAllNodesWithTag("continue_recovered").fetchSemanticsNodes().isNotEmpty()
        }
        if (compose.onAllNodesWithTag("continue_recovered").fetchSemanticsNodes().isNotEmpty()) {
            compose.onNodeWithTag("continue_recovered").performClick()
            compose.waitUntil(10_000) { compose.onAllNodesWithTag("continue_recovered").fetchSemanticsNodes().isEmpty() }
        }
        if (phase == "discover" || phase == "controls") {
            if (compose.onAllNodesWithTag("new_mission").fetchSemanticsNodes().isNotEmpty()) {
                compose.onNodeWithTag("new_mission").performClick()
            }
            compose.waitUntil(10_000) { compose.onAllNodesWithTag("mission_conversation").fetchSemanticsNodes().isNotEmpty() }
            click("explore_start")
            compose.waitUntil(30_000) { compose.onAllNodesWithTag("explore_like_0").fetchSemanticsNodes().isNotEmpty() }
            if (phase == "controls") {
                click("explore_dislike_0")
                compose.waitUntil(30_000) { compose.onAllNodesWithText("已排除：不再主动推荐").fetchSemanticsNodes().isNotEmpty() }
                click("explore_next")
                compose.waitUntil(30_000) { compose.onAllNodesWithText("已排除：不再主动推荐").fetchSemanticsNodes().isEmpty() }
                click("explore_end")
                compose.waitUntil(30_000) { compose.onAllNodesWithText("今天先看到这里").fetchSemanticsNodes().isNotEmpty() }
                compose.onNodeWithText("今天先看到这里").performScrollTo().assertIsDisplayed()
            } else {
                click("explore_like_0")
                compose.waitUntil(30_000) { compose.onAllNodesWithText("已记下：感兴趣").fetchSemanticsNodes().isNotEmpty() }
                compose.onNodeWithTag("explore_direction_0").performScrollTo()
            }
        } else {
            compose.onNodeWithTag("mission_conversation").performScrollToNode(hasText("已记下：感兴趣"))
            compose.onNodeWithText("已记下：感兴趣").assertExists()
            click("explore_select_0")
            compose.waitUntil(30_000) { compose.onAllNodesWithTag("mission_input").fetchSemanticsNodes().isNotEmpty() }
            compose.onNodeWithTag("mission_input").performScrollTo().performTextInput("预算5000元")
            click("send_turn")
            compose.waitUntil(30_000) { compose.onAllNodesWithTag("recommendation_pager").fetchSemanticsNodes().isNotEmpty() }
            compose.onNodeWithTag("recommendation_pager").assertExists()
        }
        val screenshot = java.io.File(compose.activity.getExternalFilesDir(null), "exploration-$phase.png")
        screenshot.outputStream().use {
            compose.onRoot().captureToImage().asAndroidBitmap().compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it)
        }
    }
}
