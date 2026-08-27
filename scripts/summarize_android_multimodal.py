#!/usr/bin/env python3
"""Summarize Android picker-to-Agent fixture integration evidence."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path


def text_values(path: Path) -> list[str]:
    return [
        node.attrib["text"]
        for node in ET.parse(path).getroot().iter("node")
        if node.attrib.get("text")
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attached-tree", required=True, type=Path)
    parser.add_argument("--result-tree", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--media-post-count", type=int, required=True)
    parser.add_argument("--turn-post-count", type=int, required=True)
    parser.add_argument("--events-get-count", type=int, required=True)
    args = parser.parse_args()

    attached = text_values(args.attached_tree)
    result = text_values(args.result_tree)
    checks = {
        "image_attachment_visible_before_submit": "图片附件" in attached,
        "audio_attachment_visible_before_submit": "音频附件" in attached,
        "media_attachments_cleared_after_completion": (
            "图片附件" not in result and "音频附件" not in result
        ),
        "connection_remained_online": "ONLINE" in result,
        "agent_message_visible": "fixture response" in result,
        "evidence_reference_visible": "fixture:catalog-product-1" in result,
        "two_media_uploads_created": args.media_post_count == 2,
        "one_turn_accepted": args.turn_post_count == 1,
        "one_event_stream_consumed": args.events_get_count == 1,
    }
    evidence = {
        "schema_version": 1,
        "verified_at": datetime.now(UTC).isoformat(),
        "evidence_level": "android_emulator_fixture_integration",
        "checks": checks,
        "http_status_summary": {
            "POST /v1/media 201": args.media_post_count,
            "POST /v1/threads/{id}/turns 202": args.turn_post_count,
            "GET /v1/agent-runs/{id}/events 200": args.events_get_count,
        },
        "passed": all(checks.values()),
        "limitations": [
            "The backend used deterministic fixture tools, not a real model or affiliate provider.",
            "Picker taps came from UIAutomator trees on an emulator, not a physical-device session.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
