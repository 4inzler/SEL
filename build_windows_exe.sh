#!/usr/bin/env bash
# Build script for Windows executable
# Run this on a Windows machine or in a Windows VM

set -euo pipefail

echo "=== Building SEL Windows Executable ==="
echo ""

# Check if PyInstaller is installed
if ! command -v pyinstaller >/dev/null 2>&1; then
    echo "PyInstaller not found. Installing..."
    pip install pyinstaller
fi

# Build the executable
echo "Building executable with PyInstaller..."
pyinstaller sel_windows.spec

echo ""
echo "Build complete!"
echo "Executable location: dist/sel_launcher.exe"
echo ""
echo "To distribute:"
echo "1. Copy dist/sel_launcher.exe to your SEL repository root"
echo "2. Include the entire project_echo/ directory"
echo "3. Include .env.example"
echo "4. Include WINDOWS_SETUP.md"
echo ""
echo "Users can then run sel_launcher.exe to install and start SEL."
