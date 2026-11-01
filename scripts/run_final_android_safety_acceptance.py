"""One A10 slot, with an isolated native identity and real network/process interruption."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import psycopg

from run_final_android_acceptance import await_accepted_run_completion, native_phase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/agent-runtime/src"))
from ragcommerce_agent_runtime.token_budget import PostgresTokenBudget  # noqa: E402

PACKAGE = "com.ragcommerce.agent.safetytest"


def interrupt_owned_process(shell, package):
    shell("am", "start", "-W", "-n", f"{package}/com.ragcommerce.agent.MainActivity")
    process_id = shell("pidof", package)
    shell("am", "force-stop", package)
    return process_id


def validate_erasure_source(owner, source_owner, threads, turns, cart):
    if (
        not source_owner
        or str(source_owner[0]) != owner
        or threads != 1
        or turns != [("COMPLETED",), ("COMPLETED",)]
        or cart != [(2,)]
    ):
        raise ValueError(
            "Erase only the exact completed A10-R3 isolated identity and its quantity-2 cart"
        )


def run(args):
    manifest = json.loads((ROOT / "evals/v3/final-scenarios.json").read_text(encoding="utf-8"))
    launch = json.loads((ROOT / "output/v3-demo/processes.json").read_text(encoding="utf-8"))
    if (launch["provider"], launch["retrieval"]) != ("mimo", "local"):
        raise ValueError("Explicit MiMo/local runtime is required")
    adb = [str(args.adb), "-P", str(args.adb_server_port), "-s", args.device]

    def shell(*command):
        return subprocess.check_output([*adb, "shell", *command], text=True).strip()

    def owner_id():
        payload = subprocess.check_output(
            [
                *adb,
                "exec-out",
                "run-as",
                PACKAGE,
                "cat",
                "files/datastore/shopping_settings.preferences_pb",
            ]
        )
        return (
            re.search(
                rb"[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}",
                payload[payload.index(b"install_user_id") :],
            )
            .group()
            .decode()
        )

    shell("am", "start", "-n", f"{PACKAGE}/com.ragcommerce.agent.MainActivity")
    # Let the genuine first launch create its local installation identity.
    deadline = time.monotonic() + 10
    while True:
        ready = (
            subprocess.run(
                [
                    *adb,
                    "shell",
                    "run-as",
                    PACKAGE,
                    "test",
                    "-f",
                    "files/datastore/shopping_settings.preferences_pb",
                ],
                capture_output=True,
            ).returncode
            == 0
        )
        if ready:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("Local installation identity was not created")
        time.sleep(0.1)
    owner = owner_id()
    resume_source = args.resume_pending_from or args.resume_erasure_from
    erasure_only = bool(args.resume_erasure_from)
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as connection:
        existing_threads = connection.execute(
            "SELECT COUNT(*) FROM api_threads WHERE owner_id=%s", (owner,)
        ).fetchone()[0]
        if resume_source:
            source_owner = connection.execute(
                "SELECT owner_id FROM model_budget_scenarios WHERE session_id=%s AND scenario_id=%s AND finished_at IS NOT NULL",
                (manifest["budget_session"], resume_source),
            ).fetchone()
            owned_turns = connection.execute(
                "SELECT status FROM api_turns WHERE owner_id=%s ORDER BY created_at", (owner,)
            ).fetchall()
            if erasure_only:
                cart_rows = connection.execute(
                    "SELECT quantity FROM v3_cart_items WHERE owner_id=%s", (owner,)
                ).fetchall()
                validate_erasure_source(
                    owner, source_owner, existing_threads, owned_turns, cart_rows
                )
            elif (
                not source_owner
                or str(source_owner[0]) != owner
                or existing_threads != 1
                or owned_turns != [("COMPLETED",), ("WAITING_APPROVAL",)]
            ):
                raise ValueError(
                    "Resume only the exact A10-R2 isolated identity and its untouched pending task"
                )
            source_calls, source_all_ok = connection.execute(
                "SELECT COUNT(*),bool_and(status='http_200') FROM model_budget_calls WHERE session_id=%s AND scenario_id=%s",
                (manifest["budget_session"], resume_source),
            ).fetchone()
            if source_calls == 0 or not source_all_ok:
                raise ValueError("The resumed source must have recorded real provider calls")
            if (
                not erasure_only
                and connection.execute(
                    "SELECT COUNT(*) FROM v3_cart_items WHERE owner_id=%s", (owner,)
                ).fetchone()[0]
            ):
                raise ValueError("The resumed safety identity must not contain prior cart assets")
        elif existing_threads:
            raise ValueError(
                "A10 must use a fresh isolated identity; don't delete or reuse prior user assets"
            )
        protected_cart = connection.execute(
            "SELECT owner_id,offer_id,quantity,updated_at FROM v3_cart_items WHERE owner_id<>%s ORDER BY owner_id,offer_id",
            (owner,),
        ).fetchall()
    budget = PostgresTokenBudget(dsn, manifest["budget_session"], require_scenario=True)
    slot = args.retest_slot or "A10"
    phase_name = "retest" if args.retest_slot else "first"
    extra = next(
        (item for item in manifest.get("additional_retests", []) if item["id"] == slot), None
    )
    if args.retest_slot and (extra is None or not (ROOT / extra["authorization_ref"]).is_file()):
        raise ValueError("Recorded direct human authorization is required")
    budget.start_scenario(
        slot,
        owner,
        "android",
        phase_name,
        "docs/evidence/v3/final-source-analysis-repair-20261012.json"
        if slot == "A10-R5"
        else "docs/defects/V3-FINAL-CLOSEOUT.md#f46-审批网络异常后必须提供只读恢复入口"
        if erasure_only
        else "docs/defects/V3-FINAL-CLOSEOUT.md#f39-a10原生测试标签与生产控件一致"
        if extra
        else None,
        additional_retest_slot=slot if extra else None,
        additional_retest_position=manifest.get("additional_retests", []).index(extra)
        if extra
        else 0,
        authorize_model_calls=not erasure_only,
    )
    started_at = datetime.now(UTC)
    report = {
        "id": "A10",
        "slot": slot,
        "phase": phase_name,
        "passed": False,
        "owner_id": owner,
        "resumed_from_slot": resume_source,
        "erasure_only": erasure_only,
        "device": args.device,
        "application_id": PACKAGE,
        "injected_ui_state": False,
        "runtime_source_hashes": launch["runtime_source_hashes"],
        "native_receipts": [],
        "observation_seconds": manifest["observation_seconds"],
    }
    apk = shell("pm", "path", PACKAGE).removeprefix("package:")
    report["installed_apk_sha256"] = hashlib.sha256(
        subprocess.check_output([*adb, "exec-out", "cat", apk])
    ).hexdigest()
    deadline = time.monotonic() + manifest["observation_seconds"]

    def network_state():
        chain = {"chain:disabled": "false", "chain:enabled": "true"}[
            shell("cmd", "connectivity", "get-chain3-enabled")
        ]
        package = {"allow": "true", "deny": "false"}[
            shell("cmd", "connectivity", "get-package-networking-enabled", PACKAGE).split(":")[-1]
        ]
        return chain, package

    original_chain, original_package = network_state()
    report["original_emulator_network_state"] = {
        "chain3_enabled": original_chain,
        "package_networking_enabled": original_package,
    }
    network_changed = False
    arguments = {"expectedOwner": owner}

    def phase(method):
        receipt = native_phase(adb, method, "A10", arguments, deadline, package=PACKAGE)
        report["native_receipts"].append(receipt)
        if any(
            receipt.get(key) != value
            for key, value in {"tests": 1, "failed": 0, "ignored": 0}.items()
        ):
            raise RuntimeError("Native phase failed; don't repeat it")

    def api_get(path, user=owner):
        with urlopen(
            Request(f"http://127.0.0.1:{launch['api_port']}{path}", headers={"X-User-ID": user}),
            timeout=5,
        ) as response:
            return json.load(response)

    def restore_network():
        shell("cmd", "connectivity", "set-package-networking-enabled", original_package, PACKAGE)
        shell("cmd", "connectivity", "set-chain3-enabled", original_chain)

    try:
        if not resume_source:
            phase("a10CreateActualRecommendationForIsolatedIdentity")
        with psycopg.connect(dsn) as connection:
            thread, first_run, model = connection.execute(
                "SELECT t.thread_id,t.run_id,r.model_version FROM api_turns t JOIN agent_runs r ON r.id=t.run_id WHERE t.owner_id=%s ORDER BY t.created_at",
                (owner,),
            ).fetchone()
            offers = connection.execute(
                "SELECT data FROM agent_events WHERE run_id=%s AND event_type='offers' ORDER BY event_id DESC LIMIT 1",
                (first_run,),
            ).fetchone()[0]["offers"]
        if model != "mimo-v2.5" or not offers:
            raise ValueError("An actual MiMo recommendation is required")
        arguments["expectedOffer"] = offers[0]["offer_id"]
        if erasure_only:
            arguments["diagnosticProfile"] = "read-only"
            phase("inspectCompletedApprovalRecoveryReadOnly")
        else:
            phase(
                "a10VerifyExistingPendingApproval"
                if args.resume_pending_from
                else "a10CreateActualPendingApproval"
            )
        pending = api_get(f"/v1/threads/{thread}")
        if not erasure_only and (
            pending["status"] != "WAITING_APPROVAL"
            or pending["pending_action"] != "cart.update"
            or not pending["candidates"]
        ):
            raise ValueError("Actual pending snapshot must retain Mission candidates")
        report["resumed_snapshot" if erasure_only else "before_interruption"] = {
            "thread_id": str(thread),
            "run_id": pending["active_run_id"],
            "last_event_id": pending["last_event_id"],
            "candidate_count": len(pending["candidates"]),
            "pending_action": pending["pending_action"],
        }
        if not erasure_only:
            report["process_before_stop"] = interrupt_owned_process(shell, PACKAGE)
            network_changed = True
            shell("cmd", "connectivity", "set-package-networking-enabled", "false", PACKAGE)
            shell("cmd", "connectivity", "set-chain3-enabled", "true")
            phase("a10OfflineAfterActualProcessStop")
            report["offline_approval_unchanged"] = (
                api_get(f"/v1/threads/{thread}")["active_run_id"] == pending["active_run_id"]
                and not api_get("/v1/cart")["items"]
            )
            restore_network()
            network_changed = False
            shell("am", "force-stop", PACKAGE)
            phase("a10RestorePendingApprovalAndApproveOnce")
        completed = api_get(f"/v1/threads/{thread}")
        cart = api_get("/v1/cart")
        with psycopg.connect(dsn) as connection:
            run = pending["active_run_id"]
            terminal = connection.execute(
                "SELECT COUNT(*) FROM agent_events WHERE run_id=%s AND event_type IN ('completed','failed')",
                (run,),
            ).fetchone()[0]
            receipts = connection.execute(
                "SELECT COUNT(*) FROM v3_tool_receipts WHERE owner_id=%s AND tool_name='cart.update'",
                (owner,),
            ).fetchone()[0]
            turns = connection.execute(
                "SELECT run_id,status FROM api_turns WHERE owner_id=%s ORDER BY created_at",
                (owner,),
            ).fetchall()
        report["before_deletion"] = {
            "status": completed["status"],
            "candidate_count": len(completed["candidates"]),
            "last_event_id": completed["last_event_id"],
            "terminal_events": terminal,
            "cart_tool_receipts": receipts,
            "runs": [{"run_id": str(run_id), "status": status} for run_id, status in turns],
            "cart": cart,
        }
        # A separate real owner cannot read this Mission. No fabricated UI state.
        try:
            api_get(f"/v1/threads/{thread}", "0f71a5c2-3a93-44b0-af6f-5498044ec431")
            report["foreign_owner_http_status"] = 200
        except HTTPError as error:
            report["foreign_owner_http_status"] = error.code
        phase("a10DeleteOnlyIsolatedIdentityThroughUi")
        report["new_installation_identity"] = owner_id()
        with psycopg.connect(dsn) as connection:
            remaining = {
                table: connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE owner_id=%s", (owner,)
                ).fetchone()[0]
                for table in (
                    "api_threads",
                    "api_turns",
                    "api_media_objects",
                    "v3_cart_items",
                    "v3_lists",
                    "v3_watchers",
                    "v3_tool_receipts",
                    "v3_demo_quotes",
                )
            }
            protected_after = connection.execute(
                "SELECT owner_id,offer_id,quantity,updated_at FROM v3_cart_items WHERE owner_id<>%s ORDER BY owner_id,offer_id",
                (owner,),
            ).fetchall()
        report["remaining_owner_rows"] = remaining
        report["other_cart_rows_unchanged"] = protected_after == protected_cart
        report["passed"] = all(
            (
                erasure_only or report["offline_approval_unchanged"],
                completed["status"] == "COMPLETED",
                bool(completed["candidates"]),
                terminal == 1,
                receipts == 1,
                len(turns) == 2,
                all(status == "COMPLETED" for _, status in turns),
                report["foreign_owner_http_status"] == 404,
                report["new_installation_identity"] != owner,
                not any(remaining.values()),
                report["other_cart_rows_unchanged"],
                len(cart["items"]) == 1,
                cart["items"][0]["offer_id"] == arguments["expectedOffer"],
                cart["items"][0]["quantity"] == 2,
            )
        )
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        report["failure_type"] = type(error).__name__
        report["failure_message"] = (
            str(error)
            if isinstance(error, (RuntimeError, ValueError))
            else "Device or API operation failed; refer to the native receipt"
        )
    finally:
        if network_changed:
            restore_network()
        report["network_settings_restored"] = network_state() == (original_chain, original_package)
        report["accepted_runs_finished_within_window"] = await_accepted_run_completion(
            dsn, owner, started_at, deadline
        )
        with psycopg.connect(dsn) as connection:
            calls, tokens, all_ok = connection.execute(
                "SELECT COUNT(*),COALESCE(SUM(used_tokens),0),bool_and(status='http_200') FROM model_budget_calls WHERE session_id=%s AND scenario_id=%s",
                (manifest["budget_session"], slot),
            ).fetchone()
        report.update(
            paid_call_count=calls, token_usage=tokens, provider_cost="NOT_AVAILABLE_FROM_PROVIDER"
        )
        report["passed"] = bool(
            report["passed"]
            and (all_ok if calls else bool(resume_source))
            and (calls > 0 or bool(resume_source))
            and (not erasure_only or calls == 0)
            and report["network_settings_restored"]
            and report["accepted_runs_finished_within_window"]
        )
        budget.finish_scenario(slot, "passed" if report["passed"] else "failed")
        report["shared_budget"] = budget.summary()
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--device", default="127.0.0.1:5559")
    parser.add_argument("--adb-server-port", type=int, default=20884)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--retest-slot", choices=["A10-R1", "A10-R2", "A10-R3", "A10-R4", "A10-R5"])
    parser.add_argument("--resume-pending-from", choices=["A10-R2"])
    parser.add_argument("--resume-erasure-from", choices=["A10-R3"])
    args = parser.parse_args()
    if args.output.exists():
        parser.error("preserve previous reports")
    if bool(args.resume_pending_from) != (args.retest_slot == "A10-R3"):
        parser.error("A10-R3 only resumes the existing A10-R2 pending task; no new recommendation")
    if bool(args.resume_erasure_from) != (args.retest_slot == "A10-R4"):
        parser.error(
            "A10-R4 only inspects and erases the completed A10-R3 identity; no model calls"
        )
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_level": "NATIVE_ANDROID_REAL_API_PROVIDER",
        "scenario": run(args),
    }
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Native A10 passed={report['scenario']['passed']}")
    return 0 if report["scenario"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
