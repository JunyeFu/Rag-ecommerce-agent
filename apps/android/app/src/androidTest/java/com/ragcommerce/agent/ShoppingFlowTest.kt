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
    fun guideIsTheFirstPrimaryPage() {
        setState(fixture())
        compose.onNodeWithTag("screen_导购").assertIsDisplayed()
        compose.onNodeWithTag("tab_GUIDE").assertHeightIsAtLeast(48.dp)
    }

    @Test
    fun listsAreAFirstClassPrimaryPage() {
        setState(fixture().copy(selectedTab = PrimaryTab.LISTS))
        compose.onNodeWithText("跨平台候选，不等于已下单").assertIsDisplayed()
        compose.onNodeWithTag("saved_product-1").assertIsDisplayed()
    }

    @Test
    fun cartIsAGroupedCrossMarketplaceCollection() {
        setState(fixture().copy(selectedTab = PrimaryTab.CART))
        compose.onNodeWithText("按商家分组的跨站待购集合，跳转前重新询价").assertIsDisplayed()
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
                state = fixture(),
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
        setState(fixture().copy(selectedTab = PrimaryTab.CART))
        compose.onNodeWithTag("open_offer-1").assertIsNotEnabled()
        compose.onNodeWithText("价格或库存已变化，已阻断跳转").assertIsDisplayed()
    }

    @Test
    fun changedQuoteRequiresASecondExplicitConfirmation() {
        var state by mutableStateOf(fixture().copy(selectedTab = PrimaryTab.CART))
        compose.setContent {
            ShoppingApp(
                state = state,
                onAction = { state = ShoppingReducer.reduce(state, it) },
            )
        }
        compose.onNodeWithTag("confirm_quote_offer-1").performClick()
        compose.onNodeWithTag("open_offer-1").assertIsEnabled()
    }

    @Test
    fun unavailableQuoteHasNoActiveMerchantNavigation() {
        setState(
            fixture(QuoteState.UNAVAILABLE).copy(selectedTab = PrimaryTab.CART),
        )
        compose.onNodeWithTag("open_offer-1").assertIsNotEnabled()
        compose.onNodeWithText("报价已失效或不可用，请重新询价").assertIsDisplayed()
    }

    @Test
    fun offlineStatePreservesMissionAndExplainsTheBoundary() {
        setState(fixture().copy(connection = ConnectionState.OFFLINE))
        compose.onNodeWithTag("connection_OFFLINE").assertIsDisplayed()
        compose.onNodeWithText("fixture mission").assertIsDisplayed()
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
        title = "Fixture Headphones $id",
        reasons = listOf("符合 fixture 硬约束"),
        sourceRef = "fixture:$id",
    )
}
