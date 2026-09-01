#!/usr/bin/env python3
"""Reject only retired compatibility and silent-fallback surfaces."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PATHS = (
    "apps/ops-web/src/ops-data.ts",
    "packages/connectors/src/ragcommerce_connectors/resilience.py",
    "data/seed",
    "evals/seed",
)
FORBIDDEN_TEXT = {
    "apps/android/app/src/main": (
        "LegacyShoppingApp",
        'setOf("GUIDE", "LISTS", "CART")',
        "runCatching { JSONObject",
        "runCatching { JSONArray",
    ),
    "apps/ops-web/src": ('from "./ops-data"', "from './ops-data'"),
    "packages/connectors/src": ("RetryPolicy", "CircuitBreaker"),
}


def main() -> int:
    failures = []
    for path in FORBIDDEN_PATHS:
        target = ROOT / path
        if target.is_file() or (
            target.is_dir() and any(item.is_file() for item in target.rglob("*"))
        ):
            failures.append(path)
    for root, needles in FORBIDDEN_TEXT.items():
        for path in (ROOT / root).rglob("*"):
            if not path.is_file() or path.suffix not in {
                ".kt",
                ".kts",
                ".java",
                ".py",
                ".ts",
                ".tsx",
            }:
                continue
            text = path.read_text(encoding="utf-8")
            failures.extend(
                f"{path.relative_to(ROOT).as_posix()}: {needle}"
                for needle in needles
                if needle in text
            )
    if failures:
        print("minimality violations:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("minimality=pass retired_surfaces=absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
