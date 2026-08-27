#!/usr/bin/env python3
"""Generate tiny signature-valid image/audio files for Android picker integration tests."""

from __future__ import annotations

import argparse
import base64
from pathlib import Path

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
)
OGG_SIGNATURE_FIXTURE = b"OggS" + bytes(64)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "rag-fixture.png").write_bytes(PNG_1X1)
    (args.output_dir / "rag-fixture.ogg").write_bytes(OGG_SIGNATURE_FIXTURE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
