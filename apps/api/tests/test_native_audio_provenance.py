"""M03 requires an observed native capture, not an imported fixture."""

import hashlib
import io
import json
import runpy
import wave
from pathlib import Path

import pytest


def test_native_capture_report_is_required_and_must_match_recording(tmp_path):
    harness = runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "scripts/run_final_media_acceptance.py")
    )
    stream = io.BytesIO()
    with wave.open(stream, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(16000)
        recording.writeframes(b"\x01\x00" * 16000 * 10)
    audio = tmp_path / "native.wav"
    audio.write_bytes(stream.getvalue())
    report = tmp_path / "capture.json"
    data = {
        "scenario": {
            "id": "A02",
            "native_activity": True,
            "injected_ui_state": False,
            "device": "test-device",
            "native_audio_origin": "MainActivity AudioRecord cache copied before send; no imported audio",
            "native_audio_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
            "native_media": [
                {"kind": "audio", "sha256": hashlib.sha256(audio.read_bytes()).hexdigest()}
            ],
        }
    }
    report.write_text(json.dumps(data), encoding="utf-8")
    assert harness["validate_native_audio_capture"](report, audio)["device"] == "test-device"
    data["scenario"]["injected_ui_state"] = True
    report.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="observed"):
        harness["validate_native_audio_capture"](report, audio)
    data["scenario"]["injected_ui_state"] = False
    data["scenario"]["native_audio_sha256"] = "0" * 64
    report.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="match"):
        harness["validate_native_audio_capture"](report, audio)
