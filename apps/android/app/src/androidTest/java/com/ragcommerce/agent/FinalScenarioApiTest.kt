package com.ragcommerce.agent

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.assertIsOn
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.printToString
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToIndex
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTextReplacement
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeUp
import androidx.compose.ui.test.swipeDown
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Rule
import org.junit.Test

/** Actual MainActivity/DI/API. Host registers the exact paid or zero-model-call slot. */
class FinalScenarioApiTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    @Test fun inspectNativeGalleryAndCancelWithoutUpload() {
        check(InstrumentationRegistry.getArguments().getString("diagnosticProfile") == "read-only")
        compose.waitUntil(20_000) {
            compose.onAllNodesWithTag("tab_TASK").fetchSemanticsNodes().any { !it.config.contains(SemanticsProperties.Disabled) }
        }
        compose.onNodeWithTag("tab_TASK").assertIsEnabled().performClick()
        if (compose.onAllNodesWithTag("back_to_mission").fetchSemanticsNodes().isNotEmpty()) {
            compose.onNodeWithTag("back_to_mission").performClick()
        }
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("mission_input"))
        compose.onNodeWithContentDescription("添加商品图片").performScrollTo().assertIsDisplayed().performClick()
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        automation.waitForIdle(500, 10_000)
        fun inspect(node: android.view.accessibility.AccessibilityNodeInfo) {
            android.util.Log.i("FinalGalleryDiagnostics", "node id=${node.viewIdResourceName} text=${node.text} description=${node.contentDescription} clickable=${node.isClickable}")
            repeat(node.childCount) { index -> node.getChild(index)?.let(::inspect) }
        }
        inspect(requireNotNull(automation.rootInActiveWindow))
        java.io.File(compose.activity.getExternalFilesDir(null), "final-native-gallery.png").outputStream().use {
            requireNotNull(automation.takeScreenshot()).compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it)
        }
        check(automation.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK))
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("mission_input").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("attachment_image").assertDoesNotExist()
        // Open and cancel the real OS picker only; no attachment, upload, Turn or model call.
    }

    private fun selectOwnGalleryImage() {
        compose.onNodeWithContentDescription("添加商品图片").performScrollTo().assertIsDisplayed().performClick()
        val args = InstrumentationRegistry.getArguments()
        val date = java.util.Date(requireNotNull(args.getString("expectedPhotoTimestamp")).toLong() * 1000)
        val description = "Photo taken on " + java.text.SimpleDateFormat("MMM d, yyyy, h:mm:ss a", java.util.Locale.US).format(date)
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        automation.waitForIdle(500, 10_000)
        val matches = mutableListOf<android.view.accessibility.AccessibilityNodeInfo>()
        fun inspect(node: android.view.accessibility.AccessibilityNodeInfo) {
            val actual = node.contentDescription?.toString()?.replace('\u202f', ' ')?.replace('\u00a0', ' ')
            if (node.isClickable && actual == description) matches.add(node)
            repeat(node.childCount) { index -> node.getChild(index)?.let(::inspect) }
        }
        automation.rootInActiveWindow?.let(::inspect)
        android.util.Log.i("FinalGallerySelection", "initial_match_count=${matches.size} expected=$description root_package=${automation.rootInActiveWindow?.packageName}")
        val pickerDeadline = android.os.SystemClock.uptimeMillis() + 10_000
        while (matches.isEmpty() && android.os.SystemClock.uptimeMillis() < pickerDeadline) {
            android.os.SystemClock.sleep(100)
            automation.rootInActiveWindow?.let(::inspect)
        }
        check(matches.size == 1) { "The actual OS gallery must expose exactly one self-owned test image" }
        val bounds = android.graphics.Rect()
        matches.single().getBoundsInScreen(bounds)
        check(!bounds.isEmpty) { "The selected native photo must have visible bounds" }
        val downTime = android.os.SystemClock.uptimeMillis()
        for (action in listOf(android.view.MotionEvent.ACTION_DOWN, android.view.MotionEvent.ACTION_UP)) {
            android.view.MotionEvent.obtain(downTime, android.os.SystemClock.uptimeMillis(), action, bounds.exactCenterX(), bounds.exactCenterY(), 0).also {
                check(automation.injectInputEvent(it, true))
                it.recycle()
            }
        }
        automation.waitForIdle(500, 10_000)
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("attachment_image"))
        compose.onNodeWithTag("attachment_image").performScrollTo().assertIsDisplayed()
    }

    @Test fun inspectNativeImageSelectionWithoutSending() {
        check(InstrumentationRegistry.getArguments().getString("diagnosticProfile") == "read-only")
        compose.waitUntil(20_000) {
            compose.onAllNodesWithTag("tab_TASK").fetchSemanticsNodes().any { !it.config.contains(SemanticsProperties.Disabled) }
        }
        compose.onNodeWithTag("tab_TASK").assertIsEnabled().performClick()
        if (compose.onAllNodesWithTag("back_to_mission").fetchSemanticsNodes().isNotEmpty()) {
            compose.onNodeWithTag("back_to_mission").performClick()
        }
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("mission_input"))
        if (InstrumentationRegistry.getArguments().getString("prepareNewMission") == "true") {
            newMissionFromRecovered("A03")
            compose.onNodeWithTag("mission_input").performScrollTo().performTextReplacement("请根据图片帮我选手机")
        }
        selectOwnGalleryImage()
        compose.onNodeWithText("移除").performScrollTo().assertIsDisplayed().performClick()
        compose.onNodeWithTag("attachment_image").assertDoesNotExist()
        // Real picker selection then local removal only; no send/upload/model call.
    }

    @Test fun inspectNativeVoiceAndCancelWithoutUpload() {
        check(InstrumentationRegistry.getArguments().getString("diagnosticProfile") == "read-only")
        newMissionFromRecovered("N02-VOICE-CANCEL")
        openNativeVoiceDialog()
        compose.onNodeWithTag("voice_hold").assertIsDisplayed()
        compose.onNodeWithTag("voice_send").assertIsNotEnabled()
        compose.onNodeWithTag("voice_cancel").performClick()
        compose.onNodeWithTag("voice_hold").assertDoesNotExist()
        compose.onNodeWithTag("attachment_audio").assertDoesNotExist()
        // Opens the actual permission/dialog and cancels before recording; no upload or Turn.
    }

    @Test fun a02NativeVoiceEditClarifyAndRecommend() {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("microphoneReady") == "true") { "Human microphone participation is required" }
        newMissionFromRecovered("A02")
        compose.onNodeWithTag("mission_input").performScrollTo().performTextReplacement("请听我的购买需求")
        openNativeVoiceDialog()
        // Actual AudioRecord capture. The host prompts the person before starting this method.
        compose.onNodeWithTag("voice_hold").performClick()
        android.util.Log.i("FinalScenario", "A02 microphone recording started; speak the agreed commuting-phone request now")
        android.os.SystemClock.sleep(12_000)
        compose.onNodeWithTag("voice_hold").performClick()
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("voice_preview").fetchSemanticsNodes().isNotEmpty() }
        val capture = requireNotNull(java.io.File(compose.activity.cacheDir, "voice-input").listFiles())
            .filter { it.extension == "wav" }.maxBy { it.lastModified() }
        capture.copyTo(java.io.File(compose.activity.filesDir, "final-A02-native.wav"), overwrite = true)
        compose.onNodeWithTag("voice_send").assertIsEnabled().performClick()
        compose.waitUntil(600_000) { compose.onAllNodesWithTag("media_confirmation_input").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithText("语音转写").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("media_confirmation_input").performScrollTo()
            .performTextReplacement("我想选通勤手机, 预算还没想好, 请先问清楚")
        conversationClick("media_confirm")
        compose.waitUntil(600_000) { compose.onAllNodesWithTag("clarification_quick_replies").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("mission_input").performScrollTo()
            .performTextReplacement("预算2000元，日常通勤")
        conversationClick("send_turn")
        compose.waitUntil(600_000) { compose.onAllNodesWithText("Agent 已完成").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("recommendation_rank_0").assertIsDisplayed()
    }

    @Test fun a03NativeGalleryInterpretationConfirmationAndRecommendation() {
        newMissionFromRecovered("A03")
        compose.onNodeWithTag("mission_input").performScrollTo().performTextReplacement("请根据图片帮我选手机")
        selectOwnGalleryImage()
        conversationClick("send_turn")
        compose.waitUntil(600_000) { compose.onAllNodesWithTag("media_confirmation_input").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("media_confirmation_input").performScrollTo().assertIsDisplayed()
        compose.onNodeWithText("图片线索").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("media_confirmation_input").performScrollTo().performTextReplacement("手机, 预算2000元, 用于日常通勤")
        conversationClick("media_confirm")
        compose.waitUntil(600_000) { compose.onAllNodesWithText("Agent 已完成").fetchSemanticsNodes().isNotEmpty() }
        compose.waitForIdle()
        compose.onNodeWithTag("recommendation_rank_0").assertIsDisplayed()
        compose.onNodeWithText("Agent 已完成").performScrollTo().assertIsDisplayed()
        java.io.File(compose.activity.getExternalFilesDir(null), "final-A03-result.png").outputStream().use {
            compose.onRoot().captureToImage().asAndroidBitmap().compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it)
        }
    }

    @Test fun a05ChangeBudgetBrandAndStartIndependentMission() {
        newMissionFromRecovered("A05")
        compose.onNodeWithTag("mission_input").performScrollTo().performTextReplacement("手机, 预算2500元, 用于日常通勤")
        conversationClick("send_turn")
        compose.waitUntil(600_000) { compose.onAllNodesWithText("Agent 已完成").fetchSemanticsNodes().isNotEmpty() }
        compose.waitForIdle()
        compose.onNodeWithTag("recommendation_rank_0").assertIsDisplayed()
        compose.onNodeWithText("总预算 ¥2500").assertIsDisplayed().performClick()
        compose.onNodeWithTag("mission_edit_input").performTextReplacement("只要 Nova Mobile 品牌手机, 预算1800元")
        compose.onNodeWithText("保存修改").performClick()
        compose.onNodeWithTag("recalculate_mission").performScrollTo().assertIsDisplayed().performClick()
        compose.waitUntil(600_000) { compose.onAllNodesWithText("Agent 已完成").fetchSemanticsNodes().isNotEmpty() }
        compose.waitForIdle()
        compose.onNodeWithTag("recommendation_rank_0").assertIsDisplayed()
        compose.onNodeWithText("总预算 ¥1800").assertIsDisplayed()
        compose.onNodeWithTag("back_to_mission").performClick()
        conversationClick("new_mission")
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("new_mission").fetchSemanticsNodes().isEmpty() }
        compose.onNodeWithTag("recommendation_pager").assertDoesNotExist()
        compose.onNodeWithText("总预算 ¥1800").assertDoesNotExist()
        compose.onNodeWithTag("mission_input").performScrollTo().performTextReplacement("耳机, 预算1000元, 用于日常通勤")
        conversationClick("send_turn")
        compose.waitUntil(600_000) { compose.onAllNodesWithText("Agent 已完成").fetchSemanticsNodes().isNotEmpty() }
        compose.waitForIdle()
        compose.onNodeWithTag("recommendation_rank_0").assertIsDisplayed()
        compose.onNodeWithText("总预算 ¥1000").assertIsDisplayed()
    }

    private fun actualOfferQuantity(offer: String): Int {
        val owner = requireNotNull(InstrumentationRegistry.getArguments().getString("expectedOwner"))
        val connection = java.net.URL("${BuildConfig.API_BASE_URL.trimEnd('/')}/v1/cart").openConnection() as java.net.HttpURLConnection
        connection.connectTimeout = 5000
        connection.readTimeout = 5000
        connection.setRequestProperty("X-User-ID", owner)
        try {
            check(connection.responseCode == 200)
            val items = org.json.JSONObject(connection.inputStream.bufferedReader().use { it.readText() }).getJSONArray("items")
            val matches = (0 until items.length()).map { items.getJSONObject(it) }.filter { it.getString("offer_id") == offer }
            check(matches.size <= 1)
            return if (matches.isEmpty()) 0 else matches.single().getInt("quantity")
        } finally {
            connection.disconnect()
        }
    }

    @Test fun a08RejectThenApproveActualAgentProposal() {
        val offer = requireNotNull(InstrumentationRegistry.getArguments().getString("expectedOffers")).split(',').first()
        resumeRealMission("A08")
        if (compose.onAllNodesWithTag("back_to_mission").fetchSemanticsNodes().isNotEmpty()) {
            compose.onNodeWithTag("back_to_mission").performClick()
        }
        check(actualOfferQuantity(offer) == 0)
        compose.onNodeWithTag("mission_input").performScrollTo().performTextReplacement("请把报价 $offer 以数量 2 加入待购, 等待我审批后执行。")
        conversationClick("send_turn")
        compose.waitUntil(600_000) { compose.onAllNodesWithTag("agent_approval_cancel").fetchSemanticsNodes().isNotEmpty() }
        check(actualOfferQuantity(offer) == 0)
        compose.onNodeWithTag("agent_approval_cancel").assertIsDisplayed().performClick()
        compose.waitUntil(600_000) { compose.onAllNodesWithText("Agent 已完成").fetchSemanticsNodes().isNotEmpty() }
        check(actualOfferQuantity(offer) == 0)
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("mission_input"))
        compose.onNodeWithTag("mission_input").performScrollTo().performTextReplacement("请把报价 $offer 以数量 2 加入待购, 等待我审批后执行。")
        conversationClick("send_turn")
        compose.waitUntil(600_000) { compose.onAllNodesWithTag("agent_approval_confirm").fetchSemanticsNodes().isNotEmpty() }
        check(actualOfferQuantity(offer) == 0)
        compose.onNodeWithTag("agent_approval_confirm").assertIsDisplayed().performClick()
        compose.waitUntil(600_000) { compose.onAllNodesWithText("Agent 已完成").fetchSemanticsNodes().isNotEmpty() }
        check(actualOfferQuantity(offer) == 2)
        compose.onNodeWithTag("agent_approval_confirm").assertDoesNotExist()
        compose.onNodeWithTag("tab_DECISIONS").performClick()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("waiting_quantity_$offer"))
        compose.onNodeWithTag("waiting_quantity_$offer").performScrollTo().assertIsDisplayed().assertTextContains("计划数量 2")
    }

    @Test fun inspectActualCartQuantityReadOnly() {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("diagnosticProfile") == "read-only")
        val offer = requireNotNull(args.getString("expectedOffer"))
        check(actualOfferQuantity(offer) == requireNotNull(args.getString("expectedQuantity")).toInt())
        // Actual owner-scoped API read only; no Turn, proposal, decision or model call.
    }

    @Test fun a09RequoteAndConfirmActualExternalSource() {
        val args = InstrumentationRegistry.getArguments()
        val product = requireNotNull(args.getString("expectedProducts")).split(',')[1]
        val offer = requireNotNull(args.getString("expectedOffers")).split(',')[1]
        resumeRealMission("A09")
        compose.onNodeWithTag("recommendation_pager").performTouchInput { swipeUp() }
        compose.onNodeWithTag("add_plan_$product").assertIsEnabled().performClick()
        compose.onNodeWithTag("confirm_user_action").performClick()
        compose.waitUntil(10_000) { compose.onAllNodesWithText("待购计划已保存").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("back_to_mission").performClick()
        compose.onNodeWithTag("tab_DECISIONS").assertIsEnabled().performClick()
        fun readTime(): String = compose.onNodeWithTag("quote_time_$offer").fetchSemanticsNode().config[SemanticsProperties.Text].joinToString { it.text }
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("requote_$offer"))
        val expectedExpiry = java.time.Instant.parse(requireNotNull(args.getString("expectedExpiredQuote")))
        check(expectedExpiry.isBefore(java.time.Instant.now()))
        compose.onNodeWithTag("quote_time_$offer").assertTextContains("已过期", substring = true)
        compose.onNodeWithTag("open_$offer").performScrollTo().assertIsDisplayed().assertIsNotEnabled()
        compose.onNodeWithText("报价已失效或不可用，请重新询价").performScrollTo().assertIsDisplayed()
        android.util.Log.i("FinalScenario", "A09 natural expiry blocked before explicit requote")
        val before = readTime()
        compose.onNodeWithTag("requote_$offer").performScrollTo().assertIsDisplayed().assertIsEnabled().performClick()
        compose.waitUntil(10_000) { readTime() != before }
        val after = readTime()
        compose.onNodeWithTag("open_$offer").performScrollTo().assertIsDisplayed().assertIsEnabled().performClick()
        compose.onNodeWithText("打开外部来源？").assertIsDisplayed()
        compose.onNodeWithTag("cancel_user_action").performClick()
        check(actualOfferQuantity(offer) == 1)
        compose.onNodeWithTag("open_$offer").assertIsEnabled().performClick()
        compose.onNodeWithTag("confirm_user_action").assertIsEnabled().performClick()
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        fun actualBrowserAddress(): String? {
            val root = automation.rootInActiveWindow ?: return null
            if (root.packageName?.toString() != "com.android.chrome") return null
            return root.findAccessibilityNodeInfosByViewId("com.android.chrome:id/url_bar").singleOrNull()?.text?.toString()
        }
        compose.waitUntil(30_000) { actualBrowserAddress()?.contains("example.com") == true }
        android.util.Log.i("FinalScenario", "A09 quote before=$before after=$after; external address=${actualBrowserAddress()}")
        val bitmap = requireNotNull(automation.takeScreenshot())
        java.io.FileOutputStream(java.io.File(compose.activity.filesDir, "final-A09-external.png")).use {
            bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it)
        }
        bitmap.recycle()
    }

    @Test fun a10CreateActualRecommendationForIsolatedIdentity() {
        newMissionFromRecovered("A10")
        compose.onNodeWithTag("mission_input").performTextReplacement("预算2000元的通勤手机")
        conversationClick("send_turn")
        compose.waitUntil(600_000) { compose.onAllNodesWithText("Agent 已完成").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("recommendation_rank_0").assertIsDisplayed()
    }

    @Test fun a10CreateActualPendingApproval() {
        val offer = requireNotNull(InstrumentationRegistry.getArguments().getString("expectedOffer"))
        resumeRealMission("A10")
        compose.onNodeWithTag("back_to_mission").performClick()
        compose.onNodeWithTag("mission_input").performTextReplacement("把报价 $offer 加入待购计划，数量2；请先征求我的确认，不要直接写入")
        conversationClick("send_turn")
        compose.waitUntil(600_000) { compose.onAllNodesWithTag("agent_approval_confirm").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("agent_approval_confirm").assertIsDisplayed()
        check(actualOfferQuantity(offer) == 0)
    }

    @Test fun a10VerifyExistingPendingApproval() {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("acceptanceProfile") == "real" && args.getString("scenario") == "A10")
        val offer = requireNotNull(args.getString("expectedOffer"))
        compose.waitUntil(30_000) { compose.onAllNodesWithTag("agent_approval_confirm").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("agent_approval_confirm").assertIsDisplayed().assertIsEnabled()
        check(actualOfferQuantity(offer) == 0)
        // Inspect the genuine pending task only; do not create a Turn or approve.
    }

    @Test fun a10OfflineAfterActualProcessStop() {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("acceptanceProfile") == "real" && args.getString("scenario") == "A10")
        compose.waitUntil(30_000) { compose.onAllNodesWithTag("connection_OFFLINE").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("connection_OFFLINE"))
        compose.onNodeWithTag("connection_OFFLINE").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("agent_approval_confirm").assertDoesNotExist()
        compose.onRoot().captureToImage().asAndroidBitmap().let { bitmap ->
            java.io.FileOutputStream(java.io.File(compose.activity.filesDir, "final-A10-offline.png")).use { bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
        }
    }

    @Test fun a10RestorePendingApprovalAndApproveOnce() {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("acceptanceProfile") == "real" && args.getString("scenario") == "A10")
        val offer = requireNotNull(args.getString("expectedOffer"))
        compose.waitUntil(30_000) { compose.onAllNodesWithTag("agent_approval_confirm").fetchSemanticsNodes().isNotEmpty() }
        check(actualOfferQuantity(offer) == 0)
        compose.onNodeWithTag("agent_approval_confirm").assertIsDisplayed().assertIsEnabled().performClick()
        compose.waitUntil(600_000) { compose.onAllNodesWithText("Agent 已完成").fetchSemanticsNodes().isNotEmpty() }
        check(actualOfferQuantity(offer) == 2)
        if (compose.onAllNodesWithTag("back_to_mission").fetchSemanticsNodes().isNotEmpty()) compose.onNodeWithTag("back_to_mission").performClick()
        compose.onNodeWithTag("tab_DECISIONS").assertIsEnabled().performClick()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("waiting_quantity_$offer"))
        compose.onNodeWithTag("waiting_quantity_$offer").performScrollTo().assertIsDisplayed().assertTextContains("计划数量 2")
    }

    @Test fun a10DeleteOnlyIsolatedIdentityThroughUi() {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("acceptanceProfile") == "real" && args.getString("scenario") == "A10")
        check(BuildConfig.APPLICATION_ID == "com.ragcommerce.agent.safetytest")
        val offer = requireNotNull(args.getString("expectedOffer"))
        compose.waitUntil(20_000) { compose.onAllNodesWithTag("continue_recovered").fetchSemanticsNodes().isNotEmpty() || compose.onAllNodesWithTag("tab_PROFILE").fetchSemanticsNodes().any { !it.config.contains(SemanticsProperties.Disabled) } }
        if (compose.onAllNodesWithTag("continue_recovered").fetchSemanticsNodes().isNotEmpty()) {
            compose.onNodeWithTag("connection_RECOVERED").performScrollToIndex(4)
            compose.onNodeWithTag("continue_recovered").performClick()
        }
        if (compose.onAllNodesWithTag("back_to_mission").fetchSemanticsNodes().isNotEmpty()) compose.onNodeWithTag("back_to_mission").performClick()
        compose.onNodeWithTag("tab_PROFILE").assertIsEnabled().performClick()
        compose.onNodeWithTag("screen_我的").performScrollToNode(hasText("删除我的数据"))
        compose.onNodeWithText("删除我的数据").performScrollTo().performClick()
        compose.onNodeWithText("取消").performClick()
        check(actualOfferQuantity(offer) == 2)
        compose.onNodeWithText("删除我的数据").performClick()
        compose.onNodeWithText("确认删除").assertIsEnabled().performClick()
        compose.onNodeWithTag("screen_我的").performScrollToIndex(0)
        compose.waitUntil(10_000) { compose.onAllNodesWithText("数据已删除；已创建新的本地开发身份").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithText("数据已删除；已创建新的本地开发身份").assertIsDisplayed()
        check(actualOfferQuantity(offer) == 0)
    }

    @Test fun inspectCompletedApprovalRecoveryReadOnly() {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("diagnosticProfile") == "read-only")
        val offer = requireNotNull(args.getString("expectedOffer"))
        compose.waitUntil(20_000) {
            compose.onAllNodesWithTag("continue_recovered").fetchSemanticsNodes().isNotEmpty() ||
                compose.onAllNodesWithTag("tab_DECISIONS").fetchSemanticsNodes().any { !it.config.contains(SemanticsProperties.Disabled) }
        }
        if (compose.onAllNodesWithTag("continue_recovered").fetchSemanticsNodes().isNotEmpty()) {
            compose.onNodeWithTag("connection_RECOVERED").performScrollToIndex(4)
            compose.onNodeWithTag("continue_recovered").performClick()
        }
        if (compose.onAllNodesWithTag("back_to_mission").fetchSemanticsNodes().isNotEmpty()) compose.onNodeWithTag("back_to_mission").performClick()
        compose.onNodeWithTag("tab_DECISIONS").assertIsEnabled().performClick()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("waiting_quantity_$offer"))
        compose.onNodeWithTag("waiting_quantity_$offer").performScrollTo().assertIsDisplayed().assertTextContains("计划数量 2")
        check(actualOfferQuantity(offer) == 2)
        // Real server-backed recovery only; no Turn, approval, cart change or deletion.
    }

    @Test fun inspectActualMissionSubmitReadOnly() {
        check(InstrumentationRegistry.getArguments().getString("diagnosticProfile") == "read-only")
        compose.waitUntil(20_000) { compose.onAllNodesWithTag("tab_TASK").fetchSemanticsNodes().any { !it.config.contains(SemanticsProperties.Disabled) } }
        compose.onNodeWithTag("tab_TASK").assertIsEnabled().performClick()
        compose.onNodeWithTag("mission_conversation").performScrollToIndex(1)
        compose.onNodeWithTag("mission_input").performScrollTo().performTextReplacement("预算2000元的通勤手机")
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("send_turn"))
        compose.onNodeWithTag("send_turn").performScrollTo().assertIsDisplayed().assertIsEnabled()
        // Do not send, create a Turn, write business state or call a model.
    }

    @Test fun inspectRestoredFailureReadOnly() {
        check(InstrumentationRegistry.getArguments().getString("diagnosticProfile") == "read-only")
        val initial = compose.onNodeWithTag("tab_TASK").fetchSemanticsNode()
        android.util.Log.i("FinalNativeDiagnostics", "task_before_ready disabled=${initial.config.contains(SemanticsProperties.Disabled)}")
        compose.waitUntil(20_000) {
            compose.onAllNodesWithTag("tab_TASK").fetchSemanticsNodes().any { !it.config.contains(SemanticsProperties.Disabled) }
        }
        compose.onNodeWithTag("tab_TASK").assertIsEnabled().performClick()
        try {
            compose.waitUntil(20_000) { compose.onAllNodesWithText("本次导购未完成，请调整需求或新建任务").fetchSemanticsNodes().isNotEmpty() }
        } catch (error: androidx.compose.ui.test.ComposeTimeoutException) {
            android.util.Log.i("FinalNativeDiagnostics", compose.onRoot().printToString(maxDepth = 5))
            throw error
        }
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("new_mission"))
        compose.onNodeWithTag("new_mission").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("recommendation_pager").assertDoesNotExist()
        java.io.File(compose.activity.getExternalFilesDir(null), "final-failed-restoration.png").outputStream().use {
            compose.onRoot().captureToImage().asAndroidBitmap().compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it)
        }
        // Read the existing FAILED API snapshot only; no click, Turn or model call.
    }

    @Test fun inspectWaitingControlReadOnly() {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("diagnosticProfile") == "read-only")
        val offer = requireNotNull(args.getString("offerId"))
        compose.waitUntil(20_000) { compose.onAllNodesWithTag("connection_RECOVERED").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("connection_RECOVERED").performScrollToIndex(4)
        compose.onNodeWithTag("continue_recovered").performClick()
        compose.onNodeWithTag("back_to_mission").performClick()
        compose.onNodeWithTag("tab_DECISIONS").performClick()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("waiting_remove_$offer"))
        val before = compose.onNodeWithTag("waiting_remove_$offer").fetchSemanticsNode()
        android.util.Log.i("FinalNativeDiagnostics", "remove_before_precise_scroll bounds=${before.boundsInRoot} disabled=${before.config.contains(SemanticsProperties.Disabled)}")
        compose.onNodeWithTag("waiting_remove_$offer").performScrollTo()
        val after = compose.onNodeWithTag("waiting_remove_$offer").fetchSemanticsNode()
        android.util.Log.i("FinalNativeDiagnostics", "remove_after_precise_scroll bounds=${after.boundsInRoot} disabled=${after.config.contains(SemanticsProperties.Disabled)}")
        compose.onNodeWithTag("waiting_remove_$offer").assertIsDisplayed().assertIsEnabled()
        // Inspect only: no click, cart mutation, new Turn or model call.
    }

    private fun openNativeVoiceDialog() {
        compose.onNodeWithContentDescription("添加语音").performScrollTo().performClick()
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        automation.serviceInfo = automation.serviceInfo.apply {
            flags = flags or android.accessibilityservice.AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS
        }
        val deadline = android.os.SystemClock.uptimeMillis() + 10_000
        while (android.os.SystemClock.uptimeMillis() < deadline) {
            val root = automation.rootInActiveWindow
            val grant = root?.findAccessibilityNodeInfosByViewId("com.android.permissioncontroller:id/permission_allow_foreground_only_button")?.singleOrNull()
            if (grant != null) check(grant.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK))
            if (root?.packageName?.toString() == BuildConfig.APPLICATION_ID) break
            android.os.SystemClock.sleep(100)
        }
        // Compose cannot inspect its hierarchy while the OS permission window owns the screen.
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("voice_hold").fetchSemanticsNodes().isNotEmpty() }
    }

    private fun resumeRealMission(case: String) {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("acceptanceProfile") == "real" && args.getString("scenario") == case)
        val failedApprovalSource = case == "A08" && args.getString("priorRunStatus") == "FAILED"
        compose.waitUntil(20_000) {
            compose.onAllNodesWithTag("connection_RECOVERED").fetchSemanticsNodes().isNotEmpty() ||
                (failedApprovalSource && compose.onAllNodesWithText("本次导购未完成，请调整需求或新建任务").fetchSemanticsNodes().isNotEmpty())
        }
        if (compose.onAllNodesWithTag("connection_RECOVERED").fetchSemanticsNodes().isNotEmpty()) {
            compose.onNodeWithTag("connection_RECOVERED").performScrollToIndex(4)
            compose.onNodeWithTag("continue_recovered").performClick()
        }
    }

    @Test fun inspectActualFailedMissionComposerReadOnly() {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("diagnosticProfile") == "read-only" && args.getString("priorRunStatus") == "FAILED")
        resumeRealMission("A08")
        compose.onNodeWithText("本次导购未完成，请调整需求或新建任务").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("mission_input"))
        compose.onNodeWithTag("mission_input").assertIsDisplayed()
        check(actualOfferQuantity(requireNotNull(args.getString("expectedOffers")).split(',')[0]) == 0)
        // Reads the restored FAILED snapshot and actual empty cart, without sending a new Turn.
    }

    private fun conversationClick(tag: String) {
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag(tag))
        compose.onNodeWithTag(tag).performScrollTo().assertIsDisplayed().assertIsEnabled().performClick()
    }

    private fun newMissionFromRecovered(case: String) {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("acceptanceProfile") == "real" && args.getString("scenario") == case)
        compose.waitUntil(20_000) {
            compose.onAllNodesWithTag("continue_recovered").fetchSemanticsNodes().isNotEmpty() ||
                compose.onAllNodesWithTag("tab_TASK").fetchSemanticsNodes().any { !it.config.contains(SemanticsProperties.Disabled) }
        }
        if (compose.onAllNodesWithTag("continue_recovered").fetchSemanticsNodes().isNotEmpty()) {
            compose.onNodeWithTag("connection_RECOVERED").performScrollToIndex(4)
            compose.onNodeWithTag("continue_recovered").performClick()
        } else compose.onNodeWithTag("tab_TASK").assertIsEnabled().performClick()
        if (compose.onAllNodesWithTag("back_to_mission").fetchSemanticsNodes().isNotEmpty()) {
            compose.onNodeWithTag("back_to_mission").performClick()
        }
        compose.onNodeWithTag("mission_conversation").performScrollToIndex(1)
        if (compose.onAllNodesWithTag("new_mission").fetchSemanticsNodes().isNotEmpty()) {
            conversationClick("new_mission")
        }
        compose.waitUntil(10_000) {
            compose.onAllNodesWithTag("mission_input").fetchSemanticsNodes().isNotEmpty() &&
                compose.onAllNodesWithTag("new_mission").fetchSemanticsNodes().isEmpty()
        }
    }

    @Test fun a04DiscoveryFeedbackEndAndPurchase() {
        newMissionFromRecovered("A04")
        conversationClick("explore_start")
        compose.waitUntil(20_000) { compose.onAllNodesWithTag("explore_like_0").fetchSemanticsNodes().isNotEmpty() }
        conversationClick("explore_like_0")
        compose.waitUntil(20_000) { compose.onAllNodesWithText("已记下：感兴趣").fetchSemanticsNodes().isNotEmpty() }
        conversationClick("explore_dislike_1")
        compose.waitUntil(20_000) { compose.onAllNodesWithText("已排除：不再主动推荐").fetchSemanticsNodes().isNotEmpty() }
        conversationClick("explore_next")
        compose.waitUntil(20_000) { compose.onAllNodesWithText("已排除：不再主动推荐").fetchSemanticsNodes().isEmpty() }
        conversationClick("explore_end")
        compose.waitUntil(20_000) { compose.onAllNodesWithText("今天先看到这里").fetchSemanticsNodes().isNotEmpty() }
        conversationClick("new_mission")
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("explore_start").fetchSemanticsNodes().isNotEmpty() }
        conversationClick("explore_start")
        compose.waitUntil(20_000) { compose.onAllNodesWithTag("explore_select_0").fetchSemanticsNodes().isNotEmpty() }
        conversationClick("explore_select_0")
        compose.waitUntil(20_000) { compose.onAllNodesWithTag("clarification_budget").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("mission_input").performScrollTo().performTextReplacement("预算5000元")
        conversationClick("send_turn")
        compose.waitUntil(600_000) { compose.onAllNodesWithText("Agent 已完成").fetchSemanticsNodes().isNotEmpty() }
        compose.waitForIdle()
        compose.onNodeWithTag("recommendation_rank_0").assertIsDisplayed()
        compose.onNodeWithText("Agent 已完成").performScrollTo().assertIsDisplayed()
    }

    @Test fun a07SaveAndManageWaitingCollection() {
        val args = InstrumentationRegistry.getArguments()
        val products = requireNotNull(args.getString("expectedProducts")).split(',')
        val offers = requireNotNull(args.getString("expectedOffers")).split(',')
        resumeRealMission("A07")
        compose.onNodeWithTag("save_${products[0]}").performClick()
        compose.onNodeWithTag("confirm_user_action").performClick()
        compose.waitUntil(10_000) { compose.onAllNodesWithText("已保存候选方案").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("add_plan_${products[0]}").performClick()
        compose.onNodeWithTag("confirm_user_action").performClick()
        compose.waitUntil(10_000) { compose.onAllNodesWithText("待购计划已保存").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("recommendation_pager").performTouchInput { swipeUp() }
        compose.onNodeWithTag("add_plan_${products[1]}").performClick()
        compose.onNodeWithTag("confirm_user_action").performClick()
        compose.waitUntil(10_000) { compose.onAllNodesWithText("待购计划已保存").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("back_to_mission").performClick()
        compose.onNodeWithTag("tab_DECISIONS").performClick()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("waiting_increase_${offers[0]}"))
        compose.onNodeWithTag("waiting_increase_${offers[0]}").performScrollTo().assertIsDisplayed().performClick()
        compose.onNodeWithTag("cancel_user_action").performClick()
        compose.onNodeWithTag("waiting_quantity_${offers[0]}").assertTextContains("计划数量 1")
        compose.onNodeWithTag("waiting_increase_${offers[0]}").performScrollTo().assertIsDisplayed().performClick()
        compose.onNodeWithTag("confirm_user_action").performClick()
        compose.waitUntil(10_000) { compose.onAllNodesWithText("计划数量 2").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("waiting_remove_${offers[1]}"))
        compose.waitUntil(10_000) {
            compose.onAllNodesWithTag("waiting_remove_${offers[1]}").fetchSemanticsNodes()
                .any { !it.config.contains(SemanticsProperties.Disabled) }
        }
        compose.onNodeWithTag("waiting_remove_${offers[1]}").performScrollTo().assertIsDisplayed().assertIsEnabled().performClick()
        compose.onNodeWithTag("confirm_user_action").performClick()
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("waiting_quantity_${offers[1]}").fetchSemanticsNodes().isEmpty() }
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("saved_${products[0]}"))
        compose.onNodeWithTag("saved_${products[0]}").performScrollTo().assertIsDisplayed()
    }

    @Test fun a07VerifyPersistedWaitingCollection() {
        val args = InstrumentationRegistry.getArguments()
        val products = requireNotNull(args.getString("expectedProducts")).split(',')
        val offers = requireNotNull(args.getString("expectedOffers")).split(',')
        resumeRealMission("A07")
        compose.onNodeWithTag("back_to_mission").performClick()
        compose.onNodeWithTag("tab_DECISIONS").performClick()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("waiting_quantity_${offers[0]}"))
        compose.onNodeWithTag("waiting_quantity_${offers[0]}").performScrollTo().assertIsDisplayed().assertTextContains("计划数量 2")
        compose.onNodeWithTag("waiting_quantity_${offers[1]}").assertDoesNotExist()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("saved_${products[0]}"))
        compose.onNodeWithTag("saved_${products[0]}").performScrollTo().assertIsDisplayed()
    }

    @Test fun a06VerticalCandidatesComparisonAndConversation() {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("acceptanceProfile") == "real" && args.getString("scenario") == "A06")
        // Expected IDs come from the existing real API result, not injected UI state.
        val products = requireNotNull(args.getString("expectedProducts")).split(',').take(3)
        check(products.size == 3)
        compose.waitUntil(20_000) { compose.onAllNodesWithTag("connection_RECOVERED").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("connection_RECOVERED").performScrollToIndex(4)
        compose.onNodeWithTag("continue_recovered").performClick()
        compose.onNodeWithTag("recommendation_rank_0").assertIsDisplayed()
        if (args.getString("initialSelection") == products[0]) {
            // Clear the failed first attempt's actual persisted selection via the user control.
            compose.onNodeWithTag("compare_${products[0]}").assertIsOn().performClick()
            compose.waitUntil(10_000) {
                compose.onAllNodesWithText("比较选择已保存").fetchSemanticsNodes().isNotEmpty()
            }
        }
        compose.onNodeWithTag("compare_${products[0]}").performClick()
        compose.onNodeWithTag("compare_${products[0]}").assertIsOn()
        compose.onNodeWithTag("recommendation_pager").performTouchInput { swipeUp() }
        compose.waitUntil(5_000) { compose.onAllNodesWithTag("recommendation_rank_1").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("recommendation_rank_1").assertIsDisplayed()
        compose.onNodeWithTag("compare_${products[1]}").performClick()
        compose.onNodeWithTag("compare_${products[1]}").assertIsOn()
        compose.onNodeWithTag("recommendation_pager").performTouchInput { swipeUp() }
        compose.waitUntil(5_000) { compose.onAllNodesWithTag("recommendation_rank_2").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("recommendation_rank_2").assertIsDisplayed()
        compose.onNodeWithTag("recommendation_pager").performTouchInput { swipeDown() }
        compose.onNodeWithTag("recommendation_rank_1").assertIsDisplayed()
        compose.onNodeWithTag("back_to_mission").performClick()
        compose.onNodeWithTag("tab_DECISIONS").performClick()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("comparison_table"))
        compose.onNodeWithTag("comparison_${products[0]}").assertExists()
        compose.onNodeWithTag("comparison_${products[1]}").assertExists()
        compose.onNodeWithTag("tab_TASK").performClick()
        compose.onNodeWithTag("mission_conversation").assertExists()
        compose.onNodeWithTag("tab_DECISIONS").performClick()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("comparison_table"))
        compose.onNodeWithTag("comparison_${products[0]}").assertExists()
        compose.onNodeWithTag("comparison_${products[1]}").assertExists()
    }

    @Test fun recoverExistingRealResultWithoutAnotherModelCall() {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("acceptanceProfile") == "real" && args.getString("scenario") == "A01-readonly")
        compose.waitUntil(20_000) { compose.onAllNodesWithTag("connection_RECOVERED").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("connection_RECOVERED").performScrollToIndex(4)
        compose.onNodeWithTag("continue_recovered").performClick()
        val product = "3c0668b8-1315-54ea-8d88-90c652c9aaf8"
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("product_$product").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("evidence_product_$product").performClick()
        compose.onNodeWithText("证据来源").assertIsDisplayed()
        compose.onNodeWithText("当前内容来自项目自有演示目录，不是电商平台实时报价。").assertIsDisplayed()
        // Leave the genuine API-backed disclosure visible for host-side capture.
    }

    @Test fun a01RealTextRecommendationAndEvidence() {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("acceptanceProfile") == "real" && args.getString("scenario") == "A01") {
            "Explicit real A01 profile and host-side scenario authorization are required"
        }
        compose.waitUntil(15_000) { compose.onAllNodesWithTag("tab_TASK").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("tab_TASK").performClick()
        compose.waitUntil(15_000) {
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
        if (compose.onAllNodesWithTag("new_mission").fetchSemanticsNodes().isNotEmpty()) {
            compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("new_mission"))
            compose.onNodeWithTag("new_mission").performClick()
        }
        compose.waitUntil(5_000) { compose.onAllNodesWithTag("mission_input").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("mission_input").performTextReplacement("Nova Mobile Pulse 01 演示手机, 预算2000元")
        compose.onNodeWithTag("send_turn").performScrollTo().performClick()
        compose.waitUntil(600_000) { compose.onAllNodesWithText("Agent 已完成").fetchSemanticsNodes().isNotEmpty() }
        val product = "3c0668b8-1315-54ea-8d88-90c652c9aaf8"
        compose.onNodeWithTag("product_$product").assertIsDisplayed()
        compose.onNodeWithTag("evidence_product_$product").performClick()
        compose.onNodeWithText("证据来源").assertIsDisplayed()
        compose.onNodeWithText("当前内容来自项目自有演示目录，不是电商平台实时报价。").assertIsDisplayed()
        compose.onNodeWithText("关闭依据").performClick()
    }
}
