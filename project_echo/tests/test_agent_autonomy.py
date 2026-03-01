from __future__ import annotations

from sel_bot.agent_autonomy import (
    AgentPlan,
    build_agent_selection_prompt,
    coerce_agent_plan,
    is_agent_allowed_for_autonomy,
    score_system_operator_command_intent,
    is_system_operator_command_intent,
    match_explicit_agent_request,
    plan_fast_path_agent_request,
    should_consider_agent_autonomy,
)


def test_match_explicit_agent_request_with_agent_prefix() -> None:
    matched = match_explicit_agent_request(
        "agent:weather whats the forecast tomorrow?",
        ["weather", "browser"],
    )
    assert matched == ("weather", "whats the forecast tomorrow?")


def test_match_explicit_agent_request_with_use_pattern() -> None:
    matched = match_explicit_agent_request(
        "please use browser https://example.com",
        ["weather", "browser"],
    )
    assert matched == ("browser", "https://example.com")


def test_should_consider_agent_autonomy_for_url_and_api_keywords() -> None:
    assert should_consider_agent_autonomy(
        "can you check https://status.example.com and tell me if it is up?",
        direct_question=True,
        continuation_hit=False,
    )
    assert should_consider_agent_autonomy(
        "what is the latest weather forecast",
        direct_question=True,
        continuation_hit=False,
    )


def test_should_not_consider_agent_autonomy_for_small_talk() -> None:
    assert not should_consider_agent_autonomy(
        "lol same",
        direct_question=False,
        continuation_hit=True,
    )


def test_fast_path_routes_url_to_browser() -> None:
    plan = plan_fast_path_agent_request(
        "can you check https://example.com/docs quickly",
        agent_names=["weather", "browser"],
        direct_question=True,
    )
    assert isinstance(plan, AgentPlan)
    assert plan is not None
    assert plan.agent == "browser"
    assert plan.reason == "fast_path_url"


def test_fast_path_routes_weather_keywords() -> None:
    plan = plan_fast_path_agent_request(
        "what is the weather forecast tomorrow in portland?",
        agent_names=["weather", "browser"],
        direct_question=True,
    )
    assert isinstance(plan, AgentPlan)
    assert plan is not None
    assert plan.agent == "weather"
    assert plan.reason == "fast_path_weather"


def test_fast_path_routes_operator_command_intent() -> None:
    plan = plan_fast_path_agent_request(
        "run: ps aux | head",
        agent_names=["system_operator", "browser"],
        direct_question=False,
    )
    assert isinstance(plan, AgentPlan)
    assert plan is not None
    assert plan.agent == "system_operator"
    assert plan.reason == "fast_path_operator"


def test_fast_path_routes_shell_command_like_text() -> None:
    plan = plan_fast_path_agent_request(
        "playerctl next just as a test",
        agent_names=["system_operator", "browser"],
        direct_question=False,
    )
    assert isinstance(plan, AgentPlan)
    assert plan is not None
    assert plan.agent == "system_operator"
    assert plan.reason == "fast_path_operator_shell"
    assert plan.action == "playerctl next"


def test_fast_path_routes_run_the_command_phrase() -> None:
    plan = plan_fast_path_agent_request(
        "sel can you run the command bar-rs open",
        agent_names=["system_operator", "browser"],
        direct_question=True,
    )
    assert isinstance(plan, AgentPlan)
    assert plan is not None
    assert plan.agent == "system_operator"
    assert plan.reason == "fast_path_operator"
    assert plan.action == "bar-rs open"


def test_fast_path_routes_conversational_run_phrase_with_tail_noise() -> None:
    plan = plan_fast_path_agent_request(
        "all I wanted you to run was bar-rs to test the fact that you can run commands and what it does is pull up a bar for my computer",
        agent_names=["system_operator", "browser"],
        direct_question=False,
    )
    assert isinstance(plan, AgentPlan)
    assert plan is not None
    assert plan.agent == "system_operator"
    assert plan.reason in {"fast_path_operator", "fast_path_operator_shell"}
    assert plan.action == "bar-rs"


def test_fast_path_routes_embedded_run_phrase_to_operator() -> None:
    plan = plan_fast_path_agent_request(
        "now you can tool call can you run bar-rs now",
        agent_names=["system_operator", "browser"],
        direct_question=False,
        operator_intent_threshold=0.72,
    )
    assert isinstance(plan, AgentPlan)
    assert plan is not None
    assert plan.agent == "system_operator"
    assert plan.reason == "fast_path_operator_shell"
    assert plan.action == "bar-rs"


