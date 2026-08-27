package com.ragcommerce.agent

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import org.junit.Rule
import org.junit.Test

class ProcessRecoverySeedTest {
    @get:Rule
    val compose = createAndroidComposeRule<MainActivity>()

    @Test
    fun persistMissionForExternalProcessRestartVerification() {
        compose.onNodeWithTag("tab_GUIDE").performClick()
        compose.onNodeWithTag("mission_input").performTextInput(EXPECTED_MISSION)
        compose.onNodeWithTag("send_turn").performClick()
        compose.onNodeWithText(EXPECTED_MISSION).assertExists()
    }

    companion object {
        const val EXPECTED_MISSION = "processrecoverymission"
    }
}
