import pytest
pytestmark = pytest.mark.unit

import pytest

from app.services import agent
from app.services.agent import (
    _apply_history_category_hint,
    _build_rewrite_base,
    _infer_explicit_category_from_text,
    _infer_category_from_query,
    _persist_dialog_context,
    _previous_slots_from_state,
    _prune_previous_slots_for_category_change,
    _update_category_context,
)


def test_previous_slots_reads_nested_state():
    state = {"slots": {"category": "平板", "exclude_by_category": {"平板": ["Apple"]}}}

    assert _previous_slots_from_state(state)["category"] == "平板"
    assert _previous_slots_from_state(state)["exclude_by_category"] == {"平板": ["Apple"]}


def test_previous_slots_reads_legacy_top_level_state():
    state = {"category": "平板", "price_max": 3000}

    slots = _previous_slots_from_state(state)

    assert slots["category"] == "平板"
    assert slots["price_max"] == 3000


def test_nested_slots_win_over_legacy_top_level_state():
    state = {"slots": {"category": "平板"}, "category": "手机"}

    assert _previous_slots_from_state(state)["category"] == "平板"


def test_category_context_overrides_stale_slots_category():
    state = {
        "slots": {"category": "手机", "exclude_by_category": {"手机": ["Apple"]}},
        "category_context": {"current_category": "衣服"},
    }

    assert _previous_slots_from_state(state)["category"] == "衣服"


def test_category_context_keeps_preference_map():
    context = _update_category_context(
        {"current_category": "手机", "category_preferences": {"手机": {"brand_preference": "Apple"}}},
        {"category": "鞋", "attributes": {"耐穿": "是"}},
    )

    assert context["current_category"] == "鞋"
    assert context["category_preferences"]["手机"]["brand_preference"] == "Apple"
    assert context["category_preferences"]["鞋"]["attributes"] == {"耐穿": "是"}


def test_negation_rewrite_base_uses_inherited_category():
    base = _build_rewrite_base(
        query="排除 Apple",
        expanded="排除 Apple",
        slots={"category": "平板", "exclude_by_category": {"平板": ["Apple"]}},
        has_negation=True,
        negation={"positive_query": "Apple"},
    )

    assert base == "平板 热门推荐 同类商品"


def test_category_change_prunes_category_specific_preferences():
    prev = {
        "category": "手机",
        "brand_preference": "Apple",
        "attributes": {"性能": "强"},
        "scenario": "拍照",
        "price_max": 3000,
        "exclude_brands": ["Huawei"],
        "exclude_attributes": {"颜色": "黑色"},
        "exclude_text_terms": ["苹果"],
        "exclude_by_category": {"手机": ["Apple"]},
    }

    pruned = _prune_previous_slots_for_category_change(prev, {"category": "手表"})

    assert pruned["price_max"] == 3000
    assert pruned["exclude_by_category"] == {"手机": ["Apple"]}
    assert "category" not in pruned
    assert "brand_preference" not in pruned
    assert "attributes" not in pruned
    assert "exclude_brands" not in pruned
    assert "exclude_text_terms" not in pruned


def test_equivalent_category_keeps_preferences():
    prev = {"category": "手表", "brand_preference": "Huawei", "attributes": {"续航": "长"}}

    kept = _prune_previous_slots_for_category_change(prev, {"category": "智能手表"})

    assert kept == prev


def test_food_followup_infers_snack_category_without_inheriting_phone():
    assert _infer_category_from_query("好吃又便宜的") == "零食"

    prev = {"category": "手机", "exclude_brands": ["Apple"], "brand_preference": "iQOO"}
    pruned = _prune_previous_slots_for_category_change(prev, {"category": "零食"})

    assert "category" not in pruned
    assert "exclude_brands" not in pruned
    assert "brand_preference" not in pruned


def test_food_words_do_not_override_explicit_digital_category():
    assert _infer_category_from_query("好吃又便宜的华为手表") is None


def test_explicit_category_hint_normalizes_common_generic_terms():
    assert _infer_explicit_category_from_text("推荐鞋") == "鞋"
    assert _infer_explicit_category_from_text("推荐衣服") == "衣服"


def test_history_category_hint_recovers_from_previous_user_turn():
    slots = {}

    _apply_history_category_hint(
        slots,
        [
            {"role": "user", "content": "推荐鞋"},
            {"role": "assistant", "content": "本地没找到，我帮你联网搜索。"},
            {"role": "user", "content": "好看又耐穿的"},
        ],
    )

    assert slots["category"] == "鞋"


@pytest.mark.asyncio
async def test_persist_dialog_context_updates_category_before_result_success(monkeypatch):
    calls = []

    async def fake_update_state(conversation_id, **kwargs):
        calls.append((conversation_id, kwargs))
        return kwargs

    monkeypatch.setattr(agent.sm, "update_state", fake_update_state)

    state = {
        "intent": "commodity_recommend",
        "slots": {"category": "鞋", "attributes": {"耐穿": "是"}},
        "category_context": {"current_category": "手机"},
        "_category_changed": True,
    }

    await _persist_dialog_context("conv-1", state)

    assert calls[0][0] == "conv-1"
    assert calls[0][1]["slots"]["category"] == "鞋"
    assert calls[0][1]["category_context"]["current_category"] == "鞋"
    assert calls[0][1]["product_cards"] == []
