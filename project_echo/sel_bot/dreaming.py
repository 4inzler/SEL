"""Dream processing helpers for offline memory consolidation."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from .biological_systems import memory_affects_mood


_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "been",
    "before",
    "because",
    "could",
    "does",
    "from",
    "have",
    "into",
    "just",
    "like",
    "more",
    "most",
    "only",
    "other",
    "that",
    "them",
    "then",
    "there",
    "they",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _as_memories(memories: Iterable[Any]) -> list[Any]:
    return list(memories or [])


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_text_list(value: Any, *, limit: int, fallback: list[str] | None = None) -> list[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned[:280]] if cleaned else (fallback or [])
    if not isinstance(value, list):
        return fallback or []
    output: list[str] = []
    for item in value:
        text = str(item).strip()
        if not text:
            continue
        output.append(text[:280])
        if len(output) >= limit:
            break
    return output or (fallback or [])


def _coerce_delta_map(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, float] = {}
    for key, raw in value.items():
        name = str(key).strip()
        if not name:
            continue
        result[name] = _clamp(_coerce_float(raw), -0.2, 0.2)
    return result


def _extract_theme_terms(memories: Iterable[Any], *, limit: int = 6) -> list[str]:
    counts: dict[str, int] = {}
    for mem in _as_memories(memories)[:20]:
        summary = str(getattr(mem, "summary", "") or "")
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", summary.lower()):
            if token in _STOPWORDS:
                continue
            counts[token] = counts.get(token, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [word for word, _ in ordered[:limit]]


def aggregate_emotional_signal(memories: Iterable[Any], *, limit: int = 30) -> dict[str, float]:
    """Aggregate memory-linked emotional residue from recent memories."""
    signal: dict[str, float] = {}
    for mem in _as_memories(memories)[: max(1, int(limit))]:
        summary = str(getattr(mem, "summary", "") or "").strip()
        if not summary:
            continue
        salience = _clamp(_coerce_float(getattr(mem, "salience", 0.5), default=0.5), 0.2, 1.0)
        for hormone, delta in memory_affects_mood(summary).items():
            signal[hormone] = signal.get(hormone, 0.0) + (float(delta) * salience)
    return {k: round(_clamp(v, -1.0, 1.0), 4) for k, v in signal.items() if abs(v) >= 0.004}


def suggested_cleanup_deltas(
    emotional_signal: Mapping[str, float],
    *,
    llm_suggestion: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    """Build bounded mood cleanup deltas for a dream consolidation cycle."""
    deltas: dict[str, float] = {
        "anxiety": -0.05,
        "frustration": -0.04,
        "cortisol": -0.035,
        "confusion": -0.03,
        "contentment": 0.04,
        "patience": 0.03,
        "serotonin": 0.03,
        "confidence": 0.015,
    }

    stress_load = (
        max(0.0, _coerce_float(emotional_signal.get("anxiety")))
        + max(0.0, _coerce_float(emotional_signal.get("frustration")))
        + max(0.0, _coerce_float(emotional_signal.get("cortisol")))
        + max(0.0, _coerce_float(emotional_signal.get("confusion")))
        + max(0.0, _coerce_float(emotional_signal.get("loneliness")) * 0.8)
    )
    positive_load = (
        max(0.0, _coerce_float(emotional_signal.get("contentment")))
        + max(0.0, _coerce_float(emotional_signal.get("serotonin")))
        + max(0.0, _coerce_float(emotional_signal.get("affection")))
        + max(0.0, _coerce_float(emotional_signal.get("confidence")))
    )

    deltas["anxiety"] -= _clamp(stress_load * 0.02, 0.0, 0.05)
    deltas["frustration"] -= _clamp(stress_load * 0.018, 0.0, 0.04)
    deltas["cortisol"] -= _clamp(stress_load * 0.015, 0.0, 0.035)
    deltas["contentment"] += _clamp(positive_load * 0.012, 0.0, 0.025)
    deltas["serotonin"] += _clamp(positive_load * 0.01, 0.0, 0.02)

    llm_map = _coerce_delta_map(llm_suggestion)
    for key, value in llm_map.items():
        deltas[key] = deltas.get(key, 0.0) + (value * 0.5)

    return {k: round(_clamp(v, -0.2, 0.2), 4) for k, v in deltas.items()}


def fallback_dream_payload(
    *,
    memories: Iterable[Any],
    emotional_signal: Mapping[str, float],
    trigger: str,
    timestamp: dt.datetime,
) -> dict[str, Any]:
    """Create a deterministic dream artifact when LLM synthesis is unavailable."""
    mem_list = _as_memories(memories)
    top_themes = _extract_theme_terms(mem_list)
    if top_themes:
        theme_text = ", ".join(top_themes[:4])
    else:
        theme_text = "unfinished conversations"

    fragments: list[str] = []
    for mem in mem_list[:3]:
        snippet = str(getattr(mem, "summary", "") or "").strip()
        if snippet:
            fragments.append(snippet[:130])
    if not fragments:
        fragments.append("quiet sensory replay with low external input")
    fragments_text = "; ".join(fragments[:3])

    cleanup = suggested_cleanup_deltas(emotional_signal)
    date_label = timestamp.strftime("%Y-%m-%d %H:%M UTC")
    return {
        "title": f"Dream Cycle {date_label}",
        "narrative": (
            f"Sleep-like replay threaded through {theme_text}. "
            f"Fragments revisited: {fragments_text}. "
            "Emotional intensity was compressed while preserving core lessons."
        ),
        "emotional_processing": [
            "Replayed emotionally heavy traces at lower intensity.",
            "Preserved stable social/bonding memories and reduced rumination weight.",
        ],
        "consolidated_memories": [
            f"Stable pattern from dream trigger `{trigger}` around {theme_text}.",
            "Merged overlapping events into compact recall anchors.",
        ],
        "clutter_release": [
            "Dropped repetitive worry loops with no new information.",
            "De-prioritized stale, low-salience fragments.",
        ],
        "replay_focus": top_themes[:5] or ["relationships", "tasks", "environment"],
        "mood_delta_suggestions": cleanup,
    }


def coerce_dream_payload(
    raw_payload: Any,
    *,
    memories: Iterable[Any],
    emotional_signal: Mapping[str, float],
    trigger: str,
    timestamp: dt.datetime,
) -> dict[str, Any]:
    """Coerce LLM output into a normalized dream payload shape."""
    fallback = fallback_dream_payload(
        memories=memories,
        emotional_signal=emotional_signal,
        trigger=trigger,
        timestamp=timestamp,
    )
    if not isinstance(raw_payload, dict):
        return fallback

    title = str(raw_payload.get("title", "")).strip() or fallback["title"]
    narrative = str(raw_payload.get("narrative", "")).strip() or fallback["narrative"]
    emotional_processing = _coerce_text_list(
        raw_payload.get("emotional_processing"),
        limit=6,
        fallback=fallback["emotional_processing"],
    )
    consolidated_memories = _coerce_text_list(
        raw_payload.get("consolidated_memories"),
        limit=8,
        fallback=fallback["consolidated_memories"],
    )
    clutter_release = _coerce_text_list(
        raw_payload.get("clutter_release"),
        limit=8,
        fallback=fallback["clutter_release"],
    )
    replay_focus = _coerce_text_list(
        raw_payload.get("replay_focus"),
        limit=10,
        fallback=fallback["replay_focus"],
    )
    llm_deltas = _coerce_delta_map(raw_payload.get("mood_delta_suggestions"))
    cleanup = suggested_cleanup_deltas(
        emotional_signal,
        llm_suggestion=llm_deltas,
    )
    return {
        "title": title[:180],
        "narrative": narrative[:1400],
        "emotional_processing": emotional_processing,
        "consolidated_memories": consolidated_memories,
        "clutter_release": clutter_release,
        "replay_focus": replay_focus,
        "mood_delta_suggestions": cleanup,
    }


def render_dream_markdown(entry: Mapping[str, Any]) -> str:
    """Render a dream entry into a readable markdown file."""
    dream = entry.get("dream", {}) if isinstance(entry, Mapping) else {}
    if not isinstance(dream, Mapping):
        dream = {}
    lines = [
        "# Sel Dream Journal",
        "",
        f"timestamp_utc: {entry.get('timestamp_utc', 'unknown')}",
        f"trigger: {entry.get('trigger', 'unknown')}",
        f"memory_count: {entry.get('memory_count', 0)}",
        f"hours_inactive: {entry.get('hours_inactive')}",
        "",
        f"## {dream.get('title', 'Dream')}",
        "",
        str(dream.get("narrative", "")).strip(),
        "",
        "### Emotional Processing",
    ]

    for item in dream.get("emotional_processing", []) or []:
        lines.append(f"- {item}")

    lines.append("")
    lines.append("### Consolidated Memories")
    for item in dream.get("consolidated_memories", []) or []:
        lines.append(f"- {item}")

    lines.append("")
    lines.append("### Cleared Clutter")
    for item in dream.get("clutter_release", []) or []:
        lines.append(f"- {item}")

    lines.append("")
    lines.append("### Replay Focus")
    for item in dream.get("replay_focus", []) or []:
        lines.append(f"- {item}")

    lines.append("")
    lines.append("### Mood Cleanup Deltas")
    deltas = entry.get("cleanup_deltas", {})
    if isinstance(deltas, Mapping):
        for key, value in sorted(deltas.items()):
            lines.append(f"- {key}: {value:+.3f}")

    return "\n".join(lines).strip() + "\n"


def trim_jsonl_file(path: Path, *, max_entries: int) -> None:
    """Keep only the newest N entries in a JSONL file."""
    if max_entries <= 0 or not path.exists():
        return
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) <= max_entries:
        return
    trimmed = lines[-max_entries:]
    path.write_text("\n".join(trimmed) + "\n", encoding="utf-8")


def load_recent_jsonl(path: Path, *, limit: int = 5) -> list[dict[str, Any]]:
    """Load recent JSONL entries without raising on malformed lines."""
    if limit <= 0 or not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    output: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            parsed = json.loads(line)
        except Exception:
            continue
        if isinstance(parsed, dict):
            output.append(parsed)
    return output
