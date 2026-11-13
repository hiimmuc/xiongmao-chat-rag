<#
.SYNOPSIS
  Runs the whole app on this Windows machine, with no AWS involved.

.DESCRIPTION
  Starts a project-local PostgreSQL with pgvector (scripts\local_db.py, data in .local-postgres\),
  applies migrations, then opens three PowerShell windows:
  API (http://127.0.0.1:8000), worker, and web app (http://localhost:5173).
  Create an account on the sign-in page; accounts live in the local database.

.PARAMETER PaidCalls
  Allow real Gemini/OpenAI calls with the keys in .env. These cost money.

.EXAMPLE
  .\scripts\start-local.ps1 -PaidCalls
#>
param([switch]$PaidCalls)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$python = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $python) -or -not (Test-Path "frontend\node_modules")) {
    throw "Install dependencies first (README, 'Run locally on Windows')."
}

$databaseUrl = & $python scripts\local_db.py start
if ($LASTEXITCODE -ne 0) { throw "Could not start the local database (pip install -e 'backend[test,local]')." }

# Local settings. They override anything in .env, which only needs your API keys and model catalog.
$env:APP_ENV = "local"
$env:DATABASE_URL = $databaseUrl
$env:STORAGE_DIR = Join-Path $root ".local-storage"
$env:CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
$env:PROVIDER_RETENTION_VERIFIED = if ($PaidCalls) { "true" } else { "false" }
# No VITE_API_URL: the web app calls the API on the hostname you opened it with, so the sign-in cookie works.
$env:VITE_API_URL = ""

Push-Location backend
& $python -m alembic upgrade head
$migrated = $LASTEXITCODE
Pop-Location
if ($migrated -ne 0) { throw "Migrations failed." }

# Child windows inherit the variables above.
$windows = @(
    @{ Dir = "backend";  Cmd = "& '$python' -m uvicorn app.main:app --host 127.0.0.1 --port 8000" },
    @{ Dir = "backend";  Cmd = "& '$python' -m worker.main" },
    @{ Dir = "frontend"; Cmd = "npx vite --host 127.0.0.1 --port 5173 --strictPort" }
)
New-Item -ItemType Directory -Force .local-run | Out-Null
$ids = foreach ($w in $windows) {
    (Start-Process powershell -PassThru -WorkingDirectory (Join-Path $root $w.Dir) `
        -ArgumentList "-NoExit", "-Command", $w.Cmd).Id
}
$ids | Set-Content .local-run\pids.txt

Write-Host "Open http://localhost:5173  (paid calls: $($env:PROVIDER_RETENTION_VERIFIED))"
Write-Host "Stop with .\scripts\stop-local.ps1"
