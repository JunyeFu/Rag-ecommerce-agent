"""Open/close a frozen paid acceptance slot; no model call or credential loading."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/agent-runtime/src"))
from ragcommerce_agent_runtime.token_budget import PostgresTokenBudget  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["open", "close", "summary"])
    parser.add_argument("--case")
    parser.add_argument("--owner", type=UUID)
    parser.add_argument("--phase", choices=["first", "retest"], default="first")
    parser.add_argument("--root-cause")
    parser.add_argument("--result", choices=["passed", "failed", "blocked"])
    args = parser.parse_args()
    manifest = json.loads((ROOT / "evals/v3/final-scenarios.json").read_text(encoding="utf-8"))
    budget = PostgresTokenBudget(
        os.environ["DATABASE_URL"], manifest["budget_session"], require_scenario=True
    )
    if args.action == "open":
        case = (args.case or "").split("-R", 1)[0]
        groups = {
            "golden": manifest["golden"]["ids"],
            "media": [item["id"] for item in manifest["media"]],
            "android": [item["id"] for item in manifest["android"]],
        }
        group = next((name for name, ids in groups.items() if case in ids), None)
        if not group or args.owner is None or (args.phase == "first" and args.case != case):
            parser.error("a frozen case ID and explicit owner are required")
        if args.phase == "retest" and (
            not args.root_cause or not (ROOT / args.root_cause.split("#", 1)[0]).is_file()
        ):
            parser.error("retest requires an existing project root-cause document")
        additional = next(
            (item for item in manifest.get("additional_retests", []) if item["id"] == args.case),
            None,
        )
        if additional and (
            args.phase != "retest" or not (ROOT / additional["authorization_ref"]).is_file()
        ):
            parser.error("additional retest requires its recorded human authorization")
        budget.start_scenario(
            args.case,
            args.owner,
            group,
            args.phase,
            args.root_cause,
            additional_retest_slot=args.case if additional else None,
            additional_retest_position=manifest.get("additional_retests", []).index(additional)
            if additional
            else 0,
            authorize_model_calls=(
                additional.get("model_calls_allowed", True)
                if additional
                else next(
                    (
                        item.get("model_calls_allowed", True)
                        for item in manifest.get(group, [])
                        if isinstance(item, dict) and item["id"] == case
                    ),
                    True,
                )
            ),
        )
    elif args.action == "close":
        if not args.case or not args.result:
            parser.error("close requires case and observed result")
        budget.finish_scenario(args.case, args.result)
    print(json.dumps(budget.summary(), ensure_ascii=False))


if __name__ == "__main__":
    main()
