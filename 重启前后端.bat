@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=2798"
set "BACKEND_URL=http://127.0.0.1:%BACKEND_PORT%/api/health"
set "FRONTEND_URL=http://127.0.0.1:%FRONTEND_PORT%"
set "FRONTEND_DIR=%PROJECT_DIR%fronted"

if not exist "%PROJECT_DIR%backend\app\main.py" (
  echo [ERROR] Backend entry not found: "%PROJECT_DIR%backend\app\main.py"
  pause
  exit /b 1
)

if not exist "%FRONTEND_DIR%\package.json" (
  echo [ERROR] Frontend directory not found: "%FRONTEND_DIR%"
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found in PATH.
  pause
  exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js was not found in PATH.
  pause
  exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules" (
  echo [ERROR] node_modules not found. Run npm install in "%FRONTEND_DIR%" first.
  pause
  exit /b 1
)

echo Stopping listeners on ports %BACKEND_PORT% and %FRONTEND_PORT%...
for %%I in (%BACKEND_PORT% %FRONTEND_PORT%) do (
  for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%%I .*LISTENING"') do (
    if not "%%P"=="0" (
      echo   - Killing PID %%P on port %%I
      taskkill /PID %%P /F >nul 2>nul
    )
  )
)

echo Starting backend...
start "ProductionPlan Backend" cmd /k "cd /d "%PROJECT_DIR%" && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port %BACKEND_PORT%"

echo Starting frontend...
start "ProductionPlan Frontend" cmd /k "cd /d "%FRONTEND_DIR%" && npm run dev"

echo Waiting for services to become healthy...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$backend='%BACKEND_URL%';" ^
  "$frontend='%FRONTEND_URL%';" ^
  "function Wait-Url([string]$url,[int]$retrySeconds) {" ^
  "  for ($i = 0; $i -lt $retrySeconds; $i++) {" ^
  "    try {" ^
  "      $res = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2;" ^
  "      if ($res.StatusCode -ge 200 -and $res.StatusCode -lt 500) { return $true }" ^
  "    } catch {}" ^
  "    Start-Sleep -Seconds 1" ^
  "  }" ^
  "  return $false" ^
  "};" ^
  "$backendOk = Wait-Url $backend 20;" ^
  "$frontendOk = Wait-Url $frontend 30;" ^
  "if (-not $backendOk) { Write-Host '[ERROR] Backend health check failed:' $backend; exit 1 }" ^
  "if (-not $frontendOk) { Write-Host '[ERROR] Frontend health check failed:' $frontend; exit 1 }" ^
  "Write-Host '[OK] Backend:' $backend;" ^
  "Write-Host '[OK] Frontend:' $frontend;"

if errorlevel 1 (
  echo Restart completed, but at least one service failed the health check.
  pause
  exit /b 1
)

echo Restart completed successfully.
pause
