package com.ragcommerce.agent

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModelStore
import com.ragcommerce.agent.data.*
import com.ragcommerce.agent.ui.*
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.test.*
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.*
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

/** Repository replaces the remote API/local persistence boundary, not UI state. */
@OptIn(ExperimentalCoroutinesApi::class)
class ShoppingApprovalStateTest {
    @Test fun newMissionPersistenceCannotUndoLaterUserNavigation() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val persisted = CompletableDeferred<Unit>()
        val repository = object : ShoppingRepository by ApprovalRepository() {
            override fun observeLocal() = MutableStateFlow(LocalShoppingSnapshot(null, emptyList(), "TASK", null, null, 0, false))
            override suspend fun startNewMission() { persisted.await() }
            override suspend fun saveSelectedTab(value: String) = Unit
        }
        val store = ViewModelStore()
        try {
            val model = ShoppingViewModel(SavedStateHandle(), repository)
            store.put("navigation", model); runCurrent()
            model.dispatch(ShoppingAction.StartNewMission); runCurrent()
            model.dispatch(ShoppingAction.SelectTab(PrimaryTab.DECISIONS)); runCurrent()
            persisted.complete(Unit); runCurrent()
            assertEquals(PrimaryTab.DECISIONS, model.state.value.selectedTab)
        } finally { store.clear(); Dispatchers.resetMain() }
    }

    private fun savedProduct(id: String, category: String = "耳机") = EvidenceProductUi(id, "v-$id", "商品$id", "", emptyList(), emptyList(), emptyList(), listOf("catalog:$id"), attributes = mapOf("续航" to "30小时"), category = category)

    @Test fun savedComparisonRequiresTwoToFourDistinctProductsOfOneKnownCategory() {
        val products = (1..5).map { savedProduct("$it") }
        assertEquals(4, SavedComparisonUi.create(products.take(4), emptyList()).products.size)
        listOf(products.take(1), products, listOf(products[0], products[0]),
            listOf(products[0], savedProduct("other", "手机")),
            listOf(savedProduct("unknown", ""), savedProduct("also-unknown", ""))).forEach { invalid ->
            assertThrows(SavedComparisonSelectionException::class.java) { SavedComparisonUi.create(invalid, emptyList()) }
        }
    }

    @Test fun savedComparisonSelectionIsIndependentAndLimitedToFourSavedProducts() {
        val saved = (1..5).map { SavedProductUi("$it", "商品$it", "catalog:$it") }
        var state = ShoppingUiState(savedProducts = saved, comparedProductIds = setOf("mission"))
        (1..5).forEach { state = ShoppingReducer.reduce(state, ShoppingAction.ToggleSavedComparison("$it")) }
        assertEquals(setOf("1", "2", "3", "4"), state.savedComparisonIds)
        assertEquals(setOf("mission"), state.comparedProductIds)
        state = ShoppingReducer.reduce(state, ShoppingAction.StartNewMission)
        assertEquals(4, state.savedComparisonIds.size)
        state = ShoppingReducer.reduce(state, ShoppingAction.ToggleSavedComparison("1"))
        assertEquals(setOf("2", "3", "4"), state.savedComparisonIds)
    }

    @Test fun savedComparisonRestoresWithoutAnActiveMissionAndClearKeepsSavedAndWaiting() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val comparison = SavedComparisonUi.create(listOf(savedProduct("1"), savedProduct("2")), emptyList())
        var cleared = false
        val local = MutableStateFlow(LocalShoppingSnapshot(null, emptyList(), "DECISIONS", null, null, 0, false))
        val repository = object : ShoppingRepository by ApprovalRepository() {
            override fun observeLocal() = local
            override suspend fun restoreSavedComparison() = comparison
            override suspend fun clearSavedComparison() { cleared = true }
        }
        val store = ViewModelStore()
        try {
            val model = ShoppingViewModel(SavedStateHandle(), repository)
            store.put("comparison", model); runCurrent()
            assertEquals(comparison, model.state.value.savedComparison)
            assertEquals(setOf("1", "2"), model.state.value.savedComparisonIds)
            val waiting = model.state.value.waitingOffers
            model.dispatch(ShoppingAction.ClearSavedComparison); runCurrent()
            assertTrue(cleared)
            assertNull(model.state.value.savedComparison)
            assertTrue(model.state.value.savedComparisonIds.isEmpty())
            assertEquals(waiting, model.state.value.waitingOffers)
        } finally { store.clear(); Dispatchers.resetMain() }
    }

    @Test fun openingSavedFactsDoesNotReplaceCurrentMissionOffers() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val product = EvidenceProductUi("saved", "variant", "已保存耳机", "", emptyList(), emptyList(), emptyList(), listOf("catalog:saved"), category = "耳机")
        val offer = OfferUi("saved-offer", "saved", "variant", "演示商家", "¥100", null, "DEMO_FIXTURE", "2026-10-22T00:00:00Z", "2026-10-22T01:00:00Z", "fixture:saved", QuoteState.EXPIRED, "演示报价")
        val repository = object : ShoppingRepository by ApprovalRepository() {
            override fun observeLocal() = MutableStateFlow(LocalShoppingSnapshot(null, emptyList(), "TASK", null, null, 0, false))
            override suspend fun productFacts(productId: String) = product
            override suspend fun productOffers(product: EvidenceProductUi) = listOf(offer)
        }
        val store = ViewModelStore()
        try {
            val model = ShoppingViewModel(SavedStateHandle(), repository)
            store.put("saved", model); runCurrent()
            model.dispatch(ShoppingAction.TurnOffers(listOf(offer.copy(id = "mission-offer", productId = "mission"))))
            val original = model.state.value.cartGroups
            model.dispatch(ShoppingAction.OpenSaved("saved")); runCurrent()
            assertEquals(product, model.state.value.savedDetail)
            assertEquals("opening a saved item must not change task offers", original, model.state.value.cartGroups)
        } finally { store.clear(); Dispatchers.resetMain() }
    }

    @Test fun staleLocalRunCannotTakeOverAnExplicitlyOwnedStream() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val local = MutableStateFlow(LocalShoppingSnapshot(null, emptyList(), "TASK", null, null, 0, false))
        val finish = CompletableDeferred<Unit>()
        val observed = mutableListOf<String>()
        val repository = object : ShoppingRepository by ApprovalRepository() {
            override fun observeLocal() = local
            override suspend fun explore(action: ShoppingAction.Explore, version: Int): TurnAcceptedRemote {
                local.value = local.value.copy(pendingRunId = "current")
                return TurnAcceptedRemote("current", false)
            }
            override fun observeEvents(runId: String, lastEventId: Long) = flow {
                observed += runId
                if (runId == "current") finish.await()
                emit(AgentPublicEvent(11, "completed", emptyMap()))
            }
        }
        val store = ViewModelStore()
        try {
            val model = ShoppingViewModel(SavedStateHandle(), repository)
            store.put("stream", model)
            runCurrent()
            model.dispatch(ShoppingAction.Explore("start"))
            runCurrent()
            // Room/DataStore combine may deliver an older pending-run snapshot
            // while the newly accepted stream already has its explicit owner.
            local.value = local.value.copy(pendingRunId = "older", lastEventId = 10)
            runCurrent()
            assertEquals(listOf("current"), observed)
            finish.complete(Unit)
            runCurrent()
            assertFalse(model.state.value.isLoading)
            assertEquals(ConnectionState.ONLINE, model.state.value.connection)
        } finally {
            store.clear()
            Dispatchers.resetMain()
        }
    }

    @Test fun localApprovalSnapshotCannotInterruptAnInFlightDecision() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val repository = ApprovalRepository()
        val store = ViewModelStore()
        try {
            val model = ShoppingViewModel(SavedStateHandle(), repository)
            store.put("approval", model)
            runCurrent()
            assertEquals("cart.update", model.state.value.pendingApprovalTool)
            model.dispatch(ShoppingAction.ResolveApproval(true))
            runCurrent()
            repository.local.value = repository.local.value.copy(lastEventId = 4)
            runCurrent()
            assertTrue("a stale local approval must not cancel the busy state", model.state.value.isLoading)
            model.dispatch(ShoppingAction.ResolveApproval(true))
            runCurrent()
            assertEquals(1, repository.decisions)
            repository.finished.complete(Unit)
            runCurrent()
            assertFalse(model.state.value.isLoading)
            assertNull(model.state.value.pendingApprovalTool)
            assertEquals(2, model.state.value.waitingQuantities["offer"])
            assertEquals(ConnectionState.ONLINE, model.state.value.connection)
        } finally {
            store.clear()
            Dispatchers.resetMain()
        }
    }

    @Test fun rejectedHttpDecisionExposesRecoveryWithoutResubmittingApproval() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val repository = ApprovalRepository(httpRejected = true)
        val store = ViewModelStore()
        try {
            val model = ShoppingViewModel(SavedStateHandle(), repository)
            store.put("approval", model)
            runCurrent()
            model.dispatch(ShoppingAction.ResolveApproval(true))
            runCurrent()
            assertEquals(ConnectionState.OFFLINE, model.state.value.connection)
            assertTrue(model.state.value.showConversation)
            assertFalse(model.state.value.isLoading)
            assertNull(model.state.value.pendingApprovalTool)
            assertEquals(1, repository.decisions)
        } finally {
            store.clear()
            Dispatchers.resetMain()
        }
    }

    private class ApprovalRepository(val httpRejected: Boolean = false) : ShoppingRepository {
        override suspend fun history(): List<com.ragcommerce.agent.generated.ThreadHistoryEntry> = error("not used")
        override suspend fun organizeThread(threadId: String, title: String?, archived: Boolean?) = error("not used")
        override suspend fun activateThread(threadId: String) = error("not used")
        override suspend fun messages(offset: Int): List<com.ragcommerce.agent.generated.ConversationMessage> = error("not used")
        override suspend fun candidateFeedback(action: ShoppingAction.ExcludeCandidate, version: Int): RemoteThreadSnapshot = error("not used")
        override suspend fun undoCandidateFeedback(key: String, version: Int): RemoteThreadSnapshot = error("not used")
        override suspend fun productFacts(productId: String): EvidenceProductUi = error("not used")
        override suspend fun productOffers(product: EvidenceProductUi): List<OfferUi> = error("not used")
        override suspend fun refreshSavedCandidates() = Unit
        override suspend fun removeSavedCandidate(productId: String) = error("not used")
        override suspend fun compareSavedProducts(productIds: Set<String>): SavedComparisonUi = error("not used")
        override suspend fun restoreSavedComparison(): SavedComparisonUi? = null
        override suspend fun clearSavedComparison() = Unit
        val local = MutableStateFlow(LocalShoppingSnapshot(null, emptyList(), "TASK", "run", "cart.update", 3, false))
        val finished = CompletableDeferred<Unit>()
        var decisions = 0
        override fun observeLocal() = local
        override suspend fun probeConnection() = true
        override suspend fun restoreThread(): RemoteThreadSnapshot? = null
        override suspend fun waitingCart() = WaitingCartUi(if (finished.isCompleted) mapOf("offer" to 2) else emptyMap(), emptyList())
        override suspend fun decide(runId: String, tool: String, approved: Boolean) {
            check(runId == "run" && tool == "cart.update" && approved)
            decisions++
            if (httpRejected) throw HttpException(Response.error<Unit>(409, "{}".toResponseBody()))
            finished.await()
            local.value = local.value.copy(pendingApprovalTool = null)
        }
        override suspend fun readEvents(runId: String, lastEventId: Long): List<AgentPublicEvent> {
            // Same persistence semantics as terminal events in NetworkShoppingRepository.
            local.value = local.value.copy(pendingRunId = null, pendingApprovalTool = null)
            return listOf(AgentPublicEvent(5, "completed", emptyMap()))
        }
        override suspend fun saveMission(goal: String) = error("not used")
        override suspend fun saveSelectedTab(value: String) = error("not used")
        override suspend fun setQualityDataConsent(granted: Boolean) = error("not used")
        override suspend fun submitTurn(text: String, media: List<MediaAttachmentInput>): TurnAcceptedRemote = error("not used")
        override suspend fun confirmMedia(sourceRunId: String, text: String, version: Int): TurnAcceptedRemote = error("not used")
        override suspend fun explore(action: ShoppingAction.Explore, version: Int): TurnAcceptedRemote = error("not used")
        override suspend fun startNewMission() = error("not used")
        override suspend fun updateMissionConstraints(goal: String): ShoppingMissionUi = error("not used")
        override suspend fun updateComparisonSelection(productIds: Set<String>): Set<String> = error("not used")
        override suspend fun resolveOffer(offerId: String, confirmedQuoteChange: Boolean): MerchantResolution = error("not used")
        override suspend fun requoteOffer(offer: OfferUi): List<OfferUi> = error("not used")
        override suspend fun saveProduct(product: EvidenceProductUi) = error("not used")
        override suspend fun updateOfferQuantity(offer: OfferUi, quantity: Int): WaitingCartUi = error("not used")
        override suspend fun createWatcher(offer: OfferUi, kind: String, thresholdMinor: Long?): WatcherUi = error("not used")
        override suspend fun deleteMyData() = error("not used")
    }
}
