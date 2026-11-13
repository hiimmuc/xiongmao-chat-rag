<#
.SYNOPSIS
  Stops what start-local.ps1 started. The database and uploaded files are kept.
#>
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$file = ".local-run\pids.txt"
if (Test-Path $file) {
    foreach ($id in Get-Content $file) {
        # /T also stops the API, worker and Vite processes running inside each window.
        taskkill /PID $id /T /F 2>$null | Out-Null
    }
    Remove-Item $file
}
& backend\.venv\Scripts\python.exe scripts\local_db.py stop
Write-Host "Stopped. Delete the .local-postgres folder to start with an empty database."
