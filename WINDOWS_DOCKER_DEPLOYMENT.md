# SEL Windows Docker Desktop - Maximum Security Deployment

Complete guide for running SEL on Windows with Docker Desktop in a fully secured container.

## Prerequisites

### 1. Install Docker Desktop for Windows

**Download**: https://www.docker.com/products/docker-desktop

**System Requirements:**
- Windows 10/11 64-bit: Pro, Enterprise, or Education
- WSL 2 feature enabled
- 4GB RAM minimum (8GB recommended)
- Virtualization enabled in BIOS

**Installation Steps:**

1. Download Docker Desktop installer
2. Run installer (requires admin)
3. Enable "Use WSL 2 instead of Hyper-V" (recommended)
4. Restart computer
5. Launch Docker Desktop
6. Complete setup wizard

**Verify Installation:**
```powershell
docker --version
docker-compose --version
```

Expected output:
```
Docker version 24.x.x
Docker Compose version v2.x.x
```

### 2. Configure Docker Desktop

**Settings → General:**
- ☑ Use WSL 2 based engine
- ☑ Send usage statistics (optional)

**Settings → Resources:**
- **Memory**: 4GB minimum (8GB recommended)
- **CPUs**: 2 minimum (4 recommended)
- **Disk**: 20GB minimum

**Settings → Docker Engine:**
Add this configuration:
```json
{
  "features": {
    "buildkit": true
  },
  "experimental": false,
  "debug": false
}
```

Click "Apply & Restart"

## SEL Deployment on Windows

### Step 1: Clone Repository

Open PowerShell as Administrator:

```powershell
# Navigate to Documents
cd $env:USERPROFILE\Documents

# Clone SEL
git clone https://github.com/4inzler/SEL.git
cd SEL

# Verify files
dir
```

### Step 2: Create Environment File

```powershell
# Copy example
copy .env.example .env

# Edit with notepad
notepad .env
```

**Add your credentials:**
```env
# REQUIRED
DISCORD_BOT_TOKEN=your_discord_bot_token_here
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Models (defaults are good)
OPENROUTER_MAIN_MODEL=anthropic/claude-3.7-sonnet
OPENROUTER_UTIL_MODEL=anthropic/claude-haiku-4.5
OPENROUTER_VISION_MODEL=anthropic/claude-3-5-sonnet-20241022

# Temperature
OPENROUTER_MAIN_TEMP=0.8
OPENROUTER_UTIL_TEMP=0.3
```

Save and close.

### Step 3: Build Secure Container

```powershell
# Build with maximum security
docker-compose build --no-cache

# This will:
# - Remove all shells (bash, sh, etc.)
# - Remove package managers (apt, pip)
# - Remove compilers (gcc, make)
# - Remove network tools (curl, wget)
# - Set read-only filesystem
# - Apply security profiles
```

Expected output:
```
[+] Building 120.5s
 => [internal] load build definition
 => => transferring dockerfile
 => [internal] load .dockerignore
 => [1/8] FROM python:3.11-slim
 => [2/8] RUN apt-get update && apt-get upgrade...
 => [3/8] RUN useradd -m -u 1000 -s /usr/sbin/nologin selbot...
 => [4/8] COPY project_echo/requirements.txt .
 => [5/8] RUN pip install --no-cache-dir -r requirements.txt...
 => [6/8] COPY project_echo/ /app/
 => [7/8] RUN rm -f /bin/sh /bin/bash...
 => [8/8] RUN chmod -R 755 /app...
 => exporting to image
Successfully tagged sel:latest
```

### Step 4: Start SEL (Sandboxed)

```powershell
# Start in detached mode
docker-compose up -d

# View logs
docker-compose logs -f sel-bot
```

Expected logs:
```
sel-bot | INFO [__main__] LLM Provider: OpenRouter (cloud)
sel-bot | INFO [__main__] Main Model: anthropic/claude-3.7-sonnet
sel-bot | INFO [__main__] Util Model: anthropic/claude-haiku-4.5
sel-bot | INFO [__main__] MemoryManager initialized
sel-bot | INFO [sel_bot.discord_client] Initializing security system...
sel-bot | INFO [sel_bot.async_security] Async security initialized with 5.0s timeout
sel-bot | INFO [sel_bot.discord_client] Security system initialized successfully
sel-bot | INFO [discord.gateway] Shard ID None has connected to Gateway
sel-bot | INFO [sel_bot.discord_client] Sel connected as SEL#6533
```

