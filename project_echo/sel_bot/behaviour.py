"""
Decision logic for when Sel replies.
"""

from __future__ import annotations

import math
import re
import time
from typing import Optional

from .hormones import HormoneVector


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
