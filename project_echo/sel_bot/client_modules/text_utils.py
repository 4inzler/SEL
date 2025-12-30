"""
Text Processing Utilities

Extracted from discord_client.py (refactoring 1859-line monolith).

Contains helper functions for:
- Text processing and normalization
- Keyword extraction
- Reply splitting and cadence
- Agent request matching
- Authorization checks
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from ..hormones import HormoneVector


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp value v to range [lo, hi]"""
    return max(lo, min(hi, v))


def extract_opener(text: str, max_words: int = 4) -> str:
    """Extract the opening words of a message (up to max_words)"""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    cleaned = cleaned.replace("\n", " ")
    cleaned = re.sub(r"^[@#][A-Za-z0-9_]+\s*", "", cleaned)
    cleaned = re.sub(r"^[\"'`\(\[]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    words = re.findall(r"[A-Za-z0-9']+", cleaned.lower())
    if not words:
        return ""
    return " ".join(words[:max_words])


def name_called(lowered_content: str, bot_name: str) -> bool:
    """Check if bot name is mentioned in content"""
    if not lowered_content:
        return False
    name = (bot_name or "").strip().lower()
    if not name:
        return False
    pattern = rf"\b{re.escape(name)}\b"
    return re.search(pattern, lowered_content) is not None


def safe_to_split_reply(text: str) -> bool:
    """Check if reply can be safely split (no code blocks or lists)"""
    if "```" in text:
        return False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("-", "*", "1.", "2.", "3.")):
            return False
    return True


def split_reply_for_cadence(text: str, max_parts: int = 3) -> list[str]:
    """Split long reply into parts for natural cadence"""
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    if not safe_to_split_reply(cleaned):
        return [cleaned]
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) < 3:
        return [cleaned]
    parts_count = 2 if len(sentences) <= 4 else min(max_parts, 3)
    total_len = sum(len(s) for s in sentences)
    target_len = max(1, int(total_len / parts_count))
    parts: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        if current and current_len + len(sentence) > target_len and len(parts) < parts_count - 1:
            parts.append(" ".join(current))
            current = [sentence]
            current_len = len(sentence)
        else:
            current.append(sentence)
            current_len += len(sentence)
    if current:
        parts.append(" ".join(current))
    return parts


def followup_delay(chunk: str, hormones: HormoneVector, index: int) -> float:
    """Calculate delay before sending followup message chunk"""
    base = 0.35 + min(0.8, (len(chunk) / 200.0) * 0.25)
    mood = 0.2 - (hormones.melatonin * 0.2) + (hormones.adrenaline * 0.1) - (hormones.patience * 0.05)
    return max(0.2, min(1.4, base + mood + (index * 0.05)))


def extract_topic_keywords(recent_msgs: list[str]) -> list[str]:
    """Extract top 3 topic keywords from recent messages"""
    stopwords = {
        "the", "and", "but", "with", "that", "this", "from", "you", "your",
        "about", "just", "like", "what", "when", "where", "how", "why",
        "are", "was", "were", "they", "them", "their", "have", "has", "had",
        "not", "for", "lol", "lmao", "yeah", "okay", "ok", "tbh", "ngl",
    }
    counts: Counter[str] = Counter()
    for entry in recent_msgs:
        text = entry.split(":", 1)[1] if ":" in entry else entry
        for token in re.findall(r"[A-Za-z0-9']+", text.lower()):
            if len(token) < 4 or token in stopwords:
                continue
            counts[token] += 1
    return [word for word, _ in counts.most_common(3)]


def add_human_touches(reply: str, hormones: HormoneVector) -> str:
    """
    DISABLED: Fake typo injection removed for security audit compliance.

    Previously injected manufactured typos (missing apostrophes, etc.).
    This was identified in security audit as potentially undermining trust
    and making the bot appear malfunctioning.

    Authenticity should come from the language model and prompt engineering,
    not from manufactured errors injected post-generation.

    Function kept for backwards compatibility but now returns input unchanged.
    """
    # Return reply unchanged - no manufactured typos
    return reply


