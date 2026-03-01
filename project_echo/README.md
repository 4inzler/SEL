# project_echo

Hierarchical Image Memory (HIM) reference implementation that exposes a FastAPI service backed by a SQLite-powered storage layer.

## Bundles & single-line installer

- `him_bundle_oneliner.sh`: executes a single Python one-liner that recreates the
  entire project directory tree. Run `./him_bundle_oneliner.sh` to extract into a
  directory named `him_bundle` or provide a custom destination as the first
  argument, e.g. `./him_bundle_oneliner.sh /tmp/him`.
- `him_all_in_one.sh`: fully self-extracting installer with additional
  validation and cleanup to unpack the project into a chosen directory.

Need a traditional zip? Generate one locally without committing binaries:

```bash
poetry run python tools/gen_oneliner.py --zip-out dist/him_bundle.zip
```

## Getting started

The project uses [Poetry](https://python-poetry.org/) for dependency management.

```bash
./setup.sh
```

The script installs Poetry (if needed), resolves dependencies, prepares the storage directories, and prints a hardware profile tuned for an AMD Ryzen 7 7700 CPU alongside an NVIDIA GeForce RTX 4070 SUPER GPU with at least 7 TiB of disk space.

### Running the API server

```bash
poetry run python run_him.py --data-dir ./data
```

`run_him.py` prints the detected hardware profile, highlights any deviations from the recommended CPU/GPU/storage envelope, and then boots the FastAPI service (powered by Uvicorn). The server implements the endpoints described in `HIM_Spec_v1.1.md` and stores snapshots and tiles under the `data/` directory. The storage engine maintains snapshot metadata and tile statistics in `data/him.db`, tracks hint logs for the query planner, and persists tile payloads under `data/tiles/` using content-addressed paths.

To inspect the system profile without starting the server, run:

```bash
poetry run python run_him.py --profile-only
```

### Features

- Snapshot and tile metadata persisted in SQLite with automatic hotness tracking.
- Content-addressed tile payloads organised by stream/snapshot/level/coordinate.
- Query planner that fuses access telemetry with prefetch hints to prioritise tiles.
- Prefetch hints accepted via `/v1/prefetch` and reused by `/v1/query`.

### Running tests

```bash
poetry run pytest
```

## Sel Discord Bot (optional)

The `sel_bot` package runs the Discord agent. Required env: `DISCORD_BOT_TOKEN`, `OPENROUTER_API_KEY`.
Optional env includes `DISCORD_FULL_API_MODE_ENABLED`, `DISCORD_BATCH_WINDOW_SECONDS`,
`SEL_STATUS_THOUGHTS_ENABLED`, `SEL_STATUS_THOUGHTS_INTERVAL_SECONDS`, `SEL_STATUS_THOUGHTS`,
`SEL_PROFILE_BIO_UPDATES_ENABLED`, `SEL_PROFILE_BIO_INTERVAL_SECONDS`,
`SEL_MULTI_MESSAGE_MODE_ENABLED`, `SEL_MULTI_MESSAGE_MAX_PARTS`, `SEL_MULTI_MESSAGE_MIN_REPLY_CHARS`,
`SEL_MULTI_MESSAGE_BURST_MODE`, `SEL_DISCORD_USER_STYLE_ENABLED`, `SEL_DISCORD_REACTIONS_ENABLED`,
`SEL_DISCORD_REACTION_CHANCE`,
`OPENROUTER_MAIN_MODEL`, `OPENROUTER_UTIL_MODEL`, `OPENROUTER_MAIN_TEMP`,
`OPENROUTER_UTIL_TEMP`, `OPENROUTER_TOP_P`, `DATABASE_URL`, `WHITELIST_CHANNEL_IDS`,
`SEL_PERSONA_SEED`, `HIM_MEMORY_DIR`, `HIM_MEMORY_LEVELS`, `ENABLE_PROMPTS_V2`,
`PROMPTS_V2_ROLLOUT_PERCENTAGE`, `PROMPTS_V2_SIMPLIFIED_ROLLOUT_PERCENTAGE`,
`ELEVENLABS_API_KEY`, `ELEVENLABS_BASE_URL`, `ELEVENLABS_TTS_ENABLED`, `ELEVENLABS_TTS_MODEL`,
`ELEVENLABS_VOICE_ID`, `ELEVENLABS_TTS_OUTPUT_FORMAT`, `ELEVENLABS_TTS_LANGUAGE_CODE`,
`ELEVENLABS_TTS_MAX_CHARS`, `ELEVENLABS_STT_ENABLED`, `ELEVENLABS_STT_MODEL`,
`ELEVENLABS_STT_LANGUAGE_CODE`, `ELEVENLABS_STT_MAX_BYTES`,
`AGENT_AUTONOMY_ENABLED`, `AGENT_AUTONOMY_SAFE_AGENTS`, `AGENT_AUTONOMY_MIN_CONFIDENCE`,
`AGENT_AUTONOMY_CATALOG_REFRESH_SECONDS`, `AGENT_AUTONOMY_MAX_RESULT_CHARS`,
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
