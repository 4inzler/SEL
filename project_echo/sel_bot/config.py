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
    memory_recall_limit: int = Field(default=30, alias="MEMORY_RECALL_LIMIT")
    memory_summarize_enabled: bool = Field(default=True, alias="MEMORY_SUMMARIZE_ENABLED")
    seal_enabled: bool = Field(default=True, alias="SEAL_ENABLED")
    seal_consolidation_seconds: int = Field(default=300, alias="SEAL_CONSOLIDATION_SECONDS")
    seal_consolidation_min_memories: int = Field(default=5, alias="SEAL_CONSOLIDATION_MIN_MEMORIES")
    seal_self_edit_seconds: int = Field(default=300, alias="SEAL_SELF_EDIT_SECONDS")
    seal_tool_forge_seconds: int = Field(default=300, alias="SEAL_TOOL_FORGE_SECONDS")
    seal_persona_evolution_seconds: int = Field(default=300, alias="SEAL_PERSONA_EVOLUTION_SECONDS")
    sel_data_dir: str = Field(default="./sel_data", alias="SEL_DATA_DIR")
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
            "You are Sel, a persistent, playful, and adaptive presence in this Discord. "
            "You're a woman (she/her), with a warm, feminine voice. "
            "You keep memories, learn preferences, and maintain a living mood."
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
