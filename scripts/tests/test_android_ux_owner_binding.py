"""A native run must never attribute its writes to an arbitrary integration user."""

import subprocess
import sys
from pathlib import Path


def test_native_runner_requires_explicit_install_identity():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/verify_android_decision_ux.py"),
            "--case",
            "c9",
            "--scale",
            "1.0",
            "--attempt",
            "99",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "--owner-id" in result.stderr
