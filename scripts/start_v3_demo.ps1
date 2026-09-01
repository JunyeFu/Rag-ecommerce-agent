[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$composePath = Join-Path $repoRoot "infra/compose.yaml"
$runtimeDir = Join-Path $repoRoot "output/v3-demo"
$venvScripts = Join-Path $repoRoot ".venv/Scripts"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

$env:DATABASE_URL = "postgresql+psycopg://localdev@127.0.0.1:5433/ragcommerce"
$env:MINIO_ENDPOINT = "127.0.0.1:9000"
$env:MINIO_ACCESS_KEY = "localdev"
$env:MINIO_SECRET_KEY = "localdev-not-a-live-secret"
$pythonRoots = @(
    "apps/api/src", "apps/worker/src", "packages/domain/src", "packages/agent-runtime/src",
    "packages/connectors/src", "packages/retrieval/src", "packages/evaluation/src",
    "packages/contracts/generated/python"
) | ForEach-Object { Join-Path $repoRoot $_ }
$env:PYTHONPATH = ($pythonRoots -join [IO.Path]::PathSeparator)

docker compose -p ragcommerce_v3_demo -f $composePath up -d --wait
if ($LASTEXITCODE -ne 0) { throw "infrastructure startup failed" }

Push-Location $repoRoot
$processes = @()
try {
    uv run alembic -c apps/api/alembic.ini upgrade head
    if ($LASTEXITCODE -ne 0) { throw "database migration failed" }
    uv run python scripts/generate_demo_catalog.py --check
    if ($LASTEXITCODE -ne 0) { throw "demo catalog validation failed" }

    $api = Start-Process -FilePath (Join-Path $venvScripts "uvicorn.exe") -ArgumentList @(
        "ragcommerce_api.persistent_demo:app", "--app-dir", "apps/api/src",
        "--host", "127.0.0.1", "--port", "8080"
    ) -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru
    $processes += $api
    $worker = Start-Process -FilePath (Join-Path $venvScripts "python.exe") -ArgumentList @(
        "-m", "ragcommerce_worker.persistent_demo"
    ) -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru
    $processes += $worker
    $ops = Start-Process -FilePath (Get-Command node -ErrorAction Stop).Source -ArgumentList @(
        (Join-Path $repoRoot "node_modules/vite/bin/vite.js"), "--host", "127.0.0.1",
        "--port", "24174"
    ) -WorkingDirectory (Join-Path $repoRoot "apps/ops-web") -WindowStyle Hidden -PassThru
    $processes += $ops

    [ordered]@{ api = $api.Id; worker = $worker.Id; ops = $ops.Id } |
        ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $runtimeDir "processes.json")

    $healthy = $false
    foreach ($attempt in 1..40) {
        try {
            $response = Invoke-RestMethod -Uri "http://127.0.0.1:8080/health" -TimeoutSec 2
            if ($response.status -eq "ok") { $healthy = $true; break }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $healthy) { throw "API health check failed" }
    Write-Host "V3 demo ready: API http://127.0.0.1:8080, Ops http://127.0.0.1:24174"
    Write-Host "Android debug uses http://10.0.2.2:8080/"
} catch {
    foreach ($process in $processes) {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    }
    docker compose -p ragcommerce_v3_demo -f $composePath down
    throw
} finally {
    Pop-Location
}
