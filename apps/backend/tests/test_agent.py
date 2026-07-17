import pytest
pytestmark = pytest.mark.integration

"""
Agent integration tests — 主要端点功能测试
"""
import pytest


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code in (200, 503)
    data = response.json()
    if isinstance(data, list):
        data = data[0] if data else {}
    assert "status" in data
    assert data["status"] in ("ok", "degraded")

@pytest.mark.asyncio
async def test_version_endpoint(client):
    response = await client.get("/version")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "电商AI导购系统"

@pytest.mark.asyncio
async def test_products_endpoint(client, db_check):
    response = await client.get("/api/v1/products?page_size=3")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0

@pytest.mark.asyncio
async def test_chat_chitchat(client):
    response = await client.post("/api/v1/chat", json={"message": "你好"})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")

@pytest.mark.asyncio
async def test_chat_recommend(client, db_check):
    response = await client.post("/api/v1/chat", json={"message": "推荐一款耳机"})
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_cache_clear_endpoint(client):
    response = await client.post("/api/cache/clear")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

@pytest.mark.asyncio
async def test_root_redirect(client):
    response = await client.get("/", follow_redirects=False)
    assert response.status_code == 307
