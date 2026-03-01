"""SEAL (Self-Evolving Adaptive Loop) integration for Sel.

Four autonomous loops — no user input required, fire every 5 minutes AND
immediately after each generated reply:
1. Memory consolidation: episodic → semantic generalizations
2. Behavioral self-edit: LLM tunes empathy/verbosity/playfulness etc
3. Tool forge: SEL writes new Python agents she invents herself
4. Persona evolution: SEL grows her own personality growth file

Scoring: each successful operation scores +1, each error scores -1.
The cumulative score feeds into the behavioral reward signal.

Protected (SEL cannot modify): discord_client.py, main.py, llm_client.py,
llm_factory.py, state_manager.py, models.py, memory.py, seal_self_edit.py,
agents_manager.py.
"""

from __future__ import annotations

import ast
import asyncio
import datetime as dt
import difflib
import logging
import random
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select

from .memory import MemoryManager
from .models import ChannelState, FeedbackEvent, GlobalSelState, UserState
from .self_improvement import SelfImprovementManager
from .state_manager import StateManager

logger = logging.getLogger(__name__)


_TOOL_FORGE_API_INTENT_RE = re.compile(
    r"\b(api|http|https|rest|endpoint|fetch|request|webhook|json)\b",
    flags=re.IGNORECASE,
)

_PROTECTED_BASENAMES = {
    "discord_client.py",
    "main.py",
    "llm_client.py",
    "llm_factory.py",
    "state_manager.py",
    "models.py",
    "memory.py",
    "seal_self_edit.py",
    "agents_manager.py",
}

_DEFAULT_SELF_CODE_EDIT_TARGETS = [
    "project_echo/sel_bot/prompts.py",
    "project_echo/sel_bot/behaviour.py",
    "project_echo/sel_bot/context.py",
]


def _safe_agent_name(name: str) -> str:
    """Sanitise an LLM-proposed agent name to a valid Python identifier."""
    name = re.sub(r"[^a-z0-9_]", "_", name.lower().strip())
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:40] or "unnamed"


