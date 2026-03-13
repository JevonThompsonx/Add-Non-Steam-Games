@echo off
setlocal enableextensions enabledelayedexpansion

set "me=%~n0"
set "PROJECT_DIR=%~dp0"
set "EXIT_CODE=1"

pushd "%PROJECT_DIR%" >nul 2>&1 || (
    echo [%me%] Failed to open project directory: "%PROJECT_DIR%"
    pause
    endlocal & exit /b 1
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    py ".\main.py"
    set "EXIT_CODE=!errorlevel!"
) else (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        python ".\main.py"
        set "EXIT_CODE=!errorlevel!"
    ) else (
        echo Python was not found in PATH.
        set "EXIT_CODE=1"
    )
)

popd >nul 2>&1

if not "!EXIT_CODE!"=="0" (
    echo.
    echo [%me%] Exited with code !EXIT_CODE!.
    pause
)

endlocal & exit /b %EXIT_CODE%
