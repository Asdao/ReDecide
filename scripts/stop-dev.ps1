[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = "Stop"
$devLogRoot = Join-Path $env:TEMP "GHackathon-dev"
$devStatePath = Join-Path $devLogRoot "services.json"

function Get-ListeningProcessIds([int]$Port) {
    try {
        return @(
            Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
                Select-Object -ExpandProperty OwningProcess -Unique
        )
    }
    catch {
        return @()
    }
}

function Get-ProcessTreeIds([int[]]$RootIds) {
    $ids = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($rootId in $RootIds) {
        [void]$ids.Add($rootId)
    }

    try {
        $processes = @(Get-CimInstance Win32_Process -ErrorAction Stop)
        $added = $true
        while ($added) {
            $added = $false
            foreach ($process in $processes) {
                if ($ids.Contains([int]$process.ParentProcessId) -and $ids.Add([int]$process.ProcessId)) {
                    $added = $true
                }
            }
        }

        $allowedAncestors = @("cmd.exe", "node.exe", "npm.exe", "pnpm.exe", "python.exe", "uv.exe")
        $added = $true
        while ($added) {
            $added = $false
            foreach ($process in $processes) {
                if ($ids.Contains([int]$process.ProcessId)) {
                    $parent = $processes | Where-Object { [int]$_.ProcessId -eq [int]$process.ParentProcessId } | Select-Object -First 1
                    if ($null -ne $parent -and $allowedAncestors -contains $parent.Name -and $ids.Add([int]$parent.ProcessId)) {
                        $added = $true
                    }
                }
            }
        }
    }
    catch {
        Write-Warning "Could not inspect the full process tree; stopping the known service process IDs only."
    }

    return @($ids)
}

function Test-Backend {
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 2
        return $response.status -eq "ok"
    }
    catch {
        return $false
    }
}

function Test-Frontend {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:3000" -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -ge 200 -and
            $response.StatusCode -lt 500 -and
            $response.Content -match "RE:DECIDE"
    }
    catch {
        return $false
    }
}

$targets = [System.Collections.Generic.HashSet[int]]::new()

if (Test-Backend) {
    foreach ($processId in Get-ListeningProcessIds 8000) {
        [void]$targets.Add([int]$processId)
    }
}
elseif (Get-ListeningProcessIds 8000) {
    Write-Warning "Port 8000 is occupied, but it is not the RE:DECIDE backend; leaving it running."
}

if (Test-Frontend) {
    foreach ($processId in Get-ListeningProcessIds 3000) {
        [void]$targets.Add([int]$processId)
    }
}
elseif (Get-ListeningProcessIds 3000) {
    Write-Warning "Port 3000 is occupied, but it is not the RE:DECIDE frontend; leaving it running."
}

if (Test-Path -LiteralPath $devStatePath) {
    try {
        $saved = @(Get-Content -LiteralPath $devStatePath -Raw | ConvertFrom-Json)
        foreach ($entry in $saved) {
            $serviceHealthy = ($entry.Service -eq "backend" -and (Test-Backend)) -or
                ($entry.Service -eq "frontend" -and (Test-Frontend))
            if ($serviceHealthy -and $null -ne $entry.Id) {
                [void]$targets.Add([int]$entry.Id)
            }
        }
    }
    catch {
        Write-Warning "Ignoring unreadable launcher state at $devStatePath."
    }
}

# Older launcher runs predate services.json. Uvicorn records both its reloader
# and worker IDs in the backend log, so recover those IDs when the API is live.
if (Test-Backend) {
    $backendLog = Get-ChildItem -LiteralPath $devLogRoot -Filter "backend-*.stderr.log" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -ne $backendLog) {
        $logText = Get-Content -LiteralPath $backendLog.FullName -Raw -ErrorAction SilentlyContinue
        foreach ($match in [regex]::Matches($logText, "process \[(\d+)\]")) {
            [void]$targets.Add([int]$match.Groups[1].Value)
        }
    }
}

if ($targets.Count -eq 0) {
    Write-Host "No healthy RE:DECIDE services found on ports 3000 or 8000."
    exit 0
}

$rootIds = @($targets | ForEach-Object { [int]$_ })
$processTree = Get-ProcessTreeIds $rootIds
foreach ($processId in ($processTree | Sort-Object -Descending)) {
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        continue
    }

    if ($PSCmdlet.ShouldProcess("$($process.ProcessName) (PID $processId)", "Stop")) {
        Stop-Process -Id $processId -Force
        Write-Host "Stopped $($process.ProcessName) (PID $processId)."
    }
}

if (-not $WhatIfPreference -and (Test-Path -LiteralPath $devStatePath)) {
    Remove-Item -LiteralPath $devStatePath -Force -ErrorAction SilentlyContinue
}
