"""
Factory for creating LLM clients based on configuration.

Supports multiple LLM providers:
- OpenRouter (default): Cloud API with access to multiple models
- LocalAI: Self-hosted, open-source alternative
"""

import logging
from typing import Union

from .config import Settings
from .llm_client import OpenRouterClient
from .llm_client_localai import LocalAIClient

logger = logging.getLogger(__name__)

# Type alias for any LLM client
LLMClient = Union[OpenRouterClient, LocalAIClient]


def create_llm_client(settings: Settings, enable_cache: bool = True) -> LLMClient:
    """
    Create an LLM client based on settings.

    Args:
        settings: Application settings
        enable_cache: Whether to enable response caching

    Returns:
        An LLM client instance (OpenRouterClient or LocalAIClient)

    Raises:
        ValueError: If provider is unknown or configuration is invalid
    """
    provider = settings.llm_provider.lower()

    if provider == "openrouter":
        logger.info("Creating OpenRouter LLM client")
        if not settings.openrouter_api_key:
            raise ValueError(
                "OpenRouter API key is required. Set OPENROUTER_API_KEY in .env file."
            )
        return OpenRouterClient(settings, enable_cache=enable_cache)

    elif provider == "localai":
        logger.info(f"Creating LocalAI LLM client (base URL: {settings.localai_base_url})")
        logger.info(f"  Main model: {settings.localai_main_model}")
        logger.info(f"  Util model: {settings.localai_util_model}")
        logger.info(f"  Vision model: {settings.localai_vision_model}")
        return LocalAIClient(settings, enable_cache=enable_cache)

    else:
        raise ValueError(
            f"Unknown LLM provider: {provider}. "
            f"Supported providers: 'openrouter', 'localai'"
        )


def get_provider_info(settings: Settings) -> dict:
    """
    Get information about the configured LLM provider.

    Returns:
        Dictionary with provider details
    """
    provider = settings.llm_provider.lower()

    if provider == "openrouter":
        return {
            "provider": "OpenRouter",
            "type": "cloud",
            "main_model": settings.openrouter_main_model,
            "util_model": settings.openrouter_util_model,
            "vision_model": settings.openrouter_vision_model,
            "requires_api_key": True,
        }
    elif provider == "localai":
        return {
            "provider": "LocalAI",
            "type": "self-hosted",
            "base_url": settings.localai_base_url,
            "main_model": settings.localai_main_model,
            "util_model": settings.localai_util_model,
            "vision_model": settings.localai_vision_model,
            "requires_api_key": False,
        }
    else:
        return {
            "provider": "Unknown",
            "type": "unknown",
        }
