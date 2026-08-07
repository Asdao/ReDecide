param(
    [switch]$IncludeAgentHarness
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js is required. Install Node 24.x before continuing."
}
if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
    throw "pnpm is required. Install or enable pnpm 11.x before continuing."
}

$nodeMajor = & node -p "process.versions.node.split('.')[0]"
if ($LASTEXITCODE -ne 0 -or $nodeMajor -ne "24") {
    throw "The frontend requires Node 24.x; found $(& node --version)."
}

$pnpmVersion = & pnpm --version
if ($LASTEXITCODE -ne 0 -or -not $pnpmVersion.StartsWith("11.")) {
    throw "This repository requires pnpm 11.x; found $pnpmVersion."
}

& node (Join-Path $repoRoot "security\check-lockfiles.mjs")
if ($LASTEXITCODE -ne 0) {
    throw "The lockfile policy check failed."
}

function Install-FrozenProject([string]$Project) {
    $projectPath = Join-Path $repoRoot $Project
    Write-Host "Installing $Project from its frozen lockfile..."
    Push-Location $projectPath
    try {
        & pnpm install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) {
            throw "pnpm install failed for $Project."
        }
    }
    finally {
        Pop-Location
    }
}

if ($IncludeAgentHarness) {
    Install-FrozenProject "agent-harness"
}
Install-FrozenProject "frontend"

Write-Host "JavaScript dependencies installed successfully."
