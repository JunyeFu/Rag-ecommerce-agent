"""
端点级 API 契约测试 - 验证所有业务端点返回 ApiResponse 信封 {code, data, message}

规则 (DEV-CONTROL.md §12.5 B2):
1. 所有业务端点必须返回 ApiResponse 对象
2. 需认证端点无 token 返回 401
3. 豁免端点无需 token
"""
import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.contract, pytest.mark.integration]


async def _get_token(client: AsyncClient) -> str:
    """登录获取 auth token"""
    resp = await client.post("/api/v1/auth/login", json={"nickname": "contract_test"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    return body["data"]["token"]


class TestAuthGate:
    """规则: 需认证端点无 token 返回 401"""

    @pytest.mark.parametrize("method,path", [
        ("GET", "/api/v1/cart"),
        ("GET", "/api/v1/products"),
        ("GET", "/api/v1/favorites"),
        ("GET", "/api/v1/orders"),
        ("GET", "/api/v1/footprints"),
    ])
    async def test_no_token_returns_401(self, client: AsyncClient, method, path):
        resp = await client.request(method, path)
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] in (4010, 4011)
        assert "message" in body
        assert body["data"] is None

    @pytest.mark.parametrize("path", ["/health", "/ready", "/version"])
    async def test_exempt_paths_no_token_ok(self, client: AsyncClient, path):
        """豁免路径无需 token"""
        resp = await client.get(path)
        assert resp.status_code == 200


class TestApiResponseEnvelope:
    """规则: 所有业务端点返回 {code, data, message} 信封"""

    async def test_login_returns_envelope(self, client: AsyncClient, db_check):
        resp = await client.post("/api/v1/auth/login", json={"nickname": "env_test"})
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"code", "data", "message"}
        assert body["code"] == 0
        assert "token" in body["data"]
        assert "user_id" in body["data"]

    async def test_products_returns_envelope(self, client: AsyncClient, db_check):
        token = await _get_token(client)
        resp = await client.get("/api/v1/products", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"code", "data", "message"}
        assert body["code"] == 0
        assert "items" in body["data"]
        assert "total" in body["data"]

    async def test_cart_returns_envelope(self, client: AsyncClient, db_check):
        token = await _get_token(client)
        resp = await client.get(
            "/api/v1/cart",
            params={"session_id": "00000000-0000-0000-0000-000000000001"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"code", "data", "message"}
        assert body["code"] == 0

    async def test_favorites_returns_envelope(self, client: AsyncClient, db_check):
        token = await _get_token(client)
        resp = await client.get(
            "/api/v1/favorites",
            params={"user_id": "contract_test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        body = resp.json()
        assert set(body.keys()) == {"code", "data", "message"}

    async def test_invalid_token_returns_401_envelope(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/products",
            headers={"Authorization": "Bearer invalid-uuid"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert set(body.keys()) == {"code", "data", "message"}
        assert body["code"] == 4011
