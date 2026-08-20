# Idea Vault Launcher (Windows) - optional convenience wrapper around the
# README's `docker compose up -d`. Starts Docker Desktop if it isn't running,
# brings the containers up, waits for the dashboard to respond, then opens it
# in the default browser.
#
# Usage: run directly (`powershell -File .\Launch-IdeaVault.ps1`), or compile
# it into a double-clickable .exe - see the README's "Windows one-click
# launcher" section for the command.

# ---------------- config ----------------
$AppUrl          = "http://localhost:8090"   # matches DASHBOARD_PORT's default in .env.example
$ComposeFile     = "docker-compose.yml"
$WindowTitle     = "Idea Vault"
$HealthTimeoutSec = 90
# -----------------------------------------

$Host.UI.RawUI.WindowTitle = $WindowTitle

# Compiled by ps2exe, the running exe's own path IS the process path, so this
# resolves correctly whether run as a .ps1 (dev/test) or as the compiled .exe.
if ($PSScriptRoot) {
    $ProjectDir = $PSScriptRoot
} else {
    $ProjectDir = Split-Path ([System.Diagnostics.Process]::GetCurrentProcess().Path) -Parent
}
Set-Location $ProjectDir

function Test-DockerRunning {
    docker info *>$null
    return $LASTEXITCODE -eq 0
}

function Find-DockerDesktopExe {
    $candidates = @(
        "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
        "${env:ProgramFiles(x86)}\Docker\Docker\Docker Desktop.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    return $null
}

Write-Host "== $WindowTitle =="
Write-Host "Project folder: $ProjectDir"
Write-Host ""

if (-not (Test-DockerRunning)) {
    Write-Host "Docker Desktop is not running. Starting it..."
    $dockerExe = Find-DockerDesktopExe
    if (-not $dockerExe) {
        Write-Host "ERROR: Could not find Docker Desktop.exe. Please start Docker Desktop manually and re-run this launcher."
        Read-Host "Press Enter to close"
        exit 1
    }
    Start-Process $dockerExe

    $waited = 0
    while (-not (Test-DockerRunning) -and $waited -lt 120) {
        Start-Sleep -Seconds 3
        $waited += 3
        Write-Host "  ... waiting for Docker Desktop to be ready ($waited s)"
    }
    if (-not (Test-DockerRunning)) {
        Write-Host "ERROR: Docker Desktop did not start within 120 seconds."
        Read-Host "Press Enter to close"
        exit 1
    }
    Write-Host "Docker Desktop is ready."
}

Write-Host ""
Write-Host "Starting containers (docker compose up -d)..."
docker compose -f $ComposeFile up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: 'docker compose up' failed. See output above."
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host ""
Write-Host "Waiting for the app to respond at $AppUrl ..."
$waited = 0
$up = $false
while ($waited -lt $HealthTimeoutSec) {
    try {
        $resp = Invoke-WebRequest -Uri $AppUrl -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) { $up = $true; break }
    } catch {
        # not ready yet
    }
    Start-Sleep -Seconds 2
    $waited += 2
}

if ($up) {
    Write-Host "App is up. Opening browser..."
} else {
    Write-Host "App didn't confirm readiness within $HealthTimeoutSec s - opening the browser anyway (it may still be starting)."
}
Start-Process $AppUrl

Start-Sleep -Seconds 2
