@echo off
setlocal EnableExtensions
title QwanEj - Starting
echo.
echo  ============================
echo   QwanEj - Starting up...
echo  ============================
echo.

cd /d "%~dp0"
set "FRONTEND_PORT=3000"
set "FRONTEND_URL=http://localhost:%FRONTEND_PORT%"

echo [1/4] Checking Docker Desktop...
docker info >nul 2>&1
if not errorlevel 1 goto :docker_ready

echo Docker engine is not running. Starting Docker Desktop...
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
    start "Docker Desktop" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
) else if exist "%LocalAppData%\Docker\Docker Desktop.exe" (
    start "Docker Desktop" "%LocalAppData%\Docker\Docker Desktop.exe"
) else (
    echo ERROR: Docker Desktop was not found on this computer.
    pause
    exit /b 1
)

echo Waiting for Docker engine to become ready...
for /l %%i in (1,1,60) do (
    docker info >nul 2>&1
    if not errorlevel 1 goto :docker_ready
    call :wait_2s
)
echo ERROR: Docker Desktop did not become ready within 120 seconds.
pause
exit /b 1

:docker_ready
echo [2/4] Starting backend services (Postgres, Redis, API, Celery)...
docker compose build backend
if errorlevel 1 (
    echo ERROR: Backend image build failed.
    pause
    exit /b 1
)
docker compose up -d --remove-orphans
if errorlevel 1 (
    echo ERROR: Docker Compose failed.
    docker compose logs --tail=50 migrate backend
    pause
    exit /b 1
)

echo Waiting for the API to become healthy...
set "API_PORT=8000"
for /f "tokens=2 delims=:" %%p in ('docker compose port backend 8000 2^>nul') do set "API_PORT=%%p"

set "API_READY=0"
for /l %%i in (1,1,30) do (
    powershell -NoProfile -Command "try { if ((Invoke-WebRequest -UseBasicParsing http://127.0.0.1:%API_PORT%/health/ready).StatusCode -eq 200) { exit 0 } } catch {} ; exit 1" >nul 2>&1
    if not errorlevel 1 (
        set "API_READY=1"
        goto :api_ready
    )
    call :wait_2s
)
:api_ready
if "%API_READY%" neq "1" (
    echo ERROR: The API did not become ready within 60 seconds.
    docker compose logs --tail=30 backend
    pause
    exit /b 1
)

echo.
echo [3/4] Starting frontend dev server...
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing http://localhost:%FRONTEND_PORT% -TimeoutSec 2; if ($r.StatusCode -eq 200 -and $r.Content -match 'QwanEj') { exit 0 } } catch {} ; exit 1" >nul 2>&1
if not errorlevel 1 (
    echo QwanEj frontend is already running on port %FRONTEND_PORT%.
    set "FRONTEND_READY=1"
    goto :frontend_ready
)
if not exist "frontend\node_modules\.bin\vite.cmd" (
    echo ERROR: Frontend dependencies are missing.
    echo Run "npm install" in the frontend folder, then try again.
    pause
    exit /b 1
)

set "VITE_API_PROXY_TARGET=http://127.0.0.1:%API_PORT%"
start "QwanEj Frontend" cmd /k "cd /d "%~dp0frontend" && call node_modules\.bin\vite.cmd --port %FRONTEND_PORT% --strictPort"

echo.
echo [4/4] Waiting for Vite to compile, then opening browser...
set "FRONTEND_READY=0"
for /l %%i in (1,1,30) do (
    powershell -NoProfile -Command "try { if ((Invoke-WebRequest -UseBasicParsing http://localhost:%FRONTEND_PORT%).StatusCode -eq 200) { exit 0 } } catch {} ; exit 1" >nul 2>&1
    if not errorlevel 1 (
        set "FRONTEND_READY=1"
        goto :frontend_ready
    )
    call :wait_2s
)
:frontend_ready
if "%FRONTEND_READY%" neq "1" (
    echo ERROR: Frontend did not respond within 60 seconds.
    echo Check the "QwanEj Frontend" console window for the Vite error.
    pause
    exit /b 1
)
start "" "%FRONTEND_URL%"

echo.
echo  ============================
echo   QwanEj is running!
echo.
echo   App      : %FRONTEND_URL%
echo   API docs : http://127.0.0.1:%API_PORT%/docs
echo.
echo   Run stop.bat to shut down.
echo  ============================
echo.
call :wait_3s
exit /b 0

:wait_2s
ping -n 3 127.0.0.1 >nul
exit /b 0

:wait_3s
ping -n 4 127.0.0.1 >nul
exit /b 0
