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
import androidx.compose.ui.test.printToString
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import java.net.HttpURLConnection
import java.net.URL

class TrustCenterApiFlowTest {
    @get:Rule
    val compose = createAndroidComposeRule<MainActivity>()

    @Test
    fun confirmedDeletionUsesTheRealApiAndResetsTheCurrentDevelopmentIdentity() {
        assumeTrue("persistent API is not running", apiAvailable())
        leaveRecommendationIfNeeded()
        compose.onNodeWithTag("tab_PROFILE").performClick()
        compose.onNodeWithText("删除我的数据").performClick()
        compose.onAllNodesWithText("确认删除").onFirst().performClick()
        try {
            compose.waitUntil(timeoutMillis = 10_000) {
                compose.onAllNodesWithText("数据已删除；已创建新的本地开发身份")
                    .fetchSemanticsNodes()
                    .isNotEmpty()
            }
        } catch (error: Throwable) {
            throw AssertionError(
                "Deletion did not complete. UI:\n" +
                    compose.onRoot(useUnmergedTree = true).printToString(maxDepth = 8),
                error,
            )
        }
        compose.onNodeWithText("数据已删除；已创建新的本地开发身份").assertExists()
    }

    @Test
    fun qualityDataConsentCanBeGrantedAndWithdrawn() {
        leaveRecommendationIfNeeded()
        compose.onNodeWithTag("tab_PROFILE").performClick()
        if (compose.onAllNodesWithTag("quality_consent_GRANTED").fetchSemanticsNodes().isNotEmpty()) {
            compose.onNodeWithTag("quality_consent_GRANTED").performScrollTo().performClick()
            compose.waitUntil(timeoutMillis = 5_000) {
                compose.onAllNodesWithTag("quality_consent_DENIED").fetchSemanticsNodes().isNotEmpty()
            }
        }
        compose.onNodeWithTag("quality_consent_DENIED").performScrollTo().performClick()
        try {
            compose.waitUntil(timeoutMillis = 5_000) {
                compose.onAllNodesWithTag("quality_consent_GRANTED").fetchSemanticsNodes().isNotEmpty()
            }
        } catch (error: Throwable) {
            throw AssertionError(
                "Consent did not transition to GRANTED. UI:\n" +
                    compose.onRoot(useUnmergedTree = true).printToString(maxDepth = 8),
                error,
            )
        }
        compose.onNodeWithTag("quality_consent_GRANTED").performScrollTo().performClick()
        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithTag("quality_consent_DENIED").fetchSemanticsNodes().isNotEmpty()
        }
    }

    private fun apiAvailable(): Boolean = runCatching {
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

    private fun leaveRecommendationIfNeeded() {
        if (compose.onAllNodesWithTag("back_to_mission").fetchSemanticsNodes().isNotEmpty()) {
            compose.onNodeWithTag("back_to_mission").performClick()
        }
    }
}
