@echo off
title Qwantej - Starting
echo.
echo  ============================
echo   QWANTEJ - Starting up...
echo  ============================
echo.

cd /d "%~dp0"
set "FRONTEND_PORT=3011"
set "PORTFOLIO_ENV=%~dp0..\local-server\config\portfolio.env"

echo [1/4] Checking Docker Desktop...
docker info >nul 2>&1
if not errorlevel 1 (
    set "DOCKER_READY=1"
    goto :docker_ready
)
if errorlevel 1 (
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
)

echo Waiting for Docker engine to become ready...
set "DOCKER_READY=0"
for /l %%i in (1,1,60) do (
    docker info >nul 2>&1
    if not errorlevel 1 (
        set "DOCKER_READY=1"
        goto :docker_ready
    )
    timeout /t 2 /nobreak >nul
)

:docker_ready
if "%DOCKER_READY%" neq "1" (
    echo ERROR: Docker Desktop did not become ready within 120 seconds.
    pause
    exit /b 1
)

echo [2/4] Starting backend services (Postgres, Redis, API, Celery)...
docker network inspect local-portfolio-read >nul 2>&1
if errorlevel 1 (
    docker network create local-portfolio-read >nul
    if errorlevel 1 (
        echo ERROR: Could not create the shared Portfolio read network.
        pause
        exit /b 1
    )
)
docker compose --env-file "%PORTFOLIO_ENV%" build backend
if errorlevel 1 (
    echo ERROR: Backend image build failed.
    pause
    exit /b 1
)
docker compose --env-file "%PORTFOLIO_ENV%" up -d
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
    timeout /t 2 /nobreak >nul
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
set "VITE_API_PROXY_TARGET=http://127.0.0.1:%API_PORT%"
start "Qwantej Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev -- --port %FRONTEND_PORT% --strictPort"

echo.
echo [4/4] Waiting for Vite to compile, then opening browser...
set "FRONTEND_READY=0"
for /l %%i in (1,1,30) do (
    powershell -NoProfile -Command "try { if ((Invoke-WebRequest -UseBasicParsing http://localhost:%FRONTEND_PORT%).StatusCode -eq 200) { exit 0 } } catch {} ; exit 1" >nul 2>&1
    if not errorlevel 1 (
        set "FRONTEND_READY=1"
        goto :frontend_ready
    )
    timeout /t 2 /nobreak >nul
)
:frontend_ready
if "%FRONTEND_READY%" neq "1" (
    echo ERROR: Frontend did not respond within 60 seconds.
    pause
    exit /b 1
)
start http://localhost:%FRONTEND_PORT%

echo.
echo  ============================
echo   QWANTEJ is running!
echo.
echo   App      : http://localhost:%FRONTEND_PORT%
echo   API docs : http://localhost:%API_PORT%/docs
echo.
echo   Run stop.bat to shut down.
echo  ============================
echo.
timeout /t 3 /nobreak >nul
exit
