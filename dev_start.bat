@echo off
title RAG Platform (dev)
cd /d "%~dp0"
chcp 65001 >nul

set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "VENVPY=%~dp0.venv\Scripts\python.exe"

echo.
echo [STEP 1] Working dir: %CD%

if not exist "%VENVPY%" (
    echo [ERROR] .venv not found at: %VENVPY%
    echo Run setup.bat first, or recreate venv.
    pause
    exit /b 1
)
echo [STEP 2] venv OK

REM --- Ollama check (skip if already running) ---
tasklist /fi "imagename eq ollama.exe" 2>nul | find /i "ollama.exe" >nul
if errorlevel 1 (
    echo [STEP 3] Ollama not running, starting...
    start /b ollama serve
    timeout /t 3 /nobreak >nul
) else (
    echo [STEP 3] Ollama already running
)

echo.
echo  Backend API : http://localhost:8000/docs
echo  Web UI      : http://localhost:8501/
echo.

REM --- Start backend in new window ---
echo [STEP 4] Starting backend window...
start "RAG Backend (port 8000)" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev_run.ps1"

REM Wait for backend
timeout /t 5 /nobreak >nul

REM --- Start Streamlit UI in new window ---
echo [STEP 5] Starting Streamlit UI window...
start "RAG Streamlit UI (port 8501)" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev_run_ui.ps1"

REM Wait for UI then open browser
timeout /t 4 /nobreak >nul
echo [STEP 6] Opening browser...
start "" "http://localhost:8501/"

echo.
echo [DONE] Two server windows opened.
echo Browser auto-opens at http://localhost:8501/
echo.
echo Press any key to close this launcher window...
pause >nul
endlocal
