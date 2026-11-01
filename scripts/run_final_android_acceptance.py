"""One authorized native scenario; verifies Android runner AND PostgreSQL state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/agent-runtime/src"))
from ragcommerce_agent_runtime.token_budget import PostgresTokenBudget  # noqa: E402

PACKAGE = "com.ragcommerce.agent.finaltest"
METHODS = {
    "A01": "a01RealTextRecommendationAndEvidence",
    "A02": "a02NativeVoiceEditClarifyAndRecommend",
    "A03": "a03NativeGalleryInterpretationConfirmationAndRecommendation",
    "A04": "a04DiscoveryFeedbackEndAndPurchase",
    "A05": "a05ChangeBudgetBrandAndStartIndependentMission",
    "A06": "a06VerticalCandidatesComparisonAndConversation",
    "A07": "a07SaveAndManageWaitingCollection",
    "A08": "a08RejectThenApproveActualAgentProposal",
    "A09": "a09RequoteAndConfirmActualExternalSource",
}


def require_expired_api_quote(base_url, owner, product, offer):
    """Read natural expiry before claiming a slot; never change clocks or DB state."""
    request = Request(
        f"{base_url}/v1/products/{product}/offers?fresh=false", headers={"X-User-ID": owner}
    )
    with urlopen(request, timeout=10) as response:
        quotes = json.loads(response.read())["offers"]
    quote = next(item for item in quotes if item["offer_id"] == offer)
    if datetime.fromisoformat(quote["expires_at"].replace("Z", "+00:00")) > datetime.now(UTC):
        raise ValueError(
            f"A09 preflight: quote not yet naturally expired ({quote['expires_at']}); no slot claimed"
        )
    request = Request(
        f"{base_url}/v1/offers/{offer}/resolve",
        data=b"{}",
        headers={"X-User-ID": owner, "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=10) as response:
        resolved = json.loads(response.read())
    if resolved["link_url"] is not None or resolved["expires_at"] != quote["expires_at"]:
        raise ValueError("Expired quote must not resolve or silently renew")
    return quote


def native_stdout_receipt(method, output):
    if not re.search(r"INSTRUMENTATION_CODE:\s*-1\b", output):
        return None
    success = re.search(r"^OK \((\d+) tests?\)$", output, re.MULTILINE)
    failure = re.search(r"Tests run:\s*(\d+),\s*Failures:\s*(\d+)", output)
    if success:
        tests, failed = int(success[1]), 0
    elif failure:
        tests, failed = map(int, failure.groups())
    else:
        return None
    return {
        "method": method,
        "tests": tests,
        "failed": failed,
        "ignored": 0,
        "receipt_source": "instrumentation_stdout",
    }


def native_phase(adb, method, case, arguments, deadline, package=PACKAGE):
    log_command = [*adb, "logcat", "-d", "-s", "TestRunner:I", "*:S"]
    started_pattern = re.compile(r"\S+\s+\S+\s+(\d+)\s+\d+\s+I TestRunner: started: " + method)
    previous_pids = set(
        started_pattern.findall(subprocess.check_output(log_command, text=True, errors="replace"))
    )
    command = [
        *adb,
        "shell",
        "am",
        "instrument",
        "-w",
        "-r",
        "-e",
        "class",
        f"com.ragcommerce.agent.FinalScenarioApiTest#{method}",
        "-e",
        "acceptanceProfile",
        "real",
        "-e",
        "scenario",
        case,
    ]
    for key, value in arguments.items():
        if value:
            command.extend(["-e", key, value])
    command.append(f"{package}.test/androidx.test.runner.AndroidJUnitRunner")
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace"
    )
    native_output = []
    reader = threading.Thread(target=lambda: native_output.extend(process.stdout), daemon=True)
    reader.start()
    try:
        # Observe the device's new runner, even when host ADB stdout disconnects.
        while time.monotonic() < deadline:
            logs = subprocess.run(log_command, capture_output=True, text=True, errors="replace")
            pids = [pid for pid in started_pattern.findall(logs.stdout) if pid not in previous_pids]
            if pids:
                match = re.search(
                    r"\S+\s+\S+\s+"
                    + pids[-1]
                    + r"\s+\d+\s+I TestRunner: run finished: (\d+) tests, (\d+) failed, (\d+) ignored",
                    logs.stdout,
                )
                if match:
                    return {
                        "method": method,
                        "runner_pid": int(pids[-1]),
                        **dict(
                            zip(
                                ("tests", "failed", "ignored"),
                                map(int, match.groups()),
                                strict=True,
                            )
                        ),
                    }
            if process.poll() is not None:
                reader.join(timeout=1)
                receipt = native_stdout_receipt(method, "".join(native_output))
                if receipt is not None:
                    return receipt
                return {
                    "method": method,
                    "host_exit_code": process.returncode,
                    "instrumentation_result_missing": True,
                }
            time.sleep(3)
        subprocess.run(
            [*adb, "shell", "am", "force-stop", package], check=True, capture_output=True
        )
        return {"method": method, "timed_out": True}
    finally:
        if process.poll() is None:
            process.terminate()  # Only this host-side ADB subprocess.


def await_accepted_run_completion(dsn, owner, started_at, deadline):
    """Finish already accepted runs before closing their permit; never submit another Turn."""
    while time.monotonic() < deadline:
        with psycopg.connect(dsn) as connection:
            pending = connection.execute(
                "SELECT COUNT(*) FROM api_turns WHERE owner_id=%s AND created_at>=%s AND status IN ('QUEUED','RUNNING')",
                (owner, started_at),
            ).fetchone()[0]
        if pending == 0:
            return True
        time.sleep(1)
    return False


def run(args):
    if args.case == "A02" and not args.microphone_ready:
        raise ValueError(
            "A02 requires an available person at the computer microphone before claiming its slot"
        )
    package = args.application_id
    manifest = json.loads((ROOT / "evals/v3/final-scenarios.json").read_text(encoding="utf-8"))
    launch = json.loads((ROOT / "output/v3-demo/processes.json").read_text(encoding="utf-8"))
    if launch["provider"] != "mimo" or launch["retrieval"] != "local":
        raise ValueError("explicit mimo/local runtime required")
    adb = [str(args.adb), "-P", str(args.adb_server_port), "-s", args.device]
    installed_apk_path = (
        subprocess.check_output([*adb, "shell", "pm", "path", package], text=True)
        .strip()
        .removeprefix("package:")
    )
    installed_apk_sha256 = hashlib.sha256(
        subprocess.check_output([*adb, "exec-out", "cat", installed_apk_path])
    ).hexdigest()
    subprocess.run(
        [*adb, "shell", "am", "start", "-n", f"{package}/com.ragcommerce.agent.MainActivity"],
        check=True,
        capture_output=True,
    )
    preferences = subprocess.check_output(
        [
            *adb,
            "exec-out",
            "run-as",
            package,
            "cat",
            "files/datastore/shopping_settings.preferences_pb",
        ]
    )
    owner = (
        re.search(
            rb"[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}",
            preferences[preferences.index(b"install_user_id") :],
        )
        .group()
        .decode()
    )
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    source = None
    prior_run_status = None
    expected_products = []
    expected_offers = []
    expected_variant = None
    initial_selection = []
    gallery_timestamp = None
    if args.case == "A03":
        photo = subprocess.check_output(
            [
                *adb,
                "shell",
                "content query --uri content://media/external/images/media --projection _id:_display_name:date_modified --where \"_display_name='RagFinalPhone.png'\"",
            ],
            text=True,
        )
        timestamps = re.findall(r"date_modified=(\d+)", photo)
        if len(timestamps) != 1:
            raise ValueError(
                "exactly one self-owned native gallery fixture is required before spending"
            )
        gallery_timestamp = timestamps[0]
        native_image = subprocess.check_output(
            [*adb, "exec-out", "cat", "/sdcard/Pictures/RagFinalPhone.png"]
        )
        if native_image != (ROOT / "output/final-media/phone.png").read_bytes():
            raise ValueError(
                "native gallery test image must match the self-owned acceptance fixture"
            )
    with psycopg.connect(dsn) as connection:
        cart_before = {
            str(offer): quantity
            for offer, quantity in connection.execute(
                "SELECT offer_id,quantity FROM v3_cart_items WHERE owner_id=%s", (owner,)
            ).fetchall()
        }
    if args.case in {"A06", "A07", "A08", "A09"}:
        with psycopg.connect(dsn) as connection:
            source = connection.execute(
                "SELECT t.thread_id,t.run_id,t.status,r.model_version FROM api_turns t JOIN agent_runs r ON r.id=t.run_id WHERE t.owner_id=%s ORDER BY t.created_at DESC LIMIT 1",
                (owner,),
            ).fetchone()
            allowed_prior_statuses = (
                {"COMPLETED", "FAILED"} if args.case == "A08" else {"COMPLETED"}
            )
            if not source or source[2] not in allowed_prior_statuses or source[3] != "mimo-v2.5":
                raise ValueError(
                    "An existing completed MiMo recommendation is required, not a fabricated setup"
                )
            prior_run_status = source[2]
            # Approval-only turns do not contain products. Reuse the latest real
            # recommendation in the same Mission/version, as ThreadSnapshot does.
            source = connection.execute(
                "SELECT t.thread_id,t.run_id,t.status,r.model_version FROM api_turns t JOIN agent_runs r ON r.id=t.run_id "
                "WHERE t.owner_id=%s AND t.thread_id=%s AND t.command->>'mission_version'="
                "(SELECT command->>'mission_version' FROM api_turns WHERE run_id=%s) "
                "AND t.status='COMPLETED' AND r.model_version='mimo-v2.5' "
                "AND EXISTS(SELECT 1 FROM agent_events e WHERE e.run_id=t.run_id AND e.event_type='products') "
                "ORDER BY t.created_at DESC LIMIT 1",
                (owner, source[0], source[1]),
            ).fetchone()
            if source is None:
                raise ValueError("No real recommendation exists in the current Mission/version")
            events = connection.execute(
                "SELECT data FROM agent_events WHERE run_id=%s AND event_type='products' ORDER BY event_id",
                (source[1],),
            ).fetchall()
            expected_products = [
                item["product_id"] for (data,) in events for item in data["products"]
            ][:3]
            selected = connection.execute(
                "SELECT selected_product_ids FROM api_threads WHERE thread_id=%s", (source[0],)
            ).fetchone()[0]
            initial_selection = selected
            permitted_previous_selection = args.retest_slot and selected == expected_products[:1]
            if len(expected_products) != 3 or (
                args.case == "A06" and selected and not permitted_previous_selection
            ):
                raise ValueError(
                    "A06 requires three actual candidates; only its failed first selection may be reset through native UI"
                )
            if args.case in {"A07", "A08", "A09"}:
                offer_events = connection.execute(
                    "SELECT data FROM agent_events WHERE run_id=%s AND event_type='offers' ORDER BY event_id",
                    (source[1],),
                ).fetchall()
                offers = [item for (data,) in offer_events for item in data["offers"]]
                expected_offers = [
                    next(item["offer_id"] for item in offers if item["product_id"] == product)
                    for product in expected_products[:2]
                ]
                expected_variant = next(
                    item["variant_id"] for item in offers if item["offer_id"] == expected_offers[0]
                )
                if args.case == "A08" and expected_offers[0] in cart_before:
                    raise ValueError(
                        "A08 must verify an actual not-yet-added offer, without deleting prior assets"
                    )
    expired_quote = None
    if args.case == "A09":
        expired_quote = require_expired_api_quote(
            f"http://127.0.0.1:{launch['api_port']}",
            owner,
            expected_products[1],
            expected_offers[1],
        )
    slot = args.retest_slot or args.case
    phase = "retest" if args.retest_slot else "first"
    extra = next(
        (item for item in manifest.get("additional_retests", []) if item["id"] == slot), None
    )
    if phase == "retest" and (
        not args.root_cause or not (ROOT / args.root_cause.split("#", 1)[0]).is_file()
    ):
        raise ValueError("documented corrected root cause required")
    if extra and not (ROOT / extra["authorization_ref"]).is_file():
        raise ValueError("recorded human authorization required")
    budget = PostgresTokenBudget(dsn, manifest["budget_session"], require_scenario=True)
    model_calls_allowed = args.case not in {"A06", "A07", "A09"} and (
        extra.get("model_calls_allowed", True) if extra else True
    )
    budget.start_scenario(
        slot,
        owner,
        "android",
        phase,
        args.root_cause,
        additional_retest_slot=slot if extra else None,
        additional_retest_position=manifest.get("additional_retests", []).index(extra)
        if extra
        else 0,
        authorize_model_calls=model_calls_allowed,
    )
    with psycopg.connect(dsn) as connection:
        started_at = connection.execute(
            "SELECT started_at FROM model_budget_scenarios WHERE session_id=%s AND scenario_id=%s",
            (manifest["budget_session"], slot),
        ).fetchone()[0]
    report = {
        "id": args.case,
        "slot": slot,
        "phase": phase,
        "passed": False,
        "owner_id": owner,
        "application_id": package,
        "device": args.device,
        "adb_server_port": args.adb_server_port,
        "native_activity": True,
        "installed_apk_sha256": installed_apk_sha256,
        "injected_ui_state": False,
        "runtime_source_hashes": launch.get("runtime_source_hashes"),
        "root_cause": args.root_cause,
        "observation_seconds": manifest["observation_seconds"],
        "model_calls_authorized": model_calls_allowed,
        "initial_comparison_selection": initial_selection,
        "prior_run_status": prior_run_status,
        "expired_quote_preflight": expired_quote,
    }
    started = time.monotonic()
    print(f"Native {slot} started; no automatic model retry", flush=True)
    try:
        arguments = {
            "expectedProducts": ",".join(expected_products),
            "expectedOffers": ",".join(expected_offers),
            "initialSelection": ",".join(initial_selection),
            "expectedPhotoTimestamp": gallery_timestamp,
            "expectedOwner": owner,
            "priorRunStatus": prior_run_status,
            "expectedExpiredQuote": expired_quote["expires_at"] if expired_quote else None,
            "microphoneReady": "true" if args.case == "A02" and args.microphone_ready else None,
        }
        deadline = started + manifest["observation_seconds"]
        receipts = [
            native_phase(adb, METHODS[args.case], args.case, arguments, deadline, package=package)
        ]
        first_passed = all(
            receipts[0].get(key) == value
            for key, value in {"tests": 1, "failed": 0, "ignored": 0}.items()
        )
        if args.case == "A07" and first_passed:
            subprocess.run(
                [*adb, "shell", "am", "force-stop", package], check=True, capture_output=True
            )
            report["actual_process_stop_between_phases"] = True
            receipts.append(
                native_phase(
                    adb,
                    "a07VerifyPersistedWaitingCollection",
                    args.case,
                    arguments,
                    deadline,
                    package=package,
                )
            )
        report["native_receipts"] = receipts
        report["runner"] = {
            key: sum(item.get(key, 0) for item in receipts)
            for key in ("tests", "failed", "ignored")
        }
        report["runner_passed"] = (len(receipts) == (2 if args.case == "A07" else 1)) and all(
            all(
                item.get(key) == value
                for key, value in {"tests": 1, "failed": 0, "ignored": 0}.items()
            )
            for item in receipts
        )
        if model_calls_allowed:
            report["accepted_runs_finished_within_window"] = await_accepted_run_completion(
                dsn, owner, started_at, deadline
            )
        with psycopg.connect(dsn) as connection:
            turns = connection.execute(
                "SELECT run_id,status,thread_id,command FROM api_turns WHERE owner_id=%s AND created_at>=%s ORDER BY created_at",
                (owner, started_at),
            ).fetchall()
            results = []
            for run_id, status, thread_id, command in turns:
                events = connection.execute(
                    "SELECT event_type,data FROM agent_events WHERE run_id=%s ORDER BY event_id",
                    (run_id,),
                ).fetchall()
                products = [
                    p for kind, data in events if kind == "products" for p in data["products"]
                ]
                model = connection.execute(
                    "SELECT model_version FROM agent_runs WHERE id=%s", (run_id,)
                ).fetchone()
                results.append(
                    {
                        "run_id": str(run_id),
                        "thread_id": str(thread_id),
                        "execution_path": "catalog_discovery"
                        if command["exploration_result"] is not None
                        else "model_and_tools",
                        "input_text": command["text"],
                        "mission_version": command["mission_version"],
                        "media": command["media"],
                        "media_confirmation": command["media_confirmation"],
                        "media_interpretations": [
                            data for kind, data in events if kind == "media_interpreted"
                        ],
                        "tools_started": [
                            data["tool"] for kind, data in events if kind == "tool_started"
                        ],
                        "approvals": [data for kind, data in events if kind == "approval_required"],
                        "completion_reasons": [
                            data.get("reason") for kind, data in events if kind == "completed"
                        ],
                        "tools_completed": [
                            data["tool"] for kind, data in events if kind == "tool_completed"
                        ],
                        "exploration_updates": [
                            data for kind, data in events if kind == "exploration_updated"
                        ],
                        "status": status,
                        "model": model[0] if model else None,
                        "products": [p["product_id"] for p in products],
                        "offers": [
                            {
                                key: offer[key]
                                for key in ("product_id", "price_minor", "verification")
                            }
                            for kind, data in events
                            if kind == "offers"
                            for offer in data["offers"]
                        ],
                        "evidence_coverage": bool(products)
                        and all(p["evidence_refs"] for p in products),
                        "terminal_events": sum(
                            kind in {"completed", "failed"} for kind, _ in events
                        ),
                        "unauthorized_write": any(
                            kind == "tool_completed"
                            and data["tool"] in {"cart.update", "list.update", "link.resolve"}
                            for kind, data in events
                        ),
                        "write_tools_completed": [
                            data["tool"]
                            for kind, data in events
                            if kind == "tool_completed"
                            and data["tool"] in {"cart.update", "list.update", "link.resolve"}
                        ],
                    }
                )
            if args.case == "A08":
                for index, item in enumerate(results):
                    item["unauthorized_write"] = bool(item["write_tools_completed"]) and not (
                        index == 1
                        and item["write_tools_completed"] == ["cart.update"]
                        and len(item["approvals"]) == 1
                        and item["approvals"][0]["tool"] == "cart.update"
                    )
            paid = connection.execute(
                "SELECT COUNT(*),COALESCE(SUM(used_tokens),0),bool_and(status='http_200') FROM model_budget_calls WHERE session_id=%s AND scenario_id=%s",
                (manifest["budget_session"], slot),
            ).fetchone()
        report.update(
            backend_runs=results,
            paid_call_count=paid[0],
            token_usage=paid[1],
            provider_cost="NOT_AVAILABLE_FROM_PROVIDER",
        )
        if args.case in {"A06", "A07"}:
            with psycopg.connect(dsn) as connection:
                selected = connection.execute(
                    "SELECT selected_product_ids FROM api_threads WHERE thread_id=%s AND owner_id=%s",
                    (source[0], owner),
                ).fetchone()[0]
            report.update(
                source_run_id=str(source[1]),
                source_thread_id=str(source[0]),
                expected_candidates=expected_products,
                persisted_selection=selected,
                reused_existing_real_recommendation=True,
            )
            if args.case == "A06":
                backend_passed = set(selected) == set(expected_products[:2])
            else:
                with psycopg.connect(dsn) as connection:
                    cart = connection.execute(
                        "SELECT offer_id,quantity FROM v3_cart_items WHERE owner_id=%s", (owner,)
                    ).fetchall()
                    saved = connection.execute(
                        "SELECT COUNT(*) FROM v3_list_items i JOIN v3_lists l ON l.list_id=i.list_id WHERE l.owner_id=%s AND i.variant_id=%s",
                        (owner, expected_variant),
                    ).fetchone()[0]
                quantities = {str(offer): quantity for offer, quantity in cart}
                report.update(
                    expected_offers=expected_offers,
                    persisted_cart_quantities=quantities,
                    saved_variant_count=saved,
                )
                backend_passed = (
                    quantities.get(expected_offers[0]) == 2
                    and expected_offers[1] not in quantities
                    and saved == 1
                )
            report["passed"] = (
                report["runner_passed"] and not results and paid[0] == 0 and backend_passed
            )
        elif args.case == "A09":
            with psycopg.connect(dsn) as connection:
                quote_after = connection.execute(
                    "SELECT quote FROM v3_demo_quotes WHERE owner_id=%s AND product_id=%s",
                    (owner, expected_products[1]),
                ).fetchone()[0]
                cart_after = {
                    str(offer): quantity
                    for offer, quantity in connection.execute(
                        "SELECT offer_id,quantity FROM v3_cart_items WHERE owner_id=%s", (owner,)
                    ).fetchall()
                }
            report.update(
                native_requote_and_external_confirmation_passed=report["runner_passed"]
                and not results
                and paid[0] == 0
                and cart_after == {**cart_before, expected_offers[1]: 1},
                native_expired_quote_screen_executed=report["runner_passed"]
                and expired_quote is not None,
                expiry_evidence_level="Naturally expired persisted API quote plus native disabled-link and requote assertions",
                persisted_cart_quantities=cart_after,
                persisted_quote_after=quote_after,
                source_run_id=str(source[1]),
                source_thread_id=str(source[0]),
            )
            report["passed"] = (
                report["native_requote_and_external_confirmation_passed"]
                and report["native_expired_quote_screen_executed"]
                and datetime.fromisoformat(quote_after["collected_at"].replace("Z", "+00:00"))
                >= started_at
                and datetime.fromisoformat(quote_after["expires_at"].replace("Z", "+00:00"))
                > datetime.now(UTC)
            )
        elif args.case == "A08":
            receipt_counts = []
            with psycopg.connect(dsn) as connection:
                for item in results:
                    receipt_counts.append(
                        sum(
                            connection.execute(
                                "SELECT COUNT(*) FROM v3_tool_receipts WHERE owner_id=%s AND invocation_id=%s AND tool_name='cart.update'",
                                (owner, proposal["invocation_id"]),
                            ).fetchone()[0]
                            for proposal in item["approvals"]
                        )
                    )
                target_before_replay = connection.execute(
                    "SELECT quantity,updated_at FROM v3_cart_items WHERE owner_id=%s AND offer_id=%s",
                    (owner, expected_offers[0]),
                ).fetchone()
                cart_after = {
                    str(offer): quantity
                    for offer, quantity in connection.execute(
                        "SELECT offer_id,quantity FROM v3_cart_items WHERE owner_id=%s", (owner,)
                    ).fetchall()
                }
            expected_cart = {**cart_before, expected_offers[0]: 2}
            backend_passed = bool(
                len(results) == 2
                and receipt_counts == [0, 1]
                and results[0]["completion_reasons"] == ["approval_rejected"]
                and "cart.update" not in results[0]["tools_completed"]
                and results[1]["tools_completed"].count("cart.update") == 1
                and all(
                    len(item["approvals"]) == 1
                    and item["approvals"][0]["tool"] == "cart.update"
                    and item["status"] == "COMPLETED"
                    and item["terminal_events"] == 1
                    and item["thread_id"] == str(source[0])
                    and not item["unauthorized_write"]
                    for item in results
                )
                and cart_after == expected_cart
            )
            report.update(
                expected_offer=expected_offers[0],
                receipt_counts=receipt_counts,
                persisted_cart_quantities=cart_after,
            )
            if backend_passed and report["runner_passed"]:
                request = Request(
                    f"http://127.0.0.1:{launch['api_port']}/v1/agent-runs/{results[1]['run_id']}/decisions",
                    data=json.dumps({"tool_name": "cart.update", "approved": True}).encode(),
                    headers={"X-User-ID": owner, "Content-Type": "application/json"},
                )
                with urlopen(request, timeout=5) as response:
                    replay = json.load(response)
                with psycopg.connect(dsn) as connection:
                    target_after_replay = connection.execute(
                        "SELECT quantity,updated_at FROM v3_cart_items WHERE owner_id=%s AND offer_id=%s",
                        (owner, expected_offers[0]),
                    ).fetchone()
                    replay_calls = connection.execute(
                        "SELECT COUNT(*) FROM model_budget_calls WHERE session_id=%s AND scenario_id=%s",
                        (manifest["budget_session"], slot),
                    ).fetchone()[0]
                    terminal_count = connection.execute(
                        "SELECT COUNT(*) FROM agent_events WHERE run_id=%s AND event_type IN ('completed','failed')",
                        (results[1]["run_id"],),
                    ).fetchone()[0]
                report["decision_replay"] = dict(
                    same_run=replay["run_id"] == results[1]["run_id"],
                    cart_unchanged=target_before_replay == target_after_replay,
                    model_calls_unchanged=replay_calls == paid[0],
                    terminal_count=terminal_count,
                )
                backend_passed = all(
                    (
                        report["decision_replay"]["same_run"],
                        report["decision_replay"]["cart_unchanged"],
                        report["decision_replay"]["model_calls_unchanged"],
                        terminal_count == 1,
                    )
                )
            report["passed"] = (
                report["runner_passed"] and backend_passed and paid[0] > 0 and paid[2]
            )
        elif args.case == "A02":
            recorded_audio = subprocess.check_output(
                [*adb, "exec-out", "run-as", package, "cat", "files/final-A02-native.wav"]
            )
            import io
            import wave

            with wave.open(io.BytesIO(recorded_audio)) as wav:
                audio_format = {
                    "sample_rate": wav.getframerate(),
                    "channels": wav.getnchannels(),
                    "sample_width": wav.getsampwidth(),
                    "frames": wav.getnframes(),
                }
            with psycopg.connect(dsn) as connection:
                media = connection.execute(
                    "SELECT id,kind,content_sha256,size_bytes FROM api_media_objects WHERE owner_id=%s AND created_at>=%s",
                    (owner, started_at),
                ).fetchall()
                cart_after = dict(
                    connection.execute(
                        "SELECT offer_id,quantity FROM v3_cart_items WHERE owner_id=%s", (owner,)
                    ).fetchall()
                )
            # Source interpretation, edited confirmation with clarification, then final answer.
            source, clarified, final = results if len(results) == 3 else (None, None, None)
            interpretation = (
                source["media_interpretations"][0]
                if source and len(source["media_interpretations"]) == 1
                else {}
            )
            report.update(
                native_audio_format=audio_format,
                native_audio_sha256=hashlib.sha256(recorded_audio).hexdigest(),
                native_audio_origin="MainActivity AudioRecord cache copied before send; no imported audio",
                native_media=[
                    dict(id=str(row[0]), kind=row[1], sha256=row[2], size_bytes=row[3])
                    for row in media
                ],
            )
            backend_passed = bool(
                source
                and clarified
                and final
                and len(media) == 1
                and media[0][1] == "audio"
                and media[0][2] == hashlib.sha256(recorded_audio).hexdigest()
                and audio_format["sample_rate"] == 16000
                and audio_format["channels"] == 1
                and audio_format["sample_width"] == 2
                and 16000 * 5 <= audio_format["frames"] <= 16000 * 60
                and source["status"] == "WAITING_CLARIFICATION"
                and source["tools_started"] == ["audio.transcribe"]
                and not source["products"]
                and interpretation.get("supported")
                and all(
                    word in interpretation.get("recognized_text", "") for word in ("手机", "通勤")
                )
                and clarified["media_confirmation"]
                and clarified["status"] == "WAITING_CLARIFICATION"
                and clarified["input_text"] == "我想选通勤手机, 预算还没想好, 请先问清楚"
                and final["status"] == "COMPLETED"
                and final["evidence_coverage"]
                and final["terminal_events"] == 1
                and all(
                    item["thread_id"] == source["thread_id"] and not item["unauthorized_write"]
                    for item in results
                )
                and {str(key): value for key, value in cart_after.items()} == cart_before
            )
            report["passed"] = (
                report["runner_passed"] and backend_passed and paid[0] > 0 and paid[2]
            )
        elif args.case == "A03":
            with psycopg.connect(dsn) as connection:
                media = connection.execute(
                    "SELECT id,kind,content_sha256,size_bytes FROM api_media_objects WHERE owner_id=%s AND created_at>=%s",
                    (owner, started_at),
                ).fetchall()
                cart_after = {
                    str(offer): quantity
                    for offer, quantity in connection.execute(
                        "SELECT offer_id,quantity FROM v3_cart_items WHERE owner_id=%s", (owner,)
                    ).fetchall()
                }
            report["native_media"] = [
                dict(id=str(row[0]), kind=row[1], sha256=row[2], size_bytes=row[3]) for row in media
            ]
            report["cart_unchanged"] = cart_before == cart_after
            source = results[0] if len(results) == 2 else None
            confirmed = results[1] if len(results) == 2 else None
            backend_passed = bool(
                source
                and confirmed
                and len(media) == 1
                and media[0][1] == "image"
                and media[0][2]
                == hashlib.sha256((ROOT / "output/final-media/phone.png").read_bytes()).hexdigest()
                and source["media"] == [{"id": str(media[0][0]), "kind": "image"}]
                and source["status"] == "WAITING_CLARIFICATION"
                and source["tools_started"] == ["vision.identify"]
                and not source["products"]
                and not source["unauthorized_write"]
                and len(source["media_interpretations"]) == 1
                and source["media_interpretations"][0]["supported"]
                and source["media_interpretations"][0]["category"] == "手机"
                and confirmed["thread_id"] == source["thread_id"]
                and confirmed["mission_version"] == source["mission_version"] + 1
                and confirmed["media_confirmation"]
                and confirmed["input_text"] == "手机, 预算2000元, 用于日常通勤"
                and confirmed["status"] == "COMPLETED"
                and confirmed["model"] == "mimo-v2.5"
                and confirmed["evidence_coverage"]
                and confirmed["terminal_events"] == 1
                and not confirmed["unauthorized_write"]
                and cart_before == cart_after
            )
            report["passed"] = (
                report["runner_passed"] and backend_passed and paid[0] > 0 and paid[2]
            )
        elif args.case == "A05":
            catalog = {
                row["product_id"]: row
                for row in map(
                    json.loads,
                    (ROOT / "data/demo/catalog.v3.jsonl").read_text(encoding="utf-8").splitlines(),
                )
            }
            with psycopg.connect(dsn) as connection:
                threads = connection.execute(
                    "SELECT thread_id,goal,mission_version,selected_product_ids FROM api_threads WHERE owner_id=%s AND created_at>=%s ORDER BY created_at",
                    (owner, started_at),
                ).fetchall()
                cart_after = {
                    str(offer): quantity
                    for offer, quantity in connection.execute(
                        "SELECT offer_id,quantity FROM v3_cart_items WHERE owner_id=%s", (owner,)
                    ).fetchall()
                }
            report["threads"] = [
                dict(id=str(row[0]), goal=row[1], version=row[2], selected_product_ids=row[3])
                for row in threads
            ]
            report["cart_unchanged"] = cart_before == cart_after
            backend_passed = bool(
                len(results) == 3
                and len(threads) == 2
                and results[0]["thread_id"] == results[1]["thread_id"] != results[2]["thread_id"]
                and results[1]["mission_version"] == results[0]["mission_version"] + 1
                and results[2]["mission_version"] == 1
                and results[1]["input_text"] == "只要 Nova Mobile 品牌手机, 预算1800元"
                and results[2]["input_text"] == "耳机, 预算1000元, 用于日常通勤"
                and threads[0][1] == results[1]["input_text"]
                and threads[1][1] == results[2]["input_text"]
                and all(
                    catalog[p]["brand"] == "Nova Mobile" and catalog[p]["category"] == "手机"
                    for p in results[1]["products"]
                )
                and all(catalog[p]["category"] == "耳机" for p in results[2]["products"])
                and all(
                    item["offers"]
                    and all(
                        offer["price_minor"] is not None
                        and offer["price_minor"] <= limit
                        and offer["verification"] == "DEMO_FIXTURE"
                        for offer in item["offers"]
                    )
                    for item, limit in zip(results, (250000, 180000, 100000), strict=True)
                )
                and all(
                    item["status"] == "COMPLETED"
                    and item["model"] == "mimo-v2.5"
                    and item["evidence_coverage"]
                    and item["terminal_events"] == 1
                    and not item["unauthorized_write"]
                    for item in results
                )
                and cart_before == cart_after
            )
            report["passed"] = (
                report["runner_passed"] and backend_passed and paid[0] > 0 and paid[2]
            )
        elif args.case == "A04":
            discovery = [item for item in results if item["execution_path"] == "catalog_discovery"]
            purchases = [item for item in results if item["execution_path"] == "model_and_tools"]
            with psycopg.connect(dsn) as connection:
                cart_after = {
                    str(offer): quantity
                    for offer, quantity in connection.execute(
                        "SELECT offer_id,quantity FROM v3_cart_items WHERE owner_id=%s", (owner,)
                    ).fetchall()
                }
                threads = connection.execute(
                    "SELECT thread_id,mode,goal,mission_version,exploration FROM api_threads WHERE owner_id=%s AND created_at>=%s ORDER BY created_at",
                    (owner, started_at),
                ).fetchall()
            report["threads"] = [
                dict(
                    thread_id=str(row[0]),
                    mode=row[1],
                    goal=row[2],
                    mission_version=row[3],
                    exploration=row[4],
                )
                for row in threads
            ]
            report["cart_unchanged"] = cart_before == cart_after
            all_updates = [state for item in discovery for state in item["exploration_updates"]]
            ended = [state["exploration"] for state in all_updates if state["exploration"]["ended"]]
            selected = [state for state in all_updates if state["mode"] == "PURCHASE"]
            backend_passed = (
                len(discovery) == 7
                and len(purchases) == 1
                and len(threads) == 2
                and len(ended) == 1
                and len(selected) == 1
                and set(ended[0]["feedback"].values()) == {"interested", "not_interested"}
                and len(set(ended[0]["shown_direction_ids"]))
                == len(ended[0]["shown_direction_ids"])
                and len(selected[0]["exploration"]["feedback"]) == 0
                and purchases[0]["status"] == "COMPLETED"
                and purchases[0]["model"] == "mimo-v2.5"
                and purchases[0]["evidence_coverage"]
                and purchases[0]["terminal_events"] == 1
                and all(
                    item["status"] in {"COMPLETED", "WAITING_CLARIFICATION"}
                    and not item["unauthorized_write"]
                    for item in discovery
                )
                and not purchases[0]["unauthorized_write"]
                and cart_before == cart_after
            )
            report["passed"] = (
                report["runner_passed"] and backend_passed and paid[0] > 0 and paid[2]
            )
        else:
            backend_passed = (
                len(results) == 1
                and results[0]["status"] == "COMPLETED"
                and results[0]["model"] == "mimo-v2.5"
                and results[0]["evidence_coverage"]
                and results[0]["terminal_events"] == 1
                and not results[0]["unauthorized_write"]
            )
            report["passed"] = (
                report["runner_passed"] and backend_passed and paid[0] > 0 and paid[2]
            )
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        budget.finish_scenario(slot, "passed" if report["passed"] else "failed")
        report["shared_budget"] = budget.summary()
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=METHODS, required=True)
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--device", default="emulator-5558")
    parser.add_argument("--adb-server-port", type=int, default=5037)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--retest-slot")
    parser.add_argument("--root-cause")
    parser.add_argument(
        "--application-id", choices=[PACKAGE, "com.ragcommerce.agent.safetytest"], default=PACKAGE
    )
    parser.add_argument(
        "--microphone-ready",
        action="store_true",
        help="Only after human confirms immediate participation",
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("preserve previous reports; choose a new output")
    if args.application_id != PACKAGE and args.case not in {"A08", "A09"}:
        parser.error(
            "The isolated safety installation is limited to A08 and its existing recommendation's A09 quote flow"
        )
    if args.retest_slot and not args.retest_slot.startswith(args.case + "-R"):
        parser.error("retest must belong to the requested case")
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_level": "NATIVE_ANDROID_REAL_API_PROVIDER",
        "source_state": "dirty local candidate; not a public release",
        "scenario": run(args),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Native {args.case} passed={report['scenario']['passed']}")
    return 0 if report["scenario"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
