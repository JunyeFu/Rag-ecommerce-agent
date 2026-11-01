[CmdletBinding()]
param(
    [switch]$Quick
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

foreach ($Tool in @("uv", "node", "npm")) {
    if (-not (Get-Command $Tool -ErrorAction SilentlyContinue)) {
        throw "Required tool is unavailable: $Tool"
    }
}

$Java = Get-Command java -ErrorAction SilentlyContinue
$JavaMajor = if ($Java) { ((& $Java.Source -version 2>&1 | Select-Object -First 1) -replace '.*version "(\d+).*', '$1') } else { "" }
if ($JavaMajor -ne "21") {
    throw "Required Java 21 is unavailable on PATH"
}
$env:JAVA_HOME = Split-Path -Parent (Split-Path -Parent $Java.Source)

uv sync --locked
if ($LASTEXITCODE) { exit $LASTEXITCODE }
npm ci
if ($LASTEXITCODE) { exit $LASTEXITCODE }
uv run python scripts/generate_contracts.py --check
if ($LASTEXITCODE) { exit $LASTEXITCODE }

if ($Quick) {
    uv run python scripts/verify_local.py --quick
} else {
    uv run python scripts/verify_local.py
}
if ($LASTEXITCODE) { exit $LASTEXITCODE }
