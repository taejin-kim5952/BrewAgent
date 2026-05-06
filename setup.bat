@echo off
setlocal enabledelayedexpansion

title RAG Platform Installer
set "LOG=C:\rag_install.log"

echo RAG Platform Installer > "%LOG%"
echo Started: %DATE% %TIME% >> "%LOG%"
echo ---------------------------------------- >> "%LOG%"

echo.
echo  ============================================================
echo   RAG Platform Installer
echo  ============================================================
echo.
echo  Log file: %LOG%
echo.

:: [1] Admin
echo [1/10] Checking admin...
echo [1/10] Checking admin... >> "%LOG%"
net session >nul 2>&1
if errorlevel 1 (
    echo  [FAIL] Run as administrator. >> "%LOG%"
    echo  [FAIL] Right-click setup.bat - Run as administrator
    start notepad "%LOG%"
    pause
    exit /b 1
)
echo  [OK] Admin >> "%LOG%"
echo  [OK] Admin

:: [2] Python  (py -3 우선: Microsoft Store "python" 별칭/오탐 방지)
echo.
echo [2/10] Checking Python...
echo [2/10] Checking Python... >> "%LOG%"
set "PYFORVENV="
set "PYVER="
py -3 --version >>"%LOG%" 2>&1
if %errorlevel% equ 0 (
    set "PYFORVENV=py -3"
    for /f "delims=" %%v in ('py -3 -c "import platform;print(platform.python_version())" 2^>nul') do set "PYVER=%%v"
    goto :py_ok
)
python --version >>"%LOG%" 2>&1
if errorlevel 1 (
    echo  [FAIL] Python not found (py -3 / python both missing). >> "%LOG%"
    echo  [FAIL] Install Python 3.10+ from python.org — enable "Add python.exe to PATH"
    echo  [FAIL] Or install "Python Launcher" and retry. Log: %LOG%
    start notepad "%LOG%"
    start https://www.python.org/downloads/
    pause
    exit /b 1
)
set "PYFORVENV=python"
for /f "delims=" %%v in ('python -c "import platform;print(platform.python_version())" 2^>nul') do set "PYVER=%%v"
:py_ok
if not defined PYVER set "PYVER=?"
echo  [OK] Python !PYVER! ^(!PYFORVENV!^) >> "%LOG%"
echo  [OK] Python !PYVER! ^(!PYFORVENV!^)

:: [3] Ollama
echo.
echo [3/10] Checking Ollama...
echo [3/10] Checking Ollama... >> "%LOG%"
where ollama >nul 2>&1
if errorlevel 1 (
    echo  [i] Ollama not found. Downloading... >> "%LOG%"
    echo  [i] Downloading Ollama...
    set "OLL=%TEMP%\OllamaSetup.exe"
    powershell -Command "Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' -OutFile '!OLL!' -UseBasicParsing"
    if !errorLevel! neq 0 (
        echo  [FAIL] Download failed. >> "%LOG%"
        start notepad "%LOG%"
        pause
        exit /b 1
    )
    "!OLL!" /S
    timeout /t 5 /nobreak >nul
    where ollama >nul 2>&1
    if !errorLevel! neq 0 (
        echo  [FAIL] Ollama PATH not updated. Restart and re-run. >> "%LOG%"
        start notepad "%LOG%"
        pause
        exit /b 1
    )
)
echo  [OK] Ollama >> "%LOG%"
echo  [OK] Ollama

:: [4] Install path
echo.
echo [4/10] Install path
set "DEFAULT=C:\RAGPlatform"
set /p IDIR="  Path [default: %DEFAULT%]: "
if "!IDIR!"=="" set "IDIR=%DEFAULT%"
echo  Path: !IDIR! >> "%LOG%"
echo  Path: !IDIR!
set /p OK="  Proceed? Y/N [Y]: "
if /i "!OK!"=="N" (
    echo  Cancelled >> "%LOG%"
    start notepad "%LOG%"
    pause
    exit /b 0
)

:: [5] Copy files
echo.
echo [5/10] Copying files...
echo [5/10] Copying files... >> "%LOG%"
if not exist "!IDIR!" mkdir "!IDIR!"
xcopy /E /I /Y /Q "%~dp0rag" "!IDIR!\rag" >nul 2>> "%LOG%"
if errorlevel 1 (
    echo  [FAIL] xcopy failed >> "%LOG%"
    start notepad "%LOG%"
    pause
    exit /b 1
)
copy /Y "%~dp0requirements.txt" "!IDIR!\" >nul
echo  [OK] Files copied >> "%LOG%"
echo  [OK] Files copied

:: [6] Virtual env
echo.
echo [6/10] Creating venv...
echo [6/10] Creating venv... >> "%LOG%"
if exist "!IDIR!\venv" (
    echo  [i] Reusing existing venv >> "%LOG%"
    echo  [i] Reusing existing venv
) else (
    !PYFORVENV! -m venv "!IDIR!\venv" >> "%LOG%" 2>&1
    if !errorLevel! neq 0 (
        echo  [FAIL] venv creation failed >> "%LOG%"
        start notepad "%LOG%"
        pause
        exit /b 1
    )
)
echo  [OK] venv ready >> "%LOG%"
echo  [OK] venv ready

