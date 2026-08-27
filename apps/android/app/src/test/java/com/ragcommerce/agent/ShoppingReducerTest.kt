package com.ragcommerce.agent

import com.ragcommerce.agent.ui.CartGroupUi
import com.ragcommerce.agent.ui.ConnectionState
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
    fun fourTabsHaveOnlyTheApprovedPrimaryInformationArchitecture() {
        assertEquals(listOf("导购", "清单", "购物车", "我的"), PrimaryTab.entries.map { it.label })
    }

    @Test
    fun missionAndPrimaryTabSurviveAsExplicitState() {
        val drafted = ShoppingReducer.reduce(
            ShoppingUiState(),
            ShoppingAction.UpdateDraft("预算 2000，通勤降噪"),
        )
        val submitted = ShoppingReducer.reduce(drafted, ShoppingAction.SubmitMission)
        val cart = ShoppingReducer.reduce(submitted, ShoppingAction.SelectTab(PrimaryTab.CART))
        assertEquals("预算 2000，通勤降噪", cart.missionGoal)
        assertEquals(PrimaryTab.CART, cart.selectedTab)
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
