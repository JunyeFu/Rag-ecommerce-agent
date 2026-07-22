import pytest
from app.services.agent import route_after_intent


@pytest.mark.unit
class TestRouteAfterIntent:
    def _make_state(self, **overrides):
        base = {
            "query": "推荐蓝牙耳机",
            "intent": "commodity_recommend",
            "slots": {"category": "耳机", "attributes": {"降噪": "是"}},
            "history": [],
            "session_id": "test-session",
            "confidence": 0.8,
        }
        base.update(overrides)
        return base

    # ── Direct intent branches (early returns) ──

    def test_chitchat_routes_to_generate(self):
        state = self._make_state(intent="chitchat")
        assert route_after_intent(state) == "generate"

    def test_web_search_routes_to_web_search(self):
        state = self._make_state(intent="web_search")
        assert route_after_intent(state) == "web_search"

    def test_compare_routes_to_compare(self):
        state = self._make_state(intent="commodity_compare")
        assert route_after_intent(state) == "compare"

    def test_cart_routes_to_cart(self):
        state = self._make_state(intent="cart_operation")
        assert route_after_intent(state) == "cart"

    # ── commodity_recommend -> retrieve (has enough info) ──

    def test_recommend_with_category_and_attrs_routes_to_retrieve(self):
        state = self._make_state(
            query="推荐蓝牙耳机",
            slots={"category": "耳机", "attributes": {"降噪": "是"}},
            confidence=0.8,
        )
        assert route_after_intent(state) == "retrieve"

    def test_recommend_with_budget_routes_to_retrieve(self):
        state = self._make_state(
            query="推荐耳机",
            slots={"category": "耳机", "price_max": 500},
            confidence=0.7,
        )
        assert route_after_intent(state) == "retrieve"

    def test_recommend_with_scenario_routes_to_retrieve(self):
        state = self._make_state(
            query="送女朋友生日礼物",
            intent="scenario_shopping",
            slots={"scenario": "生日礼物"},
            confidence=0.7,
        )
        assert route_after_intent(state) == "retrieve"

    def test_explicit_intent_keyword_bypasses_short_category(self):
        state = self._make_state(
            query="推荐手机",
            slots={"category": "手机"},
            confidence=0.6,
        )
        assert route_after_intent(state) == "retrieve"

    # ── ultra_vague detection ──

    def test_ultra_vague_short_query_routes_to_clarify(self):
        state = self._make_state(query="嗯", slots={}, confidence=0.5)
        assert route_after_intent(state) == "clarify"

    def test_ultra_vague_keyword_routes_to_clarify(self):
        state = self._make_state(query="推荐", slots={}, confidence=0.6)
        assert route_after_intent(state) == "clarify"

    def test_ultra_vague_buy_keyword_routes_to_clarify(self):
        state = self._make_state(query="买什么", slots={}, confidence=0.5)
        assert route_after_intent(state) == "clarify"

    def test_empty_query_routes_to_clarify(self):
        state = self._make_state(query="", slots={}, confidence=0.5)
        assert route_after_intent(state) == "clarify"

    # ── History bypass ──

    def test_ultra_vague_with_history_bypasses_clarify(self):
        state = self._make_state(
            query="嗯",
            slots={},
            confidence=0.5,
            history=[
                {"role": "user", "content": "推荐耳机"},
                {"role": "assistant", "content": "好的"},
            ],
        )
        assert route_after_intent(state) == "retrieve"

    def test_short_query_with_history_bypasses_clarify(self):
        state = self._make_state(
            query="手机壳套",
            slots={"category": "手机壳"},
            confidence=0.6,
            history=[
                {"role": "user", "content": "推荐手机壳"},
                {"role": "assistant", "content": "好的"},
            ],
        )
        assert route_after_intent(state) == "retrieve"

    def test_history_bypass_requires_at_least_two_messages(self):
        state = self._make_state(
            query="嗯",
            slots={},
            confidence=0.5,
            history=[
                {"role": "user", "content": "推荐耳机"},
            ],
        )
        assert route_after_intent(state) == "clarify"

    # ── missing_everything detection ──

    def test_missing_everything_routes_to_clarify(self):
        state = self._make_state(
            query="推荐耳机",
            slots={"missing_slots": ["category"]},
            confidence=0.6,
        )
        assert route_after_intent(state) == "clarify"

    def test_missing_slots_but_has_category_routes_to_retrieve(self):
        state = self._make_state(
            query="推荐耳机",
            slots={"missing_slots": ["brand"], "category": "耳机"},
            confidence=0.6,
        )
        assert route_after_intent(state) == "retrieve"

    # ── short_category_only detection ──

    def test_short_category_only_routes_to_clarify(self):
        state = self._make_state(
            query="手机壳套",
            slots={"category": "手机壳"},
            confidence=0.6,
        )
        assert route_after_intent(state) == "clarify"

    def test_short_category_with_explicit_intent_routes_to_retrieve(self):
        state = self._make_state(
            query="买手机壳",
            slots={"category": "手机壳"},
            confidence=0.6,
        )
        assert route_after_intent(state) == "retrieve"

    # ── low_confidence guard ──

    def test_low_confidence_routes_to_clarify(self):
        state = self._make_state(
            query="推荐耳机",
            slots={"category": "耳机"},
            confidence=0.3,
        )
        assert route_after_intent(state) == "clarify"

    def test_low_confidence_non_recommend_routes_to_retrieve(self):
        state = self._make_state(
            query="送什么生日礼物",
            intent="scenario_shopping",
            slots={"scenario": "生日"},
            confidence=0.3,
        )
        assert route_after_intent(state) == "retrieve"

    # ── anti_selection is non-shopping -> always retrieve ──

    def test_anti_selection_routes_to_retrieve(self):
        state = self._make_state(
            query="不要入耳式的",
            intent="anti_selection",
            slots={},
            confidence=0.5,
        )
        assert route_after_intent(state) == "retrieve"

    def test_anti_selection_ultra_vague_still_retrieve(self):
        state = self._make_state(
            query="嗯",
            intent="anti_selection",
            slots={},
            confidence=0.3,
        )
        assert route_after_intent(state) == "retrieve"

    # ── Default confidence ──

    def test_default_confidence_is_0_5(self):
        state = self._make_state(
            query="推荐耳机",
            slots={"category": "耳机"},
        )
        del state["confidence"]
        assert route_after_intent(state) == "retrieve"

    # ── Missing slots key ──

    def test_missing_slots_key_defaults_to_empty(self):
        state = self._make_state(
            query="推荐耳机",
            slots={"category": "耳机"},
            confidence=0.7,
        )
        assert route_after_intent(state) == "retrieve"

    # ── Long query with enough info ──

    def test_long_query_with_full_info_routes_to_retrieve(self):
        state = self._make_state(
            query="推荐一款3000元以内的降噪蓝牙耳机",
            slots={"category": "耳机", "price_max": 3000, "attributes": {"降噪": "是", "蓝牙": "是"}},
            confidence=0.9,
        )
        assert route_after_intent(state) == "retrieve"
