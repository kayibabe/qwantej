@echo off
setlocal enabledelayedexpansion
title Qwantej Shutdown
color 0E

echo ============================================================
echo                     Qwantej Shutdown
echo ============================================================
echo.

set BACKEND_PORT=8010
set FRONTEND_PORT=5173
set /a KILLED=0

:: Must match the paths set in start-Qwantej.bat
set "BPID=%TEMP%\Qwantej-backend.pid"
set "FPID=%TEMP%\Qwantej-frontend.pid"

:: -- 1. Kill the backend server process by port --------------------
echo [1/3] Stopping backend  (port %BACKEND_PORT%)...
set /a BACKEND_KILLED=0
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":%BACKEND_PORT% " ^| findstr "LISTENING"') do (
    echo       Found PID %%a -- terminating with children.
    taskkill /F /T /PID %%a >nul 2>&1
    set /a KILLED+=1
    set /a BACKEND_KILLED+=1
)
if !BACKEND_KILLED! equ 0 echo       Nothing found on port %BACKEND_PORT%.

:: -- 2. Kill the frontend server process by port -------------------
set /a FRONTEND_KILLED=0
echo [2/3] Stopping frontend (port %FRONTEND_PORT%)...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":%FRONTEND_PORT% " ^| findstr "LISTENING"') do (
    echo       Found PID %%a -- terminating with children.
    taskkill /F /T /PID %%a >nul 2>&1
    set /a KILLED+=1
    set /a FRONTEND_KILLED+=1
)
if !FRONTEND_KILLED! equ 0 echo       Nothing found on port %FRONTEND_PORT%.

:: -- 3. Close the CMD console windows opened by start-Qwantej ------
echo [3/3] Closing Qwantej console windows...
set /a WINDOWS_CLOSED=0

if exist "%BPID%" (
    for /f "usebackq delims=" %%p in ("%BPID%") do (
        echo       Closing backend console  ^(PID %%p^)...
        taskkill /F /T /PID %%p >nul 2>&1
        set /a WINDOWS_CLOSED+=1
    )
    del "%BPID%" >nul 2>&1
) else (
    echo       No backend PID file found -- relying on fallback.
)

if exist "%FPID%" (
    for /f "usebackq delims=" %%p in ("%FPID%") do (
        echo       Closing frontend console ^(PID %%p^)...
        taskkill /F /T /PID %%p >nul 2>&1
        set /a WINDOWS_CLOSED+=1
    )
    del "%FPID%" >nul 2>&1
) else (
    echo       No frontend PID file found -- relying on fallback.
)

:: Fallback: catch any lingering Qwantej-* titled windows
powershell -NoProfile -Command "$extra = 0; Get-Process -Name cmd -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like 'Qwantej-*' } | ForEach-Object { Write-Host ('      Fallback close: ' + $_.MainWindowTitle); Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; $extra++ }; if ($extra -gt 0) { Write-Host ('      Closed ' + $extra + ' additional window(s) by title.') }"

:: -- 4. Verify ports are free --------------------------------------
echo.
echo [4/4] Verifying ports are free...
ping -n 2 127.0.0.1 >nul 2>&1

set /a STILL_RUNNING=0
netstat -aon 2>nul | findstr ":%BACKEND_PORT% " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [WARN] Port %BACKEND_PORT% is still in use. A process may have survived.
    set /a STILL_RUNNING+=1
) else (
    echo       Port %BACKEND_PORT% is free. OK
)
netstat -aon 2>nul | findstr ":%FRONTEND_PORT% " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [WARN] Port %FRONTEND_PORT% is still in use. A process may have survived.
    set /a STILL_RUNNING+=1
) else (
    echo       Port %FRONTEND_PORT% is free. OK
)

:: -- Summary --------------------------------------------------------
echo.
if !KILLED! gtr 0 (
    echo [OK] Terminated !KILLED! server process^(es^) and closed !WINDOWS_CLOSED! console window^(s^).
) else (
    echo [INFO] No Qwantej server processes were found running.
)
if !STILL_RUNNING! gtr 0 (
    echo [WARN] !STILL_RUNNING! port^(s^) still occupied -- check Task Manager.
)
echo.
echo ============================================================
echo.
pause
