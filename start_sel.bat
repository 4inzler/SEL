@echo off
REM SEL Bot Launcher for Windows
REM This script starts both the HIM service and the Discord bot

setlocal enabledelayedexpansion

echo ========================================
echo     SEL Bot - Windows Launcher
echo ========================================
echo.

REM Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%project_echo"

REM Check if project_echo exists
if not exist "%PROJECT_DIR%" (
    echo Error: project_echo directory not found at %PROJECT_DIR%
    echo Please run install_sel.ps1 first.
    pause
    exit /b 1
)

REM Check for .env file
if not exist "%SCRIPT_DIR%.env" (
    echo Error: .env file not found!
    echo Please copy .env.example to .env and configure your tokens.
    pause
    exit /b 1
)

REM Load .env file
echo Loading environment variables from .env...
for /f "usebackq tokens=1,* delims==" %%a in ("%SCRIPT_DIR%.env") do (
    set "line=%%a"
    REM Skip comments and empty lines
    if not "!line:~0,1!"=="#" if not "!line!"=="" (
        set "%%a=%%b"
    )
)

REM Verify critical env vars
if not defined DISCORD_BOT_TOKEN (
    echo Error: DISCORD_BOT_TOKEN not set in .env file
    pause
    exit /b 1
)

if not defined OPENROUTER_API_KEY (
    echo Error: OPENROUTER_API_KEY not set in .env file
    pause
    exit /b 1
)

REM Set defaults for optional variables
if not defined HIM_ENABLED set HIM_ENABLED=1
if not defined HIM_PORT set HIM_PORT=8000
if not defined DATABASE_URL set DATABASE_URL=sqlite+aiosqlite:///./sel.db

REM Create data directory if it doesn't exist
set "DATA_DIR=%PROJECT_DIR%\data"
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"

REM Set HIM data directories
if not defined HIM_DATA_DIR set HIM_DATA_DIR=%DATA_DIR%
if not defined HIM_MEMORY_DIR set HIM_MEMORY_DIR=%DATA_DIR%\him_store

REM Change to project directory
cd /d "%PROJECT_DIR%"

REM Check if Poetry is available
where poetry >nul 2>&1
if errorlevel 1 (
    echo Error: Poetry not found in PATH
    echo Please run install_sel.ps1 first or add Poetry to your PATH
    pause
    exit /b 1
)

echo.
echo Starting SEL Bot...
echo.
echo Data Directory: %DATA_DIR%
echo HIM Enabled: %HIM_ENABLED%
echo Database: %DATABASE_URL%
echo.

REM Start HIM service in background if enabled
if "%HIM_ENABLED%"=="1" (
    echo Starting HIM service on port %HIM_PORT%...
    start "SEL-HIM" /MIN poetry run python run_him.py --data-dir "%HIM_DATA_DIR%" --host 127.0.0.1 --port %HIM_PORT% --skip-hardware-checks
    
    REM Wait a moment for HIM to start
    timeout /t 3 /nobreak >nul
    echo HIM service started in background window
    echo.
)

REM Start Discord bot (foreground)
echo Starting SEL Discord bot...
echo Press Ctrl+C to stop
echo.
poetry run python -m sel_bot.main

REM Cleanup on exit
echo.
echo Shutting down...

REM Try to close the HIM service window
if "%HIM_ENABLED%"=="1" (
    taskkill /FI "WINDOWTITLE eq SEL-HIM*" /T /F >nul 2>&1
)

echo SEL Bot stopped.
pause
