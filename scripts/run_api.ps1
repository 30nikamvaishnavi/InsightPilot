param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
    $ownerIds = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    $ownerProcesses = @(
        foreach ($ownerId in $ownerIds) {
            $ownerProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$ownerId" -ErrorAction SilentlyContinue
            if ($ownerProcess) {
                $ownerProcess
            } else {
                [pscustomobject]@{
                    ProcessId = [int]$ownerId
                    Name = "unknown process"
                    CommandLine = ""
                }
            }
        }
    )
    $otherProcesses = @(
        $ownerProcesses | Where-Object {
            -not $_.CommandLine -or $_.CommandLine -notmatch "insightpilot\.api:app"
        }
    )

    if ($otherProcesses.Count -gt 0) {
        foreach ($process in $otherProcesses) {
            $processName = if ($process.Name) { $process.Name } else { "unknown process" }
            Write-Host "Port $Port is used by $processName (PID $($process.ProcessId)); it was not stopped."
        }
        Write-Host "Try another port, for example: .\scripts\run_api.ps1 -Port 8001"
        exit 1
    }

    $processIdsToStop = @()
    foreach ($ownerId in $ownerIds) {
        $currentId = [int]$ownerId
        while ($currentId -gt 0) {
            $process = Get-CimInstance Win32_Process -Filter "ProcessId=$currentId" -ErrorAction SilentlyContinue
            if (-not $process -or -not $process.CommandLine -or $process.CommandLine -notmatch "insightpilot\.api:app") {
                break
            }
            if ($processIdsToStop -notcontains [int]$process.ProcessId) {
                $processIdsToStop += [int]$process.ProcessId
            }
            $currentId = [int]$process.ParentProcessId
        }
    }

    $allProcesses = @(Get-CimInstance Win32_Process)
    $foundChild = $true
    while ($foundChild) {
        $foundChild = $false
        foreach ($process in $allProcesses) {
            if ($processIdsToStop -contains [int]$process.ParentProcessId -and
                $process.CommandLine -match "insightpilot\.api:app" -and
                $processIdsToStop -notcontains [int]$process.ProcessId) {
                $processIdsToStop += [int]$process.ProcessId
                $foundChild = $true
            }
        }
    }

    foreach ($processId in $ownerIds) {
        Write-Host "Project Uvicorn is using port $Port (PID $processId)."
    }
    $answer = Read-Host "Stop it and restart? (y/N)"
    if ($answer -notmatch "^(y|yes)$") {
        Write-Host "Existing server left running."
        exit 1
    }

    foreach ($processId in ($processIdsToStop | Sort-Object -Descending)) {
        Stop-Process -Id $processId -Force -ErrorAction Stop
    }
    Start-Sleep -Seconds 1

    $remainingListeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($remainingListeners.Count -gt 0) {
        foreach ($listener in $remainingListeners) {
            $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
            $processName = if ($process.Name) { $process.Name } else { "unknown process" }
            Write-Host "Port $Port remains in use by $processName (PID $($listener.OwningProcess)); no other process was stopped."
        }
        exit 1
    }
}

$activateScript = Join-Path $projectRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    . $activateScript
}

Write-Host "Open http://127.0.0.1:$Port/ in your browser."
python -m uvicorn insightpilot.api:app --host 127.0.0.1 --port $Port
