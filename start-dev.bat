@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

REM ============================================================
REM  start-dev.bat - one-click local dev orchestrator
REM  Starts: PostgreSQL (Docker) -> migrations -> API -> frontends
REM  Ports are read from .env so they stay in sync with CORS/public URLs.
REM ============================================================

set "ROOT=%~dp0"
cd /d "%ROOT%"

REM --- 1. Dependency checks (no || / && inside if blocks) ---
where docker >nul 2>nul
if errorlevel 1 (
  echo [ERROR] docker not found in PATH.
  pause
  exit /b 1
)
docker info >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Docker daemon not reachable. Start Docker Desktop first.
  pause
  exit /b 1
)
where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] node not found in PATH.
  pause
  exit /b 1
)
where pnpm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] pnpm not found in PATH.
  pause
  exit /b 1
)
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] python not found in PATH.
  pause
  exit /b 1
)

REM --- 2. Ensure .env exists ---
if not exist ".env" (
  if exist ".env.example" (
    echo [INFO] .env not found, copying from .env.example ...
    copy /Y ".env.example" ".env" >nul
  ) else (
    echo [ERROR] Neither .env nor .env.example found.
    pause
    exit /b 1
  )
)

REM --- 3. Read ports from .env via inline PowerShell ---
REM    Parses KEY=VALUE lines; defaults applied below in batch.
for /f "usebackq tokens=1,* delims==" %%a in (`powershell -NoProfile -Command "Get-Content .env | Where-Object { $_ -match '^(POSTGRES_PORT|API_PORT|WORKSPACE_PORT|SITE_PORT)=' }"`) do (
  if "%%a"=="POSTGRES_PORT" set "PG_PORT=%%b"
  if "%%a"=="API_PORT" set "API_PORT=%%b"
  if "%%a"=="WORKSPACE_PORT" set "WS_PORT=%%b"
  if "%%a"=="SITE_PORT" set "SITE_PORT=%%b"
)

if not defined PG_PORT set "PG_PORT=5432"
if not defined API_PORT set "API_PORT=8000"
if not defined WS_PORT set "WS_PORT=5173"
if not defined SITE_PORT set "SITE_PORT=4321"

echo [INFO] Ports ^| PG=%PG_PORT% API=%API_PORT% Workspace=%WS_PORT% Site=%SITE_PORT%

REM --- 4. Start PostgreSQL via docker compose ---
echo [INFO] Starting PostgreSQL ...
docker compose up -d postgres
if errorlevel 1 goto :fail

echo [INFO] Waiting for PostgreSQL to accept connections ...
:wait_pg
docker compose exec -T postgres pg_isready -U postgres >nul 2>nul
if errorlevel 1 (
  powershell -NoProfile -Command "Start-Sleep -Seconds 2"
  goto :wait_pg
)
echo [INFO] PostgreSQL is ready.

REM --- 5. Backend venv + deps (install only if missing) ---
if not exist "apps\api\.venv\Scripts\python.exe" (
  echo [INFO] Creating Python virtualenv ...
  pushd "apps\api"
  python -m venv .venv
  if errorlevel 1 (
    popd
    goto :fail
  )
  call ".venv\Scripts\activate.bat"
  pip install -e ".[dev]"
  if errorlevel 1 (
    popd
    goto :fail
  )
  popd
) else (
  echo [INFO] Python virtualenv already exists.
)

REM --- 6. Run database migrations ---
REM    Override DATABASE_URL to 127.0.0.1 (local, not docker service name)
REM    and force PERSISTENT_WORKFLOW_ENABLED=true for local uvicorn.
echo [INFO] Running alembic upgrade head ...
pushd "apps\api"
call ".venv\Scripts\activate.bat"
set "DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:%PG_PORT%/xingwen_astro_ai"
set "PERSISTENT_WORKFLOW_ENABLED=true"
alembic upgrade head
if errorlevel 1 (
  popd
  goto :fail
)
popd
echo [INFO] Migrations complete.

REM --- 7. Frontend deps (install only if missing) ---
if not exist "node_modules" (
  echo [INFO] Installing frontend dependencies ...
  pnpm install
  if errorlevel 1 goto :fail
) else (
  echo [INFO] Frontend dependencies already present.
)

REM --- 8. Launch API in a new window ---
REM    Start-Process launches uvicorn.exe directly (bypassing cmd /k chain
REM    which prevents uvicorn from binding the port). Env vars are set in
REM    the PowerShell process; Start-Process child inherits them.
echo [INFO] Launching API server in a new window ...
powershell -NoProfile -Command "$env:DATABASE_URL='postgresql+psycopg://postgres:postgres@127.0.0.1:%PG_PORT%/xingwen_astro_ai'; $env:PERSISTENT_WORKFLOW_ENABLED='true'; Start-Process -FilePath '%CD%\apps\api\.venv\Scripts\uvicorn.exe' -ArgumentList 'app.main:app --reload --host 0.0.0.0 --port %API_PORT%' -WorkingDirectory '%CD%\apps\api'"

echo [INFO] Waiting for API readiness at http://127.0.0.1:%API_PORT%/api/health ...
call :wait_for_url "http://127.0.0.1:%API_PORT%/api/health" 120
if errorlevel 1 (
  echo [ERROR] API did not become reachable.
  pause
  exit /b 1
)

REM --- 9. Launch frontends in new windows ---
echo [INFO] Launching Workspace frontend in a new window ...
start "xingwen-workspace" cmd /k "cd /d %CD%\apps\workspace && pnpm exec vite --host 0.0.0.0 --port %WS_PORT%"

echo [INFO] Waiting for Workspace frontend at http://127.0.0.1:%WS_PORT%/workspace ...
call :wait_for_url "http://127.0.0.1:%WS_PORT%/workspace" 60
if errorlevel 1 (
  echo [WARN] Workspace frontend did not become reachable in time.
)

echo [INFO] Launching Brand Site in a new window ...
start "xingwen-site" cmd /k "cd /d %CD%\apps\site && pnpm exec astro dev --host 0.0.0.0 --port %SITE_PORT%"

echo [INFO] Waiting for Brand Site at http://127.0.0.1:%SITE_PORT%/ ...
call :wait_for_url "http://127.0.0.1:%SITE_PORT%/" 60
if errorlevel 1 (
  echo [WARN] Brand Site did not become reachable in time.
)

REM --- 10. Open browser ---
echo [INFO] Opening browser ...
start "" "http://localhost:%WS_PORT%/workspace"

echo.
echo ============================================================
echo  All services started:
echo    PostgreSQL : localhost:%PG_PORT%
echo    API        : http://localhost:%API_PORT%/api/health
echo    Workspace  : http://localhost:%WS_PORT%/workspace
echo    Brand Site : http://localhost:%SITE_PORT%/
echo ============================================================
echo.
echo Close this window anytime; services keep running in their own windows.
echo To stop PostgreSQL:  docker compose down
echo.
pause
goto :eof

:wait_for_url
REM  %1 = url, %2 = timeout seconds
powershell -NoProfile -ExecutionPolicy Bypass -Command "$url = '%~1'; $deadline = (Get-Date).AddSeconds([int]'%~2'); while ((Get-Date) -lt $deadline) { try { $resp = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 5; if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400) { exit 0 } } catch { }; Start-Sleep -Seconds 2 }; exit 1"
if errorlevel 1 exit /b 1
exit /b 0

:fail
echo.
echo [FAILED] Startup aborted. See messages above.
pause
exit /b 1
