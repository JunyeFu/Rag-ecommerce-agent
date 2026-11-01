function Stop-OwnedDemoProcess {
    param([int]$ProcessId, [datetime]$StartedAt)
    $rootProcess = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $rootProcess -or $rootProcess.StartTime.ToUniversalTime() -ne $StartedAt.ToUniversalTime()) { return }
    $snapshot = @(Get-CimInstance Win32_Process)
    $owned = @($rootProcess)
    for ($index = 0; $index -lt $owned.Count; $index++) {
        $parent = $owned[$index]
        foreach ($child in $snapshot | Where-Object ParentProcessId -EQ $parent.Id) {
            $childProcess = Get-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
            if ($childProcess -and $childProcess.StartTime -ge $parent.StartTime) {
                $owned += $childProcess
            }
        }
    }
    [array]::Reverse($owned)
    foreach ($item in $owned) {
        $current = Get-Process -Id $item.Id -ErrorAction SilentlyContinue
        if ($current -and $current.StartTime -eq $item.StartTime) {
            Stop-Process -Id $item.Id -Force
        }
    }
}
