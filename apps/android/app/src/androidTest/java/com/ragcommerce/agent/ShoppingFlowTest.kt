package com.ragcommerce.agent

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Density
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsOn
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertHasClickAction
import androidx.compose.ui.test.assertIsOff
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.isDialog
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToIndex
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTextReplacement
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeLeft
import androidx.compose.ui.test.swipeUp
import androidx.compose.ui.unit.dp
import com.ragcommerce.agent.ui.CartGroupUi
import com.ragcommerce.agent.ui.BusinessFactUi
import com.ragcommerce.agent.ui.ConnectionState
import com.ragcommerce.agent.ui.ComparisonSort
import com.ragcommerce.agent.ui.EvidenceProductUi
import com.ragcommerce.agent.ui.OfferUi
import com.ragcommerce.agent.ui.PrimaryTab
import com.ragcommerce.agent.ui.QuoteState
import com.ragcommerce.agent.ui.RecommendationRouteUi
import com.ragcommerce.agent.ui.RecommendationType
import com.ragcommerce.agent.ui.SavedProductUi
import com.ragcommerce.agent.ui.MissionItemUi
import com.ragcommerce.agent.ui.ShoppingMissionUi
import com.ragcommerce.agent.ui.ShoppingAction
import com.ragcommerce.agent.ui.ShoppingReducer
import com.ragcommerce.agent.ui.ShoppingUiState
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class ShoppingFlowTest {
    @Test fun scrollingRecommendationConstraintsKeepsBackVisible() {
        val state = fixture().copy(products = listOf(product("product-1").copy(
            matchedConstraints = List(4) { "通勤使用与随身携带条件 $it" },
            unmetConstraints = List(4) { "仍需确认的规格条件 $it" },
        )))
        compose.setContent {
            val density = LocalDensity.current.density
            CompositionLocalProvider(LocalDensity provides Density(density, 2f)) {
                ShoppingApp(state = state, onAction = {})
            }
        }
        repeat(2) { compose.onNodeWithTag("recommendation_controls").performTouchInput { swipeUp() } }
        compose.onNodeWithTag("back_to_mission").assertIsDisplayed().assertHasClickAction()
        compose.onNodeWithTag("compare_product-1").assertIsDisplayed()
    }

    @Test fun explorationCheckboxHasOneAccessibleTargetAtLargeFont() {
        compose.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 2f)) {
                ShoppingApp(state = ShoppingUiState(connection = ConnectionState.ONLINE), onAction = {})
            }
        }
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("explore_start"))
        listOf("改善生活", "发现新玩法").forEach { label ->
            compose.onAllNodes(hasText(label) or hasContentDescription(label)).assertCountEquals(1)
            compose.onNodeWithContentDescription(label).assertHasClickAction().assertHeightIsAtLeast(48.dp)
                .assertIsOn().performClick().assertIsOff()
        }
    }
    @get:Rule
    val compose = createComposeRule()

    @Test fun mediaConfirmationIsEditableAndRequiresExplicitContinue() {
        val actions = mutableListOf<ShoppingAction>()
        compose.setContent {
            ShoppingApp(state = fixture().copy(showConversation = true, draft = "预算500元的耳机",
                pendingMediaInterpretations = listOf(com.ragcommerce.agent.generated.MediaInterpretation(
                    "media-fixture", "image", "耳机", visible_attributes = listOf("头戴式"),
                    uncertainties = listOf("不能由图片确认价格"), supported = true))),
                onAction = { actions.add(it) })
        }
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("media_confirmation_input"))
        compose.onNodeWithTag("media_confirmation_input").performTextReplacement("预算600元的耳机")
        assertEquals(listOf(ShoppingAction.UpdateDraft("预算600元的耳机")), actions)
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("media_confirm"))
        compose.onNodeWithTag("media_confirm").performScrollTo().assertIsEnabled().performClick()
        assertEquals(ShoppingAction.ConfirmMedia, actions.last())
    }

    @Test fun unsupportedMediaExplainsBoundaryAndCannotSendEmptyConfirmation() {
        setState(fixture().copy(showConversation = true, draft = "",
            pendingMediaInterpretations = listOf(com.ragcommerce.agent.generated.MediaInterpretation(
                "media-fixture", "audio", "", supported = false))))
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasText("未能确定需求，你可以改用文字说明"))
        compose.onNodeWithText("未能确定需求，你可以改用文字说明").assertIsDisplayed()
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("media_confirm"))
        compose.onNodeWithTag("media_confirm").assertIsNotEnabled()
    }

    @Test fun recordingDialogHasAccessibleControlAndCancelNeverSendsMedia() {
        var dismissed = 0
        var sent = 0
        compose.setContent { VoiceRecordingDialog(onDismiss = { dismissed++ }, onSend = { sent++ }) }
        compose.onNodeWithTag("voice_hold").assertHeightIsAtLeast(48.dp).assertExists()
        compose.onNodeWithTag("voice_send").assertIsNotEnabled()
        compose.onNodeWithTag("voice_cancel").performClick()
        assertEquals(1, dismissed)
        assertEquals(0, sent)
    }

    @Test fun uncertainApprovalExposesExplicitReadOnlyRecovery() {
        val actions = mutableListOf<ShoppingAction>()
        compose.setContent {
            ShoppingApp(state = fixture().copy(
                connection = ConnectionState.OFFLINE, showConversation = true,
                pendingApprovalTool = null, isLoading = false,
                statusMessage = "确认结果未核实，请恢复连接后核对待购",
            ), onAction = { actions.add(it) })
        }
        compose.onNodeWithTag("mission_conversation").performScrollToNode(hasTestTag("retry_connection"))
        compose.onNodeWithTag("retry_connection").performScrollTo().assertIsDisplayed().assertIsEnabled().performClick()
        assertEquals(listOf(ShoppingAction.RetryConnection), actions)
        compose.onNodeWithTag("agent_approval_confirm").assertDoesNotExist()
    }

    @Test fun externalSourceRequiresExplicitConfirmationAndCancelDoesNotLaunch() {
        val launched = mutableListOf<OfferUi>()
        compose.setContent { ShoppingApp(state = fixture(QuoteState.CURRENT).copy(selectedTab = PrimaryTab.DECISIONS,
            preparedMerchantOfferId = "offer-1", preparedMerchantHost = "demo.invalid"), onAction = {}, onOpenMerchant = { launched.add(it) }) }
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("open_offer-1"))
        compose.onNodeWithTag("open_offer-1").performScrollTo().assertIsEnabled().performClick()
        compose.onNodeWithText("打开外部来源？").assertIsDisplayed()
        assertEquals(0, launched.size)
        compose.onNodeWithTag("cancel_user_action").performClick()
        assertEquals(0, launched.size)
        compose.onNodeWithTag("open_offer-1").performClick()
        compose.onNodeWithTag("confirm_user_action").performClick()
        assertEquals("offer-1", launched.single().id)
    }

    @Test fun groupedWaitingOffersScrollToActualRemovalControl() {
        val base = fixture()
        val offers = (1..4).map { base.cartGroups.single().offers.single().copy(id = "offer-$it") }
        val writes = mutableListOf<ShoppingAction.SetWaitingQuantity>()
        compose.setContent {
            ShoppingApp(state = base.copy(
                selectedTab = PrimaryTab.DECISIONS,
                cartGroups = listOf(CartGroupUi("Fixture Merchant", offers)),
                waitingOfferIds = offers.map { it.id }.toSet(),
                waitingQuantities = offers.associate { it.id to 1 },
                waitingOffers = offers,
            ), onAction = { if (it is ShoppingAction.SetWaitingQuantity) writes.add(it) })
        }
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("waiting_remove_offer-4"))
        compose.onNodeWithTag("waiting_remove_offer-4").performScrollTo().assertIsDisplayed().assertIsEnabled().performClick()
        compose.onNodeWithText("移出待购计划？").assertIsDisplayed()
        assertEquals(0, writes.size)
        compose.onNodeWithTag("confirm_user_action").performClick()
        assertEquals("offer-4", writes.single().offer.id)
        assertEquals(0, writes.single().quantity)
    }

    @Test fun waitingQuantityAndRemovalRequireConfirmation() {
        var state by mutableStateOf(fixture().copy(selectedTab = PrimaryTab.DECISIONS))
        val writes = mutableListOf<ShoppingAction.SetWaitingQuantity>()
        compose.setContent {
            ShoppingApp(state = state, onAction = { action ->
                if (action is ShoppingAction.SetWaitingQuantity) {
                    writes.add(action)
                    state = ShoppingReducer.reduce(state, ShoppingAction.WaitingCartUpdated(
                        com.ragcommerce.agent.ui.WaitingCartUi(
                            if (action.quantity == 0) emptyMap() else mapOf(action.offer.id to action.quantity),
                            if (action.quantity == 0) emptyList() else listOf(action.offer))))
                } else state = ShoppingReducer.reduce(state, action)
            })
        }
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("waiting_increase_offer-1"))
        compose.onNodeWithTag("waiting_increase_offer-1").performClick()
        compose.onNodeWithTag("cancel_user_action").performClick()
        assertEquals(0, writes.size)
        compose.onNodeWithTag("waiting_quantity_offer-1").assertTextContains("计划数量 1")
        compose.onNodeWithTag("waiting_increase_offer-1").performClick()
        compose.onNodeWithTag("confirm_user_action").performClick()
        compose.onNodeWithTag("waiting_quantity_offer-1").assertTextContains("计划数量 2")
        assertEquals(2, writes.single().quantity)
        compose.onNodeWithTag("waiting_remove_offer-1").performClick()
        compose.onNodeWithText("移出待购计划？").assertIsDisplayed()
        compose.onNodeWithTag("confirm_user_action").performClick()
        compose.onNodeWithText("待购计划为空").assertIsDisplayed()
        assertEquals(0, writes.last().quantity)
    }

    @Test
    fun taskIsTheFirstPrimaryPage() {
        setState(fixture().copy(products = emptyList()))
        compose.onNodeWithTag("screen_任务").assertIsDisplayed()
        compose.onNodeWithTag("tab_TASK").assertHeightIsAtLeast(48.dp)
    }

    @Test
    fun decisionsUnifiesSavedPlansAndWaitingCollection() {
        setState(fixture().copy(selectedTab = PrimaryTab.DECISIONS))
        compose.onNodeWithText("比较、已保存方案与待购集合，不创建订单").assertIsDisplayed()
        compose.onNodeWithTag("saved_product-1").assertIsDisplayed()
        compose.onNodeWithTag("merchant_Fixture Merchant").assertIsDisplayed()
    }

    @Test
    fun profileShowsPrivacyAndSourcePolicyWithoutFakeOrders() {
        setState(fixture().copy(selectedTab = PrimaryTab.PROFILE))
        compose.onNodeWithText("商业来源").assertIsDisplayed()
        compose.onNodeWithText("订单中心").assertDoesNotExist()
    }

    @Test
    fun recommendationCardShowsEvidenceSource() {
        setState(fixture())
        compose.onNodeWithText("查看来源与依据").assertIsDisplayed().performClick()
        compose.onNodeWithText("证据来源").assertIsDisplayed()
        compose.onNodeWithText("关闭依据").performClick()
        compose.onNodeWithTag("constraint_summary").performScrollTo().assertIsDisplayed()
    }

    @Test
    fun waitingPlanDoesNotAdvertiseUnimplementedPriceMonitoring() {
        setState(fixture().copy(selectedTab = PrimaryTab.DECISIONS))
        compose.onNodeWithTag("screen_决策").performScrollToIndex(5)
        compose.onNodeWithTag("merchant_Fixture Merchant").assertExists()
        compose.onNodeWithText("演示观察 · 不会后台提醒").assertDoesNotExist()
        compose.onNodeWithTag("watch_price_offer-1").assertDoesNotExist()
        compose.onNodeWithTag("watch_stock_offer-1").assertDoesNotExist()
    }

    @Test
    fun recommendationCardSeparatesDemoBusinessFactsFromVerifiedClaims() {
        setState(fixture())
        compose.onNodeWithTag("business_facts").assertIsDisplayed()
        compose.onNodeWithText("库存 · 演示目录包含此报价; 不代表真实库存 · 演示数据").assertIsDisplayed()
        compose.onNodeWithText("配送 · 未接入真实配送承诺 · 演示数据").assertIsDisplayed()
        compose.onNodeWithText("售后 · 未接入真实售后条款 · 演示数据").assertIsDisplayed()
    }

    @Test
    fun recommendationShowsThreeExplicitRoutesAndAlternativeRelaxation() {
        setState(
            fixture().copy(
                products = listOf(
                    product("product-1"),
                    product("product-2").copy(
                        recommendationType = RecommendationType.ALTERNATIVE,
                        relaxedConstraints = listOf("耳机必须轻量"),
                    ),
                ),
                recommendationRoutes = listOf(
                    RecommendationRouteUi(RecommendationType.STRICT, true, "满足全部可验证硬约束", emptyList(), listOf("product-1")),
                    RecommendationRouteUi(RecommendationType.BUDGET, false, "没有同时满足硬约束和预算上限的商品", emptyList(), emptyList()),
                    RecommendationRouteUi(RecommendationType.ALTERNATIVE, true, "替代商品; 明确放宽硬约束: 耳机必须轻量", listOf("耳机必须轻量"), listOf("product-2")),
                ),
            ),
        )

        compose.onNodeWithTag("recommendation_routes").performScrollTo()
        compose.onNodeWithTag("route_STRICT").assertIsDisplayed()
        compose.onNodeWithTag("route_BUDGET").assertIsDisplayed()
        compose.onNodeWithTag("recommendation_routes").performTouchInput { swipeLeft() }
        compose.onNodeWithTag("route_ALTERNATIVE").assertIsDisplayed()
        compose.onNodeWithTag("recommendation_pager").performTouchInput { swipeUp() }
        compose.onNodeWithText("明确放宽 · 耳机必须轻量").assertIsDisplayed()
    }

    @Test
    fun missionConstraintsAreEditableWithoutReplacingTheCurrentRecommendation() {
        var state by mutableStateOf(
            fixture().copy(
                connection = ConnectionState.ONLINE,
                mission = ShoppingMissionUi(
                    goal = "预算 1000 元的通勤耳机",
                    version = 1,
                    items = listOf(MissionItemUi("耳机", 1)),
                    hardConstraints = listOf("预算 1000 元"),
                    softPreferences = listOf("通勤降噪"),
                    unknowns = emptyList(),
                    budgetTotalMinor = 100000,
                ),
            ),
        )
        compose.setContent {
            ShoppingApp(
                state = state,
                onAction = { state = ShoppingReducer.reduce(state, it) },
            )
        }

        compose.onNodeWithTag("mission_constraints").assertIsDisplayed()
        compose.onNodeWithText("总预算 ¥1000").performClick()
        compose.onNodeWithTag("mission_edit_input")
            .performTextReplacement("预算 1200 元，通勤降噪必须好")
        compose.onNodeWithText("保存修改").performClick()

        compose.onNodeWithTag("recalculate_mission").assertIsDisplayed()
        compose.onNodeWithTag("recommendation_pager").assertIsDisplayed()
    }

    @Test
    fun comparisonWorkspaceAppearsForTwoSelectedProducts() {
        setState(
            fixture().copy(
                selectedTab = PrimaryTab.DECISIONS,
                products = listOf(product("product-1"), product("product-2")),
                comparedProductIds = setOf("product-1", "product-2"),
            ),
        )
        compose.onNodeWithText("比较工作台").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("comparison_product-1").assertIsDisplayed()
        compose.onNodeWithTag("comparison_product-2").assertIsDisplayed()
        compose.onNodeWithTag("comparison_table").assertIsDisplayed()
        compose.onNodeWithText("按预算").assertIsDisplayed()
        compose.onNodeWithText("按硬约束").assertIsDisplayed()
        compose.onNodeWithText("按偏好").assertIsDisplayed()
    }

    @Test
    fun comparisonSortIsAnExplicitUserChoice() {
        var state by mutableStateOf(
            fixture().copy(
                selectedTab = PrimaryTab.DECISIONS,
                products = listOf(product("product-1"), product("product-2")),
                comparedProductIds = setOf("product-1", "product-2"),
            ),
        )
        compose.setContent {
            ShoppingApp(state = state, onAction = { state = ShoppingReducer.reduce(state, it) })
        }

        compose.onNodeWithTag("comparison_sort_BUDGET").performClick()
        compose.runOnIdle { assertEquals(ComparisonSort.BUDGET, state.comparisonSort) }
    }

    @Test
    fun oneSelectedProductExplainsHowToEnterComparison() {
        setState(
            fixture().copy(
                products = listOf(product("product-1"), product("product-2")),
                comparedProductIds = setOf("product-1"),
            ),
        )
        compose.onNodeWithText("已选 1 项，再选 1 项进入比较").assertIsDisplayed()
        compose.onNodeWithText("已加入比较").assertIsDisplayed()
        compose.onNodeWithText("比较工作台").assertDoesNotExist()
    }

    @Test
    fun imageAndVoiceTargetsAreAccessibleAndLargeEnough() {
        var imageClicks = 0
        var audioClicks = 0
        compose.setContent {
            ShoppingApp(
                state = fixture().copy(products = emptyList()),
                onAction = {},
                onPickImage = { imageClicks += 1 },
                onPickAudio = { audioClicks += 1 },
            )
        }
        compose.onNodeWithContentDescription("添加商品图片")
            .assertHeightIsAtLeast(48.dp)
            .performClick()
        compose.onNodeWithContentDescription("添加语音")
            .assertHeightIsAtLeast(48.dp)
            .performClick()
        assertEquals(1, imageClicks)
        assertEquals(1, audioClicks)
    }

    @Test
    fun changedQuoteBlocksMerchantNavigation() {
        setState(fixture().copy(selectedTab = PrimaryTab.DECISIONS))
        compose.onNodeWithTag("screen_决策").performScrollToIndex(5)
        compose.onNodeWithTag("open_offer-1").assertIsNotEnabled()
        compose.onNodeWithText("价格或库存已变化，已阻断跳转").assertIsDisplayed()
    }

    @Test
    fun changedQuoteRequiresASecondExplicitConfirmation() {
        var state by mutableStateOf(fixture().copy(selectedTab = PrimaryTab.DECISIONS))
        compose.setContent {
            ShoppingApp(
                state = state,
                onAction = { state = ShoppingReducer.reduce(state, it) },
            )
        }
        compose.onNodeWithTag("screen_决策").performScrollToIndex(5)
        compose.onNodeWithTag("confirm_quote_offer-1").performScrollTo().performClick()
        compose.onNodeWithTag("open_offer-1").assertIsEnabled()
    }

    @Test
    fun unavailableQuoteHasNoActiveMerchantNavigation() {
        var state by mutableStateOf(
            fixture(QuoteState.UNAVAILABLE).copy(selectedTab = PrimaryTab.DECISIONS),
        )
        val requotes = mutableListOf<ShoppingAction.RequoteOffer>()
        compose.setContent {
            ShoppingApp(
                state = state,
                onAction = { if (it is ShoppingAction.RequoteOffer) requotes.add(it) else state = ShoppingReducer.reduce(state, it) },
            )
        }
        compose.onNodeWithTag("screen_决策").performScrollToIndex(5)
        compose.onNodeWithTag("open_offer-1").assertIsNotEnabled()
        compose.onNodeWithText("报价已失效或不可用，请重新询价").assertIsDisplayed()
        compose.onNodeWithTag("requote_offer-1").performClick()
        assertEquals("offer-1", requotes.single().offer.id)
        compose.onNodeWithTag("open_offer-1").assertIsNotEnabled()
    }

    @Test
    fun offlineStatePreservesMissionAndExplainsTheBoundary() {
        var state by mutableStateOf(fixture().copy(connection = ConnectionState.OFFLINE))
        compose.setContent {
            ShoppingApp(
                state = state,
                onAction = { state = ShoppingReducer.reduce(state, it) },
            )
        }
        compose.onNodeWithTag("connection_OFFLINE").assertIsDisplayed()
        compose.onNodeWithText("fixture mission").assertIsDisplayed()
        compose.onNodeWithTag("retry_connection").performClick()
        compose.onNodeWithTag("connection_RECONNECTING").assertIsDisplayed()
    }

    @Test
    fun recoveredStateIsExplicitAfterSseReconnect() {
        setState(
            fixture().copy(
                connection = ConnectionState.RECOVERED,
                statusMessage = "已从最后事件恢复，无重复完成事件",
            ),
        )
        compose.onNodeWithTag("connection_RECOVERED").assertIsDisplayed()
        compose.onNodeWithText("已从最后事件恢复，无重复完成事件").assertIsDisplayed()
    }

    @Test
    fun recommendationResultUsesRankedVerticalPager() {
        setState(
            fixture().copy(
                connection = ConnectionState.ONLINE,
                products = listOf(product("product-1"), product("product-2"), product("product-3")),
            ),
        )

        compose.onNodeWithTag("recommendation_pager").assertIsDisplayed()
        compose.onNodeWithTag("recommendation_rank_0")
            .assertTextContains("主推荐", substring = true)
            .assertIsDisplayed()
        compose.onNodeWithText("01 / 03").assertIsDisplayed()
        compose.onNodeWithTag("recommendation_pager").performTouchInput { swipeUp() }
        compose.onNodeWithTag("recommendation_rank_1")
            .assertTextContains("次推荐", substring = true)
            .assertIsDisplayed()
        compose.onNodeWithText("02 / 03").assertIsDisplayed()
        compose.onNodeWithTag("tab_DECISIONS").assertDoesNotExist()
    }

    @Test
    fun longControlsAndSelectionDoNotClipSecondaryCandidateActions() {
        // Explicit visual fixture. This does not replace the real A06 result.
        var state by mutableStateOf(fixture().copy(
            products = (1..3).map { product("product-$it").copy(title = "演示手机 $it", risks = listOf("DEMO_FIXTURE")) },
            comparedProductIds = setOf("product-1"),
            mission = ShoppingMissionUi(goal = "购买手机", version = 1,
                items = listOf(MissionItemUi("手机", 1)),
                hardConstraints = (1..8).map { "需要核对的详细约束 $it" },
                softPreferences = emptyList(), unknowns = emptyList(), budgetTotalMinor = 200000),
        ))
        compose.setContent { ShoppingApp(state = state, onAction = { state = ShoppingReducer.reduce(state, it) }) }
        compose.onNodeWithTag("recommendation_pager").performTouchInput { swipeUp() }
        compose.onNodeWithTag("recommendation_rank_1").assertIsDisplayed()
        compose.onNodeWithTag("compare_product-2").assertIsDisplayed().assertHeightIsAtLeast(48.dp).performClick()
        compose.onNodeWithTag("compare_product-2").assertIsOn()
        compose.onNode(hasText("提示 · 演示商品与报价，不代表商家实时信息") and
            hasAnyAncestor(hasTestTag("product_product-2"))).assertIsDisplayed()
    }

    @Test
    fun recommendationStackExposesOnlyTheConfirmedTopThree() {
        setState(
            fixture().copy(
                products = (1..5).map { index -> product("product-$index") },
            ),
        )

        compose.onNodeWithText("01 / 03").assertIsDisplayed()
        compose.onNodeWithText("01 / 05").assertDoesNotExist()
    }

    @Test
    fun recommendationCanReturnToMissionConversation() {
        var state by mutableStateOf(fixture())
        compose.setContent {
            ShoppingApp(
                state = state,
                onAction = { state = ShoppingReducer.reduce(state, it) },
            )
        }

        compose.onNodeWithTag("back_to_mission").performClick()
        compose.onNodeWithTag("mission_input").assertIsDisplayed()
    }

    @Test
    fun conversationCanReopenExistingRecommendationsWithoutNewResults() {
        var state by mutableStateOf(fixture().copy(comparedProductIds = setOf("product-1")))
        compose.setContent {
            ShoppingApp(state = state, onAction = { state = ShoppingReducer.reduce(state, it) })
        }
        compose.onNodeWithTag("back_to_mission").performClick()
        compose.onNodeWithTag("reopen_recommendations").performScrollTo().performClick()
        compose.onNodeWithTag("back_to_mission").assertIsDisplayed()
        compose.runOnIdle {
            assertEquals(setOf("product-1"), state.comparedProductIds)
            assertEquals(fixture().products, state.products)
        }
    }

    @Test
    fun largeFontLongRecommendationKeepsActionsAndFullFactsReachable() {
        val longProduct = product("product-1").copy(
            title = "Nova Mobile Pulse 01 演示手机",
            matchedConstraints = listOf("日常通勤"),
            unmetConstraints = listOf("2000元以内 通勤智能手机"),
            relaxedConstraints = listOf("2000元以内 通勤智能手机"),
            risks = listOf("演示商品与报价，不代表真实市场供应"),
        )
        val current = fixture(QuoteState.EXPIRED).copy(
            products = listOf(longProduct),
            cartGroups = fixture(QuoteState.EXPIRED).cartGroups.map { group ->
                group.copy(offers = group.offers.map { it.copy(
                    priceText = "¥1599.00", verification = "DEMO_FIXTURE",
                    businessFacts = it.businessFacts.map { fact ->
                        if (fact.type == "price") fact.copy(summary = "演示报价 ¥1599.00; 不可作为成交价") else fact
                    },
                ) })
            },
        )
        compose.setContent {
            val density = LocalDensity.current.density
            CompositionLocalProvider(LocalDensity provides Density(density, fontScale = 2f)) {
                ShoppingApp(state = current, onAction = {})
            }
        }
        compose.onNodeWithTag("compare_product-1").assertIsDisplayed()
        compose.onNodeWithTag("save_product-1").assertIsDisplayed()
        compose.onNodeWithTag("add_plan_product-1").assertIsDisplayed()
        compose.onNodeWithTag("evidence_product_product-1").assertIsDisplayed().performClick()
        compose.onNode(hasText("未满足 · 2000元以内 通勤智能手机") and hasAnyAncestor(isDialog()))
            .performScrollTo().assertIsDisplayed()
        compose.onNode(hasText("演示目录包含此报价; 不代表真实库存", substring = true) and hasAnyAncestor(isDialog()))
            .performScrollTo().assertIsDisplayed()
    }

    @Test
    fun conversationDoesNotExposeRawEvidenceIdentifiers() {
        setState(fixture().copy(
            showConversation = true,
            evidenceRefs = listOf("demo:v3:3c0668b8-1315-54ea-8d88-90c652c9aaf8:offer"),
        ))
        compose.onNodeWithTag("mission_conversation").assertExists()
        compose.onNodeWithText("证据引用").assertDoesNotExist()
        compose.onNodeWithText("demo:v3:3c0668b8-1315-54ea-8d88-90c652c9aaf8:offer").assertDoesNotExist()
    }

    @Test
    fun recommendationShowsTypedQuoteTruth() {
        val current = fixture(QuoteState.CURRENT)
        setState(
            current.copy(
                cartGroups = current.cartGroups.map { group ->
                    group.copy(
                        offers = group.offers.map { offer ->
                            offer.copy(
                                productId = "product-1",
                                verification = "DEMO_FIXTURE",
                            )
                        },
                    )
                },
            ),
        )

        compose.onNodeWithText("¥199.00").assertIsDisplayed()
        compose.onNodeWithText("演示报价 · 不可作为成交价").assertIsDisplayed()
    }

    @Test
    fun demoOfferDoesNotPresentItselfAsAPurchasableMerchant() {
        val demo = fixture(QuoteState.CURRENT)
        setState(
            demo.copy(
                selectedTab = PrimaryTab.DECISIONS,
                waitingOffers = demo.waitingOffers.map { it.copy(verification = "DEMO_FIXTURE") },
                cartGroups = demo.cartGroups.map { group ->
                    group.copy(offers = group.offers.map { it.copy(verification = "DEMO_FIXTURE") })
                },
            ),
        )

        compose.onNodeWithTag("screen_决策").performScrollToNode(hasText("演示商家 · Fixture Merchant"))
        compose.onNodeWithText("演示商家 · Fixture Merchant").assertIsDisplayed()
        compose.onNodeWithText("演示数据 · 不代表可购买").assertIsDisplayed()
        compose.onNodeWithText("查看演示来源").performScrollTo().assertIsDisplayed()
        compose.onNodeWithText("前往商家").assertDoesNotExist()
    }

    @Test
    fun liveAuthorizedOfferRetainsTheExplicitMerchantAction() {
        val live = fixture(QuoteState.CURRENT)
        setState(
            live.copy(
                selectedTab = PrimaryTab.DECISIONS,
                waitingOffers = live.waitingOffers.map { it.copy(verification = "LIVE_AUTHORIZED") },
                cartGroups = live.cartGroups.map { group ->
                    group.copy(offers = group.offers.map { it.copy(verification = "LIVE_AUTHORIZED") })
                },
            ),
        )

        compose.onNodeWithTag("screen_决策").performScrollToNode(hasTestTag("quote_time_offer-1"))
        compose.onNodeWithText("已授权实时报价 · 采集 2026-08-26T00:00:00Z").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("screen_决策").performScrollToNode(hasText("前往商家"))
        compose.onNodeWithText("前往商家").performScrollTo().assertIsDisplayed()
        compose.onNodeWithText("演示数据 · 不代表可购买").assertDoesNotExist()
    }

    @Test
    fun loadingMissionShowsOnlyPublicAgentStages() {
        var currentStage by mutableStateOf("理解需求")
        compose.setContent { ShoppingApp(state = fixture().copy(products = emptyList(), isLoading = true,
            statusMessage = currentStage), onAction = {}) }
        // The current UI shows one server-reported public stage, not four fabricated progress chips.
        listOf("理解需求", "混合检索", "核验证据", "比较候选").forEach { stage ->
            compose.runOnIdle { currentStage = stage }
            val progress = hasText(stage) and hasAnyAncestor(
                SemanticsMatcher.expectValue(SemanticsProperties.LiveRegion, LiveRegionMode.Polite))
            compose.onNodeWithTag("mission_conversation").performScrollToNode(progress)
            compose.onNodeWithText("Agent 分析中").assertIsDisplayed()
            compose.onNode(progress).assertIsDisplayed()
        }
    }

    @Test
    fun clarificationKeepsConversationOpenWithoutShowingProducts() {
        var state by mutableStateOf(
            fixture().copy(
                products = emptyList(),
                isLoading = false,
                statusMessage = "Agent 需要补充一个条件",
                agentMessages = listOf("请补充预算。"),
                clarificationQuestion = "请补充预算。",
            ),
        )
        compose.setContent {
            ShoppingApp(
                state = state,
                onAction = { state = ShoppingReducer.reduce(state, it) },
            )
        }
        compose.onNodeWithText("请补充预算。").assertIsDisplayed()
        compose.onNodeWithTag("clarification_quick_replies").assertIsDisplayed()
        compose.onNodeWithTag("clarification_budget").performClick()
        compose.onNodeWithTag("mission_conversation").performScrollToIndex(2)
        compose.onNodeWithTag("mission_input").assertIsDisplayed()
            .assertTextContains("我的预算是：")
        compose.onNodeWithTag("recommendation_pager").assertDoesNotExist()
    }

    @Test
    fun approvalUsesNativeConfirmationSheetAndDemoBoundary() {
        setState(fixture().copy(pendingApprovalTool = "cart.update"))

        compose.onNodeWithText("确认执行操作").assertIsDisplayed()
        compose.onNodeWithText("演示数据").assertIsDisplayed()
        compose.onNodeWithText("不会支付或下单").assertIsDisplayed()
        compose.onNodeWithText("取消").assertIsDisplayed()
        compose.onNodeWithText("确认并继续").assertIsDisplayed()
        compose.onNodeWithText("按本次需求修改待购商品与数量，确认前不会写入。").assertIsDisplayed()
        compose.onNodeWithText("工具 cart.update 将修改可逆的导购状态。").assertDoesNotExist()
    }

    @Test
    fun profileSeparatesRuntimeTruthPrivacyAndDeletion() {
        setState(fixture().copy(selectedTab = PrimaryTab.PROFILE))

        compose.onNodeWithText("模型与数据声明").assertIsDisplayed()
        compose.onNodeWithText("演示商品与报价，不代表真实市场信息").assertIsDisplayed()
        compose.onNodeWithText("删除我的数据").assertIsDisplayed()
    }

    @Test
    fun recoveredMissionShowsRecoveryReceipt() {
        var state by mutableStateOf(
            fixture().copy(
                connection = ConnectionState.RECOVERED,
                statusMessage = "已从最后事件恢复，无重复完成事件",
            ),
        )
        compose.setContent {
            ShoppingApp(
                state = state,
                onAction = { state = ShoppingReducer.reduce(state, it) },
            )
        }

        compose.onNodeWithText("已恢复").assertIsDisplayed()
        compose.onNodeWithTag("tab_DECISIONS").assertIsNotEnabled()
        compose.onNodeWithText("恢复说明").assertExists()
        compose.onNodeWithText("重复终态 0").assertDoesNotExist()
        compose.onNodeWithTag("connection_RECOVERED").performScrollToIndex(4)
        compose.onNodeWithTag("continue_recovered").performClick()
        compose.onNodeWithTag("recommendation_pager").assertIsDisplayed()
    }

    private fun setState(state: ShoppingUiState) {
        compose.setContent { ShoppingApp(state = state, onAction = {}) }
    }

    private fun fixture(quoteState: QuoteState = QuoteState.CHANGED) = ShoppingUiState(
        missionGoal = "fixture mission",
        products = listOf(product("product-1")),
        savedProducts = listOf(SavedProductUi("product-1", "Fixture Headphones", "fixture:product-1")),
        cartGroups = listOf(
            CartGroupUi(
                "Fixture Merchant",
                listOf(
                    OfferUi(
                        id = "offer-1",
                        productId = "product-1",
                        variantId = "variant-product-1",
                        merchantName = "Fixture Merchant",
                        priceText = "¥199.00",
                        shippingText = "¥0.00",
                        verification = "FEED_VERIFIED",
                        collectedAt = "2026-08-26T00:00:00Z",
                        expiresAt = "2026-08-26T00:05:00Z",
                        sourceRef = "fixture:offer-1",
                        quoteState = quoteState,
                        disclosure = "fixture affiliate disclosure",
                        businessFacts = listOf(
                            BusinessFactUi("price", "演示报价 ¥199.00; 不可作为成交价", "DEMO_FIXTURE", "2026-08-26T00:00:00Z", "2026-08-26T00:05:00Z", "fixture:offer-1"),
                            BusinessFactUi("inventory", "演示目录包含此报价; 不代表真实库存", "DEMO_FIXTURE", "2026-08-26T00:00:00Z", "2026-08-26T00:05:00Z", "fixture:offer-1"),
                            BusinessFactUi("delivery", "未接入真实配送承诺", "DEMO_FIXTURE", "2026-08-26T00:00:00Z", null, "fixture:offer-1"),
                            BusinessFactUi("merchant", "演示商家", "DEMO_FIXTURE", "2026-08-26T00:00:00Z", null, "fixture:offer-1"),
                            BusinessFactUi("after_sales", "未接入真实售后条款", "DEMO_FIXTURE", "2026-08-26T00:00:00Z", null, "fixture:offer-1"),
                        ),
                    ),
                ),
            ),
        ),
        waitingOfferIds = setOf("offer-1"),
        waitingQuantities = mapOf("offer-1" to 1),
    ).let { it.copy(waitingOffers = it.cartGroups.flatMap(CartGroupUi::offers)) }

    private fun product(id: String) = EvidenceProductUi(
        id = id,
        variantId = "variant-$id",
        title = "Fixture Headphones $id",
        fitSummary = "符合 fixture 硬约束",
        matchedConstraints = listOf("预算内"),
        unmetConstraints = emptyList(),
        risks = emptyList(),
        evidenceRefs = listOf("fixture:$id"),
    )
}
