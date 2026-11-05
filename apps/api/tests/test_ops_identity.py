import os

import pytest
from fastapi.testclient import TestClient
from ragcommerce_api.app import create_app
from ragcommerce_api.installation_auth import InMemoryInstallations, token_digest
from ragcommerce_api.ops import InMemoryOpsStore, OpsActor
from ragcommerce_api.ops_identity import InMemoryOpsCredentials, PostgresOpsCredentials


def configured(credentials):
    return TestClient(
        create_app(
            ops_store=InMemoryOpsStore(),
            ops_credentials=credentials,
            installation_store=InMemoryInstallations(),
        )
    )


@pytest.mark.parametrize("role,expected", [("viewer", 403), ("reviewer", 202), ("admin", 202)])
def test_server_role_overrides_spoofed_headers_and_audit_actor(role, expected):
    credentials = InMemoryOpsCredentials()
    _, value = credentials.issue("real-operator", role)
    client = configured(credentials)
    headers = {
        "Authorization": "Bearer " + value,
        "X-Ops-Role": "admin",
        "X-Ops-Actor-ID": "forged-admin",
        "Idempotency-Key": "identity-test",
    }
    response = client.post(
        "/v1/ops/evaluation-runs",
        json={"dataset_version": "fixture-v2", "runner_version": "fixture-v2"},
        headers=headers,
    )
    assert response.status_code == expected
    if expected == 202:
        audit = client.get("/v1/ops/audit", headers=headers)
        assert audit.json()[-1]["actor_ref"] == OpsActor("real-operator", role).ref
        assert audit.json()[-1]["actor_ref"] != OpsActor("forged-admin", "admin").ref
    assert client.get("/v1/ops/policy", headers=headers).json()["auth_mode"] == "server_bearer"


def test_operators_installations_and_revoked_credentials_are_separate():
    credentials = InMemoryOpsCredentials()
    credential, value = credentials.issue("operator-one", "viewer")
    client = configured(credentials)
    installation = client.post("/v1/installations").json()
    for headers in [
        {},
        {"X-Ops-Role": "admin", "X-Ops-Actor-ID": "forged-admin"},
        {"Authorization": "Bearer " + installation["token"]},
        {
            "Authorization": "Bearer invalid",
            "X-Ops-Role": "admin",
            "X-Ops-Actor-ID": "forged-admin",
        },
    ]:
        assert client.get("/v1/ops/connectors", headers=headers).status_code == 401
    headers = {"Authorization": "Bearer " + value}
    assert client.get("/v1/ops/connectors", headers=headers).status_code == 200
    assert client.get("/v1/threads", headers=headers).status_code == 401
    assert token_digest(value) in credentials.credentials and value not in str(
        credentials.credentials
    )
    credentials.revoke(credential.id)
    assert client.get("/v1/ops/connectors", headers=headers).status_code == 401


@pytest.mark.parametrize(
    "actor,role", [("bad actor", "viewer"), ("valid-actor", "owner"), ("valid-actor", "ADMIN")]
)
def test_provisioning_rejects_invalid_server_bindings(actor, role):
    with pytest.raises(ValueError):
        InMemoryOpsCredentials().issue(actor, role)


@pytest.mark.integration
def test_postgres_operations_binding_survives_new_adapter_and_revocation():
    dsn = os.environ.get("API_DATABASE_URL")
    if not dsn:
        pytest.skip("isolated API_DATABASE_URL required")
    credentials = PostgresOpsCredentials(dsn)
    credential, value = credentials.issue("durable-operator", "reviewer")
    restarted = PostgresOpsCredentials(dsn)
    assert restarted.authenticate(value).role == "reviewer"
    client = configured(restarted)
    headers = {"Authorization": "Bearer " + value}
    assert client.get("/v1/ops/connectors", headers=headers).status_code == 200
    restarted.revoke(credential.id)
    assert client.get("/v1/ops/connectors", headers=headers).status_code == 401


def test_openapi_separates_operations_and_installation_identity():
    schema = create_app().openapi()
    operation = schema["paths"]["/v1/ops/connectors"]["get"]
    assert operation["security"] == [{"OpsBearer": []}]
    assert not any(p["name"].lower().startswith("x-ops") for p in operation["parameters"])
    assert schema["paths"]["/v1/threads"]["get"]["security"] == [{"InstallationBearer": []}]


def test_admin_provision_writes_only_exclusive_protected_file(tmp_path):
    import json

    from ragcommerce_api.ops_admin import provision

    credentials = InMemoryOpsCredentials()
    target = tmp_path / "operator.json"
    identifier = provision(credentials, "file-operator", "viewer", target)
    value = json.loads(target.read_text(encoding="utf-8"))
    assert value["credential_id"] == str(identifier)
    assert credentials.authenticate(value["token"]).role == "viewer"
    if os.name == "posix":
        assert target.stat().st_mode & 0o777 == 0o600
    before = len(credentials.credentials)
    with pytest.raises(FileExistsError):
        provision(credentials, "other-operator", "admin", target)
    assert len(credentials.credentials) == before


def test_failed_credential_delivery_revokes_new_credential(tmp_path, monkeypatch):
    from ragcommerce_api.ops_admin import provision

    credentials = InMemoryOpsCredentials()

    def failed_write(*args):
        raise OSError("injected delivery failure")

    monkeypatch.setattr("ragcommerce_api.ops_admin.json.dump", failed_write)
    with pytest.raises(OSError):
        provision(credentials, "failed-delivery", "viewer", tmp_path / "failed.json")
    assert not credentials.credentials
