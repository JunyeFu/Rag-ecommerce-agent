package com.ragcommerce.agent

import com.ragcommerce.agent.ui.*
import org.junit.Assert.*
import org.junit.Test

class DecisionExperienceTest {
    private val product = EvidenceProductUi("p", "v", "演示电脑", "", emptyList(), emptyList(), emptyList(), listOf("demo:p"))

    @Test fun missingFailureListIsNotProofOfSatisfaction() {
        val mission = ShoppingMissionUi("办公", 1, emptyList(), listOf("至少16GB内存"), emptyList(), emptyList(), null)
        assertEquals("1 项待核实", constraintVerdict(product, mission))
        assertEquals("1 项已核实满足", constraintVerdict(product.copy(matchedConstraints = listOf("至少16GB内存")), mission))
        assertEquals("未设置硬约束", constraintVerdict(product, null))
    }

    @Test fun approvalCannotInventOrGuessItsTarget() {
        assertNull(approvalTargetSummary("cart.update", mapOf("offer_id" to "unknown", "quantity" to "2", "operation" to "set"), ShoppingUiState()))
        val state = ShoppingReducer.reduce(ShoppingUiState(), ShoppingAction.ApprovalRequired("list.update", mapOf("variant_id" to "v", "operation" to "add")))
        assertEquals("v", state.pendingApprovalArguments["variant_id"])
        assertEquals("演示电脑 · 加入保存", approvalTargetSummary("list.update", state.pendingApprovalArguments, state.copy(products = listOf(product))))
    }

    @Test fun newMissionClearsTaskScopedFeedbackAndAuthorization() {
        val old = ShoppingUiState(feedback = mapOf("PRODUCT:p" to "不适合"), recommendationIndex = 2,
            pendingApprovalTool = "list.update", pendingApprovalArguments = mapOf("variant_id" to "v"),
            preparedMerchantOfferId = "offer", preparedMerchantHost = "demo.invalid", conversationVisible = true)
        val fresh = ShoppingReducer.reduce(old, ShoppingAction.StartNewMission)
        assertTrue(fresh.feedback.isEmpty())
        assertTrue(fresh.pendingApprovalArguments.isEmpty())
        assertNull(fresh.preparedMerchantHost)
        assertFalse(fresh.conversationVisible)
        assertEquals(0, fresh.recommendationIndex)
    }

    @Test fun returningToConversationPreservesCandidatePageAndSelection() {
        val state = ShoppingUiState(products = listOf(product), comparedProductIds = setOf("p"))
        val browsed = ShoppingReducer.reduce(state, ShoppingAction.RecommendationPageChanged(2))
        val returned = ShoppingReducer.reduce(browsed, ShoppingAction.ReturnToMissionConversation)
        assertEquals(2, returned.recommendationIndex)
        assertEquals(setOf("p"), returned.comparedProductIds)
        assertEquals(0, ShoppingReducer.reduce(returned, ShoppingAction.TurnProducts(listOf(product.copy(id = "new")))).recommendationIndex)
    }
}