def adjust_repeated_opener(reply: str, recent_openers: list[str]) -> str:
    """Remove filler words if reply opener was used recently"""
    if not reply or not recent_openers:
        return reply
    opener = extract_opener(reply)
    if not opener:
        return reply
    recent_set = {o.lower() for o in recent_openers}
    if opener not in recent_set:
        return reply
    for filler in ("yeah", "oh", "hey", "lol", "lmao", "tbh", "ngl", "so", "ok", "okay", "hmm"):
        if reply.lower().startswith(f"{filler} "):
            return reply[len(filler):].lstrip()
    return reply


def build_channel_dynamics(
    speaker_counts: Counter[str],
    reply_to: str,
    topic_keywords: list[str],
) -> Optional[str]:
    """Build context string about channel conversation dynamics"""
    if len(speaker_counts) < 2:
        return None
    top_speakers = [name for name, _ in speaker_counts.most_common(4)]
    if reply_to not in top_speakers:
        top_speakers.insert(0, reply_to)
    names = ", ".join(top_speakers[:4])
    topic_hint = ""
    if topic_keywords:
        topic_hint = f"\nRecent topics: {', '.join(topic_keywords)}."
    return (
        f"Recent active speakers: {names}."
        f"{topic_hint}\n"
        f"You're replying to {reply_to}. If you reference someone else, name them so it's clear."
    )


def match_agent_request(content: str, agent_names: list[str]) -> Optional[tuple[str, str]]:
    """Match message content to agent request patterns"""
    lower = content.lower()
    if not agent_names:
        return None
    for name in agent_names:
        key = name.lower()
        if f"agent:{key}" in lower:
            after = lower.split(f"agent:{key}", 1)[1].strip()
            return name, (after or content)
        if f"use {key}" in lower:
            after = lower.split(f"use {key}", 1)[1].strip()
            return name, after or content
        if f"run {key}" in lower:
            after = lower.split(f"run {key}", 1)[1].strip()
            return name, after or content
        if f"{key} agent" in lower:
            after = lower.split(f"{key} agent}", 1)[1].strip()
            return name, after or content
        if f"{key} tool" in lower:
            after = lower.split(f"{key} tool", 1)[1].strip()
            return name, after or content
        # Bash agent intent routing
        if key in {"bash_agent", "bash"}:
            if lower.startswith("bash "):
                return name, content.split(" ", 1)[1].strip()
            if lower.startswith("!bash"):
                return name, content.split("!bash", 1)[1].strip()
            if "bash:" in lower:
                return name, content.split("bash:", 1)[1].strip()
            if "run bash" in lower:
                after = lower.split("run bash", 1)[1].strip()
                # recover original slice length
                offset = content.lower().find("run bash") + len("run bash")
                return name, content[offset:].strip() or after
            if "shell command" in lower or "run command" in lower:
                after = lower.split("command", 1)[1].strip()
                offset = content.lower().find("command") + len("command")
                return name, content[offset:].strip() or after
            if "```bash" in lower:
                start = content.lower().find("```bash") + len("```bash")
                end = content.lower().find("```", start)
                snippet = content[start:end] if end != -1 else content[start:]
                return name, snippet.strip()
    return None


def bash_command_from_keywords(content: str) -> Optional[str]:
    """Extract bash command from keyword patterns"""
    lower = content.lower()
    # Common explicit requests
    if "fastfetch" in lower or "fast fetch" in lower:
        return "fastfetch"
    if lower.startswith("bash "):
        return content.split(" ", 1)[1].strip()
    if "run command" in lower:
        idx = lower.find("run command") + len("run command")
        return content[idx:].strip()
    return None


def is_authorized(user_id: int, allowed_id: Optional[int]) -> bool:
    """Check if user is authorized (allowed_id None means all authorized)"""
    return allowed_id is None or user_id == allowed_id
