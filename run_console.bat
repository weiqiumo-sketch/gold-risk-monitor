@echo off
setlocal
cd /d "%~dp0"

set "GOLD_PYTHON=C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%GOLD_PYTHON%" (
  "%GOLD_PYTHON%" app.py --once
  pause
  exit /b
)

python app.py --once
pause
