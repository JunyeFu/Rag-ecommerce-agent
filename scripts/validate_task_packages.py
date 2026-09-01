#!/usr/bin/env python3
"""Validate the versioned task package baseline with only the Python standard library."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, deque
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TASK_ROOT = ROOT / "docs" / "task-packages"
MANIFEST_PATH = TASK_ROOT / "manifest.json"
CONTROL_INDEX_PATH = TASK_ROOT / "control-index.json"
REQUIRED_HEADINGS = [
    "## 目标",
    "## 状态",
    "## 范围",
    "## 非目标",
    "## 前置依赖",
    "## 路径所有权",
    "## 现状证据",
    "## 执行步骤",
    "## 数据引用",
    "## 验收",
    "## 回滚",
    "## 停止条件",
    "## 交接格式",
]
PACKAGE_ID = re.compile(r"^V[23]-[A-Z]+(?:-[A-Z]+)*-[0-9]{2}$")
SUSPICIOUS_VALUE = re.compile(
    r"(?i)(?:api[_-]?key|client[_-]?secret|access[_-]?token|password)\s*[:=]\s*[\"']?[A-Za-z0-9_./+=-]{16,}"
)
SCAN_EXCLUDED_PARTS = {".git", ".venv", "node_modules", ".gradle", "build", "dist"}
ALLOWED_STATUS = {"planned", "in_progress", "blocked", "complete"}
ALLOWED_PRIORITY = {"P0", "P1", "P2"}
ALLOWED_AUTONOMY = {"full", "conditional", "human_gate"}
ALLOWED_VERIFICATION_STATUS = {"not_run", "passed", "failed", "blocked"}
REQUIRED_DATA_FIELDS = {
    "schema_version",
    "package_id",
    "owner",
    "objective",
    "inputs",
    "outputs",
    "acceptance",
    "test_profiles",
    "business_refs",
    "development_refs",
    "risk_refs",
}
CONTROL_LEVELS = ("large", "medium", "small")
CONFIRMATION_STATUS = {"pending", "awaiting_user", "confirmed", "revise", "deferred"}


def load_json(path: Path, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"invalid JSON {path.relative_to(ROOT).as_posix()}: {exc}")
        return None


def is_safe_relative(value: str) -> bool:
    path = PurePosixPath(value.replace("\\", "/"))
    return (
        bool(value)
        and not path.is_absolute()
        and not re.match(r"^[A-Za-z]:", value)
        and ".." not in path.parts
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_dag(packages: list[dict[str, Any]], errors: list[str]) -> None:
    ids = {package["id"] for package in packages if isinstance(package.get("id"), str)}
    graph: dict[str, list[str]] = {package_id: [] for package_id in ids}
    indegree = Counter({package_id: 0 for package_id in ids})
    for package in packages:
        package_id = package.get("id")
        if package_id not in ids:
            continue
        for dependency in package.get("dependencies", []):
            if dependency not in ids:
                errors.append(f"{package_id}: unknown dependency {dependency}")
                continue
            graph[dependency].append(package_id)
            indegree[package_id] += 1
    queue = deque(sorted(package_id for package_id, count in indegree.items() if count == 0))
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for dependent in graph[current]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)
    if visited != len(ids):
        errors.append("manifest dependency graph contains a cycle")


def validate_source_hashes(errors: list[str], warnings: list[str]) -> None:
    business = load_json(TASK_ROOT / "shared" / "business-data.json", errors)
    if not isinstance(business, dict):
        return
    source = business.get("source_repo", {})
    source_root = Path(str(source.get("root_hint", "")))
    if not source_root.exists():
        warnings.append(
            f"source repository unavailable; skipped seed hash verification: {source_root}"
        )
        return
    for key in ("products", "evaluation", "ui_tokens"):
        record = source.get(key, {})
        relative = record.get("path")
        expected = record.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            errors.append(f"business-data source_repo.{key} lacks path/sha256")
            continue
        candidate = source_root / relative
        if not candidate.is_file():
            errors.append(f"source seed missing: {candidate}")
            continue
        actual = sha256_file(candidate)
        if actual.lower() != expected.lower():
            errors.append(f"source seed hash drift: {key} expected={expected} actual={actual}")


def validate_control_index(package_ids: set[str], errors: list[str]) -> None:
    control = load_json(CONTROL_INDEX_PATH, errors)
    if not isinstance(control, dict):
        return
    if control.get("schema_version") != 1:
        errors.append("control-index schema_version must equal 1")
    if control.get("control_model") != "large_medium_small":
        errors.append("control-index control_model must equal large_medium_small")
    nodes: dict[str, tuple[str, dict[str, Any]]] = {}
    for level in CONTROL_LEVELS:
        values = control.get(level)
        if not isinstance(values, list) or not values:
            errors.append(f"control-index {level} must be a non-empty list")
            continue
        for node in values:
            if not isinstance(node, dict) or not isinstance(node.get("id"), str):
                errors.append(f"control-index {level} contains an invalid node")
                continue
            node_id = node["id"]
            if node_id in nodes:
                errors.append(f"control-index duplicate node {node_id}")
            nodes[node_id] = (level, node)
            if node_id not in package_ids:
                errors.append(f"control-index node is missing from manifest: {node_id}")
    for node_id, (level, node) in nodes.items():
        if level == "large":
            if node.get("parent_id") is not None:
                errors.append(f"{node_id}: large node cannot have parent_id")
        else:
            parent_id = node.get("parent_id")
            expected_level = "large" if level == "medium" else "medium"
            if parent_id not in nodes or nodes[parent_id][0] != expected_level:
                errors.append(f"{node_id}: invalid {expected_level} parent {parent_id!r}")
            elif node_id not in nodes[parent_id][1].get("children", []):
                errors.append(f"{node_id}: parent does not list child")
        for child_id in node.get("children", []):
            if child_id not in nodes or nodes[child_id][1].get("parent_id") != node_id:
                errors.append(f"{node_id}: invalid child relationship {child_id!r}")
    small = control.get("small", [])
    orders: list[int] = []
    awaiting = 0
    for node in small if isinstance(small, list) else []:
        if not isinstance(node, dict):
            continue
        order = node.get("confirmation_order")
        if not isinstance(order, int) or order < 1:
            errors.append(f"{node.get('id')}: invalid confirmation_order")
        else:
            orders.append(order)
        status = node.get("confirmation_status")
        if status not in CONFIRMATION_STATUS:
            errors.append(f"{node.get('id')}: invalid confirmation_status {status!r}")
        awaiting += status == "awaiting_user"
        prompt = node.get("preview_prompt")
        if not isinstance(prompt, str) or not is_safe_relative(prompt):
            errors.append(f"{node.get('id')}: unsafe preview_prompt {prompt!r}")
        elif not (ROOT / prompt).is_file():
            errors.append(f"{node.get('id')}: missing preview prompt {prompt}")
    if sorted(orders) != list(range(1, len(orders) + 1)):
        errors.append("control-index confirmation_order must be contiguous from 1")
    if awaiting > 1:
        errors.append("control-index allows at most one awaiting_user item")
    policy = control.get("confirmation_policy")
    if not isinstance(policy, dict) or policy.get("mode") != "one_at_a_time":
        errors.append("control-index confirmation_policy.mode must equal one_at_a_time")
    else:
        current_package = policy.get("current_package")
        small_ids = {node.get("id") for node in small}
        if current_package is None:
            if awaiting:
                errors.append(
                    "control-index current_package is required while confirmation is awaiting_user"
                )
        elif current_package not in small_ids:
            errors.append("control-index current_package must reference a small package")


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    for schema in TASK_ROOT.glob("schemas/*.json"):
        load_json(schema, errors)
    manifest = load_json(MANIFEST_PATH, errors)
    if not isinstance(manifest, dict):
        print("task_packages=invalid errors=" + str(len(errors)))
        for error in errors:
            print("ERROR", error)
        return 1

    if manifest.get("schema_version") != 1:
        errors.append("manifest schema_version must equal 1")
    if not isinstance(manifest.get("baseline_id"), str) or not manifest["baseline_id"]:
        errors.append("manifest baseline_id must be a non-empty string")
    if not isinstance(manifest.get("authority"), str) or not manifest["authority"]:
        errors.append("manifest authority must be a non-empty string")

    packages = manifest.get("packages")
    if not isinstance(packages, list) or not packages:
        errors.append("manifest packages must be a non-empty list")
        packages = []

    ids: list[str] = []
    for package in packages:
        if not isinstance(package, dict):
            errors.append("manifest package entry is not an object")
            continue
        package_id = package.get("id")
        if not isinstance(package_id, str) or not PACKAGE_ID.fullmatch(package_id):
            errors.append(f"invalid package id: {package_id!r}")
            continue
        ids.append(package_id)
        if package.get("status") not in ALLOWED_STATUS:
            errors.append(f"{package_id}: invalid status {package.get('status')!r}")
        if package.get("priority") not in ALLOWED_PRIORITY:
            errors.append(f"{package_id}: invalid priority {package.get('priority')!r}")
        if package.get("autonomy") not in ALLOWED_AUTONOMY:
            errors.append(f"{package_id}: invalid autonomy {package.get('autonomy')!r}")
        if not isinstance(package.get("title"), str) or not package["title"]:
            errors.append(f"{package_id}: title must be a non-empty string")
        if not isinstance(package.get("dependencies"), list):
            errors.append(f"{package_id}: dependencies must be a list")
        if not isinstance(package.get("evidence"), list) or not package["evidence"]:
            errors.append(f"{package_id}: evidence must be a non-empty list")
        if not isinstance(package.get("external_gates"), list):
            errors.append(f"{package_id}: external_gates must be a list")
        package_path = package.get("path")
        if not isinstance(package_path, str) or not is_safe_relative(package_path):
            errors.append(f"{package_id}: unsafe package path {package_path!r}")
            continue
        directory = ROOT / package_path
        for name in ("TASK.md", "data.json", "pitfalls.md", "evidence/verification.json"):
            if not (directory / name).is_file():
                errors.append(f"{package_id}: missing {package_path}/{name}")
        task_path = directory / "TASK.md"
        if task_path.is_file():
            text = task_path.read_text(encoding="utf-8")
            for heading in REQUIRED_HEADINGS:
                if heading not in text:
                    errors.append(f"{package_id}: TASK.md missing heading {heading}")
        data = (
            load_json(directory / "data.json", errors)
            if (directory / "data.json").is_file()
            else None
        )
        if isinstance(data, dict):
            missing_data_fields = sorted(REQUIRED_DATA_FIELDS - set(data))
            if missing_data_fields:
                errors.append(f"{package_id}: data.json missing fields {missing_data_fields}")
            if data.get("schema_version") != 1:
                errors.append(f"{package_id}: data.json schema_version must equal 1")
            if data.get("package_id") != package_id:
                errors.append(f"{package_id}: data.json package_id mismatch")
            for field in (
                "inputs",
                "outputs",
                "acceptance",
                "test_profiles",
                "business_refs",
                "development_refs",
                "risk_refs",
            ):
                if not isinstance(data.get(field), list):
                    errors.append(f"{package_id}: data.json {field} must be a list")
        evidence = (
            load_json(directory / "evidence" / "verification.json", errors)
            if (directory / "evidence" / "verification.json").is_file()
            else None
        )
        if isinstance(evidence, dict):
            if evidence.get("package_id") != package_id:
                errors.append(f"{package_id}: verification package_id mismatch")
            verification_status = evidence.get("status")
            if verification_status not in ALLOWED_VERIFICATION_STATUS:
                errors.append(f"{package_id}: invalid verification status {verification_status!r}")
            if package.get("status") == "complete" and verification_status != "passed":
                errors.append(
                    f"{package_id}: complete manifest status requires passed verification"
                )
            if verification_status == "passed" and package.get("status") != "complete":
                errors.append(
                    f"{package_id}: passed verification requires complete manifest status"
                )
            if evidence.get("external_gates") != package.get("external_gates"):
                errors.append(f"{package_id}: verification external_gates drift from manifest")
            if not isinstance(evidence.get("checks"), list):
                errors.append(f"{package_id}: verification checks must be a list")
        for value in package.get("evidence", []):
            if not isinstance(value, str) or not is_safe_relative(value):
                errors.append(f"{package_id}: unsafe evidence path {value!r}")
            elif not (ROOT / value).is_file():
                errors.append(f"{package_id}: missing manifest evidence {value}")

    duplicates = [package_id for package_id, count in Counter(ids).items() if count > 1]
    if duplicates:
        errors.append("duplicate package ids: " + ", ".join(sorted(duplicates)))
    validate_dag(packages, errors)
    validate_control_index(set(ids), errors)

    source_baseline = manifest.get("source_baseline")
    if not isinstance(source_baseline, str) or not is_safe_relative(source_baseline):
        errors.append("manifest source_baseline must be a safe relative path")
    elif not (ROOT / source_baseline).is_file():
        errors.append(f"source baseline missing: {source_baseline}")

    validate_source_hashes(errors, warnings)

    scan_suffixes = {".md", ".json", ".py"}
    for path in ROOT.rglob("*"):
        if (
            path.is_file()
            and path.suffix.lower() in scan_suffixes
            and not SCAN_EXCLUDED_PARTS.intersection(path.relative_to(ROOT).parts)
        ):
            text = path.read_text(encoding="utf-8", errors="replace")
            if SUSPICIOUS_VALUE.search(text):
                errors.append(
                    f"suspected credential-like value: {path.relative_to(ROOT).as_posix()}"
                )

    print(f"packages={len(packages)} errors={len(errors)} warnings={len(warnings)}")
    for warning in warnings:
        print("WARNING", warning)
    for error in errors:
        print("ERROR", error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
