#!/usr/bin/env python3
"""Capture a read-only, file-level Git snapshot of the V1 source repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


def run_git(source: Path, *args: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(source), *args],
        check=True,
        capture_output=True,
        text=text,
    )
    return result.stdout


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_status(source: Path) -> list[dict[str, object]]:
    raw = run_git(
        source,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        text=False,
    )
    assert isinstance(raw, bytes)
    records = raw.split(b"\0")
    items: list[dict[str, object]] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        status = record[:2].decode("ascii", errors="replace")
        relative = record[3:].decode("utf-8", errors="surrogateescape").replace("\\", "/")
        original: str | None = None
        if ("R" in status or "C" in status) and index < len(records) and records[index]:
            original = records[index].decode("utf-8", errors="surrogateescape").replace("\\", "/")
            index += 1
        absolute = source / Path(relative)
        entry: dict[str, object] = {
            "path": relative,
            "status": status,
            "exists": absolute.exists(),
        }
        if original is not None:
            entry["original_path"] = original
        if absolute.is_file():
            entry["bytes"] = absolute.stat().st_size
            entry["sha256"] = sha256_file(absolute)
        else:
            entry["bytes"] = None
            entry["sha256"] = None
        items.append(entry)
    return sorted(items, key=lambda item: str(item["path"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    if not (source / ".git").exists():
        raise SystemExit(f"not a Git repository: {source}")

    files = parse_status(source)
    statuses = Counter(str(item["status"]) for item in files)
    upstream_raw = str(
        run_git(source, "rev-list", "--left-right", "--count", "origin/main...HEAD")
    ).strip()
    behind, ahead = (int(value) for value in upstream_raw.split())
    payload = {
        "schema_version": 1,
        "baseline_id": "RAG-COMMERCE-V2-BASELINE-20260826",
        "captured_at": datetime.now(UTC).isoformat(),
        "source_root_hint": source.as_posix(),
        "branch": str(run_git(source, "rev-parse", "--abbrev-ref", "HEAD")).strip(),
        "head": str(run_git(source, "rev-parse", "HEAD")).strip(),
        "upstream": {"ref": "origin/main", "behind": behind, "ahead": ahead},
        "dirty": {
            "file_level_items": len(files),
            "status_counts": dict(sorted(statuses.items())),
            "files": files,
        },
        "collection_policy": {
            "untracked_mode": "file_level",
            "ignored_files_collected": False,
            "environment_values_collected": False,
            "file_contents_collected": False,
            "hash_algorithm": "sha256",
        },
    }

    output = args.output
    if not output.is_absolute():
        output = Path.cwd() / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"source_baseline={output} branch={payload['branch']} head={payload['head']} "
        f"dirty_files={len(files)} behind={behind} ahead={ahead}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
