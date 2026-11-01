package com.ragcommerce.agent

import com.ragcommerce.agent.ui.CartGroupUi
import com.ragcommerce.agent.ui.ConnectionState
import com.ragcommerce.agent.ui.ComparisonSort
import com.ragcommerce.agent.ui.EvidenceProductUi
import com.ragcommerce.agent.ui.OfferUi
import com.ragcommerce.agent.ui.PrimaryTab
import com.ragcommerce.agent.ui.QuoteState
import com.ragcommerce.agent.ui.ShoppingAction
import com.ragcommerce.agent.ui.ShoppingReducer
import com.ragcommerce.agent.ui.ShoppingUiState
import com.ragcommerce.agent.ui.WaitingCartUi
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ShoppingReducerTest {
    @Test fun newMissionDoesNotKeepPreviousMissionOffers() {
        val old = offer(QuoteState.CURRENT)
        val fresh = ShoppingReducer.reduce(ShoppingUiState(
            cartGroups = listOf(CartGroupUi("fixture", listOf(old))),
            waitingOfferIds = setOf(old.id), waitingQuantities = mapOf(old.id to 2),
            waitingOffers = listOf(old),
        ), ShoppingAction.StartNewMission)
        assertTrue("Mission quotes must not masquerade as the global cart", fresh.cartGroups.isEmpty())
        assertEquals(mapOf(old.id to 2), fresh.waitingQuantities)
        assertEquals(listOf(old), fresh.waitingOffers)
    }

    @Test fun refreshedQuoteReplacesOnlyItsProductAndRevokesPriorPriceConfirmation() {
        val old = offer(QuoteState.CHANGED).copy(productId = "p1", confirmedChange = true)
        val other = old.copy(id = "other", productId = "p2")
        val fresh = old.copy(quoteState = QuoteState.CURRENT, confirmedChange = false, priceText = "¥2.00")
        val state = ShoppingUiState(cartGroups = listOf(CartGroupUi("fixture", listOf(old, other))))
        val updated = ShoppingReducer.reduce(state, ShoppingAction.OfferRequoted("p1", listOf(fresh)))
        assertEquals(listOf(other, fresh), updated.cartGroups.flatMap { it.offers })
        assertFalse(updated.cartGroups.flatMap { it.offers }.single { it.productId == "p1" }.confirmedChange)
        val unavailable = ShoppingReducer.reduce(updated, ShoppingAction.OfferRequoted("p1", emptyList()))
        assertEquals(listOf(other), unavailable.cartGroups.flatMap { it.offers })
        assertEquals("当前没有可用报价", unavailable.statusMessage)
    }

    @Test fun anotherMissionOffersCannotReplaceTheGlobalWaitingCart() {
        val waiting = offer(QuoteState.EXPIRED).copy(productId = "earbuds", productTitle = "演示耳机")
        val computer = waiting.copy(id = "computer-offer", productId = "computer", productTitle = "演示电脑")
        val global = ShoppingReducer.reduce(ShoppingUiState(), ShoppingAction.WaitingCartUpdated(
            WaitingCartUi(mapOf(waiting.id to 2), listOf(waiting))))
        val switched = ShoppingReducer.reduce(
            ShoppingReducer.reduce(global, ShoppingAction.StartNewMission), ShoppingAction.TurnOffers(listOf(computer)))
        assertEquals(listOf(computer), switched.cartGroups.flatMap { it.offers })
        assertEquals(listOf(waiting), switched.waitingOffers)
        assertEquals(mapOf(waiting.id to 2), switched.waitingQuantities)
    }

    @Test fun requoteAndConfirmationAlsoApplyToWaitingOffersOutsideTheCurrentMission() {
        val old = offer(QuoteState.EXPIRED).copy(productId = "earbuds", productTitle = "演示耳机")
        val fresh = old.copy(quoteState = QuoteState.CURRENT, productTitle = "", confirmedChange = false)
        val updated = ShoppingReducer.reduce(ShoppingUiState(waitingOffers = listOf(old)),
            ShoppingAction.OfferRequoted("earbuds", listOf(fresh)))
        assertEquals(QuoteState.CURRENT, updated.waitingOffers.single().quoteState)
        assertEquals("演示耳机", updated.waitingOffers.single().productTitle)
        val changed = ShoppingReducer.reduce(updated, ShoppingAction.QuoteRefreshRequired(old.id))
        assertFalse(changed.waitingOffers.single().mayResolve)
        val confirmed = ShoppingReducer.reduce(changed, ShoppingAction.ConfirmQuoteChange(old.id))
        assertTrue(confirmed.waitingOffers.single().mayResolve)
    }
    @Test fun cartReadbackReplacesRatherThanMergesRemovedItems() {
        val previous = ShoppingUiState(waitingOfferIds = setOf("old"), waitingQuantities = mapOf("old" to 1))
        val current = offer(QuoteState.EXPIRED).copy(id = "current")
        val updated = ShoppingReducer.reduce(previous, ShoppingAction.WaitingCartUpdated(WaitingCartUi(mapOf("current" to 2), listOf(current))))
        assertEquals(setOf("current"), updated.waitingOfferIds)
        assertEquals(mapOf("current" to 2), updated.waitingQuantities)
        assertEquals(listOf(current), updated.waitingOffers)
        val removed = ShoppingReducer.reduce(updated, ShoppingAction.WaitingCartUpdated(WaitingCartUi(emptyMap(), emptyList())))
        assertTrue(removed.waitingOfferIds.isEmpty())
        assertTrue(removed.waitingQuantities.isEmpty())
        assertTrue(removed.waitingOffers.isEmpty())
    }
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
        val online = ShoppingReducer.reduce(
            submitted,
            ShoppingAction.SetConnection(ConnectionState.ONLINE),
        )
        val decisions = ShoppingReducer.reduce(online, ShoppingAction.SelectTab(PrimaryTab.DECISIONS))
        assertEquals("预算 2000，通勤降噪", decisions.missionGoal)
        assertEquals(PrimaryTab.DECISIONS, decisions.selectedTab)
    }

    @Test
    fun recoveredMissionLocksNavigationUntilTheExplicitContinueAction() {
        val recovered = ShoppingReducer.reduce(
            ShoppingUiState(
                selectedTab = PrimaryTab.DECISIONS,
                connection = ConnectionState.ONLINE,
            ),
            ShoppingAction.SetConnection(ConnectionState.RECOVERED),
        )

        val ignoredSelection = ShoppingReducer.reduce(
            recovered,
            ShoppingAction.SelectTab(PrimaryTab.PROFILE),
        )
        val continued = ShoppingReducer.reduce(
            ignoredSelection,
            ShoppingAction.ContinueRecoveredMission,
        )
        val profile = ShoppingReducer.reduce(
            continued,
            ShoppingAction.SelectTab(PrimaryTab.PROFILE),
        )

        assertEquals(PrimaryTab.TASK, recovered.selectedTab)
        assertEquals(PrimaryTab.TASK, ignoredSelection.selectedTab)
        assertEquals(ConnectionState.ONLINE, continued.connection)
        assertEquals(PrimaryTab.PROFILE, profile.selectedTab)
    }

    @Test
    fun returningForRequoteOpensTaskAndPrefillsCurrentMission() {
        val state = ShoppingUiState(
            selectedTab = PrimaryTab.DECISIONS,
            missionGoal = "预算 1000 元的通勤耳机",
            comparedProductIds = setOf("product-1"),
            products = listOf(
                EvidenceProductUi(
                    id = "product-1",
                    variantId = "variant-1",
                    title = "Fixture Headphones",
                    fitSummary = "符合通勤需求",
                    matchedConstraints = listOf("预算内"),
                    unmetConstraints = emptyList(),
                    risks = emptyList(),
                    evidenceRefs = listOf("demo:product-1"),
                ),
            ),
        )

        val returned = ShoppingReducer.reduce(state, ShoppingAction.ReturnToMissionConversation)

        assertEquals(PrimaryTab.TASK, returned.selectedTab)
        assertEquals(state.missionGoal, returned.draft)
        assertEquals(state.products, returned.products)
        assertEquals(state.comparedProductIds, returned.comparedProductIds)
        assertTrue(returned.showConversation)
        val reopened = ShoppingReducer.reduce(returned, ShoppingAction.ShowCurrentRecommendations)
        assertFalse(reopened.showConversation)
        assertEquals(state.products, reopened.products)
        assertEquals(state.comparedProductIds, reopened.comparedProductIds)
        assertEquals(returned.draft, reopened.draft)
        val next = ShoppingReducer.reduce(returned, ShoppingAction.TurnProducts(state.products))
        assertFalse(next.showConversation)
    }

    @Test
    fun startingNewMissionClearsOnlyMissionState() {
        val saved = com.ragcommerce.agent.ui.SavedProductUi("product-1", "候选", "demo:product-1")
        val watcher = com.ragcommerce.agent.ui.WatcherUi(
            "watcher-1",
            "offer-1",
            "PRICE_BELOW",
            90000,
            "不会后台提醒",
        )
        val state = ShoppingUiState(
            selectedTab = PrimaryTab.DECISIONS,
            missionGoal = "旧购物任务",
            draft = "旧购物任务",
            products = listOf(product()),
            savedProducts = listOf(saved),
            waitingOfferIds = setOf("offer-1"),
            watchers = listOf(watcher),
        )

        val fresh = ShoppingReducer.reduce(state, ShoppingAction.StartNewMission)

        assertEquals(PrimaryTab.TASK, fresh.selectedTab)
        assertEquals("", fresh.missionGoal)
        assertEquals("", fresh.draft)
        assertTrue(fresh.products.isEmpty())
        assertEquals(listOf(saved), fresh.savedProducts)
        assertEquals(setOf("offer-1"), fresh.waitingOfferIds)
        assertEquals(listOf(watcher), fresh.watchers)
    }

    @Test
    fun clarificationPromptPrefillsAnEditableAnswerWithoutSubmitting() {
        val clarifying = ShoppingReducer.reduce(
            ShoppingUiState(isLoading = true),
            ShoppingAction.ClarificationRequired("请补充预算。"),
        )

        val drafted = ShoppingReducer.reduce(
            clarifying,
            ShoppingAction.UseClarificationPrompt("我的预算是："),
        )

        assertEquals("请补充预算。", drafted.clarificationQuestion)
        assertEquals("我的预算是：", drafted.draft)
        assertFalse(drafted.isLoading)
        assertEquals("", drafted.missionGoal)
    }

    @Test
    fun typedMissionUpdateReplacesThePublicGoal() {
        val mission = com.ragcommerce.agent.ui.ShoppingMissionUi(
            goal = "预算 1000 元的通勤耳机",
            version = 2,
            items = listOf(com.ragcommerce.agent.ui.MissionItemUi("耳机", 1)),
            hardConstraints = listOf("预算 1000 元"),
            softPreferences = listOf("通勤降噪"),
            unknowns = emptyList(),
            budgetTotalMinor = 100000,
        )
        val state = ShoppingReducer.reduce(
            ShoppingUiState(missionGoal = "旧目标"),
            ShoppingAction.MissionUpdated(mission),
        )
        assertEquals("预算 1000 元的通勤耳机", state.missionGoal)
        assertEquals(2, state.mission?.version)
        assertEquals("Mission 已更新", state.statusMessage)
    }

    @Test
    fun editedMissionWaitsForExplicitRecalculation() {
        val mission = com.ragcommerce.agent.ui.ShoppingMissionUi(
            goal = "预算 1000 元的通勤耳机",
            version = 1,
            items = listOf(com.ragcommerce.agent.ui.MissionItemUi("耳机", 1)),
            hardConstraints = emptyList(),
            softPreferences = listOf("通勤"),
            unknowns = emptyList(),
            budgetTotalMinor = 100000,
        )
        val opened = ShoppingReducer.reduce(
            ShoppingUiState(missionGoal = mission.goal, mission = mission),
            ShoppingAction.BeginMissionEdit,
        )
        val typed = ShoppingReducer.reduce(
            opened,
            ShoppingAction.UpdateMissionEdit("预算 1200 元，通勤降噪必须好"),
        )
        val saved = ShoppingReducer.reduce(typed, ShoppingAction.ApplyMissionEdit)

        assertEquals("预算 1200 元，通勤降噪必须好", saved.missionGoal)
        assertEquals(1, saved.mission?.version)
        assertTrue(saved.pendingMissionRecalculation)
        assertFalse(saved.isLoading)
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
    fun comparisonResultDoesNotPretendAgentCandidatesWereUserSelected() {
        val state = ShoppingReducer.reduce(
            ShoppingUiState(),
            ShoppingAction.TurnComparison(
                com.ragcommerce.agent.ui.ComparisonUi(
                    items = listOf("product-1", "product-2"),
                    dimensions = listOf("价格"),
                    missingFields = emptyList(),
                    evidenceRefs = listOf("demo:comparison"),
                ),
            ),
        )

        assertTrue(state.comparison != null)
        assertTrue(state.comparedProductIds.isEmpty())
    }

    @Test
    fun comparisonSortChangesOnlyTheDecisionOrderingPreference() {
        val original = ShoppingUiState(comparedProductIds = setOf("product-1", "product-2"))
        val sorted = ShoppingReducer.reduce(
            original,
            ShoppingAction.SetComparisonSort(ComparisonSort.BUDGET),
        )

        assertEquals(ComparisonSort.BUDGET, sorted.comparisonSort)
        assertEquals(original.comparedProductIds, sorted.comparedProductIds)
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

    private fun product() = EvidenceProductUi(
        id = "product-1",
        variantId = "variant-1",
        title = "Fixture Headphones",
        fitSummary = "符合通勤需求",
        matchedConstraints = listOf("预算内"),
        unmetConstraints = emptyList(),
        risks = emptyList(),
        evidenceRefs = listOf("demo:product-1"),
    )

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