## Security Verification (Windows)

### Verify Container Security

Run these commands in PowerShell:

```powershell
# 1. Verify no shell access
docker exec sel-discord-bot /bin/sh
# Expected: Error: executable file not found ✓

# 2. Verify running as non-root
docker exec sel-discord-bot whoami 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "SUCCESS: whoami blocked (no shell)" -ForegroundColor Green }

# 3. Verify read-only filesystem
docker exec sel-discord-bot python -c "open('/test', 'w')"
# Expected: Error: Read-only file system ✓

# 4. Verify no ports exposed
docker port sel-discord-bot
# Expected: (empty output) ✓

# 5. Verify security options
docker inspect sel-discord-bot --format='{{json .HostConfig.SecurityOpt}}' | ConvertFrom-Json
# Expected: no-new-privileges:true, seccomp, apparmor

# 6. Verify capabilities dropped
docker inspect sel-discord-bot --format='{{json .HostConfig.CapDrop}}' | ConvertFrom-Json
# Expected: ALL

# 7. Verify resource limits
docker stats sel-discord-bot --no-stream
# Expected: Memory limit 2GB, CPU limit 2 cores
```

### Automated Security Check Script

Save this as `verify-security.ps1`:

```powershell
# SEL Security Verification Script for Windows
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "SEL Security Verification" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$tests = @()

# Test 1: Shell access blocked
Write-Host "[1/8] Testing shell access blocking..." -NoNewline
try {
    docker exec sel-discord-bot /bin/sh 2>$null
    Write-Host " FAILED" -ForegroundColor Red
    $tests += $false
} catch {
    Write-Host " PASS" -ForegroundColor Green
    $tests += $true
}

# Test 2: Read-only filesystem
Write-Host "[2/8] Testing read-only filesystem..." -NoNewline
try {
    docker exec sel-discord-bot python -c "open('/test', 'w')" 2>$null
    Write-Host " FAILED" -ForegroundColor Red
    $tests += $false
} catch {
    Write-Host " PASS" -ForegroundColor Green
    $tests += $true
}

# Test 3: No ports exposed
Write-Host "[3/8] Testing port isolation..." -NoNewline
$ports = docker port sel-discord-bot 2>$null
if ([string]::IsNullOrWhiteSpace($ports)) {
    Write-Host " PASS" -ForegroundColor Green
    $tests += $true
} else {
    Write-Host " FAILED" -ForegroundColor Red
    $tests += $false
}

# Test 4: Container running
Write-Host "[4/8] Testing container status..." -NoNewline
$status = docker inspect sel-discord-bot --format='{{.State.Running}}' 2>$null
if ($status -eq "true") {
    Write-Host " PASS" -ForegroundColor Green
    $tests += $true
} else {
    Write-Host " FAILED" -ForegroundColor Red
    $tests += $false
}

# Test 5: Security options
Write-Host "[5/8] Testing security options..." -NoNewline
$secOpts = docker inspect sel-discord-bot --format='{{json .HostConfig.SecurityOpt}}' 2>$null | ConvertFrom-Json
if ($secOpts -contains "no-new-privileges:true") {
    Write-Host " PASS" -ForegroundColor Green
    $tests += $true
} else {
    Write-Host " FAILED" -ForegroundColor Red
    $tests += $false
}

# Test 6: Capabilities dropped
Write-Host "[6/8] Testing capabilities..." -NoNewline
$capDrop = docker inspect sel-discord-bot --format='{{json .HostConfig.CapDrop}}' 2>$null | ConvertFrom-Json
if ($capDrop -contains "ALL") {
    Write-Host " PASS" -ForegroundColor Green
    $tests += $true
} else {
    Write-Host " FAILED" -ForegroundColor Red
    $tests += $false
}

# Test 7: Resource limits
Write-Host "[7/8] Testing resource limits..." -NoNewline
$memLimit = docker inspect sel-discord-bot --format='{{.HostConfig.Memory}}' 2>$null
if ([int64]$memLimit -eq 2147483648) {  # 2GB in bytes
    Write-Host " PASS" -ForegroundColor Green
    $tests += $true
} else {
    Write-Host " FAILED" -ForegroundColor Red
    $tests += $false
}

# Test 8: No host mounts
Write-Host "[8/8] Testing host isolation..." -NoNewline
$mounts = docker inspect sel-discord-bot --format='{{json .Mounts}}' 2>$null | ConvertFrom-Json
$hostMounts = $mounts | Where-Object { $_.Type -eq "bind" }
if ($hostMounts.Count -eq 0) {
    Write-Host " PASS" -ForegroundColor Green
    $tests += $true
} else {
    Write-Host " FAILED" -ForegroundColor Red
    $tests += $false
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
$passed = ($tests | Where-Object { $_ -eq $true }).Count
$total = $tests.Count
$percentage = [math]::Round(($passed / $total) * 100, 0)

if ($passed -eq $total) {
    Write-Host "SECURITY: MAXIMUM ($passed/$total tests passed)" -ForegroundColor Green
} elseif ($passed -ge ($total * 0.75)) {
    Write-Host "SECURITY: HIGH ($passed/$total tests passed)" -ForegroundColor Yellow
} else {
    Write-Host "SECURITY: INSUFFICIENT ($passed/$total tests passed)" -ForegroundColor Red
}
Write-Host "========================================" -ForegroundColor Cyan
```

