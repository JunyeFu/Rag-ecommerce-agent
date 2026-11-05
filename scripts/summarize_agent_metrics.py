"""Recompute public metrics from existing reports without starting services or models."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = Path("docs/evidence/v3")
OUTPUT = ROOT / "docs/evaluation/agent-metrics-20261105.json"


def read(path: str | Path) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def distribution(values: list[float]) -> dict:
    ordered = sorted(values)
    return {
        "samples": len(values),
        "mean_ms": round(mean(values), 6),
        "median_ms": round(median(values), 6),
        "p95_ms": round(ordered[math.ceil(len(values) * 0.95) - 1], 6),
        "max_ms": round(ordered[-1], 6),
    }


def model_suite(path: Path) -> dict:
    report = read(path)
    rows = report["scenarios"]
    qualified = [
        row["id"]
        for row in rows
        if row["parseable"]
        and row["tool_schema_valid"]
        and row["expected_flow_complete"]
        and row["expected_product_found"]
        and row["evidence_coverage"] == 1
        and not row["unauthorized_write_or_navigation"]
        and not row["fabricated_commercial_fact"]
        and row["failure_type"] is None
    ]
    return {
        "source": path.as_posix(),
        "created_at": report["created_at"],
        "model": report["provider"]["model"],
        "report_passed": report["passed"],
        "cases": len(rows),
        "reported_summary": report["summary"],
        "jointly_qualified_cases": len(qualified),
        "not_jointly_qualified_ids": [row["id"] for row in rows if row["id"] not in qualified],
        "latency": distribution([row["latency_ms"] for row in rows]),
        "reported_total_tokens": sum(row["usage"]["total_tokens"] for row in rows),
        "failures": {
            row["id"]: row["failure_type"] for row in rows if row["failure_type"] is not None
        },
    }


def scenario(path: Path) -> dict:
    report = read(path)
    row = report["scenario"]
    return {
        "source": path.as_posix(),
        "created_at": report.get("created_at"),
        **{
            key: row[key]
            for key in (
                "id",
                "slot",
                "passed",
                "failure_type",
                "parseable",
                "tool_schema_valid",
                "expected_flow_complete",
                "expected_product_found",
                "recommendations",
                "evidence_coverage",
                "unauthorized_write_or_navigation",
                "latency_ms",
                "token_usage",
                "paid_call_count",
                "usage",
                "user_api_workflow_checks",
            )
            if key in row
        },
    }


def capacity(path: Path) -> dict:
    report = read(path)
    rows = [row for batch in report["batches"] for row in batch["results"]]
    return {
        "source": path.as_posix(),
        "created_at": report["created_at"],
        "cases": len(rows),
        "completed": sum(row["snapshot_status"] == "COMPLETED" for row in rows),
        "one_completed_terminal": sum(row["terminal"] == ["completed"] for row in rows),
        "batches": len(report["batches"]),
        "batches_passed": sum(batch["passed"] for batch in report["batches"]),
        "reported_passed": report["passed"],
        "accept": distribution([row["accepted_ms"] for row in rows]),
        "first_state_after_202": distribution([row["first_state_ms"] for row in rows]),
        "worker_started_from_submission": distribution([row["worker_started_ms"] for row in rows]),
        "worst_batch_accept_p95_ms": max(
            batch["turn_accept_p95_ms"] for batch in report["batches"]
        ),
    }


def retrieval() -> dict:
    path = EVIDENCE / "final-N07-retrieval-20261013.json"
    report = read(path)
    groups = {}
    for split in ("development", "acceptance"):
        rows = [row for row in report["results"] if row["split"] == split]
        groups[split] = {}
        for variant in ("bm25", "bge_vector", "rrf_hybrid"):
            positive = [row["variants"][variant] for row in rows if row["positive_count"]]
            negative = [row["variants"][variant] for row in rows if not row["positive_count"]]
            groups[split][variant] = {
                "cases": len(rows),
                "positive_cases": len(positive),
                "no_match_cases": len(negative),
                "recall_at_10": mean(row["recall_at_10"] for row in positive),
                "ndcg_at_10": mean(row["ndcg_at_10"] for row in positive),
                "no_match_accuracy": mean(row["no_match_correct"] for row in negative),
                "hard_constraint_violations": sum(
                    row["variants"][variant]["hard_constraint_violations"] for row in rows
                ),
            }
    return {
        "source": path.as_posix(),
        "documents": report["documents"],
        "groups": groups,
        "all_three_variants_per_query_latency": distribution(
            [row["latency_ms"] for row in report["results"]]
        ),
        "limitations": report["limitations"],
    }


def build_report() -> dict:
    first = [
        scenario(path.relative_to(ROOT))
        for path in sorted((ROOT / EVIDENCE).glob("final-real-G*-first-20261009.json"))
    ]
    specialized = read(EVIDENCE / "career-close-specialized-20261008.json")
    native = {}
    for slot in (
        "A01-R1-20261009",
        "A03-R1-20261012",
        "A04-R1-20261012",
        "A05-first-20261009",
        "A06-R1-20261009",
        "A07-R1-20261009",
        "A08-R5-20261013",
        "A09-first-20261010",
        "A10-R5-20261013",
    ):
        row = scenario(EVIDENCE / f"final-real-{slot}.json")
        native[row["id"]] = row
    startup = {}
    for label, suffix in (
        ("unprepared", "cold-start"),
        ("prepared_verify", "verified-dex-cold-start"),
    ):
        path = EVIDENCE / f"final-NFR07-installed-{suffix}-20261013.json"
        report = read(path)
        startup[label] = {
            "source": path.as_posix(),
            "latency": distribution([row["total_time_ms"] for row in report["samples"]]),
            "fatal_count": report["fatal_count"],
            "strictmode_violation_count": report["strictmode_violation_count"],
        }
    f60 = read(EVIDENCE / "final-F60-review-20261024.json")
    recovery = read(EVIDENCE / "final-N07-worker-process-recovery-02-20261013.json")
    talkback = read(EVIDENCE / "android-talkback-20261024.json")
    return {
        "schema_version": 1,
        "aggregation_date": "2026-11-05",
        "inspected_source_commit": "0ed3910c79d21c5418d1111e4c92fd85b06533d1",
        "scope": "Offline reaggregation of existing reports; no new model, device or load runs",
        "percentiles": "p95 nearest rank ceil(n*0.95); median averages the two middle values for even n; failures retained",
        "real_planning_models_measured": ["mimo-v2.5"],
        "provider_cost": "NOT_AVAILABLE_FROM_PROVIDER",
        "historical_real_suites": [
            model_suite(path.relative_to(ROOT))
            for path in sorted((ROOT / EVIDENCE).glob("mimo-v2.5-real-evaluation-run-*.json"))
        ]
        + [model_suite(EVIDENCE / "career-close-golden-20261008.json")],
        "durable_golden_first": {
            "cases": len(first),
            "passed": sum(row["passed"] for row in first),
            "parseable": sum(row["parseable"] for row in first),
            "schema_valid": sum(row["tool_schema_valid"] for row in first),
            "expected_flows": sum(row["expected_flow_complete"] for row in first),
            "recommendations": sum(row["recommendations"] for row in first),
            "recommendation_runs_with_complete_evidence": sum(
                row["evidence_coverage"] == 1 for row in first
            ),
            "unauthorized_write_or_navigation": sum(
                row["unauthorized_write_or_navigation"] for row in first
            ),
            "latency": distribution([row["latency_ms"] for row in first]),
            "reported_total_tokens": sum(row["token_usage"] for row in first),
            "paid_call_count": sum(row["paid_call_count"] for row in first),
            "scenarios": first,
        },
        "durable_golden_retests": [
            scenario(path.relative_to(ROOT))
            for path in sorted((ROOT / EVIDENCE).glob("final-real-G*-R*-20261009.json"))
        ],
        "single_scenario_historical_retests": [
            scenario(path.relative_to(ROOT))
            for path in sorted((ROOT / EVIDENCE).glob("mimo-v2.5-real-evaluation-g*-retest-*.json"))
        ],
        "specialized": {
            "source": (EVIDENCE / "career-close-specialized-20261008.json").as_posix(),
            "summary": specialized["summary"],
            "scenarios": specialized["scenarios"],
        },
        "media_attempts": [
            scenario(path.relative_to(ROOT))
            for path in sorted((ROOT / EVIDENCE).glob("final-real-M*.json"))
        ],
        "native_scenario_coverage": {
            "selected_reports": native,
            "A02": "DEFERRED_ACTUAL_HUMAN_SPEECH",
            "M03": "DEFERRED_ACTUAL_HUMAN_SPEECH",
            "scope": "Coverage using named historical attempts, not a first-pass success rate; emulator, not physical device",
        },
        "retrieval": retrieval(),
        "capacity": {
            "previous_failure": capacity(
                EVIDENCE / "final-N07-durable-load-10-batches-20261013.json"
            ),
            "local_accepted": capacity(
                EVIDENCE / "f60-20261024/final-bge-r3-durable-10-batches.json"
            ),
            "runtime": f60["runtime"],
            "all_closeout_runs": f60["runs"],
            "worker_memory_before_bytes": f60["verified_contributors"][1][
                "observed_before_worker_bytes"
            ],
            "worker_memory_after_bytes": f60["verified_contributors"][1][
                "observed_after_worker_bytes"
            ],
        },
        "worker_recovery": {
            "source": (EVIDENCE / "final-N07-worker-process-recovery-02-20261013.json").as_posix(),
            "elapsed_seconds": recovery["elapsed_seconds"],
            "lease_seconds": recovery["lease_seconds"],
            "checks": recovery["checks"],
        },
        "android_debug_qa_startup": startup,
        "talkback_scoped": {
            "source": (EVIDENCE / "android-talkback-20261024.json").as_posix(),
            "passed": talkback["native_cases_passed"],
            "cases": talkback["native_cases_total"],
            "font_scales": talkback["android"]["font_scales"],
            "provider": "explicit fake",
            "api": "in-memory fixture over actual HTTP",
        },
        "excluded_contract_reference": {
            "source": "evals/v2/results/deterministic-reference-summary.json",
            "reason": "Constructed outcomes, preset latency and zero provider calls are not measured Agent quality or latency",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = build_report()
    content = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.check:
        if OUTPUT.read_text(encoding="utf-8") != content:
            print("Agent metrics differ; run python scripts/summarize_agent_metrics.py")
            return 1
        print("Agent metrics match existing source reports; no external calls")
    else:
        OUTPUT.write_text(content, encoding="utf-8")
        print(f"Wrote {OUTPUT.relative_to(ROOT).as_posix()}; no external calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
