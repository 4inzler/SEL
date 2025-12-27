"""
Feedback processing for Sel.
"""

from __future__ import annotations

from .models import FeedbackEvent, GlobalSelState, SelfTuningEvent, UserState
from .state_manager import StateManager


async def apply_feedback(
    state_manager: StateManager,
    global_state: GlobalSelState,
    user_state: UserState | None,
    feedback: FeedbackEvent,
) -> None:
    """
    Update global and user preferences based on feedback sentiment.
    """

    changes: dict[str, dict[str, float]] = {}
    if feedback.sentiment == "positive":
        old_teasing = global_state.teasing_level
        old_emoji = global_state.emoji_rate
        global_state.teasing_level = min(1.0, global_state.teasing_level + 0.01)
        global_state.emoji_rate = min(1.0, global_state.emoji_rate + 0.01)
        global_state.positive_reactions_count += 1
        changes["teasing_level"] = {"from": old_teasing, "to": global_state.teasing_level}
        changes["emoji_rate"] = {"from": old_emoji, "to": global_state.emoji_rate}
        if user_state:
            user_state.affinity = min(1.0, user_state.affinity + 0.02)
    elif feedback.sentiment == "negative":
        old_teasing = global_state.teasing_level
        global_state.negative_reactions_count += 1
        global_state.teasing_level = max(0.0, global_state.teasing_level - 0.01)
        changes["teasing_level"] = {"from": old_teasing, "to": global_state.teasing_level}
        if user_state:
            user_state.likes_teasing = False
            user_state.trust = max(0.0, user_state.trust - 0.02)

    async with state_manager.session() as session:
        await session.merge(global_state)
        if changes:
            session.add(
                SelfTuningEvent(
                    reason=f"reaction:{feedback.sentiment}",
                    changes=changes,
                    applied=True,
                )
            )
        if user_state:
            await session.merge(user_state)
        await session.commit()
