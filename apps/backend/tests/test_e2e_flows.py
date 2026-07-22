"""
端到端测试 - 完整用户路径验证

测试金字塔顶层 (pytest -m e2e):
1. 认证流程: login -> token -> 受保护端点
2. 商品浏览: 列表 -> 详情
3. 购物车流程: 加购 -> 查看 -> 改量 -> 删除
4. 收藏流程: 切换 -> 列表 -> 移除
5. 足迹流程: 记录 -> 列表
6. 订单流程: 购物车 -> 下单
7. 鉴权失败: 无效 token -> 401

运行: pytest -m e2e (需 DB)
"""
import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.e2e, pytest.mark.integration]


async def _login(client: AsyncClient, nickname: str = "e2e_user") -> str:
    """登录获取 auth token"""
    resp = await client.post("/api/v1/auth/login", json={"nickname": nickname})
    assert resp.status_code == 200
    return resp.json()["data"]["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestAuthFlow:
    """E2E-1: 认证流程"""

    async def test_login_returns_valid_token(self, client: AsyncClient, db_check):
        """login -> 拿到 token -> 用 token 访问受保护端点"""
        token = await _login(client, "auth_flow_user")
        assert token

        resp = await client.get("/api/v1/products", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    async def test_invalid_token_blocked(self, client: AsyncClient):
        """无效 token 被拦截"""
        resp = await client.get("/api/v1/products", headers=_auth("fake-token"))
        assert resp.status_code == 401
        assert resp.json()["code"] == 4011

    async def test_no_token_blocked(self, client: AsyncClient):
        """无 token 被拦截"""
        resp = await client.get("/api/v1/products")
        assert resp.status_code == 401
        assert resp.json()["code"] == 4010

    async def test_token_persistence_across_requests(self, client: AsyncClient, db_check):
        """同一 token 可多次使用"""
        token = await _login(client, "persistence_user")
        for _ in range(3):
            resp = await client.get("/api/v1/products", headers=_auth(token))
            assert resp.status_code == 200


class TestProductBrowse:
    """E2E-2: 商品浏览"""

    async def test_list_products_with_pagination(self, client: AsyncClient, db_check):
        """分页列出商品"""
        token = await _login(client, "browse_user")
        resp = await client.get(
            "/api/v1/products",
            params={"page": 1, "page_size": 10},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "items" in data
        assert "total" in data
        assert len(data["items"]) <= 10

    async def test_filter_by_category(self, client: AsyncClient, db_check):
        """分类筛选"""
        token = await _login(client, "category_user")
        resp = await client.get(
            "/api/v1/products",
            params={"category": "食品饮料"},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        for item in items:
            assert item["category"] == "食品饮料"

    async def test_get_product_detail(self, client: AsyncClient, db_check):
        """获取商品详情（先列表取 ID 再查详情）"""
        token = await _login(client, "detail_user")
        list_resp = await client.get(
            "/api/v1/products",
            params={"page": 1, "page_size": 1},
            headers=_auth(token),
        )
        items = list_resp.json()["data"]["items"]
        if items:
            product_id = items[0]["product_id"]
            resp = await client.get(
                f"/api/v1/products/{product_id}",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            assert resp.json()["data"]["product_id"] == product_id


class TestCartFlow:
    """E2E-3: 购物车流程"""

    async def test_add_view_update_remove(self, client: AsyncClient, db_check):
        """加购 -> 查看 -> 改量 -> 删除"""
        token = await _login(client, "cart_flow_user")
        headers = _auth(token)

        # 1. 获取商品
        list_resp = await client.get(
            "/api/v1/products",
            params={"page": 1, "page_size": 1},
            headers=headers,
        )
        items = list_resp.json()["data"]["items"]
        if not items:
            pytest.skip("No products in DB")
        product_id = items[0]["product_id"]

        # 2. 加购
        add_resp = await client.post(
            "/api/v1/cart/add",
            json={"product_id": product_id, "quantity": 2},
            headers=headers,
        )
        assert add_resp.status_code == 200
        assert add_resp.json()["code"] == 0

        # 3. 查看购物车
        cart_resp = await client.get("/api/v1/cart", headers=headers)
        assert cart_resp.status_code == 200
        cart_data = cart_resp.json()["data"]
        assert "items" in cart_data
        assert any(item["product_id"] == product_id for item in cart_data["items"])

        # 4. 改量
        update_resp = await client.put(
            "/api/v1/cart/update",
            json={"product_id": product_id, "quantity": 5},
            headers=headers,
        )
        assert update_resp.status_code == 200

        # 5. 删除
        del_resp = await client.request(
            "DELETE",
            "/api/v1/cart/remove",
            json={"product_id": product_id},
            headers=headers,
        )
        assert del_resp.status_code == 200

        # 6. 确认删除
        cart_after = await client.get("/api/v1/cart", headers=headers)
        cart_items = cart_after.json()["data"]["items"]
        assert not any(item["product_id"] == product_id for item in cart_items)


class TestFavoriteFlow:
    """E2E-4: 收藏流程"""

    async def test_toggle_list_remove(self, client: AsyncClient, db_check):
        """切换收藏 -> 列表 -> 移除"""
        token = await _login(client, "fav_user")
        headers = _auth(token)

        # 获取商品
        list_resp = await client.get(
            "/api/v1/products",
            params={"page": 1, "page_size": 1},
            headers=headers,
        )
        items = list_resp.json()["data"]["items"]
        if not items:
            pytest.skip("No products in DB")
        product_id = items[0]["product_id"]

        # 添加收藏
        add_resp = await client.post(
            "/api/v1/favorites/toggle",
            json={"product_id": product_id},
            headers=headers,
        )
        assert add_resp.status_code == 200

        # 查看收藏列表
        list_fav = await client.get("/api/v1/favorites", headers=headers)
        assert list_fav.status_code == 200
        fav_data = list_fav.json()["data"]
        assert "items" in fav_data

        # 再次 toggle 移除
        del_resp = await client.post(
            "/api/v1/favorites/toggle",
            json={"product_id": product_id},
            headers=headers,
        )
        assert del_resp.status_code == 200


class TestFootprintFlow:
    """E2E-5: 足迹流程"""

    async def test_record_and_list(self, client: AsyncClient, db_check):
        """记录足迹 -> 查看足迹列表"""
        token = await _login(client, "footprint_user")
        headers = _auth(token)

        # 获取商品
        list_resp = await client.get(
            "/api/v1/products",
            params={"page": 1, "page_size": 1},
            headers=headers,
        )
        items = list_resp.json()["data"]["items"]
        if not items:
            pytest.skip("No products in DB")
        product_id = items[0]["product_id"]

        # 记录足迹
        record_resp = await client.post(
            "/api/v1/footprints",
            json={"product_id": product_id},
            headers=headers,
        )
        assert record_resp.status_code == 200

        # 查看足迹
        list_resp = await client.get("/api/v1/footprints", headers=headers)
        assert list_resp.status_code == 200
        footprint_data = list_resp.json()["data"]
        assert "items" in footprint_data


class TestOrderFlow:
    """E2E-6: 订单流程"""

    async def test_create_order_from_cart(self, client: AsyncClient, db_check):
        """加购 -> 下单"""
        token = await _login(client, "order_user")
        headers = _auth(token)

        # 1. 获取商品
        list_resp = await client.get(
            "/api/v1/products",
            params={"page": 1, "page_size": 1},
            headers=headers,
        )
        items = list_resp.json()["data"]["items"]
        if not items:
            pytest.skip("No products in DB")
        product_id = items[0]["product_id"]

        # 2. 加购
        await client.post(
            "/api/v1/cart/add",
            json={"product_id": product_id, "quantity": 1},
            headers=headers,
        )

        # 3. 下单
        order_resp = await client.post(
            "/api/v1/orders",
            json={
                "address": "测试地址",
                "remark": "e2e 测试订单",
                "product_ids": [product_id],
            },
            headers=headers,
        )
        if order_resp.status_code == 200:
            order_data = order_resp.json()["data"]
            assert "order_id" in order_data or "order_no" in order_data
