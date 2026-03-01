from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

from sel_bot.dreaming import (
    aggregate_emotional_signal,
    coerce_dream_payload,
    load_recent_jsonl,
    render_dream_markdown,
    trim_jsonl_file,
)


def _mem(summary: str, salience: float = 0.5) -> SimpleNamespace:
    return SimpleNamespace(summary=summary, salience=salience)


def test_aggregate_emotional_signal_weights_memory_salience() -> None:
    memories = [
        _mem("happy fun love", 1.0),
        _mem("sad and lost", 0.5),
    ]
    signal = aggregate_emotional_signal(memories, limit=10)

    assert signal["serotonin"] == 0.02
    assert signal["dopamine"] == 0.02
    assert signal["contentment"] == 0.02
    assert signal["cortisol"] == 0.01
    assert signal["anxiety"] == 0.005


def test_coerce_dream_payload_uses_fallback_when_missing() -> None:
    now = dt.datetime(2026, 2, 27, tzinfo=dt.timezone.utc)
    payload = coerce_dream_payload(
        None,
        memories=[_mem("happy memory from chat", 0.8)],
        emotional_signal={"serotonin": 0.04},
        trigger="scheduled",
        timestamp=now,
    )

    assert payload["title"].startswith("Dream Cycle")
    assert payload["narrative"]
    assert payload["consolidated_memories"]
    assert payload["clutter_release"]
    assert payload["replay_focus"]
    assert payload["mood_delta_suggestions"]["anxiety"] < 0


def test_coerce_dream_payload_merges_llm_cleanup_suggestions() -> None:
    now = dt.datetime(2026, 2, 27, tzinfo=dt.timezone.utc)
    payload = coerce_dream_payload(
        {
            "title": "Night replay",
            "narrative": "Revisited key memories and reduced rumination.",
            "emotional_processing": ["Lowered stress response."],
            "consolidated_memories": ["Keep the durable signal."],
            "clutter_release": ["Drop repetitive loops."],
            "replay_focus": ["tasks", "relationships"],
            "mood_delta_suggestions": {"anxiety": -0.08, "contentment": 0.06},
        },
        memories=[_mem("sad worried memory", 0.7)],
        emotional_signal={"anxiety": 0.2, "frustration": 0.15},
        trigger="manual",
        timestamp=now,
    )

    assert payload["title"] == "Night replay"
    assert payload["emotional_processing"] == ["Lowered stress response."]
    assert payload["consolidated_memories"] == ["Keep the durable signal."]
    assert payload["mood_delta_suggestions"]["anxiety"] < -0.05
    assert payload["mood_delta_suggestions"]["contentment"] > 0


def test_trim_and_load_recent_jsonl(tmp_path: Path) -> None:
    journal = tmp_path / "dream_journal.jsonl"
    with journal.open("w", encoding="utf-8") as handle:
        for idx in range(5):
            handle.write(json.dumps({"idx": idx}) + "\n")

    trim_jsonl_file(journal, max_entries=3)
    recent = load_recent_jsonl(journal, limit=2)

    assert len(recent) == 2
    assert recent[0]["idx"] == 3
    assert recent[1]["idx"] == 4


def test_render_dream_markdown_contains_sections() -> None:
    entry = {
        "timestamp_utc": "2026-02-27T00:00:00+00:00",
        "trigger": "scheduled",
        "memory_count": 4,
        "hours_inactive": 5.5,
        "cleanup_deltas": {"anxiety": -0.05, "contentment": 0.04},
        "dream": {
            "title": "Dream Cycle",
            "narrative": "Consolidated traces.",
            "emotional_processing": ["Processed stress."],
            "consolidated_memories": ["Kept important memory."],
            "clutter_release": ["Removed repetitive loop."],
            "replay_focus": ["memory", "emotion"],
        },
    }

    rendered = render_dream_markdown(entry)

    assert "# Sel Dream Journal" in rendered
    assert "### Emotional Processing" in rendered
    assert "### Consolidated Memories" in rendered
    assert "### Cleared Clutter" in rendered
    assert "### Replay Focus" in rendered
    assert "### Mood Cleanup Deltas" in rendered
