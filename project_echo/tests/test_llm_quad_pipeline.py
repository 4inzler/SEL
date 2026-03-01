from __future__ import annotations

import json
import sys
import types
from types import MethodType, SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy")

# Minimal local stubs so tests can run even when optional runtime deps
# (pydantic/pydantic-settings) are unavailable in this environment.
if "pydantic" not in sys.modules:
    pydantic_stub = types.ModuleType("pydantic")

    class _AnyHttpUrl(str):
        pass

    def _field(*args, **kwargs):
        if "default_factory" in kwargs and callable(kwargs["default_factory"]):
            return kwargs["default_factory"]()
        if "default" in kwargs:
            return kwargs["default"]
        return args[0] if args else None

    def _field_validator(*args, **kwargs):
        def decorator(fn):
            return fn

        return decorator

    pydantic_stub.AnyHttpUrl = _AnyHttpUrl
    pydantic_stub.Field = _field
    pydantic_stub.field_validator = _field_validator
    sys.modules["pydantic"] = pydantic_stub

if "pydantic_settings" not in sys.modules:
    pydantic_settings_stub = types.ModuleType("pydantic_settings")

    class _BaseSettings:
        pass

    class _SettingsConfigDict(dict):
        pass

    pydantic_settings_stub.BaseSettings = _BaseSettings
    pydantic_settings_stub.SettingsConfigDict = _SettingsConfigDict
    sys.modules["pydantic_settings"] = pydantic_settings_stub

from sel_bot.llm_client import OpenRouterClient
from sel_bot.llm_client_localai import LocalAIClient


def _openrouter_settings(**overrides):
    base = {
        "openrouter_api_key": "test-key",
        "openrouter_referer": "http://localhost",
        "openrouter_title": "test",
        "openrouter_util_model": "util-model",
        "openrouter_main_model": "main-model",
        "openrouter_util_temp": 0.2,
        "openrouter_main_temp": 0.7,
        "openrouter_top_p": 0.9,
        "llm_dual_model_assist_enabled": True,
        "llm_dual_model_assist_allow_direct": True,
        "llm_dual_model_assist_direct_threshold": 0.9,
        "llm_quad_mode_enabled": True,
        "llm_quad_second_pass_min_chars": 220,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _localai_settings(**overrides):
    base = {
        "localai_base_url": "http://localhost:8080",
        "localai_api_key": "test-key",
        "localai_util_model": "util-model",
        "localai_main_model": "main-model",
        "localai_util_temp": 0.2,
        "localai_main_temp": 0.7,
        "llm_dual_model_assist_enabled": True,
        "llm_dual_model_assist_allow_direct": True,
        "llm_dual_model_assist_direct_threshold": 0.9,
        "llm_quad_mode_enabled": True,
        "llm_quad_second_pass_min_chars": 220,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_openrouter_quad_pipeline_runs_two_util_and_two_main_passes() -> None:
    client = OpenRouterClient(_openrouter_settings(llm_dual_model_assist_allow_direct=False), enable_cache=False)
    calls: list[str] = []

    async def fake_chat(self, *, model, messages, temperature, top_p=None, context_fingerprint=None, ttl_seconds=None):
        calls.append(model)
        if model == "util-model" and len(calls) == 1:
            return json.dumps(
                {
                    "draft": "first draft",
                    "confidence": 0.40,
                    "needs_main_model": True,
                    "reason": "initial draft",
                }
            )
        if model == "util-model" and len(calls) == 2:
            return json.dumps(
                {
                    "draft": "refined draft",
                    "confidence": 0.52,
                    "needs_main_model": True,
                    "reason": "still uncertain",
                }
            )
        if model == "main-model" and len(calls) == 3:
            return "verified first main reply"
        if model == "main-model" and len(calls) == 4:
            return "final second main reply"
        raise AssertionError(f"unexpected call sequence: {calls}")

    client._chat_completion = MethodType(fake_chat, client)  # type: ignore[method-assign]

    out = await client.generate_reply(
        messages=[{"role": "system", "content": "be helpful"}],
        user_content="please explain the architecture and tradeoffs in detail",
    )

    assert out == "final second main reply"
    assert calls == ["util-model", "util-model", "main-model", "main-model"]


@pytest.mark.asyncio
async def test_openrouter_assist_falls_back_to_draft_on_main_failure() -> None:
    client = OpenRouterClient(_openrouter_settings(llm_quad_mode_enabled=False), enable_cache=False)
    calls: list[str] = []

    async def fake_chat(self, *, model, messages, temperature, top_p=None, context_fingerprint=None, ttl_seconds=None):
        calls.append(model)
        if model == "util-model":
            return json.dumps(
                {
                    "draft": "assist fallback reply",
                    "confidence": 0.45,
                    "needs_main_model": True,
                    "reason": "needs verifier",
                }
            )
        if model == "main-model":
            raise RuntimeError("main model down")
        raise AssertionError(f"unexpected model {model}")

    client._chat_completion = MethodType(fake_chat, client)  # type: ignore[method-assign]

    out = await client.generate_reply(
        messages=[{"role": "system", "content": "be helpful"}],
        user_content="give me a careful answer",
    )

    assert out == "assist fallback reply"
    assert calls == ["util-model", "main-model"]


@pytest.mark.asyncio
async def test_localai_assist_direct_path_skips_main_model() -> None:
    client = LocalAIClient(_localai_settings(llm_quad_mode_enabled=False), enable_cache=False)
    calls: list[str] = []

    async def fake_chat(self, *, model, messages, temperature, top_p=None, context_fingerprint=None, ttl_seconds=None):
        calls.append(model)
        if model == "util-model":
            return json.dumps(
                {
                    "draft": "quick direct reply",
                    "confidence": 0.97,
                    "needs_main_model": False,
                    "reason": "simple prompt",
                }
            )
        raise AssertionError("main model should not be called on direct path")

    client._chat_completion = MethodType(fake_chat, client)  # type: ignore[method-assign]

    out = await client.generate_reply(
        messages=[{"role": "system", "content": "be concise"}],
        user_content="hey",
    )

    assert out == "quick direct reply"
    assert calls == ["util-model"]
