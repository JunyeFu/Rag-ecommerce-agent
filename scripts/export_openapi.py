#!/usr/bin/env python3
"""Export or verify the deterministic FastAPI OpenAPI document."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "apps/api/src"),
    str(ROOT / "packages/agent-runtime/src"),
    str(ROOT / "packages/contracts/generated/python"),
]

from ragcommerce_api.app import app  # noqa: E402

OUTPUT = ROOT / "packages/contracts/openapi.json"


def render() -> str:
    document = app.openapi()
    document["info"]["description"] = (
        "Unified multimodal shopping turns, bounded media references and resumable public Agent events."
    )
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != expected:
            print("DRIFT packages/contracts/openapi.json")
            return 1
        print(f"openapi=verified paths={len(app.openapi()['paths'])}")
        return 0
    OUTPUT.write_text(expected, encoding="utf-8", newline="\n")
    print(f"openapi=generated paths={len(app.openapi()['paths'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
