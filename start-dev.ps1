# StrategyLab one-click dev launcher.
# Starts the API (mock/demo data, Neon DB) and the web app, waits for both to
# be ready, then prints status. Safe to re-run - existing instances are reused.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$apiDir = Join-Path $root "apps\api"
$webDir = Join-Path $root "apps\web"
$logDir = Join-Path $env:TEMP "opencode"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Test-PortUp([int]$Port) {
    return (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) -ne $null
}

# NOTE: the parameter is named $Arguments, NOT $Args. $Args is a reserved
# automatic variable in PowerShell and binding a [string[]] to it silently
# produced a null collection on PS 5.1, which made Start-Process throw
# "Cannot validate argument on parameter 'ArgumentList'".
function Start-Server {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][string]$Exe,
        [string[]]$Arguments,
        [Parameter(Mandatory)][string]$WorkDir
    )
    if (Test-PortUp $Port) {
        Write-Host "$Name already running on port $Port" -ForegroundColor DarkGray
        return
    }
    $out = Join-Path $logDir "$Name.out.log"
    $err = Join-Path $logDir "$Name.err.log"

    $launchParams = @{
        FilePath = $Exe
        WorkingDirectory = $WorkDir
        WindowStyle = 'Hidden'
        RedirectStandardOutput = $out
        RedirectStandardError = $err
    }
    if ($null -ne $Arguments -and $Arguments.Count -gt 0) {
        $launchParams.ArgumentList = $Arguments
    }

    Start-Process @launchParams | Out-Null
    Write-Host "$Name starting on port $Port (logs: $out)" -ForegroundColor Cyan
}

# 1. API - FastAPI + demo market-data provider (all mock candles), Neon Postgres
$pythonExe = Join-Path $apiDir ".venv\Scripts\python.exe"
Start-Server -Name "strategylab-api" -Port 8000 `
    -Exe $pythonExe `
    -Arguments @("-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000") `
    -WorkDir $apiDir

# 2. Web - Next.js dev server
Start-Server -Name "strategylab-web" -Port 3000 `
    -Exe "cmd.exe" `
    -Arguments @("/c","npm","run","dev") `
    -WorkDir $webDir

# 3. Wait for readiness (API cold start incl. first cloud-DB hit can take ~15s)
$deadline = (Get-Date).AddSeconds(45)
$apiHealth = $null
Write-Host -NoNewline "Waiting for API"
while ((Get-Date) -lt $deadline) {
    try {
        $apiHealth = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health" -TimeoutSec 3
        if ($apiHealth.status -eq "ok") { break }
    } catch { $apiHealth = $null }
    Write-Host -NoNewline "."
    Start-Sleep -Seconds 2
}
Write-Host ""
if ($apiHealth -and $apiHealth.status -eq "ok") {
    Write-Host "API is up  -> http://127.0.0.1:8000/api/v1/health (db=$($apiHealth.database))" -ForegroundColor Green
} else {
    Write-Host "API did not become healthy in 45s - check $logDir\strategylab-api.err.log" -ForegroundColor Red
}

$webUp = Test-PortUp 3000
if ($webUp) {
    Write-Host "Web is up -> http://localhost:3000" -ForegroundColor Green
} else {
    Write-Host "Web is starting... check logs" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Open http://localhost:3000 - no login required." -ForegroundColor White
