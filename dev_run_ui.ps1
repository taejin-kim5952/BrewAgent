# Streamlit UI 개발 서버 (포트 8501)
# 백엔드 FastAPI(:8000) 가 먼저 실행되어 있어야 함 (dev_run.ps1)

$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot

$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

$venvPy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

# 로그 폴더: 프로젝트 밖 + 한글 없는 경로 (D:\LOG)
$logDir = 'D:\LOG'
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$logName = 'streamlit_{0:yyyyMMdd-HHmmss}.log' -f (Get-Date)
$logPath = Join-Path $logDir $logName

if (-not (Test-Path $venvPy)) {
    Write-Host '[ui] ERROR: .venv missing. Run dev_start.bat first.'
    exit 1
}

try {
    cmd /c 'chcp 65001>nul' | Out-Null
} catch {}
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {}

Write-Host ''
Write-Host '================================================'
Write-Host '  Streamlit UI on  http://localhost:8501'
Write-Host '  (Backend FastAPI must be running on :8000)'
Write-Host "  Log file: $logPath"
Write-Host '================================================'
Write-Host ''

$cmdLine = "chcp 65001>nul && `"$venvPy`" -m streamlit run ui/home.py --server.port 8501 --server.headless true --browser.gatherUsageStats false 2>&1"
cmd /c $cmdLine | Tee-Object -FilePath $logPath
