package com.ragcommerce.agent

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeUp
import androidx.compose.ui.unit.dp
import com.ragcommerce.agent.ui.CartGroupUi
import com.ragcommerce.agent.ui.ConnectionState
import com.ragcommerce.agent.ui.EvidenceProductUi
import com.ragcommerce.agent.ui.OfferUi
import com.ragcommerce.agent.ui.PrimaryTab
import com.ragcommerce.agent.ui.QuoteState
import com.ragcommerce.agent.ui.SavedProductUi
import com.ragcommerce.agent.ui.ShoppingAction
import com.ragcommerce.agent.ui.ShoppingReducer
import com.ragcommerce.agent.ui.ShoppingUiState
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class ShoppingFlowTest {
    @get:Rule
    val compose = createComposeRule()

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
        compose.onNodeWithText("来源 fixture:product-1").assertIsDisplayed()
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
        compose.onNodeWithTag("confirm_quote_offer-1").performScrollTo().performClick()
        compose.onNodeWithTag("open_offer-1").assertIsEnabled()
    }

    @Test
    fun unavailableQuoteHasNoActiveMerchantNavigation() {
        setState(
            fixture(QuoteState.UNAVAILABLE).copy(selectedTab = PrimaryTab.DECISIONS),
        )
        compose.onNodeWithTag("open_offer-1").assertIsNotEnabled()
        compose.onNodeWithText("报价已失效或不可用，请重新询价").assertIsDisplayed()
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
                products = listOf(product("product-1"), product("product-2"), product("product-3")),
            ),
        )

        compose.onNodeWithTag("recommendation_pager").assertIsDisplayed()
        compose.onNodeWithText("主推荐").assertIsDisplayed()
        compose.onNodeWithText("01 / 03").assertIsDisplayed()
        compose.onNodeWithTag("recommendation_pager").performTouchInput { swipeUp() }
        compose.onNodeWithText("次推荐").assertIsDisplayed()
        compose.onNodeWithText("02 / 03").assertIsDisplayed()
        compose.onNodeWithTag("tab_DECISIONS").assertDoesNotExist()
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
        compose.onNodeWithText("DEMO_FIXTURE").assertIsDisplayed()
    }

    @Test
    fun loadingMissionShowsOnlyPublicAgentStages() {
        setState(fixture().copy(products = emptyList(), isLoading = true))

        compose.onNodeWithText("Agent 分析中").assertIsDisplayed()
        compose.onNodeWithText("理解需求").assertIsDisplayed()
        compose.onNodeWithText("混合检索").assertIsDisplayed()
        compose.onNodeWithText("核验证据").assertIsDisplayed()
        compose.onNodeWithText("比较候选").assertIsDisplayed()
    }

    @Test
    fun clarificationKeepsConversationOpenWithoutShowingProducts() {
        setState(
            fixture().copy(
                products = emptyList(),
                isLoading = false,
                statusMessage = "Agent 需要补充一个条件",
                agentMessages = listOf("请补充预算。"),
            ),
        )
        compose.onNodeWithText("请补充预算。").assertIsDisplayed()
        compose.onNodeWithTag("mission_input").assertIsDisplayed()
        compose.onNodeWithTag("recommendation_pager").assertDoesNotExist()
    }

    @Test
    fun approvalUsesNativeConfirmationSheetAndDemoBoundary() {
        setState(fixture().copy(pendingApprovalTool = "offers.refresh"))

        compose.onNodeWithText("确认执行操作").assertIsDisplayed()
        compose.onNodeWithText("DEMO_FIXTURE").assertIsDisplayed()
        compose.onNodeWithText("不会支付或下单").assertIsDisplayed()
        compose.onNodeWithText("取消").assertIsDisplayed()
        compose.onNodeWithText("确认并继续").assertIsDisplayed()
    }

    @Test
    fun profileSeparatesRuntimeTruthPrivacyAndDeletion() {
        setState(fixture().copy(selectedTab = PrimaryTab.PROFILE))

        compose.onNodeWithText("模型与数据声明").assertIsDisplayed()
        compose.onNodeWithText("当前不是 LIVE 环境").assertIsDisplayed()
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
        compose.onNodeWithText("恢复凭证").assertIsDisplayed()
        compose.onNodeWithText("重复终态 0").assertIsDisplayed()
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
                    ),
                ),
            ),
        ),
    )

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
