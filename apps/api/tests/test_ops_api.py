from __future__ import annotations

from fastapi.testclient import TestClient
from ragcommerce_api.app import create_app
from ragcommerce_api.ops import InMemoryOpsStore


def headers(role: str = "viewer", **values: str) -> dict[str, str]:
    return {
        "X-Ops-Role": role,
        "X-Ops-Actor-ID": "operator-fixture-001",
        **values,
    }


def test_ops_api_is_unavailable_without_explicit_store() -> None:
    response = TestClient(create_app()).get("/v1/ops/connectors", headers=headers())
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_connector_evidence_separates_local_and_external_status() -> None:
    client = TestClient(create_app(ops_store=InMemoryOpsStore()))
    response = client.get("/v1/ops/connectors", headers=headers())

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert len(response.json()) == 3
    assert all(item["evidence"]["local_evidence"] for item in response.json())
    assert all(item["evidence"]["external_gate"] for item in response.json())
    assert not any(item["authorization"] == "AUTHORIZED" for item in response.json())


def test_trace_contract_is_redacted_and_contains_only_digests_and_evidence_refs() -> None:
    client = TestClient(create_app(ops_store=InMemoryOpsStore()))
    response = client.get("/v1/ops/traces", headers=headers())
    payload = response.json()
    serialized = response.text.lower()

    assert response.status_code == 200
    assert payload[0]["tools"][0]["arguments_sha256"]
    assert payload[0]["tools"][0]["evidence_refs"]
    for forbidden in ("chain_of_thought", "raw_input", "raw_arguments", "secret", "password"):
        assert forbidden not in serialized


def test_entity_resolution_requires_reviewer_reason_idempotency_and_audit() -> None:
    store = InMemoryOpsStore()
    client = TestClient(create_app(ops_store=store))
    url = "/v1/ops/entity-conflicts/conflict-001/resolution"
    body = {"decision": "KEEP_SEPARATE", "reason": "来源型号字段存在可复核冲突"}

    denied = client.post(url, json=body, headers=headers("viewer", **{"Idempotency-Key": "r1"}))
    first = client.post(url, json=body, headers=headers("reviewer", **{"Idempotency-Key": "r1"}))
    replay = client.post(url, json=body, headers=headers("reviewer", **{"Idempotency-Key": "r1"}))
    audit = client.get("/v1/ops/audit", headers=headers("reviewer"))

    assert denied.status_code == 403
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert first.json()["status"] == "KEPT_SEPARATE"
    assert len(audit.json()) == 1
    assert audit.json()[0]["action"] == "entity_conflict.resolve"
    assert "来源型号" not in audit.text
    assert audit.json()[0]["payload_sha256"]


def test_evaluation_start_is_bounded_idempotent_and_does_not_claim_external_pass() -> None:
    store = InMemoryOpsStore()
    client = TestClient(create_app(ops_store=store))
    body = {"dataset_version": "v2-fixture-1", "runner_version": "deterministic-1"}
    request_headers = headers("reviewer", **{"Idempotency-Key": "eval-1"})

    first = client.post("/v1/ops/evaluation-runs", json=body, headers=request_headers)
    replay = client.post("/v1/ops/evaluation-runs", json=body, headers=request_headers)
    gates = client.get("/v1/ops/release-gates", headers=headers()).json()

    assert first.status_code == replay.status_code == 202
    assert first.json() == replay.json()
    assert first.json()["status"] == "QUEUED"
    assert first.json()["evidence"]["external_gate"]
    assert any(gate["evidence_level"] == "LIVE" and gate["status"] == "BLOCKED" for gate in gates)


def test_policy_disables_export_and_lists_sensitive_fields_as_prohibited() -> None:
    client = TestClient(create_app(ops_store=InMemoryOpsStore()))
    policy = client.get("/v1/ops/policy", headers=headers()).json()

    assert policy["export_enabled"] is False
    assert policy["audit_append_only"] is True
    assert "chain of thought" in policy["prohibited_fields"]
    assert "connector secrets" in policy["prohibited_fields"]
