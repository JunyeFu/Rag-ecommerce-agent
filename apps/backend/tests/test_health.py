"""Health endpoint tests."""
import pytest


@pytest.mark.asyncio
async def test_health_returns_object_and_status_code(client):
    response = await client.get("/health")

    assert response.status_code in (200, 503)
    data = response.json()
    assert isinstance(data, dict)
    assert data["status"] in {"ok", "degraded"}
    assert "database" in data
    assert "pgvector" in data
