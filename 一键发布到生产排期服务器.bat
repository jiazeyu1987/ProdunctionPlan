@echo off
setlocal
cd /d "%~dp0"
python tool\deploy\publish_to_server.py
if errorlevel 1 (
  echo.
  echo 发布失败
  pause
  exit /b 1
)
echo.
echo 发布成功
pause
