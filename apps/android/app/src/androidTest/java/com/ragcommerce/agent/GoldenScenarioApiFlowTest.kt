package com.ragcommerce.agent

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToIndex
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTextReplacement
import androidx.compose.ui.test.printToString
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import java.net.HttpURLConnection
import java.net.URL

class GoldenScenarioApiFlowTest {
    private val realAcceptance: Boolean
        get() = InstrumentationRegistry.getArguments().getString("acceptanceProfile") == "real"
    private val completionTimeout: Long
        get() = if (realAcceptance) 600_000 else 15_000
    @get:Rule
    val compose = createAndroidComposeRule<MainActivity>()

    @Test
    fun eightGoldenShoppingMissionsCompleteThroughTheRealAndroidApiFlow() {
        if (realAcceptance) {
            check(fixtureApiAvailable()) { "real acceptance backend unavailable; not a skipped PASS" }
        } else {
            assumeTrue("fixture API is not running", fixtureApiAvailable())
        }
        ensureConversation()

        val activeScenarios = if (realAcceptance) scenarios + realAdditionalScenarios else scenarios
        activeScenarios.forEach { scenario ->
            if (compose.onAllNodesWithTag("new_mission").fetchSemanticsNodes().isNotEmpty()) {
                if (compose.onAllNodesWithTag("mission_conversation").fetchSemanticsNodes().isNotEmpty()) {
                    compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("new_mission"))
                }
                compose.onNodeWithTag("new_mission").performClick()
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
            compose.onNodeWithTag("mission_input").performTextReplacement(scenario.query)
            compose.onNodeWithTag("send_turn").performScrollTo().performClick()
            try {
                compose.waitUntil(timeoutMillis = completionTimeout) {
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
            compose.onNodeWithTag("route_STRICT").assertExists()
            compose.onNodeWithTag("route_BUDGET").assertExists()
            compose.onNodeWithTag("route_ALTERNATIVE").assertExists()

            if (scenario.save) {
                compose.onNodeWithTag("save_${scenario.productId}").performClick()
                compose.onNodeWithText("保存候选方案？").assertExists()
                compose.onNodeWithText("确认保存").performClick()
                compose.waitUntil(timeoutMillis = 5_000) {
                    compose.onAllNodesWithText("已保存候选方案")
                        .fetchSemanticsNodes()
                        .isNotEmpty()
                }
            }
            if (scenario.cart) {
                compose.onNodeWithTag("add_plan_${scenario.productId}").performClick()
                compose.onNodeWithText("加入待购计划？").assertExists()
                compose.onNodeWithText("确认加入").performClick()
                compose.waitUntil(timeoutMillis = 5_000) {
                    compose.onAllNodesWithText("待购计划已保存")
                        .fetchSemanticsNodes()
                        .isNotEmpty()
                }
                compose.onNodeWithTag("back_to_mission").performClick()
                compose.onNodeWithTag("tab_DECISIONS").performClick()
                compose.onNodeWithTag("screen_决策").performScrollToIndex(5)
                compose.onNodeWithTag("merchant_RAG Commerce Demo Store").assertExists()
                compose.onNodeWithText("演示观察 · 不会后台提醒").assertDoesNotExist()
                compose.onNodeWithText("降价观察").assertDoesNotExist()
                compose.onNodeWithText("补货观察").assertDoesNotExist()
                compose.onNodeWithTag("tab_TASK").performClick()
            }
        }
    }

    private fun ensureConversation() {
        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithTag("tab_TASK").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithTag("tab_TASK").performClick()
        compose.waitUntil(timeoutMillis = 15_000) {
            compose.onAllNodesWithTag("connection_ONLINE").fetchSemanticsNodes().isNotEmpty() ||
                compose.onAllNodesWithTag("connection_RECOVERED").fetchSemanticsNodes().isNotEmpty()
        }
        if (compose.onAllNodesWithTag("connection_RECOVERED").fetchSemanticsNodes().isNotEmpty()) {
            compose.onNodeWithTag("connection_RECOVERED").performScrollToIndex(4)
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
        val connection = URL("${BuildConfig.API_BASE_URL.trimEnd('/')}/health").openConnection() as HttpURLConnection
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
        // Opt-in real UI profile. Backend Trace/readback and failure records are
        // required separately; these UI assertions alone are not LIVE_E2E evidence.
        val realAdditionalScenarios = listOf(
            Scenario("G07", "Aural Audio Quiet 02 演示耳机", "c9a83ba6-4cd0-51e2-88b8-8d1cbae6d2c4", "Aural Audio Quiet 02", cart = true),
            Scenario("G08", "Aural Audio Quiet 03 演示耳机，请重新核验并刷新报价", "8298eccb-d89b-5f4c-b276-3b94cb4e75a6", "Aural Audio Quiet 03"),
        )
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
