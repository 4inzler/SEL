@echo off
REM Build script for Windows executable
REM Run this in Command Prompt or PowerShell on Windows

echo === Building SEL Windows Executable ===
echo.

REM Check if Python is available
where python >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found in PATH
    echo Please install Python 3.11+ and add it to PATH
    pause
    exit /b 1
)

REM Check if PyInstaller is installed
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller
        pause
        exit /b 1
    )
)

REM Build the executable
echo.
echo Building executable with PyInstaller...
echo This may take a few minutes...
echo.
pyinstaller sel_windows.spec

if errorlevel 1 (
    echo.
    echo Build failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build complete!
echo ========================================
echo.
echo Executable location: dist\sel_launcher.exe
echo.
echo To distribute:
echo 1. Copy dist\sel_launcher.exe to your SEL repository root
echo 2. Include the entire project_echo\ directory
echo 3. Include .env.example
echo 4. Include WINDOWS_SETUP.md
echo.
echo Users can then run sel_launcher.exe to install and start SEL.
echo.
pause
