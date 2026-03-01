"""
Decision logic for when Sel replies.
"""

from __future__ import annotations

import math
import re
import time
from typing import Mapping, Optional, Sequence

from .hormones import HormoneVector

_GREETING_TARGET_RE = re.compile(
    r"^(hi|hey|hello|yo|sup|hiya|howdy|gm|good morning|good afternoon|good evening)\b[,\s]*@?([a-z0-9_\-]{2,32})",
    flags=re.IGNORECASE,
)

BROADCAST_GREETINGS = {
    "all",
    "everyone",
    "everybody",
    "folks",
    "friends",
    "chat",
    "guys",
    "yall",
    "y'all",
    "there",
}

_WORD_RE = re.compile(r"[a-z0-9_']+")
_SECOND_PERSON_WORDS = {"you", "your", "yours", "yourself", "u", "ur", "ya"}


def _name_token_variants(name: str) -> set[str]:
    parts = re.findall(r"[a-z0-9_]+", (name or "").strip().lower())
    if not parts:
        return set()
    variants = {p for p in parts if len(p) >= 2}
    if len(parts) >= 2:
        joined = "".join(parts)
        if len(joined) >= 3:
            variants.add(joined)
    return variants


def score_addressee_intent(
    content: str,
    bot_name: str,
    *,
    is_reply_to_sel: bool,
    is_reply_to_other: bool,
    is_mentioned_sel: bool,
    mentioned_other_names: Sequence[str] | None = None,
    recent_other_names: Sequence[str] | None = None,
    recent_speaker_counts: Mapping[str, int] | None = None,
    recent_sel_messages: int = 0,
    recent_author_messages: int = 0,
    greeting_target: Optional[str] = None,
    force_addressed: bool = False,
) -> dict[str, object]:
    """
    Score whether a message is addressed to Sel vs another person.

    Uses token-level cues ("each word"), explicit Discord metadata, and recent
    conversation context to produce robust routing decisions.
    """
    lowered = (content or "").strip().lower()
    tokens = _WORD_RE.findall(lowered)
    token_set = set(tokens)

    bot_variants = _name_token_variants(bot_name)
    name_called = bool(bot_variants.intersection(token_set))
    direct_question_to_sel = is_direct_question_to_sel(content, bot_name)
    if "?" in lowered and (is_reply_to_sel or is_mentioned_sel or force_addressed):
        direct_question_to_sel = True

    second_person_hits = sum(1 for t in tokens if t in _SECOND_PERSON_WORDS)

    sel_score = 0.0
    other_score = 0.0
    sel_reasons: list[str] = []
    other_reasons: list[str] = []

    if force_addressed:
        sel_score += 5.0
        sel_reasons.append("force_addressed")
    if is_mentioned_sel:
        sel_score += 3.8
        sel_reasons.append("mention_sel")
    if is_reply_to_sel:
        sel_score += 3.0
        sel_reasons.append("reply_to_sel")
    if name_called:
        sel_score += 2.0
        sel_reasons.append("name_called")
    if direct_question_to_sel:
        sel_score += 1.8
        sel_reasons.append("direct_question_to_sel")

    if second_person_hits:
        if is_reply_to_sel or is_mentioned_sel or name_called:
            sel_score += min(1.2, 0.25 + (second_person_hits * 0.3))
            sel_reasons.append("second_person_with_sel_cue")
        elif not is_reply_to_other:
            sel_score += min(0.5, second_person_hits * 0.18)
            sel_reasons.append("second_person_weak_sel_hint")

    if is_reply_to_other:
        # Direct replies to another user should strongly suppress Sel's takeover.
        other_score += 3.6
        sel_score -= 0.8
        other_reasons.append("reply_to_other")

    mention_names = [n for n in (mentioned_other_names or []) if n]
    if mention_names:
        other_score += 1.4 + min(1.2, 0.35 * len(mention_names))
        other_reasons.append("mentions_other_users")

    greeting = (greeting_target or "").strip().lower()
    if greeting:
        if greeting in bot_variants:
            sel_score += 1.2
            sel_reasons.append("greeting_to_sel")
        elif not is_broadcast_greeting_target(greeting):
            other_score += 1.5
            other_reasons.append("greeting_to_other")

    other_name_variants: set[str] = set()
    for name in mention_names:
        other_name_variants.update(_name_token_variants(name))
    for name in (recent_other_names or []):
        other_name_variants.update(_name_token_variants(name))
    other_name_variants -= bot_variants
    other_name_hits = token_set.intersection(other_name_variants)
    if other_name_hits:
        other_score += min(1.8, 0.45 * len(other_name_hits))
        other_reasons.append("other_name_tokens")

    if second_person_hits and other_score > 0 and not (is_mentioned_sel or is_reply_to_sel or name_called):
        other_score += min(0.6, second_person_hits * 0.2)
        other_reasons.append("second_person_with_other_cues")

    if recent_sel_messages > 0 and recent_author_messages > 0 and not is_reply_to_other:
        exchange_strength = min(recent_sel_messages, recent_author_messages)
        if exchange_strength > 0:
            sel_score += min(1.0, exchange_strength * 0.25)
            sel_reasons.append("recent_sel_exchange")

    active_human_speakers = 0
    if recent_speaker_counts:
        active_human_speakers = sum(1 for _, count in recent_speaker_counts.items() if int(count) > 0)
    if active_human_speakers >= 2 and not (is_reply_to_sel or is_mentioned_sel or name_called):
        sel_score -= 0.4
        other_score += 0.5
        other_reasons.append("active_multi_user_context")

    sel_threshold = 2.4 if active_human_speakers >= 2 else 1.8
    other_threshold = 1.9
    addressed_to_sel = (sel_score >= sel_threshold) and (sel_score >= (other_score + 0.35))
    addressed_to_other = (other_score >= other_threshold) and (other_score > (sel_score + 0.15))

    if force_addressed or is_mentioned_sel or is_reply_to_sel:
        addressed_to_sel = True
        addressed_to_other = False
    elif is_reply_to_other and (name_called or direct_question_to_sel):
        # Calling Sel by name (or asking a direct question) while replying to
        # someone else still routes to Sel — no question mark required.
        addressed_to_sel = True
        addressed_to_other = False
    elif is_reply_to_other and not (name_called or direct_question_to_sel):
        addressed_to_sel = False
        addressed_to_other = True
    elif addressed_to_sel:
        addressed_to_other = False

    continuation_hint = (
        not addressed_to_other
        and (
            addressed_to_sel
            or is_reply_to_sel
            or (
                recent_sel_messages > 0
                and recent_author_messages > 0
                and (
                    sel_score >= 1.0
                    or second_person_hits > 0
                    or "said" in token_set
                    or "earlier" in token_set
                )
            )
        )
    )

    return {
        "addressed_to_sel": addressed_to_sel,
        "addressed_to_other": addressed_to_other,
        "direct_question_to_sel": direct_question_to_sel,
        "name_called": name_called,
        "continuation_hint": continuation_hint,
        "sel_score": round(sel_score, 3),
        "other_score": round(other_score, 3),
        "sel_reasons": sel_reasons,
        "other_reasons": other_reasons,
    }


