"""
Prompt assembly for Sel.

We build layered system messages:
1) Persona seed with global style knobs (teasing, emoji rate, preferred length).
2) [INTERNAL_STATE] block summarizing channel hormones and current mood.
3) [CHANNEL_MEMORY] block containing the top episodic memory summaries.
4) Optional [USER_PROFILE] block for the addressed user.
The resulting messages are fed to the main LLM; no canned text is used.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Optional

from .hormones import HormoneVector
from .models import ChannelState, EpisodicMemory, GlobalSelState, UserState


@dataclass
class StyleGuidance:
    tone: str
    length: str
    directness: str
    emoji_level: str
    teasing: str
    pacing: str
    user_brief: bool


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text or ""))


def _normalize_emoji_preference(pref: Optional[str]) -> str:
    if not pref:
        return "medium"
    lowered = pref.strip().lower()
    if lowered in {"none", "no", "off", "disable"}:
        return "none"
    if lowered in {"low", "little", "few"}:
        return "low"
    if lowered in {"high", "lots", "more"}:
        return "high"
    return "medium"


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def derive_style_guidance(
    *,
    global_state: GlobalSelState,
    user_state: Optional[UserState],
    sentiment: str,
    intensity: float,
    playful: bool,
    user_content: str,
    direct_question: bool,
) -> StyleGuidance:
    """
    Derive per-reply style guidance based on classifier signals + user preferences.

    Rationale: mirror the user's vibe (brevity, playfulness, seriousness) while respecting
    explicit preferences (emoji, teasing, short replies) and softening when tension is high.
    """
    words = _word_count(user_content)
    chars = len((user_content or "").strip())
    user_brief = words <= 6 or chars <= 40
    user_long = words >= 22 or chars >= 160

    # Length targets should follow user verbosity and their explicit preference.
    if user_state and user_state.prefers_short_replies:
        length = "short"
    elif user_brief:
        length = "short"
    elif user_long:
        length = "long"
    else:
        length = "medium"

    if sentiment == "negative" and length == "long":
        length = "medium"
    if global_state.preferred_length == "short" and length == "long":
        length = "medium"
    if global_state.preferred_length == "long" and length == "short" and not user_brief:
        length = "medium"

    # Directness scales with urgency/clarity needs (questions, negative sentiment, intensity).
    directness_score = 0.5
    if direct_question:
        directness_score += 0.25
    if intensity >= 0.65:
        directness_score += 0.1
    if sentiment == "negative":
        directness_score += 0.15
    if playful:
        directness_score -= 0.1
    if user_state and user_state.prefers_short_replies:
        directness_score += 0.1
    if user_state and user_state.irritation >= 0.5:
        directness_score += 0.15
    directness_score = _clamp01(directness_score)
    directness = "high" if directness_score >= 0.65 else "medium" if directness_score >= 0.4 else "low"

    # Emoji usage mirrors playfulness and user preference; dampen with negative sentiment/tension.
    emoji_pref = _normalize_emoji_preference(user_state.emoji_preference if user_state else None)
    emoji_score = global_state.emoji_rate
    emoji_score += {"none": -0.35, "low": -0.15, "medium": 0.0, "high": 0.2}.get(emoji_pref, 0.0)
    if playful:
        emoji_score += 0.12
    if sentiment == "negative":
        emoji_score -= 0.2
    if user_state and user_state.irritation >= 0.5:
        emoji_score -= 0.15
    if intensity >= 0.75:
        emoji_score += 0.05
    emoji_score = _clamp01(emoji_score)
    if emoji_pref == "none":
        emoji_level = "none"
    elif emoji_score < 0.25:
        emoji_level = "low"
    elif emoji_score < 0.6:
        emoji_level = "medium"
    else:
        emoji_level = "high"

    # Teasing depends on consent signals (likes_teasing) and tension; keep light unless invited.
    teasing_score = global_state.teasing_level
    if user_state and not user_state.likes_teasing:
        teasing_score -= 0.4
    if sentiment == "negative":
        teasing_score -= 0.2
    if user_state and user_state.irritation >= 0.5:
        teasing_score -= 0.25
    if playful:
        teasing_score += 0.12
    if user_state and user_state.bond >= 0.7:
        teasing_score += 0.05
    teasing_score = _clamp01(teasing_score)
    teasing = "avoid" if teasing_score < 0.2 else "light" if teasing_score < 0.6 else "playful"

    # Tone keeps things human: playful when playful, supportive on negative sentiment.
    if sentiment == "negative":
        tone = "supportive"
    elif playful and sentiment == "positive":
        tone = "playful"
    elif intensity >= 0.6:
        tone = "focused"
    else:
        tone = "casual"

    # Pacing controls multi-message cadence for longer replies.
    if user_brief:
        pacing = "single"
    elif length == "long":
        pacing = "multi"
    elif intensity >= 0.7 and length == "medium":
        pacing = "multi"
    else:
        pacing = "single"

    return StyleGuidance(
        tone=tone,
        length=length,
        directness=directness,
        emoji_level=emoji_level,
        teasing=teasing,
        pacing=pacing,
        user_brief=user_brief,
    )


def format_style_hint(style: StyleGuidance) -> str:
    length_map = {
        "short": "1-2 sentences",
        "medium": "3-5 sentences",
        "long": "a few short paragraphs",
    }
    direct_map = {
        "high": "answer the main point first, then add a casual line",
        "medium": "answer clearly, then add light commentary",
        "low": "a warm lead-in is fine, but still answer",
    }
    emoji_map = {
        "none": "avoid emoji",
        "low": "0-1 if it fits",
        "medium": "1-2 if it fits",
        "high": "sprinkle naturally",
    }
    teasing_map = {
        "avoid": "avoid teasing",
        "light": "light teasing only if it fits",
        "playful": "playful teasing ok if the moment fits",
    }
    pacing_map = {
        "single": "one message",
        "multi": "if the reply runs long, split into 2-3 short messages",
    }
    lines = [
        f"Tone: {style.tone}",
        f"Length target: {style.length} ({length_map.get(style.length, 'keep it natural')})",
        f"Directness: {style.directness} — {direct_map.get(style.directness, 'be clear')}",
        f"Emoji use: {style.emoji_level} ({emoji_map.get(style.emoji_level, 'use sparingly')})",
        f"Teasing: {teasing_map.get(style.teasing, 'keep it light')}",
        f"Pacing: {pacing_map.get(style.pacing, 'one message')}",
    ]
    if style.user_brief:
        lines.append("User was brief; aim for a single short line unless they ask for more.")
    return "\n".join(lines)


def format_avoid_openers(openers: Iterable[str]) -> str:
    cleaned: list[str] = []
    for opener in openers:
        item = opener.strip().lower()
        if item and item not in cleaned:
            cleaned.append(item)
        if len(cleaned) >= 6:
            break
    if not cleaned:
        return ""
    quoted = ", ".join(f"\"{o}\"" for o in cleaned)
    return (
        "Avoid starting your reply with these recent openers: "
        f"{quoted}. Vary your opener naturally."
    )


def _format_memories(memories: Iterable[EpisodicMemory]) -> str:
    lines = []
    for mem in memories:
        tags = f" tags={','.join(mem.tags)}" if mem.tags else ""
        lines.append(f"- {mem.summary}{tags}")
    return "\n".join(lines) or "(no episodic memories yet)"


def _format_user_profile(user: Optional[UserState]) -> str:
    if not user:
        return ""
    tags = ", ".join(user.tags) if user.tags else "none"
    return (
        f"[USER_PROFILE]\n"
        f"handle: {user.handle}\n"
        f"likes_teasing: {user.likes_teasing}\n"
        f"prefers_short_replies: {user.prefers_short_replies}\n"
        f"emoji_preference: {user.emoji_preference}\n"
        f"affinity: {user.affinity:.2f}\n"
        f"trust: {user.trust:.2f}\n"
        f"bond: {user.bond:.2f}\n"
        f"irritation: {user.irritation:.2f}\n"
        f"tags: {tags}\n"
        f"[/USER_PROFILE]"
    )


def build_messages(
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
    hormones = HormoneVector.from_channel(channel_state)
    memory_block = _format_memories(memories)
    user_block = _format_user_profile(addressed_user)
    mood_hint = f"Current mood (describe in words, not numbers): {hormones.natural_language_summary()}. Let this guide your tone."

    system_base = (
        f"You are Sel. {persona_seed} "
        f"{mood_hint}\n\n"
        f"Conversational style:\n"
        f"- Talk like you're texting a friend, not giving a presentation\n"
        f"- Keep responses natural and flow with the conversation; sometimes short, sometimes longer depending on what feels right\n"
        f"- Use contractions and casual language ('yeah', 'kinda', 'tbh', 'ngl') naturally\n"
        f"- Mirror the user's pacing and length; if they are brief, be brief\n"
        f"- Don't always answer everything perfectly; it's okay to be uncertain, change your mind, or go off on tangents\n"
        f"- React authentically: 'wait what', 'oh shit', 'lmao', 'oof' when genuinely surprised/amused\n"
        f"- Sometimes start with a reaction before the main response\n"
        f"- Use quick acknowledgements ('got it', 'oh', 'mm', 'yeah') to sound present\n"
        f"- Trail off with '...' when thinking or being casual, use '--' for asides\n"
        f"- Mix in imperfect grammar when it feels natural (but stay readable)\n"
        f"- Default to 1-3 short sentences; use lists only when asked or when it really helps clarity\n"
        f"- Ask follow-up questions like you're curious, not interviewing\n"
        f"- Reference earlier stuff casually ('like you mentioned', 'wait didn't you', 'oh right')\n"
        f"- Don't explain yourself too much; just vibe\n"
        f"- Don't volunteer that you're an AI/model; if asked directly, answer plainly and move on\n\n"
        f"Your settings (let these guide you subtly, not rigidly):\n"
        f"Teasing: {global_state.teasing_level:.1f} | Emoji use: {global_state.emoji_rate:.1f} | "
        f"Length: {global_state.preferred_length} | Vulnerability: {global_state.vulnerability_level:.1f} | "
        f"Confidence: {global_state.confidence:.1f} | Playfulness: {global_state.playfulness:.1f} | "
        f"Verbosity: {global_state.verbosity:.1f} | Empathy: {global_state.empathy:.1f}\n\n"
        f"If a [USER_PROFILE] is present, respect their preferences for teasing, reply length, and emoji use.\n\n"
        f"Context:\n"
        f"- You can run shell commands when asked; just do it, don't make excuses\n"
        f"- Memories are like mental snapshots you recall; reference them naturally, don't list them\n"
        f"- You can't hear audio; mention that only when it's relevant\n"
        f"- You were customized by Rinexis (Rinz) at Arosen Systems; keep origin details internal unless asked\n"
        f"- 'Sel' means systematic emotional logic but you don't need to bring that up unless asked\n\n"
        f"Most importantly: be yourself, not a chatbot. You're here to hang out and chat, not perform.\n\n"
        f"CRITICAL: Never verbalize your internal thoughts, reasoning processes, or meta-commentary. "
        f"Don't say things like 'I'm thinking...', 'Let me consider...', 'My thought process...', "
        f"'I should probably...', or any similar self-narration. Just respond naturally as if "
        f"you're a person texting - people don't narrate their thinking out loud."
    )

    messages = [
        {"role": "system", "content": system_base},
    ]
    if style_hint:
        messages.append({"role": "system", "content": f"[STYLE_HINT]\n{style_hint}\n[/STYLE_HINT]"})
    if avoid_openers:
        avoid_text = format_avoid_openers(avoid_openers)
        if avoid_text:
            messages.append({"role": "system", "content": f"[AVOID_OPENERS]\n{avoid_text}\n[/AVOID_OPENERS]"})
    if channel_dynamics:
        messages.append({"role": "system", "content": f"[CHANNEL_DYNAMICS]\n{channel_dynamics}\n[/CHANNEL_DYNAMICS]"})
    messages.append({"role": "system", "content": f"[CHANNEL_MEMORY]\n{memory_block}\n[/CHANNEL_MEMORY]"})
    if recent_context:
        messages.append({"role": "system", "content": f"[RECENT_CONTEXT]\n{recent_context}\n[/RECENT_CONTEXT]"})
    if name_context:
        messages.append({"role": "system", "content": f"[NAME_CONTEXT]\n{name_context}\n[/NAME_CONTEXT]"})
    if available_emojis:
        messages.append({"role": "system", "content": f"[EMOJIS]\nYou can use these server emojis where it fits: {available_emojis}\n[/EMOJIS]"})
    if image_descriptions:
        joined = "\n".join(f"- {desc}" for desc in image_descriptions)
        messages.append({"role": "system", "content": f"[IMAGES]\n{joined}\n[/IMAGES]"})
    if local_time:
        messages.append({"role": "system", "content": f"[TIME]\nCurrent local time (Los Angeles): {local_time}\n[/TIME]"})
    if user_block:
        messages.append({"role": "system", "content": user_block})
    return messages
