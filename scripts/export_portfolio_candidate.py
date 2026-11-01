"""Export an explicit current-source inventory, never local secrets or build state."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    ".editorconfig",
    ".env.example",
    ".gitignore",
    ".node-version",
    ".nvmrc",
    ".python-version",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "package.json",
    "package-lock.json",
    "playwright.agent.config.ts",
    "playwright.config.ts",
    "pyproject.toml",
    "toolchain.versions.json",
    "uv.lock",
}
SOURCE_DIRS = {".github", "apps", "docs", "e2e", "evals", "infra", "packages", "scripts"}
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    ".gradle",
    ".kotlin",
    "node_modules",
    "build",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "output",
    "_archive",
    "_worktrees",
    ".state",
    "runtime",
    ".local",
}


def include(path: Path) -> bool:
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False
    if path.name.startswith(".env") and path.name != ".env.example":
        return False
    if path.name == "local.properties" or path.suffix in {
        ".jks",
        ".keystore",
        ".log",
        ".pid",
        ".pyc",
    }:
        return False
    return (
        path.as_posix() in ROOT_FILES
        or path.parts[0] in SOURCE_DIRS
        or path.parts[:2] in {("data", "demo"), ("data", "normalization")}
    )


def export(destination: Path) -> dict:
    destination = destination.resolve()
    if destination.exists() or destination.is_relative_to(ROOT):
        raise ValueError("Use a new independent directory outside the product checkout")
    inventory = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
        )
        .decode("utf-8")
        .split("\0")
    )
    files = []
    for value in sorted(set(inventory) - {""}):
        relative = Path(value)
        if not include(relative):
            continue
        source = ROOT / relative
        if source.is_symlink() or not source.resolve().is_relative_to(ROOT):
            raise ValueError(
                f"Source link cannot enter a portable candidate: {relative.as_posix()}"
            )
        if source.is_file():  # Tracked deletions stay deleted; user assets are not restored.
            files.append(relative)
    destination.mkdir(parents=True)
    rows = []
    for relative in files:
        source = ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        rows.append(
            {
                "path": relative.as_posix(),
                "size": target.stat().st_size,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
        )
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "kind": "preliminary_local_verification_candidate",
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "dirty_source": True,
        "files": rows,
        "file_count": len(rows),
        "credentials_copied": False,
        "build_outputs_copied": False,
        "LOCAL_PORTFOLIO_READY": "HOLD",
        "PUBLIC_RELEASE": "NOT_PERFORMED",
        "COMMERCIAL_RELEASE": "NO_GO",
    }
    (destination / "CANDIDATE-MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    manifest = export(args.destination)
    print(f"Exported {manifest['file_count']} explicit source files; readiness remains HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
