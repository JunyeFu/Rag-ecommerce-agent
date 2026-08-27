#!/usr/bin/env python3
"""Validate mission and selected-tab restoration from UIAutomator trees."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path


def inspect(path: Path, expected_text: str) -> dict[str, object]:
    root = ET.parse(path).getroot()
    nodes = list(root.iter("node"))
    selected_labels = [
        child.attrib.get("text", "")
        for node in nodes
        if node.attrib.get("selected") == "true"
        for child in node.iter("node")
        if child.attrib.get("text")
    ]
    expected_present = any(expected_text in node.attrib.get("text", "") for node in nodes)
    root_bounds = next(
        (
            node.attrib.get("bounds")
            for node in nodes
            if node.attrib.get("resource-id") == "android:id/content"
        ),
        None,
    )
    return {
        "expected_mission_present": expected_present,
        "selected_labels": selected_labels,
        "root_bounds": root_bounds,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--process-tree", required=True, type=Path)
    parser.add_argument("--rotation-tree", required=True, type=Path)
    parser.add_argument("--expected", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    process = inspect(args.process_tree, args.expected)
    rotation = inspect(args.rotation_tree, args.expected)
    process_pass = process["expected_mission_present"] and "导购" in process["selected_labels"]
    rotation_pass = rotation["expected_mission_present"]
    result = {
        "schema_version": 1,
        "verified_at": datetime.now(UTC).isoformat(),
        "evidence_level": "android_emulator_ui_tree",
        "expected_mission": args.expected,
        "process_restart": {**process, "passed": process_pass},
        "rotation_recreation": {**rotation, "passed": rotation_pass},
        "passed": process_pass and rotation_pass,
        "limitations": [
            "This is emulator process/configuration recovery evidence, not physical-device evidence."
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
