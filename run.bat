@echo off
setlocal
cd /d "%~dp0"

set "GOLD_PYTHON=C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
if exist "%GOLD_PYTHON%" (
  start "" "%GOLD_PYTHON%" "%~dp0app.py"
  exit /b 0
)

where pythonw >nul 2>&1
if %errorlevel%==0 (
  start "" pythonw "%~dp0app.py"
  exit /b 0
)

echo 未找到 Python。请安装 Python 3.11 或更高版本，或直接使用 GitHub Pages 看板。
pause
