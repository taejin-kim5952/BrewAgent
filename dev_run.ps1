# Dev server: console + timestamped log file.
# Uvicorn/loguru write INFO to stderr; PowerShell 5.x treats piped native stderr as ErrorRecord
# (red NativeCommandError). Running through cmd merges 2>&1 so lines stay plain text.

$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot

$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

$venvPy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$logName = 'dev_server_{0:yyyyMMdd-HHmmss}.log' -f (Get-Date)
$logPath = Join-Path $PSScriptRoot $logName

if (-not (Test-Path $venvPy)) {
    Write-Host '[dev] ERROR: .venv missing. Run dev_start.bat again.'
    exit 1
}

try {
    cmd /c 'chcp 65001>nul' | Out-Null
} catch {}
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $OutputEncoding = [Console]::OutputEncoding
} catch {}

Write-Host ''
Write-Host "Log file: $logPath"
Write-Host ''

# cmd merges Python stderr into stdout so Tee-Object gets normal strings
$cmdLine = "chcp 65001>nul && `"$venvPy`" -m uvicorn rag.server.main:app --host 0.0.0.0 --port 8000 --reload 2>&1"
cmd /c $cmdLine | Tee-Object -FilePath $logPath