def engagement_pressure_from_hormones(
    hormones: HormoneVector,
    *,
    is_continuation: bool = False,
    replying_to_other: bool = False,
) -> float:
    """
    Deterministic hormone pressure for engagement decisions.

    Positive values mean "more likely to engage", negative values mean "more likely to stay quiet".
    """
    engage_drive = (
        hormones.dopamine * 0.32
        + hormones.oxytocin * 0.18
        + hormones.serotonin * 0.10
        + hormones.novelty * 0.16
        + hormones.curiosity * 0.28
        + hormones.endorphin * 0.12
        + hormones.excitement * 0.12
        + hormones.affection * 0.12
        + hormones.confidence * 0.08
        + hormones.estrogen * 0.08
        + hormones.testosterone * 0.06
        + hormones.anticipation * 0.06
    )
    disengage_drag = (
        max(0.0, hormones.cortisol) * 0.34
        + max(0.0, hormones.melatonin) * 0.30
        + max(0.0, hormones.anxiety) * 0.22
        + max(0.0, hormones.frustration) * 0.14
        + max(0.0, hormones.boredom) * 0.08
        + max(0.0, hormones.confusion) * 0.08
        + max(0.0, hormones.progesterone) * 0.06
        + max(0.0, hormones.patience) * 0.08
    )
    pressure = engage_drive - disengage_drag
    if is_continuation:
        pressure += 0.08
    if replying_to_other:
        pressure -= 0.22
    return max(-1.0, min(1.0, pressure))


