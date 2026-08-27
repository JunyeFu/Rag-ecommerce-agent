from ragcommerce_api.app import app, health


def test_health_matches_public_contract() -> None:
    payload = health()
    operation = app.openapi()["paths"]["/health"]["get"]

    assert payload.model_dump() == {"status": "ok", "contract_version": "0.1.0"}
    assert operation["operationId"] == "getHealth"
