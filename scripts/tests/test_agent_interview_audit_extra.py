"""Q6-Q10 audit probes. Explicit runs may fail; no business implementation is changed.

All HTTP requests use TestClient, Qdrant uses :memory:, model/DNS results are
injected, and erasure touches only stores created by the individual test.
"""

from __future__ import annotations

import asyncio
import base64
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from ragcommerce_agent_runtime import (
    OpenAICompatibleProvider,
    ProviderInvalidResponse,
    ScriptedPlanner,
    ToolExecutionContext,
)
from ragcommerce_api.app import create_app
from ragcommerce_api.demo import create_demo_app
from ragcommerce_api.erasure import InMemoryUserDataEraser
from ragcommerce_api.media import InMemoryMediaStore
from ragcommerce_api.service import TurnService
from ragcommerce_connectors import ConnectorError, SafeLinkPolicy
from ragcommerce_retrieval import (
    EvidenceBundle,
    InMemoryProjection,
    OutboxEvent,
    OutboxProjector,
    ProjectionOperation,
    QdrantHybridSemanticIndex,
    SearchDocument,
)
from ragcommerce_retrieval.qdrant_projection import QdrantProjection
from scripts.tests.test_agent_interview_audit import CATALOG, make_agent

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="
)


def finished_run():
    client = TestClient(create_demo_app(CATALOG))
    headers = {"X-User-ID": str(uuid4()), "Idempotency-Key": "extra-stream"}
    text = "Nova Mobile Pulse 01 演示手机,预算2000元"
    thread = client.post("/v1/threads", json={"goal": text}, headers=headers).json()
    accepted = client.post(
        f"/v1/threads/{thread['thread_id']}/turns",
        json={"text": text, "media_ids": []},
        headers=headers,
    )
    assert accepted.status_code == 202
    path = f"/v1/agent-runs/{accepted.json()['run_id']}/events"
    return client, headers, path


def event_ids(text):
    return [int(value) for value in re.findall(r"^id: (\d+)$", text, re.M)]


