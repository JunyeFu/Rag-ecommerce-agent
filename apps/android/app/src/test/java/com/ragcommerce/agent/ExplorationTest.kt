package com.ragcommerce.agent

import com.ragcommerce.agent.data.parseExploration
import com.ragcommerce.agent.generated.ExplorationState
import com.ragcommerce.agent.ui.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ExplorationTest {
    @Test fun transitionClearsCurrentDecisionButPreservesSavedItems() {
        val saved = SavedProductUi("p", "saved", "demo:source")
        val before = ShoppingUiState(savedProducts = listOf(saved), waitingOfferIds = setOf("offer"),
            pendingApprovalTool = "cart.update", comparedProductIds = setOf("p"), draft = "old")
        val after = ShoppingReducer.reduce(before, ShoppingAction.ExplorationUpdated("DISCOVERY", ExplorationState()))
        assertNull(after.pendingApprovalTool)
        assertTrue(after.comparedProductIds.isEmpty())
        assertEquals(listOf(saved), after.savedProducts)
        assertEquals(setOf("offer"), after.waitingOfferIds)
        assertEquals("", after.draft)
        val fresh = ShoppingReducer.reduce(after, ShoppingAction.StartNewMission)
        assertEquals("PURCHASE", fresh.mode)
        assertNull(fresh.exploration)
    }

    @Test fun feedbackAndDirectionEvidenceAreParsedFromServerState() {
        val parsed = parseExploration(JSONObject("""{
          "directions":[{"direction_id":"耳机:专注学习","title":"专注学习","category":"耳机",
            "experience_tags":["life_improvement"],"evidence_refs":["demo:v3:x"],"supporting_product_ids":["x"]}],
          "feedback":{"耳机:专注学习":"not_interested"},"shown_direction_ids":["耳机:专注学习"],
          "shown_product_ids":["x"],"experience_tags":[],"selected_direction_id":null,
          "exhausted":false,"ended":false
        }"""))
        assertEquals("not_interested", parsed.feedback["耳机:专注学习"])
        assertEquals(listOf("demo:v3:x"), parsed.directions.single().evidence_refs)
    }

    @Test(expected = org.json.JSONException::class)
    fun invalidExplorationDoesNotBecomeEmptySuccess() { parseExploration(JSONObject("{}")) }
}
