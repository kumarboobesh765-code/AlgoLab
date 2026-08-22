# Start the StrategyLab API (local dev, SQLite fallback)
# Usage: .\scripts\run-api.ps1
Set-Location "$PSScriptRoot\..\apps\api"
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv run uvicorn app.main:app --reload --port 8000
