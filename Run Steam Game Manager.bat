@echo off
setlocal

set "PROJECT_DIR=%~dp0"

powershell -NoExit -ExecutionPolicy Bypass -Command "& { Set-Location -LiteralPath $env:PROJECT_DIR; if (Get-Command py -ErrorAction SilentlyContinue) { py '.\main.py' } elseif (Get-Command python -ErrorAction SilentlyContinue) { python '.\main.py' } else { Write-Host 'Python was not found in PATH.' -ForegroundColor Red } }"

endlocal
