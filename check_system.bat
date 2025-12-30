@echo off
REM SEL System Check - Verifies Windows system is ready to run SEL
REM Run this before installing to check prerequisites

echo ========================================
echo     SEL System Requirements Check
echo ========================================
echo.

set PASS=0
set FAIL=0

REM Check Windows version
echo [1/5] Checking Windows version...
ver | findstr /i "Windows" >nul
if %errorlevel% equ 0 (
    echo [OK] Windows detected
    set /a PASS+=1
) else (
    echo [WARN] Could not detect Windows version
    set /a FAIL+=1
)
echo.

REM Check Python installation
echo [2/5] Checking Python installation...
where python >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
    echo [OK] Python found: !PYTHON_VER!
    
    REM Check Python version is 3.11+
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>nul
    if !errorlevel! equ 0 (
        echo [OK] Python version is 3.11 or higher
        set /a PASS+=1
    ) else (
        echo [FAIL] Python 3.11+ required, found: !PYTHON_VER!
        echo       Download from: https://www.python.org/downloads/
        set /a FAIL+=1
    )
) else (
    echo [FAIL] Python not found in PATH
    echo       Download from: https://www.python.org/downloads/
    echo       Make sure to check 'Add Python to PATH' during installation
    set /a FAIL+=1
)
echo.

REM Check Poetry installation
echo [3/5] Checking Poetry installation...
where poetry >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%i in ('poetry --version 2^>^&1') do set POETRY_VER=%%i
    echo [OK] Poetry found: !POETRY_VER!
    set /a PASS+=1
) else (
    echo [INFO] Poetry not installed (will be installed automatically)
    set /a PASS+=1
)
echo.

REM Check for .env file
echo [4/5] Checking configuration file...
if exist .env (
    echo [OK] .env file exists
    
    REM Check for required tokens
    findstr /C:"DISCORD_BOT_TOKEN" .env | findstr /V /C:"DISCORD_BOT_TOKEN=your" >nul
    if !errorlevel! equ 0 (
        echo [OK] DISCORD_BOT_TOKEN appears to be configured
    ) else (
        echo [WARN] DISCORD_BOT_TOKEN not configured in .env
        set /a FAIL+=1
    )
    
    findstr /C:"OPENROUTER_API_KEY" .env | findstr /V /C:"OPENROUTER_API_KEY=your" >nul
    if !errorlevel! equ 0 (
        echo [OK] OPENROUTER_API_KEY appears to be configured
        set /a PASS+=1
    ) else (
        echo [WARN] OPENROUTER_API_KEY not configured in .env
        set /a FAIL+=1
    )
) else (
    echo [INFO] .env file not found (will be created from template)
    set /a PASS+=1
)
echo.

REM Check for project_echo directory
echo [5/5] Checking project files...
if exist project_echo (
    echo [OK] project_echo directory found
    
    if exist project_echo\sel_bot (
        echo [OK] sel_bot module found
    ) else (
        echo [FAIL] sel_bot module not found
        set /a FAIL+=1
    )
    
    if exist project_echo\him (
        echo [OK] him module found
    ) else (
        echo [FAIL] him module not found
        set /a FAIL+=1
    )
    
    if exist project_echo\pyproject.toml (
        echo [OK] pyproject.toml found
        set /a PASS+=1
    ) else (
        echo [FAIL] pyproject.toml not found
        set /a FAIL+=1
    )
) else (
    echo [FAIL] project_echo directory not found
    echo       Make sure you're running this from the SEL repository root
    set /a FAIL+=1
)
echo.

REM Check disk space
echo [BONUS] Checking disk space...
for /f "tokens=3" %%a in ('dir /-c ^| findstr /C:"bytes free"') do set SPACE=%%a
if defined SPACE (
    echo [INFO] Free disk space: %SPACE% bytes
    echo       (SEL requires ~500MB for installation)
) else (
    echo [INFO] Could not determine disk space
)
echo.

REM Summary
echo ========================================
echo           Summary
echo ========================================
echo.
echo Tests passed: %PASS%
echo Tests failed: %FAIL%
echo.

if %FAIL% gtr 0 (
    echo [ACTION REQUIRED] Please fix the failed checks above before installing SEL.
    echo.
    echo Common fixes:
    echo - Install Python 3.11+ from https://www.python.org/downloads/
    echo - Make sure "Add Python to PATH" is checked during installation
    echo - Configure .env file with your Discord and OpenRouter tokens
    echo.
    echo For detailed help, see WINDOWS_SETUP.md
) else (
    echo [READY] Your system is ready to run SEL!
    echo.
    echo Next steps:
    if not exist .env (
        echo 1. Run install_sel.ps1 to set up dependencies
        echo 2. Edit .env with your tokens
        echo 3. Run start_sel.bat to launch SEL
    ) else (
        echo 1. Run start_sel.bat to launch SEL
        echo    (or run install_sel.ps1 if you haven't installed dependencies yet^)
    )
)

echo.
echo ========================================
pause
