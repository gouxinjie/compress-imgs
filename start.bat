@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"

echo Starting CompressImgs...
echo URL: http://127.0.0.1:8000
echo.

"%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

if errorlevel 1 (
  echo.
  echo Start failed. Check Python environment and dependencies.
  pause
)
