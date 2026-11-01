package com.ragcommerce.agent

import android.graphics.Bitmap
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.After
import org.junit.Rule
import org.junit.Test
import java.io.File
import org.json.JSONObject

/** Explicit fake Provider, real native UI / HTTP / PostgreSQL. No injected ShoppingUiState. */
class DecisionExperienceApiTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    @After fun finalScreen() { shot("final-screen") }

    @Test fun c9AccessibilityLabelsHaveContextAndTouchTargets() {
        fresh()
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("explore_start"))
        listOf("改善生活", "发现新玩法").forEach { label ->
            val node = compose.onNodeWithContentDescription(label)
            node.assertIsDisplayed().assertHasClickAction()
            val bounds = node.getUnclippedBoundsInRoot()
            assertTrue((bounds.bottom - bounds.top).value >= 48f)
        }
        submit("预算500元，推荐通勤降噪耳机")
        val id = visibleProduct()
        val candidate = compose.onNodeWithTag("compare_$id")
        val label = candidate.fetchSemanticsNode().config.getOrNull(SemanticsProperties.ContentDescription).orEmpty().joinToString()
        assertTrue("Comparison checkbox must identify its product", label.startsWith("加入比较 · ") && label.length > 8)
        candidate.assertIsDisplayed().assertHasClickAction().performClick()
        candidate.assertIsOn()
        shot("a11y-candidate-label")
    }

    private fun exists(tag: String) = compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()
    private fun waitTag(tag: String) = compose.waitUntil(30_000) { exists(tag) }
    private fun resumeResult() {
        compose.waitUntil(30_000) { exists("recommendation_pager") || exists("connection_RECOVERED") }
        if (exists("connection_RECOVERED")) {
            compose.onNodeWithTag("connection_RECOVERED").performScrollToNode(hasTestTag("continue_recovered"))
            compose.onNodeWithTag("continue_recovered").performClick()
        }
        waitTag("recommendation_pager")
    }
    private fun conversation(tag: String) {
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag(tag))
        compose.waitUntil(30_000) { compose.onAllNodes(hasTestTag(tag) and isEnabled()).fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag(tag).performClick()
    }
    private fun setup() {
        compose.waitUntil(30_000) {
            exists("back_to_mission") || exists("connection_RECOVERED") ||
                compose.onAllNodes(hasTestTag("tab_TASK") and isEnabled()).fetchSemanticsNodes().isNotEmpty()
        }
        if (exists("tab_TASK")) compose.onNodeWithTag("tab_TASK").performClick()
        compose.waitUntil(30_000) { exists("connection_ONLINE") || exists("connection_RECOVERED") }
        if (exists("connection_RECOVERED")) {
            compose.onNodeWithTag("connection_RECOVERED").performScrollToNode(hasTestTag("continue_recovered"))
            compose.onNodeWithTag("continue_recovered").performClick()
        }
        if (exists("back_to_mission")) compose.onNodeWithTag("back_to_mission").performClick()
        if (exists("tab_TASK")) compose.onNodeWithTag("tab_TASK").performClick()
        waitTag("mission_conversation")
    }
    private fun fresh() {
        setup()
        if (exists("new_mission")) conversation("new_mission")
        waitTag("mission_input")
    }
    private fun submit(goal: String) {
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("mission_input"))
        compose.onNodeWithTag("mission_input").performTextReplacement(goal)
        conversation("send_turn")
        waitTag("recommendation_pager")
        completeTurn()
        compose.waitForIdle()
    }
    private fun completeTurn() {
        compose.waitUntil(30_000) {
            compose.onAllNodesWithText("Agent 已完成").fetchSemanticsNodes().isNotEmpty() ||
                compose.onAllNodesWithText("Agent 未完成", substring = true).fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("Agent 已完成").assertExists("Agent failed; a visible product card is not terminal success")
    }
    private fun prefix(value: String) = SemanticsMatcher("tag starts with $value") {
        it.config.getOrNull(SemanticsProperties.TestTag)?.startsWith(value) == true
    }
    private fun visibleProduct(): String = compose.onAllNodes(prefix("product_")).fetchSemanticsNodes()
        .first { it.boundsInRoot.height > 0 && it.boundsInRoot.width > 0 }
        .config[SemanticsProperties.TestTag].removePrefix("product_")
    private fun fullButton(tag: String) {
        val node = compose.onNodeWithTag(tag)
        node.assertIsDisplayed().assertHasClickAction().assertIsEnabled()
        val bounds = node.getUnclippedBoundsInRoot()
        val root = compose.onNode(isRoot() and hasAnyDescendant(hasTestTag(tag))).getUnclippedBoundsInRoot()
        assertTrue("$tag extends above viewport: $bounds", bounds.top >= root.top)
        assertTrue("$tag extends below viewport: $bounds", bounds.bottom <= root.bottom)
        val visible = node.fetchSemanticsNode().boundsInRoot
        val density = compose.activity.resources.displayMetrics.density
        assertTrue("$tag is clipped by its parent", visible.height + 1 >= (bounds.bottom - bounds.top).value * density)
    }
    private fun shot(label: String) {
        compose.waitForIdle()
        val args = InstrumentationRegistry.getArguments()
        val scale = args.getString("uxScale") ?: "1"
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        automation.waitForIdle(250, 3_000)
        val deviceBitmap = requireNotNull(automation.takeScreenshot())
        File(compose.activity.getExternalFilesDir(null), "ux-$scale-$label-device.png").outputStream().use {
            deviceBitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
        }
        deviceBitmap.recycle()
    }

    private fun decisionControl(tag: String, click: Boolean = true) {
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag(tag))
        compose.onNodeWithTag(tag).performScrollTo()
        fullButton(tag)
        if (click) compose.onNodeWithTag(tag).performClick()
    }
    private fun saveCandidate(): String {
        val id = visibleProduct()
        fullButton("save_$id"); compose.onNodeWithTag("save_$id").performClick()
        compose.onNodeWithTag("confirm_user_action").performScrollTo()
        fullButton("confirm_user_action"); compose.onNodeWithTag("confirm_user_action").performClick()
        compose.waitUntil(15_000) { !exists("confirm_user_action") }
        compose.waitUntil(15_000) { compose.onAllNodesWithText("已保存候选方案").fetchSemanticsNodes().isNotEmpty() }
        return id
    }
    private fun decisions() {
        if (exists("back_to_mission")) compose.onNodeWithTag("back_to_mission").performClick()
        compose.onNodeWithTag("tab_DECISIONS").performClick()
    }
    private fun savedComparisonContext() = File(compose.activity.getExternalFilesDir(null),
        "saved-comparison-${InstrumentationRegistry.getArguments().getString("uxScale")}.json")
    private fun checkSavedComparison(ids: List<String>, label: String) {
        decisionControl("saved_compare_start", click = false)
        compose.onNodeWithTag("saved_compare_count").assertTextEquals("已选 ${ids.size}/4")
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasText("已保存商品比较"))
        compose.onNodeWithText("已保存商品比较").performScrollTo().assertIsDisplayed()
        shot("$label-heading")
        ids.forEach { id ->
            compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("saved_compare_product_$id"))
            compose.onNodeWithTag("saved_compare_product_$id").assert(hasAnyDescendant(hasTestTag("evidence_saved_compare_$id")))
            compose.onNodeWithTag("saved_compare_product_$id").assert(hasAnyDescendant(hasText("演示报价", substring = true)))
            decisionControl("evidence_saved_compare_$id")
            compose.onAllNodesWithText("证据记录", substring = true).onFirst().assertExists()
            compose.onAllNodesWithText("有效至", substring = true).onFirst().assertExists()
            fullButton("evidence_close"); compose.onNodeWithTag("evidence_close").performClick()
        }
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasText("同口径规格与取舍"))
        compose.onNodeWithText("同口径规格与取舍").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasText("续航"))
        compose.onNodeWithText("续航").performScrollTo().assertIsDisplayed()
        shot("$label-facts")
    }

    @Test fun c8SavedBatchCompareAcrossMissionsWithoutChangingTask() {
        fresh(); submit("预算1000元演示耳机，保存比较任务一")
        val first = saveCandidate()
        compose.onNodeWithTag("recommendation_pager").performScrollToIndex(1)
        val second = saveCandidate(); assertNotEquals(first, second)
        fresh(); submit("预算1000元演示耳机，保存比较任务二")
        compose.onNodeWithTag("recommendation_pager").performScrollToIndex(2)
        val third = saveCandidate(); assertTrue(third !in listOf(first, second))
        val earbuds = listOf(first, second, third)
        fresh(); submit("预算5000元办公电脑，至少16GB内存，保存比较隔离任务")
        val computer = saveCandidate()
        compose.onNodeWithTag("compare_$computer").performClick()
        compose.onNodeWithTag("recommendation_pager").performScrollToIndex(1)
        val otherComputer = saveCandidate()
        compose.onNodeWithTag("compare_$otherComputer").performClick()
        decisions()
        if (exists("saved_compare_clear")) decisionControl("saved_compare_clear")
        decisionControl("saved_compare_pick_$first")
        decisionControl("saved_compare_pick_$computer")
        decisionControl("saved_compare_start")
        compose.waitUntil(15_000) { exists("decision_error") }
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("decision_error"))
        compose.onNodeWithTag("decision_error").assertTextContains("请选同一品类", substring = true)
        shot("c8-mixed-category-explained")
        decisionControl("saved_compare_clear")
        (earbuds + computer).forEach { decisionControl("saved_compare_pick_$it") }
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("saved_compare_pick_$otherComputer"))
        compose.onNodeWithTag("saved_compare_pick_$otherComputer").assertIsNotEnabled()
        decisionControl("saved_compare_clear")
        earbuds.forEach { decisionControl("saved_compare_pick_$it") }
        decisionControl("saved_compare_start")
        compose.waitUntil(15_000) { exists("saved_compare_result") }
        checkSavedComparison(earbuds, "c8-three-saved")
        // Saved-detail reads and comparison must not replace this computer Mission.
        decisionControl("open_saved_$first")
        waitTag("saved_detail_list"); compose.onNodeWithText("关闭").performClick()
        compose.onNodeWithTag("tab_TASK").performClick()
        conversation("reopen_recommendations")
        assertEquals(otherComputer, visibleProduct())
        compose.onNodeWithTag("compare_$otherComputer").assertIsOn()
        shot("c8-current-task-retained")
        fresh(); decisions()
        checkSavedComparison(earbuds, "c8-blank-task-retained")
        savedComparisonContext().writeText(JSONObject().put("ids", org.json.JSONArray(earbuds)).toString())
    }

    @Test fun c8bSavedBatchComparisonAfterProcessRestart() {
        val values = JSONObject(savedComparisonContext().readText()).getJSONArray("ids")
        val ids = (0 until values.length()).map { values.getString(it) }
        setup(); decisions()
        compose.waitUntil(15_000) { exists("saved_compare_result") }
        checkSavedComparison(ids, "c8b-restored")
        ids.forEach { id ->
            compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("saved_compare_pick_$id"))
            compose.onNodeWithTag("saved_compare_pick_$id").assertIsOn()
        }
    }

    @Test fun c8cRemovingComparedSavedItemInvalidatesResultAndClearIsReversible() {
        val values = JSONObject(savedComparisonContext().readText()).getJSONArray("ids")
        val ids = (0 until values.length()).map { values.getString(it) }
        setup(); decisions()
        decisionControl("open_saved_${ids.first()}")
        waitTag("saved_detail_list")
        compose.onNodeWithTag("saved_detail_list").performScrollToNode(hasText("移出保存"))
        compose.onNodeWithText("移出保存").performScrollTo().performClick()
        compose.onNodeWithText("确认移出保存").performScrollTo().performClick()
        compose.waitUntil(15_000) { !exists("saved_detail_list") }
        decisionControl("saved_compare_start", click = false)
        compose.onNodeWithTag("saved_compare_count").assertTextEquals("已选 2/4")
        compose.onNodeWithTag("saved_compare_result").assertDoesNotExist()
        decisionControl("saved_compare_start")
        compose.waitUntil(15_000) { exists("saved_compare_result") }
        checkSavedComparison(ids.drop(1), "c8c-two-after-removal")
        decisionControl("saved_compare_clear")
        compose.onNodeWithTag("saved_compare_count").assertTextEquals("已选 0/4")
        compose.onNodeWithTag("saved_compare_start").assertIsNotEnabled()
        shot("c8c-cleared")
    }

    @Test fun c8dClearedComparisonStaysClearedAfterRestart() {
        setup(); decisions()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("saved_compare_count"))
        compose.onNodeWithTag("saved_compare_count").assertTextEquals("已选 0/4")
        compose.onNodeWithTag("saved_compare_result").assertDoesNotExist()
        val values = JSONObject(savedComparisonContext().readText()).getJSONArray("ids")
        (1 until values.length()).forEach { index ->
            val id = values.getString(index)
            compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("saved_compare_pick_$id"))
            compose.onNodeWithTag("saved_compare_pick_$id").assertIsOff()
        }
        shot("c8d-clear-persisted-saved-retained")
    }

    @Test fun c1CandidateQuestionExclusionAndUndo() {
        fresh(); submit("预算500元通勤耳机，续航重要")
        compose.onNodeWithTag("recommendation_pager").performScrollToIndex(1)
        compose.waitForIdle()
        compose.onNodeWithTag("recommendation_rank_1").assertIsDisplayed()
        val original = visibleProduct()
        val title = compose.onAllNodes(hasText("演示耳机", substring = true) and hasAnyAncestor(hasTestTag("product_$original")), useUnmergedTree = true)
            .fetchSemanticsNodes().first().config[SemanticsProperties.Text].joinToString { it.text }
        fullButton("discuss_$original"); compose.onNodeWithTag("discuss_$original").performClick()
        compose.onNodeWithTag("candidate_feedback_input").performTextReplacement("它的续航记录是什么？")
        compose.onNodeWithText("准备追问").performClick()
        waitTag("mission_conversation")
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("mission_input"))
        compose.onNodeWithTag("mission_input").assertTextContains("针对【$title】", substring = true)
        shot("c1-candidate-question")
        conversation("send_turn"); waitTag("recommendation_pager"); completeTurn()
        compose.onNodeWithTag("recommendation_pager").performScrollToIndex(1)
        compose.waitForIdle()
        compose.onNodeWithTag("recommendation_rank_1").assertIsDisplayed()
        val target = visibleProduct()
        compose.onNodeWithTag("discuss_$target").performClick()
        compose.onNodeWithTag("candidate_exclude").performClick()
        compose.onNodeWithTag("candidate_category_scope").assertIsOff()
        compose.onNodeWithTag("candidate_feedback_input").performTextReplacement("第二款太重，但保留续航要求")
        shot("c1-explicit-scope")
        compose.onNodeWithText("确认排除").performClick()
        waitTag("mission_conversation")
        conversation("recalculate_mission"); waitTag("recommendation_pager"); completeTurn()
        repeat(3) { page ->
            assertNotEquals(target, visibleProduct())
            if (page < 2) { compose.onNodeWithTag("recommendation_pager").performTouchInput { swipeUp() }; compose.waitForIdle() }
        }
        compose.onNodeWithTag("back_to_mission").performClick()
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasText("撤销排除"))
        compose.onNodeWithText("撤销排除").performClick()
        conversation("recalculate_mission"); waitTag("recommendation_pager"); completeTurn()
        shot("c1-undone")
    }

    @Test fun c2VerticalCandidatesComparisonAndReturn() {
        fresh(); submit("预算5000元办公电脑，必须至少16GB内存")
        val first = visibleProduct()
        fullButton("compare_$first"); compose.onNodeWithTag("compare_$first").performClick()
        compose.onNodeWithTag("recommendation_pager").performTouchInput { swipeUp() }
        compose.waitForIdle()
        val second = visibleProduct(); assertNotEquals(first, second)
        fullButton("discuss_$second"); fullButton("compare_$second")
        compose.onNodeWithTag("compare_$second").performClick()
        shot("c2-secondary-selected")
        compose.onNodeWithTag("recommendation_pager").performTouchInput { swipeUp() }
        compose.waitForIdle(); assertNotEquals(second, visibleProduct())
        shot("c2-tertiary")
        compose.onNodeWithTag("recommendation_pager").performTouchInput { swipeDown() }
        compose.waitForIdle(); assertEquals(second, visibleProduct())
        compose.onNodeWithTag("back_to_mission").performClick()
        compose.onNodeWithTag("tab_DECISIONS").performClick()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasText("同口径规格与取舍"))
        compose.onNodeWithTag("comparison_$first").assert(hasAnyDescendant(hasText("¥", substring = true)))
        compose.onNodeWithTag("comparison_$second").assert(hasAnyDescendant(hasText("¥", substring = true)))
        compose.onNodeWithText("同口径规格与取舍").assertIsDisplayed()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasText("内存"))
        compose.onAllNodesWithText("16GB", substring = true).onFirst().assertExists()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasText("存储"))
        compose.onAllNodesWithText("1TB SSD", substring = true).onFirst().assertExists()
        shot("c2-facts-comparison")
        compose.onNodeWithTag("tab_TASK").performClick()
        conversation("reopen_recommendations")
        assertEquals(second, visibleProduct())
        compose.onNodeWithTag("compare_$second").assertIsOn()
        shot("c2-page-retained")
    }

    @Test fun c3NoMatchNeedsExplicitConstraintEdit() {
        fresh(); submit("预算500元耳机，必须续航至少100小时")
        compose.onNodeWithTag("recommendation_controls").performScrollToNode(hasText("编辑要求，再次检索"))
        compose.onNodeWithText("编辑要求，再次检索").performClick()
        compose.onNodeWithTag("mission_edit_input").assertTextContains("100小时", substring = true)
        shot("c3-original-requirements")
        compose.onNodeWithTag("mission_edit_input").performTextReplacement("预算500元耳机，续航重要")
        compose.onNodeWithText("保存修改").performClick()
        compose.onNodeWithTag("recommendation_controls").performScrollToNode(hasTestTag("recalculate_mission"))
        compose.onNodeWithTag("recalculate_mission").performClick()
        waitTag("recommendation_pager")
        completeTurn()
        shot("c3-adjusted-recommendation")
    }

    @Test fun c4SavedFactsContinueRemoveAndWaitingCart() {
        fresh(); submit("预算1000元演示耳机")
        val product = visibleProduct()
        fullButton("save_$product"); compose.onNodeWithTag("save_$product").performClick()
        compose.onNodeWithTag("confirm_user_action").performClick()
        compose.waitUntil(15_000) { compose.onAllNodesWithText("已保存候选方案").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("back_to_mission").performClick()
        compose.onNodeWithTag("tab_DECISIONS").performClick()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("open_saved_$product"))
        compose.onNodeWithTag("open_saved_$product").performClick()
        waitTag("saved_detail_list")
        compose.onNodeWithTag("saved_detail_list").performScrollToNode(hasText("新建任务继续选购"))
        shot("c4-saved-facts")
        compose.onNodeWithText("加入待购").performScrollTo().performClick()
        compose.onNodeWithTag("confirm_user_action").performClick()
        compose.waitUntil(15_000) { !exists("confirm_user_action") }
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasText("计划数量 1"))
        compose.onNodeWithText("计划数量 1").performScrollTo().assertIsDisplayed()
        shot("c4-waiting-quantity")
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("open_saved_$product"))
        compose.onNodeWithTag("open_saved_$product").performClick()
        waitTag("saved_detail_list")
        compose.onNodeWithTag("saved_detail_list").performScrollToNode(hasText("新建任务继续选购"))
        compose.onNodeWithText("新建任务继续选购").performScrollTo().performClick()
        waitTag("mission_conversation")
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("mission_input"))
        compose.onNodeWithTag("mission_input").assertTextContains("想进一步比较和选购", substring = true)
        shot("c4-continue-draft")
        compose.onNodeWithTag("tab_DECISIONS").performClick()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("open_saved_$product"))
        compose.onNodeWithTag("open_saved_$product").performClick()
        waitTag("saved_detail_list")
        compose.onNodeWithTag("saved_detail_list").performScrollToNode(hasText("移出保存"))
        compose.onNodeWithText("移出保存").performScrollTo().performClick()
        compose.onNodeWithText("确认移出保存").performScrollTo().performClick()
        compose.waitUntil(15_000) { !exists("open_saved_$product") }
        shot("c4-removed")
    }

    private fun cartContextFile() = File(compose.activity.getExternalFilesDir(null),
        "cart-context-${InstrumentationRegistry.getArguments().getString("uxScale")}.json")

    private fun waiting(offer: String, quantity: Int) {
        if (exists("back_to_mission")) compose.onNodeWithTag("back_to_mission").performClick()
        compose.onNodeWithTag("tab_DECISIONS").performClick()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("waiting_quantity_$offer"))
        compose.onNodeWithTag("waiting_quantity_$offer").performScrollTo().assertTextEquals("计划数量 $quantity")
        compose.onNodeWithText("待购计划为空").assertDoesNotExist()
    }

    private fun cartButton(tag: String) {
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag(tag))
        compose.onNodeWithTag(tag).performScrollTo()
        fullButton(tag)
        compose.onNodeWithTag(tag).performClick()
    }

    private fun waitForCartReadback() {
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasText("待购计划"))
        compose.onNodeWithTag("screen_决策").performTouchInput { swipeUp() }
        compose.waitUntil(15_000) { compose.onAllNodes(prefix("waiting_quantity_")).fetchSemanticsNodes().isNotEmpty() }
    }

    private fun openMission(goal: String) {
        compose.onNodeWithTag("tab_TASK").performClick()
        if (exists("back_to_mission")) compose.onNodeWithTag("back_to_mission").performClick()
        conversation("task_history")
        waitTag("task_history_list")
        compose.onNodeWithTag("task_history_list").performScrollToNode(hasText(goal))
        val row = prefix("history_") and hasAnyDescendant(hasText(goal))
        compose.onNode(hasText("继续任务") and hasAnyAncestor(row)).performScrollTo().performClick()
        compose.waitUntil(15_000) { !exists("task_history_list") }
        resumeResult()
    }

    @Test fun c7WaitingCartAcrossNewAndOtherMissions() {
        val marker = System.currentTimeMillis().toString().takeLast(7)
        val earbudGoal = "预算1000元演示耳机，跨任务待购$marker"
        val computerGoal = "预算5000元办公电脑，至少16GB内存，跨任务$marker"
        fresh(); submit(earbudGoal)
        val product = visibleProduct()
        compose.onNodeWithTag("save_$product").performClick()
        compose.onNodeWithTag("confirm_user_action").performClick()
        compose.waitUntil(15_000) { compose.onAllNodesWithText("已保存候选方案").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("back_to_mission").performClick()
        compose.onNodeWithTag("tab_DECISIONS").performClick()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("open_saved_$product"))
        compose.onNodeWithTag("open_saved_$product").performClick()
        waitTag("saved_detail_list")
        compose.onNodeWithTag("saved_detail_list").performScrollToNode(hasText("加入待购"))
        compose.onNodeWithText("加入待购").performScrollTo().performClick()
        compose.onNodeWithTag("confirm_user_action").performClick()
        compose.waitUntil(15_000) { !exists("confirm_user_action") }
        waitForCartReadback()
        compose.onNodeWithTag("screen_决策").performScrollToNode(prefix("waiting_quantity_"))
        val offer = compose.onAllNodes(prefix("waiting_quantity_")).fetchSemanticsNodes().single()
            .config[SemanticsProperties.TestTag].removePrefix("waiting_quantity_")
        waiting(offer, 1)
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("waiting_product_$offer"))
        val title = compose.onNodeWithTag("waiting_product_$offer").fetchSemanticsNode().config[SemanticsProperties.Text].joinToString("")
        assertTrue(title.contains("耳机"))

        // ContinueSaved is a different reset path from the ordinary new-Mission button.
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("open_saved_$product"))
        compose.onNodeWithTag("open_saved_$product").performClick()
        waitTag("saved_detail_list")
        compose.onNodeWithTag("saved_detail_list").performScrollToNode(hasText("新建任务继续选购"))
        compose.onNodeWithText("新建任务继续选购").performScrollTo().performClick()
        waitTag("mission_conversation")
        waiting(offer, 1)
        shot("c7-continued-task-cart")

        compose.onNodeWithTag("tab_TASK").performClick()
        submit(computerGoal)
        compose.onAllNodesWithText("演示电脑", substring = true).onFirst().assertExists()
        waiting(offer, 1)
        cartButton("waiting_increase_$offer")
        compose.onNodeWithTag("confirm_user_action").performClick()
        compose.waitUntil(15_000) { compose.onAllNodesWithText("计划数量 2").fetchSemanticsNodes().isNotEmpty() }
        waiting(offer, 2)
        shot("c7-other-category-cart")
        openMission(earbudGoal); waiting(offer, 2)
        openMission(computerGoal); waiting(offer, 2)
        cartContextFile().writeText(JSONObject().put("offer_id", offer).put("product_id", product)
            .put("title", title).put("computer_goal", computerGoal).put("earbud_goal", earbudGoal).toString())
        shot("c7-switched-back-cart")
    }

    @Test fun c7bWaitingCartAfterProcessRestart() {
        val context = JSONObject(cartContextFile().readText())
        val offer = context.getString("offer_id")
        setup()
        waiting(offer, 2)
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("waiting_product_$offer"))
        compose.onNodeWithTag("waiting_product_$offer").assertTextEquals(context.getString("title"))
        shot("c7b-other-task-restart-title")
        cartButton("waiting_increase_$offer")
        fullButton("cancel_user_action"); compose.onNodeWithTag("cancel_user_action").performClick()
        waiting(offer, 2)
        cartButton("waiting_increase_$offer")
        fullButton("confirm_user_action"); compose.onNodeWithTag("confirm_user_action").performClick()
        compose.waitUntil(15_000) { compose.onAllNodesWithText("计划数量 3").fetchSemanticsNodes().isNotEmpty() }
        waiting(offer, 3)
        compose.onNodeWithTag("tab_TASK").performClick()
        conversation("new_mission")
        waiting(offer, 3)
        shot("c7b-blank-task-before-restart")
    }

    @Test fun c7cWaitingCartWithoutActiveMissionAfterRestart() {
        val context = JSONObject(cartContextFile().readText())
        val offer = context.getString("offer_id")
        setup()
        assertEquals("", compose.onNodeWithTag("mission_input").fetchSemanticsNode().config[SemanticsProperties.EditableText].text)
        waiting(offer, 3)
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("waiting_product_$offer"))
        compose.onNodeWithTag("waiting_product_$offer").assertTextEquals(context.getString("title"))
        shot("c7c-no-active-task-restart-title")
        cartButton("waiting_decrease_$offer")
        fullButton("confirm_user_action"); compose.onNodeWithTag("confirm_user_action").performClick()
        compose.waitUntil(15_000) { compose.onAllNodesWithText("计划数量 2").fetchSemanticsNodes().isNotEmpty() }
        waiting(offer, 2)
        cartButton("waiting_remove_$offer")
        fullButton("cancel_user_action"); compose.onNodeWithTag("cancel_user_action").performClick()
        waiting(offer, 2)
        cartButton("waiting_remove_$offer")
        shot("c7c-removal-confirmation")
        fullButton("confirm_user_action"); compose.onNodeWithTag("confirm_user_action").performClick()
        compose.waitUntil(15_000) { compose.onAllNodesWithText("待购计划为空").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithText("待购计划为空").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("waiting_quantity_$offer").assertDoesNotExist()
        shot("c7c-removed")
    }

    @Test fun c7vWaitingCartStableVisuals() {
        val context = JSONObject(cartContextFile().readText())
        val product = context.getString("product_id")
        val offer = context.getString("offer_id")
        setup()
        compose.onNodeWithTag("tab_DECISIONS").performClick()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("open_saved_$product"))
        compose.onNodeWithTag("open_saved_$product").performClick()
        waitTag("saved_detail_list")
        compose.onNodeWithTag("saved_detail_list").performScrollToNode(hasText("加入待购"))
        compose.onNodeWithText("加入待购").performScrollTo().performClick()
        fullButton("confirm_user_action")
        compose.onNodeWithTag("confirm_user_action").performClick()
        compose.waitUntil(15_000) { !exists("confirm_user_action") }
        waitForCartReadback()
        waiting(offer, 1)
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("waiting_product_$offer"))
        compose.onNodeWithTag("waiting_product_$offer").performScrollTo().assertIsDisplayed().assertTextEquals(context.getString("title"))
        shot("c7v-global-product-title")
        cartButton("waiting_remove_$offer")
        fullButton("confirm_user_action")
        shot("c7v-confirmation")
        compose.onNodeWithTag("confirm_user_action").performClick()
        compose.waitUntil(15_000) { compose.onAllNodesWithText("待购计划为空").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithText("待购计划为空").performScrollTo().assertIsDisplayed()
        shot("c7v-removed")
    }

    @Test fun c5HistoryRenameArchiveAndPublicConversation() {
        val marker = System.currentTimeMillis().toString().takeLast(6)
        val goal = "预算500元耳机，UX历史任务$marker"
        val title = "通勤耳机 UX $marker"
        fresh(); submit(goal)
        compose.onNodeWithTag("back_to_mission").performClick()
        conversation("conversation_history")
        compose.waitUntil(15_000) { compose.onAllNodesWithText("本次完整对话").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithText("本次完整对话").assertIsDisplayed()
        compose.onAllNodesWithText(goal).onFirst().assertExists()
        shot("c5-public-conversation")
        compose.onNodeWithText("返回任务").performClick()
        conversation("task_history")
        waitTag("task_history_list")
        val item = prefix("history_") and hasAnyDescendant(hasText(goal))
        compose.onNode(item).performScrollTo()
        compose.onNode(hasText("命名") and hasAnyAncestor(item)).performClick()
        compose.onNodeWithTag("history_title_input").performTextReplacement(title)
        compose.onNodeWithText("确认保存").performClick()
        compose.waitUntil(15_000) { compose.onAllNodesWithText(title).fetchSemanticsNodes().isNotEmpty() }
        val renamed = prefix("history_") and hasAnyDescendant(hasText(title))
        compose.onNode(renamed).performScrollTo()
        compose.onNode(hasText("归档") and hasAnyAncestor(renamed)).performClick()
        compose.onNodeWithText("确认保存").performClick()
        compose.onNodeWithTag("history_archived").performClick()
        compose.onNodeWithTag("task_history_list").performScrollToNode(hasText(title))
        shot("c5-archived")
        compose.onNode(renamed).performScrollTo()
        compose.onNode(hasText("继续任务") and hasAnyAncestor(renamed)).performClick()
        compose.waitUntil(15_000) { !exists("history_archived") }
        resumeResult()
        shot("c5-reopened")
    }

    @Test fun c5bHistorySurvivesProcessRestart() {
        setup(); conversation("task_history")
        waitTag("task_history_list")
        compose.onNodeWithTag("history_archived").performClick()
        val row = prefix("history_") and hasAnyDescendant(hasText("通勤耳机 UX ", substring = true))
        compose.onAllNodes(row).onFirst().performScrollTo()
        shot("c5-restart-history")
        compose.onAllNodes(hasText("继续任务") and hasAnyAncestor(row)).onFirst().performScrollTo().performClick()
        compose.waitUntil(15_000) { !exists("history_archived") }
        resumeResult()
        shot("c5-restart-restored")
        compose.onNodeWithTag("back_to_mission").performClick()
        conversation("task_history")
        waitTag("task_history_list")
        val computerGoal = "预算5000元办公电脑，必须至少16GB内存"
        compose.onNodeWithTag("task_history_list").performScrollToNode(hasText(computerGoal))
        val computerRow = prefix("history_") and hasAnyDescendant(hasText(computerGoal))
        compose.onAllNodes(hasText("继续任务") and hasAnyAncestor(computerRow)).onFirst().performClick()
        compose.waitUntil(15_000) { !exists("history_archived") }
        resumeResult()
        compose.onAllNodesWithText("演示电脑", substring = true).onFirst().assertExists()
        shot("c5-other-task-isolated")
    }

    @Test fun c4aSaveBeforeProcessRestart() {
        fresh(); submit("预算1000元耳机，原生保存恢复")
        val product = visibleProduct()
        compose.onNodeWithTag("save_$product").performClick()
        compose.onNodeWithTag("confirm_user_action").performClick()
        compose.waitUntil(15_000) { compose.onAllNodesWithText("已保存候选方案").fetchSemanticsNodes().isNotEmpty() }
        shot("c4-before-restart")
    }

    @Test fun c4bSavedAndWaitingStateAfterProcessRestart() {
        setup(); compose.onNodeWithTag("tab_DECISIONS").performClick()
        compose.onNodeWithTag("screen_决策").performScrollToNode(prefix("open_saved_"))
        val savedTag = compose.onAllNodes(prefix("open_saved_")).fetchSemanticsNodes().first().config[SemanticsProperties.TestTag]
        compose.onNodeWithTag(savedTag).performClick()
        waitTag("saved_detail_list")
        compose.onNodeWithTag("saved_detail_list").performScrollToNode(hasText("移出保存"))
        shot("c4-after-restart-facts")
        compose.onNodeWithText("移出保存").performScrollTo().performClick()
        compose.onNodeWithText("确认移出保存").performScrollTo().performClick()
        compose.waitUntil(15_000) { !exists(savedTag) }
        compose.onNodeWithTag("screen_决策").performScrollToNode(prefix("waiting_quantity_"))
        compose.onNodeWithText("计划数量 1").performScrollTo().assertIsDisplayed()
        shot("c4-restart-cart-retained")
    }

    @Test fun c6ExploreExistingEquipmentAndNoPurchase() {
        fresh(); conversation("explore_start"); waitTag("explore_like_0")
        conversation("explore_like_0")
        conversation("explore_next")
        waitTag("explore_like_0")
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("explore_direction_0"))
        shot("c6-scenario-hints")
        conversation("explore_use_existing")
        compose.waitUntil(15_000) { compose.onAllNodesWithText("本次结论：先用现有设备尝试").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("connection_ONLINE"))
        completeTurn()
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasText("本次结论：先用现有设备尝试"))
        compose.onNodeWithText("本次结论：先用现有设备尝试").performScrollTo().assertIsDisplayed()
        shot("c6-use-existing")
        fresh(); conversation("explore_start"); waitTag("explore_like_0")
        conversation("explore_not_buying")
        compose.waitUntil(15_000) { compose.onAllNodesWithText("本次结论：暂不购买").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("connection_ONLINE"))
        completeTurn()
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasText("本次结论：暂不购买"))
        compose.onNodeWithText("本次结论：暂不购买").performScrollTo().assertIsDisplayed()
        shot("c6-not-buying")
    }
}