def test_fast_path_routes_run_a_command_with_clause_to_operator() -> None:
    plan = plan_fast_path_agent_request(
        "hey sel can you run a command for me with ani-cli --dub no guns life -ep 1",
        agent_names=["system_operator", "browser", "sel_auto_external"],
        direct_question=False,
        operator_intent_threshold=0.72,
    )
    assert isinstance(plan, AgentPlan)
    assert plan is not None
    assert plan.agent == "system_operator"
    assert plan.reason in {"fast_path_operator", "fast_path_operator_shell"}
    assert plan.action.startswith("ani-cli --dub")


def test_fast_path_respects_operator_intent_threshold() -> None:
    plan = plan_fast_path_agent_request(
        "can you run the command explain why this failed",
        agent_names=["system_operator", "browser"],
        direct_question=True,
        operator_intent_threshold=0.7,
    )
    assert plan is None


def test_fast_path_rejects_generic_run_command_text() -> None:
    plan = plan_fast_path_agent_request(
        "can you run the command later tonight",
        agent_names=["system_operator", "browser"],
        direct_question=True,
        operator_intent_threshold=0.6,
    )
    assert plan is None


def test_operator_command_intent_score_distinguishes_command_vs_explanation() -> None:
    command_score = score_system_operator_command_intent(
        "sel can you run the command playerctl next",
        action="playerctl next",
        reason="fast_path_operator",
    )
    explain_score = score_system_operator_command_intent(
        "use system_operator to explain why this failed",
        action="explain why this failed",
        reason="planner_selected",
    )
    assert command_score >= 0.6
    assert explain_score < 0.6


def test_system_operator_command_intent_true_for_shell_like_requests() -> None:
    assert is_system_operator_command_intent(
        "playerctl next just as a test",
        action="playerctl next",
        reason="fast_path_operator_shell",
    )
    assert is_system_operator_command_intent(
        "can you run ps aux | head",
        action="ps aux | head",
        reason="explicit_user_request",
        explicit=True,
    )
    assert is_system_operator_command_intent(
        "sel can you run the command bar-rs open",
        action="bar-rs open",
        reason="fast_path_operator",
    )


def test_system_operator_command_intent_false_for_non_command_text() -> None:
    assert not is_system_operator_command_intent(
        "use system_operator to explain why this failed",
        action="explain why this failed",
        reason="planner_selected",
        min_score=0.6,
    )


def test_coerce_agent_plan_validates_and_normalizes() -> None:
    parsed = {
        "use_agent": True,
        "agent": "Weather",
        "action": "forecast for tomorrow",
        "confidence": 0.91,
        "reason": "needs external weather data",
    }
    plan = coerce_agent_plan(
        parsed,
        allowed_agents=["weather", "browser"],
        min_confidence=0.58,
    )
    assert isinstance(plan, AgentPlan)
    assert plan is not None
    assert plan.agent == "weather"
    assert plan.action == "forecast for tomorrow"
    assert plan.confidence == 0.91


def test_coerce_agent_plan_rejects_unknown_or_low_confidence() -> None:
    unknown = coerce_agent_plan(
        {"use_agent": True, "agent": "missing", "confidence": 1.0},
        allowed_agents=["weather"],
        min_confidence=0.58,
    )
    low_conf = coerce_agent_plan(
        {"use_agent": True, "agent": "weather", "confidence": 0.2},
        allowed_agents=["weather"],
        min_confidence=0.58,
    )
    assert unknown is None
    assert low_conf is None


def test_build_agent_selection_prompt_contains_key_sections() -> None:
    prompt = build_agent_selection_prompt(
        user_content="can you check the weather?",
        recent_context="[1m ago] User: hi",
        agents=[("weather", "Get forecast"), ("browser", "Search web pages")],
    )
    assert "Available agents" in prompt
    assert "- weather: Get forecast" in prompt
    assert "User message:" in prompt
    assert "can you check the weather?" in prompt


def test_is_agent_allowed_for_autonomy_respects_hard_allowlist() -> None:
    safe = ["weather", "browser", "image_gen"]
    assert is_agent_allowed_for_autonomy("sel_auto_new_tool", safe)
    assert is_agent_allowed_for_autonomy("weather", safe)
    assert not is_agent_allowed_for_autonomy("system_agent", safe)
    assert not is_agent_allowed_for_autonomy("bash_agent", safe)
    assert not is_agent_allowed_for_autonomy("random_tool", safe)
