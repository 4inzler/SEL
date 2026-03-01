from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path


def _load_agent_module():
    agent_path = Path(__file__).resolve().parents[2] / "agents" / "system_operator.py"
    spec = importlib.util.spec_from_file_location("system_operator", agent_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[arg-type]
    return module


def test_operator_agent_available_in_both_agent_dirs() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    root_agent = repo_root / "agents" / "system_operator.py"
    project_agent = repo_root / "project_echo" / "agents" / "system_operator.py"
    assert root_agent.exists()
    assert project_agent.exists()
    assert root_agent.read_text(encoding="utf-8") == project_agent.read_text(encoding="utf-8")


def test_operator_agent_disabled_by_default(monkeypatch) -> None:
    module = _load_agent_module()
    monkeypatch.delenv("SEL_OPERATOR_MODE_ENABLED", raising=False)
    output = asyncio.run(module.run("run: pwd", user_id="1", channel_id="1"))
    assert "disabled" in output.lower()


def test_operator_agent_restricted_mode_blocks_unsafe_prefix(monkeypatch) -> None:
    module = _load_agent_module()
    monkeypatch.setenv("SEL_OPERATOR_MODE_ENABLED", "true")
    monkeypatch.setenv("SEL_OPERATOR_FULL_HOST_PRIVILEGES", "false")
    monkeypatch.setenv("SEL_OPERATOR_REQUIRE_APPROVAL_USER", "false")
    output = asyncio.run(module.run("run: touch /tmp/sel_operator_probe", user_id="1", channel_id="1"))
    assert "restricted mode" in output.lower()


def test_operator_agent_runs_command_when_enabled(monkeypatch) -> None:
    module = _load_agent_module()
    monkeypatch.setenv("SEL_OPERATOR_MODE_ENABLED", "true")
    monkeypatch.setenv("SEL_OPERATOR_FULL_HOST_PRIVILEGES", "true")
    monkeypatch.setenv("SEL_OPERATOR_REQUIRE_APPROVAL_USER", "false")
    output = asyncio.run(module.run("run: echo operator_ok", user_id="1", channel_id="1"))
    assert "**Sel Operator**" in output
    assert "I ran this command for you:" in output
    assert "$ echo operator_ok" in output
    assert "operator_ok" in output


def test_operator_agent_blocks_denylisted_patterns(monkeypatch) -> None:
    module = _load_agent_module()
    monkeypatch.setenv("SEL_OPERATOR_MODE_ENABLED", "true")
    monkeypatch.setenv("SEL_OPERATOR_FULL_HOST_PRIVILEGES", "true")
    monkeypatch.setenv("SEL_OPERATOR_REQUIRE_APPROVAL_USER", "false")
    output = asyncio.run(module.run("run: rm -rf /", user_id="1", channel_id="1"))
    assert "blocked" in output.lower()


def test_operator_agent_extracts_polite_command(monkeypatch) -> None:
    module = _load_agent_module()
    monkeypatch.setenv("SEL_OPERATOR_MODE_ENABLED", "true")
    monkeypatch.setenv("SEL_OPERATOR_FULL_HOST_PRIVILEGES", "true")
    monkeypatch.setenv("SEL_OPERATOR_REQUIRE_APPROVAL_USER", "false")
    output = asyncio.run(module.run("can you run echo hi just as a test", user_id="1", channel_id="1"))
    assert "**Sel Operator**" in output
    assert "$ echo hi" in output
    assert "From your input:" in output
    assert "hi" in output


def test_operator_agent_honors_runtime_kwargs_without_env(monkeypatch) -> None:
    module = _load_agent_module()
    monkeypatch.delenv("SEL_OPERATOR_MODE_ENABLED", raising=False)
    monkeypatch.delenv("SEL_OPERATOR_FULL_HOST_PRIVILEGES", raising=False)
    monkeypatch.delenv("SEL_OPERATOR_REQUIRE_APPROVAL_USER", raising=False)
    output = asyncio.run(
        module.run(
            "run: echo runtime_ok",
            user_id="1",
            channel_id="1",
            operator_mode_enabled=True,
            operator_full_host_privileges=True,
            operator_require_approval_user=False,
        )
    )
    assert "**Sel Operator**" in output
    assert "runtime_ok" in output


def test_operator_agent_extracts_conversational_command_with_tail_noise(monkeypatch) -> None:
    module = _load_agent_module()
    monkeypatch.setenv("SEL_OPERATOR_MODE_ENABLED", "true")
    monkeypatch.setenv("SEL_OPERATOR_FULL_HOST_PRIVILEGES", "true")
    monkeypatch.setenv("SEL_OPERATOR_REQUIRE_APPROVAL_USER", "false")
    prompt = (
        "all I wanted you to run was echo bar_rs_ok to test the fact that you can run "
        "commands and what it does is pull up a bar for my computer"
    )
    output = asyncio.run(module.run(prompt, user_id="1", channel_id="1"))
    assert "**Sel Operator**" in output
    assert "$ echo bar_rs_ok" in output
    assert "From your input:" in output
    assert "bar_rs_ok" in output


def test_operator_agent_shows_no_output_message_for_silent_success(monkeypatch) -> None:
    module = _load_agent_module()
    monkeypatch.setenv("SEL_OPERATOR_MODE_ENABLED", "true")
    monkeypatch.setenv("SEL_OPERATOR_FULL_HOST_PRIVILEGES", "true")
    monkeypatch.setenv("SEL_OPERATOR_REQUIRE_APPROVAL_USER", "false")
    output = asyncio.run(module.run("run: true", user_id="1", channel_id="1"))
    assert "**Sel Operator**" in output
    assert "$ true" in output
    assert "Completed successfully" in output
    assert "_No terminal output._" in output
