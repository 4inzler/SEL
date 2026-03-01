"""Helpers for autonomous agent selection and invocation planning."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional


_URL_RE = re.compile(r"https?://\S+", flags=re.IGNORECASE)
_EXTERNAL_DATA_HINTS = (
    "weather",
    "forecast",
    "temperature",
    "rain",
    "snow",
    "wind",
    "search",
    "lookup",
    "look up",
    "find",
    "news",
    "price",
    "stock",
    "crypto",
    "api",
    "endpoint",
    "http",
    "https",
    "status",
    "uptime",
    "docs",
    "documentation",
    "json",
    "terminal",
    "shell",
    "command",
    "process",
    "cpu",
    "memory",
    "disk",
    "logs",
    "service",
    "daemon",
    "system",
)
_HARD_BLOCKED_AGENTS = {"system_agent", "bash_agent", "bash"}
_SHELL_COMMAND_HINTS = {
    "playerctl",
    "ls",
    "pwd",
    "whoami",
    "date",
    "uptime",
    "cat",
    "head",
    "tail",
    "sed",
    "grep",
    "rg",
    "find",
    "du",
    "df",
    "ps",
    "top",
    "free",
    "uname",
    "env",
    "printenv",
    "which",
    "whereis",
    "git",
    "docker",
    "systemctl",
    "journalctl",
    "service",
    "ip",
    "ss",
    "netstat",
    "curl",
    "wget",
    "python",
    "python3",
    "pip",
    "pip3",
    "npm",
    "node",
    "uv",
    "echo",
}
_OPERATOR_INTENT_MARKERS = (
    "run:",
    "command:",
    "cmd:",
    "bash:",
    "terminal:",
    "shell command",
    "run command",
    "run a command",
    "run the command",
    "execute a command",
    "execute the command",
)
_NON_COMMAND_EXPLANATION_HINTS = (
    "explain",
    "why",
    "what is",
    "what does",
    "how does",
    "describe",
    "tell me about",
)
_NON_COMMAND_FIRST_TOKENS = {"explain", "why", "what", "how", "describe", "tell"}
_NON_COMMAND_ARG_TOKENS = {
    "me",
    "you",
    "this",
    "that",
    "it",
    "please",
    "pls",
    "now",
    "later",
    "today",
    "tomorrow",
    "tonight",
    "why",
    "how",
    "what",
    "when",
    "where",
}


@dataclass(frozen=True)
class AgentPlan:
    agent: str
    action: str
    confidence: float
    reason: str
    explicit: bool = False


def _extract_shell_candidate(text: str) -> str:
    candidate = (text or "").strip()
    if not candidate:
        return ""
    if candidate.startswith("`") and candidate.endswith("`") and len(candidate) > 2:
        candidate = candidate[1:-1].strip()

    def _trim_tail(command_text: str) -> str:
        command = (command_text or "").strip()
        command = re.sub(r"^(?:was|is)\s+", "", command, flags=re.IGNORECASE).strip()
        for tail in (
            r"\s+just\s+as\s+a\s+test$",
            r"\s+as\s+a\s+test$",
            r"\s+to\s+test\b.*$",
            r"\s+for\s+testing\b.*$",
            r"\s+to\s+verify\b.*$",
            r"\s+to\s+check\b.*$",
            r"\s+and\s+what\s+it\s+does\b.*$",
            r"\s+what\s+it\s+does\b.*$",
            r"\s+right\s+now$",
            r"\s+now$",
            r"\s+for\s+me$",
            r"\s+please$",
            r"\s+pls$",
            r"\s+if\s+you\s+can$",
            r"\s+real\s+quick$",
            r"\s+thanks$",
            r"\s+thank\s+you$",
        ):
            command = re.sub(tail, "", command, flags=re.IGNORECASE).strip()
        return command

    def _looks_command_fragment(fragment: str) -> bool:
        parts = fragment.split()
        if not parts:
            return False
        first = re.sub(r"[^a-z0-9._/-]", "", parts[0].lower())
        if not first:
            return False
        if first in _SHELL_COMMAND_HINTS:
            return True
        if first.startswith(("./", "~/", "/")):
            return True
        return bool(re.search(r"[-_./0-9]", first))

    # Drop a leading name call like "sel, can you run ..."
    candidate = re.sub(
        r"^[a-z][a-z0-9_-]{1,31}[,:-]?\s+(?=(?:can|could|would|please|pls|run|execute)\b)",
        "",
        candidate,
        flags=re.IGNORECASE,
    ).strip()

    quoted = re.search(
        r"\b(?:run|execute)\s+(?:the\s+)?(?:command\s+)?[`'\"]([^`'\"]+)[`'\"]",
        candidate,
        flags=re.IGNORECASE,
    )
    if quoted:
        return _trim_tail(quoted.group(1).strip())

    conversational_patterns = (
        r"^.*?\b(?:want|wanted|need|needed)\s+you\s+to\s+(?:please\s+)?(?:run|execute)\s+was\s+(.+)$",
        r"^.*?\b(?:want|wanted|need|needed)\s+you\s+to\s+(?:please\s+)?(?:run|execute)\s+(?:the\s+)?(?:command\s+)?(.+)$",
        r"^.*?\b(?:run|execute)\s+was\s+(?:the\s+)?(?:command\s+)?(.+)$",
    )
    for pattern in conversational_patterns:
        match = re.match(pattern, candidate, flags=re.IGNORECASE)
        if match:
            extracted = _trim_tail(match.group(1).strip())
            if extracted:
                return extracted

    embedded_patterns = (
        r"\b(?:can|could|would)\s+you\s+(?:please\s+)?(?:run|execute)\s+(?:the\s+)?(?:command\s+)?(.+)$",
        r"\b(?:please|pls)\s+(?:run|execute)\s+(?:the\s+)?(?:command\s+)?(.+)$",
    )
    for pattern in embedded_patterns:
        match = re.search(pattern, candidate, flags=re.IGNORECASE)
        if match:
            extracted = _trim_tail(match.group(1).strip())
            if extracted:
                extracted = re.sub(r"^(?:the|a)\s+command\b", "", extracted, flags=re.IGNORECASE).strip()
                if _looks_command_fragment(extracted):
                    return extracted
                with_match = re.search(r"\bwith\s+(.+)$", extracted, flags=re.IGNORECASE)
                if with_match:
                    with_extracted = _trim_tail(with_match.group(1).strip())
                    if _looks_command_fragment(with_extracted):
                        return with_extracted

    polite_patterns = (
        r"^(?:can|could|would)\s+you\s+(?:please\s+)?(?:run|execute)\s+(?:the\s+)?command\s+(.+)$",
        r"^(?:can|could|would)\s+you\s+(?:please\s+)?(?:run|execute)\s+(.+)$",
        r"^(?:please|pls)\s+(?:run|execute)\s+(?:the\s+)?command\s+(.+)$",
        r"^(?:please|pls)\s+(?:run|execute)\s+(.+)$",
        r"^run\s+(?:the\s+)?command\s+(.+)$",
        r"^run\s+(.+)$",
        r"^execute\s+(?:the\s+)?command\s+(.+)$",
        r"^execute\s+(.+)$",
    )
    for pattern in polite_patterns:
        match = re.match(pattern, candidate, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            break

    candidate = re.sub(r"^(?:the|a)\s+command\s+", "", candidate, flags=re.IGNORECASE).strip()

    with_match = re.search(r"\bwith\s+(.+)$", candidate, flags=re.IGNORECASE)
    if with_match:
        extracted = _trim_tail(with_match.group(1).strip())
        if _looks_command_fragment(extracted):
            return extracted

    return _trim_tail(candidate)


def _looks_like_shell_command(text: str) -> bool:
    candidate = _extract_shell_candidate(text)
    if not candidate or len(candidate) > 220:
        return False
    if "?" in candidate:
        return False
    if "\n" in candidate and "```" not in text:
        return False
    if any(op in candidate for op in ("|", "&&", "||", ";", "$(", ">", "<")):
        return True

    tokens = candidate.split()
    if not tokens:
        return False
    first = re.sub(r"[^a-z0-9._/-]", "", tokens[0].lower())
    second = re.sub(r"[^a-z0-9._/-]", "", tokens[1].lower()) if len(tokens) > 1 else ""

    if len(tokens) == 1 and re.match(r"^[a-z0-9._/-]+$", first):
        if first in _SHELL_COMMAND_HINTS or re.search(r"[-_./0-9]", first):
            return True

    if first in _SHELL_COMMAND_HINTS:
        return True
    if candidate.startswith("./") or candidate.startswith("~/") or candidate.startswith("/"):
        return True
    if (
        len(tokens) >= 2
        and first not in _NON_COMMAND_FIRST_TOKENS
        and second not in _NON_COMMAND_ARG_TOKENS
        and re.match(r"^[a-z0-9._/-]+$", first)
        and (re.search(r"[-_./0-9]", first) or second.startswith("-") or re.search(r"[-_./0-9]", second))
    ):
        return True
    if re.search(r"\b(?:run|execute)\b", (text or "").lower()):
        if (
            first
            and first not in {"the", "a", "an", "command"}
            and first not in _NON_COMMAND_FIRST_TOKENS
            and second not in _NON_COMMAND_ARG_TOKENS
            and re.match(r"^[a-z0-9._/-]+$", first)
            and (re.search(r"[-_./0-9]", first) or second.startswith("-") or re.search(r"[-_./0-9]", second))
        ):
            return True
    return False


def score_system_operator_command_intent(
    content: str,
    *,
    action: str = "",
    reason: str = "",
    explicit: bool = False,
) -> float:
    """
    Return 0.0-1.0 confidence that a system_operator request is command intent.

    This is used to decide whether Sel should return raw terminal output directly
    versus rephrasing through normal conversational generation.
    """
    text = (content or "").strip()
    act = (action or "").strip()
    lower_text = text.lower()
    lower_action = act.lower()
    lower_reason = (reason or "").strip().lower()
    score = 0.0
    action_looks_command_like = bool(act) and _looks_like_shell_command(act)

    if lower_reason in {"fast_path_operator", "fast_path_operator_shell"}:
        score += 0.08 if lower_reason == "fast_path_operator" else 0.14
    elif lower_reason == "explicit_user_request":
        score += 0.06
    if any(marker in lower_text for marker in _OPERATOR_INTENT_MARKERS):
        score += 0.16
    if any(marker in lower_action for marker in _OPERATOR_INTENT_MARKERS):
        score += 0.16
    if _looks_like_shell_command(text):
        score += 0.36
    if action_looks_command_like:
        score += 0.58
    if any(op in act for op in ("|", "&&", "||", ";")):
        score += 0.25
    if explicit and re.match(r"^(?:run|execute)\b", lower_text) and action_looks_command_like:
        score += 0.12

    # Penalize explanatory asks that mention tools but don't look command-like.
    if any(hint in lower_text for hint in _NON_COMMAND_EXPLANATION_HINTS):
        if not (_looks_like_shell_command(text) or _looks_like_shell_command(act)):
            score -= 0.4
    if lower_action.startswith(("explain ", "why ", "what ", "how ", "describe ", "tell ")):
        if not action_looks_command_like:
            score -= 0.55
    if "?" in text and not (_looks_like_shell_command(text) or _looks_like_shell_command(act)):
        score -= 0.12

    return max(0.0, min(1.0, score))


def is_system_operator_command_intent(
    content: str,
    *,
    action: str = "",
    reason: str = "",
    explicit: bool = False,
    min_score: float = 0.6,
) -> bool:
    threshold = max(0.0, min(1.0, float(min_score)))
    return score_system_operator_command_intent(
        content,
        action=action,
        reason=reason,
        explicit=explicit,
    ) >= threshold


def plan_fast_path_agent_request(
    content: str,
    *,
    agent_names: Iterable[str],
    direct_question: bool = False,
    operator_intent_threshold: float = 0.6,
) -> Optional[AgentPlan]:
    """
    Deterministic low-latency router for obvious tool intents.

    This avoids an extra utility-model planner call for clear cases like:
    - URL/web lookup -> browser
    - weather forecast -> weather
    - terminal command intent -> system_operator
    """
    text = (content or "").strip()
    if not text:
        return None
    lower = text.lower()
    extracted_shell = _extract_shell_candidate(text)
    available = {name.lower(): name for name in agent_names if str(name).strip()}

    def _has(*markers: str) -> bool:
        return any(marker in lower for marker in markers)

    # Explicit command-like terminal intent
    operator_name = available.get("system_operator")
    operator_threshold = max(0.0, min(1.0, float(operator_intent_threshold)))
    if operator_name and _has(
        "run:",
        "command:",
        "cmd:",
        "bash:",
        "terminal:",
        "terminal snapshot",
        "shell command",
        "run command",
        "run a command",
        "run the command",
        "execute a command",
        "execute the command",
    ):
        extracted = _extract_shell_candidate(text)
        op_score = score_system_operator_command_intent(
            text,
            action=extracted or text,
            reason="fast_path_operator",
            explicit=False,
        )
        if op_score < operator_threshold:
            return None
        return AgentPlan(
            agent=operator_name,
            action=extracted or text,
            confidence=0.99,
            reason="fast_path_operator",
            explicit=False,
        )
    if (
        operator_name
        and extracted_shell
        and extracted_shell != text
        and _looks_like_shell_command(extracted_shell)
    ):
        op_score = score_system_operator_command_intent(
            text,
            action=extracted_shell,
            reason="fast_path_operator_shell",
            explicit=False,
        )
        if op_score >= operator_threshold:
            return AgentPlan(
                agent=operator_name,
                action=extracted_shell,
                confidence=0.96,
                reason="fast_path_operator_shell",
                explicit=False,
            )
    if operator_name and _looks_like_shell_command(text):
        extracted = _extract_shell_candidate(text)
        op_score = score_system_operator_command_intent(
            text,
            action=extracted,
            reason="fast_path_operator_shell",
            explicit=False,
        )
        if op_score < operator_threshold:
            return None
        return AgentPlan(
            agent=operator_name,
            action=extracted,
            confidence=0.97,
            reason="fast_path_operator_shell",
            explicit=False,
        )

    browser_name = available.get("browser")
    weather_name = available.get("weather")

    # URL almost always means browser lookup.
    if browser_name and _URL_RE.search(text):
        return AgentPlan(
            agent=browser_name,
            action=text,
            confidence=0.97,
            reason="fast_path_url",
            explicit=False,
        )

    # Deterministic weather route.
    if weather_name and _has("weather", "forecast", "temperature", "rain", "snow", "wind"):
        return AgentPlan(
            agent=weather_name,
            action=text,
            confidence=0.95,
            reason="fast_path_weather",
            explicit=False,
        )

    # Deterministic web lookup route for obvious browsing asks.
    if browser_name and (
        _has(
            "search",
            "look up",
            "lookup",
            "check status",
            "latest news",
            "docs",
            "documentation",
            "web",
            "website",
        )
        or (direct_question and _has("latest", "current", "status", "uptime", "price", "crypto", "stock"))
    ):
        return AgentPlan(
            agent=browser_name,
            action=text,
            confidence=0.91,
            reason="fast_path_browser",
            explicit=False,
        )

    return None


def is_agent_allowed_for_autonomy(agent_name: str, safe_agents: Iterable[str]) -> bool:
    """Hard allowlist gate for runtime autonomy."""
    name = (agent_name or "").strip()
    if not name:
        return False
    lowered = name.lower()
    if lowered in _HARD_BLOCKED_AGENTS:
        return False
    if lowered.startswith("sel_auto_"):
        return True
    safe_set = {item.strip().lower() for item in safe_agents if item and item.strip()}
    return lowered in safe_set


def match_explicit_agent_request(content: str, agent_names: Iterable[str]) -> Optional[tuple[str, str]]:
    """Match direct requests that explicitly name an agent/tool."""
    if not content:
        return None
    lower = content.lower()
    for name in agent_names:
        key = name.lower()
        patterns = (
            f"agent:{key}",
            f"use {key}",
            f"run {key}",
            f"{key} tool",
            f"{key} agent",
        )
        for marker in patterns:
            idx = lower.find(marker)
            if idx == -1:
                continue
            after = content[idx + len(marker):].strip()
            return name, after or content.strip()
    return None


def should_consider_agent_autonomy(
    content: str,
    *,
    direct_question: bool,
    continuation_hit: bool,
) -> bool:
    """Fast heuristic gate before invoking extra planning calls."""
    text = (content or "").strip()
    if not text:
        return False
    lower = text.lower()
    if _URL_RE.search(text):
        return True
    if any(hint in lower for hint in _EXTERNAL_DATA_HINTS):
        return True
    if direct_question and not continuation_hit:
        return any(
            cue in lower
            for cue in ("latest", "current", "check", "check status", "how much", "can you fetch")
        )
    return False


def build_agent_selection_prompt(
    *,
    user_content: str,
    recent_context: str,
    agents: list[tuple[str, str]],
    max_recent_chars: int = 1000,
) -> str:
    """Build util-model prompt asking whether to use one agent."""
    catalog = "\n".join(f"- {name}: {description}" for name, description in agents)
    recent_trimmed = (recent_context or "").strip()
    if len(recent_trimmed) > max_recent_chars:
        recent_trimmed = recent_trimmed[-max_recent_chars:]
    if not recent_trimmed:
        recent_trimmed = "(none)"

    return (
        "You are Sel's tool planner.\n"
        "Decide if one agent should be run before Sel replies.\n"
        "Only use an agent when external lookup/action is genuinely useful.\n"
        "Prefer no-agent for normal chat or subjective/emotional discussion.\n\n"
        "Return ONLY JSON:\n"
        "{\"use_agent\": bool, \"agent\": \"name\", \"action\": \"input text\", "
        "\"confidence\": 0.0-1.0, \"reason\": \"short\"}\n\n"
        f"Available agents:\n{catalog}\n\n"
        f"Recent context:\n{recent_trimmed}\n\n"
        f"User message:\n{user_content.strip() or '(empty)'}"
    )


def coerce_agent_plan(
    parsed: object,
    *,
    allowed_agents: Iterable[str],
    min_confidence: float,
) -> Optional[AgentPlan]:
    """Validate util-model output and convert it into an executable plan."""
    if not isinstance(parsed, dict):
        return None
    use_agent = bool(parsed.get("use_agent", False))
    if not use_agent:
        return None

    allowed_map = {name.lower(): name for name in allowed_agents}
    raw_agent = str(parsed.get("agent", "")).strip()
    if not raw_agent:
        return None
    agent = allowed_map.get(raw_agent.lower())
    if not agent:
        return None

    raw_confidence = parsed.get("confidence", 0.0)
    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    if confidence < min_confidence:
        return None

    action = str(parsed.get("action", "")).strip()
    reason = str(parsed.get("reason", "")).strip() or "planner_selected"
    return AgentPlan(
        agent=agent,
        action=action,
        confidence=confidence,
        reason=reason[:120],
        explicit=False,
    )
