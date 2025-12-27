# SEL Bot Windows Installer
# Installs Python, Poetry, and project dependencies for Windows

param(
    [string]$PythonVersion = "3.11"
)

$ErrorActionPreference = "Stop"

Write-Host "=== SEL Bot Windows Installer ===" -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Warning: Not running as Administrator. Some installations may require elevation." -ForegroundColor Yellow
}

# Function to check if a command exists
function Test-Command {
    param($CommandName)
    $null -ne (Get-Command $CommandName -ErrorAction SilentlyContinue)
}

# Check and install Python
Write-Host "Checking Python installation..." -ForegroundColor Green
if (Test-Command python) {
    $pythonVer = python --version 2>&1
    Write-Host "Found: $pythonVer" -ForegroundColor Cyan
    
    # Extract version number
    if ($pythonVer -match "Python (\d+)\.(\d+)") {
        $major = [int]$matches[1]
        $minor = [int]$matches[2]
        
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
            Write-Host "Python 3.11+ is required. Current version is too old." -ForegroundColor Red
            Write-Host "Please install Python 3.11+ from: https://www.python.org/downloads/" -ForegroundColor Yellow
            exit 1
        }
    }
} else {
    Write-Host "Python not found. Please install Python 3.11+ from:" -ForegroundColor Red
    Write-Host "https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Make sure to check 'Add Python to PATH' during installation!" -ForegroundColor Yellow
    exit 1
}

# Check and install Poetry
Write-Host ""
Write-Host "Checking Poetry installation..." -ForegroundColor Green
if (Test-Command poetry) {
    $poetryVer = poetry --version 2>&1
    Write-Host "Found: $poetryVer" -ForegroundColor Cyan
} else {
    Write-Host "Poetry not found. Installing Poetry..." -ForegroundColor Yellow
    
    try {
        (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
        
        # Add Poetry to PATH for current session
        $poetryPath = "$env:APPDATA\Python\Scripts"
        if (Test-Path $poetryPath) {
            $env:Path += ";$poetryPath"
            Write-Host "Poetry installed successfully!" -ForegroundColor Green
        } else {
            Write-Host "Poetry installation completed, but path not found. You may need to restart your terminal." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Failed to install Poetry automatically." -ForegroundColor Red
        Write-Host "Please install manually: https://python-poetry.org/docs/#installation" -ForegroundColor Yellow
        exit 1
    }
}

# Navigate to project_echo directory
Write-Host ""
Write-Host "Setting up project dependencies..." -ForegroundColor Green
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Join-Path $scriptDir "project_echo"

if (-not (Test-Path $projectDir)) {
    Write-Host "Error: project_echo directory not found at $projectDir" -ForegroundColor Red
    exit 1
}

Set-Location $projectDir

# Configure Poetry to create virtual environment in project directory
poetry config virtualenvs.in-project true

# Install dependencies
Write-Host "Installing Python dependencies (this may take a few minutes)..." -ForegroundColor Yellow
try {
    poetry install
    Write-Host "Dependencies installed successfully!" -ForegroundColor Green
} catch {
    Write-Host "Failed to install dependencies. Error: $_" -ForegroundColor Red
    exit 1
}

# Create data directory
$dataDir = Join-Path $projectDir "data"
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir | Out-Null
    Write-Host "Created data directory at: $dataDir" -ForegroundColor Cyan
}

# Create .env file if it doesn't exist
$envFile = Join-Path $scriptDir ".env"
$envExample = Join-Path $scriptDir ".env.example"

if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-Host ""
        Write-Host "Created .env file from template." -ForegroundColor Green
        Write-Host "IMPORTANT: Edit .env and add your DISCORD_BOT_TOKEN and OPENROUTER_API_KEY" -ForegroundColor Yellow
    } else {
        Write-Host ""
        Write-Host "Warning: No .env.example found. You'll need to create .env manually." -ForegroundColor Yellow
    }
}

# Run hardware profile check
Write-Host ""
Write-Host "Running hardware profile check..." -ForegroundColor Green
try {
    $env:HIM_DATA_DIR = $dataDir
    poetry run python run_him.py --profile-only --data-dir $dataDir
} catch {
    Write-Host "Warning: Hardware profile check failed, but installation may still work." -ForegroundColor Yellow
}

# Installation complete
Write-Host ""
Write-Host "=== Installation Complete! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Edit .env file with your Discord bot token and OpenRouter API key" -ForegroundColor White
Write-Host "2. Run 'start_sel.bat' to launch SEL" -ForegroundColor White
Write-Host ""
Write-Host "For more information, see WINDOWS_SETUP.md" -ForegroundColor Cyan
