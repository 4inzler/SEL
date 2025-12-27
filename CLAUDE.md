# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SEL is a Discord presence bot with an integrated Hierarchical Image Memory (HIM) system. The bot maintains episodic memory, tracks emotional state through a hormonal system, and supports pluggable LangChain-style agents for extended capabilities.

**Two main subsystems:**
- **sel_bot**: Discord bot with memory, hormones, and agent orchestration
- **HIM service**: FastAPI-based hierarchical memory storage with vector indexing and tile-based retrieval

## Development Commands

### Local Development

**Install dependencies:**
```bash
cd project_echo && poetry install
```

**Run the Discord bot:**
```bash
# From project_echo directory
poetry run python -m sel_bot.main
```

**Run the HIM API server:**
```bash
# From project_echo directory
poetry run python run_him.py --data-dir ./data
```

**Profile hardware without starting server:**
```bash
poetry run python run_him.py --profile-only
```

**Run tests:**
```bash
# From project_echo directory
poetry run pytest
```

**Backfill memories from Discord history:**
```bash
# Requires DISCORD_BOT_TOKEN and BACKFILL_CHANNEL_IDS env vars
poetry run python -m tools.backfill_memories
```

### Docker Deployment

**Build and run complete stack (bot + Postgres):**
```bash
# From repository root
docker-compose up --build
```

The compose file provisions:
- `sel-service`: Bot with GPU access and host command execution
- `db`: PostgreSQL 15 database

Override `DATABASE_URL` to use SQLite: `sqlite+aiosqlite:///./data/sel.db`

## Architecture

### Core Components

