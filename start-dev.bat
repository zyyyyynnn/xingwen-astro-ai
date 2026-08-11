@echo off
setlocal EnableExtensions
chcp 65001 >nul

if /i "%~1"=="--preflight" (
  shift
) else (
  start "Xingwen Preflight" cmd /k ""%~f0" --preflight %*"
  exit /b 0
)

title Xingwen Preflight

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "API_DIR=%ROOT%\apps\api"
set "COMPOSE_PROJECT_NAME=xingwen-astro-ai-dev"
set "API_URL=http://127.0.0.1:8000"
set "API_HEALTH_URL=%API_URL%/api/health"
set "WORKSPACE_URL=http://127.0.0.1:5173/workspace"
set "SITE_URL=http://127.0.0.1:4321"
set "PAUSE_ON_EXIT=1"

if /i "%~1"=="--no-pause" set "PAUSE_ON_EXIT=0"
if not "%~1"=="" if /i not "%~1"=="--no-pause" goto :usage

cd /d "%ROOT%" || goto :abort

echo [INFO] Preflight: checking local tools and repository files...
call :require_command docker || goto :abort
call :require_command uv || goto :abort
call :require_command pnpm || goto :abort
call :require_command powershell || goto :abort

docker info >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker Desktop is not running or the Docker daemon is unavailable.
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
if not exist "%API_DIR%\pyproject.toml" (
  echo [ERROR] API project was not found at %API_DIR%.
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
  echo [INFO] Creating .env from .env.example for local development.
  copy /Y "%ROOT%\.env.example" "%ROOT%\.env" >nul || goto :abort
)

set "POSTGRES_DB=xingwen_astro_ai"
set "POSTGRES_USER=postgres"
set "POSTGRES_PASSWORD=postgres"
set "POSTGRES_PORT=5432"
for /f "usebackq tokens=1,* delims==" %%A in ("%ROOT%\.env") do (
  if /i "%%A"=="POSTGRES_DB" set "POSTGRES_DB=%%B"
  if /i "%%A"=="POSTGRES_USER" set "POSTGRES_USER=%%B"
  if /i "%%A"=="POSTGRES_PASSWORD" set "POSTGRES_PASSWORD=%%B"
  if /i "%%A"=="POSTGRES_PORT" set "POSTGRES_PORT=%%B"
)
set "LOCAL_DATABASE_URL=postgresql+psycopg://%POSTGRES_USER%:%POSTGRES_PASSWORD%@127.0.0.1:%POSTGRES_PORT%/%POSTGRES_DB%"

docker compose -p %COMPOSE_PROJECT_NAME% config --quiet >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker Compose configuration is invalid. Inspect .env.
  goto :abort
)

echo [INFO] Preflight: synchronizing locked dependencies...
uv sync --project "%API_DIR%" --frozen >nul 2>&1 || goto :abort
call pnpm install --frozen-lockfile >nul 2>&1 || goto :abort

echo [INFO] Preflight: switching application services to local windows...
docker compose -p %COMPOSE_PROJECT_NAME% stop api workspace site >nul 2>&1
call :require_free_port 8000 API || goto :abort
call :require_free_port 5173 Workspace || goto :abort
call :require_free_port 4321 Site || goto :abort

echo [INFO] Preflight: starting PostgreSQL...
docker compose -p %COMPOSE_PROJECT_NAME% up -d --wait postgres >nul 2>&1 || goto :abort

echo [INFO] Preflight: applying the current database schema...
pushd "%API_DIR%"
set "DATABASE_URL=%LOCAL_DATABASE_URL%"
uv run alembic upgrade head >nul 2>&1
set "MIGRATION_RESULT=%ERRORLEVEL%"
popd
if not "%MIGRATION_RESULT%"=="0" goto :abort

echo [INFO] Starting backend window...
start "Xingwen Backend" cmd /k "cd /d "%API_DIR%" && set "DATABASE_URL=%LOCAL_DATABASE_URL%" && uv run --project "%API_DIR%" uvicorn app.main:app --app-dir "%API_DIR%\src" --reload --host 127.0.0.1 --port 8000"
call :wait_for_url "%API_HEALTH_URL%" 120 Backend || goto :diagnose

echo [INFO] Starting frontend window...
start "Xingwen Frontend" cmd /k "cd /d "%ROOT%" && set "VITE_API_BASE_URL=%API_URL%" && set "PUBLIC_WORKSPACE_URL=%WORKSPACE_URL%" && pnpm dev"
call :wait_for_url "%SITE_URL%" 120 Site || goto :diagnose
call :wait_for_url "%WORKSPACE_URL%" 120 Workspace || goto :diagnose

echo [INFO] Opening homepage %SITE_URL% ...
start "" "%SITE_URL%"

echo.
echo ============================================================
echo  Xingwen Astro AI local development is ready.
echo  Homepage:  %SITE_URL%
echo  Workspace: %WORKSPACE_URL%
echo  API:       %API_HEALTH_URL%
echo  PostgreSQL Compose project: %COMPOSE_PROJECT_NAME%
echo.
echo  Windows: Xingwen Preflight, Xingwen Backend, Xingwen Frontend
echo  Stop backend/frontend: Ctrl+C in their windows
echo  Stop PostgreSQL: docker compose -p %COMPOSE_PROJECT_NAME% stop postgres
echo ============================================================
echo.

if "%PAUSE_ON_EXIT%"=="1" pause
exit /b 0

:require_command
where %~1 >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Required command not found: %~1
  exit /b 1
)
exit /b 0

:require_free_port
powershell -NoProfile -ExecutionPolicy Bypass -Command "$port = %~1; if (@(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue).Count -gt 0) { exit 1 }"
if errorlevel 1 (
  echo [ERROR] %~2 port %~1 is already in use.
  exit /b 1
)
exit /b 0

:wait_for_url
echo [INFO] Waiting for %~3 at %~1 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$url = '%~1'; $deadline = (Get-Date).AddSeconds([int]'%~2'); while ((Get-Date) -lt $deadline) { try { $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 5; if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) { exit 0 } } catch { }; Start-Sleep -Seconds 2 }; exit 1"
if errorlevel 1 (
  echo [ERROR] %~3 did not become reachable within %~2 seconds.
  exit /b 1
)
echo [OK] %~3 is reachable.
exit /b 0

:diagnose
echo.
echo [ERROR] Startup did not complete. Check the Backend and Frontend windows.
docker compose -p %COMPOSE_PROJECT_NAME% ps --all >nul 2>&1
goto :abort

:usage
echo Usage: start-dev.bat [--no-pause]
echo.
echo Runs preflight in this window, starts Backend and Frontend windows, then opens Homepage.
exit /b 2

:abort
echo.
echo [ERROR] Startup did not complete. Existing services were left available for diagnosis.
if "%PAUSE_ON_EXIT%"=="1" pause
exit /b 1
