from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sel_bot import seal_self_edit


class _FakeProc:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", b""


@pytest.mark.asyncio
async def test_git_push_agent_resolves_relative_path_within_repo(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    module_file = repo_root / "project_echo" / "sel_bot" / "seal_self_edit.py"
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_text("# stub\n", encoding="utf-8")

    agents_dir = repo_root / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "sel_auto_example.py").write_text("DESCRIPTION='x'\n", encoding="utf-8")

    monkeypatch.setattr(seal_self_edit, "__file__", str(module_file))
    monkeypatch.chdir(repo_root)

    calls: list[tuple[tuple[str, ...], str | None]] = []

    async def fake_create_subprocess_exec(*cmd, cwd=None, stdout=None, stderr=None):
        calls.append((cmd, cwd))
        return _FakeProc()

    monkeypatch.setattr(seal_self_edit.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    editor = object.__new__(seal_self_edit.SEALSelfEditor)
    await seal_self_edit.SEALSelfEditor._git_push_agent(editor, Path("agents/sel_auto_example.py"))

    assert calls
    first_cmd, first_cwd = calls[0]
    assert list(first_cmd[:2]) == ["git", "add"]
    assert first_cmd[2] == "agents/sel_auto_example.py"
    assert first_cwd == str(repo_root)


@pytest.mark.asyncio
async def test_git_push_agent_skips_when_file_outside_repo(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    module_file = repo_root / "project_echo" / "sel_bot" / "seal_self_edit.py"
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_text("# stub\n", encoding="utf-8")

    external_file = tmp_path / "external" / "sel_auto_example.py"
    external_file.parent.mkdir(parents=True, exist_ok=True)
    external_file.write_text("DESCRIPTION='x'\n", encoding="utf-8")

    monkeypatch.setattr(seal_self_edit, "__file__", str(module_file))

    calls: list[tuple[str, ...]] = []

    async def fake_create_subprocess_exec(*cmd, cwd=None, stdout=None, stderr=None):
        calls.append(cmd)
        return _FakeProc()

    monkeypatch.setattr(seal_self_edit.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    editor = object.__new__(seal_self_edit.SEALSelfEditor)
    await seal_self_edit.SEALSelfEditor._git_push_agent(editor, external_file)

    assert not calls


def _make_quality_editor(min_quality: int = 8) -> seal_self_edit.SEALSelfEditor:
    editor = object.__new__(seal_self_edit.SEALSelfEditor)
    editor.settings = SimpleNamespace(seal_tool_forge_min_quality_score=min_quality)
    return editor


def test_tool_forge_quality_score_rejects_low_quality_api_stub() -> None:
    editor = _make_quality_editor(min_quality=8)
    code = (
        "DESCRIPTION = 'tiny api helper'\n\n"
        "def run(query: str, **kwargs) -> str:\n"
        "    # TODO improve this later\n"
        "    return 'ok'\n"
    )
    parsed = ast.parse(code)

    score, issues = seal_self_edit.SEALSelfEditor._score_tool_forge_code(
        editor,
        code,
        parsed,
        description="Fetch API data",
        purpose="Call an HTTP API endpoint",
    )

    assert score < seal_self_edit.SEALSelfEditor._tool_forge_quality_threshold(editor)
    assert "placeholder_content" in issues
    assert "api_intent_without_httpx" in issues


def test_tool_forge_quality_score_accepts_api_tool_with_timeout() -> None:
    editor = _make_quality_editor(min_quality=8)
    code = (
        "import httpx\n\n"
        "DESCRIPTION = 'Fetch JSON from an API endpoint.'\n\n"
        "def run(query: str, **kwargs) -> str:\n"
        "    url = (kwargs.get('url') or query).strip()\n"
        "    if not url:\n"
        "        return 'Please provide a URL.'\n"
        "    try:\n"
        "        with httpx.Client(timeout=8.0) as client:\n"
        "            response = client.get(url)\n"
        "            response.raise_for_status()\n"
        "            return response.text[:220]\n"
        "    except Exception as exc:\n"
        "        return f'API request failed: {exc}'\n"
    )
    parsed = ast.parse(code)

    score, issues = seal_self_edit.SEALSelfEditor._score_tool_forge_code(
        editor,
        code,
        parsed,
        description="Fetch remote API data",
        purpose="Useful endpoint lookup utility",
    )

    assert score >= seal_self_edit.SEALSelfEditor._tool_forge_quality_threshold(editor)
    assert "api_intent_without_httpx" not in issues


class _FakeMemoryManager:
    async def retrieve_recent(self, _memory_id: str, limit: int = 15):
        return []


class _FakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def _chat_completion(self, model: str, messages, temperature: float):
        self.calls += 1
        if self.calls == 1:
            return json.dumps(
                {
                    "name": "api_stub",
                    "description": "Fetch remote API data",
                    "purpose": "Call an HTTP API endpoint",
                }
            )
        return (
            "DESCRIPTION = 'api stub'\n\n"
            "def run(query: str, **kwargs) -> str:\n"
            "    # TODO: this tool is incomplete\n"
            "    return 'todo'\n"
        )

    def _parse_json_response(self, raw: str):
        return json.loads(raw)


@pytest.mark.asyncio
async def test_tool_forge_low_quality_code_gets_negative_score(tmp_path) -> None:
    editor = object.__new__(seal_self_edit.SEALSelfEditor)
    editor.llm_client = _FakeLLM()
    editor.memory_manager = _FakeMemoryManager()
    editor.settings = SimpleNamespace(
        openrouter_util_model="test-model",
        seal_tool_forge_min_quality_score=8,
        global_memory_enabled=False,
        global_memory_id="sel_global",
    )
    editor._agents_dir = tmp_path
    editor._seal_score = 0

    await seal_self_edit.SEALSelfEditor._run_tool_forge(editor)

    assert editor._seal_score == -1
    assert list(tmp_path.glob("sel_auto_*.py")) == []


def test_forbidden_target_blocks_env_and_protected_files(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    editor = object.__new__(seal_self_edit.SEALSelfEditor)

    assert seal_self_edit.SEALSelfEditor._is_forbidden_target(
        editor, repo_root / ".env", repo_root=repo_root
    )
    assert seal_self_edit.SEALSelfEditor._is_forbidden_target(
        editor, repo_root / ".env.local", repo_root=repo_root
    )
    assert seal_self_edit.SEALSelfEditor._is_forbidden_target(
        editor, repo_root / "project_echo" / "sel_bot" / "main.py", repo_root=repo_root
    )
    assert not seal_self_edit.SEALSelfEditor._is_forbidden_target(
        editor, repo_root / "project_echo" / "sel_bot" / "prompts.py", repo_root=repo_root
    )


def test_tool_forge_mode_uses_configured_probabilities(monkeypatch) -> None:
    editor = object.__new__(seal_self_edit.SEALSelfEditor)
    editor.settings = SimpleNamespace(
        seal_tool_forge_improve_existing_chance=0.5,
        seal_tool_forge_self_code_edit_chance=0.2,
    )

    monkeypatch.setattr(seal_self_edit.random, "random", lambda: 0.1)
    assert seal_self_edit.SEALSelfEditor._tool_forge_mode(editor, has_auto_agents=True) == "improve_existing_tool"

    monkeypatch.setattr(seal_self_edit.random, "random", lambda: 0.6)
    assert seal_self_edit.SEALSelfEditor._tool_forge_mode(editor, has_auto_agents=True) == "self_code_edit"

    monkeypatch.setattr(seal_self_edit.random, "random", lambda: 0.95)
    assert seal_self_edit.SEALSelfEditor._tool_forge_mode(editor, has_auto_agents=True) == "new_tool"

    monkeypatch.setattr(seal_self_edit.random, "random", lambda: 0.1)
    assert seal_self_edit.SEALSelfEditor._tool_forge_mode(editor, has_auto_agents=False) == "self_code_edit"


def test_self_code_edit_candidates_exclude_env_and_protected(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    prompts = repo_root / "project_echo" / "sel_bot" / "prompts.py"
    protected_main = repo_root / "project_echo" / "sel_bot" / "main.py"
    env_like = repo_root / "project_echo" / "sel_bot" / ".env.py"
    prompts.parent.mkdir(parents=True, exist_ok=True)
    prompts.write_text("x = 1\n", encoding="utf-8")
    protected_main.write_text("x = 1\n", encoding="utf-8")
    env_like.write_text("x = 1\n", encoding="utf-8")

    editor = object.__new__(seal_self_edit.SEALSelfEditor)
    editor.settings = SimpleNamespace(
        seal_self_code_edit_targets=[
            "project_echo/sel_bot/prompts.py",
            "project_echo/sel_bot/main.py",
            "project_echo/sel_bot/.env.py",
        ]
    )

    candidates = seal_self_edit.SEALSelfEditor._self_code_edit_candidates(editor, repo_root)
    assert candidates == [prompts.resolve()]


@pytest.mark.asyncio
async def test_write_with_test_gate_reverts_on_failed_gate(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    module_file = repo_root / "project_echo" / "sel_bot" / "seal_self_edit.py"
    target_file = repo_root / "project_echo" / "sel_bot" / "prompts.py"
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_text("# stub\n", encoding="utf-8")
    target_file.write_text("x = 1\n", encoding="utf-8")

    monkeypatch.setattr(seal_self_edit, "__file__", str(module_file))

    editor = object.__new__(seal_self_edit.SEALSelfEditor)
    editor.settings = SimpleNamespace(seal_enabled=True)
    editor._agents_dir = repo_root / "agents"
    editor._agents_dir.mkdir(parents=True, exist_ok=True)
    editor._seal_score = 0

    async def fake_gate(*, target_file: Path, repo_root: Path) -> tuple[bool, str]:
        return False, "pytest failed: synthetic gate failure"

    editor._run_quick_test_gate = fake_gate  # type: ignore[method-assign]

    applied = await seal_self_edit.SEALSelfEditor._write_with_test_gate(
        editor,
        target_file=target_file,
        new_content="x = 2\n",
        mode="self_code_edit",
        success_label="self_code_edit",
    )

    assert not applied
    assert target_file.read_text(encoding="utf-8") == "x = 1\n"
    assert editor._seal_score == -1
    assert editor._self_edit_fail_count == 1
    assert editor._recent_self_edits[-1]["result"] == "reverted"


@pytest.mark.asyncio
async def test_write_with_test_gate_keeps_edit_on_pass(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    module_file = repo_root / "project_echo" / "sel_bot" / "seal_self_edit.py"
    target_file = repo_root / "project_echo" / "sel_bot" / "prompts.py"
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_text("# stub\n", encoding="utf-8")
    target_file.write_text("x = 1\n", encoding="utf-8")

    monkeypatch.setattr(seal_self_edit, "__file__", str(module_file))

    editor = object.__new__(seal_self_edit.SEALSelfEditor)
    editor.settings = SimpleNamespace(seal_enabled=True)
    editor._agents_dir = repo_root / "agents"
    editor._agents_dir.mkdir(parents=True, exist_ok=True)
    editor._seal_score = 0

    async def fake_gate(*, target_file: Path, repo_root: Path) -> tuple[bool, str]:
        return True, "pytest passed: synthetic gate pass"

    editor._run_quick_test_gate = fake_gate  # type: ignore[method-assign]

    applied = await seal_self_edit.SEALSelfEditor._write_with_test_gate(
        editor,
        target_file=target_file,
        new_content="x = 2\n",
        mode="self_code_edit",
        success_label="self_code_edit",
    )

    assert applied
    assert target_file.read_text(encoding="utf-8") == "x = 2\n"
    assert editor._seal_score == 1
    assert editor._self_edit_pass_count == 1
    assert editor._recent_self_edits[-1]["result"] == "applied"


def test_get_status_snapshot_contains_probabilities_and_counters(tmp_path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "sel_auto_helper.py").write_text("DESCRIPTION='x'\n", encoding="utf-8")

    editor = object.__new__(seal_self_edit.SEALSelfEditor)
    editor.settings = SimpleNamespace(
        seal_enabled=True,
        seal_tool_forge_improve_existing_chance=0.4,
        seal_tool_forge_self_code_edit_chance=0.1,
    )
    editor._agents_dir = agents_dir
    editor._seal_score = 3
    editor._seal_pass_count = 7
    editor._seal_fail_count = 4
    editor._self_edit_pass_count = 2
    editor._self_edit_fail_count = 1
    editor._last_tool_forge_mode = "self_code_edit"
    editor._recent_self_edits = [
        {
            "timestamp": "2026-02-27 01:00:00 UTC",
            "mode": "self_code_edit",
            "file": "project_echo/sel_bot/prompts.py",
            "result": "applied",
            "detail": "pytest passed",
        }
    ]

    snapshot = seal_self_edit.SEALSelfEditor.get_status_snapshot(editor)

    assert snapshot["enabled"] is True
    assert snapshot["score"] == 3
    assert snapshot["pass_count"] == 7
    assert snapshot["fail_count"] == 4
    assert snapshot["self_edit_pass_count"] == 2
    assert snapshot["self_edit_fail_count"] == 1
    assert snapshot["last_mode"] == "self_code_edit"
    assert snapshot["auto_agent_count"] == 1
    assert snapshot["mode_probabilities"]["improve_existing_tool"] == pytest.approx(0.4)
    assert snapshot["mode_probabilities"]["self_code_edit"] == pytest.approx(0.1)
    assert snapshot["mode_probabilities"]["new_tool"] == pytest.approx(0.5)
    assert snapshot["recent_self_edits"][-1]["result"] == "applied"
