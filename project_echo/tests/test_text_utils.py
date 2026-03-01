from __future__ import annotations

from sel_bot.client_modules.text_utils import match_agent_request


def test_match_agent_request_agent_phrase_suffix() -> None:
    result = match_agent_request("weather agent forecast tomorrow", ["weather"])
    assert result == ("weather", "forecast tomorrow")


def test_match_agent_request_tool_phrase_suffix() -> None:
    result = match_agent_request("browser tool https://example.com", ["browser"])
    assert result == ("browser", "https://example.com")
