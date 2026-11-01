"""The native runner must not revoke an unfinished, already accepted AgentRun."""

import json
import runpy
from argparse import Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def test_audio_case_refuses_before_runtime_or_slot_when_person_unavailable():
    harness = runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "scripts/run_final_android_acceptance.py")
    )
    with pytest.raises(ValueError, match="available person"):
        harness["run"](Namespace(case="A02", microphone_ready=False))


@pytest.mark.parametrize(
    "expired,link,accepted",
    [(False, None, False), (True, "https://example.com", False), (True, None, True)],
)
def test_expiry_preflight_requires_expired_api_quote_and_blocked_resolve(
    monkeypatch, expired, link, accepted
):
    harness = runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "scripts/run_final_android_acceptance.py")
    )
    expiry = (datetime.now(UTC) + timedelta(minutes=-1 if expired else 15)).isoformat()
    quote = {"offer_id": "offer", "expires_at": expiry}
    payloads = [{"offers": [quote]}, {"link_url": link, "expires_at": expiry}]
    requests = []

    def open_request(request, **kwargs):
        requests.append(request)
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payloads.pop(0)).encode()
        return response

    monkeypatch.setitem(harness["require_expired_api_quote"].__globals__, "urlopen", open_request)
    if accepted:
        assert (
            harness["require_expired_api_quote"](
                "http://localhost:20881", "owner", "product", "offer"
            )
            == quote
        )
    else:
        with pytest.raises(ValueError):
            harness["require_expired_api_quote"](
                "http://localhost:20881", "owner", "product", "offer"
            )
    assert requests[0].full_url.endswith("/v1/products/product/offers?fresh=false")
    assert requests[0].get_header("X-user-id") == "owner"
    assert all("turn" not in request.full_url for request in requests)


def test_native_failure_waits_for_existing_run_without_submitting(monkeypatch):
    harness = runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "scripts/run_final_android_acceptance.py")
    )
    connection = MagicMock()
    connection.execute.return_value.fetchone.side_effect = [(1,), (0,)]
    opened = MagicMock()
    opened.__enter__.return_value = connection
    monkeypatch.setattr(harness["psycopg"], "connect", lambda dsn: opened)
    monkeypatch.setattr(harness["time"], "monotonic", lambda: 1)
    sleeps = []
    monkeypatch.setattr(harness["time"], "sleep", sleeps.append)
    assert harness["await_accepted_run_completion"]("test-dsn", "owner", "start", 10)
    assert sleeps == [1]
    assert connection.execute.call_count == 2
    assert all(
        call.args[0].startswith("SELECT COUNT(*)") for call in connection.execute.call_args_list
    )


def test_completed_run_closes_without_extra_wait(monkeypatch):
    harness = runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "scripts/run_final_android_acceptance.py")
    )
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = (0,)
    opened = MagicMock()
    opened.__enter__.return_value = connection
    monkeypatch.setattr(harness["psycopg"], "connect", lambda dsn: opened)
    monkeypatch.setattr(harness["time"], "monotonic", lambda: 1)
    sleep = MagicMock()
    monkeypatch.setattr(harness["time"], "sleep", sleep)
    assert harness["await_accepted_run_completion"]("test-dsn", "owner", "start", 10)
    sleep.assert_not_called()


def test_observation_window_does_not_extend(monkeypatch):
    harness = runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "scripts/run_final_android_acceptance.py")
    )
    connect = MagicMock()
    monkeypatch.setattr(harness["psycopg"], "connect", connect)
    monkeypatch.setattr(harness["time"], "monotonic", lambda: 10)
    assert not harness["await_accepted_run_completion"]("test-dsn", "owner", "start", 10)
    connect.assert_not_called()


def test_native_stdout_success_when_logcat_receipt_is_unavailable():
    harness = runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "scripts/run_final_android_acceptance.py")
    )
    receipt = harness["native_stdout_receipt"](
        "nativeCase",
        "INSTRUMENTATION_RESULT: stream=\nTime: 4.5\n\nOK (1 test)\nINSTRUMENTATION_CODE: -1\n",
    )
    assert receipt == {
        "method": "nativeCase",
        "tests": 1,
        "failed": 0,
        "ignored": 0,
        "receipt_source": "instrumentation_stdout",
    }


def test_native_stdout_failure_is_not_success():
    harness = runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "scripts/run_final_android_acceptance.py")
    )
    receipt = harness["native_stdout_receipt"](
        "nativeCase", "FAILURES!!!\nTests run: 1, Failures: 1\nINSTRUMENTATION_CODE: -1\n"
    )
    assert receipt["tests"] == receipt["failed"] == 1


def test_incomplete_native_stdout_has_no_success_receipt():
    harness = runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "scripts/run_final_android_acceptance.py")
    )
    assert harness["native_stdout_receipt"]("nativeCase", "INSTRUMENTATION_CODE: -1\n") is None


def test_actual_process_is_launched_before_interruption(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    harness = runpy.run_path(str(root / "scripts/run_final_android_safety_acceptance.py"))
    commands = []

    def shell(*command):
        commands.append(command)
        if command[0] == "pidof":
            assert commands[0] == (
                "am",
                "start",
                "-W",
                "-n",
                "owned.app/com.ragcommerce.agent.MainActivity",
            )
            return "312"
        return ""

    assert harness["interrupt_owned_process"](shell, "owned.app") == "312"
    assert commands[-1] == ("am", "force-stop", "owned.app")


def test_erasure_resume_requires_exact_completed_isolated_assets(monkeypatch):
    from uuid import UUID

    import pytest

    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    harness = runpy.run_path(str(root / "scripts/run_final_android_safety_acceptance.py"))
    owner = "ee34fda3-f4ef-4ff1-a95a-29845a14af2d"
    validate = harness["validate_erasure_source"]
    validate(owner, (UUID(owner),), 1, [("COMPLETED",), ("COMPLETED",)], [(2,)])
    with pytest.raises(ValueError):
        validate(owner, (UUID(int=1),), 1, [("COMPLETED",), ("COMPLETED",)], [(2,)])
    with pytest.raises(ValueError):
        validate(owner, (UUID(owner),), 1, [("COMPLETED",), ("WAITING_APPROVAL",)], [(2,)])
    with pytest.raises(ValueError):
        validate(owner, (UUID(owner),), 1, [("COMPLETED",), ("COMPLETED",)], [(2,), (1,)])
