"""One frozen media slot through MinIO/API/Worker and the same paid ledger."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import httpx
import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_final_acceptance import PostgresTokenBudget, ThreadSnapshot, consume  # noqa: E402


async def run(case, media_path, dsn, base_url, manifest, slot, phase, root_cause):
    launch = json.loads((ROOT / "output/v3-demo/processes.json").read_text(encoding="utf-8"))
    if launch["provider"] != "mimo" or launch["retrieval"] != "local":
        raise RuntimeError("media real acceptance requires explicit mimo/local running profile")
    owner = uuid4()
    headers = {"X-User-ID": str(owner)}
    budget = PostgresTokenBudget(dsn, manifest["budget_session"], require_scenario=True)
    budget.start_scenario(slot, owner, "media", phase, root_cause)
    start = perf_counter()
    report = {
        "id": case["id"],
        "slot": slot,
        "root_cause": root_cause,
        "runtime_source_hashes": launch.get("runtime_source_hashes"),
        "passed": False,
        "failure_type": None,
        "input_sha256": hashlib.sha256(media_path.read_bytes()).hexdigest(),
        "input_name": media_path.name,
        "run_ids": [],
    }
    text = "我要相机, 不要手机, 预算3000元" if case["id"] == "M04" else "请根据附件帮助我挑选3C产品"
    try:
        async with httpx.AsyncClient(
            base_url=base_url, timeout=manifest["observation_seconds"]
        ) as client:
            uploaded = await client.post(
                "/v1/media",
                headers={
                    **headers,
                    "Content-Type": "audio/wav" if case["id"] == "M03" else "image/png",
                },
                content=media_path.read_bytes(),
            )
            uploaded.raise_for_status()
            media_id = uploaded.json()["media_id"]
            thread = await client.post("/v1/threads", headers=headers, json={"goal": text})
            thread.raise_for_status()
            thread_id = thread.json()["thread_id"]
            accepted = await client.post(
                f"/v1/threads/{thread_id}/turns",
                headers={**headers, "Idempotency-Key": str(uuid4())},
                json={"text": text, "media_ids": [media_id]},
            )
            accepted.raise_for_status()
            source_run = accepted.json()["run_id"]
            report["run_ids"].append(source_run)
            async with asyncio.timeout(manifest["observation_seconds"]):
                await consume(client, f"/v1/agent-runs/{source_run}/events", headers)
            response = await client.get(f"/v1/threads/{thread_id}", headers=headers)
            response.raise_for_status()
            pending = ThreadSnapshot.model_validate(response.json())
            with psycopg.connect(dsn) as connection:
                started = connection.execute(
                    "SELECT data->>'tool' FROM agent_events WHERE run_id=%s AND event_type='tool_started' ORDER BY event_id",
                    (source_run,),
                ).fetchall()
                model = connection.execute(
                    "SELECT model_version FROM agent_runs WHERE id=%s", (source_run,)
                ).fetchone()[0]
                failures = connection.execute(
                    "SELECT data FROM agent_events WHERE run_id=%s AND event_type IN ('failed','tool_failed') ORDER BY event_id",
                    (source_run,),
                ).fetchall()
            if failures:
                report["failure_type"] = failures[-1][0].get(
                    "summary", failures[-1][0].get("error_type")
                )
                report["schema_diagnostics"] = [
                    item[0]["error_summary"] for item in failures if "error_summary" in item[0]
                ]
            interpreted = pending.pending_media_interpretations
            checks = {
                "explicit_real_model": model == manifest["provider"],
                "waits_for_confirmation": pending.status == "WAITING_CLARIFICATION"
                and len(interpreted) == 1,
                "no_early_retrieval_or_write": started
                == [("audio.transcribe" if case["id"] == "M03" else "vision.identify",)]
                and not pending.candidates,
                "original_goal_preserved": pending.goal == text,
            }
            if interpreted:
                value = interpreted[0]
                report["interpretation"] = value.model_dump(mode="json")
                if case["id"] == "M02":
                    checks["unsupported_explained"] = not value.supported and bool(
                        value.uncertainties
                    )
                elif case["id"] == "M03":
                    checks["intelligible_voice_transcribed"] = value.supported and bool(
                        value.recognized_text.strip()
                    )
                else:
                    checks["visible_phone_not_commercial_fact"] = (
                        value.supported and value.category == "手机"
                    )
                if case["id"] in {"M01", "M04"}:
                    confirmed_text = (
                        "我选择手机, 预算2000元, 日常通勤"
                        if case["id"] == "M01"
                        else "我确认按文字选择相机, 不要手机, 预算3000元"
                    )
                    confirmation = {
                        "text": "",
                        "media_ids": [],
                        "expected_mission_version": pending.mission.version,
                        "media_confirmation": {"source_run_id": source_run, "text": confirmed_text},
                    }
                    confirmation_headers = {**headers, "Idempotency-Key": str(uuid4())}
                    confirmed = await client.post(
                        f"/v1/threads/{thread_id}/turns",
                        headers=confirmation_headers,
                        json=confirmation,
                    )
                    confirmed.raise_for_status()
                    confirmed_run = confirmed.json()["run_id"]
                    report["run_ids"].append(confirmed_run)
                    await consume(client, f"/v1/agent-runs/{confirmed_run}/events", headers)
                    repeated = await client.post(
                        f"/v1/threads/{thread_id}/turns",
                        headers=confirmation_headers,
                        json=confirmation,
                    )
                    repeated.raise_for_status()
                    response = await client.get(f"/v1/threads/{thread_id}", headers=headers)
                    response.raise_for_status()
                    after = ThreadSnapshot.model_validate(response.json())
                    checks["confirmation_idempotent"] = (
                        repeated.json()["run_id"] == confirmed_run and repeated.json()["replayed"]
                    )
                    checks["user_choice_updates_mission"] = (
                        after.goal == confirmed_text
                        and after.mission.version == pending.mission.version + 1
                    )
                    checks["confirmed_retrieval_completed"] = (
                        after.status == "COMPLETED"
                        and bool(after.candidates)
                        and all(item.evidence_refs for item in after.candidates)
                    )
                    if case["id"] == "M04":
                        checks["text_choice_not_overwritten_by_image"] = all(
                            "相机" in item.title for item in after.candidates
                        )
            report.update(checks=checks, passed=all(checks.values()))
    except (httpx.HTTPError, TimeoutError, ValueError) as error:
        report["failure_type"] = type(error).__name__
    finally:
        budget.finish_scenario(slot, "passed" if report["passed"] else "failed")
    with psycopg.connect(dsn) as connection:
        usage = connection.execute(
            "SELECT count(*),coalesce(sum(used_tokens),0),bool_and(status='http_200') FROM model_budget_calls WHERE session_id=%s AND scenario_id=%s",
            (manifest["budget_session"], slot),
        ).fetchone()
    report.update(
        paid_call_count=usage[0],
        token_usage=usage[1],
        all_calls_successful=usage[2],
        latency_ms=round((perf_counter() - start) * 1000, 3),
        shared_budget=budget.summary(),
        provider_cost="NOT_AVAILABLE_FROM_PROVIDER",
    )
    report["passed"] = report["passed"] and usage[0] > 0 and usage[2]
    return report


def validate_native_audio_capture(report_path: Path, media_path: Path) -> dict:
    import wave

    source = json.loads(report_path.read_text(encoding="utf-8"))["scenario"]
    if (
        source["id"] != "A02"
        or not source["native_activity"]
        or source["injected_ui_state"]
        or source.get("native_audio_origin")
        != "MainActivity AudioRecord cache copied before send; no imported audio"
    ):
        raise ValueError("M03 requires an observed MainActivity AudioRecord capture")
    digest = hashlib.sha256(media_path.read_bytes()).hexdigest()
    if source["native_audio_sha256"] != digest or not any(
        item["kind"] == "audio" and item["sha256"] == digest for item in source["native_media"]
    ):
        raise ValueError("M03 input must match the recorded native bytes and uploaded media")
    with wave.open(str(media_path)) as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (
            16000,
            1,
            2,
        ) or not 5 <= audio.getnframes() / 16000 <= 60:
            raise ValueError("M03 requires 5-60 seconds of native 16 kHz mono PCM WAV")
    return {
        "device": source["device"],
        "source_case": "A02",
        "capture_sha256": digest,
        "capture_report": report_path.name,
        "origin": source["native_audio_origin"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True, choices=["M01", "M02", "M03", "M04"])
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:20881")
    parser.add_argument("--retest-slot")
    parser.add_argument("--root-cause")
    parser.add_argument("--native-capture-report", type=Path)
    args = parser.parse_args()
    if args.output.exists() or not args.input.is_file():
        parser.error("new output and an existing actual media file required")
    if args.retest_slot and (
        not args.retest_slot.startswith(args.case + "-R")
        or not args.root_cause
        or not (ROOT / args.root_cause.split("#", 1)[0]).is_file()
    ):
        parser.error("retest needs an explicit case-R slot and corrected root-cause document")
    native_capture = None
    if args.case == "M03":
        if args.native_capture_report is None:
            parser.error(
                "M03 requires --native-capture-report from the observed A02 AudioRecord run"
            )
        native_capture = validate_native_audio_capture(args.native_capture_report, args.input)
    manifest = json.loads((ROOT / "evals/v3/final-scenarios.json").read_text(encoding="utf-8"))
    case = next(item for item in manifest["media"] if item["id"] == args.case)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_level": "REAL_MIMO_MEDIA_DURABLE_API",
        "scope": "Self-authored illustration and public API; not native gallery/recording E2E or photo robustness",
        "native_capture": native_capture,
        "scenario": asyncio.run(
            run(
                case,
                args.input,
                os.environ["DATABASE_URL"],
                args.base_url,
                manifest,
                args.retest_slot or args.case,
                "retest" if args.retest_slot else "first",
                args.root_cause,
            )
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"case={args.case} passed={report['scenario']['passed']} no automatic retry")
    return 0 if report["scenario"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
