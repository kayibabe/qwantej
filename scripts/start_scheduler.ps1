# start_scheduler.ps1 — launch the qwantej multi-worker scheduler.
#
# Usage (foreground, Ctrl-C to stop):
#   .\scripts\start_scheduler.ps1
#
# Usage (background, log to file):
#   Start-Process powershell -ArgumentList "-File scripts\start_scheduler.ps1" -WindowStyle Hidden
#
# Register as a Windows Task Scheduler task (runs at logon, hidden):
#   $trigger  = New-ScheduledTaskTrigger -AtLogon
#   $action   = New-ScheduledTaskAction -Execute "powershell.exe" `
#                   -Argument "-NonInteractive -File `"$PWD\scripts\start_scheduler.ps1`"" `
#                   -WorkingDirectory $PWD
#   $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
#                   -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
#   Register-ScheduledTask -TaskName "qwantej-scheduler" -Trigger $trigger `
#       -Action $action -Settings $settings -RunLevel Highest -Force

$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$venv = Join-Path $repo ".venv\Scripts\python.exe"

if (-not (Test-Path $venv)) {
    Write-Error "virtualenv not found at $venv — run: python -m venv .venv && .venv\Scripts\pip install -e .[backend]"
    exit 1
}

$logDir = Join-Path $repo "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$logFile = Join-Path $logDir "scheduler-$(Get-Date -Format 'yyyyMMdd').log"

Write-Host "Starting qwantej scheduler — log: $logFile"
& $venv -m backend.workers.scheduler @args 2>&1 | Tee-Object -FilePath $logFile -Append
