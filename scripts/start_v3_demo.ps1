[CmdletBinding()]
param(
    [ValidateSet("fake", "mimo")][string]$ProviderMode = "fake",
    [ValidateSet("fixture", "local", "real")][string]$RetrievalMode = "local",
    [int]$ApiPort = 20881,
    [int]$OpsPort = 24174,
    [string]$ComposeProject = "ragcommerce_v3_demo",
    [string]$BudgetSession = "internship-final-20261009",
    [string]$DatabaseName = "ragcommerce",
    [int]$PostgresPort = 5433,
    [int]$QdrantPort = 6333,
    [int]$QdrantGrpcPort = 6334,
    [int]$RedisPort = 6379,
    [int]$MinioPort = 9000,
    [int]$MinioConsolePort = 9001
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "demo_processes.ps1")
$composePath = Join-Path $repoRoot "infra/compose.yaml"
$runtimeDir = Join-Path $repoRoot "output/v3-demo"
$python = Join-Path $repoRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Run scripts/bootstrap.ps1 -Quick first" }
foreach ($port in @($ApiPort, $OpsPort, $PostgresPort, $QdrantPort, $QdrantGrpcPort, $RedisPort, $MinioPort, $MinioConsolePort)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "Port $port is already listening; choose an explicitly registered free port"
    }
}
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$env:DATABASE_URL = "postgresql+psycopg://localdev@127.0.0.1:$PostgresPort/$DatabaseName"
$env:MINIO_ENDPOINT = "127.0.0.1:$MinioPort"
$env:MINIO_ACCESS_KEY = "localdev"
$env:MINIO_SECRET_KEY = "localdev-not-a-live-secret"
$env:POSTGRES_PORT = [string]$PostgresPort
$env:QDRANT_HTTP_PORT = [string]$QdrantPort
$env:QDRANT_GRPC_PORT = [string]$QdrantGrpcPort
$env:REDIS_PORT = [string]$RedisPort
$env:OBJECT_STORAGE_PORT = [string]$MinioPort
$env:OBJECT_STORAGE_CONSOLE_PORT = [string]$MinioConsolePort
$env:RETRIEVAL_MODE = $RetrievalMode
$env:QDRANT_URL = "http://127.0.0.1:$QdrantPort"
$env:RAG_API_URL = "http://127.0.0.1:$ApiPort"
$env:MODEL_PROVIDER_MODE = if ($ProviderMode -eq "fake") { "fake" } else { "openai_compatible" }
$env:MODEL_BUDGET_SESSION = $BudgetSession
if ($ProviderMode -eq "mimo") {
    if (-not $env:OPENAI_COMPATIBLE_API_KEY) {
        $env:OPENAI_COMPATIBLE_API_KEY = if ($env:MIMO_API_KEY) { $env:MIMO_API_KEY } else {
            [Environment]::GetEnvironmentVariable("MIMO_API_KEY", "User")
        }
    }
    if (-not $env:OPENAI_COMPATIBLE_API_KEY) { throw "MiMo key is unavailable in process/User environment" }
    $env:OPENAI_COMPATIBLE_BASE_URL = "https://api.xiaomimimo.com/v1"
    $env:OPENAI_COMPATIBLE_MODEL = "mimo-v2.5"
}
$pythonRoots = @(
    "apps/api/src", "apps/worker/src", "packages/domain/src", "packages/agent-runtime/src",
    "packages/connectors/src", "packages/retrieval/src", "packages/evaluation/src",
    "packages/contracts/generated/python"
) | ForEach-Object { Join-Path $repoRoot $_ }
$env:PYTHONPATH = $pythonRoots -join [IO.Path]::PathSeparator
$processes = @()
Push-Location -LiteralPath $repoRoot
try {
    docker compose -p $ComposeProject -f $composePath up -d --wait
    if ($LASTEXITCODE) { throw "Fixed-version infrastructure startup failed" }
    & $python scripts/ensure_demo_database.py
    if ($LASTEXITCODE) { throw "Explicit demo database preparation failed" }
    & $python -m alembic -c apps/api/alembic.ini upgrade head
    if ($LASTEXITCODE) { throw "Database migration failed" }
    & $python scripts/generate_demo_catalog.py --check
    if ($LASTEXITCODE) { throw "Demo catalog validation failed" }
    & $python scripts/seed_demo_ops.py
    if ($LASTEXITCODE) { throw "Owned demo Ops declaration failed" }
    if ($RetrievalMode -eq "local") {
        & $python scripts/prepare_local_embedding.py
        if ($LASTEXITCODE) { throw "Local embedding preparation failed" }
    }
    if ($RetrievalMode -ne "fixture") {
        & $python scripts/build_retrieval_index.py
        if ($LASTEXITCODE) { throw "Explicit retrieval index build failed" }
    }
    $launch = @{ FilePath = $python; WorkingDirectory = $repoRoot; WindowStyle = "Hidden"; PassThru = $true }
    $api = Start-Process @launch -ArgumentList @("-m", "uvicorn", "ragcommerce_api.persistent_demo:app", "--app-dir", "apps/api/src", "--host", "127.0.0.1", "--port", [string]$ApiPort) -RedirectStandardOutput (Join-Path $runtimeDir "api.stdout.log") -RedirectStandardError (Join-Path $runtimeDir "api.stderr.log")
    $processes += $api
    $workers = @(foreach ($number in 1..2) {
        Start-Process @launch -ArgumentList @("-m", "ragcommerce_worker.persistent_demo") -RedirectStandardOutput (Join-Path $runtimeDir "worker-$number.stdout.log") -RedirectStandardError (Join-Path $runtimeDir "worker-$number.stderr.log")
    })
    $processes += $workers
    $ops = Start-Process -FilePath (Get-Command node).Source -ArgumentList @((Join-Path $repoRoot "node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", [string]$OpsPort, "--strictPort") -WorkingDirectory (Join-Path $repoRoot "apps/ops-web") -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir "ops.stdout.log") -RedirectStandardError (Join-Path $runtimeDir "ops.stderr.log")
    $processes += $ops
    $owned = @($processes | ForEach-Object { @{ pid = $_.Id; started_at = $_.StartTime.ToUniversalTime().ToString("o") } })
    $runtimeSourceHashes = @{}
    foreach ($relativeSource in @(
        'apps/api/src/ragcommerce_api/provider_config.py', 'apps/api/src/ragcommerce_api/media_tools.py',
        'apps/api/src/ragcommerce_api/service.py', 'apps/api/src/ragcommerce_api/postgres_index.py',
        'apps/api/src/ragcommerce_api/postgres_demo.py', 'apps/worker/src/ragcommerce_worker/persistent_demo.py',
        'apps/api/src/ragcommerce_api/demo.py', 'apps/api/src/ragcommerce_api/quote_schema.py',
        'apps/api/src/ragcommerce_api/erasure.py', 'apps/api/migrations/versions/20261013_0015_demo_quotes.py',
        'packages/agent-runtime/src/ragcommerce_agent_runtime/model_provider.py',
        'packages/agent-runtime/src/ragcommerce_agent_runtime/runtime.py',
        'packages/agent-runtime/src/ragcommerce_agent_runtime/contracts.py',
        'packages/agent-runtime/src/ragcommerce_agent_runtime/tools.py',
        'packages/agent-runtime/src/ragcommerce_agent_runtime/store.py',
        'packages/agent-runtime/src/ragcommerce_agent_runtime/postgres_store.py',
        'packages/agent-runtime/src/ragcommerce_agent_runtime/token_budget.py',
        'packages/retrieval/src/ragcommerce_retrieval/semantic.py',
        'packages/contracts/openapi.json', 'data/demo/catalog.v3.jsonl'
    )) {
        $runtimeSourceHashes[$relativeSource] = (Get-FileHash -LiteralPath (Join-Path $repoRoot $relativeSource) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    @{ project = $ComposeProject; processes = $owned; api_port = $ApiPort; ops_port = $OpsPort; database = $DatabaseName; provider = $ProviderMode; retrieval = $RetrievalMode; runtime_source_hashes = $runtimeSourceHashes } | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $runtimeDir "processes.json")
    $healthy = $false
    foreach ($attempt in 1..60) {
        if ($api.HasExited -or ($workers | Where-Object HasExited)) { throw "API or Worker exited; inspect local runtime logs" }
        try {
            $response = Invoke-RestMethod -Uri "$env:RAG_API_URL/health" -TimeoutSec 2
            if ($response.status -eq "ok") { $healthy = $true; break }
        } catch [System.Net.Http.HttpRequestException] {
            Start-Sleep -Milliseconds 500
        } catch [System.Net.WebException] {
            Start-Sleep -Milliseconds 500
        } catch [System.Threading.Tasks.TaskCanceledException] {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $healthy) { throw "API health check failed" }
    Write-Host "Demo ready: $env:RAG_API_URL; Ops http://127.0.0.1:$OpsPort; provider=$ProviderMode; retrieval=$RetrievalMode"
    Write-Host "Android: http://10.0.2.2:$ApiPort/ ; stop: scripts/stop_v3_demo.ps1"
} catch {
    foreach ($process in $processes) {
        Stop-OwnedDemoProcess -ProcessId $process.Id -StartedAt $process.StartTime.ToUniversalTime().ToString("o")
    }
    docker compose -p $ComposeProject -f $composePath down
    throw
} finally { Pop-Location }
