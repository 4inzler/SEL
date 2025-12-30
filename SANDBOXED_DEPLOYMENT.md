# SEL Sandboxed Deployment Guide

**SECURITY**: This configuration completely isolates SEL from your host system.

## What Was Changed

### 1. Shell Execution DISABLED
```
agents/system_agent.py → BACKUP_WITH_SHELL_ACCESS.py
agents/system_agent.DISABLED.py → system_agent.py (stub that returns error)
```

**Result**: SEL cannot execute ANY shell commands on host or container.

### 2. Docker Sandboxing Applied

**Old Configuration (DANGEROUS):**
```yaml
volumes:
  - ${HOST_HOME}:/host/home:rw  # FULL HOST ACCESS!
  - ./agents:/app/agents         # Can modify agent code!
```

**New Configuration (SECURE):**
```yaml
volumes:
  - sel_data:/data:rw            # Only isolated data volume
  # NO HOST FILESYSTEM ACCESS
```

**Security Features:**
- ✅ Read-only root filesystem
- ✅ No shell binaries (`/bin/sh`, `/bin/bash` removed)
- ✅ Runs as non-root user (UID 1000)
- ✅ All Linux capabilities dropped
- ✅ Resource limits (2GB RAM, 2 CPUs, 100 PIDs)
- ✅ No host filesystem mounts
- ✅ Isolated Docker volumes only
- ✅ `no-new-privileges` enabled
- ✅ `/tmp` as tmpfs (memory-only, noexec)

## Windows Deployment with Docker Desktop

### Prerequisites

1. **Install Docker Desktop for Windows**
   - Download: https://www.docker.com/products/docker-desktop
   - Enable WSL 2 backend (recommended)
   - Allocate resources: 4GB RAM minimum

2. **Install Git for Windows** (if not installed)
   - Download: https://git-scm.com/download/win

### Step 1: Clone Repository

```powershell
cd C:\Users\Administrator\Documents
git clone https://github.com/4inzler/SEL.git
cd SEL
```

### Step 2: Create Environment File

Create `.env` file in the SEL directory:

```powershell
notepad .env
```

Add your credentials:
```env
# Discord
DISCORD_BOT_TOKEN=your_discord_bot_token_here

# OpenRouter
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MAIN_MODEL=anthropic/claude-3.7-sonnet
OPENROUTER_UTIL_MODEL=anthropic/claude-haiku-4.5
OPENROUTER_VISION_MODEL=anthropic/claude-3-5-sonnet-20241022

# Temperature settings
OPENROUTER_MAIN_TEMP=0.8
OPENROUTER_UTIL_TEMP=0.3
```

Save and close.

### Step 3: Build and Run

```powershell
# Build the sandboxed container
docker-compose build

# Start SEL (sandboxed, no shell access)
docker-compose up -d

# View logs
docker-compose logs -f sel-bot
```

### Step 4: Verify Sandboxing

Check that SEL is isolated:

```powershell
# Try to access shell (should fail)
docker exec -it sel-discord-bot /bin/sh
# Error: /bin/sh: no such file or directory ✓

# Check filesystem is read-only
docker exec -it sel-discord-bot python -c "open('/test', 'w')"
# Error: Read-only file system ✓

# Verify running as non-root
docker exec -it sel-discord-bot whoami
# selbot ✓ (not root)
```

### Step 5: Test SEL

Send a message in Discord:
```
@SEL run ls
```

Expected response:
```
🔒 System access is disabled for security. SEL cannot execute shell commands in this sandboxed environment.
```

## Linux Deployment (Same Configuration)

```bash
# Clone
git clone https://github.com/4inzler/SEL.git
cd SEL

# Create .env (same as Windows)
nano .env

# Build and run
docker-compose build
docker-compose up -d

# View logs
docker-compose logs -f sel-bot
```

## Managing the Sandboxed SEL

### Start/Stop
```powershell
# Start
docker-compose up -d

# Stop
docker-compose down

# Restart
docker-compose restart
```

