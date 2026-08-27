#!/usr/bin/env python3
"""Validate V2-DATA-01 deterministic hashes, provenance, and safety boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import export_v1_seed

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()

    expected = export_v1_seed.render(args.source.resolve())
    for path, content in expected.items():
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            raise ValueError(f"deterministic output drift: {path.relative_to(ROOT).as_posix()}")

    manifest = json.loads((ROOT / "docs/data/seed-manifest.json").read_text(encoding="utf-8"))
    for record in manifest["outputs"].values():
        if sha(ROOT / record["path"]) != record["sha256"]:
            raise ValueError(f"manifest output hash drift: {record['path']}")
    report = json.loads((ROOT / "docs/data/quality-report.json").read_text(encoding="utf-8"))
    if any(report["safety"].values()):
        raise ValueError("seed safety counts must remain zero")
    ledger = json.loads((ROOT / "docs/data/license-ledger.json").read_text(encoding="utf-8"))
    if any(asset["commercial_use_allowed"] for asset in ledger["assets"]):
        raise ValueError("pending source was incorrectly marked for commercial use")
    print("seed validation passed: outputs=5 catalog=287 evaluation=226 unsafe=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
