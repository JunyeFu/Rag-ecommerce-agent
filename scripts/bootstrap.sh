#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

for tool in uv node npm java; do
  command -v "$tool" >/dev/null || { echo "Required tool is unavailable: $tool" >&2; exit 1; }
done

uv sync --locked
npm ci
uv run python scripts/generate_contracts.py --check

if [[ "${1:-}" == "--quick" ]]; then
  uv run python scripts/verify_local.py --quick
else
  uv run python scripts/verify_local.py
fi
