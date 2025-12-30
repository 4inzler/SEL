# SEL Security Verification Script for Windows
# Comprehensive security testing

Write-Host @"
========================================
SEL Security Verification
Testing Maximum Security Configuration
========================================
"@ -ForegroundColor Cyan

Write-Host ""

$tests = @()
$details = @()

# Test 1: Shell access blocked
Write-Host "[1/10] Shell access blocking..." -NoNewline
try {
    $result = docker exec sel-discord-bot /bin/sh 2>&1
    Write-Host " FAIL" -ForegroundColor Red
    $tests += $false
    $details += "Shell access NOT blocked - CRITICAL VULNERABILITY"
} catch {
    Write-Host " PASS" -ForegroundColor Green
    $tests += $true
    $details += "Shell binaries removed successfully"
}

# Test 2: Read-only filesystem
Write-Host "[2/10] Read-only filesystem..." -NoNewline
try {
    docker exec sel-discord-bot python -c "open('/test', 'w')" 2>$null
    Write-Host " FAIL" -ForegroundColor Red
    $tests += $false
    $details += "Filesystem is writable - SECURITY ISSUE"
} catch {
    Write-Host " PASS" -ForegroundColor Green
    $tests += $true
    $details += "Root filesystem is read-only"
}

# Test 3: No ports exposed
Write-Host "[3/10] Port isolation..." -NoNewline
$ports = docker port sel-discord-bot 2>$null
if ([string]::IsNullOrWhiteSpace($ports)) {
    Write-Host " PASS" -ForegroundColor Green
    $tests += $true
    $details += "No ports exposed to host"
} else {
    Write-Host " FAIL" -ForegroundColor Red
    $tests += $false
    $details += "Ports exposed: $ports - SECURITY ISSUE"
}

# Test 4: Container running
Write-Host "[4/10] Container status..." -NoNewline
$status = docker inspect sel-discord-bot --format='{{.State.Running}}' 2>$null
if ($status -eq "true") {
    Write-Host " PASS" -ForegroundColor Green
    $tests += $true
    $details += "Container is running"
} else {
    Write-Host " FAIL" -ForegroundColor Red
    $tests += $false
    $details += "Container not running - check logs"
}

# Test 5: Security options
Write-Host "[5/10] Security options..." -NoNewline
$secOpts = docker inspect sel-discord-bot --format='{{json .HostConfig.SecurityOpt}}' 2>$null | ConvertFrom-Json
if ($secOpts -contains "no-new-privileges:true") {
    Write-Host " PASS" -ForegroundColor Green
    $tests += $true
    $details += "no-new-privileges enabled"
} else {
    Write-Host " FAIL" -ForegroundColor Red
    $tests += $false
    $details += "no-new-privileges NOT enabled - SECURITY ISSUE"
}

# Test 6: All capabilities dropped
Write-Host "[6/10] Capabilities..." -NoNewline
$capDrop = docker inspect sel-discord-bot --format='{{json .HostConfig.CapDrop}}' 2>$null | ConvertFrom-Json
if ($capDrop -contains "ALL") {
    Write-Host " PASS" -ForegroundColor Green
    $tests += $true
    $details += "All Linux capabilities dropped"
} else {
    Write-Host " FAIL" -ForegroundColor Red
    $tests += $false
    $details += "Not all capabilities dropped - SECURITY ISSUE"
}

# Test 7: Resource limits
Write-Host "[7/10] Resource limits..." -NoNewline
$memLimit = docker inspect sel-discord-bot --format='{{.HostConfig.Memory}}' 2>$null
if ([int64]$memLimit -eq 2147483648) {
    Write-Host " PASS" -ForegroundColor Green
    $tests += $true
    $details += "Memory limited to 2GB"
} else {
    Write-Host " FAIL" -ForegroundColor Red
    $tests += $false
    $details += "Memory limit not set correctly"
}

# Test 8: No host mounts
Write-Host "[8/10] Host isolation..." -NoNewline
$mounts = docker inspect sel-discord-bot --format='{{json .Mounts}}' 2>$null | ConvertFrom-Json
$hostMounts = $mounts | Where-Object { $_.Type -eq "bind" }
if ($hostMounts.Count -eq 0) {
    Write-Host " PASS" -ForegroundColor Green
    $tests += $true
    $details += "No host filesystem mounts"
} else {
    Write-Host " FAIL" -ForegroundColor Red
    $tests += $false
    $details += "Host mounts found: $($hostMounts.Count) - SECURITY ISSUE"
}

# Test 9: Non-root user
Write-Host "[9/10] User privileges..." -NoNewline
$user = docker inspect sel-discord-bot --format='{{.Config.User}}' 2>$null
if ($user -eq "1000:1000") {
    Write-Host " PASS" -ForegroundColor Green
    $tests += $true
    $details += "Running as non-root user (UID 1000)"
} else {
    Write-Host " FAIL" -ForegroundColor Red
    $tests += $false
    $details += "Not running as expected user - SECURITY ISSUE"
}

# Test 10: Privileged mode disabled
Write-Host "[10/10] Privileged mode..." -NoNewline
$privileged = docker inspect sel-discord-bot --format='{{.HostConfig.Privileged}}' 2>$null
if ($privileged -eq "false") {
    Write-Host " PASS" -ForegroundColor Green
    $tests += $true
    $details += "Privileged mode disabled"
} else {
    Write-Host " FAIL" -ForegroundColor Red
    $tests += $false
    $details += "Privileged mode enabled - CRITICAL VULNERABILITY"
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
$passed = ($tests | Where-Object { $_ -eq $true }).Count
$total = $tests.Count
$percentage = [math]::Round(($passed / $total) * 100, 0)

Write-Host "Security Test Results: $passed/$total ($percentage%)" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Status
if ($passed -eq $total) {
    Write-Host "STATUS: MAXIMUM SECURITY" -ForegroundColor Green -BackgroundColor Black
    Write-Host "All security tests passed!" -ForegroundColor Green
} elseif ($passed -ge ($total * 0.8)) {
    Write-Host "STATUS: HIGH SECURITY" -ForegroundColor Yellow -BackgroundColor Black
    Write-Host "Most security tests passed, review failures" -ForegroundColor Yellow
} elseif ($passed -ge ($total * 0.5)) {
    Write-Host "STATUS: MEDIUM SECURITY" -ForegroundColor Yellow -BackgroundColor Black
    Write-Host "WARNING: Multiple security tests failed!" -ForegroundColor Yellow
} else {
    Write-Host "STATUS: LOW SECURITY" -ForegroundColor Red -BackgroundColor Black
    Write-Host "CRITICAL: Container is not properly secured!" -ForegroundColor Red
}

# Details
if ($passed -lt $total) {
    Write-Host ""
    Write-Host "Failed Tests:" -ForegroundColor Red
    for ($i = 0; $i -lt $tests.Count; $i++) {
        if (-not $tests[$i]) {
            Write-Host "  - $($details[$i])" -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan

# Exit code
if ($passed -eq $total) {
    exit 0
} else {
    exit 1
}
