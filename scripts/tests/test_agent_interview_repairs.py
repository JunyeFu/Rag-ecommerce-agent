"""Post-remediation checks; historical audit inputs/results stay unchanged."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4

import pytest
import test_agent_interview_audit as audit
import test_agent_interview_audit_extra as extra
from fastapi.testclient import TestClient
from ragcommerce_agent_runtime import PostgresCheckpointStore
from ragcommerce_agent_runtime.postgres_connection import connect
from ragcommerce_api.app import create_app
from ragcommerce_api.erasure import InMemoryUserDataEraser, PostgresUserDataEraser
from ragcommerce_api.installation_auth import (
    InMemoryInstallations,
    PostgresInstallations,
    token_digest,
)
from ragcommerce_api.media import InMemoryMediaStore, MediaRejected, MinioMediaStore, validate_media
from ragcommerce_api.postgres_index import PostgresTurnIndex
from ragcommerce_api.service import TurnService


@pytest.mark.parametrize(
    "claim",
    [
        "该商品售价3999元。",
        "这款商品的实际售价为1000元。",
        "售价$999.00。",
        "实际售价3999块。",
        "价格为三千九百九十九元。",
        "该商家是品牌官方旗舰店。",
        "全国联保。",
        "库存9999件,明日送达,已售十万件。",
    ],
)
def test_q3_claim_cannot_reach_public_sse(claim):
    audit.test_q3_unsupported_claim_does_not_reach_public_sse(claim)


@pytest.mark.parametrize(
    "claim",
    [
        "售价3999元",
        "售价1000元",
        "$999",
        "3999块",
        "三千九百元",
        "官方旗舰店",
        "全国联保",
        "库存9999 明日送达",
    ],
)
def test_q3_phase_text_never_calls_response_model(claim):
    model = audit.provider(claim)
    text = asyncio.run(model.respond(audit.turn("预算1000元"), ()))
    assert text == "请补充商品类别、预算或主要用途。"
    assert model.usage()["total_tokens"] == 0


def secure_app(credentials=None, index=None, media=None, planner=None, durable=False):
    credentials = credentials or InMemoryInstallations()
    agent = extra.make_agent(planner or extra.ScriptedPlanner(()))
    media = media or InMemoryMediaStore()
    if durable:
        agent.store = PostgresCheckpointStore(index.dsn)
    service = TurnService(agent, media, index)
    eraser = (
        InMemoryUserDataEraser(media, PostgresUserDataEraser(index.dsn))
        if durable
        else InMemoryUserDataEraser(media, service.index, agent.store)
    )
    app = create_app(
        service,
        media_store=media,
        data_eraser=eraser,
        installation_store=credentials,
        execute_background=not durable,
    )
    return app, service, media, agent.store


def install(client):
    response = client.post("/v1/installations")
    assert response.status_code == 201 and response.headers["Cache-Control"] == "no-store"
    value = response.json()
    return value, {"Authorization": "Bearer " + value["token"]}


def test_q4_real_credential_required_and_owner_header_cannot_override():
    app, _, _, _ = secure_app()
    client = TestClient(app)
    value, headers = install(client)
    _, other_headers = install(client)
    assert token_digest(value["token"]) in app.state.installations.credentials
    assert value["token"] not in str(app.state.installations.credentials)
    for bad in [
        {"X-User-ID": value["owner_id"]},
        {**headers, "Authorization": "Bearer invalid"},
        {},
    ]:
        assert client.get("/v1/threads", headers=bad).status_code == 401
    thread = client.post("/v1/threads", json={"goal": "private task"}, headers=headers).json()[
        "thread_id"
    ]
    assert client.get(f"/v1/threads/{thread}", headers=other_headers).status_code == 404
    assert (
        client.get(
            f"/v1/threads/{thread}", headers={**other_headers, "X-User-ID": value["owner_id"]}
        ).status_code
        == 404
    )
    assert client.get(f"/v1/threads/{thread}", headers=headers).headers["X-Auth-Mode"] == "bearer"
    run = client.post(
        f"/v1/threads/{thread}/turns",
        json={"text": "private task", "media_ids": []},
        headers={**headers, "Idempotency-Key": "auth-run"},
    ).json()["run_id"]
    assert client.get(f"/v1/agent-runs/{run}/events", headers=headers).status_code == 200
    assert client.get(f"/v1/agent-runs/{run}/events", headers=other_headers).status_code == 404
    assert (
        client.get(
            "/v1/ops/connectors",
            headers={**headers, "X-Ops-Role": "admin", "X-Ops-Actor-ID": "test"},
        ).status_code
        == 503
    )
    deletion = client.delete(
        "/v1/users/me/data", headers={**headers, "X-Deletion-Confirmation": "delete-my-data"}
    )
    assert deletion.status_code == 200
    assert client.get("/v1/threads", headers=headers).status_code == 401
    assert client.get("/v1/threads", headers=other_headers).status_code == 200


def test_q10_busy_then_retry_erases_without_late_checkpoint():
    started, resume = Event(), Event()

    class Paused(extra.ScriptedPlanner):
        async def plan(self, *args):
            started.set()
            assert await asyncio.to_thread(resume.wait, 5)
            return ()

    app, _, media, store = secure_app(planner=Paused(()))
    client = TestClient(app)
    value, headers = install(client)
    thread = client.post("/v1/threads", json={"goal": "private"}, headers=headers).json()[
        "thread_id"
    ]
    obj = media.create(UUID(value["owner_id"]), "image/png", extra.PNG)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            client.post,
            f"/v1/threads/{thread}/turns",
            json={"text": "private", "media_ids": []},
            headers={**headers, "Idempotency-Key": "paused"},
        )
        try:
            assert started.wait(5)
            assert (
                TestClient(app)
                .delete(
                    "/v1/users/me/data",
                    headers={**headers, "X-Deletion-Confirmation": "delete-my-data"},
                )
                .status_code
                == 409
            )
            assert obj.id in media.records
        finally:
            resume.set()
        accepted = future.result(timeout=10)
    run = UUID(accepted.json()["run_id"])
    cp = store.load(run)
    assert (
        client.delete(
            "/v1/users/me/data", headers={**headers, "X-Deletion-Confirmation": "delete-my-data"}
        ).status_code
        == 200
    )
    assert store.load(run) is None and obj.id not in media.records
    with pytest.raises(ValueError, match="no longer exists"):
        store.save(cp)


@pytest.mark.parametrize(
    "content_type,data",
    [
        ("image/png", b"\x89PNG\r\n\x1a\n"),
        ("audio/wav", b"RIFF\x00\x00\x00\x00WAVE"),
        ("audio/ogg", b"OggSfixture"),
    ],
)
def test_q8_invalid_content_never_reaches_either_storage_adapter(content_type, data):
    class NoWrite:
        def put_object(self, *a, **k):
            pytest.fail("invalid input reached object storage")

    minio = object.__new__(MinioMediaStore)
    minio.client = NoWrite()
    for store in [InMemoryMediaStore(), minio]:
        with pytest.raises(MediaRejected):
            store.create(uuid4(), content_type, data)


def test_q8_decoding_dimensions_and_actual_wav_frames():
    import io
    import wave

    from PIL import Image

    for mode, fmt, mime in [
        ("RGB", "JPEG", "image/jpeg"),
        ("RGBA", "PNG", "image/png"),
        ("RGB", "WEBP", "image/webp"),
    ]:
        content = io.BytesIO()
        Image.new(mode, (2, 2)).save(content, fmt)
        assert validate_media(mime, content.getvalue())[0] == mime
        with pytest.raises(MediaRejected):
            validate_media(mime, content.getvalue()[:20])
    huge = io.BytesIO()
    Image.new("L", (4001, 4000)).save(huge, "PNG")
    with pytest.raises(MediaRejected, match="pixel/frame"):
        validate_media("image/png", huge.getvalue())
    content = io.BytesIO()
    with wave.open(content, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 160)
    assert validate_media("audio/wav", content.getvalue())[1] == "audio"
    with pytest.raises(MediaRejected):
        validate_media("audio/wav", content.getvalue()[:-2])


def test_q2_present_matching_and_nonmatching_attribute():
    from dataclasses import replace

    from ragcommerce_retrieval.search import HybridIndex

    document = replace(extra.document(), attributes={"防水": "IP68"})
    assert HybridIndex._satisfies(document, {"防水": "IP68"})
    assert not HybridIndex._satisfies(document, {"防水": "IP67"})


@pytest.mark.integration
def test_q4_q10_postgres_restart_and_minio_inflight_erasure(monkeypatch):
    dsn = os.environ.get("INTERVIEW_DATABASE_URL") or os.environ.get("API_DATABASE_URL")
    if not dsn:
        pytest.skip("isolated INTERVIEW_DATABASE_URL required")
    credentials = PostgresInstallations(dsn)
    minio_default = "minioadmin"  # Public factory credential of the isolated local test container.
    media = MinioMediaStore(
        dsn,
        os.environ.get("MINIO_ENDPOINT", "127.0.0.1:59079"),
        os.environ.get("MINIO_ACCESS_KEY", minio_default),
        os.environ.get("MINIO_SECRET_KEY", minio_default),
        bucket="interview-repairs",
    )
    started, resume = Event(), Event()

    class Paused(extra.ScriptedPlanner):
        async def plan(self, *args):
            started.set()
            assert await asyncio.to_thread(resume.wait, 30)
            return ()

    app, service, _, store = secure_app(
        credentials, PostgresTurnIndex(dsn), media, Paused(()), durable=True
    )
    other_app, _, _, _ = secure_app(
        PostgresInstallations(dsn), PostgresTurnIndex(dsn), media, durable=True
    )
    client, other_client = TestClient(app), TestClient(other_app)
    value, headers = install(client)
    owner = UUID(value["owner_id"])
    assert other_client.get("/v1/threads", headers=headers).status_code == 200
    thread = client.post(
        "/v1/threads", json={"goal": "persistent private"}, headers=headers
    ).json()["thread_id"]
    obj = media.create(owner, "image/png", extra.PNG)
    accepted = client.post(
        f"/v1/threads/{thread}/turns",
        json={"text": "private", "media_ids": []},
        headers={**headers, "Idempotency-Key": "durable-paused"},
    )
    assert accepted.status_code == 202
    run = UUID(accepted.json()["run_id"])
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, service.execute(run))
        try:
            assert started.wait(10)
            with connect(dsn) as c:
                c.execute("UPDATE api_turns SET claimed_at='2000-01-01' WHERE run_id=%s", (run,))
            # Even an expired lease cannot steal execution from a live worker.
            assert PostgresTurnIndex(dsn).claim_next() is None
            import json
            import subprocess
            import sys

            code = "import sys,json; p=json.load(sys.stdin); sys.path[:0]=p['paths']; from ragcommerce_api.installation_auth import PostgresInstallations; from ragcommerce_api.postgres_index import PostgresTurnIndex; assert str(PostgresInstallations(p['dsn']).authenticate(p['credential']))==p['owner']; assert PostgresTurnIndex(p['dsn']).claim_next() is None; print('verified')"
            child = subprocess.run(
                [sys.executable, "-c", code],
                input=json.dumps(
                    {
                        "paths": sys.path,
                        "dsn": dsn,
                        "credential": value["token"],
                        "owner": str(owner),
                    }
                ),
                capture_output=True,
                text=True,
                timeout=20,
            )
            assert child.returncode == 0, child.stderr
            assert child.stdout.strip() == "verified"

            assert (
                other_client.delete(
                    "/v1/users/me/data",
                    headers={**headers, "X-Deletion-Confirmation": "delete-my-data"},
                ).status_code
                == 409
            )
            assert media.read_owned(owner, obj.id)[1] == extra.PNG
        finally:
            resume.set()
        future.result(timeout=40)
    cp = store.load(run)
    real_remove = media.client.remove_object

    def fail_remove(*args):
        raise RuntimeError("injected object deletion failure")

    monkeypatch.setattr(media.client, "remove_object", fail_remove)
    failed = TestClient(other_app, raise_server_exceptions=False).delete(
        "/v1/users/me/data", headers={**headers, "X-Deletion-Confirmation": "delete-my-data"}
    )
    assert failed.status_code == 500
    assert store.load(run) is not None
    assert client.get("/v1/threads", headers=headers).status_code == 200
    monkeypatch.setattr(media.client, "remove_object", real_remove)
    deleted = other_client.delete(
        "/v1/users/me/data", headers={**headers, "X-Deletion-Confirmation": "delete-my-data"}
    )
    assert deleted.status_code == 200, deleted.text
    assert store.load(run) is None
    assert client.get("/v1/threads", headers=headers).status_code == 401
    with pytest.raises(ValueError, match="no longer exists"):
        store.save(cp)
    from minio.error import S3Error

    with pytest.raises(S3Error):
        media.client.stat_object(media.bucket, f"{owner}/{obj.id}")
    with connect(dsn) as c:
        for table, key, arg in [
            ("api_threads", "owner_id", owner),
            ("api_turns", "owner_id", owner),
            ("api_media_objects", "owner_id", owner),
            ("api_installations", "owner_id", owner),
            ("agent_runs", "conversation_id", UUID(thread)),
            ("conversations", "id", UUID(thread)),
        ]:
            assert (
                c.execute(f"SELECT COUNT(*) FROM {table} WHERE {key}=%s", (arg,)).fetchone()[0] == 0
            )


def test_q9_strict_dns_gate_is_distinct_from_offline_fixture():
    from ragcommerce_connectors.security import SafeLinkPolicy
    from ragcommerce_connectors.spi import ConnectorError

    policy = SafeLinkPolicy(frozenset({"shop.example"}))
    urls = ("https://shop.example/item",)
    assert policy.validate_fixture_chain(urls) == urls[0]
    for addresses in [
        None,
        {},
        {"shop.example": ()},
        {"shop.example": ("not-an-ip",)},
        {"shop.example": ("8.8.8.8", "127.0.0.1")},
    ]:
        with pytest.raises(ConnectorError):
            policy.validate_chain(urls, addresses)
    assert policy.validate_chain(urls, {"shop.example": ("8.8.8.8",)}) == urls[0]


def test_q5_lf_lockfiles_match_current_security_snapshot():
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    snapshot = json.loads(
        (root / "docs/security/evidence/security-gate.json").read_text(encoding="utf-8")
    )
    locked = snapshot["checks"]["locked_inputs"]
    attributes = (root / ".gitattributes").read_text(encoding="utf-8")
    for name, field in [("uv.lock", "uv_lock_sha256"), ("package-lock.json", "npm_lock_sha256")]:
        content = (root / name).read_bytes()
        assert b"\r\n" not in content
        assert f"/{name} text eol=lf" in attributes
        assert hashlib.sha256(content).hexdigest() == locked[field]


@pytest.mark.parametrize(
    "case,args",
    [
        (extra.test_q8_valid_small_png_upload_is_accepted_control, ()),
        (extra.test_q8_wrong_signature_is_rejected, ()),
        (
            extra.test_q8_header_only_media_is_rejected_at_upload,
            ("image/png", b"\x89PNG\r\n\x1a\n"),
        ),
        (extra.test_q8_header_only_media_is_rejected_at_upload, ("image/jpeg", b"\xff\xd8\xff")),
        (
            extra.test_q8_header_only_media_is_rejected_at_upload,
            ("audio/wav", b"RIFF\x00\x00\x00\x00WAVE"),
        ),
        (extra.test_q8_oversized_image_is_rejected_before_storage, ()),
        (extra.test_q8_expired_media_is_not_readable_and_can_be_removed, ()),
        (extra.test_q8_truncated_wav_is_rejected_before_a_model_request, ()),
        (extra.test_q10_erasure_requires_explicit_confirmation_control, ()),
        (extra.test_q10_completed_data_erasure_is_owner_scoped_and_repeatable, ()),
        (extra.test_q10_unconfigured_eraser_does_not_claim_success, ()),
        (extra.test_q10_erasure_failure_is_not_returned_as_deleted_true, ()),
        (extra.test_q10_inflight_agent_cannot_recreate_a_successfully_erased_checkpoint, ()),
    ],
    ids=lambda value: getattr(value, "__name__", None),
)
def test_q8_q10_original_probes_with_explicit_fixture_identity(monkeypatch, case, args):
    from functools import partial

    # Original probe bodies/inputs are immutable. Their factory now explicitly
    # selects the same local development identity that existed during the audit.
    monkeypatch.setattr(extra, "create_app", partial(create_app, development_identity=True))
    case(*args)