Run it:
```powershell
.\verify-security.ps1
```

## Windows-Specific Features

### Using PowerShell Scripts

**Start SEL:**
```powershell
# Save as start-sel.ps1
docker-compose up -d
Write-Host "SEL started in secure sandbox" -ForegroundColor Green
docker-compose logs -f sel-bot
```

**Stop SEL:**
```powershell
# Save as stop-sel.ps1
docker-compose down
Write-Host "SEL stopped" -ForegroundColor Yellow
```

**Restart SEL:**
```powershell
# Save as restart-sel.ps1
docker-compose restart sel-bot
Write-Host "SEL restarted" -ForegroundColor Cyan
docker-compose logs --tail=50 sel-bot
```

**View Logs:**
```powershell
# Save as logs-sel.ps1
param(
    [int]$Lines = 100
)
docker-compose logs --tail=$Lines -f sel-bot
```

### Windows Firewall Configuration

**Allow Docker Desktop:**

1. Open Windows Defender Firewall
2. Click "Allow an app through firewall"
3. Click "Change settings"
4. Find "Docker Desktop"
5. Check both Private and Public
6. Click OK

**Block SEL from accessing local network:**

```powershell
# Run as Administrator
# Block SEL container from accessing local network
New-NetFirewallRule -DisplayName "Block SEL Local Network" `
    -Direction Outbound `
    -Action Block `
    -RemoteAddress 192.168.0.0/16,10.0.0.0/8,172.16.0.0/12 `
    -Program "C:\Program Files\Docker\Docker\resources\com.docker.backend.exe"
```

## Troubleshooting Windows Issues

### Docker Desktop Not Starting

**Solution 1: Enable WSL 2**
```powershell
# Run as Administrator
wsl --install
wsl --set-default-version 2
```

Restart computer.

**Solution 2: Enable Virtualization**
1. Restart computer
2. Enter BIOS (usually F2, F10, or Del during boot)
3. Find "Virtualization Technology" or "VT-x"
4. Enable it
5. Save and exit

### Build Fails with "no space left on device"

**Solution: Clean Docker**
```powershell
# Remove unused containers
docker system prune -a

# Remove unused volumes
docker volume prune

# Increase disk space in Docker Desktop
# Settings → Resources → Disk image size → Increase
```

### Container Exits Immediately

**Check logs:**
```powershell
docker-compose logs sel-bot
```

**Common issues:**
- Missing .env file → Create it
- Invalid Discord token → Check .env
- Invalid OpenRouter API key → Check .env

### "Access Denied" Errors

**Run PowerShell as Administrator:**
1. Right-click PowerShell
2. Select "Run as administrator"
3. Navigate to SEL directory
4. Run commands again

### Cannot Connect to Discord

**Check network:**
```powershell
# Test Discord connectivity
Test-NetConnection discord.com -Port 443
```

