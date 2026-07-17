"""Natural-language cart helper tests."""

import pytest

from types import SimpleNamespace

from app.services.agent import (
    _cart_item_matches_query,
    _extract_cart_item_index,
    _extract_cart_action,
    _extract_cart_item_indices,
    _find_product_for_cart,
    _find_products_for_multi_cart,
    _parse_quantity,
    _parse_quantity_delta,
)


def test_cart_quantity_action_detection():
    assert _extract_cart_action("把第一个数量改成2") == "quantity"
    assert _parse_quantity("把第一个数量改成2") == 2


def test_cart_add_is_not_misclassified_as_quantity():
    assert _extract_cart_action("把第一个加到购物车") == "add"


def test_cart_quantity_chinese_number():
    assert _parse_quantity("第二个改为两件") == 2


def test_cart_quantity_natural_phrases():
    assert _extract_cart_action("把购物车里第一个改到3件") == "quantity"
    assert _parse_quantity("把购物车里第一个改到3件") == 3
    assert _extract_cart_action("购物车里耳机数量调整为2") == "quantity"
    assert _parse_quantity("购物车里耳机数量调整为2") == 2
    assert _extract_cart_action("第一个买两件") == "quantity"
    assert _parse_quantity("第一个买两件") == 2
    assert _extract_cart_action("第一个加一件") == "quantity"
    assert _parse_quantity_delta("第一个加一件") == 1
    assert _extract_cart_action("第一个减一件") == "quantity"
    assert _parse_quantity_delta("第一个减一件") == -1
    assert _extract_cart_action("购物车里的商品全部减少为一件") == "quantity"
    assert _parse_quantity("购物车里的商品全部减少为一件") == 1


def test_cart_quantity_multi_item_indices():
    assert _extract_cart_item_indices("第二第三个减少两件", 3) == ([1, 2], None)
    assert _extract_cart_item_indices("购物车里的商品全部减少为一件", 3) == ([0, 1, 2], None)
    assert _extract_cart_item_indices("前两个都改成一件", 3) == ([0, 1], None)


def test_cart_item_matches_category_keyword():
    item = SimpleNamespace(
        title="vivo iQOO TWS Air3 奔霆白 KPL推荐蓝牙耳机",
        brand=None,
        category="蓝牙耳机",
    )
    assert _cart_item_matches_query(item, "把购物车里的蓝牙耳机改为2件")
    assert _cart_item_matches_query(item, "把耳机数量调整为2")


def test_quantity_number_is_not_item_index():
    assert _extract_cart_item_index("购物车里耳机数量调整为2", 1) == (None, None)
    assert _extract_cart_item_index("把第一个加一件", 1) == (0, None)


@pytest.mark.asyncio
async def test_cart_backref_uses_product_id_field():
    from app.services.agent import _find_product_for_cart

    product = await _find_product_for_cart(
        "把第一个加入购物车",
        {
            "product_cards": [
                {
                    "product_id": "22222222-2222-2222-2222-222222222222",
                    "title": "上一轮第一张商品卡",
                    "price": 199.0,
                }
            ],
            "slots": {},
        },
    )

    assert product == {
        "id": "22222222-2222-2222-2222-222222222222",
        "title": "上一轮第一张商品卡",
        "price": 199.0,
    }


async def _fake_product_for_cart(_query, _state):
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "title": "测试加购商品",
        "price": 99.0,
    }


@pytest.mark.asyncio
async def test_chat_cart_uses_cart_session_id(monkeypatch, db_check):
    import uuid
    from app.core.database import AsyncSessionLocal
    from app.services import agent, cart_service

    conversation_id = str(uuid.uuid4())
    cart_session_id = str(uuid.uuid4())
    user_id = "test-user-cart-session"

    monkeypatch.setattr(agent, "_find_product_for_cart", _fake_product_for_cart)

    state = await agent.node_cart({
        "query": "把第一个加入购物车",
        "session_id": conversation_id,
        "cart_session_id": cart_session_id,
        "user_id": user_id,
        "slots": {},
    })

    assert "response" in state
    async with AsyncSessionLocal() as db:
        cart_items = await cart_service.get_cart(db, cart_session_id, user_id=user_id)
        conversation_items = await cart_service.get_cart(db, conversation_id, user_id=user_id)
        assert len(cart_items) == 1
        assert cart_items[0].product_id == "11111111-1111-1111-1111-111111111111"
        assert conversation_items == []

        await cart_service.clear_cart(db, cart_session_id, user_id=user_id)
        await db.commit()


