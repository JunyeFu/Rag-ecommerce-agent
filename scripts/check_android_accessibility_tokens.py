#!/usr/bin/env python3
"""Check Android design-token contrast pairs used by small text and status UI."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

COLOR_PATTERN = re.compile(r"val\s+(\w+)\s*=\s*Color\(0xFF([0-9A-Fa-f]{6})\)")
PAIRS = (
    ("TextPrimary", "Background"),
    ("TextPrimary", "Surface"),
    ("TextSecondary", "Background"),
    ("TextSecondary", "Surface"),
    ("Brand", "Surface"),
    ("Warning", "WarningContainer"),
    ("Danger", "Surface"),
)


def channel(value: int) -> float:
    normalized = value / 255
    return normalized / 12.92 if normalized <= 0.04045 else ((normalized + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    red, green, blue = (int(hex_color[index : index + 2], 16) for index in (0, 2, 4))
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def contrast(first: str, second: str) -> float:
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tokens", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    colors = dict(COLOR_PATTERN.findall(args.tokens.read_text(encoding="utf-8")))
    checks = []
    for foreground, background in PAIRS:
        ratio = contrast(colors[foreground], colors[background])
        checks.append(
            {
                "foreground": foreground,
                "background": background,
                "ratio": round(ratio, 2),
                "required": 4.5,
                "passed": ratio >= 4.5,
            },
        )
    result = {
        "schema_version": 1,
        "verified_at": datetime.now(UTC).isoformat(),
        "standard": "WCAG 2 contrast formula; 4.5:1 small-text threshold",
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
        "limitations": ["TalkBack focus order still requires physical-device human acceptance."],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
