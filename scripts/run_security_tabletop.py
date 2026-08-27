#!/usr/bin/env python3
"""Replay the local connector-revocation and incident-containment tabletop."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "packages/connectors/src"),
    str(ROOT / "packages/domain/src"),
]

from ragcommerce_connectors import (  # noqa: E402
    ConnectorError,
    SafeLinkPolicy,
    load_fixture_connectors,
)

OUTPUT = ROOT / "docs/security/evidence/incident-tabletop.json"


def render() -> str:
    connectors = load_fixture_connectors(ROOT / "packages/connectors/fixtures")
    live_disabled = all(not connector.capability.live_enabled for connector in connectors)
    private_denied = False
    try:
        SafeLinkPolicy(frozenset({"item.example"})).validate_chain(
            ("https://item.example/p/1",), {"item.example": ("127.0.0.1",)}
        )
    except ConnectorError:
        private_denied = True
    runbook = (ROOT / "docs/security/connector-revocation.md").read_text(encoding="utf-8")
    passed = live_disabled and private_denied and "UNAUTHORIZED" in runbook and "BLOCKED" in runbook
    result = {
        "schema_version": 1,
        "status": "passed_local_tabletop" if passed else "failed",
        "steps": [
            {
                "name": "fixture_connectors_are_non_live",
                "passed": live_disabled,
                "connector_count": len(connectors),
            },
            {"name": "private_dns_target_is_denied", "passed": private_denied},
            {
                "name": "revocation_runbook_has_fail_closed_states",
                "passed": "UNAUTHORIZED" in runbook and "BLOCKED" in runbook,
            },
        ],
        "external_actions_executed": False,
        "external_gate": "Platform-side credential revocation and live recovery require connector owner authority",
    }
    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render()
    passed = json.loads(expected)["status"] == "passed_local_tabletop"
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != expected:
            print("DRIFT docs/security/evidence/incident-tabletop.json")
            return 1
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(expected, encoding="utf-8", newline="\n")
    print(f"security_tabletop={str(passed).lower()} external_actions=false")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
