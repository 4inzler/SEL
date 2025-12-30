# Build SEL Windows Launcher
# Creates sel_launcher.exe with Docker Desktop enforcement

Write-Host @"
========================================
SEL Launcher Builder
Building Docker-enforced Windows launcher
========================================
"@ -ForegroundColor Cyan

Write-Host ""

# Check Python
Write-Host "[1/4] Checking Python..." -NoNewline
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK" -ForegroundColor Green
        Write-Host "      $pythonVersion" -ForegroundColor Gray
    } else {
        throw "Python not found"
    }
} catch {
    Write-Host " FAILED" -ForegroundColor Red
    Write-Host ""
    Write-Host "ERROR: Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Install from: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

# Check/Install PyInstaller
Write-Host "[2/4] Checking PyInstaller..." -NoNewline
$hasInstaller = $false
try {
    pyinstaller --version >$null 2>&1
    if ($LASTEXITCODE -eq 0) {
        $hasInstaller = $true
        Write-Host " OK" -ForegroundColor Green
    }
} catch {}

if (-not $hasInstaller) {
    Write-Host " NOT FOUND" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Installing PyInstaller..." -ForegroundColor Cyan
    python -m pip install pyinstaller

    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to install PyInstaller" -ForegroundColor Red
        exit 1
    }
    Write-Host "PyInstaller installed successfully!" -ForegroundColor Green
}

# Clean old builds
Write-Host "[3/4] Cleaning old builds..." -NoNewline
if (Test-Path "build") {
    Remove-Item -Recurse -Force "build"
}
if (Test-Path "dist") {
    Remove-Item -Recurse -Force "dist"
}
if (Test-Path "sel_launcher.spec") {
    Remove-Item -Force "sel_launcher.spec"
}
Write-Host " OK" -ForegroundColor Green

# Build executable
Write-Host "[4/4] Building launcher..." -ForegroundColor Yellow
Write-Host ""
Write-Host "This may take a minute..." -ForegroundColor Gray
Write-Host ""

pyinstaller --onefile `
    --name sel_launcher `
    --console `
    --clean `
    windows_launcher.py

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Build failed!" -ForegroundColor Red
    exit 1
}

# Copy to root
Write-Host ""
Write-Host "Copying executable..." -NoNewline
if (Test-Path "dist\sel_launcher.exe") {
    Copy-Item "dist\sel_launcher.exe" "sel_launcher.exe" -Force
    Write-Host " OK" -ForegroundColor Green
} else {
    Write-Host " FAILED" -ForegroundColor Red
    Write-Host "Executable not found in dist folder" -ForegroundColor Red
    exit 1
}

# Get file size
$exeSize = (Get-Item "sel_launcher.exe").Length / 1MB

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Launcher created: sel_launcher.exe" -ForegroundColor White
Write-Host "Size: $([math]::Round($exeSize, 2)) MB" -ForegroundColor Gray
Write-Host ""
Write-Host "This launcher enforces:" -ForegroundColor Cyan
Write-Host "  ✓ Docker Desktop installation" -ForegroundColor White
Write-Host "  ✓ Docker Desktop running" -ForegroundColor White
Write-Host "  ✓ WSL 2 backend enabled" -ForegroundColor White
Write-Host "  ✓ Docker Compose available" -ForegroundColor White
Write-Host "  ✓ .env configuration" -ForegroundColor White
Write-Host ""
Write-Host "Native Windows execution is DISABLED." -ForegroundColor Yellow
Write-Host "SEL can ONLY run in Docker Desktop." -ForegroundColor Yellow
Write-Host ""
Write-Host "To test the launcher, run: sel_launcher.exe" -ForegroundColor Cyan
Write-Host ""