@pytest.mark.asyncio
async def test_chat_confirm_checkout_does_not_clear_cart(db_check):
    import uuid
    from app.core.database import AsyncSessionLocal
    from app.services import agent, cart_service

    cart_session_id = str(uuid.uuid4())
    user_id = "test-user-confirm-checkout"

    async with AsyncSessionLocal() as db:
        await cart_service.add_to_cart(
            db,
            cart_session_id,
            "33333333-3333-3333-3333-333333333333",
            "确认页测试商品",
            88.0,
            user_id=user_id,
        )
        await db.commit()

    state = await agent.node_cart({
        "query": "确认下单",
        "session_id": str(uuid.uuid4()),
        "cart_session_id": cart_session_id,
        "user_id": user_id,
        "slots": {},
    })

    assert "打开确认下单页面" in state["response"]
    assert "下单成功" not in state["response"]
    async with AsyncSessionLocal() as db:
        cart_items = await cart_service.get_cart(db, cart_session_id, user_id=user_id)
        assert len(cart_items) == 1
        await cart_service.clear_cart(db, cart_session_id, user_id=user_id)
        await db.commit()


@pytest.mark.asyncio
async def test_cart_backref_can_add_remaining_card_after_exclusions():
    product = await _find_product_for_cart(
        "排除前两个，剩下的那个加入购物车并买两件",
        {
            "product_cards": [
                {"product_id": "11111111-1111-1111-1111-111111111111", "title": "候选一", "price": 10.0},
                {"product_id": "22222222-2222-2222-2222-222222222222", "title": "候选二", "price": 20.0},
                {"product_id": "33333333-3333-3333-3333-333333333333", "title": "候选三", "price": 30.0},
            ],
            "slots": {},
        },
    )

    assert _extract_cart_action("排除前两个，剩下的那个加入购物车并买两件") == "add"
    assert _parse_quantity("排除前两个，剩下的那个加入购物车并买两件") == 2
    assert product == {
        "id": "33333333-3333-3333-3333-333333333333",
        "title": "候选三",
        "price": 30.0,
    }


def test_cart_multi_backref_adds_two_current_cards():
    products = _find_products_for_multi_cart(
        "这两款都加入购物车吧",
        {
            "product_cards": [
                {"product_id": "JD2113676", "title": "第一款手机", "price": 1999.0},
                {"product_id": "JD2102664", "title": "第二款手机", "price": 2499.0},
                {"product_id": "JD2126492", "title": "第三款手机", "price": 2999.0},
            ],
            "slots": {},
        },
    )

    assert products == [
        {"id": "JD2113676", "title": "第一款手机", "price": 1999.0},
        {"id": "JD2102664", "title": "第二款手机", "price": 2499.0},
    ]


def test_cart_multi_backref_adds_explicit_ordinal_cards():
    state = {
        "product_cards": [
            {"product_id": "JD2113676", "title": "第一款手机", "price": 1999.0},
            {"product_id": "JD2102664", "title": "第二款手机", "price": 2499.0},
            {"product_id": "JD2126492", "title": "第三款手机", "price": 2999.0},
        ],
        "slots": {},
    }

    assert _find_products_for_multi_cart("第一第二个加入购物车", state) == [
        {"id": "JD2113676", "title": "第一款手机", "price": 1999.0},
        {"id": "JD2102664", "title": "第二款手机", "price": 2499.0},
    ]
    assert _find_products_for_multi_cart("第二个，第三个加入购物车", state) == [
        {"id": "JD2102664", "title": "第二款手机", "price": 2499.0},
        {"id": "JD2126492", "title": "第三款手机", "price": 2999.0},
    ]


@pytest.mark.asyncio
async def test_cart_db_fallback_accepts_sku_product_id(monkeypatch):
    from app.services import rag

    async def fake_retrieve(**_kwargs):
        return {
            "chunks": [
                {
                    "payload": {
                        "product_id": "JD2718819",
                        "title": "SKU 型商品",
                        "price": 699.0,
                    }
                }
            ]
        }

    monkeypatch.setattr(rag, "retrieve", fake_retrieve)

    product = await _find_product_for_cart("把SKU 型商品加入购物车", {"product_cards": [], "slots": {}})

    assert product == {"id": "JD2718819", "title": "SKU 型商品", "price": 699.0}
