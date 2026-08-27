from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from ragcommerce_agent_runtime import (
    InMemoryCheckpointStore,
    RunCheckpoint,
    RuntimeIdentity,
    TurnCommand,
)
from ragcommerce_api.app import create_app
from ragcommerce_api.erasure import InMemoryUserDataEraser
from ragcommerce_api.media import InMemoryMediaStore
from ragcommerce_api.service import InMemoryTurnIndex, ThreadRecord, TurnRecord


class RecordingEraser:
    def __init__(self) -> None:
        self.users = []

    def erase(self, user_id):
        self.users.append(user_id)
        return 0


def headers(user_id, *, confirm: bool = False) -> dict[str, str]:
    values = {"X-User-ID": str(user_id)}
    if confirm:
        values["X-Deletion-Confirmation"] = "delete-my-data"
    return values


def test_user_data_erasure_endpoint_is_confirmed_identity_scoped_and_fail_closed() -> None:
    user_id = uuid4()
    eraser = RecordingEraser()
    client = TestClient(create_app(data_eraser=eraser))
    assert client.delete("/v1/users/me/data", headers=headers(user_id)).status_code == 400
    response = client.delete("/v1/users/me/data", headers=headers(user_id, confirm=True))
    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert eraser.users == [user_id]

    unconfigured = TestClient(create_app()).delete(
        "/v1/users/me/data", headers=headers(user_id, confirm=True)
    )
    assert unconfigured.status_code == 503


def test_in_memory_erasure_removes_media_sessions_traces_and_preferences_for_one_user() -> None:
    user_id, other_id = uuid4(), uuid4()
    media = InMemoryMediaStore()
    own_media = media.create(user_id, "image/png", b"\x89PNG\r\n\x1a\nowned")
    other_media = media.create(other_id, "image/png", b"\x89PNG\r\n\x1a\nother")

    index = InMemoryTurnIndex()
    thread_id, mission_id, run_id = uuid4(), uuid4(), uuid4()
    command = TurnCommand(user_id, thread_id, run_id, "erase-test", "recommend")
    index.create_thread(ThreadRecord(thread_id, mission_id, user_id, "recommend"))
    index.reserve(TurnRecord(user_id, thread_id, run_id, "erase-test", "0" * 64, command))

    checkpoints = InMemoryCheckpointStore()
    identity = RuntimeIdentity("runtime", "model", "prompt", "policy", "contract")
    checkpoints.begin_run(command, identity, datetime.now(UTC))
    checkpoints.save(RunCheckpoint(run_id, command.idempotency_key))
    checkpoints.save_preferences(user_id, {"color": "black"}, consent=True)
    checkpoints.save_preferences(other_id, {"color": "white"}, consent=True)

    deleted = InMemoryUserDataEraser(media, index, checkpoints).erase(user_id)
    assert deleted >= 6
    assert own_media.id not in media.records
    assert other_media.id in media.records
    assert index.get_thread(thread_id) is None
    assert index.get_run(run_id) is None
    assert checkpoints.load(run_id) is None
    assert checkpoints.load_preferences(user_id) == {}
    assert checkpoints.load_preferences(other_id) == {"color": "white"}
