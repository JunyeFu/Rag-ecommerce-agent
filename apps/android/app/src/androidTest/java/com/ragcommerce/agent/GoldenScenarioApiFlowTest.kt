package com.ragcommerce.agent

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToIndex
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.printToString
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import java.net.HttpURLConnection
import java.net.URL

class GoldenScenarioApiFlowTest {
    @get:Rule
    val compose = createAndroidComposeRule<MainActivity>()

    @Test
    fun eightGoldenShoppingMissionsCompleteThroughTheRealAndroidApiFlow() {
        assumeTrue("fixture API is not running", fixtureApiAvailable())
        ensureConversation()

        scenarios.forEachIndexed { index, scenario ->
            if (index > 0) {
                compose.onNodeWithTag("mission_conversation").performScrollToIndex(2)
                try {
                    compose.waitUntil(timeoutMillis = 5_000) {
                        compose.onAllNodesWithTag("mission_input").fetchSemanticsNodes().isNotEmpty()
                    }
                } catch (error: Throwable) {
                    throw AssertionError(
                        "${scenario.id} could not return to the Mission composer. UI:\n" +
                            compose.onRoot(useUnmergedTree = true).printToString(maxDepth = 6),
                        error,
                    )
                }
            }
            compose.onNodeWithTag("mission_input").performTextInput(scenario.query)
            compose.onNodeWithTag("send_turn").performScrollTo().performClick()
            try {
                compose.waitUntil(timeoutMillis = 15_000) {
                    compose.onAllNodesWithText("Agent 已完成")
                        .fetchSemanticsNodes()
                        .isNotEmpty()
                }
            } catch (error: Throwable) {
                throw AssertionError(
                    "${scenario.id} did not reach Agent completion. UI:\n" +
                        compose.onRoot(useUnmergedTree = true).printToString(maxDepth = 6),
                    error,
                )
            }
            compose.onNodeWithTag("product_${scenario.productId}")
                .assertExists("${scenario.id} did not render the expected rank-1 product")
            compose.onAllNodesWithText(scenario.expectedTitle, substring = true)
                .onFirst()
                .assertExists()
            compose.onNodeWithTag("connection_ONLINE").assertExists()

            if (scenario.save) {
                compose.onNodeWithTag("save_${scenario.productId}").performClick()
                compose.waitUntil(timeoutMillis = 5_000) {
                    compose.onAllNodesWithText("已保存到 Agent 候选清单")
                        .fetchSemanticsNodes()
                        .isNotEmpty()
                }
            }
            if (scenario.cart) {
                compose.onNodeWithText("加入待购集合").performClick()
                compose.waitUntil(timeoutMillis = 5_000) {
                    compose.onAllNodesWithText("已加入 API 驱动的待购集合")
                        .fetchSemanticsNodes()
                        .isNotEmpty()
                }
                compose.onNodeWithTag("back_to_mission").performClick()
                compose.onNodeWithTag("tab_DECISIONS").performClick()
                compose.onNodeWithTag("merchant_RAG Commerce Demo Store").assertExists()
                compose.onNodeWithTag("tab_TASK").performClick()
            }
            if (compose.onAllNodesWithTag("back_to_mission").fetchSemanticsNodes().isNotEmpty()) {
                compose.onNodeWithTag("back_to_mission").performClick()
            }
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
        compose.waitForIdle()
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

    private data class Scenario(
        val id: String,
        val query: String,
        val productId: String,
        val expectedTitle: String,
        val save: Boolean = false,
        val cart: Boolean = false,
    )

    private companion object {
        val scenarios = listOf(
            Scenario(
                "G01",
                "Nova Mobile Pulse 01 演示手机，预算 2000 元",
                "3c0668b8-1315-54ea-8d88-90c652c9aaf8",
                "Nova Mobile Pulse 01 演示手机",
            ),
            Scenario(
                "G02",
                "Nova Mobile Pulse 02 演示手机，日常通勤",
                "089f04cb-b770-5de2-a756-c4c7aa5b6905",
                "Nova Mobile Pulse 02 演示手机",
                save = true,
                cart = true,
            ),
            Scenario(
                "G03",
                "Arc Compute Forge 01 演示电脑用于开发",
                "747af6fc-c4c8-5a79-9ddb-0ec83e60a1da",
                "Arc Compute Forge 01 演示电脑",
            ),
            Scenario(
                "G04",
                "Arc Compute Forge 02 演示电脑",
                "b800b918-2694-5e58-876b-bbdfaa527766",
                "Arc Compute Forge 02 演示电脑",
                save = true,
            ),
            Scenario(
                "G05",
                "Arc Compute Forge 03 演示电脑",
                "ce106976-76fd-5a1c-8bd2-b4aceb064633",
                "Arc Compute Forge 03 演示电脑",
            ),
            Scenario(
                "G06",
                "Aural Audio Quiet 01 演示耳机，通勤降噪",
                "7677c181-73f4-5369-885f-86f78dd8bd79",
                "Aural Audio Quiet 01 演示耳机",
                cart = true,
            ),
            Scenario(
                "G09",
                "Luma Optics Frame 01 演示相机用于摄影",
                "633d005b-263c-57a5-bb16-5f16aa1553d1",
                "Luma Optics Frame 01 演示相机",
            ),
            Scenario(
                "G10",
                "Luma Optics Frame 02 演示相机",
                "2fbeee34-af5f-5dc5-8bca-36b5c3bc37ca",
                "Luma Optics Frame 02 演示相机",
            ),
        )
    }
}