Expected:
```
TcpTestSucceeded : True
```

**Check container network:**
```powershell
docker exec sel-discord-bot python -c "import socket; print(socket.gethostbyname('discord.com'))"
```

## Windows Security Best Practices

### 1. Use Windows Defender

Ensure Windows Defender is enabled:
```powershell
Get-MpComputerStatus
```

### 2. Keep Docker Updated

```powershell
# Check for updates in Docker Desktop
# Settings → Software Updates → Check for updates
```

### 3. Regular Backups

**Backup SEL data:**
```powershell
# Create backup directory
mkdir C:\Backups\SEL

# Backup data volume
docker run --rm -v sel_data:/data -v C:\Backups\SEL:/backup alpine tar czf /backup/sel-backup-$(Get-Date -Format 'yyyy-MM-dd').tar.gz /data
```

**Restore backup:**
```powershell
# Restore from backup
docker run --rm -v sel_data:/data -v C:\Backups\SEL:/backup alpine tar xzf /backup/sel-backup-YYYY-MM-DD.tar.gz -C /
```

### 4. Monitor Resource Usage

```powershell
# Real-time monitoring
docker stats sel-discord-bot

# Expected output:
# NAME              CPU %   MEM USAGE / LIMIT   MEM %   NET I/O
# sel-discord-bot   1.5%    512MB / 2GB         25%     1MB / 500KB
```

### 5. Regular Security Audits

Run weekly:
```powershell
# Check for vulnerabilities
docker scan sel-discord-bot

# Update SEL
cd $env:USERPROFILE\Documents\SEL
git pull origin master
docker-compose build --no-cache
docker-compose up -d
```

## Advanced Windows Configuration

### Use Windows Task Scheduler

**Auto-start SEL on boot:**

1. Open Task Scheduler
2. Create Basic Task
3. Name: "Start SEL Discord Bot"
4. Trigger: "When the computer starts"
5. Action: "Start a program"
6. Program: `powershell.exe`
7. Arguments: `-File "C:\Users\Administrator\Documents\SEL\start-sel.ps1"`
8. Finish

### Use Windows Events

**Monitor container crashes:**
```powershell
# Create event log watcher
$query = @"
<QueryList>
  <Query Id="0" Path="Application">
    <Select Path="Application">*[System[Provider[@Name='Docker']]]</Select>
  </Query>
</QueryList>
"@

$action = {
    Write-Host "Docker event detected!"
    docker-compose logs --tail=50 sel-bot | Out-File C:\Logs\sel-crash-$(Get-Date -Format 'yyyy-MM-dd-HH-mm').txt
}

Register-ObjectEvent -InputObject ([System.Diagnostics.Eventing.Reader.EventLogWatcher]::new($query)) -EventName EventRecordWritten -Action $action
```

## Complete Windows Deployment Checklist

- [ ] Docker Desktop installed and running
- [ ] WSL 2 enabled
- [ ] Virtualization enabled in BIOS
- [ ] SEL repository cloned
- [ ] .env file created with tokens
- [ ] Container built successfully
- [ ] Container started and running
- [ ] Security verification passed (8/8)
- [ ] No ports exposed (verified)
- [ ] Shell access blocked (verified)
- [ ] Filesystem read-only (verified)
- [ ] SEL connected to Discord
- [ ] Tested command blocking works
- [ ] Backup strategy configured
- [ ] Windows Firewall configured
- [ ] Auto-start configured (optional)

## Quick Commands Reference

```powershell
# Start
docker-compose up -d

# Stop
docker-compose down

# Restart
docker-compose restart sel-bot

# Logs (last 100 lines)
docker-compose logs --tail=100 sel-bot

# Logs (follow)
docker-compose logs -f sel-bot

# Update
git pull && docker-compose build && docker-compose up -d

# Security check
.\verify-security.ps1

# Stats
docker stats sel-discord-bot --no-stream

# Backup
docker run --rm -v sel_data:/data -v C:\Backups\SEL:/backup alpine tar czf /backup/sel-backup.tar.gz /data
```

---

**Windows Deployment Status**: READY
**Security Level**: MAXIMUM
**Docker Desktop**: REQUIRED
**WSL 2**: RECOMMENDED
