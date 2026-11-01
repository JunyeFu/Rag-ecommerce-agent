"""Run one native UX case against the isolated explicit-fake API; retain failures."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_android_instrumentation_case import instrumentation_result

CASES = {
    "c9": "c9AccessibilityLabelsHaveContextAndTouchTargets",
    "c1": "c1CandidateQuestionExclusionAndUndo",
    "c2": "c2VerticalCandidatesComparisonAndReturn",
    "c3": "c3NoMatchNeedsExplicitConstraintEdit",
    "c4": "c4SavedFactsContinueRemoveAndWaitingCart",
    "c4a": "c4aSaveBeforeProcessRestart",
    "c4b": "c4bSavedAndWaitingStateAfterProcessRestart",
    "c5": "c5HistoryRenameArchiveAndPublicConversation",
    "c5b": "c5bHistorySurvivesProcessRestart",
    "c6": "c6ExploreExistingEquipmentAndNoPurchase",
    "c7": "c7WaitingCartAcrossNewAndOtherMissions",
    "c7b": "c7bWaitingCartAfterProcessRestart",
    "c7c": "c7cWaitingCartWithoutActiveMissionAfterRestart",
    "c7v": "c7vWaitingCartStableVisuals",
    "c8": "c8SavedBatchCompareAcrossMissionsWithoutChangingTask",
    "c8b": "c8bSavedBatchComparisonAfterProcessRestart",
    "c8c": "c8cRemovingComparedSavedItemInvalidatesResultAndClearIsReversible",
    "c8d": "c8dClearedComparisonStaysClearedAfterRestart",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--scale", choices=["1.0", "2.0"], required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--package", default="com.ragcommerce.agent.uxreview")
    parser.add_argument(
        "--owner-id",
        required=True,
        help="Explicit isolated install identity; never infer ownership from the first database row",
    )
    parser.add_argument(
        "--output-root", type=Path, default=Path("output/android-ux-native-20261021")
    )
    args = parser.parse_args()
    output = args.output_root / f"{args.case}-{args.scale}-attempt{args.attempt}"
    if output.exists():
        raise FileExistsError("Retain old results; use a new attempt number")
    output.mkdir(parents=True)
    adb = [
        "C:/Users/fujunye/AppData/Local/Android/Sdk/platform-tools/adb.exe",
        "-P",
        "5037",
        "-s",
        "emulator-5554",
    ]
    package = args.package

    def command(*values):
        return subprocess.run(
            [*adb, *values],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )

    started = datetime.now(UTC).isoformat()
    with psycopg.connect(os.environ["API_DATABASE_URL"], row_factory=dict_row) as connection:
        owner = args.owner_id
        before_threads = connection.execute(
            "SELECT thread_id,mission_version,selected_product_ids FROM api_threads WHERE owner_id=%s ORDER BY created_at",
            (owner,),
        ).fetchall()
        before_saved = connection.execute(
            "SELECT l.owner_id,l.list_id,i.variant_id FROM v3_lists l JOIN v3_list_items i USING(list_id) WHERE l.owner_id=%s ORDER BY l.list_id,i.variant_id",
            (owner,),
        ).fetchall()
        before_cart = connection.execute(
            "SELECT owner_id,offer_id,quantity FROM v3_cart_items WHERE owner_id=%s ORDER BY owner_id,offer_id",
            (owner,),
        ).fetchall()
        before_quotes = connection.execute(
            "SELECT product_id,quote->>'offer_id' AS offer_id,quote->>'collected_at' AS collected_at,quote->>'expires_at' AS expires_at FROM v3_demo_quotes WHERE owner_id=%s ORDER BY product_id",
            (owner,),
        ).fetchall()
    command("shell", "settings", "put", "system", "font_scale", args.scale).check_returncode()
    command("shell", "am", "force-stop", package).check_returncode()
    # The shared adb connection once returned 255 before JUnit finished. Persist
    # that invocation's standard JUnit output on-device; never restart the case.
    receipt = f"/sdcard/ux-instrument-{uuid4().hex}.txt"
    native_command = (
        f"am instrument -w -r -e class com.ragcommerce.agent.DecisionExperienceApiTest#{CASES[args.case]} "
        f"-e uxScale {args.scale} {package}.test/androidx.test.runner.AndroidJUnitRunner"
    )
    deadline = time.monotonic() + 180
    test = command(
        "shell",
        f"{native_command} > {receipt} 2>&1; printf '\\nUX_PROCESS_EXIT:%s\\n' \"$?\" >> {receipt}",
    )
    device_log = command("shell", "cat", receipt)
    native = device_log.stdout
    while (
        "UX_PROCESS_EXIT:" not in native
        and device_log.returncode == 0
        and time.monotonic() < deadline
    ):
        time.sleep(0.5)
        device_log = command("shell", "cat", receipt)
        native = device_log.stdout
    process_exit = re.search(r"UX_PROCESS_EXIT:(\d+)", native)
    native_exit = int(process_exit.group(1)) if process_exit else 255
    print(native)
    result = instrumentation_result(native, native_exit)
    command("shell", "rm", receipt)
    command("pull", f"/sdcard/Android/data/{package}/files", str(output / "screenshots"))
    evidence = {
        "case": args.case,
        "scale": args.scale,
        "attempt": args.attempt,
        "started_at": started,
        "finished_at": datetime.now(UTC).isoformat(),
        "device": "Pixel_9a / emulator-5554",
        "owner_id": owner,
        "provider": "explicit fake DemoProvider",
        "mimo_calls": 0,
        "result": result,
        "native_exit_code": native_exit,
        "transport_exit_code": test.returncode,
        "device_receipt_complete": process_exit is not None,
        "qa_rate_limit_per_minute": 600,
        "production_rate_policy_tested": False,
        "failures": [
            line.strip()
            for line in native.splitlines()
            if any(
                v in line
                for v in ("AssertionError", "FAILURES", "Exception:", "Error:", "Process crashed")
            )
        ][:12],
    }
    destination = output / "result.json"
    destination.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # Read real DB state independently. Do not multiply rate-limited user HTTP reads
    # by all historical threads: that contaminated the first acceptance batch.
    with psycopg.connect(os.environ["API_DATABASE_URL"], row_factory=dict_row) as connection:
        rows = connection.execute(
            "SELECT thread_id,owner_id,goal,mission_version,experience,selected_product_ids,mode,exploration FROM api_threads WHERE owner_id=%s ORDER BY created_at",
            (owner,),
        ).fetchall()
        turns = connection.execute(
            "SELECT thread_id,run_id,status,command->'recommendation_feedback' AS feedback,command->'excluded_product_ids' AS excluded_products FROM api_turns WHERE owner_id=%s ORDER BY created_at",
            (owner,),
        ).fetchall()
        current_turns = connection.execute(
            "SELECT run_id,status FROM api_turns WHERE owner_id=%s AND created_at >= %s ORDER BY created_at",
            (owner, started),
        ).fetchall()
        saved = connection.execute(
            "SELECT l.owner_id,l.list_id,i.variant_id FROM v3_lists l JOIN v3_list_items i USING(list_id) WHERE l.owner_id=%s ORDER BY l.list_id,i.variant_id",
            (owner,),
        ).fetchall()
        cart = connection.execute(
            "SELECT owner_id,offer_id,quantity FROM v3_cart_items WHERE owner_id=%s ORDER BY owner_id,offer_id",
            (owner,),
        ).fetchall()
        quotes = connection.execute(
            "SELECT product_id,quote->>'offer_id' AS offer_id,quote->>'collected_at' AS collected_at,quote->>'expires_at' AS expires_at FROM v3_demo_quotes WHERE owner_id=%s ORDER BY product_id",
            (owner,),
        ).fetchall()
    evidence.update(
        database_threads=rows,
        database_turns=turns,
        saved=saved,
        cart=cart,
        quote_readback={
            "before": before_quotes,
            "after": quotes,
            "unchanged": before_quotes == quotes,
        },
        commerce_unchanged={"saved": before_saved == saved, "cart": before_cart == cart},
        current_turns=current_turns,
        overall_passed=result["passed"]
        and all(turn["status"] == "COMPLETED" for turn in current_turns),
    )
    if args.case in {"c8b", "c8c", "c8d"}:
        evidence["saved_comparison_readback"] = {
            "no_new_runs": not current_turns,
            "original_quotes_not_renewed": before_quotes == quotes,
            "waiting_cart_unchanged": before_cart == cart,
            "mission_selection_unchanged": before_threads
            == [
                {key: row[key] for key in ("thread_id", "mission_version", "selected_product_ids")}
                for row in rows
            ],
        }
        if args.case != "c8c":
            evidence["saved_comparison_readback"]["saved_list_unchanged"] = before_saved == saved
        else:
            evidence["saved_comparison_readback"]["only_one_saved_item_removed"] = (
                len(before_saved) - len(saved) == 1
            )
        evidence["overall_passed"] &= all(evidence["saved_comparison_readback"].values())
    destination.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "case": args.case,
                "scale": args.scale,
                **result,
                "overall_passed": evidence["overall_passed"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if evidence["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
