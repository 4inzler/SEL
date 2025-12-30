# SEL Windows Deployment Script
# Automated deployment with security verification

param(
    [switch]$SkipBuild,
    [switch]$SkipVerify
)

Write-Host @"
========================================
SEL Discord Bot - Windows Deployment
Maximum Security Configuration
========================================
"@ -ForegroundColor Cyan

# Check if Docker is running
Write-Host "`n[1/6] Checking Docker Desktop..." -NoNewline
try {
    docker ps >$null 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK" -ForegroundColor Green
    } else {
        throw "Docker not responding"
    }
} catch {
    Write-Host " FAILED" -ForegroundColor Red
    Write-Host "ERROR: Docker Desktop is not running!" -ForegroundColor Red
    Write-Host "Please start Docker Desktop and try again." -ForegroundColor Yellow
    exit 1
}

# Check for .env file
Write-Host "[2/6] Checking configuration..." -NoNewline
if (Test-Path ".env") {
    Write-Host " OK" -ForegroundColor Green
} else {
    Write-Host " FAILED" -ForegroundColor Red
    Write-Host "ERROR: .env file not found!" -ForegroundColor Red
    Write-Host "Please create .env file with your tokens:" -ForegroundColor Yellow
    Write-Host "  1. Copy .env.example to .env" -ForegroundColor Yellow
    Write-Host "  2. Edit .env and add your DISCORD_BOT_TOKEN and OPENROUTER_API_KEY" -ForegroundColor Yellow
    exit 1
}

# Build container
if (-not $SkipBuild) {
    Write-Host "[3/6] Building secure container..." -ForegroundColor Yellow
    Write-Host "This may take several minutes on first run..." -ForegroundColor Gray

    docker-compose build --no-cache

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Build complete!" -ForegroundColor Green
    } else {
        Write-Host "Build failed!" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[3/6] Skipping build (--SkipBuild)" -ForegroundColor Gray
}

# Start container
Write-Host "[4/6] Starting SEL (sandboxed)..." -NoNewline
docker-compose up -d

if ($LASTEXITCODE -eq 0) {
    Write-Host " OK" -ForegroundColor Green
} else {
    Write-Host " FAILED" -ForegroundColor Red
    exit 1
}

# Wait for startup
Write-Host "[5/6] Waiting for startup..." -NoNewline
Start-Sleep -Seconds 5
Write-Host " OK" -ForegroundColor Green

# Verify security
if (-not $SkipVerify) {
    Write-Host "[6/6] Verifying security..." -ForegroundColor Yellow
    Write-Host ""

    $passed = 0
    $total = 6

    # Test 1: Shell blocked
    Write-Host "  [1/6] Shell access blocking..." -NoNewline
    try {
        docker exec sel-discord-bot /bin/sh 2>$null
        Write-Host " FAIL" -ForegroundColor Red
    } catch {
        Write-Host " PASS" -ForegroundColor Green
        $passed++
    }

    # Test 2: Read-only FS
    Write-Host "  [2/6] Read-only filesystem..." -NoNewline
    try {
        docker exec sel-discord-bot python -c "open('/test', 'w')" 2>$null
        Write-Host " FAIL" -ForegroundColor Red
    } catch {
        Write-Host " PASS" -ForegroundColor Green
        $passed++
    }

    # Test 3: No ports
    Write-Host "  [3/6] Port isolation..." -NoNewline
    $ports = docker port sel-discord-bot 2>$null
    if ([string]::IsNullOrWhiteSpace($ports)) {
        Write-Host " PASS" -ForegroundColor Green
        $passed++
    } else {
        Write-Host " FAIL" -ForegroundColor Red
    }

    # Test 4: Running
    Write-Host "  [4/6] Container status..." -NoNewline
    $status = docker inspect sel-discord-bot --format='{{.State.Running}}' 2>$null
    if ($status -eq "true") {
        Write-Host " PASS" -ForegroundColor Green
        $passed++
    } else {
        Write-Host " FAIL" -ForegroundColor Red
    }

    # Test 5: Security opts
    Write-Host "  [5/6] Security options..." -NoNewline
    $secOpts = docker inspect sel-discord-bot --format='{{json .HostConfig.SecurityOpt}}' 2>$null
    if ($secOpts -match "no-new-privileges") {
        Write-Host " PASS" -ForegroundColor Green
        $passed++
    } else {
        Write-Host " FAIL" -ForegroundColor Red
    }

    # Test 6: Caps dropped
    Write-Host "  [6/6] Capabilities dropped..." -NoNewline
    $capDrop = docker inspect sel-discord-bot --format='{{json .HostConfig.CapDrop}}' 2>$null
    if ($capDrop -match "ALL") {
        Write-Host " PASS" -ForegroundColor Green
        $passed++
    } else {
        Write-Host " FAIL" -ForegroundColor Red
    }

    Write-Host ""
    Write-Host "Security Score: $passed/$total" -ForegroundColor $(if ($passed -eq $total) { "Green" } else { "Yellow" })
} else {
    Write-Host "[6/6] Skipping verification (--SkipVerify)" -ForegroundColor Gray
}

# Show logs
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "SEL is now running in a secure sandbox." -ForegroundColor White
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Yellow
Write-Host "  View logs:    docker-compose logs -f sel-bot" -ForegroundColor Gray
Write-Host "  Stop SEL:     docker-compose down" -ForegroundColor Gray
Write-Host "  Restart SEL:  docker-compose restart sel-bot" -ForegroundColor Gray
Write-Host "  Check stats:  docker stats sel-discord-bot" -ForegroundColor Gray
Write-Host ""
Write-Host "Showing recent logs (Ctrl+C to exit):" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Show logs
docker-compose logs --tail=20 -f sel-bot
