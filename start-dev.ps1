# StrategyLab one-click dev launcher.
# Starts the API (mock/demo data, Neon DB) and the web app, waits for both to
# be ready, then prints status. Safe to re-run — existing instances are reused.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$apiDir = Join-Path $root "apps\api"
$logDir = Join-Path $env:TEMP "opencode"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Test-PortUp([int]$Port) {
    return (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) -ne $null
}

function Start-Server {
    param([string]$Name, [int]$Port, [string]$Exe, [string[]]$Args, [string]$WorkDir)
    if (Test-PortUp $Port) {
        Write-Host "$Name already running on port $Port" -ForegroundColor DarkGray
        return
    }
    $out = Join-Path $logDir "$Name.out.log"
    $err = Join-Path $logDir "$Name.err.log"
    Start-Process -FilePath $Exe -ArgumentList $Args -WorkingDirectory $WorkDir `
        -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err | Out-Null
    Write-Host "$Name starting on port $Port (logs: $out)" -ForegroundColor Cyan
}

# 1. API — FastAPI + demo market-data provider (all mock candles), Neon Postgres
Start-Server -Name "strategylab-api" -Port 8000 `
    -Exe (Join-Path $apiDir ".venv\Scripts\python.exe") `
    -Args @("-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000") `
    -WorkDir $apiDir

# 2. Web — Next.js dev server
Start-Server -Name "strategylab-web" -Port 3000 `
    -Exe "cmd.exe" `
    -Args @("/c","npm","run","dev") `
    -WorkDir (Join-Path $root "apps\web")

# 3. Wait for readiness (API cold start incl. first cloud-DB hit can take ~15s)
$deadline = (Get-Date).AddSeconds(45)
Write-Host -NoNewline "Waiting for API"
while ((Get-Date) -lt $deadline) {
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health" -TimeoutSec 3
        if ($h.status -eq "ok") { break }
    } catch {}
    Write-Host -NoNewline "."
    Start-Sleep -Seconds 2
}
if ($h.status -eq "ok") {
    Write-Host ""
    Write-Host "API is up  -> http://127.0.0.1:8000/api/v1/health (db=$($h.database))" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "API did not become healthy in 45s — check $logDir\strategylab-api.err.log" -ForegroundColor Red
}

$webUp = Test-PortUp 3000
Write-Host ("Web is {0} -> http://localhost:3000" -f ($(if ($webUp) {"up"} else {"starting… check logs"}))) -ForegroundColor $(if ($webUp) {"Green"} else {"Yellow"})
Write-Host ""
Write-Host "Open http://localhost:3000 — no login required." -ForegroundColor White