def test_q6_reconnect_replays_exact_suffix_without_duplicate_ids():
    client, headers, path = finished_run()
    first = client.get(path, headers=headers)
    ids = event_ids(first.text)
    assert len(ids) > 3 and ids == sorted(set(ids))
    cursor = ids[len(ids) // 2]
    replay = client.get(path, headers={**headers, "Last-Event-ID": str(cursor)})
    assert event_ids(replay.text) == [value for value in ids if value > cursor]
    assert replay.text.count("event: completed") == 1


@pytest.mark.parametrize("cursor,expected", [("-1", 400), ("not-an-id", 400), ("999999999", 409)])
def test_q6_invalid_or_future_cursor_is_rejected(cursor, expected):
    client, headers, path = finished_run()
    assert client.get(path, headers={**headers, "Last-Event-ID": cursor}).status_code == expected


def test_q6_terminal_cursor_returns_no_old_events_and_disables_buffering():
    client, headers, path = finished_run()
    last = event_ids(client.get(path, headers=headers).text)[-1]
    response = client.get(path, headers={**headers, "Last-Event-ID": str(last)})
    assert response.status_code == 200 and not event_ids(response.text)
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-accel-buffering"] == "no"


def document(title="old"):
    return SearchDocument(
        "extra-item",
        title,
        None,
        "耳机",
        {},
        (),
        EvidenceBundle("audit-fixture", "0" * 64, "extra-item", ("title",)),
    )


def upsert(sequence, event_id, title="old"):
    return OutboxEvent(
        sequence, event_id, "extra-item", ProjectionOperation.UPSERT, document(title)
    )


def test_q7_duplicate_event_is_not_applied_twice():
    projection = InMemoryProjection()
    projector = OutboxProjector(projection)
    event = upsert(1, "e1")
    assert projector.apply(event)
    assert not projector.apply(event)
    assert list(projection.documents) == ["extra-item"]


def test_q7_out_of_order_update_cannot_replace_newer_version():
    projection = InMemoryProjection()
    projector = OutboxProjector(projection)
    projector.apply(upsert(2, "new", "new"))
    with pytest.raises(ValueError, match="sequence"):
        projector.apply(upsert(1, "old"))
    assert projection.documents["extra-item"].title == "new"


def test_q7_old_event_cannot_resurrect_a_deleted_item():
    projection = InMemoryProjection()
    projector = OutboxProjector(projection)
    projector.apply(upsert(1, "e1"))
    projector.apply(OutboxEvent(2, "delete", "extra-item", ProjectionOperation.DELETE, None))
    with pytest.raises(ValueError, match="sequence"):
        projector.apply(upsert(1, "late"))
    assert not projection.documents


def test_q7_failed_fixture_rebuild_preserves_last_good_projection():
    projection = InMemoryProjection()
    projector = OutboxProjector(projection)
    projector.apply(upsert(1, "old"))
    invalid = OutboxEvent(2, "invalid", "extra-item", ProjectionOperation.UPSERT, None)
    with pytest.raises(ValueError):
        projector.rebuild((invalid,))
    assert "extra-item" in projection.documents, (
        "fixture rebuild cleared the old index before validation"
    )


@pytest.fixture
def qdrant():
    client = QdrantClient(":memory:")
    try:
        yield client
    finally:
        client.close()


def test_q7_failed_legacy_qdrant_rebuild_preserves_last_good_projection(qdrant):
    projection = QdrantProjection(qdrant, "extra-legacy", "audit")
    projection.rebuild((upsert(1, "old"),))
    invalid = OutboxEvent(2, "invalid", "extra-item", ProjectionOperation.UPSERT, None)
    with pytest.raises(ValueError):
        projection.rebuild((invalid,))
    assert projection.seed_ids() == ("extra-item",), (
        "legacy rebuild replaced the old collection with an empty one"
    )


def test_q7_current_builder_failure_does_not_switch_the_read_alias(qdrant, monkeypatch):
    class Embedding:
        async def embed(self, texts):
            return tuple((1.0, 0.0) for _ in texts)

    index = QdrantHybridSemanticIndex((document(),), Embedding(), qdrant, "extra-current")
    previous = asyncio.run(index.build_index())

    def fail_upsert(*args, **kwargs):
        raise RuntimeError("injected new collection write failure")

    monkeypatch.setattr(qdrant, "upsert", fail_upsert)
    with pytest.raises(RuntimeError, match="injected"):
        asyncio.run(index.build_index())
    aliases = {entry.alias_name: entry.collection_name for entry in qdrant.get_aliases().aliases}
    assert aliases["extra-current"] == previous
    assert qdrant.collection_exists(previous)


def media_client():
    store = InMemoryMediaStore()
    return TestClient(create_app(media_store=store)), store, {"X-User-ID": str(uuid4())}


def test_q8_valid_small_png_upload_is_accepted_control():
    client, store, headers = media_client()
    response = client.post(
        "/v1/media", content=PNG, headers={**headers, "Content-Type": "image/png"}
    )
    assert response.status_code == 201
    assert len(store.records) == 1


def test_q8_wrong_signature_is_rejected():
    client, store, headers = media_client()
    response = client.post(
        "/v1/media", content=b"not an image", headers={**headers, "Content-Type": "image/png"}
    )
    assert response.status_code == 415 and not store.records


@pytest.mark.parametrize(
    "content_type,content",
    [
        ("image/png", b"\x89PNG\r\n\x1a\n"),
        ("image/jpeg", b"\xff\xd8\xff"),
        ("audio/wav", b"RIFF\x00\x00\x00\x00WAVE"),
    ],
)
def test_q8_header_only_media_is_rejected_at_upload(content_type, content):
    client, store, headers = media_client()
    response = client.post(
        "/v1/media", content=content, headers={**headers, "Content-Type": content_type}
    )
    assert response.status_code in {400, 415, 422}, "signature-only truncated media was admitted"
    assert not store.records


def test_q8_oversized_image_is_rejected_before_storage():
    client, store, headers = media_client()
    response = client.post(
        "/v1/media",
        content=PNG + b"0" * InMemoryMediaStore.IMAGE_LIMIT,
        headers={**headers, "Content-Type": "image/png"},
    )
    assert response.status_code == 413 and not store.records


def test_q8_expired_media_is_not_readable_and_can_be_removed():
    store = InMemoryMediaStore(ttl=timedelta(seconds=-1))
    owner = uuid4()
    record = store.create(owner, "image/png", PNG)
    with pytest.raises(KeyError):
        store.read_owned(owner, record.id)
    assert store.purge_expired() == 1


def test_q8_truncated_wav_is_rejected_before_a_model_request():
    class NoCalls:
        calls = 0

        async def post_json(self, *args):
            self.calls += 1
            raise AssertionError("invalid WAV must not reach the transport")

    transport = NoCalls()
    model = OpenAICompatibleProvider(
        "https://audit.invalid/v1", "test-only", "fake", transport=transport
    )
    context = ToolExecutionContext(uuid4(), uuid4(), uuid4(), uuid4(), "audit-media")
    with pytest.raises(ProviderInvalidResponse, match="WAV"):
        asyncio.run(
            model.interpret_media(context, "audio", "audio/wav", b"RIFF\x00\x00\x00\x00WAVE")
        )
    assert transport.calls == 0


def test_q9_allowed_host_with_public_resolution_is_accepted_control():
    policy = SafeLinkPolicy(frozenset({"item.example"}))
    assert (
        policy.validate_chain(("https://item.example/item",), {"item.example": ("8.8.8.8",)})
        == "https://item.example/item"
    )


@pytest.mark.parametrize(
    "addresses", [{}, {"item.example": ()}, {"item.example": ("8.8.8.8", "10.0.0.1")}]
)
def test_q9_missing_or_mixed_private_dns_evidence_is_rejected(addresses):
    with pytest.raises(ConnectorError):
        SafeLinkPolicy(frozenset({"item.example"})).validate_chain(
            ("https://item.example/item",), addresses
        )


def test_q9_omitting_dns_argument_cannot_skip_the_live_address_check():
    with pytest.raises(ConnectorError):
        SafeLinkPolicy(frozenset({"item.example"})).validate_chain(("https://item.example/item",))


def erasure_app(planner=None):
    agent = make_agent(planner or ScriptedPlanner(()))
    media = InMemoryMediaStore()
    service = TurnService(agent, media)
    eraser = InMemoryUserDataEraser(media, service.index, agent.store)
    return create_app(service, media_store=media, data_eraser=eraser), service, media, agent.store


def test_q10_erasure_requires_explicit_confirmation_control():
    app, service, _, _ = erasure_app()
    owner = uuid4()
    record = service.create_thread(owner, "private task")
    response = TestClient(app).delete("/v1/users/me/data", headers={"X-User-ID": str(owner)})
    assert response.status_code == 400
    assert service.require_thread(owner, record.id).goal == "private task"


def test_q10_completed_data_erasure_is_owner_scoped_and_repeatable():
    app, service, media, store = erasure_app()
    owner, other = uuid4(), uuid4()
    client = TestClient(app)
    own = service.create_thread(owner, "private audit task")
    foreign = service.create_thread(other, "other audit task")
    own_media = media.create(owner, "image/png", PNG)
    foreign_media = media.create(other, "image/png", PNG)
    store.save_preferences(owner, {"color": "red"}, True)
    store.save_preferences(other, {"color": "blue"}, True)
    headers = {"X-User-ID": str(owner), "X-Deletion-Confirmation": "delete-my-data"}
    assert client.delete("/v1/users/me/data", headers=headers).status_code == 200
    assert client.delete("/v1/users/me/data", headers=headers).status_code == 200
    assert service.index.get_thread(own.id) is None and own_media.id not in media.records
    assert service.require_thread(other, foreign.id).goal == "other audit task"
    assert foreign_media.id in media.records and store.load_preferences(other) == {"color": "blue"}
    assert store.load_preferences(owner) == {}


def test_q10_unconfigured_eraser_does_not_claim_success():
    response = TestClient(create_app()).delete(
        "/v1/users/me/data",
        headers={"X-User-ID": str(uuid4()), "X-Deletion-Confirmation": "delete-my-data"},
    )
    assert response.status_code == 503


def test_q10_erasure_failure_is_not_returned_as_deleted_true():
    class BrokenEraser:
        def erase(self, owner):
            raise RuntimeError("injected storage failure")

    response = TestClient(
        create_app(data_eraser=BrokenEraser()), raise_server_exceptions=False
    ).delete(
        "/v1/users/me/data",
        headers={"X-User-ID": str(uuid4()), "X-Deletion-Confirmation": "delete-my-data"},
    )
    assert response.status_code == 500


def test_q10_inflight_agent_cannot_recreate_a_successfully_erased_checkpoint():
    started, resume = Event(), Event()
    observed = {}

    class PausedPlanner(ScriptedPlanner):
        async def plan(self, command, prior_results, replan):
            observed["run_id"] = command.run_id
            started.set()
            assert await asyncio.to_thread(resume.wait, 5), "audit barrier timed out"
            return ()

    app, service, _, store = erasure_app(PausedPlanner(()))
    owner = uuid4()
    thread = service.create_thread(owner, "private task that must be erased")
    request_client = TestClient(app, raise_server_exceptions=False)
    delete_client = TestClient(app)
    headers = {"X-User-ID": str(owner), "Idempotency-Key": "erase-inflight"}
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            request_client.post,
            f"/v1/threads/{thread.id}/turns",
            json={"text": "private task that must be erased", "media_ids": []},
            headers=headers,
        )
        try:
            assert started.wait(5), "audit runtime never reached the pause point"
            deletion = delete_client.delete(
                "/v1/users/me/data",
                headers={**headers, "X-Deletion-Confirmation": "delete-my-data"},
            )
        finally:
            resume.set()
        future.result(timeout=10)
    if deletion.status_code == 409:
        return
    assert deletion.status_code == 200
    assert store.load(observed["run_id"]) is None, (
        "in-flight save recreated an orphan checkpoint after successful deletion"
    )
