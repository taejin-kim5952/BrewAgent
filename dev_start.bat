@echo off
setlocal
title RAG Platform (dev)
cd /d "%~dp0"
chcp 65001 >nul

set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

set "VENVPY=%~dp0.venv\Scripts\python.exe"

py -3 --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PY=py -3"
) else (
    set "PY=python"
)

if not exist "%VENVPY%" (
    echo [dev] Creating .venv and installing packages (first run only^)...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [dev] ERROR: venv creation failed
        pause
        exit /b 1
    )
    "%VENVPY%" -m pip install --upgrade pip >nul
    "%VENVPY%" -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 (
        echo [dev] ERROR: pip install failed
        pause
        exit /b 1
    )
) else (
    "%VENVPY%" -c "import uvicorn" 2>nul
    if errorlevel 1 (
        echo [dev] Dependencies incomplete ^(e.g. uvicorn missing^) - running pip install...
        "%VENVPY%" -m pip install -r "%~dp0requirements.txt"
        if errorlevel 1 (
            echo [dev] ERROR: pip install failed
            pause
            exit /b 1
        )
    )
)

tasklist /fi "imagename eq ollama.exe" 2>nul | find /i "ollama.exe" >nul
if errorlevel 1 (
    echo [dev] Ollama not running - starting in background...
    start /b ollama serve
    timeout /t 3 /nobreak >nul
)

echo.
echo Working directory: %CD%
echo Admin UI: http://localhost:8000/
echo API docs: http://localhost:8000/docs
echo Log file: %CD%\dev_server_YYYYMMDD-hhmmss.log ^(new file each run^)
echo Stop: Ctrl+C
echo.

timeout /t 2 /nobreak >nul
start "" "http://localhost:8000/"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev_run.ps1"

pause
endlocal
