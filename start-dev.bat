@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "COMPOSE_PROJECT_NAME=xingwen-astro-ai-dev"
set "WORKSPACE_URL=http://127.0.0.1:5173/workspace"
set "SITE_URL=http://127.0.0.1:4321"
set "API_HEALTH_URL=http://127.0.0.1:8000/api/health"
set "PAUSE_ON_EXIT=1"

if /i "%~1"=="--no-pause" set "PAUSE_ON_EXIT=0"
if not "%~1"=="" if /i not "%~1"=="--no-pause" goto :usage

cd /d "%ROOT%" || goto :abort

echo [INFO] Checking local prerequisites...
call :require_command docker || goto :abort
call :require_command powershell || goto :abort

docker info >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker Desktop is not running or the Docker daemon is unavailable.
  echo [INFO] Start Docker Desktop, then run this script again.
  goto :abort
)

docker compose version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker Compose is not available through the Docker CLI.
  goto :abort
)

if not exist "%ROOT%\docker-compose.yml" (
  echo [ERROR] docker-compose.yml was not found at %ROOT%.
  goto :abort
)
if not exist "%ROOT%\package.json" (
  echo [ERROR] package.json was not found at %ROOT%.
  goto :abort
)
if not exist "%ROOT%\.env" (
  if not exist "%ROOT%\.env.example" (
    echo [ERROR] Neither .env nor .env.example exists at %ROOT%.
    goto :abort
  )
  echo [INFO] .env is missing; copying .env.example for local development.
  copy /Y "%ROOT%\.env.example" "%ROOT%\.env" >nul
  if errorlevel 1 (
    echo [ERROR] Could not create .env from .env.example.
    goto :abort
  )
  echo [WARN] Review .env and replace external API placeholders before using AI features.
)

docker compose config --quiet >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker Compose configuration is invalid.
  echo [INFO] Inspect .env and run: docker compose config --quiet
  goto :abort
)

echo [INFO] Starting the Docker-first development stack...
docker compose up --build --wait --detach
if errorlevel 1 (
  echo [ERROR] Docker Compose could not start the development stack.
  docker compose ps --all
  goto :abort
)

call :wait_for_url "%API_HEALTH_URL%" 120 API || goto :diagnose
call :wait_for_url "%WORKSPACE_URL%" 120 Workspace || goto :diagnose
call :wait_for_url "%SITE_URL%" 120 Site || goto :diagnose

echo [INFO] Opening %WORKSPACE_URL% ...
start "" "%WORKSPACE_URL%"

echo.
echo ============================================================
echo  Xingwen Astro AI development stack is ready.
echo  Workspace: %WORKSPACE_URL%
echo  Site:      %SITE_URL%
echo  API:       %API_HEALTH_URL%
echo  Compose:   %COMPOSE_PROJECT_NAME%
echo.
echo  Stop containers without deleting volumes:
echo    docker compose -p %COMPOSE_PROJECT_NAME% down
echo  Inspect service state:
echo    docker compose -p %COMPOSE_PROJECT_NAME% ps
echo  View service logs:
echo    docker compose -p %COMPOSE_PROJECT_NAME% logs --tail=80 api workspace site
echo ============================================================
echo.

if "%PAUSE_ON_EXIT%"=="1" pause
exit /b 0

:wait_for_url
set "CHECK_URL=%~1"
set "CHECK_TIMEOUT=%~2"
set "CHECK_NAME=%~3"
echo [INFO] Waiting for %CHECK_NAME% at %CHECK_URL% ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$url = $env:CHECK_URL; $deadline = (Get-Date).ToUniversalTime().AddSeconds([int]$env:CHECK_TIMEOUT); while ((Get-Date).ToUniversalTime() -lt $deadline) { try { $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 5; if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) { exit 0 } } catch { }; Start-Sleep -Seconds 2 }; exit 1"
if errorlevel 1 (
  echo [ERROR] %CHECK_NAME% did not become reachable within %CHECK_TIMEOUT% seconds.
  exit /b 1
)
echo [OK] %CHECK_NAME% is reachable.
exit /b 0

:require_command
where %~1 >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Required command not found: %~1
  exit /b 1
)
exit /b 0

:diagnose
echo.
echo [ERROR] A service did not become reachable. Current Compose state:
docker compose ps --all
echo [INFO] Inspect logs with: docker compose -p %COMPOSE_PROJECT_NAME% logs --tail=80 api workspace site
goto :abort

:usage
echo Usage: start-dev.bat [--no-pause]
echo.
echo Starts the Docker-first development stack, waits for health, and opens Workspace.
exit /b 2

:abort
echo.
echo [ERROR] Startup did not complete. Existing containers were left in place for diagnosis.
echo [INFO] Stop them when needed with: docker compose -p %COMPOSE_PROJECT_NAME% down
if "%PAUSE_ON_EXIT%"=="1" pause
exit /b 1
