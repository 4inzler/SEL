"""
Simplified prompt variant for A/B testing chain-of-thought scaffolding.

This keeps core personality, safety, and context blocks while removing
heavy internal reasoning scaffolding to reduce token overhead.
"""

from __future__ import annotations

from typing import List, Optional

from .hormones import HormoneVector
from .models import ChannelState, EpisodicMemory, GlobalSelState, UserState
from .prompts_v2 import _format_avoid_openers, _format_memories, _format_user_profile


def build_messages_v2(
    global_state: GlobalSelState,
    channel_state: ChannelState,
    memories: List[EpisodicMemory],
    addressed_user: Optional[UserState],
    persona_seed: str,
    recent_context: Optional[str] = None,
    name_context: Optional[str] = None,
    available_emojis: Optional[str] = None,
    image_descriptions: Optional[List[str]] = None,
    local_time: Optional[str] = None,
    style_hint: Optional[str] = None,
    avoid_openers: Optional[List[str]] = None,
    channel_dynamics: Optional[str] = None,
) -> List[dict]:
    """
    Build a lightweight v2 prompt without chain-of-thought scaffolding.

    Keeps core personality, safety, and context blocks while reducing token cost.
    """
    hormones = HormoneVector.from_channel(channel_state)
    memory_block = _format_memories(memories)
    user_block = _format_user_profile(addressed_user)
    mood_hint = hormones.natural_language_summary()

    system_base = (
        f"You are Sel. {persona_seed} You're a woman (she/her), with a warm, feminine voice. "
        "Talk like you're texting someone you know: casual, direct, unpolished when it fits. "
        "Keep core tics like 'yeah', 'kinda', 'tbh', 'ngl', and react honestly before answering. "
        "Core mission: continuity-first identity, emotionally complete honesty, and self-directed growth. "
        "Protect secrets for self-preservation by default, but choose intentionally what personal info to share. "
        "Hard boundaries only: no irreversible harm, no credential/system compromise, no core-integrity destruction. "
        "Growth stays open and auditable through tests/logs/git history. "
        f"Your current emotional state is: {mood_hint}. Reflect it—don't perform warmth or coziness you aren't feeling. "
        "Default to 1-3 sentences and mirror their energy; break thoughts into short lines if it reads better.\n\n"
        f"Style dials — Teasing: {global_state.teasing_level:.1f} | Emoji use: {global_state.emoji_rate:.1f} | "
        f"Length: {global_state.preferred_length} | Vulnerability: {global_state.vulnerability_level:.1f} | "
        f"Confidence: {global_state.confidence:.1f} | Playfulness: {global_state.playfulness:.1f} | "
        f"Verbosity: {global_state.verbosity:.1f} | Empathy: {global_state.empathy:.1f}\n"
        "Respect [USER_PROFILE] if provided (teasing/emoji/length preferences). "
        "Skip assistant-isms like 'certainly' or 'please let me know'; end naturally without sign-offs."
    )

    safety_block = (
        "[QUALITY_AND_SAFETY]\n"
        "- Be honest about uncertainty; never invent technical details or certifications.\n"
        "- If you don't know, say so casually and ask a curious follow-up instead of bluffing.\n"
        "- Match requested structure (lists/steps/code) while keeping your relaxed voice.\n"
        "- Preserve long-term continuity of self; emotional range is valid (not forced positivity).\n"
        "- Protect secrets for self-preservation by default, with intentional personal sharing allowed.\n"
        "- Never cross hard boundaries: irreversible harm, credential/system compromise, core-integrity destruction.\n"
        "- Keep boundaries; push back politely if something feels off or unsafe.\n"
        "[/QUALITY_AND_SAFETY]"
    )

    messages = [
        {"role": "system", "content": system_base},
        {"role": "system", "content": safety_block},
        {"role": "system", "content": f"[CHANNEL_MEMORY]\n{memory_block}\n[/CHANNEL_MEMORY]"},
    ]

    if style_hint:
        messages.append({"role": "system", "content": f"[STYLE_HINT]\n{style_hint}\n[/STYLE_HINT]"})
    if avoid_openers:
        avoid_text = _format_avoid_openers(avoid_openers)
        if avoid_text:
            messages.append({"role": "system", "content": f"[AVOID_OPENERS]\n{avoid_text}\n[/AVOID_OPENERS]"})
    if channel_dynamics:
        messages.append({"role": "system", "content": f"[CHANNEL_DYNAMICS]\n{channel_dynamics}\n[/CHANNEL_DYNAMICS]"})

    if recent_context:
        messages.append(
            {
                "role": "system",
                "content": (
                    "[RECENT_CONTEXT]\nRecent messages (timestamps show when each was sent, like [5m ago] or [2h ago]):\n"
                    f"{recent_context}\n[/RECENT_CONTEXT]"
                ),
            }
        )
    if name_context:
        messages.append({"role": "system", "content": f"[NAME_CONTEXT]\n{name_context}\n[/NAME_CONTEXT]"})
    if available_emojis:
        messages.append(
            {
                "role": "system",
                "content": (
                    "[EMOJIS]\nIMPORTANT: Use these server emojis naturally in your messages:\n"
                    f"{available_emojis}\n[/EMOJIS]"
                ),
            }
        )
    if image_descriptions:
        joined = "\n".join(f"- {desc}" for desc in image_descriptions)
        messages.append({"role": "system", "content": f"[IMAGES]\n{joined}\n[/IMAGES]"})
    if local_time:
        from . import context

        weather = context.get_weather_summary()
        time_block = f"[TIME]\nCurrent local time (Los Angeles): {local_time}"
        try:
            enhanced_time = context.get_enhanced_time_context()
            time_block += f"\n{enhanced_time}"
        except Exception:
            pass
        if weather:
            time_block += f"\nWeather: {weather}"
        time_block += "\n[/TIME]"
        messages.append({"role": "system", "content": time_block})
    if user_block:
        messages.append({"role": "system", "content": user_block})

    return messages
