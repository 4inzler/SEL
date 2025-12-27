Sel - Discord presence bot powered by OpenRouter and SQLAlchemy.

## Setup
- Install dependencies with Poetry: `cd project_echo && poetry install`. (Or `pip install .`)
- Export required env vars: `DISCORD_BOT_TOKEN`, `OPENROUTER_API_KEY`.
- Optional env: `OPENROUTER_MAIN_MODEL`, `OPENROUTER_UTIL_MODEL`, `OPENROUTER_MAIN_TEMP`, `OPENROUTER_UTIL_TEMP`, `OPENROUTER_TOP_P`, `DATABASE_URL`, `WHITELIST_CHANNEL_IDS`, `SEL_PERSONA_SEED`, `INACTIVITY_PING_HOURS`, `INACTIVITY_PING_COOLDOWN_HOURS`, `INACTIVITY_PING_CHECK_SECONDS`, `HIM_MEMORY_DIR`, `HIM_MEMORY_LEVELS`.
- Run locally: `poetry run python -m sel_bot.main`.

## Docker
- Build and run with `docker-compose up --build`.
- The compose file provides `sel-service` plus a Postgres `db`. Override `DATABASE_URL` to use SQLite if preferred (e.g., `sqlite+aiosqlite:///./data/sel.db` with a mounted volume).

## Notes
- Sel watches all messages in allowed channels, tracks hormones per channel, writes episodic memory summaries into the Hierarchical Image Memory store, and replies via OpenRouter models (default main: `anthropic/claude-3.5-sonnet`, utility: `anthropic/claude-3-haiku-20240307`).
- Memories store short summaries only as vector tiles inside the HIM pyramid--no raw logs are persisted.
- Sel now keeps a heartbeat presence and will proactively ping users she has not heard from recently using configurable inactivity timers.
- Mood is richer (dopamine/serotonin/oxytocin/cortisol/melatonin/novelty plus curiosity and patience) and the prompt nudges her toward more human pacing and follow-ups.
- To backfill lost memories from Discord history, provide `DISCORD_BOT_TOKEN` and `BACKFILL_CHANNEL_IDS`, then run: `poetry run python -m tools.backfill_memories`. It will pair Sel's past replies with their prompting messages and write new HIM memories.