def should_respond(
    is_mentioned: bool,
    direct_question: bool,
    hormones: HormoneVector,
    base_chance: float,
    messages_since_response: int,
    seconds_since_response: Optional[float],
    has_image: bool = False,
    is_continuation: bool = False,
) -> bool:
    """
    Sel always responds to mentions or direct questions.
    Otherwise we roll a chance influenced by mood and context:
    - Higher dopamine/oxytocin increases chance.
    - High cortisol/melatonin reduces chance.
    - Conversation momentum: much more likely to respond when in active conversation.
    - Continuations, images, and backlog nudges push Sel to re-engage.
    - No randomness or time-based modulation is used.
    """

    if is_mentioned or direct_question:
        return True

    # Conversation momentum: only boost if this is a continuation (reply/followup to SEL)
    # Much more conservative - don't jump into conversations not about SEL
    conversation_active = seconds_since_response is not None and seconds_since_response < 30
    momentum_boost = 0.0

    # Only apply momentum if it's actually a continuation of SEL's conversation
    if is_continuation and conversation_active:
        momentum_boost = 0.15  # Reduced from 0.35
        # Slightly higher if very recent (within 10 seconds)
        if seconds_since_response is not None and seconds_since_response < 10:
            momentum_boost = 0.22  # Reduced from 0.55

    continuation_boost = 0.12 if is_continuation else 0.0  # Reduced from 0.18
    image_boost = 0.08 if has_image else 0.0  # Reduced from 0.12
    backlog = max(0, messages_since_response)
    backlog_boost = min(0.12, backlog * 0.025)  # Reduced from 0.2 and 0.04

    mood_bonus = max(
        0.0,
        (hormones.dopamine * 0.6)
        + (hormones.oxytocin * 0.4)
        + (hormones.serotonin * 0.2)
        + (hormones.curiosity * 0.5)
        + (hormones.patience * 0.3)
        + (hormones.estrogen * 0.5)
        + (hormones.testosterone * 0.3)
        + (hormones.adrenaline * 0.25)
        + (hormones.endorphin * 0.45)
        + (hormones.progesterone * 0.25),
    ) * 0.12
    mood_penalty = max(
        0.0,
        (hormones.cortisol * 0.7)
        + (hormones.melatonin * 0.4)
        + (max(0.0, -hormones.patience) * 0.4)
        + (hormones.adrenaline * 0.35)
        + (max(0.0, -hormones.estrogen) * 0.25)
        + (max(0.0, -hormones.testosterone) * 0.2)
        + (max(0.0, -hormones.progesterone) * 0.1),
    ) * 0.12

    chance = max(
        0.02,
        base_chance + mood_bonus - mood_penalty + momentum_boost + continuation_boost + image_boost + backlog_boost,
    )
    # Mood-adaptive floor purely from hormones
    chance += hormones.novelty * 0.06
    chance += hormones.curiosity * 0.05
    chance += hormones.patience * 0.02
    chance += hormones.estrogen * 0.04
    chance += hormones.testosterone * 0.03
    chance += hormones.adrenaline * 0.05
    chance += hormones.endorphin * 0.06
    chance += hormones.progesterone * 0.03
    chance -= max(0.0, hormones.melatonin) * 0.06
    chance -= max(0.0, hormones.cortisol) * 0.06
    chance = max(0.0, min(0.98, chance))

    engagement_score = chance
    # Higher threshold - SEL is more reserved about jumping into conversations
    # Only lower threshold if this is actually a continuation of SEL's conversation
    base_threshold = 0.45 if (conversation_active and is_continuation) else 0.65
    threshold = (
        base_threshold
        - (0.06 if is_continuation else 0.0)  # Reduced from 0.08
        - (0.03 if has_image else 0.0)  # Reduced from 0.04
        - min(0.06, backlog * 0.008)  # Reduced from 0.08 and 0.01
        - (hormones.curiosity * 0.04)  # Reduced from 0.05
        + (hormones.patience * 0.06)  # Increased (more patience = less likely to butt in)
        + (hormones.cortisol * 0.05)
        - (hormones.estrogen * 0.02)  # Reduced from 0.03
        + (hormones.adrenaline * 0.04)
        - (hormones.endorphin * 0.04)  # Reduced from 0.05
        - (hormones.progesterone * 0.02)
    )
    return engagement_score >= threshold


def is_direct_question_to_sel(content: str, bot_name: str) -> bool:
    lowered = content.lower()
    if "?" not in lowered:
        return False
    name = bot_name.strip().lower()
    if not name:
        return False
    pattern = rf"\b{re.escape(name)}\b"
    return re.search(pattern, lowered) is not None


def extract_greeting_target(content: str) -> Optional[str]:
    """Return the greeting target token if message starts with a direct greeting."""
    if not content:
        return None
    lowered = content.strip().lower()
    match = _GREETING_TARGET_RE.match(lowered)
    if not match:
        return None
    target = match.group(2).strip(".,!?:;")
    return target or None


def is_broadcast_greeting_target(target: str) -> bool:
    if not target:
        return False
    return target.lower() in BROADCAST_GREETINGS