### View Logs
```powershell
# All logs
docker-compose logs -f

# SEL only
docker-compose logs -f sel-bot

# Last 100 lines
docker-compose logs --tail=100 sel-bot
```

### Update SEL
```powershell
# Pull latest code
git pull origin master

# Rebuild
docker-compose build

# Restart
docker-compose down
docker-compose up -d
```

### Access Data

Data is stored in Docker volume `sel_data`:

```powershell
# Backup data
docker run --rm -v sel_data:/data -v ${PWD}:/backup alpine tar czf /backup/sel-backup.tar.gz /data

# Restore data
docker run --rm -v sel_data:/data -v ${PWD}:/backup alpine tar xzf /backup/sel-backup.tar.gz -C /
```

## Security Verification Checklist

After deployment, verify:

- [ ] SEL cannot execute shell commands (test with `@SEL run ls`)
- [ ] No shell binaries in container (`docker exec sel-discord-bot /bin/sh` fails)
- [ ] Running as non-root (`docker exec sel-discord-bot whoami` shows `selbot`)
- [ ] Filesystem is read-only (except `/data`)
- [ ] No host mounts (`docker inspect sel-discord-bot` shows no host paths)
- [ ] Resource limits applied (`docker stats sel-discord-bot`)
- [ ] Logs working (`docker-compose logs sel-bot`)

## What SEL CAN Do (Sandboxed)

✅ Connect to Discord
✅ Respond to messages
✅ Store memories (in isolated volume)
✅ Use OpenRouter/Claude API
✅ Manage emotions/hormones
✅ Apply security sanitization
✅ Use agents that don't need shell (image_gen, weather, browser)

## What SEL CANNOT Do (Sandboxed)

❌ Execute shell commands
❌ Access host filesystem
❌ Modify system files
❌ Run binaries on host
❌ Access other containers (network isolated)
❌ Escape sandbox
❌ Escalate privileges

## Troubleshooting

### "Cannot connect to Docker daemon"
- Ensure Docker Desktop is running
- Check Docker Desktop settings

### "Permission denied"
- Run PowerShell as Administrator
- Or add your user to `docker-users` group

### "Port already in use"
- Stop conflicting service
- Or change port in docker-compose.yml

### "Out of memory"
- Increase Docker Desktop memory allocation
- Settings → Resources → Memory → 4GB+

### SEL not responding
```powershell
# Check logs
docker-compose logs sel-bot

# Restart
docker-compose restart sel-bot

# Check environment variables
docker exec sel-discord-bot env | grep DISCORD
```

## Comparison: Old vs New

| Feature | Old (UNSAFE) | New (SANDBOXED) |
|---------|--------------|-----------------|
| Shell Access | ✓ Full access | ✗ Disabled |
| Host Filesystem | ✓ /home mounted | ✗ Isolated |
| Run as Root | ✓ Possible | ✗ Non-root only |
| Read-only FS | ✗ No | ✓ Yes |
| Resource Limits | ✗ None | ✓ 2GB/2CPU |
| Capabilities | ✓ All | ✗ Dropped |
| Host Access | ✓ Via agents | ✗ Impossible |

## Production Recommendations

1. **Use This Sandboxed Configuration** - No exceptions
2. **Keep shell execution disabled** - Never enable system_agent
3. **Monitor resource usage** - `docker stats`
4. **Regular backups** - Automated daily backups of `sel_data` volume
5. **Update regularly** - `git pull && docker-compose build`
6. **Review logs** - Check for security warnings
7. **Limit Discord permissions** - Only necessary channels

## Re-enabling Shell Access (NOT RECOMMENDED)

If you MUST enable shell access (development only):

```powershell
# Restore original agent
cd agents
mv system_agent.py system_agent.SANDBOXED.py
mv system_agent.BACKUP_WITH_SHELL_ACCESS.py system_agent.py

# Rebuild
docker-compose build
docker-compose up -d
```

**WARNING**: This removes all sandboxing. Only do this in isolated development environments.

---

**Deployment Status**: SANDBOXED ✓
**Shell Access**: DISABLED ✓
**Host Isolation**: COMPLETE ✓
**Production Ready**: YES ✓
