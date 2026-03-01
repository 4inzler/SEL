"""
System Operator Agent for Sel.

Runs host terminal commands when operator mode is enabled.
Supports restricted mode and full-privilege mode with a catastrophic-command denylist.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any

DESCRIPTION = "Run terminal commands and inspect host state (operator mode only)"
CACHEABLE = False
CACHE_TTL = 0

_DEFAULT_RESTRICTED_PREFIXES = (
    "pwd",
    "whoami",
    "date",
    "uptime",
    "ls",
    "dir",
    "cat",
    "head",
    "tail",
    "sed ",
    "grep ",
    "rg ",
    "find ",
    "du ",
    "df ",
    "ps ",
    "top",
    "free",
    "uname",
    "env",
    "printenv",
    "which ",
    "whereis ",
    "git status",
    "git log",
    "git diff",
    "docker ps",
    "docker logs",
    "ss ",
    "netstat",
    "ip a",
)

_DEFAULT_BLOCK_PATTERNS = (
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
)


def _bool_env(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, str(default))).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, default)))
    except Exception:
        return default


def _coerce_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    raw = str(value).strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _resolve_data_dir(data_dir_override: str | None = None) -> Path:
    raw_value = data_dir_override or os.environ.get("SEL_DATA_DIR", "./sel_data")
    raw = Path(str(raw_value)).expanduser()
    return raw if raw.is_absolute() else (Path.cwd() / raw).resolve()


def _block_patterns(block_patterns_override: Any = None) -> list[str]:
    override_items = _coerce_list(block_patterns_override)
    if override_items:
        return [item.lower() for item in override_items]

    raw = str(os.environ.get("SEL_OPERATOR_BLOCK_PATTERNS", "")).strip()
    if raw:
        return [item.strip().lower() for item in raw.split(",") if item.strip()]
    return [item.lower() for item in _DEFAULT_BLOCK_PATTERNS]


def _is_blocked(command: str, block_patterns: list[str] | None = None) -> bool:
    lowered = f" {command.lower()} "
    patterns = block_patterns if block_patterns is not None else _block_patterns()
    for marker in patterns:
        if marker and marker in lowered:
            return True
    return False


def _extract_command(prompt: str) -> str:
    text = (prompt or "").strip()
    if not text:
        return ""
    lower = text.lower()

    def _trim_tail(command_text: str) -> str:
        command = (command_text or "").strip()
        command = re.sub(r"^(?:was|is)\s+", "", command, flags=re.IGNORECASE).strip()
        tails = (
            r"\s+just\s+as\s+a\s+test$",
            r"\s+as\s+a\s+test$",
            r"\s+to\s+test\b.*$",
            r"\s+for\s+testing\b.*$",
            r"\s+to\s+verify\b.*$",
            r"\s+to\s+check\b.*$",
            r"\s+and\s+what\s+it\s+does\b.*$",
            r"\s+what\s+it\s+does\b.*$",
            r"\s+for\s+me$",
            r"\s+please$",
            r"\s+pls$",
            r"\s+if\s+you\s+can$",
            r"\s+real\s+quick$",
            r"\s+thanks$",
            r"\s+thank\s+you$",
        )
        for tail in tails:
            command = re.sub(tail, "", command, flags=re.IGNORECASE).strip()
        return command

    fenced = re.search(r"```(?:bash|sh)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        return _trim_tail(fenced.group(1).strip())

    quoted = re.search(
        r"\b(?:run|execute)\s+(?:the\s+)?(?:command\s+)?[`'\"]([^`'\"]+)[`'\"]",
        text,
        flags=re.IGNORECASE,
    )
    if quoted:
        return _trim_tail(quoted.group(1).strip())

    conversational = (
        r"^.*?\b(?:want|wanted|need|needed)\s+you\s+to\s+(?:please\s+)?(?:run|execute)\s+was\s+(.+)$",
        r"^.*?\b(?:want|wanted|need|needed)\s+you\s+to\s+(?:please\s+)?(?:run|execute)\s+(?:the\s+)?(?:command\s+)?(.+)$",
        r"^.*?\b(?:run|execute)\s+was\s+(?:the\s+)?(?:command\s+)?(.+)$",
    )
    for pattern in conversational:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            extracted = _trim_tail(match.group(1).strip())
            if extracted:
                return extracted

    polite = (
        r"^(?:can|could|would)\s+you\s+(?:please\s+)?(?:run|execute)\s+(.+)$",
        r"^(?:please|pls)\s+(?:run|execute)\s+(.+)$",
    )
    for pattern in polite:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            return _trim_tail(match.group(1).strip())

    prefixes = ("run:", "command:", "cmd:", "bash:", "terminal:")
    for prefix in prefixes:
        if lower.startswith(prefix):
            return _trim_tail(text[len(prefix):].strip())
    if lower.startswith("run "):
        return _trim_tail(text[4:].strip())
    if lower.startswith("bash "):
        return _trim_tail(text[5:].strip())
    if lower in {"status", "terminal status", "snapshot", "terminal snapshot"}:
        return (
            "pwd; whoami; date; "
            "ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -n 12; "
            "df -h | head -n 8"
        )
    return _trim_tail(text)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[truncated]"


def _inline(text: str, limit: int = 220) -> str:
    cleaned = " ".join((text or "").strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."


def _format_operator_output(
    *,
    input_text: str,
    command: str,
    exit_code: int,
    duration_ms: int,
    timed_out: bool,
    stdout_text: str,
    stderr_text: str,
) -> str:
    if timed_out:
        status = f"Timed out after `{duration_ms} ms`."
    elif exit_code == 0:
        status = f"Completed successfully (`exit 0`, `{duration_ms} ms`)."
    else:
        status = f"Failed (`exit {exit_code}`, `{duration_ms} ms`)."

    input_inline = _inline(input_text)
    lines = ["**Sel Operator**", "I ran this command for you:", f"`$ {command}`"]
    if input_inline:
        lines.append(f"From your input: `{input_inline}`")
    lines.append(status)

    has_stdout = bool(stdout_text.strip())
    has_stderr = bool(stderr_text.strip())

    if has_stdout:
        lines.append("")
        lines.append("**stdout**")
        lines.append(f"```text\n{stdout_text}\n```")
    if has_stderr:
        lines.append("")
        lines.append("**stderr**")
        lines.append(f"```text\n{stderr_text}\n```")
    if not has_stdout and not has_stderr:
        lines.append("")
        lines.append("_No terminal output._")

    return "\n".join(lines)


def _append_log(payload: dict[str, Any], *, data_dir_override: str | None = None) -> None:
    try:
        data_dir = _resolve_data_dir(data_dir_override)
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / "operator_command_log.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


def _approval_required_and_missing(
    user_id: str,
    *,
    require_approval_user: bool | None = None,
    approval_user_id: str | None = None,
) -> bool:
    required = _coerce_bool(
        require_approval_user,
        _bool_env("SEL_OPERATOR_REQUIRE_APPROVAL_USER", True),
    )
    if not required:
        return False

    approval_user = str(approval_user_id or os.environ.get("APPROVAL_USER_ID", "")).strip()
    if not approval_user:
        return False
    return str(user_id or "").strip() != approval_user


def _restricted_command_allowed(command: str) -> bool:
    lowered = command.strip().lower()
    if not lowered:
        return False
    for prefix in _DEFAULT_RESTRICTED_PREFIXES:
        if lowered == prefix or lowered.startswith(prefix):
            return True
    return False


async def _run_shell(command: str, timeout_seconds: int) -> tuple[int, str, str, bool]:
    proc = await asyncio.create_subprocess_exec(
        "/usr/bin/bash",
        "-lc",
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    timed_out = False
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=max(3, timeout_seconds))
    except asyncio.TimeoutError:
        timed_out = True
        proc.kill()
        stdout_bytes, stderr_bytes = await proc.communicate()
    return proc.returncode or 0, stdout_bytes.decode("utf-8", errors="replace"), stderr_bytes.decode("utf-8", errors="replace"), timed_out


async def run(prompt: str, user_id: str = "", channel_id: str = "", **kwargs) -> str:
    enabled = _coerce_bool(
        kwargs.get("operator_mode_enabled"),
        _bool_env("SEL_OPERATOR_MODE_ENABLED", False),
    )
    full_privileges = _coerce_bool(
        kwargs.get("operator_full_host_privileges"),
        _bool_env("SEL_OPERATOR_FULL_HOST_PRIVILEGES", False),
    )
    require_approval_user = _coerce_bool(
        kwargs.get("operator_require_approval_user"),
        _bool_env("SEL_OPERATOR_REQUIRE_APPROVAL_USER", True),
    )
    approval_user_id = str(kwargs.get("operator_approval_user_id") or "").strip() or str(
        os.environ.get("APPROVAL_USER_ID", "")
    ).strip()
    timeout_seconds = _coerce_int(
        kwargs.get("operator_command_timeout_seconds"),
        _int_env("SEL_OPERATOR_COMMAND_TIMEOUT_SECONDS", 45),
    )
    max_output = _coerce_int(
        kwargs.get("operator_max_output_chars"),
        _int_env("SEL_OPERATOR_MAX_OUTPUT_CHARS", 6000),
    )
    data_dir_override = str(kwargs.get("operator_data_dir") or "").strip() or None
    block_patterns = _block_patterns(kwargs.get("operator_block_patterns"))

    command = _extract_command(prompt)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    if not enabled:
        return (
            "Operator mode is disabled. Enable with `SEL_OPERATOR_MODE_ENABLED=true`."
        )
    if _approval_required_and_missing(
        str(user_id),
        require_approval_user=require_approval_user,
        approval_user_id=approval_user_id,
    ):
        return "Operator command denied: user is not authorized for operator mode."
    if not command:
        return (
            "No command detected. Use `run: <command>` or ask for `terminal snapshot`."
        )
    if _is_blocked(command, block_patterns):
        _append_log(
            {
                "timestamp_utc": now,
                "user_id": str(user_id),
                "channel_id": str(channel_id),
                "command": command,
                "blocked": True,
                "reason": "block_pattern",
            }
            ,
            data_dir_override=data_dir_override,
        )
        return "Operator blocked command due to denylist policy."
    if not full_privileges and not _restricted_command_allowed(command):
        _append_log(
            {
                "timestamp_utc": now,
                "user_id": str(user_id),
                "channel_id": str(channel_id),
                "command": command,
                "blocked": True,
                "reason": "restricted_mode_prefix",
            }
            ,
            data_dir_override=data_dir_override,
        )
        return (
            "Operator is in restricted mode and this command is not allowed. "
            "Set `SEL_OPERATOR_FULL_HOST_PRIVILEGES=true` to allow broad commands."
        )

    started = dt.datetime.now(dt.timezone.utc)
    code, stdout_text, stderr_text, timed_out = await _run_shell(command, timeout_seconds)
    duration_ms = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000)
    stdout_trim = _truncate(stdout_text.strip(), max_output)
    stderr_trim = _truncate(stderr_text.strip(), max_output)

    _append_log(
        {
            "timestamp_utc": now,
            "user_id": str(user_id),
            "channel_id": str(channel_id),
            "command": command,
            "blocked": False,
            "timed_out": timed_out,
            "exit_code": int(code),
            "duration_ms": duration_ms,
            "full_privileges": full_privileges,
        },
        data_dir_override=data_dir_override,
    )

    return _format_operator_output(
        input_text=prompt,
        command=command,
        exit_code=int(code),
        duration_ms=duration_ms,
        timed_out=bool(timed_out),
        stdout_text=stdout_trim,
        stderr_text=stderr_trim,
    )
