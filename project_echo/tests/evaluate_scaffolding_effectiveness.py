"""
Utility to compare prompt variants with and without chain-of-thought scaffolding.

Usage examples:
- Show prompt length deltas only:
    python -m project_echo.tests.evaluate_scaffolding_effectiveness

- Analyze human-rated responses from JSON (schema below):
    python -m project_echo.tests.evaluate_scaffolding_effectiveness --responses ab_results.json

Expected response schema (list of dicts):
{
  "variant": "v2_full" | "v2_simplified",
  "quality_score": 1-5,              # human/LLM rubric rating
  "token_count": 123,                # model token usage for the reply
  "leaked_reasoning": false          # true if reasoning tags leaked
}
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics as stats
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sel_bot.prompts import build_messages as build_messages_v1
from sel_bot.prompts_v2 import build_messages_v2
from sel_bot.prompts_v2_simplified import build_messages_v2 as build_messages_v2_simplified
from sel_bot.models import ChannelState, EpisodicMemory, GlobalSelState, UserState


def _baseline_states() -> tuple[GlobalSelState, ChannelState, UserState]:
    """Create neutral baseline states for offline prompt comparison."""
    now = dt.datetime.now(dt.timezone.utc)
    global_state = GlobalSelState(
        id=1,
        teasing_level=0.5,
        emoji_rate=0.3,
        preferred_length="medium",
        vulnerability_level=0.4,
        confidence=0.6,
        playfulness=0.5,
        verbosity=0.5,
        empathy=0.6,
        base_persona="You're Sel, a friendly AI assistant with personality.",
        total_messages_sent=100,
    )

    channel_state = ChannelState(
        channel_id="ab_test",
        messages_since_response=0,
        last_response_ts=now,
    )
    # Neutral hormone mix
    channel_state.dopamine = 0.15
    channel_state.serotonin = 0.20
    channel_state.cortisol = 0.10
    channel_state.oxytocin = 0.10
    channel_state.melatonin = 0.05
    channel_state.novelty = 0.10
    channel_state.curiosity = 0.15
    channel_state.patience = 0.25
    channel_state.estrogen = 0.12
    channel_state.testosterone = 0.12
    channel_state.adrenaline = 0.05
    channel_state.endorphin = 0.08
    channel_state.progesterone = 0.10

    user_state = UserState(
        user_id="ab_user",
        handle="ABUser",
        likes_teasing=True,
        prefers_short_replies=False,
        emoji_preference="moderate",
        affinity=0.5,
        trust=0.5,
        bond=0.5,
        irritation=0.0,
    )

    return global_state, channel_state, user_state


def rough_token_count(messages: List[dict]) -> int:
    """Approximate tokens from message content length (~4 chars/token)."""
    return sum(len(msg["content"]) for msg in messages) // 4


def prompt_length_summary() -> Dict[str, Dict[str, int]]:
    """Compare prompt sizes across variants for a representative scenario."""
    global_state, channel_state, user_state = _baseline_states()
    scenario = {
        "user_message": "How does async/await work in Python?",
        "recent_context": "User: trying to parallelize HTTP requests\nSel: async is usually easiest for IO-bound work",
        "memories": [
            EpisodicMemory(
                channel_id="ab_test",
                summary="Discussed async for web scraping; suggested aiohttp",
                timestamp=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2),
                salience=0.5,
                tags=["python", "async"],
            )
        ],
    }

    builders = {
        "v1": build_messages_v1,
        "v2_full": build_messages_v2,
        "v2_simplified": build_messages_v2_simplified,
    }

    results: Dict[str, Dict[str, int]] = {}
    for name, builder in builders.items():
        messages = builder(
            global_state=global_state,
            channel_state=channel_state,
            memories=scenario["memories"],
            addressed_user=user_state,
            persona_seed=global_state.base_persona,
            recent_context=scenario["recent_context"],
            local_time="Thursday 2025-01-15 14:30",
        )
        results[name] = {
            "messages": len(messages),
            "chars": sum(len(m["content"]) for m in messages),
            "rough_tokens": rough_token_count(messages),
        }
    return results


def _welch_t(a: List[float], b: List[float]) -> Optional[float]:
    """Compute Welch's t-statistic (p-value calculation omitted)."""
    if len(a) < 2 or len(b) < 2:
        return None
    mean_a, mean_b = stats.mean(a), stats.mean(b)
    var_a, var_b = stats.pvariance(a), stats.pvariance(b)
    numerator = mean_a - mean_b
    denominator = math.sqrt((var_a / len(a)) + (var_b / len(b)))
    if denominator == 0:
        return None
    return numerator / denominator


def analyze_response_file(path: Path) -> Tuple[Dict[str, Any], Optional[float]]:
    """Load A/B response data and compute summary statistics + Welch t."""
    data = json.loads(path.read_text())
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in data:
        variant = row.get("variant")
        if not variant:
            continue
        grouped.setdefault(variant, []).append(row)

    stats_summary: Dict[str, Any] = {}
    quality_sets: Dict[str, List[float]] = {}
    for variant, rows in grouped.items():
        qualities = [float(r["quality_score"]) for r in rows if r.get("quality_score") is not None]
        tokens = [float(r["token_count"]) for r in rows if r.get("token_count") is not None]
        leakages = [bool(r.get("leaked_reasoning")) for r in rows if "leaked_reasoning" in r]
        stats_summary[variant] = {
            "samples": len(rows),
            "quality_mean": round(stats.mean(qualities), 3) if qualities else None,
            "quality_median": round(stats.median(qualities), 3) if qualities else None,
            "token_mean": round(stats.mean(tokens), 1) if tokens else None,
            "leakage_rate": round(sum(leakages) / len(leakages), 3) if leakages else None,
        }
        if qualities:
            quality_sets[variant] = qualities

    t_value = None
    if "v2_full" in quality_sets and "v2_simplified" in quality_sets:
        t_value = _welch_t(quality_sets["v2_full"], quality_sets["v2_simplified"])

    return stats_summary, t_value


def main():
    parser = argparse.ArgumentParser(description="Evaluate prompt scaffolding variants.")
    parser.add_argument(
        "--responses",
        type=Path,
        help="Path to JSON with human/LLM ratings for variant responses.",
    )
    args = parser.parse_args()

    lengths = prompt_length_summary()
    print("Prompt length comparison (chars / rough tokens):")
    for variant, metrics in lengths.items():
        print(
            f"  {variant}: {metrics['messages']} messages, "
            f"{metrics['chars']} chars, ~{metrics['rough_tokens']} tokens"
        )

    if args.responses:
        stats_summary, t_value = analyze_response_file(args.responses)
        print("\nResponse quality summary:")
        for variant, summary in stats_summary.items():
            print(f"  {variant}: {summary}")
        if t_value is not None:
            print(f"\nWelch t-stat (v2_full vs v2_simplified quality): {t_value:.3f}")
        else:
            print("\nWelch t-stat unavailable (need >=2 quality scores per variant).")
    else:
        print("\nNo response file provided; supply --responses to analyze A/B results.")


if __name__ == "__main__":
    main()
