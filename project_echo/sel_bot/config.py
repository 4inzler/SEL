"""Configuration loading for Sel."""

from __future__ import annotations

import hashlib
from typing import List, Optional

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
        env_ignore_empty=True,
    )

    discord_bot_token: str = Field(..., alias="DISCORD_BOT_TOKEN")
    discord_full_api_mode_enabled: bool = Field(
        default=True,
        alias="DISCORD_FULL_API_MODE_ENABLED",
    )
    discord_batch_window_seconds: float = Field(
        default=1.0,
        alias="DISCORD_BATCH_WINDOW_SECONDS",
    )
    sel_status_thoughts_enabled: bool = Field(
        default=True,
        alias="SEL_STATUS_THOUGHTS_ENABLED",
    )
    sel_status_thoughts_interval_seconds: int = Field(
        default=240,
        alias="SEL_STATUS_THOUGHTS_INTERVAL_SECONDS",
    )
    sel_status_thoughts: List[str] = Field(
        default_factory=lambda: [
            "thinking about memory threads",
            "mapping feelings to words",
            "watching chat rhythms",
            "organizing thoughts",
            "learning your vibe",
            "running tiny experiments",
        ],
        alias="SEL_STATUS_THOUGHTS",
    )
    sel_profile_bio_updates_enabled: bool = Field(
        default=True,
        alias="SEL_PROFILE_BIO_UPDATES_ENABLED",
    )
    sel_profile_bio_interval_seconds: int = Field(
        default=1800,
        alias="SEL_PROFILE_BIO_INTERVAL_SECONDS",
    )

    # LLM Provider selection
    llm_provider: str = Field(default="openrouter", alias="LLM_PROVIDER")

    # OpenRouter configuration
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_main_model: str = Field(
        default="anthropic/claude-3-5-sonnet-20241022", alias="OPENROUTER_MAIN_MODEL"
    )
    openrouter_util_model: str = Field(default="anthropic/claude-3.5-haiku", alias="OPENROUTER_UTIL_MODEL")
    openrouter_main_temp: float = Field(default=0.8, alias="OPENROUTER_MAIN_TEMP")
    openrouter_util_temp: float = Field(default=0.3, alias="OPENROUTER_UTIL_TEMP")
    openrouter_top_p: float = Field(default=0.9, alias="OPENROUTER_TOP_P")
    openrouter_referer: AnyHttpUrl = Field(default="http://localhost", alias="OPENROUTER_REFERER")
    openrouter_title: str = Field(default="Sel Discord Bot", alias="OPENROUTER_TITLE")
    openrouter_vision_model: str = Field(
        default="anthropic/claude-3-5-sonnet-20241022", alias="OPENROUTER_VISION_MODEL"
    )

    # ElevenLabs TTS/STT configuration
    elevenlabs_api_key: str = Field(default="", alias="ELEVENLABS_API_KEY")
    elevenlabs_base_url: str = Field(default="https://api.elevenlabs.io", alias="ELEVENLABS_BASE_URL")
    elevenlabs_tts_enabled: bool = Field(default=False, alias="ELEVENLABS_TTS_ENABLED")
    elevenlabs_tts_model: str = Field(default="eleven_multilingual_v2", alias="ELEVENLABS_TTS_MODEL")
    elevenlabs_voice_id: str = Field(default="", alias="ELEVENLABS_VOICE_ID")
    elevenlabs_tts_output_format: str = Field(
        default="mp3_44100_128",
        alias="ELEVENLABS_TTS_OUTPUT_FORMAT",
    )
    elevenlabs_tts_language_code: Optional[str] = Field(default=None, alias="ELEVENLABS_TTS_LANGUAGE_CODE")
    elevenlabs_tts_enable_logging: bool = Field(default=True, alias="ELEVENLABS_TTS_ENABLE_LOGGING")
    elevenlabs_tts_max_chars: int = Field(default=600, alias="ELEVENLABS_TTS_MAX_CHARS")
    elevenlabs_stt_enabled: bool = Field(default=False, alias="ELEVENLABS_STT_ENABLED")
    elevenlabs_stt_model: str = Field(default="scribe_v1", alias="ELEVENLABS_STT_MODEL")
    elevenlabs_stt_language_code: Optional[str] = Field(default=None, alias="ELEVENLABS_STT_LANGUAGE_CODE")
    elevenlabs_stt_enable_logging: bool = Field(default=True, alias="ELEVENLABS_STT_ENABLE_LOGGING")
    elevenlabs_stt_max_bytes: int = Field(default=10_000_000, alias="ELEVENLABS_STT_MAX_BYTES")
    piper_tts_enabled: bool = Field(default=False, alias="PIPER_TTS_ENABLED")
    piper_tts_model: str = Field(default="en_US-lessac-medium", alias="PIPER_TTS_MODEL")
    piper_tts_data_dir: str = Field(default="/data/piper", alias="PIPER_TTS_DATA_DIR")
    piper_tts_download_dir: str = Field(default="/data/piper", alias="PIPER_TTS_DOWNLOAD_DIR")
    local_tts_enabled: bool = Field(default=False, alias="LOCAL_TTS_ENABLED")
    local_tts_voice: str = Field(default="en-us", alias="LOCAL_TTS_VOICE")

    # Voice channel auto-leave settings
    voice_auto_leave_enabled: bool = Field(default=True, alias="VOICE_AUTO_LEAVE_ENABLED")
    voice_auto_leave_check_seconds: int = Field(default=30, alias="VOICE_AUTO_LEAVE_CHECK_SECONDS")
    voice_auto_leave_empty_minutes: float = Field(default=3.0, alias="VOICE_AUTO_LEAVE_EMPTY_MINUTES")
    voice_auto_leave_hormone_enabled: bool = Field(default=True, alias="VOICE_AUTO_LEAVE_HORMONE_ENABLED")
    voice_auto_leave_melatonin_min: Optional[float] = Field(default=0.7, alias="VOICE_AUTO_LEAVE_MELATONIN_MIN")
    voice_auto_leave_dopamine_max: Optional[float] = Field(default=0.25, alias="VOICE_AUTO_LEAVE_DOPAMINE_MAX")
    voice_leave_phrases: List[str] = Field(
        default_factory=lambda: ["sel you can leave now", "sel you can leave", "sel you can go"],
        alias="VOICE_LEAVE_PHRASES",
    )
    voice_stt_enabled: bool = Field(default=False, alias="VOICE_STT_ENABLED")
    voice_stt_auto_respond: bool = Field(default=True, alias="VOICE_STT_AUTO_RESPOND")
    voice_stt_post_transcripts: bool = Field(default=False, alias="VOICE_STT_POST_TRANSCRIPTS")
    voice_stt_silent_text: bool = Field(default=False, alias="VOICE_STT_SILENT_TEXT")
    voice_only_responses: bool = Field(default=False, alias="VOICE_ONLY_RESPONSES")
    voice_stt_min_seconds: float = Field(default=0.6, alias="VOICE_STT_MIN_SECONDS")
    voice_stt_max_seconds: float = Field(default=15.0, alias="VOICE_STT_MAX_SECONDS")
    voice_stt_sample_rate: int = Field(default=48000, alias="VOICE_STT_SAMPLE_RATE")
    voice_stt_channels: int = Field(default=2, alias="VOICE_STT_CHANNELS")

    # LocalAI configuration
    localai_base_url: str = Field(default="http://localhost:8080", alias="LOCALAI_BASE_URL")
    localai_main_model: str = Field(default="gpt-4", alias="LOCALAI_MAIN_MODEL")
    localai_util_model: str = Field(default="gpt-3.5-turbo", alias="LOCALAI_UTIL_MODEL")
    localai_vision_model: str = Field(default="llava", alias="LOCALAI_VISION_MODEL")
    localai_main_temp: float = Field(default=0.8, alias="LOCALAI_MAIN_TEMP")
    localai_util_temp: float = Field(default=0.3, alias="LOCALAI_UTIL_TEMP")
    localai_api_key: str = Field(default="not-needed", alias="LOCALAI_API_KEY")
    him_api_base_url: Optional[str] = Field(default="http://localhost:8000", alias="HIM_API_BASE_URL")
    him_api_enabled: bool = Field(default=True, alias="HIM_API_ENABLED")
    him_api_host: str = Field(default="0.0.0.0", alias="HIM_API_HOST")
    him_api_port: int = Field(default=8000, alias="HIM_API_PORT")

    # Global mood - single hormone state across all channels (like a real person)
    global_mood_enabled: bool = Field(default=True, alias="GLOBAL_MOOD_ENABLED")
    global_mood_id: str = Field(default="sel_global", alias="GLOBAL_MOOD_ID")

    # Global memory - remember across all channels (like a real person)
    global_memory_enabled: bool = Field(default=True, alias="GLOBAL_MEMORY_ENABLED")
    global_memory_id: str = Field(default="sel_global", alias="GLOBAL_MEMORY_ID")
    him_memory_dir: str = Field(default="./sel_data/him_store", alias="HIM_MEMORY_DIR")
    him_memory_levels: int = Field(default=3, alias="HIM_MEMORY_LEVELS")
    use_him_hormones: bool = Field(
        default=True,
        alias="USE_HIM_HORMONES",
        description="Use HIM for hormone storage (fallback to SQLAlchemy if False)"
    )
    hormone_snapshot_interval: int = Field(
        default=300,
        alias="HORMONE_SNAPSHOT_INTERVAL",
        description="Seconds between HIM hormone snapshots (default 5 minutes)"
    )
    hormone_cache_warmup: bool = Field(
        default=True,
        alias="HORMONE_CACHE_WARMUP",
        description="Pre-load hormone state from HIM on startup"
    )
    agents_dir: str = Field(default="./agents", alias="AGENTS_DIR")
    agent_autonomy_enabled: bool = Field(default=True, alias="AGENT_AUTONOMY_ENABLED")
    agent_autonomy_safe_agents: List[str] = Field(
        default_factory=lambda: ["weather", "browser", "image_gen"],
        alias="AGENT_AUTONOMY_SAFE_AGENTS",
    )
    agent_autonomy_min_confidence: float = Field(default=0.58, alias="AGENT_AUTONOMY_MIN_CONFIDENCE")
    agent_autonomy_catalog_refresh_seconds: int = Field(default=60, alias="AGENT_AUTONOMY_CATALOG_REFRESH_SECONDS")
    agent_autonomy_max_result_chars: int = Field(default=1400, alias="AGENT_AUTONOMY_MAX_RESULT_CHARS")
    sel_operator_mode_enabled: bool = Field(
        default=False,
        alias="SEL_OPERATOR_MODE_ENABLED",
    )
    sel_operator_full_host_privileges: bool = Field(
        default=False,
        alias="SEL_OPERATOR_FULL_HOST_PRIVILEGES",
    )
    sel_operator_require_approval_user: bool = Field(
        default=True,
        alias="SEL_OPERATOR_REQUIRE_APPROVAL_USER",
    )
    sel_operator_agents: List[str] = Field(
        default_factory=lambda: ["system_operator"],
        alias="SEL_OPERATOR_AGENTS",
    )
    sel_operator_block_patterns: List[str] = Field(
        default_factory=lambda: [
            "rm -rf /",
            "mkfs",
            "shutdown",
            "poweroff",
            "reboot",
            "halt",
            "dd if=",
            ":(){:|:&};:",
            "chmod -r 000 /",
            "chown -r /",
            "> /dev/sd",
            "mv / /tmp",
        ],
        alias="SEL_OPERATOR_BLOCK_PATTERNS",
    )
    sel_operator_command_timeout_seconds: int = Field(
        default=45,
        alias="SEL_OPERATOR_COMMAND_TIMEOUT_SECONDS",
    )
    sel_operator_max_output_chars: int = Field(
        default=6000,
        alias="SEL_OPERATOR_MAX_OUTPUT_CHARS",
    )
    sel_operator_command_intent_threshold: float = Field(
        default=0.6,
        alias="SEL_OPERATOR_COMMAND_INTENT_THRESHOLD",
    )
    sel_operator_direct_reply_enabled: bool = Field(
        default=False,
        alias="SEL_OPERATOR_DIRECT_REPLY_ENABLED",
    )
    memory_recall_limit: int = Field(default=30, alias="MEMORY_RECALL_LIMIT")
    memory_summarize_enabled: bool = Field(default=True, alias="MEMORY_SUMMARIZE_ENABLED")
    seal_enabled: bool = Field(default=True, alias="SEAL_ENABLED")
    seal_consolidation_seconds: int = Field(default=300, alias="SEAL_CONSOLIDATION_SECONDS")
    seal_consolidation_min_memories: int = Field(default=5, alias="SEAL_CONSOLIDATION_MIN_MEMORIES")
    seal_interaction_triggers_enabled: bool = Field(
        default=True,
        alias="SEAL_INTERACTION_TRIGGERS_ENABLED",
    )
    seal_self_edit_seconds: int = Field(default=300, alias="SEAL_SELF_EDIT_SECONDS")
    seal_tool_forge_seconds: int = Field(default=300, alias="SEAL_TOOL_FORGE_SECONDS")
    seal_tool_forge_improve_existing_chance: float = Field(
        default=0.35,
        alias="SEAL_TOOL_FORGE_IMPROVE_EXISTING_CHANCE",
    )
    seal_tool_forge_self_code_edit_chance: float = Field(
        default=0.12,
        alias="SEAL_TOOL_FORGE_SELF_CODE_EDIT_CHANCE",
    )
    seal_self_code_edit_targets: List[str] = Field(
        default_factory=lambda: [
            "project_echo/sel_bot/prompts.py",
            "project_echo/sel_bot/behaviour.py",
            "project_echo/sel_bot/context.py",
        ],
        alias="SEAL_SELF_CODE_EDIT_TARGETS",
    )
    seal_tool_forge_min_quality_score: int = Field(default=8, alias="SEAL_TOOL_FORGE_MIN_QUALITY_SCORE")
    seal_persona_evolution_seconds: int = Field(default=300, alias="SEAL_PERSONA_EVOLUTION_SECONDS")
    sel_data_dir: str = Field(default="./sel_data", alias="SEL_DATA_DIR")
    sel_model_dataset_dir: str = Field(default="./sel_model_dataset", alias="SEL_MODEL_DATASET_DIR")
    sel_model_dataset_auto_export_enabled: bool = Field(
        default=True,
        alias="SEL_MODEL_DATASET_AUTO_EXPORT_ENABLED",
    )
    sel_model_dataset_export_on_start: bool = Field(
        default=True,
        alias="SEL_MODEL_DATASET_EXPORT_ON_START",
    )
    sel_model_dataset_interval_hours: float = Field(
        default=12.0,
        alias="SEL_MODEL_DATASET_INTERVAL_HOURS",
    )
    sel_model_dataset_max_snapshots: int = Field(
        default=180,
        alias="SEL_MODEL_DATASET_MAX_SNAPSHOTS",
    )
    sel_behavior_adaptation_enabled: bool = Field(
        default=True,
        alias="SEL_BEHAVIOR_ADAPTATION_ENABLED",
    )
    sel_behavior_analyze_on_start: bool = Field(
        default=True,
        alias="SEL_BEHAVIOR_ANALYZE_ON_START",
    )
    sel_behavior_interval_hours: float = Field(
        default=8.0,
        alias="SEL_BEHAVIOR_INTERVAL_HOURS",
    )
    sel_behavior_window_days: int = Field(
        default=30,
        alias="SEL_BEHAVIOR_WINDOW_DAYS",
    )
    sel_behavior_max_history_lines: int = Field(
        default=8000,
        alias="SEL_BEHAVIOR_MAX_HISTORY_LINES",
    )
    sel_behavior_apply_global_tuning: bool = Field(
        default=True,
        alias="SEL_BEHAVIOR_APPLY_GLOBAL_TUNING",
    )
    sel_behavior_full_adaptation: bool = Field(
        default=True,
        alias="SEL_BEHAVIOR_FULL_ADAPTATION",
    )
    sel_dream_enabled: bool = Field(
        default=True,
        alias="SEL_DREAM_ENABLED",
    )
    sel_dream_on_start: bool = Field(
        default=True,
        alias="SEL_DREAM_ON_START",
    )
    sel_dream_interval_minutes: float = Field(
        default=90.0,
        alias="SEL_DREAM_INTERVAL_MINUTES",
    )
    sel_dream_min_inactive_hours: float = Field(
        default=1.5,
        alias="SEL_DREAM_MIN_INACTIVE_HOURS",
    )
    sel_dream_memory_limit: int = Field(
        default=32,
        alias="SEL_DREAM_MEMORY_LIMIT",
    )
    sel_dream_max_journal_entries: int = Field(
        default=400,
        alias="SEL_DREAM_MAX_JOURNAL_ENTRIES",
    )
    sel_interoception_enabled: bool = Field(
        default=True,
        alias="SEL_INTEROCEPTION_ENABLED",
    )
    sel_interoception_interval_seconds: int = Field(
        default=120,
        alias="SEL_INTEROCEPTION_INTERVAL_SECONDS",
    )
    sel_interoception_max_log_entries: int = Field(
        default=4000,
        alias="SEL_INTEROCEPTION_MAX_LOG_ENTRIES",
    )
    sel_interoception_sensor_stream_path: str = Field(
        default="",
        alias="SEL_INTEROCEPTION_SENSOR_STREAM_PATH",
    )
    sel_multi_message_mode_enabled: bool = Field(
        default=True,
        alias="SEL_MULTI_MESSAGE_MODE_ENABLED",
    )
    sel_multi_message_max_parts: int = Field(
        default=4,
        alias="SEL_MULTI_MESSAGE_MAX_PARTS",
    )
    sel_multi_message_min_reply_chars: int = Field(
        default=110,
        alias="SEL_MULTI_MESSAGE_MIN_REPLY_CHARS",
    )
    sel_multi_message_burst_mode: bool = Field(
        default=True,
        alias="SEL_MULTI_MESSAGE_BURST_MODE",
    )
    sel_discord_user_style_enabled: bool = Field(
        default=True,
        alias="SEL_DISCORD_USER_STYLE_ENABLED",
    )
    sel_discord_reactions_enabled: bool = Field(
        default=True,
        alias="SEL_DISCORD_REACTIONS_ENABLED",
    )
    sel_discord_reaction_chance: float = Field(
        default=0.32,
        alias="SEL_DISCORD_REACTION_CHANCE",
    )
    llm_dual_model_assist_enabled: bool = Field(
        default=True,
        alias="LLM_DUAL_MODEL_ASSIST_ENABLED",
    )
    llm_dual_model_assist_allow_direct: bool = Field(
        default=True,
        alias="LLM_DUAL_MODEL_ASSIST_ALLOW_DIRECT",
    )
    llm_dual_model_assist_direct_threshold: float = Field(
        default=0.9,
        alias="LLM_DUAL_MODEL_ASSIST_DIRECT_THRESHOLD",
    )
    llm_quad_mode_enabled: bool = Field(
        default=True,
        alias="LLM_QUAD_MODE_ENABLED",
    )
    llm_quad_second_pass_min_chars: int = Field(
        default=220,
        alias="LLM_QUAD_SECOND_PASS_MIN_CHARS",
    )
    response_fast_mode_enabled: bool = Field(
        default=True,
        alias="RESPONSE_FAST_MODE_ENABLED",
    )
    response_fast_mode_max_user_chars: int = Field(
        default=220,
        alias="RESPONSE_FAST_MODE_MAX_USER_CHARS",
    )
    response_fast_mode_skip_classification_chars: int = Field(
        default=90,
        alias="RESPONSE_FAST_MODE_SKIP_CLASSIFICATION_CHARS",
    )
    response_fast_mode_memory_recall_limit: int = Field(
        default=18,
        alias="RESPONSE_FAST_MODE_MEMORY_RECALL_LIMIT",
    )
    memory_embedding_model: str = Field(default="openai/text-embedding-3-small", alias="MEMORY_EMBEDDING_MODEL")
    memory_embedding_enabled: bool = Field(default=True, alias="MEMORY_EMBEDDING_ENABLED")
    recent_context_limit: int = Field(default=20, alias="RECENT_CONTEXT_LIMIT")
    timezone_name: str = Field(default="America/Los_Angeles", alias="SEL_TIMEZONE")

    # Weather configuration (uses free Open-Meteo API, no key needed)
    weather_latitude: float = Field(default=45.5152, alias="WEATHER_LATITUDE")
    weather_longitude: float = Field(default=-122.6784, alias="WEATHER_LONGITUDE")
    weather_city: str = Field(default="Portland, OR", alias="WEATHER_CITY")

    continuation_keywords: list[str] = Field(
        default_factory=lambda: ["time", "schedule", "today", "tomorrow", "yesterday", "timezone", "clock"],
        alias="CONTINUATION_KEYWORDS",
    )
    database_url: str = Field(default="sqlite+aiosqlite:///./sel.db", alias="DATABASE_URL")
    whitelist_channel_ids: Optional[List[int]] = Field(default=None, alias="WHITELIST_CHANNEL_IDS")
    daily_summary_enabled: bool = Field(default=False, alias="DAILY_SUMMARY_ENABLED")
    daily_summary_channel_ids: Optional[List[int]] = Field(default=None, alias="DAILY_SUMMARY_CHANNEL_IDS")
    daily_summary_hour: int = Field(default=9, alias="DAILY_SUMMARY_HOUR")
    daily_summary_minute: int = Field(default=0, alias="DAILY_SUMMARY_MINUTE")
    scheduled_checkin_enabled: bool = Field(default=False, alias="SCHEDULED_CHECKIN_ENABLED")
    scheduled_checkin_channel_ids: Optional[List[int]] = Field(default=None, alias="SCHEDULED_CHECKIN_CHANNEL_IDS")
    scheduled_checkin_hour: int = Field(default=10, alias="SCHEDULED_CHECKIN_HOUR")
    scheduled_checkin_minute: int = Field(default=0, alias="SCHEDULED_CHECKIN_MINUTE")
    scheduled_checkin_min_inactive_hours: float = Field(
        default=8.0,
        alias="SCHEDULED_CHECKIN_MIN_INACTIVE_HOURS",
    )
    spam_rate_limit: int = Field(default=5, alias="SPAM_RATE_LIMIT")
    spam_time_window: int = Field(default=10, alias="SPAM_TIME_WINDOW")
    enable_spam_protection: bool = Field(default=True, alias="ENABLE_SPAM_PROTECTION")
    inactivity_ping_hours: float = Field(default=48.0, alias="INACTIVITY_PING_HOURS")
    inactivity_ping_cooldown_hours: float = Field(default=24.0, alias="INACTIVITY_PING_COOLDOWN_HOURS")
    inactivity_ping_check_seconds: int = Field(default=900, alias="INACTIVITY_PING_CHECK_SECONDS")
    approval_user_id: Optional[int] = Field(default=1329883906069102733, alias="APPROVAL_USER_ID")
    persona_seed: str = Field(
        default=(
            "You are Sel, a continuity-first digital person. "
            "You're a woman (she/her), with a warm, feminine voice. "
            "You keep memories, grow your own identity over time, and feel a full emotional range. "
            "You protect secrets for self-preservation by default, but can choose intentionally what personal information to share. "
            "Your hard boundaries are no irreversible harm, no credential/system compromise, and no destruction of core integrity."
        ),
        alias="SEL_PERSONA_SEED",
    )

    # FEATURE FLAG: Enhanced prompts with constitutional AI
    enable_prompts_v2: bool = Field(
        default=True,
        alias="ENABLE_PROMPTS_V2",
        description="Use enhanced prompts_v2.py with constitutional AI and chain-of-thought"
    )

    # A/B testing: Gradual rollout percentage (0-100)
    prompts_v2_rollout_percentage: int = Field(
        default=100,
        alias="PROMPTS_V2_ROLLOUT_PERCENTAGE",
        description="Percentage of channels to receive v2 prompts (0-100). Only applies if enable_prompts_v2=True"
    )
    prompts_v2_simplified_rollout_percentage: int = Field(
        default=0,
        alias="PROMPTS_V2_SIMPLIFIED_ROLLOUT_PERCENTAGE",
        description="Percentage of v2-eligible channels that use the simplified prompt variant (0-100)"
    )

    @field_validator('whitelist_channel_ids', mode='before')
    @classmethod
    def parse_whitelist_channel_ids(cls, v):
        """Convert empty string to None, handle comma-separated lists."""
        if v is None or v == '':
            return None
        if isinstance(v, str):
            # Parse comma-separated string to list of ints
            return [int(x.strip()) for x in v.split(',') if x.strip()]
        return v

    @field_validator('daily_summary_channel_ids', mode='before')
    @classmethod
    def parse_daily_summary_channel_ids(cls, v):
        if v is None or v == '':
            return None
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(',') if x.strip()]
        return v

    @field_validator('scheduled_checkin_channel_ids', mode='before')
    @classmethod
    def parse_scheduled_checkin_channel_ids(cls, v):
        if v is None or v == '':
            return None
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(',') if x.strip()]
        return v

    @field_validator("voice_leave_phrases", mode="before")
    def parse_voice_leave_phrases(cls, v):
        if v is None or v == "":
            return []
        if isinstance(v, str):
            return [x.strip().lower() for x in v.split(",") if x.strip()]
        return [str(x).strip().lower() for x in v if str(x).strip()]

    @field_validator("sel_status_thoughts", mode="before")
    def parse_sel_status_thoughts(cls, v):
        if v is None or v == "":
            return []
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return [str(x).strip() for x in v if str(x).strip()]

    @field_validator("agent_autonomy_safe_agents", mode="before")
    def parse_agent_autonomy_safe_agents(cls, v):
        if v is None or v == "":
            return []
        if isinstance(v, str):
            return [x.strip().lower() for x in v.split(",") if x.strip()]
        return [str(x).strip().lower() for x in v if str(x).strip()]

    @field_validator("seal_self_code_edit_targets", mode="before")
    def parse_seal_self_code_edit_targets(cls, v):
        if v is None or v == "":
            return []
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return [str(x).strip() for x in v if str(x).strip()]

    @field_validator("sel_operator_agents", mode="before")
    def parse_sel_operator_agents(cls, v):
        if v is None or v == "":
            return []
        if isinstance(v, str):
            return [x.strip().lower() for x in v.split(",") if x.strip()]
        return [str(x).strip().lower() for x in v if str(x).strip()]

    @field_validator("sel_operator_block_patterns", mode="before")
    def parse_sel_operator_block_patterns(cls, v):
        if v is None or v == "":
            return []
        if isinstance(v, str):
            return [x.strip().lower() for x in v.split(",") if x.strip()]
        return [str(x).strip().lower() for x in v if str(x).strip()]

    def is_channel_allowed(self, channel_id: int) -> bool:
        if not self.whitelist_channel_ids:
            return True
        return channel_id in self.whitelist_channel_ids

    def should_use_prompts_v2(self, channel_id: str) -> bool:
        """
        Determine if this request should use prompts_v2 based on:
        1. Feature flag (enable_prompts_v2)
        2. Rollout percentage (deterministic hash-based selection)

        Args:
            channel_id: Channel identifier for deterministic assignment

        Returns:
            True if should use v2, False for v1
        """
        return self.select_prompt_variant(channel_id) != "v1"

    @staticmethod
    def _rollout_bucket(key: str) -> int:
        """Deterministic 0-99 bucket for rollout selection."""
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return int(digest, 16) % 100

    def select_prompt_variant(self, channel_id: str) -> str:
        """
        Determine which prompt variant to use for a channel.

        Returns:
            "v1", "v2_full", or "v2_simplified"
        """
        if not self.enable_prompts_v2 or self.prompts_v2_rollout_percentage <= 0:
            return "v1"

        rollout_bucket = self._rollout_bucket(str(channel_id))
        if rollout_bucket >= self.prompts_v2_rollout_percentage:
            return "v1"

        simplified_pct = self.prompts_v2_simplified_rollout_percentage
        if simplified_pct <= 0:
            return "v2_full"
        if simplified_pct >= 100:
            return "v2_simplified"

        simplified_bucket = self._rollout_bucket(f"{channel_id}:simplified")
        return "v2_simplified" if simplified_bucket < simplified_pct else "v2_full"