**project_echo/sel_bot/**
- `main.py`: Entry point; initializes all managers and clients
- `discord_client.py`: Discord event handling, message processing, bash agent detection
- `llm_client.py`: OpenRouter API wrapper (main/utility/vision models)
- `state_manager.py`: Per-channel state (hormones, last ping, conversation mode)
- `memory.py`: Hierarchical memory management (HIM integration)
- `hormones.py`: Emotional state tracking (dopamine, serotonin, oxytocin, cortisol, melatonin, novelty, curiosity, patience)
- `prompts.py`: System prompts and behavioral tuning
- `agents_manager.py`: Dynamic loading of agent modules from `/agents`
- `config.py`: Pydantic settings with environment variable loading
- `models.py`: SQLAlchemy models for channel state and metadata

**project_echo/him/**
- `api.py`: FastAPI server implementing HIM_Spec_v1.1.md endpoints
- `storage.py`: SQLite-backed tile storage with content addressing
- `planner.py`: Query planning and prefetch hint processing
- `vector.py`: Embedding utilities and similarity operations
- `synapse.py`: Snapshot and tile metadata management
- `simulation.py`: Memory simulation and testing utilities

**agents/**
- Drop Python files here to expose new agents
- Each module must define `DESCRIPTION` string and `run(query: str, **kwargs) -> str` function
- Loaded dynamically at startup; hot-reload supported if mounted as Docker volume

**System Access:**
- `agents/system_agent.py`: Sel's unified system interface - the only system agent
  - Uses LLM to understand natural language queries (no rigid patterns)
  - Handles everything: navigation, disk/memory, processes, ports, docker, git, files
  - Maintains persistent state (working directory, history, background jobs)
  - Backend: `tmux_control_api.py` (port 9001) for shell execution
- Configured via `TMUX_CONTROL_URL`, `TMUX_CONTROL_TOKEN` env vars

### Data Flow

1. **Message Received** → discord_client
2. **State Loaded** → StateManager fetches channel hormones and metadata
3. **Context Built** → Recent messages + memory recall from HIM
4. **LLM Called** → OpenRouter generates response based on persona + state
5. **Memory Stored** → Significant interactions written as HIM tiles
6. **State Updated** → Hormones adjust based on interaction (dopamine for novelty, serotonin for positive, cortisol for stress)
7. **Response Sent** → Back to user with updated emotional context

### Agent Detection & Execution

Agents are invoked via three methods (priority order):

1. **Explicit patterns**: `agent:system_agent`, `bash <cmd>`, `run command <cmd>`
2. **Keyword detection**: `fastfetch`, `bash <cmd>`, `run command <cmd>`
3. **LLM classification**: utility model detects system queries (authorized users only)

**All system access routes through `system_agent`** - it uses LLM to understand intent:
- "disk space?" → `{action: "disk"}` → runs `df -h`
- "what's on port 3000" → `{action: "port", params: {port: "3000"}}` → runs `lsof`
- "bash ls" → `{action: "run_command", command: "ls"}` → runs directly

**Authorization**: Only `APPROVAL_USER_ID` can execute system commands (default: `1329883906069102733`)

**Execution flow**:
- System intent detected → `system_agent`
- LLM parses query → extracts action + params
- Routes to handler → executes via tmux API
- Memory created: `"Sel ran: {query}"` with salience 0.4

### Memory System (HIM)

**Hierarchical tiled storage:**
- Each memory stored as vector tile in pyramid structure (L0 to L{HIM_MEMORY_LEVELS})
- Content-addressed by `blake3(stream | snapshot | level | x | y | payload)`
- Storage path: `{HIM_MEMORY_DIR}/{stream}/{snapshot}/{level}/{x}/{y}/{tile_id[:12]}`

**Streams (bands):**
- `kv_cache`: Key-value cache (Zarr/TileDB, fp8/int8/fp16, zstd compressed)
- `emb`: Embeddings (256-1024 dims, fp16 or int8 with PQ)
- `skills`: JSON/WASM modules (signed releases)
- `logs/audit`: Parquet row groups for efficient scans

**Retrieval path:**
1. Coarse scan at top pyramid levels (L{n}, L{n-1}) using in-RAM centroids
2. Localize ROIs via nearest-neighbor search in embedding space
3. Refine by loading ≤K high-res tiles from NVMe/storage
4. Accept when recall ≥ 0.98 or confidence ≥ τ or budget T expires

**API endpoints** (see HIM_Spec_v1.1.md):
- `GET /v1/snapshots/:id`
- `POST /v1/query` → returns QueryPlan with tile_ids
- `POST /v1/prefetch` with hint array
- `GET /v1/tiles/:stream/:snapshot/:level/:x/:y`
- `POST /v1/tiles` (bulk ingest, supports deltas)

### Hormonal System

Each channel maintains independent hormone levels (0.0-1.0):
- **dopamine**: Novelty response, reward, engagement
- **serotonin**: Well-being, positive interaction
- **oxytocin**: Social bonding, empathy
- **cortisol**: Stress, urgency, negative events
- **melatonin**: Rest drive, reduced activity
- **novelty**: Exposure to new stimuli
- **curiosity**: Drive to explore/question
- **patience**: Tolerance for delayed responses

Hormones decay over time and are updated based on:
- Message sentiment and content
- Response acceptance/rejection
- Inactivity duration
- User engagement patterns

Prompts include current hormone levels to influence response tone and behavior.

## Environment Variables

**Required:**
- `DISCORD_BOT_TOKEN`: Discord bot authentication
- `OPENROUTER_API_KEY`: OpenRouter API key for LLM access

**Optional (for production security):**
- `TMUX_CONTROL_TOKEN`: Authentication token for tmux control API (optional for local dev)
- `HOST_EXEC_TOKEN`: Authentication token for host exec API (optional for local dev)

**LLM Configuration:**
- `OPENROUTER_MAIN_MODEL`: Primary model (default: `anthropic/claude-3.5-sonnet`)
- `OPENROUTER_UTIL_MODEL`: Utility model (default: `anthropic/claude-3-haiku-20240307`)
- `OPENROUTER_VISION_MODEL`: Vision model (default: `openai/gpt-4o-mini`)
- `OPENROUTER_MAIN_TEMP`: Main model temperature (default: 0.8)
- `OPENROUTER_UTIL_TEMP`: Utility model temperature (default: 0.3)
- `OPENROUTER_TOP_P`: Nucleus sampling (default: 0.9)

**Database:**
- `DATABASE_URL`: Connection string (default: `sqlite+aiosqlite:///./sel.db`)

**Memory:**
- `HIM_MEMORY_DIR`: HIM tile storage path (default: `./sel_data/him_store`)
- `HIM_MEMORY_LEVELS`: Pyramid depth (default: 3)
- `HIM_API_BASE_URL`: HIM service endpoint (default: `http://localhost:8000`)
- `MEMORY_RECALL_LIMIT`: Max memories to recall per query (default: 10)
- `RECENT_CONTEXT_LIMIT`: Recent messages to include (default: 20)

**Terminal Control:**
- `TMUX_CONTROL_URL`: Tmux control API endpoint (default: `http://localhost:9001`)
- `TMUX_CONTROL_TOKEN`: Authentication token (required for security)
- `HOST_EXEC_URL`: Host command API endpoint (default: `http://host.docker.internal:9000/run`)
- `HOST_EXEC_TOKEN`: Authentication token (required for security)
- `HOST_EXEC_WHITELIST`: Comma-separated command prefixes (default: `*` allows all)

**Bot Behavior:**
- `APPROVAL_USER_ID`: Discord user ID authorized for bash commands (default: `1329883906069102733`)
- `WHITELIST_CHANNEL_IDS`: Comma-separated channel IDs (default: all channels)
- `SEL_PERSONA_SEED`: Base personality prompt
- `SEL_TIMEZONE`: Timezone for time-aware responses (default: `America/Los_Angeles`)
- `INACTIVITY_PING_HOURS`: Hours before proactive ping (default: 48.0)
- `INACTIVITY_PING_COOLDOWN_HOURS`: Cooldown between pings (default: 24.0)
- `INACTIVITY_PING_CHECK_SECONDS`: Ping check interval (default: 900)

**Other:**
- `AGENTS_DIR`: Agent modules directory (default: `./agents`)

## Code Style

- **Python 3.11+**, 4-space indentation, PEP 8 compliance
- **Type hints** required; match existing annotation density
- **Snake_case** for functions/variables, **PascalCase** for classes, **UPPER_SNAKE** for constants/env vars
- **Pure functions** where possible; document side effects explicitly
- **Behavioral tuning** lives in `sel_bot/prompts.py` and `sel_bot/hormones.py` with inline rationale
- **Small modules** with clear responsibilities; maintain existing docstring style

## Testing

- Tests in `project_echo/tests/test_*.py`, mirroring module names
- Use fixtures from `project_echo/tests/conftest.py` instead of ad-hoc setup
- **Never couple tests to `sel_data/` contents**—create temporary data directories
- Add regression tests when modifying behavior (response thresholds, storage logic, hormone math)
- Pin expected values or API response shapes to catch drift

## Agent Development

Create new agents by adding Python files to `/agents`:

```python
"""Brief description of agent purpose."""

DESCRIPTION = "Short summary for agent discovery"

def run(query: str, **kwargs) -> str:
    """
    Execute agent logic and return string response.

    Args:
        query: User input or command
        **kwargs: Additional context (varies by invocation)

    Returns:
        String result to display to user
    """
    # Implementation here
    return "result"
```

**Guidelines:**
- Keep agents minimal and focused
- Use environment variables for configuration (access via `os.environ`)
- Return user-friendly strings (will be sent as Discord messages)
- Handle errors gracefully with descriptive messages
- Avoid heavy dependencies unless necessary
- Document any required env vars in docstring

**Hot-reload**: If `/agents` is mounted as a Docker volume, new agents can be added without rebuilding.

## HIM Development

When modifying the HIM service:

- **API changes**: Update `project_echo/HIM_Spec_v1.1.md` to reflect new endpoints or schemas
- **Storage changes**: Ensure backward compatibility or provide migration; tiles are content-addressed (blake3)
- **Performance**: Target p95 query latency ≤ 150ms local, ≤ 350ms cross-AZ for K ≤ 8 tiles
- **Determinism**: Maintain byte-for-byte replay fidelity under pinned environments
- **Tests**: Add storage/vector/planner tests covering new functionality

**Key constraints:**
- Tiles are 512×512 with optional 16px halo
- Pyramid overhead ≈ 4/3 of base (all levels); truncate low levels to optimize
- Warm NVMe cache hit rate ≥ 95% for top 10% tiles
- Prefetch coverage ≥ 90% for batched queries

## Commit Guidelines

- **Concise, present-tense, scoped**: `sel_bot: raise image reply chance`, `him: tighten tile eviction`
- **Single scope per commit**: Avoid multi-module changes in one commit
- **Document risks**: State behavioral impact in commit message or PR description
- **Include test output**: Show pytest results, log snippets, or screenshots for UX changes
- **Secrets**: Never commit tokens/keys; use `.env` (gitignored) and document new env vars in README.md

## Important Notes

- **Runtime data** in `sel_data/` and `project_echo/data/`: Treat as artifacts, not canonical sources
- **Hormone math changes**: Document rationale inline in `hormones.py`; may affect personality significantly
- **Prompt changes**: Keep in `prompts.py`; test across multiple scenarios before committing
- **Agent coordination**: Changes to `/agents` modules should be minimal unless coordinated (mounted volume)
- **HIM spec compliance**: All storage/API changes must align with `HIM_Spec_v1.1.md` SLOs and schemas
- **GPU support**: Docker compose reserves all NVIDIA GPUs; configure `NVIDIA_VISIBLE_DEVICES` to limit
- **Host exec security**: Default whitelist is `*` (permissive); tighten in production via `HOST_EXEC_WHITELIST`