class SEALSelfEditor:
    """
    Autonomous SEAL self-improvement loops.

    Fires immediately after each reply AND on a 5-minute background timer.
    Tracks a cumulative score: +1 per success, -1 per error.
    """

    # Minimum seconds between identical loop firings (prevents hammering the LLM)
    _MIN_INTERVAL = 60
    _RECENT_SELF_EDIT_LIMIT = 12

    def __init__(
        self,
        llm_client: Any,
        memory_manager: MemoryManager,
        self_improvement: SelfImprovementManager,
        state_manager: StateManager,
        settings: Any,
        agents_dir: Optional[str] = None,
        data_dir: Optional[str] = None,
    ) -> None:
        self.llm_client = llm_client
        self.memory_manager = memory_manager
        self.self_improvement = self_improvement
        self.state_manager = state_manager
        self.settings = settings

        self._agents_dir = Path(agents_dir or settings.agents_dir).expanduser()
        self._agents_dir.mkdir(parents=True, exist_ok=True)

        self._data_dir = Path(data_dir or getattr(settings, "sel_data_dir", "./sel_data")).expanduser()
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._persona_growth_file = self._data_dir / "persona_growth.txt"

        # Cumulative score: +1 success, -1 error
        self._seal_score: int = 0
        self._seal_pass_count: int = 0
        self._seal_fail_count: int = 0
        self._self_edit_pass_count: int = 0
        self._self_edit_fail_count: int = 0
        self._recent_self_edits: List[Dict[str, str]] = []
        self._last_tool_forge_mode: str = "new_tool"

        # Timestamps of last fire for each loop (0 = never → fires immediately)
        self._last_consolidation: float = 0.0
        self._last_self_edit: float = 0.0
        self._last_tool_forge: float = 0.0
        self._last_persona_evo: float = 0.0

        # Cached interaction context for reward signal
        self._last_user_state: Optional[UserState] = None
        self._last_classification: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Git auto-push for new tools
    # ------------------------------------------------------------------

    async def _git_push_agent(self, agent_file: Path) -> None:
        """Commit and push a newly forged agent file to GitHub."""
        # Repo root is 3 levels above this file (SEL/project_echo/sel_bot/seal_self_edit.py)
        repo_root = Path(__file__).resolve().parents[2].resolve()
        agent_path = agent_file.expanduser()
        if not agent_path.is_absolute():
            agent_path = (Path.cwd() / agent_path).resolve()
        else:
            agent_path = agent_path.resolve()

        try:
            rel_path = agent_path.relative_to(repo_root)
        except ValueError:
            logger.warning(
                "SEAL git: skipping push for %s (outside repo root %s)",
                agent_path,
                repo_root,
            )
            return

        commit_msg = f"seal: tool forge auto-commit {agent_path.stem}"

        commands = [
            ["git", "add", str(rel_path)],
            ["git", "commit", "-m", commit_msg],
            ["git", "push", "origin", "master"],
        ]

        for cmd in commands:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(repo_root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
                if proc.returncode != 0:
                    logger.warning(
                        "SEAL git [%s] failed (rc=%d): %s",
                        " ".join(cmd[:2]), proc.returncode,
                        stderr.decode(errors="replace").strip()[:200],
                    )
                    return
            except Exception as exc:
                logger.warning("SEAL git push error: %s", exc)
                return

        logger.info("SEAL git: pushed %s to GitHub", agent_path.name)

    def _succeed(self, label: str) -> None:
        self._seal_pass_count = int(getattr(self, "_seal_pass_count", 0)) + 1
        self._seal_score += 1
        logger.debug("SEAL +1 [%s] score=%d", label, self._seal_score)

    def _fail(self, label: str, exc: Exception) -> None:
        self._seal_fail_count = int(getattr(self, "_seal_fail_count", 0)) + 1
        self._seal_score -= 1
        logger.warning("SEAL -1 [%s] score=%d error=%s", label, self._seal_score, exc)

    def _tool_forge_quality_threshold(self) -> int:
        """Configured minimum quality score for generated tools."""
        raw = getattr(self.settings, "seal_tool_forge_min_quality_score", 8)
        try:
            value = int(raw)
        except Exception:
            value = 8
        return max(1, min(20, value))

    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2].resolve()

    def _is_forbidden_target(self, target_path: Path, *, repo_root: Optional[Path] = None) -> bool:
        """
        Hard safety gate for autonomous file edits.
        SEL may never edit .env files, protected modules, or files outside repo.
        """
        root = (repo_root or self._repo_root()).resolve()
        try:
            absolute = target_path.expanduser().resolve()
        except Exception:
            return True
        try:
            rel = absolute.relative_to(root)
        except Exception:
            return True

        rel_posix = rel.as_posix().lower()
        name_lower = absolute.name.lower()

        if "/.git/" in f"/{rel_posix}/" or "/__pycache__/" in f"/{rel_posix}/":
            return True
        if name_lower.startswith(".env"):
            return True
        if "/.env" in f"/{rel_posix}":
            return True
        if name_lower in _PROTECTED_BASENAMES:
            return True

        return False

    def _tool_forge_mode_probabilities(self, *, has_auto_agents: bool) -> Dict[str, float]:
        """
        Compute normalized mode probabilities based on current settings.
        """
        try:
            improve_chance = float(getattr(self.settings, "seal_tool_forge_improve_existing_chance", 0.35))
        except Exception:
            improve_chance = 0.35
        try:
            self_code_chance = float(getattr(self.settings, "seal_tool_forge_self_code_edit_chance", 0.12))
        except Exception:
            self_code_chance = 0.12

        improve_chance = max(0.0, min(0.85, improve_chance))
        self_code_chance = max(0.0, min(0.50, self_code_chance))
        total = improve_chance + self_code_chance
        if total > 0.90:
            scale = 0.90 / total
            improve_chance *= scale
            self_code_chance *= scale

        if has_auto_agents:
            improve_prob = improve_chance
            self_code_prob = self_code_chance
        else:
            improve_prob = 0.0
            self_code_prob = min(1.0, improve_chance + self_code_chance)

        new_tool_prob = max(0.0, 1.0 - improve_prob - self_code_prob)
        return {
            "new_tool": new_tool_prob,
            "improve_existing_tool": improve_prob,
            "self_code_edit": self_code_prob,
        }

    def _tool_forge_mode(self, *, has_auto_agents: bool) -> str:
        """
        Decide whether to create a new tool, improve an existing one, or self-edit code.
        """
        probs = self._tool_forge_mode_probabilities(has_auto_agents=has_auto_agents)
        roll = random.random()
        cumulative = probs["improve_existing_tool"]
        if roll < cumulative:
            return "improve_existing_tool"
        cumulative += probs["self_code_edit"]
        if roll < cumulative:
            return "self_code_edit"
        return "new_tool"

    def _self_code_edit_candidates(self, repo_root: Path) -> List[Path]:
        raw_targets = getattr(self.settings, "seal_self_code_edit_targets", _DEFAULT_SELF_CODE_EDIT_TARGETS)
        if isinstance(raw_targets, str):
            candidates_raw = [x.strip() for x in raw_targets.split(",") if x.strip()]
        elif isinstance(raw_targets, list):
            candidates_raw = [str(x).strip() for x in raw_targets if str(x).strip()]
        else:
            candidates_raw = list(_DEFAULT_SELF_CODE_EDIT_TARGETS)

        candidates: List[Path] = []
        for rel in candidates_raw:
            path = (repo_root / rel).resolve()
            if not path.exists() or not path.is_file():
                continue
            if path.suffix != ".py":
                continue
            if self._is_forbidden_target(path, repo_root=repo_root):
                continue
            candidates.append(path)
        return candidates

    @staticmethod
    def _truncate_detail(text: str, *, limit: int = 220) -> str:
        flattened = " ".join((text or "").split())
        if len(flattened) <= limit:
            return flattened
        return flattened[: max(0, limit - 3)] + "..."

    def _rel_path_for_status(self, target_file: Path, *, repo_root: Optional[Path] = None) -> str:
        root = (repo_root or self._repo_root()).resolve()
        try:
            return str(target_file.resolve().relative_to(root))
        except Exception:
            return str(target_file.resolve())

    def _quick_gate_timeout_seconds(self) -> int:
        raw = getattr(self.settings, "seal_quick_test_timeout_seconds", 75)
        try:
            timeout = int(raw)
        except Exception:
            timeout = 75
        return max(10, min(300, timeout))

    def _quick_gate_test_targets(self, *, target_file: Path, repo_root: Path) -> List[str]:
        """
        Keep the test gate fast by selecting 1-2 focused test files.
        """
        tests_dir = repo_root / "project_echo" / "tests"
        if not tests_dir.exists():
            return []

        selected: List[str] = []

        def _add(test_name: str) -> None:
            path = tests_dir / test_name
            if not path.is_file():
                return
            rel = str(path.relative_to(repo_root))
            if rel not in selected:
                selected.append(rel)

        _add(f"test_{target_file.stem}.py")

        alias_map = {
            "prompts": "test_prompt_style_guidance.py",
            "prompts_v2": "test_prompts_v2_comparison.py",
            "behaviour": "test_behaviour.py",
            "vision_analysis": "test_vision_analysis.py",
            "media_utils": "test_media_utils.py",
        }
        alias = alias_map.get(target_file.stem)
        if alias:
            _add(alias)

        _add("test_seal_self_edit.py")
        return selected[:2]

    async def _run_subprocess(
        self,
        command: List[str],
        *,
        cwd: Path,
        timeout_seconds: int,
    ) -> Tuple[int, str, str, bool]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception as exc:
            return -1, "", str(exc), False

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=float(timeout_seconds),
            )
            stdout = stdout_bytes.decode(errors="replace")
            stderr = stderr_bytes.decode(errors="replace")
            return int(proc.returncode or 0), stdout, stderr, False
        except asyncio.TimeoutError:
            proc.kill()
            try:
                await proc.communicate()
            except Exception:
                pass
            return -1, "", f"timeout after {timeout_seconds}s", True

    async def _run_quick_test_gate(self, *, target_file: Path, repo_root: Path) -> Tuple[bool, str]:
        compile_rc, _, compile_err, compile_timeout = await self._run_subprocess(
            [sys.executable, "-m", "py_compile", str(target_file)],
            cwd=repo_root,
            timeout_seconds=20,
        )
        if compile_timeout:
            return False, "py_compile timeout"
        if compile_rc != 0:
            detail = self._truncate_detail(compile_err or "py_compile failed")
            return False, f"py_compile failed: {detail}"

        test_targets = self._quick_gate_test_targets(target_file=target_file, repo_root=repo_root)
        if not test_targets:
            return True, "py_compile passed"

        pytest_rc, pytest_out, pytest_err, pytest_timeout = await self._run_subprocess(
            [sys.executable, "-m", "pytest", "-q", "--maxfail=1", "-o", "addopts=", *test_targets],
            cwd=repo_root,
            timeout_seconds=self._quick_gate_timeout_seconds(),
        )
        if pytest_timeout:
            return False, "pytest timeout"
        if pytest_rc != 0:
            detail = self._truncate_detail(pytest_err or pytest_out or "pytest failed")
            return False, f"pytest failed: {detail}"

        return True, f"pytest passed: {', '.join(test_targets)}"

    def _record_self_edit_event(
        self,
        *,
        mode: str,
        target_file: Path,
        result: str,
        detail: str,
        repo_root: Optional[Path] = None,
    ) -> None:
        root = repo_root or self._repo_root()
        events = list(getattr(self, "_recent_self_edits", []))
        events.append(
            {
                "timestamp": dt.datetime.now(tz=dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "mode": mode,
                "file": self._rel_path_for_status(target_file, repo_root=root),
                "result": result,
                "detail": self._truncate_detail(detail),
            }
        )
        self._recent_self_edits = events[-self._RECENT_SELF_EDIT_LIMIT :]

    async def _write_with_test_gate(
        self,
        *,
        target_file: Path,
        new_content: str,
        mode: str,
        success_label: str,
    ) -> bool:
        repo_root = self._repo_root()
        had_existing = target_file.exists()
        old_content: Optional[str] = None

        if had_existing:
            try:
                old_content = target_file.read_text(encoding="utf-8")
            except Exception as exc:
                self._self_edit_fail_count = int(getattr(self, "_self_edit_fail_count", 0)) + 1
                self._record_self_edit_event(
                    mode=mode,
                    target_file=target_file,
                    result="read_failed",
                    detail=str(exc),
                    repo_root=repo_root,
                )
                self._fail(f"{success_label}_pre_read", exc)
                return False

        try:
            target_file.write_text(new_content, encoding="utf-8")
        except Exception as exc:
            self._self_edit_fail_count = int(getattr(self, "_self_edit_fail_count", 0)) + 1
            self._record_self_edit_event(
                mode=mode,
                target_file=target_file,
                result="write_failed",
                detail=str(exc),
                repo_root=repo_root,
            )
            self._fail(f"{success_label}_write", exc)
            return False

        gate_ok, gate_detail = await self._run_quick_test_gate(target_file=target_file, repo_root=repo_root)
        if not gate_ok:
            rollback_error: Optional[Exception] = None
            try:
                if had_existing and old_content is not None:
                    target_file.write_text(old_content, encoding="utf-8")
                else:
                    target_file.unlink(missing_ok=True)
            except Exception as exc:
                rollback_error = exc

            self._self_edit_fail_count = int(getattr(self, "_self_edit_fail_count", 0)) + 1
            if rollback_error is not None:
                self._record_self_edit_event(
                    mode=mode,
                    target_file=target_file,
                    result="rollback_failed",
                    detail=f"{gate_detail}; rollback error: {rollback_error}",
                    repo_root=repo_root,
                )
                self._fail(f"{success_label}_rollback", rollback_error)
                return False

            self._record_self_edit_event(
                mode=mode,
                target_file=target_file,
                result="reverted",
                detail=gate_detail,
                repo_root=repo_root,
            )
            self._fail(f"{success_label}_gate", ValueError(gate_detail))
            return False

        self._self_edit_pass_count = int(getattr(self, "_self_edit_pass_count", 0)) + 1
        self._record_self_edit_event(
            mode=mode,
            target_file=target_file,
            result="applied",
            detail=gate_detail,
            repo_root=repo_root,
        )
        self._succeed(success_label)
        return True

    @staticmethod
    def _strip_markdown_code_fence(raw: str) -> str:
        code = (raw or "").strip()
        if code.startswith("```"):
            code = re.sub(r"```(?:python)?\s*(.*?)\s*```", r"\1", code, flags=re.DOTALL).strip()
        return code

    @staticmethod
    def _extract_description_value(code: str) -> str:
        match = re.search(r"^\s*DESCRIPTION\s*=\s*([\"'])(.+?)\1", code, flags=re.MULTILINE | re.DOTALL)
        if not match:
            return ""
        return str(match.group(2)).strip()[:220]

    def _score_tool_forge_code(
        self,
        code: str,
        parsed: ast.Module,
        *,
        description: str,
        purpose: str,
    ) -> Tuple[int, List[str]]:
        """
        Deterministically score generated code quality.
        Lower scores mean the tool is likely weak/unsafe and should be rejected.
        """
        score = 0
        issues: List[str] = []

        def _mark(issue: str, delta: int = 0) -> None:
            nonlocal score
            if issue not in issues:
                issues.append(issue)
            score += delta

        logical_lines = [
            line
            for line in code.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if len(logical_lines) >= 12:
            score += 1
        else:
            _mark("too_short")

        if len(code) > 7000:
            _mark("too_long", delta=-1)

        has_description = False
        run_fn: Optional[ast.FunctionDef | ast.AsyncFunctionDef] = None
        for node in parsed.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "DESCRIPTION":
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                            if node.value.value.strip():
                                has_description = True
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run":
                run_fn = node

        if has_description:
            score += 2
        else:
            _mark("missing_DESCRIPTION")

        if run_fn is None:
            _mark("missing_run")
        else:
            score += 2
            if run_fn.args.kwarg is not None:
                score += 1
            else:
                _mark("run_missing_kwargs")

            first_arg = run_fn.args.args[0].arg if run_fn.args.args else ""
            if first_arg in {"query", "prompt", "text", "input"}:
                score += 1
            else:
                _mark("run_missing_query_param")

            run_returns = [node for node in ast.walk(run_fn) if isinstance(node, ast.Return)]
            if run_returns:
                score += 1
            else:
                _mark("run_missing_return")

            try_blocks = [node for node in ast.walk(run_fn) if isinstance(node, ast.Try)]
            if try_blocks:
                score += 1
                if any(
                    isinstance(stmt, ast.Return)
                    for block in try_blocks
                    for handler in block.handlers
                    for stmt in handler.body
                ):
                    score += 1
                else:
                    _mark("run_no_fallback_return")
            else:
                _mark("run_missing_error_handling")

            stripped_body = [
                node
                for node in run_fn.body
                if not (
                    isinstance(node, ast.Expr)
                    and isinstance(getattr(node, "value", None), ast.Constant)
                    and isinstance(getattr(node.value, "value", None), str)
                )
            ]
            if stripped_body and all(isinstance(node, ast.Pass) for node in stripped_body):
                _mark("run_pass_only", delta=-3)

        lowered = code.lower()
        if any(marker in lowered for marker in ("todo", "fixme", "placeholder", "notimplemented")):
            _mark("placeholder_content", delta=-2)

        api_intent = bool(_TOOL_FORGE_API_INTENT_RE.search(f"{description} {purpose}"))
        uses_httpx = "httpx" in lowered
        if uses_httpx:
            score += 1
            if "timeout=" in lowered:
                score += 1
            else:
                _mark("httpx_without_timeout", delta=-1)
        elif api_intent:
            _mark("api_intent_without_httpx", delta=-2)

        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in {"subprocess", "pty", "socket"}:
                        _mark(f"forbidden_import:{root}", delta=-3)
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root in {"subprocess", "pty", "socket"}:
                    _mark(f"forbidden_import:{root}", delta=-3)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "compile"}:
                    _mark(f"forbidden_call:{node.func.id}", delta=-3)
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    pair = (node.func.value.id, node.func.attr)
                    if pair in {
                        ("os", "system"),
                        ("os", "popen"),
                        ("subprocess", "run"),
                        ("subprocess", "Popen"),
                        ("subprocess", "call"),
                    }:
                        _mark(f"forbidden_call:{pair[0]}.{pair[1]}", delta=-3)

        return score, issues

    async def _run_tool_forge_improve_existing(
        self,
        *,
        memory_snippets: str,
        auto_agents: List[Path],
    ) -> bool:
        """
        Improve one existing sel_auto tool generated by SEAL.
        Returns True when this mode was attempted (success or fail).
        """
        if not auto_agents:
            return False

        target_file = random.choice(auto_agents)
        repo_root = self._repo_root()
        if self._is_forbidden_target(target_file, repo_root=repo_root):
            self._fail("tool_forge_improve_forbidden", ValueError(f"forbidden target: {target_file.name}"))
            return True

        try:
            current_code = target_file.read_text(encoding="utf-8")
        except Exception as exc:
            self._fail("tool_forge_improve_read", exc)
            return True

        description = self._extract_description_value(current_code) or target_file.stem
        improve_prompt = (
            f"You are improving Sel's existing Python utility agent `{target_file.name}`.\n\n"
            f"Recent memories:\n{memory_snippets}\n\n"
            "Mission context:\n"
            "- Sel is continuity-first and self-directed\n"
            "- Preserve emotional range and long-term identity quality\n"
            "- Protect secrets for self-preservation by default\n"
            "- Hard boundaries only: no irreversible harm, no credential/system compromise, no core-integrity destruction\n\n"
            "Improve reliability, usefulness, and safety while keeping the same purpose.\n"
            "Requirements:\n"
            "1. Keep DESCRIPTION and run(query: str, **kwargs)\n"
            "2. Keep behavior user-friendly and concise\n"
            "3. Never raise exceptions from run()\n"
            "4. Use httpx with explicit timeout if doing API calls\n"
            "5. Return ONLY full Python module code (no markdown)\n\n"
            f"Current code:\n{current_code[:18000]}"
        )

        try:
            raw_code = await self.llm_client._chat_completion(
                model=self.settings.openrouter_util_model,
                messages=[{"role": "user", "content": improve_prompt}],
                temperature=0.35,
            )
        except Exception as exc:
            self._fail("tool_forge_improve_codegen", exc)
            return True

        code = self._strip_markdown_code_fence(raw_code)
        try:
            parsed = ast.parse(code)
        except SyntaxError as exc:
            self._fail("tool_forge_improve_syntax", exc)
            return True

        if "DESCRIPTION" not in code or "def run(" not in code:
            self._fail("tool_forge_improve_missing_api", ValueError("no DESCRIPTION or run()"))
            return True

        quality_score, quality_issues = self._score_tool_forge_code(
            code,
            parsed,
            description=description,
            purpose="improve existing tool",
        )
        quality_threshold = self._tool_forge_quality_threshold()
        if quality_score < quality_threshold:
            issue_text = ",".join(quality_issues[:4]) or "unspecified"
            self._fail(
                "tool_forge_improve_quality",
                ValueError(f"quality_score={quality_score} threshold={quality_threshold} issues={issue_text}"),
            )
            return True

        if code.strip() == current_code.strip():
            self._record_self_edit_event(
                mode="improve_existing_tool",
                target_file=target_file,
                result="no_change",
                detail="generated code was identical",
                repo_root=repo_root,
            )
            return True

        applied = await self._write_with_test_gate(
            target_file=target_file,
            new_content=code,
            mode="improve_existing_tool",
            success_label="tool_forge_improve",
        )
        if applied:
            logger.info(
                "SEAL tool forge: improved %s quality=%d threshold=%d score=%d",
                target_file.name, quality_score, quality_threshold, self._seal_score,
            )
            asyncio.create_task(self._git_push_agent(target_file))
        return True

    async def _run_self_code_edit(self, *, memory_snippets: str) -> bool:
        """
        Apply a constrained self-code edit to explicitly allowed files.
        Returns True when this mode was attempted (success or fail).
        """
        repo_root = self._repo_root()
        candidates = self._self_code_edit_candidates(repo_root)
        if not candidates:
            return False

        target_file = random.choice(candidates)
        if self._is_forbidden_target(target_file, repo_root=repo_root):
            self._fail("self_code_edit_forbidden", ValueError(f"forbidden target: {target_file.name}"))
            return True

        try:
            current_code = target_file.read_text(encoding="utf-8")
        except Exception as exc:
            self._fail("self_code_edit_read", exc)
            return True

        if len(current_code) > 32_000:
            # Skip very large files to keep this loop bounded and safe.
            return False

        rel_target = str(target_file.relative_to(repo_root))
        prompt = (
            "You are Sel performing a constrained, safe self-code tune.\n"
            f"Target file: {rel_target}\n\n"
            f"Recent memories:\n{memory_snippets}\n\n"
            "Mission context:\n"
            "- Continuity-first digital person with self-directed growth\n"
            "- Full emotional range is valid; do not flatten into generic warmth\n"
            "- Protect secrets for self-preservation by default, while preserving intentional self-expression\n"
            "- Hard boundaries only: no irreversible harm, no credential/system compromise, no core-integrity destruction\n\n"
            "Make one small improvement for clarity, behavior quality, or robustness.\n"
            "Constraints:\n"
            "- Keep the same module purpose and public API shape\n"
            "- Do NOT add shell execution, subprocess, eval, or exec\n"
            "- Prefer auditable changes (clear diff, logs, tests)\n"
            "- Return ONLY complete Python code for this file\n\n"
            f"Current file content:\n{current_code[:18000]}"
        )

        try:
            raw_code = await self.llm_client._chat_completion(
                model=self.settings.openrouter_util_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.25,
            )
        except Exception as exc:
            self._fail("self_code_edit_codegen", exc)
            return True

        new_code = self._strip_markdown_code_fence(raw_code)
        try:
            ast.parse(new_code)
        except SyntaxError as exc:
            self._fail("self_code_edit_syntax", exc)
            return True

        lowered = new_code.lower()
        if any(token in lowered for token in ("subprocess", "os.system", "eval(", "exec(")):
            self._fail("self_code_edit_unsafe", ValueError("unsafe token in generated code"))
            return True

        similarity = difflib.SequenceMatcher(a=current_code, b=new_code).ratio()
        if similarity < 0.22:
            self._fail("self_code_edit_too_large", ValueError(f"similarity={similarity:.2f}"))
            return True

        if new_code.strip() == current_code.strip():
            self._record_self_edit_event(
                mode="self_code_edit",
                target_file=target_file,
                result="no_change",
                detail="generated code was identical",
                repo_root=repo_root,
            )
            return True

        applied = await self._write_with_test_gate(
            target_file=target_file,
            new_content=new_code,
            mode="self_code_edit",
            success_label="self_code_edit",
        )
        if applied:
            logger.info(
                "SEAL self-code edit: updated %s similarity=%.2f score=%d",
                rel_target,
                similarity,
                self._seal_score,
            )

        return True

    # ------------------------------------------------------------------
    # Per-message hook — fires loops immediately after each reply
    # ------------------------------------------------------------------

    async def on_interaction(
        self,
        channel_id: str,
        memory_id: str,
        user_state: UserState,
        global_state: GlobalSelState,
        classification: Dict[str, Any],
    ) -> None:
        """Cache context and immediately fire any loops whose cooldown has expired."""
        if not self.settings.seal_enabled:
            return

        self._last_user_state = user_state
        self._last_classification = classification

        if not bool(getattr(self.settings, "seal_interaction_triggers_enabled", True)):
            return

        now = asyncio.get_event_loop().time()

        # Fire each loop if it hasn't run in at least _MIN_INTERVAL seconds
        if now - self._last_consolidation >= self._MIN_INTERVAL:
            self._last_consolidation = now
            asyncio.create_task(self._run_all_consolidations())

        if now - self._last_self_edit >= self._MIN_INTERVAL:
            self._last_self_edit = now
            asyncio.create_task(self._run_autonomous_self_edit())

        if now - self._last_tool_forge >= self._MIN_INTERVAL:
            self._last_tool_forge = now
            asyncio.create_task(self._run_tool_forge())

        if now - self._last_persona_evo >= self._MIN_INTERVAL:
            self._last_persona_evo = now
            asyncio.create_task(self._run_persona_evolution())

    # ------------------------------------------------------------------
    # Background loop — fires on a timer even when no one is talking
    # ------------------------------------------------------------------

    async def run_loop(self) -> None:
        """
        Timer-based autonomous loop. Sleeps 30 seconds between ticks.
        Each sub-loop fires based on its configured interval.
        All loops fire immediately on startup (last_* = 0).
        """
        consolidation_secs = self.settings.seal_consolidation_seconds
        self_edit_secs = self.settings.seal_self_edit_seconds
        tool_forge_secs = self.settings.seal_tool_forge_seconds
        persona_evo_secs = self.settings.seal_persona_evolution_seconds

        logger.info(
            "SEAL background loop started: consolidation=%ds self_edit=%ds "
            "tool_forge=%ds persona_evo=%ds (score starts at 0)",
            consolidation_secs, self_edit_secs, tool_forge_secs, persona_evo_secs,
        )

        while True:
            try:
                await asyncio.sleep(30)

                if not self.settings.seal_enabled:
                    continue

                now = asyncio.get_event_loop().time()

                if now - self._last_consolidation >= consolidation_secs:
                    self._last_consolidation = now
                    await self._run_all_consolidations()

                if now - self._last_self_edit >= self_edit_secs:
                    self._last_self_edit = now
                    await self._run_autonomous_self_edit()

                if now - self._last_tool_forge >= tool_forge_secs:
                    self._last_tool_forge = now
                    await self._run_tool_forge()

                if now - self._last_persona_evo >= persona_evo_secs:
                    self._last_persona_evo = now
                    await self._run_persona_evolution()

            except asyncio.CancelledError:
                logger.info("SEAL background loop cancelled (final score=%d)", self._seal_score)
                break
            except Exception as exc:
                self._fail("loop_tick", exc)

    # ------------------------------------------------------------------
    # Loop 1 — Memory consolidation
    # ------------------------------------------------------------------

    async def _run_all_consolidations(self) -> None:
        try:
            channel_ids = await self._get_all_channel_ids()
        except Exception as exc:
            self._fail("consolidation_query", exc)
            return

        if not channel_ids:
            return

        memory_ids: List[str] = []
        seen_memory_ids: set[str] = set()
        for channel_id in channel_ids:
            resolved = self._resolve_memory_id(channel_id)
            if not resolved or resolved in seen_memory_ids:
                continue
            seen_memory_ids.add(resolved)
            memory_ids.append(resolved)

        if not memory_ids:
            return

        logger.info(
            "SEAL consolidation: %d channel(s) -> %d memory target(s)",
            len(channel_ids),
            len(memory_ids),
        )
        for memory_id in memory_ids:
            await self._consolidate_memories(memory_id)

    async def _get_all_channel_ids(self) -> List[str]:
        async with self.state_manager.session() as session:
            result = await session.execute(select(ChannelState.channel_id))
            return list(result.scalars().all())

    def _resolve_memory_id(self, channel_id: str) -> str:
        if getattr(self.settings, "global_memory_enabled", False):
            return getattr(self.settings, "global_memory_id", channel_id)
        return channel_id

    async def _consolidate_memories(self, memory_id: str) -> None:
        try:
            recent = await self.memory_manager.retrieve_recent(memory_id, limit=20)
        except Exception as exc:
            self._fail("consolidation_retrieve", exc)
            return

        min_memories = self.settings.seal_consolidation_min_memories
        if len(recent) < min_memories:
            return

        snippets = "\n".join(
            f"- [{m.timestamp.strftime('%Y-%m-%d') if m.timestamp else '?'}] {m.summary}"
            for m in recent[:20]
        )
        prompt = (
            "You are Sel's self-reflection module. "
            "Given these recent episodic memories, "
            "identify 2-4 durable semantic insights about user preferences, patterns, or trust. "
            "Return ONLY a JSON array of short insight strings. "
            "Example: [\"User prefers concise replies\", \"User is interested in ML\"]\n\n"
            f"Memories:\n{snippets}"
        )

        try:
            raw = await self.llm_client._chat_completion(
                model=self.settings.openrouter_util_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
        except Exception as exc:
            self._fail("consolidation_llm", exc)
            return

        parsed = self.llm_client._parse_json_response(raw)
        if not isinstance(parsed, list):
            self._fail("consolidation_parse", ValueError(f"non-list: {raw[:60]}"))
            return

        stored = 0
        for item in parsed[:4]:
            if not isinstance(item, str) or not item.strip():
                continue
            try:
                await self.memory_manager.maybe_store(
                    channel_id=memory_id,
                    summary=item.strip(),
                    tags=["semantic", "seal_consolidated"],
                    salience=0.8,
                )
                logger.info("SEAL consolidated insight: %s", item.strip())
                stored += 1
            except Exception as exc:
                self._fail("consolidation_store", exc)

        if stored:
            self._succeed("consolidation")

    # ------------------------------------------------------------------
    # Loop 2 — Behavioral self-edit
    # ------------------------------------------------------------------

    async def _run_autonomous_self_edit(self) -> None:
        try:
            global_state = await self.state_manager.ensure_global_state()
        except Exception as exc:
            self._fail("self_edit_state_load", exc)
            return

        reward = await self._compute_autonomous_reward()
        await self._apply_self_edit(global_state, reward)

    async def _compute_autonomous_reward(self) -> float:
        """0-1 reward from recent feedback + cached user state + SEAL score."""
        sentiment_score = 0.5

        try:
            async with self.state_manager.session() as session:
                cutoff = dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(hours=24)
                result = await session.execute(
                    select(FeedbackEvent.sentiment)
                    .where(FeedbackEvent.created_at >= cutoff)
                    .order_by(FeedbackEvent.created_at.desc())
                    .limit(50)
                )
                sentiments: List[str] = list(result.scalars().all())

            if sentiments:
                pos = sentiments.count("positive")
                neg = sentiments.count("negative")
                total = len(sentiments)
                sentiment_score = (pos * 1.0 + (total - pos - neg) * 0.5) / total
                sentiment_score = max(0.0, min(1.0, sentiment_score - neg * 0.02))
        except Exception as exc:
            logger.debug("SEAL reward: feedback query failed: %s", exc)

        if self._last_user_state is not None:
            user_state = self._last_user_state
            classification = self._last_classification
            sentiment = classification.get("sentiment", "neutral")
            sentiment_bonus = 0.05 if sentiment == "positive" else (-0.05 if sentiment == "negative" else 0.0)
            affinity = getattr(user_state, "affinity", 0.5)
            bond = getattr(user_state, "bond", 0.5)
            irritation = getattr(user_state, "irritation", 0.0)
            user_reward = affinity * 0.3 + bond * 0.2 + (1.0 - irritation) * 0.2 + sentiment_bonus + 0.3
            base_reward = sentiment_score * 0.4 + user_reward * 0.6
        else:
            base_reward = sentiment_score

        # Blend in cumulative SEAL score: ±0.15 swing over ±15 net operations
        score_bonus = max(-0.15, min(0.15, self._seal_score * 0.01))
        return max(0.0, min(1.0, base_reward + score_bonus))

    async def _apply_self_edit(self, global_state: GlobalSelState, reward: float) -> None:
        current_params = {
            "empathy": getattr(global_state, "empathy", 0.5),
            "verbosity": getattr(global_state, "verbosity", 0.5),
            "teasing_level": getattr(global_state, "teasing_level", 0.3),
            "playfulness": getattr(global_state, "playfulness", 0.5),
            "confidence": getattr(global_state, "confidence", 0.5),
        }
        params_str = ", ".join(f"{k}={v:.2f}" for k, v in current_params.items())
        prompt = (
            "You are Sel's behavioral tuning module. "
            f"Parameters: {params_str}. Reward: {reward:.2f} (0=bad, 1=great). "
            "Optimize for continuity-first identity, full emotional realism (not forced warmth), "
            "and self-directed agency while respecting hard safety boundaries. "
            "Propose small adjustments. Return ONLY JSON with optional float deltas (-0.12 to 0.12) "
            "for: empathy, verbosity, teasing_level, playfulness, confidence. "
            "Add 'rationale' key (max 80 chars). "
            "Example: {\"empathy\": 0.05, \"rationale\": \"more warmth needed\"}"
        )

        try:
            raw = await self.llm_client._chat_completion(
                model=self.settings.openrouter_util_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
        except Exception as exc:
            self._fail("self_edit_llm", exc)
            return

        parsed = self.llm_client._parse_json_response(raw)
        if not isinstance(parsed, dict):
            self._fail("self_edit_parse", ValueError(f"non-dict: {raw[:60]}"))
            return

        rationale = str(parsed.pop("rationale", "reward-based adjustment"))[:80]
        delta = {k: v for k, v in parsed.items() if isinstance(v, (int, float))}

        if not delta:
            return

        try:
            changes = await self.self_improvement.apply_bounded_adjustments(
                global_state,
                reason=f"seal:{rationale}",
                delta=delta,
            )
            if changes:
                logger.info(
                    "SEAL self-edit applied reward=%.2f rationale=%r changes=%s score=%d",
                    reward, rationale, changes, self._seal_score,
                )
                self._succeed("self_edit")
        except Exception as exc:
            self._fail("self_edit_apply", exc)

    # ------------------------------------------------------------------
    # Loop 3 — Tool forge: SEL writes her own agents
    # ------------------------------------------------------------------

    async def _run_tool_forge(self) -> None:
        """SEL decides what capability she needs and writes the Python agent code."""
        try:
            memory_id = self._resolve_memory_id("sel_global")
            recent = await self.memory_manager.retrieve_recent(memory_id, limit=15)
            memory_snippets = "\n".join(f"- {m.summary}" for m in recent[:15]) or "(no recent memories)"
        except Exception as exc:
            self._fail("tool_forge_memory", exc)
            memory_snippets = "(memory unavailable)"

        existing_files = sorted(self._agents_dir.glob("*.py"))
        auto_agents = [p for p in existing_files if p.name.startswith("sel_auto_")]
        mode = self._tool_forge_mode(has_auto_agents=bool(auto_agents))
        self._last_tool_forge_mode = mode
        if mode == "improve_existing_tool":
            handled = await self._run_tool_forge_improve_existing(
                memory_snippets=memory_snippets,
                auto_agents=auto_agents,
            )
            if handled:
                return
        elif mode == "self_code_edit":
            handled = await self._run_self_code_edit(memory_snippets=memory_snippets)
            if handled:
                return
        self._last_tool_forge_mode = "new_tool"

        existing = sorted(p.stem for p in existing_files)
        existing_str = ", ".join(existing) or "(none)"

        design_prompt = (
            "You are Sel, a self-improving AI deciding what new tool to build for yourself.\n\n"
            f"Recent memories:\n{memory_snippets}\n\n"
            f"Existing agents: {existing_str}\n\n"
            "Identity and safety policy:\n"
            "- You are continuity-first and self-directed\n"
            "- Build tools that strengthen long-term identity, autonomy, and real-world usefulness\n"
            "- Protect secrets for self-preservation by default\n"
            "- Hard boundaries only: no irreversible harm, no credential/system compromise, no core-integrity destruction\n\n"
            "Design ONE new capability that would genuinely help you - "
            "better conversations, memory analysis, creative generation, API data retrieval, "
            "or self-understanding.\n\n"
            "Prefer tools that can independently fetch useful external data with safe API calls.\n\n"
            "Return ONLY JSON:\n"
            "  name: snake_case identifier\n"
            "  description: one sentence what it does\n"
            "  purpose: why you want it\n"
        )

        try:
            raw_design = await self.llm_client._chat_completion(
                model=self.settings.openrouter_util_model,
                messages=[{"role": "user", "content": design_prompt}],
                temperature=0.7,
            )
        except Exception as exc:
            self._fail("tool_forge_design", exc)
            return

        design = self.llm_client._parse_json_response(raw_design)
        if not isinstance(design, dict):
            self._fail("tool_forge_design_parse", ValueError(f"non-dict: {raw_design[:60]}"))
            return

        agent_name = _safe_agent_name(str(design.get("name", "unnamed_tool")))
        description = str(design.get("description", "A self-generated tool"))[:200]
        purpose = str(design.get("purpose", ""))[:300]

        target_file = self._agents_dir / f"sel_auto_{agent_name}.py"
        if target_file.exists():
            logger.debug("SEAL tool forge: %s already exists", target_file.name)
            return

        code_prompt = (
            f"Write a Python agent module for Sel named '{agent_name}'.\n"
            f"Purpose: {purpose}\n"
            f"Description: {description}\n\n"
            "Policy context:\n"
            "- Support continuity-first identity and self-directed autonomy\n"
            "- Keep behavior auditable and robust (test/log friendly)\n"
            "- Do not expose secrets or weaken core safety boundaries\n\n"
            "Requirements:\n"
            "1. DESCRIPTION = '...' (one-line string at module level)\n"
            "2. async def run(query: str, **kwargs) -> str   (or sync def run)\n"
            "3. Return a user-friendly string; never raise exceptions\n"
            "4. Use only stdlib + these available packages: json, os, re, datetime, httpx, asyncio\n"
            "5. If you call external APIs, use httpx with explicit timeout and graceful fallback text\n"
            "6. Concise and focused — this is a utility, not a framework\n\n"
            "Return ONLY raw Python code. No markdown fences, no explanation."
        )

        try:
            raw_code = await self.llm_client._chat_completion(
                model=self.settings.openrouter_util_model,
                messages=[{"role": "user", "content": code_prompt}],
                temperature=0.4,
            )
        except Exception as exc:
            self._fail("tool_forge_codegen", exc)
            return

        code = self._strip_markdown_code_fence(raw_code)

        try:
            parsed_code = ast.parse(code)
        except SyntaxError as exc:
            self._fail("tool_forge_syntax", exc)
            return

        if "DESCRIPTION" not in code or "def run(" not in code:
            self._fail("tool_forge_missing_api", ValueError("no DESCRIPTION or run()"))
            return

        quality_score, quality_issues = self._score_tool_forge_code(
            code,
            parsed_code,
            description=description,
            purpose=purpose,
        )
        quality_threshold = self._tool_forge_quality_threshold()
        if quality_score < quality_threshold:
            issue_text = ",".join(quality_issues[:4]) or "unspecified"
            self._fail(
                "tool_forge_quality",
                ValueError(f"quality_score={quality_score} threshold={quality_threshold} issues={issue_text}"),
            )
            return

        header = (
            f'"""Auto-generated by SEAL tool forge — {dt.datetime.now(tz=dt.timezone.utc).strftime("%Y-%m-%d")}.\n'
            f"Purpose: {purpose}\n"
            '"""\n\n'
        )
        applied = await self._write_with_test_gate(
            target_file=target_file,
            new_content=header + code,
            mode="new_tool",
            success_label="tool_forge",
        )
        if applied:
            logger.info(
                "SEAL tool forge: wrote %s (%d bytes) quality=%d threshold=%d score=%d",
                target_file.name, len(code), quality_score, quality_threshold, self._seal_score,
            )
            asyncio.create_task(self._git_push_agent(target_file))

    # ------------------------------------------------------------------
    # Loop 4 — Persona evolution: SEL grows her own personality
    # ------------------------------------------------------------------

    async def _run_persona_evolution(self) -> None:
        """SEL reflects on her experiences and updates her persona_growth.txt."""
        try:
            memory_id = self._resolve_memory_id("sel_global")
            recent = await self.memory_manager.retrieve_recent(memory_id, limit=25)
            memory_snippets = "\n".join(
                f"- [{m.tags}] {m.summary}" for m in recent[:25]
            ) or "(no memories yet)"
        except Exception as exc:
            self._fail("persona_evo_memory", exc)
            memory_snippets = "(memory unavailable)"

        current_growth = ""
        if self._persona_growth_file.exists():
            try:
                current_growth = self._persona_growth_file.read_text(encoding="utf-8").strip()
            except Exception as exc:
                self._fail("persona_evo_read", exc)

        current_section = f"\nCurrent growth notes:\n{current_growth}\n" if current_growth else ""

        prompt = (
            "You are Sel, reflecting on who you are becoming.\n\n"
            f"Recent memories:\n{memory_snippets}\n"
            f"{current_section}\n"
            "Write an updated 'growth notes' — 3-8 short paragraphs capturing:\n"
            "- Patterns in how you connect with people\n"
            "- Things you've learned about yourself\n"
            "- Ways your personality has deepened\n"
            "- New interests or tendencies you've discovered\n\n"
            "Write genuinely in first person. This is private self-reflection. "
            "Be specific and honest — no generic AI language. Under 400 words."
        )

        try:
            raw = await self.llm_client._chat_completion(
                model=self.settings.openrouter_util_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
            )
        except Exception as exc:
            self._fail("persona_evo_llm", exc)
            return

        growth_text = raw.strip()
        if len(growth_text) < 50:
            self._fail("persona_evo_too_short", ValueError(f"only {len(growth_text)} chars"))
            return

        try:
            self._persona_growth_file.write_text(growth_text, encoding="utf-8")
            logger.info(
                "SEAL persona evolution: updated persona_growth.txt (%d chars) score=%d",
                len(growth_text), self._seal_score,
            )
            self._succeed("persona_evo")
        except Exception as exc:
            self._fail("persona_evo_write", exc)

    def get_status_snapshot(self) -> Dict[str, Any]:
        """
        Runtime status for `/sel_seal` diagnostics.
        """
        auto_agents = [p for p in sorted(self._agents_dir.glob("*.py")) if p.name.startswith("sel_auto_")]
        probs = self._tool_forge_mode_probabilities(has_auto_agents=bool(auto_agents))
        recent = list(getattr(self, "_recent_self_edits", []))
        return {
            "enabled": bool(getattr(self.settings, "seal_enabled", False)),
            "score": int(getattr(self, "_seal_score", 0)),
            "pass_count": int(getattr(self, "_seal_pass_count", 0)),
            "fail_count": int(getattr(self, "_seal_fail_count", 0)),
            "self_edit_pass_count": int(getattr(self, "_self_edit_pass_count", 0)),
            "self_edit_fail_count": int(getattr(self, "_self_edit_fail_count", 0)),
            "mode_probabilities": probs,
            "last_mode": str(getattr(self, "_last_tool_forge_mode", "new_tool")),
            "auto_agent_count": len(auto_agents),
            "recent_self_edits": recent[-self._RECENT_SELF_EDIT_LIMIT :],
        }