:: [7] pip install
echo.
echo [7/10] Installing packages (may take several minutes)...
echo [7/10] Installing packages... >> "%LOG%"
"!IDIR!\venv\Scripts\python.exe" -m pip install --upgrade pip >> "%LOG%" 2>&1
"!IDIR!\venv\Scripts\python.exe" -m pip install -r "!IDIR!\requirements.txt" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo  [FAIL] pip install failed - see log >> "%LOG%"
    echo  [FAIL] pip install failed. Opening log...
    start notepad "%LOG%"
    pause
    exit /b 1
)
echo  [OK] Packages installed >> "%LOG%"
echo  [OK] Packages installed

:: [8] Tesseract (optional)
echo.
echo [8/10] Checking Tesseract...
echo [8/10] Checking Tesseract... >> "%LOG%"
where tesseract >nul 2>&1
if errorlevel 1 (
    echo  [i] Tesseract not found (optional) >> "%LOG%"
    echo  [i] Tesseract not found (optional - image OCR)
) else (
    echo  [OK] Tesseract >> "%LOG%"
    echo  [OK] Tesseract
)

:: [9] Model
echo.
echo [9/10] Download AI model
echo  [1] gemma3:4b  ~3GB  (Recommended)
echo  [2] gemma3:12b ~8GB
echo  [3] Both
echo  [4] Skip
set /p MC="  Choice [1]: "
if "!MC!"=="" set MC=1
echo  Model choice: !MC! >> "%LOG%"

start /b ollama serve
timeout /t 3 /nobreak >nul

if "!MC!"=="1" (
    echo  Downloading gemma3:4b... >> "%LOG%"
    ollama pull gemma3:4b
    echo  [OK] gemma3:4b >> "%LOG%"
) else if "!MC!"=="2" (
    echo  Downloading gemma3:12b... >> "%LOG%"
    ollama pull gemma3:12b
    echo  [OK] gemma3:12b >> "%LOG%"
) else if "!MC!"=="3" (
    ollama pull gemma3:4b
    ollama pull gemma3:12b
    echo  [OK] Both models >> "%LOG%"
) else (
    echo  [i] Skipped model download >> "%LOG%"
    echo  [i] Skipped
)

:: [10] Shortcuts + config
echo.
echo [10/10] Creating shortcuts...
echo [10/10] Creating shortcuts... >> "%LOG%"

mkdir "!IDIR!\storage\indices" 2>nul
mkdir "!IDIR!\storage\exports" 2>nul

if not exist "!IDIR!\platform\configs\local.yaml" (
    echo # local overrides > "!IDIR!\platform\configs\local.yaml"
)

:: start.bat
(
echo @echo off
echo title RAG Platform
echo echo Starting...
echo tasklist /fi "imagename eq ollama.exe" 2^>nul ^| find /i "ollama.exe" ^>nul
echo if errorlevel 1 ^( start /b ollama serve ^& timeout /t 3 /nobreak ^>nul ^)
echo set PYTHONIOENCODING=utf-8
echo set PYTHONUTF8=1
echo call "!IDIR!\venv\Scripts\activate.bat"
echo cd /d "!IDIR!"
echo echo Server : http://localhost:8000
echo echo Docs   : http://localhost:8000/docs
echo echo Press Ctrl+C to stop.
echo start "" "http://localhost:8000/docs"
echo python -m uvicorn rag.server.main:app --host 0.0.0.0 --port 8000 --reload
echo pause
) > "!IDIR!\start.bat"

:: stop.bat
(
echo @echo off
echo taskkill /f /im uvicorn.exe 2^>nul
echo echo Stopped.
echo pause
) > "!IDIR!\stop.bat"

:: Desktop shortcut via Python
echo import winreg > "%TEMP%\gd.py"
echo k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders') >> "%TEMP%\gd.py"
echo print(winreg.QueryValueEx(k, 'Desktop')[0]) >> "%TEMP%\gd.py"
for /f "delims=" %%D in ('!PYFORVENV! "%TEMP%\gd.py" 2^>nul') do set "DESKPATH=%%D"
del "%TEMP%\gd.py" 2>nul

echo Desktop: !DESKPATH! >> "%LOG%"

if defined DESKPATH (
    (
        echo @echo off
        echo call "!IDIR!\start.bat"
    ) > "!DESKPATH!\RAG Platform.bat"
    echo  [OK] Desktop: !DESKPATH!\RAG Platform.bat >> "%LOG%"
    echo  [OK] Desktop shortcut created
) else (
    echo  [i] Desktop path not found >> "%LOG%"
    echo  [i] Could not create desktop shortcut
)

:: Done
echo ---------------------------------------- >> "%LOG%"
echo INSTALL COMPLETE >> "%LOG%"
echo Install dir: !IDIR! >> "%LOG%"
echo Finished: %DATE% %TIME% >> "%LOG%"

echo.
echo  ============================================================
echo   DONE!  Install path: !IDIR!
echo   Log saved to: %LOG%
echo  ============================================================
echo.
echo  Opening log in Notepad...
start notepad "%LOG%"
echo.
pause
endlocal
