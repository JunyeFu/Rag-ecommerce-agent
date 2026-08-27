[CmdletBinding()]
param(
    [switch]$Quick
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

foreach ($Tool in @("uv", "node", "npm", "java")) {
    if (-not (Get-Command $Tool -ErrorAction SilentlyContinue)) {
        throw "Required tool is unavailable: $Tool"
    }
}

uv sync --locked
npm ci
uv run python scripts/generate_contracts.py --check

if ($Quick) {
    uv run python scripts/verify_local.py --quick
} else {
    uv run python scripts/verify_local.py
}
