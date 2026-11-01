[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "demo_processes.ps1")
$recordPath = Join-Path $repoRoot "output/v3-demo/processes.json"
if (-not (Test-Path -LiteralPath $recordPath)) { throw "No owned demo process record" }
$record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
foreach ($owned in $record.processes) {
    Stop-OwnedDemoProcess -ProcessId $owned.pid -StartedAt $owned.started_at
}
docker compose -p $record.project -f (Join-Path $repoRoot "infra/compose.yaml") down
if ($LASTEXITCODE) { throw "Owned infrastructure stop failed" }
Remove-Item -LiteralPath $recordPath
Write-Host "Owned demo stopped; database/media volumes preserved"
