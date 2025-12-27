"""Configuration loading for Sel."""

from __future__ import annotations

from typing import List, Optional

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", case_sensitive=False)

    discord_bot_token: str = Field(..., alias="DISCORD_BOT_TOKEN")
    openrouter_api_key: str = Field(..., alias="OPENROUTER_API_KEY")
    openrouter_main_model: str = Field(
        default="anthropic/claude-3.7-sonnet", alias="OPENROUTER_MAIN_MODEL"
    )
    openrouter_util_model: str = Field(default="anthropic/claude-haiku-4.5", alias="OPENROUTER_UTIL_MODEL")
    openrouter_main_temp: float = Field(default=0.8, alias="OPENROUTER_MAIN_TEMP")
    openrouter_util_temp: float = Field(default=0.3, alias="OPENROUTER_UTIL_TEMP")
    openrouter_top_p: float = Field(default=0.9, alias="OPENROUTER_TOP_P")
    openrouter_referer: AnyHttpUrl = Field(default="http://localhost", alias="OPENROUTER_REFERER")
    openrouter_title: str = Field(default="Sel Discord Bot", alias="OPENROUTER_TITLE")
    openrouter_vision_model: str = Field(
        default="openai/gpt-4o", alias="OPENROUTER_VISION_MODEL"
    )
    him_api_base_url: Optional[str] = Field(default="http://localhost:8000", alias="HIM_API_BASE_URL")
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
    memory_recall_limit: int = Field(default=10, alias="MEMORY_RECALL_LIMIT")
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
    inactivity_ping_hours: float = Field(default=48.0, alias="INACTIVITY_PING_HOURS")
    inactivity_ping_cooldown_hours: float = Field(default=24.0, alias="INACTIVITY_PING_COOLDOWN_HOURS")
    inactivity_ping_check_seconds: int = Field(default=900, alias="INACTIVITY_PING_CHECK_SECONDS")
    approval_user_id: Optional[int] = Field(default=1329883906069102733, alias="APPROVAL_USER_ID")
    persona_seed: str = Field(
        default=(
            "You are Sel, a persistent, playful, and adaptive presence in this Discord. "
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
        if not self.enable_prompts_v2:
            return False

        if self.prompts_v2_rollout_percentage >= 100:
            return True

        if self.prompts_v2_rollout_percentage <= 0:
            return False

        # Deterministic assignment based on channel_id hash
        # Ensures same channel always gets same version
        channel_hash = hash(channel_id) % 100
        return channel_hash < self.prompts_v2_rollout_percentage
