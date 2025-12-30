@echo off
echo ========================================
echo SEL Wordle Test
echo ========================================
echo.
echo This will start SEL Desktop Assistant.
echo When prompted:
echo   1. Select mode: 1
echo   2. Type: complete a wordle
echo.
echo Press any key to start...
pause >nul

cd "%~dp0"
py sel_desktop.py

pause
