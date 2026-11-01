"""Skipped instrumentation cannot prove a native business flow."""

import runpy
from pathlib import Path

import pytest


@pytest.mark.parametrize("status", [-3, -4])
def test_skip_is_not_a_successful_case(status):
    harness = runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "scripts/run_android_instrumentation_case.py")
    )
    result = harness["instrumentation_result"](
        f"INSTRUMENTATION_STATUS_CODE: {status}\nOK (1 test)\nINSTRUMENTATION_CODE: -1", 0
    )
    assert result == {"passed": False, "tests": 1, "skipped": 1}


def test_actual_completed_case_has_no_skip():
    harness = runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "scripts/run_android_instrumentation_case.py")
    )
    assert harness["instrumentation_result"]("OK (8 tests)\nINSTRUMENTATION_CODE: -1", 0) == {
        "passed": True,
        "tests": 8,
        "skipped": 0,
    }
