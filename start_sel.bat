@echo off
REM SEL Bot Launcher for Windows - DOCKER ONLY
REM SEL requires Docker Desktop with WSL 2 backend
REM Native Windows execution is disabled for security

setlocal enabledelayedexpansion

echo ========================================
echo   SEL Bot - Docker Launcher
echo ========================================
echo.
echo SECURITY NOTICE:
echo SEL can ONLY run in Docker Desktop.
echo Native Windows execution is disabled.
echo.
echo ========================================
echo.

REM Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"

REM Check Docker installed
echo [1/3] Checking Docker Desktop...
docker --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Docker Desktop is not installed!
    echo.
    echo Please install Docker Desktop from:
    echo https://www.docker.com/products/docker-desktop
    echo.
    echo Enable WSL 2 backend during installation.
    echo.
    pause
    exit /b 1
)
echo OK - Docker found

REM Check Docker running
echo [2/3] Checking Docker status...
docker info >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Docker Desktop is not running!
    echo.
    echo Please start Docker Desktop:
    echo 1. Press Windows Key
    echo 2. Type 'Docker Desktop'
    echo 3. Launch Docker Desktop
    echo 4. Wait for whale icon in system tray
    echo 5. Run this script again
    echo.
    pause
    exit /b 1
)
echo OK - Docker running

REM Check .env file
echo [3/3] Checking configuration...
if not exist "%SCRIPT_DIR%.env" (
    echo.
    echo ERROR: .env file not found!
    echo.
    echo Please copy .env.example to .env and configure:
    echo - DISCORD_BOT_TOKEN
    echo - OPENROUTER_API_KEY
    echo.
    pause
    exit /b 1
)
echo OK - Configuration found

echo.
echo ========================================
echo   Starting SEL in Docker
echo ========================================
echo.

REM Change to script directory
cd /d "%SCRIPT_DIR%"

REM Start container
echo Starting SEL container...
docker-compose up -d

if errorlevel 1 (
    echo.
    echo ERROR: Failed to start container!
    echo.
    pause
    exit /b 1
)

echo.
echo SEL container started successfully!
echo.
echo Viewing logs (press Ctrl+C to exit)...
echo ========================================
echo.

REM Show logs
docker-compose logs -f sel-bot

echo.
echo ========================================
echo SEL is still running in background
echo.
echo Useful commands:
echo   docker-compose logs -f sel-bot  - View logs
echo   docker-compose down             - Stop SEL
echo   docker-compose restart sel-bot  - Restart SEL
echo.
pause
