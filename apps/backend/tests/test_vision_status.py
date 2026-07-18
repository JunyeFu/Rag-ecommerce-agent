import pytest
pytestmark = pytest.mark.integration

"""Vision readiness tests."""
import pytest


@pytest.mark.asyncio
async def test_vision_status_does_not_load_model(client):
    response = await client.get("/api/v1/upload/vision-status")

    assert response.status_code == 200
    data = response.json()
    assert {"ready", "provider", "cloud_vision_configured"} <= set(data)
    assert data["provider"] in {"doubao_vision_api", "llm_vision_api"}
