@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "FRONTEND_DIR=%SCRIPT_DIR%fronted"
set "PORT=2798"

if not exist "%FRONTEND_DIR%\package.json" (
  echo [ERROR] Frontend directory not found: "%FRONTEND_DIR%"
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

echo Checking existing frontend listener on port %PORT%...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  if not "%%P"=="0" (
    echo Stopping process %%P that is listening on port %PORT%...
    taskkill /PID %%P /F >nul 2>nul
  )
)

cd /d "%FRONTEND_DIR%"
echo Starting frontend dev server...
echo URL: http://127.0.0.1:2798
echo.
call npm run dev

pause
