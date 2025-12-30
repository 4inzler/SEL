@echo off
REM Quick launcher for vector database diagnostics
REM Double-click this file to run the diagnostic check

echo.
echo ========================================
echo   SEL BOT DIAGNOSTIC - QUICK START
echo ========================================
echo.
echo This will check if your vector database
echo is poisoned with HTML/JavaScript from
echo the pentest attacks.
echo.
echo Press any key to start...
pause >nul

REM Try PowerShell first (better formatting)
echo.
echo Running diagnostics...
echo.

powershell -ExecutionPolicy Bypass -File "C:\Users\Public\run_diagnostics.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo PowerShell failed, trying Python directly...
    echo.

    REM Fallback to direct Python
    cd C:\Users\Public
    python vector_store_diagnostics.py
)

echo.
echo ========================================
echo   DIAGNOSTIC COMPLETE
echo ========================================
echo.
echo Next steps in: PENTEST_RESPONSE_PLAN.md
echo.
pause
