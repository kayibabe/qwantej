@echo off
setlocal EnableExtensions
title QwanEj - Stopping
echo.
echo  ============================
echo   QwanEj - Shutting down...
echo  ============================
echo.

cd /d "%~dp0"

echo [1/3] Closing the QwanEj frontend console...
set "QWANTEJ_FRONTEND=%~dp0frontend"
powershell -NoProfile -Command "$frontend = $env:QWANTEJ_FRONTEND; $targets = Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'cmd.exe' -and $_.CommandLine -like ('*' + $frontend + '*') -and ($_.CommandLine -like '*vite*' -or $_.CommandLine -like '*npm run dev*')) -or ($_.Name -eq 'node.exe' -and $_.CommandLine -like ('*' + $frontend + '*vite*')) }; if (-not $targets) { exit 1 }; foreach ($target in $targets) { taskkill /PID $target.ProcessId /T /F 2>$null | Out-Null }; exit 0"
if errorlevel 1 (
    echo No QwanEj frontend process was found.
) else (
    echo Frontend stopped.
)

echo [2/3] Stopping backend services...
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker is not running; backend services are already stopped.
) else (
    docker compose down --remove-orphans
    if errorlevel 1 (
        echo WARNING: Docker Compose reported an error while stopping the services.
        pause
        exit /b 1
    )
)

echo [3/3] Done.
echo.
echo  ============================
echo   All services stopped.
echo   Your data is safe in the
echo   Docker volume (postgres_data).
echo  ============================
echo.
call :wait_3s
exit /b 0

:wait_3s
ping -n 4 127.0.0.1 >nul
exit /b 0
