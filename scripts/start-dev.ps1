[CmdletBinding()]
param(
    [switch]$SkipSetup
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$frontendRoot = Join-Path $repoRoot "frontend"
$devLogRoot = Join-Path $env:TEMP "GHackathon-dev"
$startedProcesses = [System.Collections.Generic.List[System.Diagnostics.Process]]::new()

function Test-TcpPort([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $client.Connect("127.0.0.1", $Port)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
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

function Wait-ForService(
    [string]$Name,
    [scriptblock]$HealthCheck,
    [System.Diagnostics.Process]$Process,
    [string]$ErrorLog
) {
    for ($attempt = 0; $attempt -lt 120; $attempt += 1) {
        if (& $HealthCheck) {
            return
        }
        if ($Process.HasExited) {
            $details = if (Test-Path $ErrorLog) { (Get-Content $ErrorLog -Tail 30) -join "`n" } else { "No error log was created." }
            throw "$Name exited before becoming ready.`n$details"
        }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name did not become ready within 60 seconds. See $ErrorLog"
}

function Start-LoggedProcess(
    [string]$Name,
    [string]$FilePath,
    [string[]]$Arguments,
    [string]$WorkingDirectory
) {
    New-Item -ItemType Directory -Path $devLogRoot -Force | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss-fff"
    $stdout = Join-Path $devLogRoot "$Name-$stamp.stdout.log"
    $stderr = Join-Path $devLogRoot "$Name-$stamp.stderr.log"
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -WindowStyle Hidden `
        -PassThru
    $startedProcesses.Add($process)
    return [pscustomobject]@{
        Process = $process
        Stdout = $stdout
        Stderr = $stderr
    }
}

$backendRunning = Test-Backend
$frontendRunning = Test-Frontend

if (-not $backendRunning -and (Test-TcpPort 8000)) {
    throw "Port 8000 is already occupied, but it is not this repository's healthy backend. Stop that process or choose another port."
}
if (-not $frontendRunning -and (Test-TcpPort 3000)) {
    throw "Port 3000 is already occupied, but it is not responding as a frontend. Stop that process or choose another port."
}

if ($backendRunning -and $frontendRunning) {
    Write-Host "Backend and frontend are already running; nothing new was started."
    Write-Host "Frontend: http://localhost:3000"
    Write-Host "Backend:  http://127.0.0.1:8000/docs"
    exit 0
}

if (-not $SkipSetup) {
    if (-not $backendRunning) {
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            throw "uv is required. Install uv and Python 3.12+ before continuing."
        }
        Push-Location $repoRoot
        try {
            & uv sync --extra full --locked
            if ($LASTEXITCODE -ne 0) { throw "Python dependency setup failed." }
        }
        finally {
            Pop-Location
        }
    }

    if (-not $frontendRunning) {
        & (Join-Path $PSScriptRoot "install-js-deps.ps1")
        if ($LASTEXITCODE -ne 0) { throw "Frontend dependency setup failed." }
    }
}

$rootEnv = Join-Path $repoRoot ".env"
if (-not (Test-Path $rootEnv)) {
    Copy-Item (Join-Path $repoRoot ".env.example") $rootEnv
    Write-Warning "Created .env from .env.example. Add DEEPSEEK_API_KEY for live coaching."
}

$frontendEnv = Join-Path $frontendRoot ".env.local"
if (-not (Test-Path $frontendEnv)) {
    @(
        "NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000",
        "NEXT_PUBLIC_REPLAY_UPLOAD_MODE=direct"
    ) | Set-Content -LiteralPath $frontendEnv
}

try {
    if (-not $backendRunning) {
        $uvCommand = Get-Command uv -ErrorAction Stop
        $backend = Start-LoggedProcess `
            -Name "backend" `
            -FilePath $uvCommand.Source `
            -Arguments @("run", "uvicorn", "backend.app.main:app", "--env-file", ".env", "--reload", "--port", "8000") `
            -WorkingDirectory $repoRoot
        Wait-ForService -Name "Backend" -HealthCheck ${function:Test-Backend} -Process $backend.Process -ErrorLog $backend.Stderr
        Write-Host "Started backend (PID $($backend.Process.Id)). Logs: $($backend.Stdout)"
    }
    else {
        Write-Host "Reusing the healthy backend already listening on port 8000."
    }

    if (-not $frontendRunning) {
        $pnpmCommand = Get-Command pnpm -ErrorAction Stop
        $frontend = Start-LoggedProcess `
            -Name "frontend" `
            -FilePath $pnpmCommand.Source `
            -Arguments @("dev") `
            -WorkingDirectory $frontendRoot
        Wait-ForService -Name "Frontend" -HealthCheck ${function:Test-Frontend} -Process $frontend.Process -ErrorLog $frontend.Stderr
        Write-Host "Started frontend (PID $($frontend.Process.Id)). Logs: $($frontend.Stdout)"
    }
    else {
        Write-Host "Reusing the frontend already listening on port 3000."
    }
}
catch {
    foreach ($process in $startedProcesses) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    throw
}

Write-Host ""
Write-Host "Ready:"
Write-Host "  Frontend: http://localhost:3000"
Write-Host "  Backend:  http://127.0.0.1:8000/docs"
Write-Host ""
Write-Host "Rerunning this script will reuse these healthy services instead of starting conflicting copies."
if ($startedProcesses.Count -gt 0) {
    $ids = ($startedProcesses | ForEach-Object { $_.Id }) -join ","
    Write-Host "To stop services started by this run: Stop-Process -Id $ids"
}
