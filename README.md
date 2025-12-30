Sel - Discord presence bot powered by OpenRouter and SQLAlchemy.

## What is SEL?

**SEL is a Discord bot with personality, memory, and emotions** - NOT a trained AI model.

### What SEL Uses:
- **Language Generation**: Claude (via OpenRouter API) for understanding and generating text
- **Memory System**: Custom Hierarchical Image Memory (HIM) vector database
- **Personality**: Custom hormone-based emotional simulation system
- **Security**: 8-layer comprehensive sanitization system

### What SEL Is:
✅ Discord bot with custom architecture for memory, personality, and security
✅ Uses existing LLMs (Claude) as the intelligence backend
✅ Custom vector storage system (HIM) for episodic memories
✅ Rule-based hormone system for emotional simulation
✅ Comprehensive security hardening and sandboxing

### What SEL Is NOT:
❌ A trained machine learning model
❌ Novel AI research or custom LLM
❌ Training its own neural networks
❌ Independent from Claude/OpenRouter

**Honest Description**: SEL is sophisticated Discord bot architecture (memory management, emotional simulation, security) built on top of Claude for language understanding and generation. The custom work is in the orchestration, not the underlying language model.

## Security Acknowledgments

**Special thanks to luna_midori5** for comprehensive penetration testing and security advice that led to significant hardening:
- Identified encoder vulnerabilities (12-dim hash collisions)
- Discovered vector database poisoning vectors
- Found HTML/JavaScript injection pathways
- Exposed command injection possibilities
- Recommended complete sandboxing

The current security architecture (8-layer sanitization, Docker sandboxing, shell execution removal) was developed in direct response to their findings.

**Special thanks to luna midori** for comprehensive code audit identifying:
- Remote Code Execution (RCE) vulnerabilities in host_exec_api.py and tmux_control_api.py (now removed)
- Git history secret leakage (see security notice below)
- Non-deterministic rollout bugs
- Monolithic code structure issues

## ⚠️ CRITICAL SECURITY NOTICE

**SECRET LEAKAGE IN GIT HISTORY** (Discovered by luna midori)

Early commits (`36e5a61`, `4ffcb48`) contained real `DISCORD_BOT_TOKEN` and `OPENROUTER_API_KEY` in `.env.example`. While removed from HEAD, these secrets are **permanently compromised** and remain in git history.

**If you forked/cloned this repository before 2025-12-29:**

1. **ROTATE ALL KEYS IMMEDIATELY**:
   - Discord Bot Token: https://discord.com/developers/applications
   - OpenRouter API Key: https://openrouter.ai/keys

2. **Assume compromise**: Any tokens used before rotation may have been exposed

3. **Do NOT reuse old tokens**

4. **For repository owners**: Consider rewriting git history with `git filter-repo` or BFG Repo-Cleaner to remove secrets permanently, or mark this repository as compromised and create a new one

**Current .env.example is safe** - it contains only placeholder values. But historical commits are permanently tainted.

## Quick Start

### Windows (Docker Desktop Required)

**IMPORTANT**: SEL can ONLY run in Docker Desktop with WSL 2 backend on Windows. Native execution is disabled for security.

**Prerequisites:**
- Docker Desktop for Windows with WSL 2 enabled
- 8GB RAM recommended
- Windows 10/11 Pro, Enterprise, or Education

**Installation:**
1. **Install Docker Desktop**: Download from https://www.docker.com/products/docker-desktop
   - Enable "Use WSL 2 instead of Hyper-V" during setup
   - Restart computer after installation
2. **Run the launcher**: Double-click `sel_launcher.exe` (enforces Docker + WSL 2)
3. **Configure tokens**: Edit `.env` file with your `DISCORD_BOT_TOKEN` and `OPENROUTER_API_KEY`
4. **Start SEL**: Run the launcher again and select deployment option

**Alternative commands:**
- `start_sel.bat` - Docker deployment with checks
- `.\deploy-windows.ps1` - Automated deployment with security verification
- `.\verify-security.ps1` - Run security tests on container

See [WINDOWS_DOCKER_DEPLOYMENT.md](WINDOWS_DOCKER_DEPLOYMENT.md) for complete Docker Desktop setup guide.

### Linux/Mac
- Install dependencies with Poetry: `cd project_echo && poetry install`. (Or `pip install .`)
- Export required env vars: `DISCORD_BOT_TOKEN`, `OPENROUTER_API_KEY`.
- Optional env: `OPENROUTER_MAIN_MODEL`, `OPENROUTER_UTIL_MODEL`, `OPENROUTER_MAIN_TEMP`, `OPENROUTER_UTIL_TEMP`, `OPENROUTER_TOP_P`, `DATABASE_URL`, `WHITELIST_CHANNEL_IDS`, `SEL_PERSONA_SEED`, `INACTIVITY_PING_HOURS`, `INACTIVITY_PING_COOLDOWN_HOURS`, `INACTIVITY_PING_CHECK_SECONDS`, `HIM_MEMORY_DIR`, `HIM_MEMORY_LEVELS`.
- Run locally: `poetry run python -m sel_bot.main`.

## Docker (Maximum Security Configuration)

SEL runs in a hardened Docker container with:
- ✅ All shells removed (bash, sh, etc.)
- ✅ Read-only root filesystem
- ✅ No listening ports exposed
- ✅ All Linux capabilities dropped
- ✅ Seccomp and AppArmor profiles active
- ✅ Non-root user execution (UID 1000)
- ✅ Resource limits enforced (2GB RAM, 2 CPU)
- ✅ No host filesystem access

**Quick Start:**
- Build and run: `docker-compose up --build`
- Windows: Use `.\deploy-windows.ps1` for automated deployment
- Verify security: `.\verify-security.ps1` (Windows) or see SECURITY.md

**Container Configuration:**
- The compose file provides `sel-bot` service with maximum security hardening
- Data persists in named volume `sel_data`
- Network isolation enforced (Discord and OpenRouter API only)
- Override `DATABASE_URL` to use SQLite if preferred (e.g., `sqlite+aiosqlite:///./data/sel.db`)

## Notes
- Sel watches all messages in allowed channels, tracks hormones per channel, writes episodic memory summaries into the Hierarchical Image Memory store, and replies via OpenRouter models (default main: `anthropic/claude-3.5-sonnet`, utility: `anthropic/claude-3-haiku-20240307`).
- Memories store short summaries only as vector tiles inside the HIM pyramid--no raw logs are persisted.
- Sel now keeps a heartbeat presence and will proactively ping users she has not heard from recently using configurable inactivity timers.
- Mood is richer (dopamine/serotonin/oxytocin/cortisol/melatonin/novelty plus curiosity and patience) and the prompt nudges her toward more human pacing and follow-ups.
- To backfill lost memories from Discord history, provide `DISCORD_BOT_TOKEN` and `BACKFILL_CHANNEL_IDS`, then run: `poetry run python -m tools.backfill_memories`. It will pair Sel's past replies with their prompting messages and write new HIM memories.
