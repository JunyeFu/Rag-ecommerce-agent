"""Capture the file-level dirty tree before portfolio implementation, without secrets."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_NAMES = {".env", ".env.docker", "local.properties"}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def capture() -> dict[str, object]:
    entries = git("status", "--porcelain=v1", "-z", "--untracked-files=all").split(b"\0")
    records = []
    position = 0
    while position < len(entries) and entries[position]:
        entry = entries[position].decode("utf-8")
        status, relative = entry[:2], entry[3:]
        position += 1
        previous = None
        if "R" in status or "C" in status:
            previous = entries[position].decode("utf-8")
            position += 1
        path = ROOT / relative
        excluded = path.name in EXCLUDED_NAMES or path.suffix.lower() in {".jks", ".keystore"}
        content = path.read_bytes() if path.is_file() and not excluded else None
        records.append(
            {
                "path": relative,
                "status": status,
                "previous_path": previous,
                "size": len(content) if content is not None else None,
                "sha256": hashlib.sha256(content).hexdigest() if content is not None else None,
                "content_excluded": excluded,
                "ownership": "FINAL_self"
                if relative == "scripts/capture_portfolio_baseline.py"
                or relative.startswith("docs/task-packages/packages/V3-FINAL-")
                else "pre_existing",
            }
        )
    return {
        "schema_version": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "phase": "before_product_implementation",
        "branch": git("branch", "--show-current").decode().strip(),
        "head": git("rev-parse", "HEAD").decode().strip(),
        "dirty_count": len(records),
        "status_counts": dict(Counter(r["status"] for r in records)),
        "ignored_files_collected": False,
        "environment_collected": False,
        "files": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError("baseline output must be inside the repository")
    result = capture()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"baseline={output.relative_to(ROOT).as_posix()} dirty_files={result['dirty_count']}")


if __name__ == "__main__":
    main()
