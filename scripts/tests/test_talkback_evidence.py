"""A second invocation must not replace a failed native acceptance receipt."""

import subprocess
import sys
from pathlib import Path


def test_existing_evidence_is_rejected_before_any_device_operation(tmp_path):
    evidence = tmp_path / "result.json"
    evidence.write_text('{"passed": false}', encoding="utf-8")
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/verify_android_talkback.py"),
            "--serial",
            "must-not-connect",
            "--flow",
            "navigation",
            "--output",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "previous attempts must be retained" in result.stderr
    assert evidence.read_text(encoding="utf-8") == '{"passed": false}'
