#!/usr/bin/env python3
"""Reduce AndroidX Macrobenchmark output to a small task-package evidence file."""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--threshold-ms", type=float, default=2000.0)
    args = parser.parse_args()

    raw = json.loads(args.input.read_text(encoding="utf-8"))
    benchmark = next(item for item in raw["benchmarks"] if item["name"] == "coldStartup")
    metric = benchmark["metrics"]["timeToInitialDisplayMs"]
    runs = sorted(float(value) for value in metric["runs"])
    if not runs:
        raise RuntimeError("Macrobenchmark did not emit startup metric runs")
    rank = max(1, math.ceil(0.95 * len(runs)))
    p95 = runs[rank - 1]
    result = {
        "schema_version": 1,
        "verified_at": datetime.now(UTC).isoformat(),
        "source": "AndroidX Macrobenchmark StartupTimingMetric",
        "evidence_level": "emulator_regression_only",
        "device": {
            "model": raw["context"]["build"]["model"],
            "sdk": raw["context"]["build"]["version"]["sdk"],
            "cpu_locked": raw["context"]["cpuLocked"],
        },
        "compilation_mode": raw["context"]["compilationMode"],
        "configured_iterations": benchmark["repeatIterations"],
        "measured_run_count": len(runs),
        "time_to_initial_display_ms": {
            "minimum": metric["minimum"],
            "median": metric["median"],
            "maximum": metric["maximum"],
            "p95_nearest_rank": p95,
            "threshold": args.threshold_ms,
            "passed": p95 <= args.threshold_ms,
        },
        "limitations": [
            "EMULATOR was explicitly suppressed so this is a local regression gate, not physical-device evidence.",
            "CPU frequency was not locked.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if result["time_to_initial_display_ms"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
