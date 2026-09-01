package com.ragcommerce.agent

import com.ragcommerce.agent.ui.CartGroupUi
import com.ragcommerce.agent.ui.ConnectionState
import com.ragcommerce.agent.ui.EvidenceProductUi
import com.ragcommerce.agent.ui.OfferUi
import com.ragcommerce.agent.ui.PrimaryTab
import com.ragcommerce.agent.ui.QuoteState
import com.ragcommerce.agent.ui.ShoppingAction
import com.ragcommerce.agent.ui.ShoppingReducer
import com.ragcommerce.agent.ui.ShoppingUiState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ShoppingReducerTest {
    @Test
    fun initialStateDoesNotClaimAnUnverifiedConnection() {
        val state = ShoppingUiState()

        assertEquals(ConnectionState.CHECKING, state.connection)
    }

    @Test
    fun serverQuoteChangeRevokesPriorLocalConfirmation() {
        val offer = OfferUi(
            id = "offer-1",
            merchantName = "fixture",
            priceText = "¥1.00",
            shippingText = null,
            verification = "FEED_VERIFIED",
            collectedAt = "2026-08-26T00:00:00Z",
            expiresAt = "2026-08-26T00:05:00Z",
            sourceRef = "fixture:offer",
            quoteState = QuoteState.CHANGED,
            disclosure = "fixture disclosure",
            confirmedChange = true,
        )
        val state = ShoppingUiState(cartGroups = listOf(CartGroupUi("fixture", listOf(offer))))

        val refreshed = ShoppingReducer.reduce(
            state,
            ShoppingAction.QuoteRefreshRequired("offer-1"),
        )

        assertFalse(refreshed.cartGroups.single().offers.single().confirmedChange)
        assertFalse(refreshed.cartGroups.single().offers.single().mayResolve)
    }

    @Test
    fun threeTabsHaveOnlyTheAgentFirstInformationArchitecture() {
        assertEquals(listOf("任务", "决策", "我的"), PrimaryTab.entries.map { it.label })
    }

    @Test
    fun missionAndPrimaryTabSurviveAsExplicitState() {
        val drafted = ShoppingReducer.reduce(
            ShoppingUiState(),
            ShoppingAction.UpdateDraft("预算 2000，通勤降噪"),
        )
        val submitted = ShoppingReducer.reduce(drafted, ShoppingAction.SubmitMission)
        val decisions = ShoppingReducer.reduce(submitted, ShoppingAction.SelectTab(PrimaryTab.DECISIONS))
        assertEquals("预算 2000，通勤降噪", decisions.missionGoal)
        assertEquals(PrimaryTab.DECISIONS, decisions.selectedTab)
    }

    @Test
    fun typedMissionUpdateReplacesThePublicGoal() {
        val state = ShoppingReducer.reduce(
            ShoppingUiState(missionGoal = "旧目标"),
            ShoppingAction.MissionUpdated("预算 1000 元的通勤耳机"),
        )
        assertEquals("预算 1000 元的通勤耳机", state.missionGoal)
        assertEquals("Mission 已更新", state.statusMessage)
    }

    @Test
    fun typedProductEventReplacesCandidatesAndCollectsEvidence() {
        val product = EvidenceProductUi(
            id = "product-1",
            variantId = "variant-1",
            title = "Fixture Headphones",
            fitSummary = "符合通勤降噪",
            matchedConstraints = listOf("预算内"),
            unmetConstraints = emptyList(),
            risks = listOf("演示报价"),
            evidenceRefs = listOf("demo:product-1"),
        )

        val state = ShoppingReducer.reduce(
            ShoppingUiState(),
            ShoppingAction.TurnProducts(listOf(product)),
        )

        assertEquals(listOf(product), state.products)
        assertEquals(listOf("demo:product-1"), state.evidenceRefs)
    }

    @Test
    fun changedQuoteBlocksNavigationUntilExplicitConfirmation() {
        val offer = offer(QuoteState.CHANGED)
        val state = ShoppingUiState(cartGroups = listOf(CartGroupUi("fixture", listOf(offer))))
        assertFalse(offer.mayResolve)
        val confirmed = ShoppingReducer.reduce(state, ShoppingAction.ConfirmQuoteChange(offer.id))
            .cartGroups.single().offers.single()
        assertTrue(confirmed.mayResolve)
    }

    @Test
    fun expiredAndUnavailableQuotesNeverResolve() {
        assertFalse(offer(QuoteState.EXPIRED).mayResolve)
        assertFalse(offer(QuoteState.UNAVAILABLE).mayResolve)
    }

    @Test
    fun discoveryOnlyPriceCanRemainAbsentWithoutClientFabrication() {
        val offer = offer(QuoteState.CURRENT, priceText = null)
        assertNull(offer.priceText)
        assertTrue(offer.sourceRef.isNotBlank())
    }

    @Test
    fun reconnectStatesPreserveMissionAndCart() {
        val original = ShoppingUiState(
            missionGoal = "fixture mission",
            cartGroups = listOf(CartGroupUi("fixture", listOf(offer(QuoteState.CURRENT)))),
        )
        val offline = ShoppingReducer.reduce(
            original,
            ShoppingAction.SetConnection(ConnectionState.OFFLINE),
        )
        val recovered = ShoppingReducer.reduce(
            offline,
            ShoppingAction.SetConnection(ConnectionState.RECOVERED),
        )
        assertEquals(original.missionGoal, recovered.missionGoal)
        assertEquals(original.cartGroups, recovered.cartGroups)
    }

    private fun offer(state: QuoteState, priceText: String? = "¥199.00") = OfferUi(
        id = "offer-1",
        merchantName = "fixture",
        priceText = priceText,
        shippingText = "¥0.00",
        verification = "FEED_VERIFIED",
        collectedAt = "2026-08-26T00:00:00Z",
        expiresAt = "2026-08-26T00:05:00Z",
        sourceRef = "fixture:offer-1",
        quoteState = state,
        disclosure = "fixture disclosure",
    )
}
