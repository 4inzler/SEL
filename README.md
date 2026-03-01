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
- Optional env: `DISCORD_FULL_API_MODE_ENABLED`, `DISCORD_BATCH_WINDOW_SECONDS`,
  `SEL_STATUS_THOUGHTS_ENABLED`, `SEL_STATUS_THOUGHTS_INTERVAL_SECONDS`, `SEL_STATUS_THOUGHTS`,
  `SEL_PROFILE_BIO_UPDATES_ENABLED`, `SEL_PROFILE_BIO_INTERVAL_SECONDS`,
  `SEL_MULTI_MESSAGE_MODE_ENABLED`, `SEL_MULTI_MESSAGE_MAX_PARTS`, `SEL_MULTI_MESSAGE_MIN_REPLY_CHARS`,
  `SEL_MULTI_MESSAGE_BURST_MODE`, `SEL_DISCORD_USER_STYLE_ENABLED`, `SEL_DISCORD_REACTIONS_ENABLED`,
  `SEL_DISCORD_REACTION_CHANCE`,
  `OPENROUTER_MAIN_MODEL`, `OPENROUTER_UTIL_MODEL`, `OPENROUTER_MAIN_TEMP`, `OPENROUTER_UTIL_TEMP`, `OPENROUTER_TOP_P`, `DATABASE_URL`, `WHITELIST_CHANNEL_IDS`, `SEL_PERSONA_SEED`, `INACTIVITY_PING_HOURS`, `INACTIVITY_PING_COOLDOWN_HOURS`, `INACTIVITY_PING_CHECK_SECONDS`, `HIM_MEMORY_DIR`, `HIM_MEMORY_LEVELS`, `ENABLE_PROMPTS_V2`, `PROMPTS_V2_ROLLOUT_PERCENTAGE`, `PROMPTS_V2_SIMPLIFIED_ROLLOUT_PERCENTAGE`,
  `ELEVENLABS_API_KEY`, `ELEVENLABS_BASE_URL`, `ELEVENLABS_TTS_ENABLED`, `ELEVENLABS_TTS_MODEL`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_TTS_OUTPUT_FORMAT`, `ELEVENLABS_TTS_LANGUAGE_CODE`, `ELEVENLABS_TTS_MAX_CHARS`,
  `ELEVENLABS_STT_ENABLED`, `ELEVENLABS_STT_MODEL`, `ELEVENLABS_STT_LANGUAGE_CODE`, `ELEVENLABS_STT_MAX_BYTES`,
  `VOICE_AUTO_LEAVE_ENABLED`, `VOICE_AUTO_LEAVE_CHECK_SECONDS`, `VOICE_AUTO_LEAVE_EMPTY_MINUTES`, `VOICE_AUTO_LEAVE_HORMONE_ENABLED`, `VOICE_AUTO_LEAVE_MELATONIN_MIN`, `VOICE_AUTO_LEAVE_DOPAMINE_MAX`, `VOICE_LEAVE_PHRASES`,
  `VOICE_STT_ENABLED`, `VOICE_STT_AUTO_RESPOND`, `VOICE_STT_POST_TRANSCRIPTS`, `VOICE_STT_MIN_SECONDS`, `VOICE_STT_MAX_SECONDS`, `VOICE_STT_SAMPLE_RATE`, `VOICE_STT_CHANNELS`,
  `AGENT_AUTONOMY_ENABLED`, `AGENT_AUTONOMY_SAFE_AGENTS`, `AGENT_AUTONOMY_MIN_CONFIDENCE`, `AGENT_AUTONOMY_CATALOG_REFRESH_SECONDS`, `AGENT_AUTONOMY_MAX_RESULT_CHARS`,
  `SEL_OPERATOR_MODE_ENABLED`, `SEL_OPERATOR_FULL_HOST_PRIVILEGES`, `SEL_OPERATOR_REQUIRE_APPROVAL_USER`,
  `SEL_OPERATOR_AGENTS`, `SEL_OPERATOR_BLOCK_PATTERNS`, `SEL_OPERATOR_COMMAND_TIMEOUT_SECONDS`, `SEL_OPERATOR_MAX_OUTPUT_CHARS`, `SEL_OPERATOR_COMMAND_INTENT_THRESHOLD`, `SEL_OPERATOR_DIRECT_REPLY_ENABLED`,
  `RESPONSE_FAST_MODE_ENABLED`, `RESPONSE_FAST_MODE_MAX_USER_CHARS`, `RESPONSE_FAST_MODE_SKIP_CLASSIFICATION_CHARS`, `RESPONSE_FAST_MODE_MEMORY_RECALL_LIMIT`,
  `SEAL_TOOL_FORGE_MIN_QUALITY_SCORE`, `SEAL_TOOL_FORGE_IMPROVE_EXISTING_CHANCE`,
  `SEAL_TOOL_FORGE_SELF_CODE_EDIT_CHANCE`, `SEAL_SELF_CODE_EDIT_TARGETS`,
  `SEL_MODEL_DATASET_DIR`, `SEL_MODEL_DATASET_AUTO_EXPORT_ENABLED`, `SEL_MODEL_DATASET_EXPORT_ON_START`,
  `SEL_MODEL_DATASET_INTERVAL_HOURS`, `SEL_MODEL_DATASET_MAX_SNAPSHOTS`,
  `SEL_BEHAVIOR_ADAPTATION_ENABLED`, `SEL_BEHAVIOR_ANALYZE_ON_START`, `SEL_BEHAVIOR_INTERVAL_HOURS`,
  `SEL_BEHAVIOR_WINDOW_DAYS`, `SEL_BEHAVIOR_MAX_HISTORY_LINES`, `SEL_BEHAVIOR_APPLY_GLOBAL_TUNING`,
  `SEL_BEHAVIOR_FULL_ADAPTATION`,
  `SEL_DREAM_ENABLED`, `SEL_DREAM_ON_START`, `SEL_DREAM_INTERVAL_MINUTES`,
  `SEL_DREAM_MIN_INACTIVE_HOURS`, `SEL_DREAM_MEMORY_LIMIT`, `SEL_DREAM_MAX_JOURNAL_ENTRIES`,
  `SEAL_INTERACTION_TRIGGERS_ENABLED`,
  `SEL_INTEROCEPTION_ENABLED`, `SEL_INTEROCEPTION_INTERVAL_SECONDS`, `SEL_INTEROCEPTION_MAX_LOG_ENTRIES`,
  `SEL_INTEROCEPTION_SENSOR_STREAM_PATH`,
  `LLM_DUAL_MODEL_ASSIST_ENABLED`, `LLM_DUAL_MODEL_ASSIST_ALLOW_DIRECT`, `LLM_DUAL_MODEL_ASSIST_DIRECT_THRESHOLD`,
  `LLM_QUAD_MODE_ENABLED`, `LLM_QUAD_SECOND_PASS_MIN_CHARS`.
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
